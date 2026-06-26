from typing import Any

from core.models import Address
from rest_framework import serializers

from .models import (
    BillingArticle,
    Invoice,
    InvoiceLine,
    Offer,
    OfferLine,
    Reminder,
)

# ---------------------------------------------------------------------------
# Address
# ---------------------------------------------------------------------------

class AddressSerializer(serializers.ModelSerializer[Address]):
    display_name = serializers.CharField(read_only=True)

    class Meta:
        model = Address
        fields = [
            'id', 'wz_source_id', 'display_name',
            'anrede', 'vorname', 'nachname', 'firma', 'abteilung',
            'strasse', 'plz', 'ort', 'telefon', 'email', 'uid', 'anmerkung',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'wz_source_id', 'display_name', 'created_at', 'updated_at']


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
    address_display = serializers.CharField(source='address.display_name', read_only=True)
    address_email = serializers.CharField(source='address.email', read_only=True, default='')
    net_total = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    gross_total = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)

    class Meta:
        model = Offer
        fields = [
            'id', 'number', 'status', 'address', 'address_display', 'address_email',
            'document_date', 'valid_until',
            'net_total', 'gross_total',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'number', 'address_display', 'address_email', 'net_total', 'gross_total', 'created_at', 'updated_at']


class OfferSerializer(serializers.ModelSerializer[Offer]):
    address_display = serializers.CharField(source='address.display_name', read_only=True)
    address_email = serializers.CharField(source='address.email', read_only=True, default='')
    net_total = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    gross_total = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    tax_total = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    lines = OfferLineSerializer(many=True, read_only=True)

    class Meta:
        model = Offer
        fields = [
            'id', 'number', 'status', 'address', 'address_display', 'address_email',
            'recipient_text',
            'document_date', 'valid_until', 'notes',
            'net_total', 'gross_total', 'tax_total',
            'lines',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'number', 'address_display', 'address_email', 'recipient_text',
            'net_total', 'gross_total', 'tax_total',
            'created_at', 'updated_at',
        ]

    def validate(self, data: dict[str, Any]) -> dict[str, Any]:
        document_date = data.get('document_date', self.instance.document_date if self.instance else None)
        valid_until = data.get('valid_until', self.instance.valid_until if self.instance else None)
        if document_date and valid_until and valid_until < document_date:
            raise serializers.ValidationError(
                {'valid_until': 'Das Ablaufdatum darf nicht vor dem Angebotsdatum liegen.'})
        return data


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
# Invoice
# ---------------------------------------------------------------------------

class InvoiceListSerializer(serializers.ModelSerializer[Invoice]):
    """Lightweight serializer for list views (no nested lines)."""
    address_display = serializers.CharField(source='address.display_name', read_only=True)
    address_email = serializers.CharField(source='address.email', read_only=True, default='')
    net_total = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    gross_total = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    reverses_number = serializers.CharField(source='reverses.number', read_only=True, default=None)
    reversed_by_id = serializers.SerializerMethodField()

    class Meta:
        model = Invoice
        fields = [
            'id', 'number', 'status', 'address', 'address_display', 'address_email',
            'source_offer',
            'reverses', 'reverses_number', 'reversed_by_id',
            'document_date', 'due_date', 'paid_at', 'notes',
            'net_total', 'gross_total',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'number', 'address_display', 'address_email',
            'reverses', 'reverses_number', 'reversed_by_id',
            'net_total', 'gross_total',
            'created_at', 'updated_at',
        ]

    def get_reversed_by_id(self, obj: Invoice) -> int | None:
        reversal: Invoice | None = obj.reversed_by.first()
        return reversal.pk if reversal is not None else None


class InvoiceSerializer(serializers.ModelSerializer[Invoice]):
    address_display = serializers.CharField(source='address.display_name', read_only=True)
    address_email = serializers.CharField(source='address.email', read_only=True, default='')
    net_total = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    gross_total = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    tax_total = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    lines = InvoiceLineSerializer(many=True, read_only=True)
    reverses_number = serializers.CharField(source='reverses.number', read_only=True, default=None)
    reversed_by_id = serializers.SerializerMethodField()

    class Meta:
        model = Invoice
        fields = [
            'id', 'number', 'status', 'address', 'address_display', 'address_email',
            'recipient_text',
            'source_offer',
            'reverses', 'reverses_number', 'reversed_by_id',
            'document_date', 'due_date', 'notes', 'paid_at',
            'net_total', 'gross_total', 'tax_total',
            'lines',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'number', 'address_display', 'address_email', 'recipient_text',
            'reverses', 'reverses_number', 'reversed_by_id',
            'net_total', 'gross_total', 'tax_total',
            'created_at', 'updated_at',
        ]

    def get_reversed_by_id(self, obj: Invoice) -> int | None:
        reversal: Invoice | None = obj.reversed_by.first()
        return reversal.pk if reversal is not None else None

    def validate(self, data: dict[str, Any]) -> dict[str, Any]:
        document_date = data.get('document_date', self.instance.document_date if self.instance else None)
        due_date = data.get('due_date', self.instance.due_date if self.instance else None)
        if document_date and due_date and due_date < document_date:
            raise serializers.ValidationError(
                {'due_date': 'Das Fälligkeitsdatum darf nicht vor dem Rechnungsdatum liegen.'})
        return data


# ---------------------------------------------------------------------------
# Reminder
# ---------------------------------------------------------------------------

class ReminderSerializer(serializers.ModelSerializer[Reminder]):
    open_amount = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    invoice_number = serializers.CharField(source='invoice.number', read_only=True)
    invoice_address_display = serializers.CharField(source='invoice.address.display_name', read_only=True)
    invoice_address_email = serializers.CharField(source='invoice.address.email', read_only=True, default='')

    class Meta:
        model = Reminder
        fields = [
            'id', 'invoice', 'invoice_number', 'invoice_address_display', 'invoice_address_email',
            'level', 'number', 'status',
            'reminder_date', 'due_date', 'fee', 'notes',
            'open_amount',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'number', 'open_amount',
            'invoice_number', 'invoice_address_display', 'invoice_address_email',
            'created_at', 'updated_at',
        ]

    def validate(self, data: dict[str, Any]) -> dict[str, Any]:
        reminder_date = data.get('reminder_date', self.instance.reminder_date if self.instance else None)
        due_date = data.get('due_date', self.instance.due_date if self.instance else None)
        if reminder_date and due_date and due_date < reminder_date:
            raise serializers.ValidationError(
                {'due_date': 'Das Fälligkeitsdatum darf nicht vor dem Mahnungsdatum liegen.'})
        return data


# ---------------------------------------------------------------------------
# Issue / action request serializers
# ---------------------------------------------------------------------------

class IssueDocumentSerializer(serializers.Serializer[Any]):
    """Request body for the issue action — no fields required currently."""
    pass


class SyncWzSerializer(serializers.Serializer[Any]):
    """Request body for WZ address sync."""
    host = serializers.CharField()
    database = serializers.CharField()
    user = serializers.CharField()
    password = serializers.CharField()
