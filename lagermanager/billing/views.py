import datetime
import logging
from typing import Any

from auditlog.models import LogEntry
from constance import config
from core.models import Address
from core.permissions import DjangoModelPermissionsWithView, require_perm
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Q, QuerySet
from django.http import HttpResponse
from django.utils import timezone
from emails.models import EmailLog
from emails.serializers import EmailLogSerializer
from emails.services.email import AttachmentSpec, send_document_email
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer
from rest_framework.views import APIView

from .models import (
    BillingArticle,
    Invoice,
    InvoiceLine,
    NumberSequence,
    Offer,
    OfferLine,
    Reminder,
)
from .serializers import (
    AddressSerializer,
    BillingArticleSerializer,
    InvoiceLineSerializer,
    InvoiceListSerializer,
    InvoiceSerializer,
    OfferLineSerializer,
    OfferListSerializer,
    OfferSerializer,
    ReminderSerializer,
    SyncWzSerializer,
)
from .services.numbering import allocate_article_number, allocate_number
from .services.render import (
    build_email_defaults,
    render_document_html,
    render_document_pdf,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Audit-log helpers
# ---------------------------------------------------------------------------

def _serialize_log_entry(e: LogEntry, source: str = 'document') -> dict[str, Any]:
    # Plain dict instead of a DRF serializer: this is a read-only, fixed-shape
    # response with no validation or write path, so the overhead of a serializer
    # class adds nothing. LogEntry also lacks stubs, making a typed ModelSerializer
    # awkward. Revisit if a schema generator (e.g. drf-spectacular) is added.
    actor = (e.actor.get_full_name() or e.actor.username) if e.actor else None
    return {
        'id': e.pk,
        'timestamp': e.timestamp,
        'actor': actor,
        'action': e.action,
        'changes': e.changes,
        'source': source,
        'object_repr': e.object_repr,
    }


def _line_log_entries(
    parent_obj: Offer | Invoice,
    line_ct: ContentType,
    parent_fk_field: str,
) -> QuerySet[LogEntry]:
    """Return all LogEntry records for line items ever associated with parent_obj.

    Deleted lines are found via JSON path queries on the changes field (auditlog
    stores FK values as [old_pk_str, new_pk_str] in the changes dict).
    """
    parent_pk_str = str(parent_obj.pk)

    # CREATE entries have [None-str, pk]; DELETE entries have [pk, None-str].
    historic_pks: set[str] = set(
        LogEntry.objects
        .filter(content_type=line_ct)
        .filter(
            Q(**{f'changes__{parent_fk_field}__0': parent_pk_str}) |
            Q(**{f'changes__{parent_fk_field}__1': parent_pk_str})
        )
        .values_list('object_pk', flat=True)
        .distinct()
    )

    # Current lines whose updates may not touch the FK field at all.
    current_pks: set[str] = {
        str(pk) for pk in parent_obj.lines.values_list('pk', flat=True)
    }

    all_pks = historic_pks | current_pks
    if not all_pks:
        return LogEntry.objects.none()  # type: ignore[no-any-return]  # auditlog has no stubs

    return (  # type: ignore[no-any-return]  # auditlog has no stubs
        LogEntry.objects
        .filter(content_type=line_ct, object_pk__in=all_pks)
        .select_related('actor')
    )


class AuditLogHistoryMixin:
    """Adds GET /{pk}/history/ returning django-auditlog entries for this object."""

    @action(detail=True, methods=['get'], url_path='history')
    def history(self, request: Request, pk: str | None = None) -> Response:
        obj = self.get_object()  # type: ignore[attr-defined]
        ct = ContentType.objects.get_for_model(obj)
        entries = (
            LogEntry.objects
            .filter(content_type=ct, object_pk=str(obj.pk))
            .select_related('actor')
            .order_by('-timestamp')
        )
        data = [_serialize_log_entry(e) for e in entries if e.changes]
        return Response(data)


class DocumentEmailMixin:
    """Adds GET /{pk}/email-info/ and POST /{pk}/send-email/ to a document ViewSet.

    Concrete ViewSets must implement:
        _email_pdf_filename(doc) -> str
        _allowed_send_statuses()  -> tuple[str, ...]  (statuses that may be sent)
        _after_send_status()      -> str | None        (None = no status change)
    """

    def _email_pdf_filename(self, doc: Any) -> str:
        raise NotImplementedError

    def _allowed_send_statuses(self) -> tuple[str, ...]:
        raise NotImplementedError

    def _after_send_status(self) -> str | None:
        return None

    # Provided by the concrete ViewSet — declared here so mypy knows it exists.
    def get_serializer_class(self) -> type[BaseSerializer[Any]]:
        raise NotImplementedError

    @action(detail=True, methods=['get'], url_path='email-info')
    def email_info(self, request: Request, pk: str | None = None) -> Response:
        """Return email defaults (prefilled subject/body/recipient) + send history."""
        doc = self.get_object()  # type: ignore[attr-defined]
        defaults: dict[str, str] = build_email_defaults(doc)

        ct = ContentType.objects.get_for_model(doc)
        log_qs: QuerySet[EmailLog] = (
            EmailLog.objects
            .filter(content_type=ct, object_id=str(doc.pk))
            .prefetch_related('attachments')
            .select_related('sent_by')
        )
        return Response({
            'defaults': defaults,
            'log': EmailLogSerializer(log_qs, many=True).data,
        })

    @action(detail=True, methods=['post'], url_path='send-email')
    def send_email(self, request: Request, pk: str | None = None) -> Response:
        """Send the document as a PDF attachment by email and record the attempt."""
        doc = self.get_object()  # type: ignore[attr-defined]

        if doc.status not in self._allowed_send_statuses():
            return Response(
                {'detail': 'Dieses Dokument kann in seinem aktuellen Status nicht versendet werden.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        recipient: str = (request.data.get('recipient') or '').strip()
        subject: str = (request.data.get('subject') or '').strip()
        body: str = request.data.get('body') or ''
        cc: str = (request.data.get('cc') or '').strip()

        if not recipient:
            return Response(
                {'detail': 'Empfänger-E-Mail-Adresse fehlt.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            pdf_bytes: bytes = render_document_pdf(doc)
        except RuntimeError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        filename = self._email_pdf_filename(doc)
        attachment: AttachmentSpec = (filename, pdf_bytes, 'application/pdf')

        try:
            send_document_email(
                subject=subject,
                body=body,
                recipient=recipient,
                cc=cc,
                sent_by=request.user,  # type: ignore[arg-type]
                related_object=doc,
                attachments=[attachment],
            )
        except Exception as exc:
            # EmailLog row with status=FAILED was already written by the service.
            return Response(
                {'detail': f'E-Mail konnte nicht gesendet werden: {exc}'},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        new_status = self._after_send_status()
        if new_status is not None and doc.status != new_status:
            doc.status = new_status
            doc.save(update_fields=['status'])

        # Return fresh serializer data so the frontend list updates immediately.
        serializer_class = self.get_serializer_class()
        return Response(serializer_class(doc).data)


# ---------------------------------------------------------------------------
# Address
# ---------------------------------------------------------------------------

class AddressViewSet(AuditLogHistoryMixin, viewsets.ModelViewSet[Address]):
    queryset = Address.objects.all()
    serializer_class = AddressSerializer
    permission_classes = [IsAuthenticated, DjangoModelPermissionsWithView]

    def get_queryset(self) -> Any:
        qs = Address.objects.all()
        q: str | None = self.request.query_params.get('q')
        if q:
            from django.db.models import Q
            qs = qs.filter(
                Q(vorname__icontains=q)
                | Q(nachname__icontains=q)
                | Q(firma__icontains=q)
                | Q(email__icontains=q)
            )
        return qs


class WzAddressSyncView(APIView):
    """POST /api/addresses/sync-wz/ — sync addresses from Wiffzack MSSQL."""

    permission_classes = [IsAuthenticated, require_perm('core.run_import')]

    def post(self, request: Request) -> Response:
        ser = SyncWzSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data: dict[str, str] = ser.validated_data

        try:
            from core.services.wz_address_sync import sync_addresses
            count: int = sync_addresses(
                host=data['host'],
                database=data['database'],
                user=data['user'],
                password=data['password'],
            )
        except Exception as exc:
            logger.exception('WZ address sync failed')
            return Response({'error': str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({'status': 'ok', 'count': count})


# ---------------------------------------------------------------------------
# BillingArticle
# ---------------------------------------------------------------------------

class BillingArticleViewSet(viewsets.ModelViewSet[BillingArticle]):
    permission_classes = [IsAuthenticated, DjangoModelPermissionsWithView]

    def get_queryset(self) -> Any:
        qs = BillingArticle.objects.select_related('tax_rate')
        active_only: str | None = self.request.query_params.get('active')
        if active_only and active_only.lower() in ('1', 'true', 'yes'):
            qs = qs.filter(is_active=True)
        return qs

    def get_serializer_class(self) -> type[BaseSerializer[BillingArticle]]:
        return BillingArticleSerializer

    def perform_create(self, serializer: BaseSerializer[BillingArticle]) -> None:
        if not serializer.validated_data.get('article_number'):
            with transaction.atomic():
                serializer.save(article_number=allocate_article_number())
        else:
            serializer.save()


# ---------------------------------------------------------------------------
# Offer
# ---------------------------------------------------------------------------

def _snapshot_recipient(doc: Offer | Invoice) -> None:
    """Snapshot the formatted address block onto the document at issue time."""
    doc.recipient_text = doc.address.format_address_block()


class OfferViewSet(DocumentEmailMixin, AuditLogHistoryMixin, viewsets.ModelViewSet[Offer]):
    permission_classes = [IsAuthenticated, DjangoModelPermissionsWithView]

    def get_queryset(self) -> Any:
        return Offer.objects.select_related('address').prefetch_related('lines__tax_rate')

    def get_serializer_class(self) -> type[BaseSerializer[Offer]]:
        if self.action == 'list':
            return OfferListSerializer
        return OfferSerializer

    def _email_pdf_filename(self, doc: Any) -> str:
        offer: Offer = doc
        return f'angebot_{offer.number or "entwurf_" + str(offer.pk)}.pdf'

    def _allowed_send_statuses(self) -> tuple[str, ...]:
        return (Offer.Status.ISSUED, Offer.Status.SENT)

    def _after_send_status(self) -> str | None:
        return Offer.Status.SENT

    # ---- Nested lines -------------------------------------------------------

    @action(detail=True, methods=['get', 'post'], url_path='lines')
    def lines(self, request: Request, pk: str | None = None) -> Response:
        offer: Offer = self.get_object()
        if request.method == 'GET':
            qs = offer.lines.select_related('billing_article', 'tax_rate')
            return Response(OfferLineSerializer(qs, many=True).data)

        # POST — reconcile: update existing lines in-place, add new, remove absent.
        # This lets auditlog record only genuine field changes instead of
        # delete-all + create-all noise on every save.
        lines_data: list[dict[str, Any]] = request.data if isinstance(
            request.data, list) else []

        submitted_ids: set[int] = set()
        for item in lines_data:
            try:
                if item.get('id'):
                    submitted_ids.add(int(item['id']))
            except (ValueError, TypeError):
                pass

        with transaction.atomic():
            offer.lines.exclude(pk__in=submitted_ids).delete()
            existing: dict[int, OfferLine] = {
                line.pk: line
                for line in offer.lines.filter(pk__in=submitted_ids)
            }
            for idx, item in enumerate(lines_data):
                payload: dict[str, Any] = {
                    'offer': offer.pk,
                    'position': idx + 1,
                    'billing_article': item.get('billing_article'),
                    'description': item.get('description', ''),
                    'unit': item.get('unit', ''),
                    'quantity': item.get('quantity', 0),
                    'unit_price': item.get('unit_price', 0),
                    'tax_rate': item.get('tax_rate'),
                }
                line_pk = item.get('id')
                line_instance: OfferLine | None = (
                    existing.get(int(line_pk)) if line_pk else None
                )
                ser = (
                    OfferLineSerializer(line_instance, data=payload)
                    if line_instance
                    else OfferLineSerializer(data=payload)
                )
                ser.is_valid(raise_exception=True)
                ser.save()

        qs = offer.lines.select_related('billing_article', 'tax_rate')
        return Response(OfferLineSerializer(qs, many=True).data, status=status.HTTP_200_OK)

    # ---- History (parent + lines merged) ------------------------------------

    @action(detail=True, methods=['get'], url_path='history')
    def history(  # type: ignore[override]  # intentionally richer than mixin: includes line-item entries
        self, request: Request, pk: str | None = None,
    ) -> Response:
        offer: Offer = self.get_object()
        offer_ct = ContentType.objects.get_for_model(Offer)
        line_ct = ContentType.objects.get_for_model(OfferLine)

        parent_entries = (
            LogEntry.objects
            .filter(content_type=offer_ct, object_pk=str(offer.pk))
            .select_related('actor')
        )
        line_entries = _line_log_entries(offer, line_ct, 'offer')

        data = sorted(
            [_serialize_log_entry(e, 'document') for e in parent_entries if e.changes] +
            [_serialize_log_entry(e, 'line')
             for e in line_entries if e.changes],
            key=lambda x: x['timestamp'],
            reverse=True,
        )
        return Response(data)

    # ---- Issue --------------------------------------------------------------

    @action(detail=True, methods=['post'], url_path='issue')
    def issue(self, request: Request, pk: str | None = None) -> Response:
        offer: Offer = self.get_object()
        if offer.status != Offer.Status.DRAFT:
            return Response(
                {'detail': 'Nur Entwürfe können ausgestellt werden.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        with transaction.atomic():
            offer.number = allocate_number(
                NumberSequence.DocType.OFFER, offer.document_date)
            _snapshot_recipient(offer)
            offer.status = Offer.Status.ISSUED
            offer.save(update_fields=['number', 'recipient_text', 'status'])
        return Response(OfferSerializer(offer).data)

    # ---- Convert offer → invoice --------------------------------------------

    @action(detail=True, methods=['post'], url_path='convert')
    def convert(self, request: Request, pk: str | None = None) -> Response:
        offer: Offer = self.get_object()
        if offer.status in (Offer.Status.CONVERTED, Offer.Status.DRAFT):
            return Response(
                {'detail': 'Nur ausgestellte Angebote können in eine Rechnung umgewandelt werden.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        with transaction.atomic():
            due_date = offer.document_date + \
                datetime.timedelta(days=config.INVOICE_PAYMENT_TERMS_DAYS)
            invoice = Invoice.objects.create(
                address=offer.address,
                source_offer=offer,
                document_date=offer.document_date,
                due_date=due_date,
                notes=offer.notes,
                status=Invoice.Status.DRAFT,
            )
            for line in offer.lines.select_related('billing_article', 'tax_rate'):
                InvoiceLine.objects.create(
                    invoice=invoice,
                    position=line.position,
                    billing_article=line.billing_article,
                    description=line.description,
                    unit=line.unit,
                    quantity=line.quantity,
                    unit_price=line.unit_price,
                    tax_rate=line.tax_rate,
                )
            offer.status = Offer.Status.CONVERTED
            offer.save(update_fields=['status'])
        return Response(InvoiceSerializer(invoice).data, status=status.HTTP_201_CREATED)

    # ---- Guard: block mutations on non-draft offers -------------------------

    def update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        offer: Offer = self.get_object()
        if offer.status != Offer.Status.DRAFT:
            return Response(
                {'detail': 'Nur Entwürfe können bearbeitet werden.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().update(request, *args, **kwargs)

    def destroy(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        offer: Offer = self.get_object()
        if offer.status != Offer.Status.DRAFT:
            return Response(
                {'detail': 'Nur Entwürfe können gelöscht werden.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().destroy(request, *args, **kwargs)

    # ---- Duplicate ----------------------------------------------------------

    @action(detail=True, methods=['post'], url_path='duplicate')
    def duplicate(self, request: Request, pk: str | None = None) -> Response:
        offer: Offer = self.get_object()
        with transaction.atomic():
            new_offer = Offer.objects.create(
                address=offer.address,
                document_date=offer.document_date,
                valid_until=offer.valid_until,
                notes=offer.notes,
                status=Offer.Status.DRAFT,
            )
            for line in offer.lines.select_related('billing_article', 'tax_rate'):
                OfferLine.objects.create(
                    offer=new_offer,
                    position=line.position,
                    billing_article=line.billing_article,
                    description=line.description,
                    unit=line.unit,
                    quantity=line.quantity,
                    unit_price=line.unit_price,
                    tax_rate=line.tax_rate,
                )
        return Response(OfferSerializer(new_offer).data, status=status.HTTP_201_CREATED)

    # ---- Preview / PDF ------------------------------------------------------

    @action(detail=True, methods=['get'], url_path='preview')
    def preview(self, request: Request, pk: str | None = None) -> HttpResponse:
        offer: Offer = self.get_object()
        html = render_document_html(offer)
        return HttpResponse(html, content_type='text/html; charset=utf-8')

    @action(detail=True, methods=['get'], url_path='pdf')
    def pdf(self, request: Request, pk: str | None = None) -> HttpResponse:
        offer: Offer = self.get_object()
        pdf_bytes = render_document_pdf(offer)
        filename = f'angebot_{offer.number or "preview_"+str(offer.pk)}.pdf'
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response


# ---------------------------------------------------------------------------
# Invoice
# ---------------------------------------------------------------------------

def _clone_lines(src: Invoice, dst: Invoice, *, negate: bool = False) -> None:
    """Copy all line items from *src* to *dst*, optionally negating the quantity."""
    for line in src.lines.select_related('billing_article', 'tax_rate'):
        InvoiceLine.objects.create(
            invoice=dst,
            position=line.position,
            billing_article=line.billing_article,
            description=line.description,
            unit=line.unit,
            quantity=-line.quantity if negate else line.quantity,
            unit_price=line.unit_price,
            tax_rate=line.tax_rate,
        )


class InvoiceViewSet(DocumentEmailMixin, AuditLogHistoryMixin, viewsets.ModelViewSet[Invoice]):
    permission_classes = [IsAuthenticated, DjangoModelPermissionsWithView]

    def get_queryset(self) -> Any:
        return (
            Invoice.objects
            .select_related('address', 'source_offer', 'reverses')
            .prefetch_related('lines__tax_rate', 'reversed_by')
        )

    def get_serializer_class(self) -> type[BaseSerializer[Invoice]]:
        if self.action == 'list':
            return InvoiceListSerializer
        return InvoiceSerializer

    def _email_pdf_filename(self, doc: Any) -> str:
        invoice: Invoice = doc
        return f'rechnung_{invoice.number or invoice.pk}.pdf'

    def _allowed_send_statuses(self) -> tuple[str, ...]:
        return (Invoice.Status.ISSUED, Invoice.Status.SENT)

    def _after_send_status(self) -> str | None:
        return Invoice.Status.SENT

    # ---- Guard: block mutations on non-draft invoices -----------------------

    def update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        invoice: Invoice = self.get_object()
        if invoice.status != Invoice.Status.DRAFT:
            return Response(
                {'detail': 'Nur Entwürfe können bearbeitet werden.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().update(request, *args, **kwargs)

    def destroy(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        invoice: Invoice = self.get_object()
        if invoice.status != Invoice.Status.DRAFT:
            return Response(
                {'detail': 'Nur Entwürfe können gelöscht werden. Ausgestellte Rechnungen müssen storniert werden.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().destroy(request, *args, **kwargs)

    # ---- Nested lines -------------------------------------------------------

    @action(detail=True, methods=['get', 'post'], url_path='lines')
    def lines(self, request: Request, pk: str | None = None) -> Response:
        invoice: Invoice = self.get_object()
        if request.method == 'GET':
            qs = invoice.lines.select_related('billing_article', 'tax_rate')
            return Response(InvoiceLineSerializer(qs, many=True).data)

        if invoice.status != Invoice.Status.DRAFT:
            return Response(
                {'detail': 'Positionen können nur bei Entwürfen geändert werden.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        lines_data: list[dict[str, Any]] = request.data if isinstance(
            request.data, list) else []

        submitted_ids: set[int] = set()
        for item in lines_data:
            try:
                if item.get('id'):
                    submitted_ids.add(int(item['id']))
            except (ValueError, TypeError):
                pass

        with transaction.atomic():
            invoice.lines.exclude(pk__in=submitted_ids).delete()
            existing: dict[int, InvoiceLine] = {
                line.pk: line
                for line in invoice.lines.filter(pk__in=submitted_ids)
            }
            for idx, item in enumerate(lines_data):
                payload: dict[str, Any] = {
                    'invoice': invoice.pk,
                    'position': idx + 1,
                    'billing_article': item.get('billing_article'),
                    'description': item.get('description', ''),
                    'unit': item.get('unit', ''),
                    'quantity': item.get('quantity', 0),
                    'unit_price': item.get('unit_price', 0),
                    'tax_rate': item.get('tax_rate'),
                }
                line_pk = item.get('id')
                line_instance: InvoiceLine | None = (
                    existing.get(int(line_pk)) if line_pk else None
                )
                ser = (
                    InvoiceLineSerializer(line_instance, data=payload)
                    if line_instance
                    else InvoiceLineSerializer(data=payload)
                )
                ser.is_valid(raise_exception=True)
                ser.save()

        qs = invoice.lines.select_related('billing_article', 'tax_rate')
        return Response(InvoiceLineSerializer(qs, many=True).data, status=status.HTTP_200_OK)

    # ---- History (parent + lines merged) ------------------------------------

    @action(detail=True, methods=['get'], url_path='history')
    def history(  # type: ignore[override]  # intentionally richer than mixin: includes line-item entries
        self, request: Request, pk: str | None = None,
    ) -> Response:
        invoice: Invoice = self.get_object()
        invoice_ct = ContentType.objects.get_for_model(Invoice)
        line_ct = ContentType.objects.get_for_model(InvoiceLine)

        parent_entries = (
            LogEntry.objects
            .filter(content_type=invoice_ct, object_pk=str(invoice.pk))
            .select_related('actor')
        )
        line_entries = _line_log_entries(invoice, line_ct, 'invoice')

        data = sorted(
            [_serialize_log_entry(e, 'document') for e in parent_entries if e.changes] +
            [_serialize_log_entry(e, 'line')
             for e in line_entries if e.changes],
            key=lambda x: x['timestamp'],
            reverse=True,
        )
        return Response(data)

    # ---- Issue --------------------------------------------------------------

    @action(detail=True, methods=['post'], url_path='issue')
    def issue(self, request: Request, pk: str | None = None) -> Response:
        invoice: Invoice = self.get_object()
        if invoice.status != Invoice.Status.DRAFT:
            return Response(
                {'detail': 'Nur Entwürfe können ausgestellt werden.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        with transaction.atomic():
            invoice.number = allocate_number(
                NumberSequence.DocType.INVOICE, invoice.document_date)
            _snapshot_recipient(invoice)
            invoice.status = Invoice.Status.ISSUED
            invoice.save(update_fields=['number', 'recipient_text', 'status'])
        return Response(InvoiceSerializer(invoice).data)

    # ---- Cancel / reverse ---------------------------------------------------

    @action(detail=True, methods=['post'], url_path='cancel')
    def cancel(self, request: Request, pk: str | None = None) -> Response:
        invoice: Invoice = self.get_object()
        if invoice.status not in (Invoice.Status.ISSUED, Invoice.Status.SENT):
            return Response(
                {'detail': 'Nur ausgestellte oder versendete Rechnungen können storniert werden.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        reason: str = (request.data.get('reason') or '').strip()
        if not reason:
            return Response(
                {'detail': 'Ein Stornierungsgrund ist erforderlich.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        create_draft: bool = bool(request.data.get('create_draft', False))
        with transaction.atomic():
            today = timezone.localdate()
            notes = f'Stornorechnung für Rechnung {invoice.number}\nGrund: {reason}'
            # Create the reverse (Storno) invoice as a draft first, then issue it.
            reverse = Invoice.objects.create(
                address=invoice.address,
                document_date=today,
                due_date=today,
                reverses=invoice,
                notes=notes,
                status=Invoice.Status.DRAFT,
            )
            _clone_lines(invoice, reverse, negate=True)
            reverse.number = allocate_number(
                NumberSequence.DocType.INVOICE, reverse.document_date)
            reverse.recipient_text = invoice.recipient_text
            reverse.status = Invoice.Status.ISSUED
            reverse.save(update_fields=['number', 'recipient_text', 'status'])
            # Mark the original as cancelled.
            invoice.status = Invoice.Status.CANCELLED
            invoice.save(update_fields=['status'])
            # Optionally create a new draft copy of the original invoice.
            draft: Invoice | None = None
            if create_draft:
                draft = Invoice.objects.create(
                    address=invoice.address,
                    document_date=invoice.document_date,
                    due_date=invoice.due_date,
                    notes=invoice.notes,
                    source_offer=invoice.source_offer,
                    status=Invoice.Status.DRAFT,
                )
                _clone_lines(invoice, draft)
        return Response(
            {
                'reverse': InvoiceSerializer(reverse).data,
                'draft': InvoiceSerializer(draft).data if draft else None,
            },
            status=status.HTTP_201_CREATED,
        )

    # ---- Mark paid ----------------------------------------------------------

    @action(detail=True, methods=['post'], url_path='mark-paid')
    def mark_paid(self, request: Request, pk: str | None = None) -> Response:
        invoice: Invoice = self.get_object()
        if invoice.status not in (Invoice.Status.ISSUED, Invoice.Status.SENT):
            return Response(
                {'detail': 'Nur ausgestellte oder versendete Rechnungen können als bezahlt markiert werden.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        paid_date_str: str | None = request.data.get('paid_at')
        paid_at: datetime.date
        if paid_date_str:
            try:
                paid_at = datetime.date.fromisoformat(paid_date_str)
            except ValueError:
                return Response({'detail': 'Ungültiges Datum.'}, status=status.HTTP_400_BAD_REQUEST)
        else:
            paid_at = timezone.localdate()
        invoice.status = Invoice.Status.PAID
        invoice.paid_at = paid_at
        invoice.save(update_fields=['status', 'paid_at'])
        return Response(InvoiceSerializer(invoice).data)

    # ---- Duplicate ----------------------------------------------------------

    @action(detail=True, methods=['post'], url_path='duplicate')
    def duplicate(self, request: Request, pk: str | None = None) -> Response:
        invoice: Invoice = self.get_object()
        with transaction.atomic():
            new_invoice = Invoice.objects.create(
                address=invoice.address,
                document_date=invoice.document_date,
                due_date=invoice.due_date,
                notes=invoice.notes,
                status=Invoice.Status.DRAFT,
            )
            _clone_lines(invoice, new_invoice)
        return Response(InvoiceSerializer(new_invoice).data, status=status.HTTP_201_CREATED)

    # ---- Create reminder (Mahnung) ------------------------------------------

    @action(detail=True, methods=['post'], url_path='create-reminder')
    def create_reminder(self, request: Request, pk: str | None = None) -> Response:
        invoice: Invoice = self.get_object()
        if invoice.status not in (Invoice.Status.ISSUED, Invoice.Status.SENT):
            return Response(
                {'detail': 'Mahnungen können nur für ausgestellte oder versendete Rechnungen erstellt werden.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        today = timezone.localdate()
        level = invoice.reminders.count() + 1
        reminder = Reminder.objects.create(
            invoice=invoice,
            level=min(level, 3),
            reminder_date=today,
            due_date=today + datetime.timedelta(days=14),
        )
        return Response(ReminderSerializer(reminder).data, status=status.HTTP_201_CREATED)

    # ---- Preview / PDF ------------------------------------------------------

    @action(detail=True, methods=['get'], url_path='preview')
    def preview(self, request: Request, pk: str | None = None) -> HttpResponse:
        invoice: Invoice = self.get_object()
        html = render_document_html(invoice)
        return HttpResponse(html, content_type='text/html; charset=utf-8')

    @action(detail=True, methods=['get'], url_path='pdf')
    def pdf(self, request: Request, pk: str | None = None) -> HttpResponse:
        invoice: Invoice = self.get_object()
        pdf_bytes = render_document_pdf(invoice)
        filename = f'rechnung_{invoice.number or invoice.pk}.pdf'
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response


# ---------------------------------------------------------------------------
# Reminder
# ---------------------------------------------------------------------------

class ReminderViewSet(DocumentEmailMixin, AuditLogHistoryMixin, viewsets.ModelViewSet[Reminder]):
    permission_classes = [IsAuthenticated, DjangoModelPermissionsWithView]

    def get_queryset(self) -> Any:
        qs = Reminder.objects.select_related('invoice__address')
        invoice_id_str: str | None = self.request.query_params.get(
            'invoice_id')
        if invoice_id_str:
            try:
                qs = qs.filter(invoice_id=int(invoice_id_str))
            except ValueError:
                pass
        return qs

    def get_serializer_class(self) -> type[BaseSerializer[Reminder]]:
        return ReminderSerializer

    def _email_pdf_filename(self, doc: Any) -> str:
        reminder: Reminder = doc
        return f'mahnung_{reminder.number or reminder.pk}.pdf'

    def _allowed_send_statuses(self) -> tuple[str, ...]:
        # Reminders have no SENT status; allow sending once issued (and re-sending).
        return (Reminder.Status.ISSUED,)

    def _after_send_status(self) -> str | None:
        # Reminder has no 'sent' status — leave it as 'issued'.
        return None

    @action(detail=True, methods=['post'], url_path='issue')
    def issue(self, request: Request, pk: str | None = None) -> Response:
        reminder: Reminder = self.get_object()
        if reminder.status != Reminder.Status.DRAFT:
            return Response(
                {'detail': 'Nur Entwürfe können ausgestellt werden.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        with transaction.atomic():
            reminder.number = allocate_number(
                NumberSequence.DocType.REMINDER, reminder.reminder_date)
            reminder.status = Reminder.Status.ISSUED
            reminder.save(update_fields=['number', 'status'])
        return Response(ReminderSerializer(reminder).data)

    @action(detail=True, methods=['get'], url_path='preview')
    def preview(self, request: Request, pk: str | None = None) -> HttpResponse:
        reminder: Reminder = self.get_object()
        html = render_document_html(reminder)
        return HttpResponse(html, content_type='text/html; charset=utf-8')

    @action(detail=True, methods=['get'], url_path='pdf')
    def pdf(self, request: Request, pk: str | None = None) -> HttpResponse:
        reminder: Reminder = self.get_object()
        pdf_bytes = render_document_pdf(reminder)
        filename = f'mahnung_{reminder.number or reminder.pk}.pdf'
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
