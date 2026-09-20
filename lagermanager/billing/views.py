import datetime
import logging
from decimal import Decimal, InvalidOperation
from typing import Any

from auditlog.models import LogEntry
from constance import config
from core.permissions import DjangoModelPermissionsWithView
from core.views import AuditLogHistoryMixin, _serialize_log_entry
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

from .models import (
    BillingArticle,
    Invoice,
    InvoiceLine,
    InvoiceTemplate,
    InvoiceTemplateLine,
    NumberSequence,
    Offer,
    OfferLine,
    Payment,
    Reminder,
)
from .serializers import (
    BillingArticleSerializer,
    InvoiceLineSerializer,
    InvoiceListSerializer,
    InvoiceSerializer,
    InvoiceTemplateSerializer,
    OfferLineSerializer,
    OfferListSerializer,
    OfferSerializer,
    PaymentSerializer,
    ReminderSerializer,
)
from .services import ledger
from .services.numbering import allocate_article_number, allocate_number
from .services.render import (
    build_email_defaults,
    render_document_html,
    render_document_pdf,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Audit-log helpers (billing-specific; _serialize_log_entry imported from core.views)
# ---------------------------------------------------------------------------

def _child_log_entries(
    parent_obj: Offer | Invoice,
    child_ct: ContentType,
    parent_fk_field: str,
    current_pks: set[str],
) -> QuerySet[LogEntry]:
    """Return all LogEntry records for children ever associated with parent_obj.

    Used for both line items and payments.  Deleted children are found via JSON
    path queries on the changes field (auditlog stores FK values as
    [old_pk_str, new_pk_str] in the changes dict); current_pks covers children
    whose updates never touched the FK field at all.
    """
    parent_pk_str = str(parent_obj.pk)

    # CREATE entries have [None-str, pk]; DELETE entries have [pk, None-str].
    historic_pks: set[str] = set(
        LogEntry.objects
        .filter(content_type=child_ct)
        .filter(
            Q(**{f'changes__{parent_fk_field}__0': parent_pk_str}) |
            Q(**{f'changes__{parent_fk_field}__1': parent_pk_str})
        )
        .values_list('object_pk', flat=True)
        .distinct()
    )

    all_pks = historic_pks | current_pks
    if not all_pks:
        return LogEntry.objects.none()  # type: ignore[no-any-return]  # auditlog has no stubs

    return (  # type: ignore[no-any-return]  # auditlog has no stubs
        LogEntry.objects
        .filter(content_type=child_ct, object_pk__in=all_pks)
        .select_related('actor')
    )


def _line_log_entries(
    parent_obj: Offer | Invoice,
    line_ct: ContentType,
    parent_fk_field: str,
) -> QuerySet[LogEntry]:
    """_child_log_entries for a document's line items."""
    return _child_log_entries(
        parent_obj, line_ct, parent_fk_field,
        {str(pk) for pk in parent_obj.lines.values_list('pk', flat=True)},
    )


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
        return Offer.objects.select_related('address', 'customer').prefetch_related('lines__tax_rate')

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
                customer=offer.customer,
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


def _clone_lines_to_template(src: Invoice, dst: InvoiceTemplate) -> None:
    """Copy all line items from an invoice to a template."""
    for line in src.lines.select_related('billing_article', 'tax_rate'):
        InvoiceTemplateLine.objects.create(
            template=dst,
            position=line.position,
            billing_article=line.billing_article,
            description=line.description,
            unit=line.unit,
            quantity=line.quantity,
            unit_price=line.unit_price,
            tax_rate=line.tax_rate,
        )


def _apply_available_credit(
    invoice: Invoice,
    payment_date: datetime.date,
    *,
    amount: Decimal | None = None,
    strict: bool = False,
) -> Decimal:
    """Offset the customer's unused credit against an open invoice.

    Credit is always used when there is any — the customer's money should not sit
    idle next to their own open invoice — so this is not optional at issue time.
    It stays reversible: deleting the resulting payment returns the credit.

    With amount=None it takes as much as both the credit and the open amount
    allow, and having nothing to apply is simply a no-op.  strict=True lets a
    CreditError out so an explicit request reports why it was refused.
    """
    if invoice.customer_id is None or invoice.customer is None:
        return Decimal('0.00')
    usable = min(ledger.available_credit(invoice.customer), invoice.open_amount)
    to_apply = usable if amount is None else amount
    if to_apply <= 0:
        if strict:
            raise ledger.CreditError('Es ist kein verrechenbares Guthaben vorhanden.')
        return Decimal('0.00')
    try:
        ledger.apply_credit(invoice, to_apply, payment_date)
    except ledger.CreditError:
        if strict:
            raise
        return Decimal('0.00')
    invoice.refresh_from_db()
    ledger.recalculate_invoice_status(invoice)
    invoice.refresh_from_db()
    return to_apply


class InvoiceViewSet(DocumentEmailMixin, AuditLogHistoryMixin, viewsets.ModelViewSet[Invoice]):
    permission_classes = [IsAuthenticated, DjangoModelPermissionsWithView]

    def get_queryset(self) -> Any:
        return (
            Invoice.objects
            .select_related('address', 'customer', 'source_offer', 'reverses')
            # payments/reminders back the open_amount & status properties — without
            # them the list endpoint would issue two extra queries per invoice.
            .prefetch_related('lines__tax_rate', 'reversed_by', 'payments', 'reminders')
        )

    def get_serializer_class(self) -> type[BaseSerializer[Invoice]]:
        if self.action == 'list':
            return InvoiceListSerializer
        return InvoiceSerializer

    def _email_pdf_filename(self, doc: Any) -> str:
        invoice: Invoice = doc
        return f'rechnung_{invoice.number or invoice.pk}.pdf'

    def _allowed_send_statuses(self) -> tuple[str, ...]:
        return Invoice.OPEN_STATUSES

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
        payment_ct = ContentType.objects.get_for_model(Payment)

        parent_entries = (
            LogEntry.objects
            .filter(content_type=invoice_ct, object_pk=str(invoice.pk))
            .select_related('actor')
        )
        line_entries = _line_log_entries(invoice, line_ct, 'invoice')
        payment_entries = _child_log_entries(
            invoice, payment_ct, 'invoice',
            {str(pk) for pk in invoice.payments.values_list('pk', flat=True)},
        )

        data = sorted(
            [_serialize_log_entry(e, 'document') for e in parent_entries if e.changes] +
            [_serialize_log_entry(e, 'line')
             for e in line_entries if e.changes] +
            [_serialize_log_entry(e, 'payment')
             for e in payment_entries if e.changes],
            key=lambda x: x['timestamp'],
            reverse=True,
        )
        return Response(data)

    # ---- Issue --------------------------------------------------------------

    @action(detail=True, methods=['post'], url_path='issue')
    def issue(self, request: Request, pk: str | None = None) -> Response:
        """Issue a draft invoice.

        document_date is no longer user-editable — it is always set to today,
        the date of issuance. due_date may be supplied in the request body
        (prefilled client-side to document_date + INVOICE_PAYMENT_TERMS_DAYS);
        it otherwise falls back to that same default.
        """
        invoice: Invoice = self.get_object()
        if invoice.status != Invoice.Status.DRAFT:
            return Response(
                {'detail': 'Nur Entwürfe können ausgestellt werden.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        document_date = timezone.localdate()
        due_date_str: str | None = request.data.get('due_date')
        due_date: datetime.date
        if due_date_str:
            try:
                due_date = datetime.date.fromisoformat(due_date_str)
            except ValueError:
                return Response({'detail': 'Ungültiges Fälligkeitsdatum.'}, status=status.HTTP_400_BAD_REQUEST)
        else:
            due_date = document_date + datetime.timedelta(days=config.INVOICE_PAYMENT_TERMS_DAYS)
        if due_date < document_date:
            return Response(
                {'detail': 'Das Fälligkeitsdatum darf nicht vor dem Rechnungsdatum liegen.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        applied_credit = Decimal('0.00')
        with transaction.atomic():
            invoice.document_date = document_date
            invoice.due_date = due_date
            invoice.number = allocate_number(
                NumberSequence.DocType.INVOICE, invoice.document_date)
            _snapshot_recipient(invoice)
            invoice.status = Invoice.Status.ISSUED
            invoice.save(update_fields=[
                'document_date', 'due_date', 'number', 'recipient_text', 'status',
            ])
            # Charge the customer's account, then settle what we can from credit
            # the customer already has.  available_credit() counts unconsumed
            # money, not a positive balance, so the charge above does not change
            # what may be applied here.
            ledger.record_invoice_issued(invoice)
            applied_credit = _apply_available_credit(invoice, document_date)

        data = InvoiceSerializer(invoice).data
        # Reported so the client can tell the user what was offset for them.
        data['applied_credit'] = str(applied_credit)
        return Response(data)

    @action(detail=True, methods=['post'], url_path='apply-credit')
    def apply_credit(self, request: Request, pk: str | None = None) -> Response:
        """Offset the customer's unused credit against this invoice.

        Needed for invoices that were issued before the credit existed — issue()
        offsets automatically, but only with whatever was available at the time.
        The whole invariant lives in services/ledger.apply_credit(), which is why
        PaymentSerializer refuses method=credit outright.
        """
        invoice: Invoice = self.get_object()
        if invoice.status not in Invoice.OPEN_STATUSES:
            return Response(
                {'detail': 'Guthaben kann nur bei offenen Rechnungen verrechnet werden.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        amount_raw: Any = request.data.get('amount')
        amount: Decimal | None = None
        if amount_raw not in (None, ''):
            try:
                amount = Decimal(str(amount_raw))
            except (InvalidOperation, TypeError):
                return Response({'detail': 'Ungültiger Guthabenbetrag.'},
                                status=status.HTTP_400_BAD_REQUEST)
        try:
            with transaction.atomic():
                applied = _apply_available_credit(
                    invoice, timezone.localdate(), amount=amount, strict=True)
        except ledger.CreditError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        data = InvoiceSerializer(invoice).data
        data['applied_credit'] = str(applied)
        return Response(data)

    # ---- Cancel / reverse ---------------------------------------------------

    @action(detail=True, methods=['post'], url_path='cancel')
    def cancel(self, request: Request, pk: str | None = None) -> Response:
        invoice: Invoice = self.get_object()
        if invoice.status not in Invoice.OPEN_STATUSES:
            return Response(
                {'detail': 'Nur offene Rechnungen können storniert werden.'},
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
                customer=invoice.customer,
                address=invoice.address,
                document_date=today,
                service_date=invoice.service_date,
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
            # The Storno reverses the invoice amount on the customer's account;
            # fees dunned on top of it have to be credited back explicitly.
            ledger.record_invoice_issued(reverse)
            ledger.reverse_reminder_fees(invoice)
            # Mark the original as cancelled.
            invoice.status = Invoice.Status.CANCELLED
            invoice.save(update_fields=['status'])
            # Optionally create a new draft copy of the original invoice.
            draft: Invoice | None = None
            if create_draft:
                draft = Invoice.objects.create(
                    customer=invoice.customer,
                    address=invoice.address,
                    document_date=invoice.document_date,
                    service_date=invoice.service_date,
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

    # ---- Payments -----------------------------------------------------------

    @action(detail=True, methods=['get'], url_path='payment-info')
    def payment_info(self, request: Request, pk: str | None = None) -> Response:
        """Everything the payment dialog needs in one round-trip."""
        invoice: Invoice = self.get_object()
        return Response({
            'invoice': invoice.pk,
            'number': invoice.number,
            'status': invoice.status,
            'customer': invoice.customer_id,
            'gross_total': str(invoice.gross_total),
            'reminder_fee_total': str(invoice.reminder_fee_total),
            'total_due': str(invoice.total_due),
            'paid_amount': str(invoice.paid_amount),
            'open_amount': str(invoice.open_amount),
            'payments': PaymentSerializer(
                invoice.payments.select_related('customer', 'invoice'), many=True).data,
        })

    @action(detail=True, methods=['post'], url_path='mark-paid')
    def mark_paid(self, request: Request, pk: str | None = None) -> Response:
        """Settle the invoice in full by booking one payment for the open amount.

        Kept as a convenience shortcut now that payments are first-class; the
        real work happens in PaymentViewSet.
        """
        invoice: Invoice = self.get_object()
        if invoice.status not in Invoice.OPEN_STATUSES:
            return Response(
                {'detail': 'Nur offene Rechnungen können als bezahlt markiert werden.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if invoice.customer_id is None:
            return Response(
                {'detail': 'Die Rechnung hat keinen Kunden.'},
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

        open_amount = invoice.open_amount
        if open_amount <= 0:
            # Either already settled, or a zero-total invoice with nothing to pay.
            return Response(
                {'detail': 'Die Rechnung hat keinen offenen Betrag.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            payment = Payment.objects.create(
                customer=invoice.customer,
                invoice=invoice,
                payment_date=paid_at,
                amount=open_amount,
                method=Payment.Method.TRANSFER,
            )
            ledger.record_payment(payment)
            invoice.refresh_from_db()
            ledger.recalculate_invoice_status(invoice)
        return Response(InvoiceSerializer(invoice).data)

    # ---- Duplicate ----------------------------------------------------------

    @action(detail=True, methods=['post'], url_path='duplicate')
    def duplicate(self, request: Request, pk: str | None = None) -> Response:
        invoice: Invoice = self.get_object()
        with transaction.atomic():
            new_invoice = Invoice.objects.create(
                customer=invoice.customer,
                address=invoice.address,
                document_date=invoice.document_date,
                service_date=invoice.service_date,
                due_date=invoice.due_date,
                notes=invoice.notes,
                status=Invoice.Status.DRAFT,
            )
            _clone_lines(invoice, new_invoice)
        return Response(InvoiceSerializer(new_invoice).data, status=status.HTTP_201_CREATED)

    # ---- Save as template -----------------------------------------------------

    @action(detail=True, methods=['post'], url_path='save-as-template')
    def save_as_template(self, request: Request, pk: str | None = None) -> Response:
        invoice: Invoice = self.get_object()
        name: str = (request.data.get('name') or '').strip()
        if not name:
            return Response(
                {'detail': 'Ein Name für die Vorlage ist erforderlich.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if InvoiceTemplate.objects.filter(name=name).exists():
            return Response(
                {'detail': 'Name bereits vergeben.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        with transaction.atomic():
            template = InvoiceTemplate.objects.create(name=name, notes=invoice.notes)
            _clone_lines_to_template(invoice, template)
        return Response(InvoiceTemplateSerializer(template).data, status=status.HTTP_201_CREATED)

    # ---- Create reminder (Mahnung) ------------------------------------------

    @action(detail=True, methods=['post'], url_path='create-reminder')
    def create_reminder(self, request: Request, pk: str | None = None) -> Response:
        invoice: Invoice = self.get_object()
        if invoice.status not in Invoice.OPEN_STATUSES:
            return Response(
                {'detail': 'Mahnungen können nur für offene Rechnungen erstellt werden.'},
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
# InvoiceTemplate
# ---------------------------------------------------------------------------

class InvoiceTemplateViewSet(viewsets.ModelViewSet[InvoiceTemplate]):
    permission_classes = [IsAuthenticated, DjangoModelPermissionsWithView]

    def get_queryset(self) -> Any:
        return InvoiceTemplate.objects.prefetch_related('lines__tax_rate', 'lines__billing_article')

    def get_serializer_class(self) -> type[BaseSerializer[InvoiceTemplate]]:
        return InvoiceTemplateSerializer


# ---------------------------------------------------------------------------
# Reminder
# ---------------------------------------------------------------------------

class ReminderViewSet(DocumentEmailMixin, AuditLogHistoryMixin, viewsets.ModelViewSet[Reminder]):
    permission_classes = [IsAuthenticated, DjangoModelPermissionsWithView]

    def get_queryset(self) -> Any:
        qs = Reminder.objects.select_related('invoice__address', 'invoice__customer')
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

    # ---- Guard: the fee is fixed once the reminder has gone out -------------

    def update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        reminder: Reminder = self.get_object()
        if reminder.status != Reminder.Status.DRAFT and 'fee' in request.data:
            try:
                new_fee = Decimal(str(request.data['fee']))
            except (InvalidOperation, TypeError):
                return Response({'detail': 'Ungültige Mahngebühr.'},
                                status=status.HTTP_400_BAD_REQUEST)
            if new_fee != reminder.fee:
                # The fee is already booked on the customer's account; changing
                # it here would silently desync the ledger.
                return Response(
                    {'detail': 'Die Mahngebühr kann nach dem Ausstellen nicht mehr geändert werden.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        return super().update(request, *args, **kwargs)

    @action(detail=True, methods=['post'], url_path='issue')
    def issue(self, request: Request, pk: str | None = None) -> Response:
        reminder: Reminder = self.get_object()
        if reminder.status != Reminder.Status.DRAFT:
            return Response(
                {'detail': 'Nur Entwürfe können ausgestellt werden.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # Checked here and not only at creation time: a draft written while the
        # invoice was still open goes stale the moment the customer pays, and
        # issuing it anyway would dun someone who owes nothing and charge a fee
        # that reopens a settled invoice.
        if reminder.invoice.status not in Invoice.OPEN_STATUSES:
            return Response(
                {'detail': 'Die Rechnung ist nicht mehr offen — diese Mahnung kann '
                           'nicht ausgestellt werden.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        with transaction.atomic():
            reminder.number = allocate_number(
                NumberSequence.DocType.REMINDER, reminder.reminder_date)
            reminder.status = Reminder.Status.ISSUED
            reminder.save(update_fields=['number', 'status'])
            # The fee is owed from now on: charge it and re-check the invoice,
            # whose open amount the fee has just increased.
            ledger.record_reminder_issued(reminder)
            invoice = reminder.invoice
            invoice.refresh_from_db()
            ledger.recalculate_invoice_status(invoice)
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


# ---------------------------------------------------------------------------
# Payment
# ---------------------------------------------------------------------------

class PaymentViewSet(AuditLogHistoryMixin, viewsets.ModelViewSet[Payment]):
    """Zahlungen — partial payments against an invoice, or standalone prepayments.

    Every write also books (or removes) the matching ledger entry and re-checks
    the invoice's status, so the customer's balance and the invoice's open
    amount can never drift apart from the payments themselves.
    """

    permission_classes = [IsAuthenticated, DjangoModelPermissionsWithView]

    def get_queryset(self) -> Any:
        qs = Payment.objects.select_related('customer', 'invoice')
        invoice_id_str: str | None = self.request.query_params.get('invoice_id')
        if invoice_id_str:
            try:
                qs = qs.filter(invoice_id=int(invoice_id_str))
            except ValueError:
                pass
        customer_id_str: str | None = self.request.query_params.get('customer_id')
        if customer_id_str:
            try:
                qs = qs.filter(customer_id=int(customer_id_str))
            except ValueError:
                pass
        unallocated: str | None = self.request.query_params.get('unallocated')
        if unallocated is not None and unallocated.lower() in ('1', 'true', 'yes'):
            qs = qs.filter(invoice__isnull=True)
        return qs

    def get_serializer_class(self) -> type[BaseSerializer[Payment]]:
        return PaymentSerializer

    def perform_create(self, serializer: BaseSerializer[Payment]) -> None:
        with transaction.atomic():
            payment: Payment = serializer.save()
            ledger.record_payment(payment)
            self._resync_invoice(payment.invoice)

    def perform_update(self, serializer: BaseSerializer[Payment]) -> None:
        previous_invoice: Invoice | None = (
            serializer.instance.invoice if serializer.instance else None
        )
        with transaction.atomic():
            payment: Payment = serializer.save()
            # Re-book rather than patch: the entry mirrors amount, date and
            # invoice, and any of them may have changed.
            ledger.discard_payment_entries(payment)
            ledger.record_payment(payment)
            self._resync_invoice(payment.invoice)
            if previous_invoice is not None and previous_invoice.pk != payment.invoice_id:
                self._resync_invoice(previous_invoice)

    def perform_destroy(self, instance: Payment) -> None:
        invoice: Invoice | None = instance.invoice
        with transaction.atomic():
            # Drop the ledger entry too, or the balance would keep counting money
            # that is no longer recorded.  The audit log preserves that both existed.
            ledger.discard_payment_entries(instance)
            instance.delete()
            self._resync_invoice(invoice)

    @staticmethod
    def _resync_invoice(invoice: Invoice | None) -> None:
        if invoice is None:
            return
        invoice.refresh_from_db()
        ledger.recalculate_invoice_status(invoice)
