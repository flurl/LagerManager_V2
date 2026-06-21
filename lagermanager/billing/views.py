import datetime
import logging
from typing import Any

from constance import config

from core.models import Address
from core.permissions import DjangoModelPermissionsWithView, require_perm
from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
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
from .services.render import render_document_html, render_document_pdf

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Address
# ---------------------------------------------------------------------------

class AddressViewSet(viewsets.ModelViewSet[Address]):
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


class OfferViewSet(viewsets.ModelViewSet[Offer]):
    permission_classes = [IsAuthenticated, DjangoModelPermissionsWithView]

    def get_queryset(self) -> Any:
        return Offer.objects.select_related('address').prefetch_related('lines__tax_rate')

    def get_serializer_class(self) -> type[BaseSerializer[Offer]]:
        if self.action == 'list':
            return OfferListSerializer
        return OfferSerializer

    # ---- Nested lines -------------------------------------------------------

    @action(detail=True, methods=['get', 'post'], url_path='lines')
    def lines(self, request: Request, pk: str | None = None) -> Response:
        offer: Offer = self.get_object()
        if request.method == 'GET':
            qs = offer.lines.select_related('billing_article', 'tax_rate')
            return Response(OfferLineSerializer(qs, many=True).data)

        # POST — replace all lines atomically
        lines_data: list[dict[str, Any]] = request.data if isinstance(
            request.data, list) else []
        with transaction.atomic():
            offer.lines.all().delete()
            for item in lines_data:
                item['offer'] = offer.pk
                ser = OfferLineSerializer(data=item)
                ser.is_valid(raise_exception=True)
                ser.save()
        qs = offer.lines.select_related('billing_article', 'tax_rate')
        return Response(OfferLineSerializer(qs, many=True).data, status=status.HTTP_200_OK)

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
            due_date = offer.document_date + datetime.timedelta(days=config.INVOICE_PAYMENT_TERMS_DAYS)
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

class InvoiceViewSet(viewsets.ModelViewSet[Invoice]):
    permission_classes = [IsAuthenticated, DjangoModelPermissionsWithView]

    def get_queryset(self) -> Any:
        return Invoice.objects.select_related('address', 'source_offer').prefetch_related('lines__tax_rate')

    def get_serializer_class(self) -> type[BaseSerializer[Invoice]]:
        if self.action == 'list':
            return InvoiceListSerializer
        return InvoiceSerializer

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
        with transaction.atomic():
            invoice.lines.all().delete()
            for item in lines_data:
                item['invoice'] = invoice.pk
                ser = InvoiceLineSerializer(data=item)
                ser.is_valid(raise_exception=True)
                ser.save()
        qs = invoice.lines.select_related('billing_article', 'tax_rate')
        return Response(InvoiceLineSerializer(qs, many=True).data, status=status.HTTP_200_OK)

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

    # ---- Cancel -------------------------------------------------------------

    @action(detail=True, methods=['post'], url_path='cancel')
    def cancel(self, request: Request, pk: str | None = None) -> Response:
        invoice: Invoice = self.get_object()
        if invoice.status not in (Invoice.Status.ISSUED, Invoice.Status.SENT):
            return Response(
                {'detail': 'Nur ausgestellte oder versendete Rechnungen können storniert werden.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        invoice.status = Invoice.Status.CANCELLED
        invoice.save(update_fields=['status'])
        return Response(InvoiceSerializer(invoice).data)

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

class ReminderViewSet(viewsets.ModelViewSet[Reminder]):
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
