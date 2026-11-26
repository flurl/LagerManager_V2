"""
Billing app models — Offers, Invoices, Reminders, BillingArticles.

Customers live in core.Customer; their addresses in core.Address (global,
optionally synced from Wiffzack POS).

Documents (Offer, Invoice, Reminder) are global — a continuous numbered ledger
independent of the accounting-period selector.
"""
import datetime
import os
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from auditlog.registry import auditlog
from django.contrib.auth.models import User
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
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


class ContinuousNumberSequence(models.Model):
    """
    Per-document-type counter that never resets.

    Its value is appended to the monthly number as a suffix (e.g. -00001) so that
    documents carry a gapless, strictly increasing number across months and years.
    allocate_number() in services/numbering.py is the only code that should mutate
    last_value.
    """

    doc_type = models.CharField(
        max_length=20, choices=NumberSequence.DocType.choices, unique=True)
    last_value = models.IntegerField(default=0)

    class Meta:
        verbose_name = 'Fortlaufende Nummernfolge'
        verbose_name_plural = 'Fortlaufende Nummernfolgen'

    def __str__(self) -> str:
        return f'{self.doc_type} (fortlaufend): {self.last_value}'


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
    # Who the document is for.  Nullable at DB level only because rows from
    # before customers existed had none (the one-off backfill_customers_and_ledger
    # command, since removed, filled them in); the serializers require it for
    # every new document.
    customer = models.ForeignKey(
        'core.Customer', on_delete=models.PROTECT,
        null=True, blank=True, related_name='offers')
    # Which of the customer's addresses the document is sent to.
    address = models.ForeignKey(
        'core.Address', on_delete=models.PROTECT, related_name='offers')

    # Snapshotted at issue time so the document is immutable thereafter
    recipient_text = models.TextField(blank=True)

    document_date = models.DateField()
    valid_until = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Ergänzungen / Dateien hanging off this document (see DocumentAttachment).
    attachments = GenericRelation('billing.DocumentAttachment')

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
        PARTIALLY_PAID = 'partially_paid', 'Teilweise bezahlt'
        PAID = 'paid', 'Bezahlt'
        CANCELLED = 'cancelled', 'Storniert'

    #: Statuses of an issued, not-yet-settled invoice — the ones that accept
    #: payments, reminders, sending and cancellation.
    OPEN_STATUSES = (Status.ISSUED, Status.SENT, Status.PARTIALLY_PAID)

    number = models.CharField(max_length=50, null=True,
                              blank=True, db_index=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT)
    # Who owes the money.  Nullable at DB level only because rows from before
    # customers existed had none (the one-off backfill_customers_and_ledger
    # command, since removed, filled them in); the serializers require it for
    # every new document.
    customer = models.ForeignKey(
        'core.Customer', on_delete=models.PROTECT,
        null=True, blank=True, related_name='invoices')
    # Which of the customer's addresses the invoice is sent to.
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

    reverses = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='reversed_by',
        help_text='Bei Stornorechnungen: die stornierte Originalrechnung.',
    )

    # No longer user-editable: set to today's date when the invoice is issued
    # (see InvoiceViewSet.issue). Defaults to today while still a draft.
    document_date = models.DateField(default=datetime.date.today)
    # Leistungsdatum — optional; if unset, the invoice document date applies.
    service_date = models.DateField(null=True, blank=True)
    due_date = models.DateField(default=datetime.date.today)
    notes = models.TextField(blank=True)
    # Derived, never set by hand: the payment_date of the payment that settled
    # the invoice.  services/ledger.recalculate_invoice_status() owns this field
    # and clears it whenever the invoice reopens.
    paid_at = models.DateField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Ergänzungen / Dateien hanging off this document (see DocumentAttachment).
    attachments = GenericRelation('billing.DocumentAttachment')

    if TYPE_CHECKING:
        lines: RelatedManager["InvoiceLine"]
        reversed_by: RelatedManager["Invoice"]
        reminders: RelatedManager["Reminder"]
        ledger_entries: RelatedManager["CustomerLedgerEntry"]

    class Meta:
        ordering = ['-document_date', '-pk']
        verbose_name = 'Rechnung'
        verbose_name_plural = 'Rechnungen'

    def __str__(self) -> str:
        return self.number or f'Rechnung #{self.pk} (Entwurf)'

    @property
    def is_reversal(self) -> bool:
        """True if this invoice is a Stornorechnung (reversal of another invoice)."""
        return self.reverses_id is not None

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

    # -- Payment state -----------------------------------------------------

    @property
    def reminder_fee_total(self) -> Decimal:
        """Fees of every reminder of this invoice that has been issued.

        Draft reminders are excluded: their fee is not owed until the reminder
        goes out.
        """
        return sum(
            (r.fee for r in self.reminders.all()
             if r.status != Reminder.Status.DRAFT),
            Decimal('0.00'),
        )

    @property
    def total_due(self) -> Decimal:
        """Everything the customer owes on this invoice, reminder fees included."""
        return self.gross_total + self.reminder_fee_total

    def _settlements(self) -> "list[LedgerAllocation]":
        """Allocations of money (not of a Storno) onto this invoice's charges.

        Reads through the prefetchable paths in INVOICE_SETTLEMENT_PREFETCH, so a
        list endpoint pays for it once rather than per invoice.  The charges are
        the invoice's Soll entries: the invoice itself and its reminder fees.
        Payment entries also point at the invoice, as a reference, but are Haben
        and therefore skipped by the amount check.
        """
        return [
            allocation
            for entry in self.ledger_entries.all()
            if entry.amount > 0 and entry.entry_type in CustomerLedgerEntry.CHARGE_TYPES
            for allocation in entry.allocations_received.all()
            if not allocation.is_reversal
        ]

    @property
    def paid_amount(self) -> Decimal:
        """Money allocated to this invoice and its fees, applied credit included.

        Never more than the charges: an overpayment stays unallocated on the
        payment entry and is the customer's credit, not part of this invoice.
        """
        return sum(
            (a.amount for a in self._settlements()),
            Decimal('0.00'),
        )

    @property
    def applied_payments(self) -> "list[AppliedPayment]":
        """The invoice's payment list: one row per payment or applied credit.

        - every payment booked for this invoice, even one that settles nothing
          of it (paid twice, released by a cancellation, or reversed) — it
          must stay visible to be corrected, and a reversed one to show why
          the invoice reopened (see AppliedPayment.is_reversed);
        - every other money entry whose credit was applied to this invoice.
        """
        grouped: dict[int, list[LedgerAllocation]] = {}
        for allocation in self._settlements():
            grouped.setdefault(allocation.credit_entry_id, []).append(allocation)

        rows: list[AppliedPayment] = []
        for entry in self.ledger_entries.all():
            if entry.entry_type != CustomerLedgerEntry.EntryType.PAYMENT:
                continue
            own = grouped.pop(entry.pk, [])
            rows.append(AppliedPayment(
                entry=entry,
                amount=sum((a.amount for a in own), Decimal('0.00')),
                payment_date=entry.entry_date,
                is_credit=False,
            ))
        for allocations in grouped.values():
            rows.append(AppliedPayment(
                entry=allocations[0].credit_entry,
                amount=sum((a.amount for a in allocations), Decimal('0.00')),
                payment_date=max(a.allocation_date for a in allocations),
                is_credit=True,
            ))
        rows.sort(key=lambda row: (row.payment_date, row.entry.pk))
        return rows

    @property
    def paid_at_candidate(self) -> datetime.date | None:
        """Date of the latest allocation — when the invoice became (more) paid."""
        settlements = self._settlements()
        return max((a.allocation_date for a in settlements), default=None)

    @property
    def open_amount(self) -> Decimal:
        return self.total_due - self.paid_amount

    @property
    def is_fully_paid(self) -> bool:
        return self.total_due > 0 and self.open_amount <= 0


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
# InvoiceTemplate
# ---------------------------------------------------------------------------

class InvoiceTemplate(models.Model):
    """A reusable, customer-agnostic invoice blueprint (line items + notes).

    Not registered with auditlog — templates don't need change history.
    """

    name = models.CharField(max_length=255, unique=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    if TYPE_CHECKING:
        lines: RelatedManager["InvoiceTemplateLine"]

    class Meta:
        ordering = ['name']
        verbose_name = 'Rechnungsvorlage'
        verbose_name_plural = 'Rechnungsvorlagen'

    def __str__(self) -> str:
        return self.name

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


class InvoiceTemplateLine(AbstractLineItem):
    """A single line item on an invoice template."""

    template = models.ForeignKey(
        InvoiceTemplate, on_delete=models.CASCADE, related_name='lines')

    class Meta(AbstractLineItem.Meta):
        verbose_name = 'Vorlagenzeile'

    def __str__(self) -> str:
        return f'{self.template} / Pos {self.position}: {self.description}'


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

    # Ergänzungen / Dateien hanging off this document (see DocumentAttachment).
    attachments = GenericRelation('billing.DocumentAttachment')

    class Meta:
        ordering = ['-reminder_date', '-pk']
        verbose_name = 'Mahnung'
        verbose_name_plural = 'Mahnungen'

    def __str__(self) -> str:
        return self.number or f'Mahnung #{self.pk} (Entwurf)'

    @property
    def cumulative_fee(self) -> Decimal:
        """Fees of this reminder and every earlier level on the same invoice.

        A level-2 reminder duns the level-1 fee as well, so the fees accumulate.
        Other drafts are excluded — their fee is not owed yet — but this
        reminder's own fee always counts, even while it is still a draft, so a
        preview shows what the customer will be asked to pay.
        """
        return sum(
            (r.fee for r in self.invoice.reminders.all()
             if r.level <= self.level
             and (r.pk == self.pk or r.status != Reminder.Status.DRAFT)),
            Decimal('0.00'),
        )

    @property
    def open_amount(self) -> Decimal:
        """What the customer still owes: invoice + cumulative fees − payments."""
        return (
            self.invoice.gross_total
            + self.cumulative_fee
            - self.invoice.paid_amount
        )

    @property
    def payments(self) -> "list[AppliedPayment]":
        """Payments settling the dunned invoice, for the PDF template.

        A reversed payment never reached us, so the customer is not shown it.
        """
        return [p for p in self.invoice.applied_payments if not p.is_reversed]


# ---------------------------------------------------------------------------
# CustomerLedgerEntry
# ---------------------------------------------------------------------------

class CustomerLedgerEntry(models.Model):
    """
    One movement on a customer's account (Debitorenkonto).

    The customer's balance is the sum of these entries and is never stored, so
    it cannot drift.  Amounts are signed the way an accountant reads the
    account: positive is Soll — the customer owes more (an invoice, a reminder
    fee); negative is Haben — the customer owes less (a payment, a Storno, a
    reversed fee).  A positive balance means the customer owes us; a negative
    one is credit.

    The balance says nothing about *which* money settled *which* charge; that
    is LedgerAllocation's job.  An entry's open amount is its absolute amount
    minus what has been allocated from or to it.

    Entries are append-only by convention — a correction is a new entry, never
    an edit or a deletion (the Radierverbot, § 190 Abs. 3 UGB).  A payment
    booked in error is cancelled by a "Zahlung Storno": a Soll entry of the
    same amount that points at it through `reverses` and is allocated against
    it.  services/ledger.py is the only code that creates them.
    """

    class EntryType(models.TextChoices):
        INVOICE = 'invoice', 'Rechnung'
        REMINDER_FEE = 'reminder_fee', 'Mahngebühr'
        PAYMENT = 'payment', 'Zahlung'
        ADJUSTMENT = 'adjustment', 'Korrektur'
        PAYMENT_REVERSAL = 'payment_reversal', 'Zahlung Storno'

    class Method(models.TextChoices):
        TRANSFER = 'transfer', 'Überweisung'
        CASH = 'cash', 'Bar'
        CARD = 'card', 'Karte'
        OTHER = 'other', 'Sonstiges'

    #: Haben entries that undo a charge rather than bring in money.  They are
    #: allocated against the charge they reverse and never count as payments
    #: or as credit available to other invoices.  (A Zahlung Storno is the
    #: mirror image — a Soll entry undoing money — and is never a charge an
    #: invoice can be settled by, so it needs no list of its own.)
    REVERSAL_TYPES = (EntryType.INVOICE, EntryType.REMINDER_FEE)
    #: Haben entries that are money the customer has given us.
    MONEY_TYPES = (EntryType.PAYMENT, EntryType.ADJUSTMENT)
    #: Types whose Soll entries are an invoice's charges — what payments for
    #: the invoice settle.  Checked together with amount > 0, because a Storno
    #: or reversed fee has the same type on the Haben side.  A Zahlung Storno
    #: also points at the invoice and is Soll, but is no charge of it.
    CHARGE_TYPES = (EntryType.INVOICE, EntryType.REMINDER_FEE)

    customer = models.ForeignKey(
        'core.Customer', on_delete=models.PROTECT, related_name='ledger_entries')
    entry_type = models.CharField(max_length=20, choices=EntryType.choices)
    entry_date = models.DateField()
    amount = models.DecimalField(
        max_digits=18, decimal_places=2,
        help_text='Signed: positive = Soll (charge), negative = Haben (payment).')
    description = models.CharField(max_length=255, blank=True)
    # Payment details — only set on PAYMENT entries.
    method = models.CharField(
        max_length=20, choices=Method.choices, blank=True, verbose_name='Zahlungsart')
    note = models.TextField(blank=True)

    # For a charge: the document that charged it.  For a payment: the invoice
    # the customer said they were paying — a reference only.  Which charges the
    # money actually settles is recorded by LedgerAllocation.
    invoice = models.ForeignKey(
        Invoice, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='ledger_entries')
    reminder = models.ForeignKey(
        'Reminder', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='ledger_entries')
    # For a correction: the entry it cancels.  One-to-one, so an entry can be
    # reversed only once.  Only PAYMENT_REVERSAL uses it so far; a general
    # correction entry would reuse the same link.
    reverses = models.OneToOneField(
        'self', on_delete=models.PROTECT, null=True, blank=True,
        related_name='reversal', verbose_name='storniert')

    created_at = models.DateTimeField(auto_now_add=True)

    if TYPE_CHECKING:
        allocations_received: RelatedManager["LedgerAllocation"]
        allocations_given: RelatedManager["LedgerAllocation"]
        reversal: "CustomerLedgerEntry"

    class Meta:
        ordering = ['entry_date', 'pk']
        verbose_name = 'Kontobewegung'
        verbose_name_plural = 'Kontobewegungen'
        indexes = [
            models.Index(fields=['customer', 'entry_date'],
                         name='ledger_customer_date_idx'),
        ]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(amount=0),
                name='ledger_entry_amount_nonzero',
            ),
            # Money in is always Haben.
            models.CheckConstraint(
                condition=~models.Q(entry_type='payment') | models.Q(amount__lt=0),
                name='ledger_payment_is_haben',
            ),
            # A Zahlung Storno takes money back out: Soll, and always says
            # which payment it cancels.
            models.CheckConstraint(
                condition=~models.Q(entry_type='payment_reversal')
                | (models.Q(amount__gt=0) & models.Q(reverses__isnull=False)),
                name='ledger_payment_reversal_is_soll',
            ),
        ]

    def __str__(self) -> str:
        return f'{self.entry_date:%d.%m.%Y} {self.get_entry_type_display()}: {self.amount} €'

    @property
    def is_reversal(self) -> bool:
        """True for a movement that undoes an earlier charge.

        Both kinds read as a plain "Rechnung"/"Mahngebühr" otherwise, which is
        misleading next to the charge they cancel:

        - a Storno invoice's entry, which is Haben because its lines are
          negated (see services/ledger.record_invoice_issued);
        - a reminder fee credited back when an invoice is cancelled
          (services/ledger.record_cancellation), which is the only way a fee
          entry can come out negative;
        - a Zahlung Storno, which cancels a payment.
        """
        if self.entry_type == CustomerLedgerEntry.EntryType.PAYMENT_REVERSAL:
            return True
        if self.entry_type == CustomerLedgerEntry.EntryType.INVOICE:
            return bool(
                self.invoice_id and self.invoice and self.invoice.is_reversal)
        if self.entry_type == CustomerLedgerEntry.EntryType.REMINDER_FEE:
            return self.amount < 0
        return False

    @property
    def is_reversed(self) -> bool:
        """True when a later entry (a Zahlung Storno) cancels this one."""
        try:
            self.reversal  # noqa: B018 — the reverse one-to-one raises when absent
        except CustomerLedgerEntry.DoesNotExist:
            return False
        return True


# ---------------------------------------------------------------------------
# LedgerAllocation
# ---------------------------------------------------------------------------

class LedgerAllocation(models.Model):
    """
    Ausgleich — part of a Haben entry settling part of a Soll entry.

    This is what makes the ledger an open-item account: a payment settles an
    invoice (or a reminder fee) through an allocation, a prepayment is a
    payment entry with nothing allocated yet, applying credit is allocating
    that open rest, and a Storno is allocated against the invoice it cancels.

    The balance never depends on allocations — only the open amounts of the
    individual entries do.  services/ledger.py is the only writer and keeps
    both sides from being over-allocated.

    Example — invoice RE-1 over 100, payments of 60 and 70 for it, then
    invoice RE-2 over 20:

        CustomerLedgerEntry               LedgerAllocation
        id  type     amount  invoice      debit  credit  amount
        1   invoice   +100   RE-1         1      2         60   60 settle RE-1
        2   payment    -60   RE-1         1      3         40   rest of RE-1
        3   payment    -70   RE-1         4      3         20   credit → RE-2
        4   invoice    +20   RE-2

    The balance is the sum of the amounts: −10, i.e. 10 credit.  The
    allocations say who paid what: the 70 payment covers only the 40 still
    open on RE-1 (record_payment caps it); its rest of 30 is credit, of which
    apply_credit puts 20 on RE-2 when that is issued.  Open amounts follow:
    entry 1 → 100 − 60 − 40 = 0 (paid), entry 3 → 70 − 40 − 20 = 10 (the
    available credit), entry 4 → 0 (paid).

    Reversing a payment (Zahlung Storno) first removes its allocations, so
    whatever it settled reopens, then allocates the Storno against it.  A
    charge is protected while anything is allocated to it.
    """

    debit_entry = models.ForeignKey(
        CustomerLedgerEntry, on_delete=models.PROTECT,
        related_name='allocations_received', verbose_name='Soll-Buchung')
    credit_entry = models.ForeignKey(
        CustomerLedgerEntry, on_delete=models.CASCADE,
        related_name='allocations_given', verbose_name='Haben-Buchung')
    amount = models.DecimalField(max_digits=18, decimal_places=2, verbose_name='Betrag')
    # When the charge was settled: the payment date for a payment booked
    # against an invoice, the day of application when credit is used later.
    allocation_date = models.DateField(verbose_name='Ausgleichsdatum')

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['allocation_date', 'pk']
        verbose_name = 'Ausgleich'
        verbose_name_plural = 'Ausgleiche'
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name='ledger_allocation_amount_positive',
            ),
            models.UniqueConstraint(
                fields=['debit_entry', 'credit_entry'],
                name='ledger_allocation_unique_pair',
            ),
        ]

    def __str__(self) -> str:
        return f'{self.amount} € von #{self.credit_entry_id} auf #{self.debit_entry_id}'

    @property
    def is_reversal(self) -> bool:
        """True when a Storno or reversed fee settles the charge, not money."""
        return self.credit_entry.entry_type in CustomerLedgerEntry.REVERSAL_TYPES


@dataclass(frozen=True)
class AppliedPayment:
    """A payment as seen from one invoice: what of it settles that invoice.

    Not a model — the rows of Invoice.applied_payments, grouped from the
    allocations of one Haben entry.  Shaped like the old Payment model so the
    PDF templates can keep reading payment_date, amount and
    get_method_display().
    """

    entry: CustomerLedgerEntry
    amount: Decimal
    payment_date: datetime.date
    # The money was booked for something else (a prepayment, an overpayment of
    # another invoice) and applied to this invoice from the customer's credit.
    is_credit: bool

    @property
    def method(self) -> str:
        return 'credit' if self.is_credit else self.entry.method

    def get_method_display(self) -> str:
        if self.is_credit:
            return 'Guthaben'
        return self.entry.get_method_display() or self.entry.get_entry_type_display()

    @property
    def note(self) -> str:
        return self.entry.note

    @property
    def is_reversed(self) -> bool:
        """The payment was cancelled by a Zahlung Storno and settles nothing."""
        return self.entry.is_reversed

    @property
    def received(self) -> Decimal:
        """What the customer paid, as told on the Zahlungsübersicht.

        A payment booked for the invoice counts in full, so an overpayment shows
        as credit there; applied credit counts with what was applied.
        """
        return self.amount if self.is_credit else -self.entry.amount


#: Prefetch paths behind Invoice.paid_amount / open_amount / applied_payments.
INVOICE_SETTLEMENT_PREFETCH: tuple[str, ...] = (
    'ledger_entries__allocations_received__credit_entry__reversal',
    'ledger_entries__reversal',
)


# ---------------------------------------------------------------------------
# DocumentAttachment
# ---------------------------------------------------------------------------

# Upload limit per file.  Enforced by the FileHandler, not by the model, so a
# future kind may set its own.
MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024


def document_attachment_upload_path(instance: "DocumentAttachment", filename: str) -> str:
    """Store under billing_attachments/<document-model>/<document-pk>/<filename>."""
    model: str = instance.content_type.model if instance.content_type_id else 'orphaned'
    return os.path.join('billing_attachments', model, str(instance.object_id or 0), filename)


class DocumentAttachment(models.Model):
    """An attachment hanging off an Offer, Invoice or Reminder.

    The three document models share no base class, so the link to the document
    is generic — the same approach emails.EmailLog takes.  Two differences to
    EmailLog are deliberate:

    * ``object_id`` is an integer column, not a CharField.  Attachments are
      reached through a GenericRelation (for cascade delete and for the
      attachment_count annotation), and PostgreSQL cannot join bigint to
      varchar.  EmailLog only ever filters its object_id as a string.
    * The documents own their attachments: deleting a document deletes them,
      whereas an EmailLog deliberately outlives the document it refers to.

    ``kind`` is a free-form key into the handler registry (billing/attachments/)
    and deliberately carries no ``choices``, so registering a new attachment
    type needs no model change and no migration.  The serializer rejects kinds
    that are not registered.
    """

    class Delivery(models.TextChoices):
        MERGE = 'merge', 'An Dokument-PDF anhängen'
        SEPARATE = 'separate', 'Eigener Anhang'

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveBigIntegerField()
    document = GenericForeignKey('content_type', 'object_id')

    kind = models.CharField(max_length=32, db_index=True)
    position = models.PositiveIntegerField(default=0)

    # Shared payload: a short label plus long text.  Used by every kind that
    # needs them (Ergänzung: title + note text; Datei: the description).
    title = models.CharField(max_length=255, blank=True)
    body = models.TextField(blank=True)
    # Escape hatch for kinds whose payload is neither of the above (e.g. the
    # parameters of a future report generated from data).
    data = models.JSONField(default=dict, blank=True)

    # Only file-backed kinds use these.  null=True (rather than just blank) is
    # required here: "no file at all" has to be distinguishable for the
    # post_delete cleanup, unlike the legacy nullable text columns the
    # project-wide rule is about.
    file = models.FileField(
        upload_to=document_attachment_upload_path, null=True, blank=True)
    original_filename = models.CharField(max_length=255, blank=True)
    mime_type = models.CharField(max_length=100, blank=True)
    size_bytes = models.PositiveIntegerField(default=0)

    # How this attachment leaves the building when the document is emailed.
    # Only honoured for kinds whose handler supports merging.  New attachments
    # get their handler's default_delivery from the serializer; the field
    # default below is only a fallback for rows created some other way.
    delivery = models.CharField(
        max_length=20, choices=Delivery.choices, default=Delivery.MERGE)

    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['position', 'pk']
        indexes = [
            models.Index(fields=['content_type', 'object_id'],
                         name='doc_attachment_owner_idx'),
        ]
        verbose_name = 'Dokument-Anhang'
        verbose_name_plural = 'Dokument-Anhänge'

    def __str__(self) -> str:
        label: str = self.title or self.original_filename or str(self.pk)
        return f'{self.kind}: {label}'


# ---------------------------------------------------------------------------
# Audit log registration
# ---------------------------------------------------------------------------

auditlog.register(BillingArticle)
auditlog.register(Offer)
auditlog.register(OfferLine)
auditlog.register(Invoice)
auditlog.register(InvoiceLine)
auditlog.register(Reminder)
auditlog.register(CustomerLedgerEntry)
auditlog.register(LedgerAllocation)
auditlog.register(DocumentAttachment)
