from decimal import Decimal
from typing import Any

from rest_framework import serializers

from .models import (
    BillingArticle,
    CustomerLedgerEntry,
    Invoice,
    InvoiceLine,
    InvoiceTemplate,
    InvoiceTemplateLine,
    Offer,
    OfferLine,
    Payment,
    Reminder,
)

# ---------------------------------------------------------------------------
# Shared validation
# ---------------------------------------------------------------------------

def validate_customer_address(
    serializer: serializers.Serializer[Any], data: dict[str, Any],
) -> dict[str, Any]:
    """Require a customer on every document and keep address and customer in sync.

    `customer` is nullable in the database only so the backfill command can run
    on rows that predate it; every document written through the API must name
    one, and the address it is sent to has to belong to that customer.
    """
    instance = getattr(serializer, 'instance', None)
    customer = data.get('customer', instance.customer if instance else None)
    address = data.get('address', instance.address if instance else None)

    if customer is None:
        raise serializers.ValidationError({'customer': 'Ein Kunde ist erforderlich.'})
    if address is not None and address.customer_id != customer.pk:
        raise serializers.ValidationError(
            {'address': 'Die Adresse gehört nicht zu diesem Kunden.'})
    return data


# ---------------------------------------------------------------------------
# BillingArticle
# ---------------------------------------------------------------------------

class BillingArticleSerializer(serializers.ModelSerializer[BillingArticle]):
    tax_rate_percent = serializers.DecimalField(
        source='tax_rate.percent', max_digits=5, decimal_places=2, read_only=True,
    )

    class Meta:
        model = BillingArticle
        fields = [
            'id', 'article_number', 'name', 'description', 'unit',
            'unit_price', 'tax_rate', 'tax_rate_percent', 'is_active',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'tax_rate_percent', 'created_at', 'updated_at']

    def validate_article_number(self, value: str) -> str:
        if value and value.startswith('#'):
            # Allow the auto-assigned number to round-trip on updates.
            instance = getattr(self, 'instance', None)
            if instance is None or instance.article_number != value:
                raise serializers.ValidationError(
                    'Manuelle Artikelnummern dürfen nicht mit # beginnen.'
                )
        return value


# ---------------------------------------------------------------------------
# Offer lines
# ---------------------------------------------------------------------------

class OfferLineSerializer(serializers.ModelSerializer[OfferLine]):
    net_amount = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    gross_amount = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    tax_rate_percent = serializers.DecimalField(
        source='tax_rate.percent', max_digits=5, decimal_places=2, read_only=True,
    )
    billing_article_name = serializers.CharField(source='billing_article.name', read_only=True)

    class Meta:
        model = OfferLine
        fields = [
            'id', 'offer', 'position',
            'billing_article', 'billing_article_name',
            'description', 'unit', 'quantity', 'unit_price',
            'tax_rate', 'tax_rate_percent',
            'net_amount', 'gross_amount',
        ]
        read_only_fields = ['id', 'net_amount', 'gross_amount', 'tax_rate_percent', 'billing_article_name']


# ---------------------------------------------------------------------------
# Offer
# ---------------------------------------------------------------------------

class OfferListSerializer(serializers.ModelSerializer[Offer]):
    """Lightweight serializer for list views (no nested lines)."""
    customer_display = serializers.CharField(source='customer.display_name', read_only=True)
    address_display = serializers.CharField(source='address.display_name', read_only=True)
    address_email = serializers.CharField(source='address.email', read_only=True, default='')
    net_total = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    gross_total = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)

    class Meta:
        model = Offer
        fields = [
            'id', 'number', 'status',
            'customer', 'customer_display',
            'address', 'address_display', 'address_email',
            'document_date', 'valid_until',
            'net_total', 'gross_total',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'number', 'customer_display', 'address_display', 'address_email',
            'net_total', 'gross_total', 'created_at', 'updated_at',
        ]


class OfferSerializer(serializers.ModelSerializer[Offer]):
    customer_display = serializers.CharField(source='customer.display_name', read_only=True)
    address_display = serializers.CharField(source='address.display_name', read_only=True)
    address_email = serializers.CharField(source='address.email', read_only=True, default='')
    net_total = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    gross_total = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    tax_total = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    lines = OfferLineSerializer(many=True, read_only=True)

    class Meta:
        model = Offer
        fields = [
            'id', 'number', 'status',
            'customer', 'customer_display',
            'address', 'address_display', 'address_email',
            'recipient_text',
            'document_date', 'valid_until', 'notes',
            'net_total', 'gross_total', 'tax_total',
            'lines',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'number', 'customer_display', 'address_display', 'address_email',
            'recipient_text',
            'net_total', 'gross_total', 'tax_total',
            'created_at', 'updated_at',
        ]

    def validate(self, data: dict[str, Any]) -> dict[str, Any]:
        document_date = data.get('document_date', self.instance.document_date if self.instance else None)
        valid_until = data.get('valid_until', self.instance.valid_until if self.instance else None)
        if document_date and valid_until and valid_until < document_date:
            raise serializers.ValidationError(
                {'valid_until': 'Das Ablaufdatum darf nicht vor dem Angebotsdatum liegen.'})
        return validate_customer_address(self, data)


# ---------------------------------------------------------------------------
# Invoice lines
# ---------------------------------------------------------------------------

class InvoiceLineSerializer(serializers.ModelSerializer[InvoiceLine]):
    net_amount = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    gross_amount = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    tax_rate_percent = serializers.DecimalField(
        source='tax_rate.percent', max_digits=5, decimal_places=2, read_only=True,
    )
    billing_article_name = serializers.CharField(source='billing_article.name', read_only=True)

    class Meta:
        model = InvoiceLine
        fields = [
            'id', 'invoice', 'position',
            'billing_article', 'billing_article_name',
            'description', 'unit', 'quantity', 'unit_price',
            'tax_rate', 'tax_rate_percent',
            'net_amount', 'gross_amount',
        ]
        read_only_fields = ['id', 'net_amount', 'gross_amount', 'tax_rate_percent', 'billing_article_name']


# ---------------------------------------------------------------------------
# Payment
# ---------------------------------------------------------------------------

class PaymentSerializer(serializers.ModelSerializer[Payment]):
    customer_display = serializers.CharField(source='customer.display_name', read_only=True)
    method_display = serializers.CharField(source='get_method_display', read_only=True)
    invoice_number = serializers.CharField(source='invoice.number', read_only=True, default=None)

    class Meta:
        model = Payment
        fields = [
            'id', 'customer', 'customer_display',
            'invoice', 'invoice_number',
            'payment_date', 'amount', 'method', 'method_display', 'note',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'customer_display', 'invoice_number', 'method_display',
            'created_at', 'updated_at',
        ]

    def validate_amount(self, value: Decimal) -> Decimal:
        if value <= 0:
            raise serializers.ValidationError('Der Betrag muss größer als 0 sein.')
        return value

    def validate(self, data: dict[str, Any]) -> dict[str, Any]:
        instance: Payment | None = getattr(self, 'instance', None)
        customer = data.get('customer', instance.customer if instance else None)
        invoice = data.get('invoice', instance.invoice if instance else None)
        method = data.get('method', instance.method if instance else None)

        if method == Payment.Method.CREDIT:
            # A credit application moves no money: it books no ledger entry, so
            # accepting one here would let an invoice be settled from credit the
            # customer does not have, without a trace on the account.  The whole
            # invariant lives in services/ledger.apply_credit(), reachable through
            # POST /invoices/{id}/apply-credit/.
            raise serializers.ValidationError(
                {'method': 'Guthaben wird nicht als Zahlung erfasst, sondern über '
                           '„Guthaben verrechnen" bei der Rechnung gebucht.'})

        if invoice is None:
            # A payment without an invoice is a prepayment; it only raises the
            # customer's balance and becomes credit.
            return data

        if invoice.customer_id != customer.pk:
            raise serializers.ValidationError(
                {'invoice': 'Die Rechnung gehört nicht zu diesem Kunden.'})
        if invoice.status == Invoice.Status.DRAFT:
            raise serializers.ValidationError(
                {'invoice': 'Für Entwürfe können keine Zahlungen erfasst werden.'})
        if invoice.status == Invoice.Status.CANCELLED:
            raise serializers.ValidationError(
                {'invoice': 'Für stornierte Rechnungen können keine Zahlungen erfasst werden.'})
        return data


class CustomerLedgerEntrySerializer(serializers.ModelSerializer[CustomerLedgerEntry]):
    entry_type_display = serializers.CharField(source='get_entry_type_display', read_only=True)
    invoice_number = serializers.CharField(source='invoice.number', read_only=True, default=None)

    class Meta:
        model = CustomerLedgerEntry
        fields = [
            'id', 'customer', 'entry_type', 'entry_type_display', 'entry_date',
            'amount', 'description', 'invoice', 'invoice_number', 'reminder',
            'payment', 'created_at',
        ]
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Invoice
# ---------------------------------------------------------------------------

class InvoiceListSerializer(serializers.ModelSerializer[Invoice]):
    """Lightweight serializer for list views (no nested lines)."""
    customer_display = serializers.CharField(source='customer.display_name', read_only=True)
    address_display = serializers.CharField(source='address.display_name', read_only=True)
    address_email = serializers.CharField(source='address.email', read_only=True, default='')
    net_total = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    gross_total = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    reminder_fee_total = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    total_due = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    paid_amount = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    open_amount = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    reverses_number = serializers.CharField(source='reverses.number', read_only=True, default=None)
    reversed_by_id = serializers.SerializerMethodField()

    class Meta:
        model = Invoice
        fields = [
            'id', 'number', 'status',
            'customer', 'customer_display',
            'address', 'address_display', 'address_email',
            'source_offer',
            'reverses', 'reverses_number', 'reversed_by_id',
            'document_date', 'service_date', 'due_date', 'paid_at', 'notes',
            'net_total', 'gross_total',
            'reminder_fee_total', 'total_due', 'paid_amount', 'open_amount',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'number', 'customer_display', 'address_display', 'address_email',
            'reverses', 'reverses_number', 'reversed_by_id',
            # document_date/due_date are no longer user-editable; both are set
            # by InvoiceViewSet.issue() when the invoice is issued.
            'document_date', 'due_date',
            'net_total', 'gross_total',
            'reminder_fee_total', 'total_due', 'paid_amount', 'open_amount',
            'created_at', 'updated_at',
        ]

    def get_reversed_by_id(self, obj: Invoice) -> int | None:
        reversal: Invoice | None = obj.reversed_by.first()
        return reversal.pk if reversal is not None else None


class InvoiceSerializer(serializers.ModelSerializer[Invoice]):
    customer_display = serializers.CharField(source='customer.display_name', read_only=True)
    address_display = serializers.CharField(source='address.display_name', read_only=True)
    address_email = serializers.CharField(source='address.email', read_only=True, default='')
    net_total = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    gross_total = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    tax_total = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    reminder_fee_total = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    total_due = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    paid_amount = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    open_amount = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    lines = InvoiceLineSerializer(many=True, read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)
    reverses_number = serializers.CharField(source='reverses.number', read_only=True, default=None)
    reversed_by_id = serializers.SerializerMethodField()

    class Meta:
        model = Invoice
        fields = [
            'id', 'number', 'status',
            'customer', 'customer_display',
            'address', 'address_display', 'address_email',
            'recipient_text',
            'source_offer',
            'reverses', 'reverses_number', 'reversed_by_id',
            'document_date', 'service_date', 'due_date', 'notes', 'paid_at',
            'net_total', 'gross_total', 'tax_total',
            'reminder_fee_total', 'total_due', 'paid_amount', 'open_amount',
            'lines', 'payments',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'number', 'customer_display', 'address_display', 'address_email',
            'recipient_text',
            'reverses', 'reverses_number', 'reversed_by_id',
            # document_date/due_date are no longer user-editable; both are set
            # by InvoiceViewSet.issue() when the invoice is issued.
            'document_date', 'due_date', 'paid_at',
            'net_total', 'gross_total', 'tax_total',
            'reminder_fee_total', 'total_due', 'paid_amount', 'open_amount',
            'payments',
            'created_at', 'updated_at',
        ]

    def get_reversed_by_id(self, obj: Invoice) -> int | None:
        reversal: Invoice | None = obj.reversed_by.first()
        return reversal.pk if reversal is not None else None

    def validate(self, data: dict[str, Any]) -> dict[str, Any]:
        return validate_customer_address(self, data)


# ---------------------------------------------------------------------------
# InvoiceTemplate
# ---------------------------------------------------------------------------

class InvoiceTemplateLineSerializer(serializers.ModelSerializer[InvoiceTemplateLine]):
    net_amount = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    gross_amount = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    tax_rate_percent = serializers.DecimalField(
        source='tax_rate.percent', max_digits=5, decimal_places=2, read_only=True,
    )
    billing_article_name = serializers.CharField(source='billing_article.name', read_only=True)

    class Meta:
        model = InvoiceTemplateLine
        fields = [
            'id', 'position',
            'billing_article', 'billing_article_name',
            'description', 'unit', 'quantity', 'unit_price',
            'tax_rate', 'tax_rate_percent',
            'net_amount', 'gross_amount',
        ]
        read_only_fields = ['id', 'net_amount', 'gross_amount', 'tax_rate_percent', 'billing_article_name']


class InvoiceTemplateSerializer(serializers.ModelSerializer[InvoiceTemplate]):
    net_total = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    gross_total = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    lines = InvoiceTemplateLineSerializer(many=True, read_only=True)

    class Meta:
        model = InvoiceTemplate
        fields = [
            'id', 'name', 'notes',
            'net_total', 'gross_total',
            'lines',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'net_total', 'gross_total', 'created_at', 'updated_at']


# ---------------------------------------------------------------------------
# Reminder
# ---------------------------------------------------------------------------

class ReminderSerializer(serializers.ModelSerializer[Reminder]):
    open_amount = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    cumulative_fee = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    invoice_number = serializers.CharField(source='invoice.number', read_only=True)
    invoice_address_display = serializers.CharField(source='invoice.address.display_name', read_only=True)
    invoice_address_email = serializers.CharField(source='invoice.address.email', read_only=True, default='')

    class Meta:
        model = Reminder
        fields = [
            'id', 'invoice', 'invoice_number', 'invoice_address_display', 'invoice_address_email',
            'level', 'number', 'status',
            'reminder_date', 'due_date', 'fee', 'notes',
            'open_amount', 'cumulative_fee',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'number', 'open_amount', 'cumulative_fee',
            'invoice_number', 'invoice_address_display', 'invoice_address_email',
            'created_at', 'updated_at',
        ]

    def validate(self, data: dict[str, Any]) -> dict[str, Any]:
        reminder_date = data.get('reminder_date', self.instance.reminder_date if self.instance else None)
        due_date = data.get('due_date', self.instance.due_date if self.instance else None)
        if reminder_date and due_date and due_date < reminder_date:
            raise serializers.ValidationError(
                {'due_date': 'Das Fälligkeitsdatum darf nicht vor dem Mahnungsdatum liegen.'})

        # Only on create: an existing reminder must stay editable (notes, dates)
        # even once its invoice has been settled or cancelled.  Issuing it is
        # what ReminderViewSet.issue refuses.
        if self.instance is None:
            invoice = data.get('invoice')
            if invoice is not None and invoice.status not in Invoice.OPEN_STATUSES:
                raise serializers.ValidationError(
                    {'invoice': 'Mahnungen können nur für offene Rechnungen erstellt werden.'})
        return data


# ---------------------------------------------------------------------------
# Issue / action request serializers
# ---------------------------------------------------------------------------

class IssueDocumentSerializer(serializers.Serializer[Any]):
    """Request body for the issue action — no fields required currently."""
    pass


