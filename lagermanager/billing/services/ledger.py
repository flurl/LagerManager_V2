"""
Customer ledger: balance, open items and invoice payment state.

The ledger is an open-item account (Offene-Posten-Buchhaltung):

- CustomerLedgerEntry is every movement.  Signed the accountant's way:
  positive = Soll (the customer owes more), negative = Haben (owes less).  The
  balance is their sum and is never stored; a positive balance is what the
  customer owes, a negative one is credit.
- LedgerAllocation records which Haben settles which Soll.  A payment booked
  for an invoice is allocated to it; a prepayment is a payment with nothing
  allocated; applying credit allocates that open rest; a Storno is allocated
  against the invoice it cancels, a Zahlung Storno against the payment.

Entries and allocations are written from this module and nowhere else (no
save() overrides, no signals), mirroring how allocate_number() is the only
writer of the number sequences.
"""
import datetime
from collections.abc import Iterable
from decimal import Decimal

from core.models import Customer
from django.contrib.contenttypes.models import ContentType
from django.db.models import Sum
from emails.models import EmailLog

from billing.models import (
    CustomerLedgerEntry,
    Invoice,
    LedgerAllocation,
    Reminder,
)
from billing.services.payment_supplement import sync_payment_supplement

ZERO = Decimal('0.00')
Entry = CustomerLedgerEntry


class CreditError(ValueError):
    """Raised when credit cannot be applied as requested."""


class ReversalError(ValueError):
    """Raised when a payment cannot be reversed as requested."""


# ---------------------------------------------------------------------------
# Balance and open amounts
# ---------------------------------------------------------------------------

def customer_balance(customer: Customer) -> Decimal:
    """Sum of every ledger entry of this customer.  Positive = the customer owes."""
    total: Decimal | None = (
        Entry.objects
        .filter(customer=customer)
        .aggregate(total=Sum('amount'))['total']
    )
    return total if total is not None else ZERO


def entry_open_amount(entry: CustomerLedgerEntry) -> Decimal:
    """What of this entry is not yet allocated, as a positive amount."""
    related = entry.allocations_received if entry.amount > 0 else entry.allocations_given
    allocated: Decimal | None = related.aggregate(total=Sum('amount'))['total']
    return abs(entry.amount) - (allocated or ZERO)


def _money_entries(customer: Customer) -> list[CustomerLedgerEntry]:
    """The customer's money-in entries with an unallocated rest, oldest first."""
    entries = (
        Entry.objects
        .filter(customer=customer, amount__lt=0, entry_type__in=Entry.MONEY_TYPES)
        .order_by('entry_date', 'pk')
    )
    return [e for e in entries if entry_open_amount(e) > 0]


def available_credit(customer: Customer) -> Decimal:
    """Money received from the customer that no charge has been settled with.

    Deliberately *not* "the negative part of the balance": an outstanding
    invoice raises the balance while a prepayment still sits there unused, and
    it is exactly that unused money which may be applied to another invoice.
    Stornos and reversed fees are not counted — they are allocated against the
    charge they cancel.
    """
    money_in: Decimal | None = (
        Entry.objects
        .filter(customer=customer, amount__lt=0, entry_type__in=Entry.MONEY_TYPES)
        .aggregate(total=Sum('amount'))['total']
    )
    if money_in is None:
        return ZERO
    allocated: Decimal | None = (
        LedgerAllocation.objects
        .filter(credit_entry__customer=customer,
                credit_entry__entry_type__in=Entry.MONEY_TYPES)
        .aggregate(total=Sum('amount'))['total']
    )
    remaining = -money_in - (allocated or ZERO)
    return remaining if remaining > 0 else ZERO


# ---------------------------------------------------------------------------
# Allocation
# ---------------------------------------------------------------------------

def allocate(
    debit: CustomerLedgerEntry,
    credit: CustomerLedgerEntry,
    amount: Decimal,
    allocation_date: datetime.date,
) -> Decimal:
    """Settle up to `amount` of `debit` with `credit`.  Returns what was allocated.

    Capped at both entries' open amounts, so neither side is ever
    over-allocated.  A second allocation between the same pair is added to the
    first rather than stored twice.
    """
    if debit.customer_id != credit.customer_id:
        raise CreditError('Buchungen verschiedener Kunden können nicht ausgeglichen werden.')
    amount = min(amount, entry_open_amount(debit), entry_open_amount(credit))
    if amount <= 0:
        return ZERO
    allocation: LedgerAllocation | None = LedgerAllocation.objects.filter(
        debit_entry=debit, credit_entry=credit).first()
    if allocation is None:
        LedgerAllocation.objects.create(
            debit_entry=debit, credit_entry=credit,
            amount=amount, allocation_date=allocation_date)
    else:
        allocation.amount += amount
        allocation.allocation_date = max(allocation.allocation_date, allocation_date)
        allocation.save(update_fields=['amount', 'allocation_date'])
    return amount


def invoice_charges(invoice: Invoice) -> list[CustomerLedgerEntry]:
    """The invoice's Soll entries in the order money settles them.

    Reminder fees first, oldest dunning level first, then the invoice amount —
    §1416 ABGB: without another agreement a payment goes to costs before the
    principal.
    """
    charges = list(
        Entry.objects
        .filter(invoice=invoice, amount__gt=0, entry_type__in=Entry.CHARGE_TYPES)
        .select_related('reminder')
    )
    charges.sort(key=lambda e: (
        0 if e.entry_type == Entry.EntryType.REMINDER_FEE else 1,
        e.reminder.level if e.reminder is not None else 0,
        e.entry_date,
        e.pk,
    ))
    return charges


def allocate_to_invoice(
    credit: CustomerLedgerEntry,
    invoice: Invoice,
    amount: Decimal | None = None,
    allocation_date: datetime.date | None = None,
) -> Decimal:
    """Settle `invoice` with up to `amount` of `credit` (all of its rest if None)."""
    limit = entry_open_amount(credit) if amount is None else amount
    when = allocation_date or credit.entry_date
    applied = ZERO
    for debit in invoice_charges(invoice):
        if applied >= limit:
            break
        applied += allocate(debit, credit, limit - applied, when)
    return applied


def _settlements_of(invoice: Invoice) -> Iterable[LedgerAllocation]:
    """Allocations of money (not of a Storno) onto the invoice's charges."""
    return (
        LedgerAllocation.objects
        .filter(debit_entry__invoice=invoice, debit_entry__amount__gt=0,
                debit_entry__entry_type__in=Entry.CHARGE_TYPES)
        .exclude(credit_entry__entry_type__in=Entry.REVERSAL_TYPES)
    )


# ---------------------------------------------------------------------------
# Recording charges
# ---------------------------------------------------------------------------

def record_invoice_issued(invoice: Invoice) -> CustomerLedgerEntry | None:
    """Charge the customer the invoice's gross total.

    A Storno invoice carries negated lines, so its gross total is negative and
    the entry comes out Haben — see record_cancellation() for allocating it.

    Returns None when the invoice has no customer (only possible for rows that
    predate the backfill) or a zero total.
    """
    customer: Customer | None = invoice.customer
    if customer is None:
        return None
    gross = invoice.gross_total
    if gross == 0:
        return None
    return Entry.objects.create(
        customer=customer,
        entry_type=Entry.EntryType.INVOICE,
        entry_date=invoice.document_date,
        amount=gross,
        description=f'Rechnung {invoice.number or f"#{invoice.pk}"}',
        invoice=invoice,
    )


def record_reminder_issued(reminder: Reminder) -> CustomerLedgerEntry | None:
    """Charge the customer this reminder's fee.  None when there is no fee."""
    invoice = reminder.invoice
    customer: Customer | None = invoice.customer
    if customer is None or reminder.fee == 0:
        return None
    return Entry.objects.create(
        customer=customer,
        entry_type=Entry.EntryType.REMINDER_FEE,
        entry_date=reminder.reminder_date,
        amount=reminder.fee,
        description=f'Mahngebühr {reminder.number or f"#{reminder.pk}"} '
                    f'(Rechnung {invoice.number or f"#{invoice.pk}"})',
        invoice=invoice,
        reminder=reminder,
    )


def record_cancellation(invoice: Invoice, storno: Invoice) -> None:
    """Book the Storno of `invoice` and settle the invoice with it.

    1. Money already allocated to the invoice is released — the Storno hands
       it back, so it becomes the customer's credit again.
    2. The Storno is booked and allocated against the invoice amount.
    3. The fee of every issued reminder is reversed and allocated against it;
       the Storno only covers the invoice amount itself.
    """
    LedgerAllocation.objects.filter(pk__in=[a.pk for a in _settlements_of(invoice)]).delete()

    storno_entry = record_invoice_issued(storno)
    invoice_entry: CustomerLedgerEntry | None = Entry.objects.filter(
        invoice=invoice, entry_type=Entry.EntryType.INVOICE, amount__gt=0).first()
    if storno_entry is not None and invoice_entry is not None:
        allocate(invoice_entry, storno_entry, -storno_entry.amount, storno.document_date)

    customer: Customer | None = invoice.customer
    if customer is None:
        return
    for reminder in invoice.reminders.exclude(status=Reminder.Status.DRAFT):
        if reminder.fee == 0:
            continue
        reversal = Entry.objects.create(
            customer=customer,
            entry_type=Entry.EntryType.REMINDER_FEE,
            entry_date=storno.document_date,
            amount=-reminder.fee,
            description=f'Storno Mahngebühr {reminder.number or f"#{reminder.pk}"}',
            invoice=invoice,
            reminder=reminder,
        )
        fee_entry: CustomerLedgerEntry | None = Entry.objects.filter(
            reminder=reminder, entry_type=Entry.EntryType.REMINDER_FEE, amount__gt=0).first()
        if fee_entry is not None:
            allocate(fee_entry, reversal, reminder.fee, storno.document_date)


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------

def record_payment(
    customer: Customer,
    payment_date: datetime.date,
    amount: Decimal,
    method: str = Entry.Method.TRANSFER,
    note: str = '',
    invoice: Invoice | None = None,
) -> CustomerLedgerEntry:
    """Book money received from the customer.

    With an invoice, the payment settles it — fees first — up to its open
    amount; anything beyond that stays unallocated and is the customer's
    credit.  Without one it is a prepayment and entirely credit.
    """
    if amount <= 0:
        raise ValueError('A payment amount must be positive.')
    description = (
        f'Zahlung Rechnung {invoice.number or f"#{invoice.pk}"}'
        if invoice is not None else 'Zahlung ohne Rechnungsbezug'
    )
    entry = Entry.objects.create(
        customer=customer,
        entry_type=Entry.EntryType.PAYMENT,
        entry_date=payment_date,
        amount=-amount,
        method=method,
        note=note,
        description=description,
        invoice=invoice,
    )
    if invoice is not None:
        allocate_to_invoice(entry, invoice, allocation_date=payment_date)
    return entry


def reverse_payment(
    entry: CustomerLedgerEntry,
    reason: str,
    reversal_date: datetime.date,
) -> CustomerLedgerEntry:
    """Cancel a payment booked in error with a "Zahlung Storno".

    Nothing is deleted (Radierverbot): the payment stays on the account and a
    Soll entry of the same amount cancels it.

    1. The payment's allocations are removed — every invoice or fee it settled
       reopens, and none of its money is credit any longer.
    2. The Zahlung Storno is booked, pointing at the payment, with the reason
       as its note and the payment's invoice as reference.
    3. The two are allocated against each other in full.

    Every affected invoice has its status recalculated.  To correct rather
    than just cancel, book the right payment afterwards.
    """
    if entry.entry_type != Entry.EntryType.PAYMENT:
        raise ReversalError('Nur Zahlungen können storniert werden.')
    if entry.is_reversed:
        raise ReversalError('Diese Zahlung wurde bereits storniert.')
    reason = reason.strip()
    if not reason:
        raise ReversalError('Ein Stornierungsgrund ist erforderlich.')

    invoice_ids: set[int] = {
        pk for pk in entry.allocations_given.values_list('debit_entry__invoice_id', flat=True)
        if pk is not None
    }
    if entry.invoice_id is not None:
        invoice_ids.add(entry.invoice_id)
    entry.allocations_given.all().delete()

    reversal = Entry.objects.create(
        customer_id=entry.customer_id,
        entry_type=Entry.EntryType.PAYMENT_REVERSAL,
        entry_date=reversal_date,
        amount=-entry.amount,
        description=f'Zahlung Storno – {entry.description}' if entry.description
        else 'Zahlung Storno',
        note=reason,
        invoice_id=entry.invoice_id,
        reverses=entry,
    )
    allocate(reversal, entry, reversal.amount, reversal_date)

    for invoice in Invoice.objects.filter(pk__in=invoice_ids):
        recalculate_invoice_status(invoice)
    return reversal


def apply_credit(
    invoice: Invoice,
    amount: Decimal | None = None,
    allocation_date: datetime.date | None = None,
) -> Decimal:
    """Settle `invoice` from the customer's unused money, oldest first.

    With amount=None, applies as much as both the credit and the open amount
    allow.  The balance does not change — the money is already on the ledger,
    it is only allocated — while the invoice's open amount drops.  Returns the
    amount applied.
    """
    customer: Customer | None = invoice.customer
    if customer is None:
        raise CreditError('Die Rechnung hat keinen Kunden.')

    credit = available_credit(customer)
    open_amount = invoice.open_amount
    if amount is None:
        amount = min(credit, open_amount)
        if amount <= 0:
            raise CreditError('Es ist kein verrechenbares Guthaben vorhanden.')
    if amount <= 0:
        raise CreditError('Der Guthabenbetrag muss größer als 0 sein.')
    if amount > credit:
        raise CreditError(f'Das verfügbare Guthaben beträgt nur {credit} €.')
    if amount > open_amount:
        raise CreditError(f'Der offene Rechnungsbetrag beträgt nur {open_amount} €.')

    when = allocation_date or invoice.document_date
    applied = ZERO
    for source in _money_entries(customer):
        if applied >= amount:
            break
        applied += allocate_to_invoice(source, invoice, amount - applied, when)
    return applied


def release_credit(invoice: Invoice, credit: CustomerLedgerEntry) -> Decimal:
    """Undo applying `credit` to `invoice`; the money becomes credit again.

    Only for money that was booked for something else — a payment booked for
    this invoice is cancelled with reverse_payment() instead.  Returns the amount
    released.
    """
    if credit.invoice_id == invoice.pk and credit.entry_type == Entry.EntryType.PAYMENT:
        raise CreditError('Diese Zahlung wurde für die Rechnung erfasst — '
                          'bitte die Zahlung stornieren.')
    allocations = LedgerAllocation.objects.filter(
        credit_entry=credit, debit_entry__invoice=invoice, debit_entry__amount__gt=0,
        debit_entry__entry_type__in=Entry.CHARGE_TYPES)
    released: Decimal | None = allocations.aggregate(total=Sum('amount'))['total']
    allocations.delete()
    return released or ZERO


# ---------------------------------------------------------------------------
# Invoice status
# ---------------------------------------------------------------------------

def recalculate_invoice_status(invoice: Invoice) -> None:
    """Bring status, paid_at and the Zahlungsübersicht in line with the allocations.

    The single owner of the PAID transition.  Drafts and cancelled invoices keep
    their status.  An invoice that loses its payments reopens — to SENT if it
    was ever sent, otherwise to ISSUED.

    Every change to what settles an invoice and every issued reminder ends here,
    which is why the Zahlungsübersicht is synced here too — for cancelled
    invoices as well, whose payments are released by the cancellation.
    """
    # Allocations may have changed since the invoice was loaded.
    invoice.refresh_from_db()
    sync_payment_supplement(invoice)
    if invoice.status in (Invoice.Status.DRAFT, Invoice.Status.CANCELLED):
        return

    paid = invoice.paid_amount
    total_due = invoice.total_due

    new_status: str
    new_paid_at: datetime.date | None
    if total_due > 0 and paid >= total_due:
        new_status = Invoice.Status.PAID
        new_paid_at = invoice.paid_at_candidate
    elif paid > 0:
        new_status = Invoice.Status.PARTIALLY_PAID
        new_paid_at = None
    else:
        # Nothing paid — reopen.  An invoice that was sent stays "sent"; the
        # e-mail log is the record that it went out, so we must not lose that.
        new_status = (
            Invoice.Status.SENT if _was_ever_sent(invoice) else Invoice.Status.ISSUED
        )
        new_paid_at = None

    if invoice.status != new_status or invoice.paid_at != new_paid_at:
        invoice.status = new_status
        invoice.paid_at = new_paid_at
        invoice.save(update_fields=['status', 'paid_at'])


def _was_ever_sent(invoice: Invoice) -> bool:
    """True when a successful e-mail was logged for this invoice."""
    return EmailLog.objects.filter(
        content_type=ContentType.objects.get_for_model(Invoice),
        object_id=str(invoice.pk),
        status=EmailLog.Status.SENT,
    ).exists()
