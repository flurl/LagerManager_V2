"""
Customer ledger and invoice payment state.

The customer's balance is never stored — it is the sum of that customer's
CustomerLedgerEntry rows.  Entries are written explicitly from this module and
nowhere else (no save() overrides, no signals), mirroring how allocate_number()
is the only writer of the number sequences.  That keeps the one subtle rule of
the design greppable: a Payment with method=CREDIT re-uses money that is already
on the ledger, so it books no entry.

Sign convention: negative = the customer was charged, positive = money came in.
A negative balance means the customer owes us, a positive one is credit.
"""
import datetime
from decimal import Decimal

from core.models import Customer
from django.contrib.contenttypes.models import ContentType
from django.db.models import Sum
from emails.models import EmailLog

from billing.models import CustomerLedgerEntry, Invoice, Payment, Reminder
from billing.services.payment_supplement import sync_payment_supplement

ZERO = Decimal('0.00')


# ---------------------------------------------------------------------------
# Balance
# ---------------------------------------------------------------------------

def customer_balance(customer: Customer) -> Decimal:
    """Sum of every ledger entry of this customer."""
    total: Decimal | None = (
        CustomerLedgerEntry.objects
        .filter(customer=customer)
        .aggregate(total=Sum('amount'))['total']
    )
    return total if total is not None else ZERO


def available_credit(customer: Customer) -> Decimal:
    """Money received from the customer that no invoice has consumed yet.

    Deliberately *not* "the positive part of the balance".  An outstanding
    invoice drives the balance negative while a prepayment is still sitting
    there unused, and it is exactly that unused money which may be earmarked
    against another invoice.  Defining it this way also makes the figure
    independent of whether the invoice being issued has already been charged,
    so issue() can book the charge first and apply the credit afterwards.

    Money is "consumed" by an invoice only up to that invoice's total, so an
    overpayment stays available; a cancelled invoice consumes nothing, because
    its Storno hands the money back.
    """
    paid_in: Decimal | None = (
        Payment.objects
        .filter(customer=customer)
        .exclude(method=Payment.Method.CREDIT)
        .aggregate(total=Sum('amount'))['total']
    )
    if paid_in is None:
        return ZERO

    consumed = ZERO
    invoices = (
        Invoice.objects
        .filter(customer=customer, payments__isnull=False)
        .exclude(status=Invoice.Status.CANCELLED)
        .distinct()
        .prefetch_related('lines__tax_rate', 'payments', 'reminders')
    )
    for invoice in invoices:
        # max(..., 0) guards a Storno, whose total_due is negative.
        consumed += max(min(invoice.paid_amount, invoice.total_due), ZERO)

    remaining = paid_in - consumed
    return remaining if remaining > 0 else ZERO


# ---------------------------------------------------------------------------
# Recording charges and payments
# ---------------------------------------------------------------------------

def record_invoice_issued(invoice: Invoice) -> CustomerLedgerEntry | None:
    """Charge the customer the invoice's gross total.

    A Storno invoice carries negated lines, so its gross total is negative and
    the entry comes out positive — cancelling an invoice restores the balance
    without a special case here.

    Returns None when the invoice has no customer (only possible for rows that
    predate the backfill) or a zero total.
    """
    customer: Customer | None = invoice.customer
    if customer is None:
        return None
    gross = invoice.gross_total
    if gross == 0:
        return None
    return CustomerLedgerEntry.objects.create(
        customer=customer,
        entry_type=CustomerLedgerEntry.EntryType.INVOICE,
        entry_date=invoice.document_date,
        amount=-gross,
        description=f'Rechnung {invoice.number or f"#{invoice.pk}"}',
        invoice=invoice,
    )


def record_reminder_issued(reminder: Reminder) -> CustomerLedgerEntry | None:
    """Charge the customer this reminder's fee.  None when there is no fee."""
    invoice = reminder.invoice
    customer: Customer | None = invoice.customer
    if customer is None or reminder.fee == 0:
        return None
    return CustomerLedgerEntry.objects.create(
        customer=customer,
        entry_type=CustomerLedgerEntry.EntryType.REMINDER_FEE,
        entry_date=reminder.reminder_date,
        amount=-reminder.fee,
        description=f'Mahngebühr {reminder.number or f"#{reminder.pk}"} '
                    f'(Rechnung {invoice.number or f"#{invoice.pk}"})',
        invoice=invoice,
        reminder=reminder,
    )


def reverse_reminder_fees(invoice: Invoice) -> list[CustomerLedgerEntry]:
    """Credit back the fees of every issued reminder of a cancelled invoice.

    The Storno invoice reverses the invoice amount itself; the fees dunned on
    top of it have to be reversed explicitly.
    """
    customer: Customer | None = invoice.customer
    if customer is None:
        return []
    entries: list[CustomerLedgerEntry] = []
    for reminder in invoice.reminders.exclude(status=Reminder.Status.DRAFT):
        if reminder.fee == 0:
            continue
        entries.append(CustomerLedgerEntry.objects.create(
            customer=customer,
            entry_type=CustomerLedgerEntry.EntryType.REMINDER_FEE,
            entry_date=invoice.document_date,
            amount=reminder.fee,
            description=f'Storno Mahngebühr {reminder.number or f"#{reminder.pk}"}',
            invoice=invoice,
            reminder=reminder,
        ))
    return entries


def record_payment(payment: Payment) -> CustomerLedgerEntry | None:
    """Book a payment on the ledger.

    Returns None for a credit application: that money is already on the ledger
    from the original prepayment, so booking it again would double-count it.
    """
    if not payment.affects_balance:
        return None
    if payment.invoice_id is not None and payment.invoice is not None:
        description = (
            f'Zahlung Rechnung {payment.invoice.number or f"#{payment.invoice.pk}"}'
        )
    else:
        description = 'Zahlung ohne Rechnungsbezug'
    return CustomerLedgerEntry.objects.create(
        customer=payment.customer,
        entry_type=CustomerLedgerEntry.EntryType.PAYMENT,
        entry_date=payment.payment_date,
        amount=payment.amount,
        description=description,
        invoice=payment.invoice,
        payment=payment,
    )


def discard_payment_entries(payment: Payment) -> int:
    """Remove a payment's ledger entries, e.g. when the payment is deleted.

    The audit log keeps the record that both existed.
    """
    deleted, _ = CustomerLedgerEntry.objects.filter(payment=payment).delete()
    return int(deleted)


# ---------------------------------------------------------------------------
# Credit
# ---------------------------------------------------------------------------

class CreditError(ValueError):
    """Raised when credit cannot be applied as requested."""


def apply_credit(
    invoice: Invoice,
    amount: Decimal,
    payment_date: datetime.date | None = None,
) -> Payment:
    """Apply `amount` of the customer's existing credit to `invoice`.

    Creates a Payment with method=CREDIT and — deliberately — no ledger entry:
    the credit is already on the ledger, it is only being earmarked for this
    invoice.  The balance is therefore unchanged, while the invoice's
    open_amount drops.
    """
    if invoice.customer_id is None or invoice.customer is None:
        raise CreditError('Die Rechnung hat keinen Kunden.')
    if amount <= 0:
        raise CreditError('Der Guthabenbetrag muss größer als 0 sein.')

    credit = available_credit(invoice.customer)
    if amount > credit:
        raise CreditError(
            f'Das verfügbare Guthaben beträgt nur {credit} €.')

    open_amount = invoice.open_amount
    if amount > open_amount:
        raise CreditError(
            f'Der offene Rechnungsbetrag beträgt nur {open_amount} €.')

    return Payment.objects.create(
        customer=invoice.customer,
        invoice=invoice,
        payment_date=payment_date or invoice.document_date,
        amount=amount,
        method=Payment.Method.CREDIT,
        note='Verrechnung mit Kundenguthaben',
    )


# ---------------------------------------------------------------------------
# Invoice status
# ---------------------------------------------------------------------------

def recalculate_invoice_status(invoice: Invoice) -> None:
    """Bring status, paid_at and the Zahlungsübersicht in line with the payments.

    The single owner of the PAID transition.  Drafts and cancelled invoices keep
    their status.  An invoice that loses its payments reopens — to SENT if it
    was ever sent, otherwise to ISSUED.

    Every change to an invoice's payments and every issued reminder ends here,
    which is why the Zahlungsübersicht is synced here too — for cancelled invoices as
    well, whose payments may still be corrected.
    """
    sync_payment_supplement(invoice)
    if invoice.status in (Invoice.Status.DRAFT, Invoice.Status.CANCELLED):
        return

    payments = list(invoice.payments.all())
    paid = sum((p.amount for p in payments), ZERO)
    total_due = invoice.total_due

    new_status: str
    new_paid_at: datetime.date | None
    if total_due > 0 and paid >= total_due:
        new_status = Invoice.Status.PAID
        new_paid_at = max(p.payment_date for p in payments) if payments else None
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
