"""
Billing app models — Offers, Invoices, Reminders, BillingArticles.

Addresses live in core.Address (global, optionally synced from Wiffzack POS).

Documents (Offer, Invoice, Reminder) are global — a continuous numbered ledger
independent of the accounting-period selector.
"""
import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from django.db import models

if TYPE_CHECKING:
    from django.db.models.fields.related_descriptors import RelatedManager

# ---------------------------------------------------------------------------
# BillingArticle
# ---------------------------------------------------------------------------


class BillingArticle(models.Model):
    """
    Catalogue of billable articles/services for use as line items on offers and invoices.
    Independent of the period-scoped pos_import.Article catalogue.
    """

    article_number = models.CharField(max_length=50, blank=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    unit = models.CharField(max_length=50, blank=True)
    unit_price = models.DecimalField(
        max_digits=18, decimal_places=2, default=Decimal('0.00'))
    tax_rate = models.ForeignKey(
        'deliveries.TaxRate',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='billing_articles',
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Faktura-Artikel'
        verbose_name_plural = 'Faktura-Artikel'

    def __str__(self) -> str:
        if self.article_number:
            return f'{self.article_number} – {self.name}'
        return self.name


# ---------------------------------------------------------------------------
# Number sequence
# ---------------------------------------------------------------------------

class ArticleNumberSequence(models.Model):
    """
    Single-row global counter for auto-assigned billing article numbers.
    allocate_article_number() in services/numbering.py is the only code that
    should mutate last_value.  Format: #0001, #0002, …
    """

    last_value = models.IntegerField(default=0)

    class Meta:
        verbose_name = 'Artikel-Nummernfolge'

    def __str__(self) -> str:
        return f'Artikel-Nummernfolge: {self.last_value}'


class NumberSequence(models.Model):
    """
    Per-document-type, per-month gapless numbering counter.
    The sequence resets each month.  allocate_number() in services/numbering.py
    is the only code that should mutate last_value.
    """

    class DocType(models.TextChoices):
        OFFER = 'offer', 'Angebot'
        INVOICE = 'invoice', 'Rechnung'
        REMINDER = 'reminder', 'Mahnung'

    doc_type = models.CharField(max_length=20, choices=DocType.choices)
    year = models.IntegerField()
    month = models.IntegerField()
    last_value = models.IntegerField(default=0)

    class Meta:
        unique_together = [('doc_type', 'year', 'month')]
        verbose_name = 'Nummernfolge'

    def __str__(self) -> str:
        return f'{self.doc_type} {self.year}/{self.month:02d}: {self.last_value}'


# ---------------------------------------------------------------------------
# Offer
# ---------------------------------------------------------------------------

class Offer(models.Model):
    """Angebot — a price quote sent to a customer."""

    class Status(models.TextChoices):
        DRAFT = 'draft', 'Entwurf'
        ISSUED = 'issued', 'Ausgestellt'
        SENT = 'sent', 'Versendet'
        ACCEPTED = 'accepted', 'Angenommen'
        REJECTED = 'rejected', 'Abgelehnt'
        CONVERTED = 'converted', 'In Rechnung gestellt'

    number = models.CharField(max_length=50, null=True,
                              blank=True, db_index=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT)
    address = models.ForeignKey(
        'core.Address', on_delete=models.PROTECT, related_name='offers')

    # Snapshotted at issue time so the document is immutable thereafter
    recipient_text = models.TextField(blank=True)

    document_date = models.DateField()
    valid_until = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    if TYPE_CHECKING:
        lines: RelatedManager["OfferLine"]

    class Meta:
        ordering = ['-document_date', '-pk']
        verbose_name = 'Angebot'
        verbose_name_plural = 'Angebote'

    def __str__(self) -> str:
        return self.number or f'Angebot #{self.pk} (Entwurf)'

    @property
    def net_total(self) -> Decimal:
        return sum(
            (line.net_amount for line in self.lines.all()),
            Decimal('0.00'),
        )

    @property
    def gross_total(self) -> Decimal:
        return sum(
            (line.gross_amount for line in self.lines.all()),
            Decimal('0.00'),
        )

    @property
    def tax_total(self) -> Decimal:
        return self.gross_total - self.net_total


# ---------------------------------------------------------------------------
# AbstractLineItem
# ---------------------------------------------------------------------------

class AbstractLineItem(models.Model):
    """Shared fields and computed properties for offer and invoice line items."""

    position = models.IntegerField(default=0)

    # Optional catalogue reference; may be null for free-text lines
    billing_article = models.ForeignKey(
        BillingArticle,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='%(class)s_lines',
    )

    description = models.CharField(max_length=500)
    unit = models.CharField(max_length=50, blank=True)
    quantity = models.DecimalField(
        max_digits=18, decimal_places=4, default=Decimal('1.0000'))
    unit_price = models.DecimalField(max_digits=18, decimal_places=2)
    tax_rate = models.ForeignKey(
        'deliveries.TaxRate',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='%(class)s_lines',
    )

    class Meta:
        abstract = True
        ordering = ['position']

    @property
    def net_amount(self) -> Decimal:
        return (self.quantity * self.unit_price).quantize(Decimal('0.01'))

    @property
    def tax_percent(self) -> Decimal:
        if self.tax_rate_id and self.tax_rate:
            return self.tax_rate.percent
        return Decimal('0.00')

    @property
    def gross_amount(self) -> Decimal:
        return (self.net_amount * (1 + self.tax_percent / 100)).quantize(Decimal('0.01'))


# ---------------------------------------------------------------------------
# OfferLine
# ---------------------------------------------------------------------------

class OfferLine(AbstractLineItem):
    """A single line item on an offer."""

    offer = models.ForeignKey(
        Offer, on_delete=models.CASCADE, related_name='lines')

    class Meta(AbstractLineItem.Meta):
        verbose_name = 'Angebotszeile'

    def __str__(self) -> str:
        return f'{self.offer} / Pos {self.position}: {self.description}'


# ---------------------------------------------------------------------------
# Invoice
# ---------------------------------------------------------------------------

class Invoice(models.Model):
    """Rechnung — a formal invoice to a customer."""

    class Status(models.TextChoices):
        DRAFT = 'draft', 'Entwurf'
        ISSUED = 'issued', 'Ausgestellt'
        SENT = 'sent', 'Versendet'
        PAID = 'paid', 'Bezahlt'
        CANCELLED = 'cancelled', 'Storniert'

    number = models.CharField(max_length=50, null=True,
                              blank=True, db_index=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT)
    address = models.ForeignKey(
        'core.Address', on_delete=models.PROTECT, related_name='invoices')

    # Snapshotted at issue time
    recipient_text = models.TextField(blank=True)

    source_offer = models.ForeignKey(
        Offer,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='invoices',
    )

    document_date = models.DateField()
    due_date = models.DateField(default=datetime.date.today)
    notes = models.TextField(blank=True)
    paid_at = models.DateField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    if TYPE_CHECKING:
        lines: RelatedManager["InvoiceLine"]

    class Meta:
        ordering = ['-document_date', '-pk']
        verbose_name = 'Rechnung'
        verbose_name_plural = 'Rechnungen'

    def __str__(self) -> str:
        return self.number or f'Rechnung #{self.pk} (Entwurf)'

    @property
    def net_total(self) -> Decimal:
        return sum(
            (line.net_amount for line in self.lines.all()),
            Decimal('0.00'),
        )

    @property
    def gross_total(self) -> Decimal:
        return sum(
            (line.gross_amount for line in self.lines.all()),
            Decimal('0.00'),
        )

    @property
    def tax_total(self) -> Decimal:
        return self.gross_total - self.net_total


# ---------------------------------------------------------------------------
# InvoiceLine
# ---------------------------------------------------------------------------

class InvoiceLine(AbstractLineItem):
    """A single line item on an invoice."""

    invoice = models.ForeignKey(
        Invoice, on_delete=models.CASCADE, related_name='lines')

    class Meta(AbstractLineItem.Meta):
        verbose_name = 'Rechnungszeile'

    def __str__(self) -> str:
        return f'{self.invoice} / Pos {self.position}: {self.description}'


# ---------------------------------------------------------------------------
# Reminder
# ---------------------------------------------------------------------------

class Reminder(models.Model):
    """Mahnung — a payment reminder dunning an outstanding invoice."""

    class Status(models.TextChoices):
        DRAFT = 'draft', 'Entwurf'
        ISSUED = 'issued', 'Ausgestellt'
        PAID = 'paid', 'Bezahlt'

    invoice = models.ForeignKey(
        Invoice, on_delete=models.PROTECT, related_name='reminders')
    level = models.IntegerField(default=1, help_text='Mahnstufe (1–3)')
    number = models.CharField(max_length=50, null=True,
                              blank=True, db_index=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT)

    reminder_date = models.DateField()
    due_date = models.DateField()

    # Additional fee charged with this reminder
    fee = models.DecimalField(
        max_digits=18, decimal_places=2, default=Decimal('0.00'))

    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-reminder_date', '-pk']
        verbose_name = 'Mahnung'
        verbose_name_plural = 'Mahnungen'

    def __str__(self) -> str:
        return self.number or f'Mahnung #{self.pk} (Entwurf)'

    @property
    def open_amount(self) -> Decimal:
        """Invoice gross total + reminder fee."""
        return self.invoice.gross_total + self.fee
