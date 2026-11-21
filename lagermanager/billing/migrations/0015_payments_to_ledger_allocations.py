"""
Turn Payments into ledger entries + allocations and flip the ledger sign.

Hand-written (agreed with the user): it converts data, there is no schema change.
Runs on the historical models, so everything is computed from ledger entries and
Payment rows — never from Invoice properties, which a migration cannot see.

1. Flip the sign: positive = Soll (customer owes), negative = Haben.
2. Copy each payment's method and note onto its PAYMENT entry.
3. Allocate every Storno against the invoice it cancels and every reversed
   reminder fee against the fee it reverses.
4. Allocate every real payment (not method=credit) that names an invoice
   against that invoice — fees first, then the invoice amount.  Payments on
   cancelled invoices stay unallocated: the Storno handed that money back, so
   it is credit, exactly as available_credit() treated it before.
5. Allocate every credit application (method=credit) from the customer's
   oldest payments that still have money left (FIFO).
6. Check, per invoice and per customer, that nothing moved: an invoice's paid
   amount is what its payments covered, capped at its charges, and a customer's
   available credit is the same as the old formula gave.  Abort otherwise.
7. Give every group that could view/add/delete payments the same right on
   ledger entries — the payments endpoint is guarded by those from now on.

Reversible: backwards() rebuilds the Payment rows (credit applications as
method=credit) from the entries and allocations and flips the sign back.
"""
from collections import defaultdict
from decimal import Decimal
from typing import Any

from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.models import F

ZERO = Decimal('0.00')
# Frozen copies of the choices: a migration must not change meaning when the
# application code does.
INVOICE = 'invoice'
REMINDER_FEE = 'reminder_fee'
PAYMENT = 'payment'
ADJUSTMENT = 'adjustment'
CANCELLED = 'cancelled'
CREDIT = 'credit'


class _Ledger:
    """In-memory open amounts, so allocations never over-allocate an entry."""

    def __init__(self, apps: Apps) -> None:
        self.Entry: Any = apps.get_model('billing', 'CustomerLedgerEntry')
        self.Allocation: Any = apps.get_model('billing', 'LedgerAllocation')
        self.open: dict[int, Decimal] = {
            e.pk: abs(e.amount) for e in self.Entry.objects.all()
        }

    def allocate(self, debit: Any, credit: Any, amount: Decimal, date: Any) -> Decimal:
        amount = min(amount, self.open[debit.pk], self.open[credit.pk])
        if amount <= 0:
            return ZERO
        allocation = self.Allocation.objects.filter(
            debit_entry=debit, credit_entry=credit).first()
        if allocation is None:
            self.Allocation.objects.create(
                debit_entry=debit, credit_entry=credit, amount=amount,
                allocation_date=date)
        else:
            allocation.amount += amount
            allocation.allocation_date = max(allocation.allocation_date, date)
            allocation.save(update_fields=['amount', 'allocation_date'])
        self.open[debit.pk] -= amount
        self.open[credit.pk] -= amount
        return amount

    def charges_of(self, invoice_id: int) -> list[Any]:
        """The invoice's Soll entries, fees first (oldest dunning level first)."""
        charges = list(
            self.Entry.objects
            .filter(invoice_id=invoice_id, amount__gt=0,
                    entry_type__in=[INVOICE, REMINDER_FEE])
            .select_related('reminder')
        )
        charges.sort(key=lambda e: (
            0 if e.entry_type == REMINDER_FEE else 1,
            e.reminder.level if e.reminder_id else 0,
            e.entry_date, e.pk,
        ))
        return charges

    def allocate_to_invoice(self, credit: Any, invoice_id: int, amount: Decimal,
                            date: Any) -> Decimal:
        applied = ZERO
        for debit in self.charges_of(invoice_id):
            if applied >= amount:
                break
            applied += self.allocate(debit, credit, amount - applied, date)
        return applied


def _snapshot(apps: Apps) -> tuple[dict[int, Decimal], dict[int, Decimal], dict[int, Decimal]]:
    """Old per-customer balance and available credit, old per-invoice paid amount."""
    Entry: Any = apps.get_model('billing', 'CustomerLedgerEntry')
    # Payment exists only in the historical state the type checker cannot see.
    Payment: Any = apps.get_model('billing', 'Payment')  # type: ignore[misc]
    Invoice: Any = apps.get_model('billing', 'Invoice')

    balance: dict[int, Decimal] = defaultdict(lambda: ZERO)
    charges: dict[int, Decimal] = defaultdict(lambda: ZERO)
    for e in Entry.objects.all():
        balance[e.customer_id] += e.amount
        # Old sign: negative = charge.
        if e.invoice_id and e.amount < 0 and e.entry_type in (INVOICE, REMINDER_FEE):
            charges[e.invoice_id] -= e.amount

    paid: dict[int, Decimal] = defaultdict(lambda: ZERO)
    paid_in: dict[int, Decimal] = defaultdict(lambda: ZERO)
    for p in Payment.objects.all():
        if p.invoice_id:
            paid[p.invoice_id] += p.amount
        if p.method != CREDIT:
            paid_in[p.customer_id] += p.amount

    cancelled: set[int] = set(
        Invoice.objects.filter(status=CANCELLED).values_list('pk', flat=True))
    invoice_customer: dict[int, int] = dict(
        Invoice.objects.filter(customer__isnull=False).values_list('pk', 'customer_id'))

    # Old available_credit(): money in minus what non-cancelled invoices consumed.
    consumed: dict[int, Decimal] = defaultdict(lambda: ZERO)
    expected_paid: dict[int, Decimal] = {}
    for invoice_id, amount in paid.items():
        if invoice_id in cancelled or invoice_id not in invoice_customer:
            expected_paid[invoice_id] = ZERO
            continue
        settled = max(min(amount, charges[invoice_id]), ZERO)
        expected_paid[invoice_id] = settled
        consumed[invoice_customer[invoice_id]] += settled
    credit: dict[int, Decimal] = {
        customer_id: max(amount - consumed[customer_id], ZERO)
        for customer_id, amount in paid_in.items()
    }
    return dict(balance), credit, expected_paid


def _verify(apps: Apps, old_balance: dict[int, Decimal], old_credit: dict[int, Decimal],
            expected_paid: dict[int, Decimal]) -> None:
    Entry: Any = apps.get_model('billing', 'CustomerLedgerEntry')
    Allocation: Any = apps.get_model('billing', 'LedgerAllocation')
    errors: list[str] = []

    balance: dict[int, Decimal] = defaultdict(lambda: ZERO)
    for e in Entry.objects.all():
        balance[e.customer_id] += e.amount
    for customer_id, amount in old_balance.items():
        if balance[customer_id] != -amount:
            errors.append(f'Kunde {customer_id}: Saldo {balance[customer_id]} statt {-amount}')

    paid: dict[int, Decimal] = defaultdict(lambda: ZERO)
    given: dict[int, Decimal] = defaultdict(lambda: ZERO)
    for a in Allocation.objects.select_related('debit_entry', 'credit_entry'):
        if a.credit_entry.entry_type in (PAYMENT, ADJUSTMENT):
            paid[a.debit_entry.invoice_id] += a.amount
            given[a.credit_entry_id] += a.amount
    for invoice_id, amount in expected_paid.items():
        if paid[invoice_id] != amount:
            errors.append(f'Rechnung {invoice_id}: bezahlt {paid[invoice_id]} statt {amount}')

    credit: dict[int, Decimal] = defaultdict(lambda: ZERO)
    for e in Entry.objects.filter(amount__lt=0, entry_type__in=[PAYMENT, ADJUSTMENT]):
        credit[e.customer_id] += -e.amount - given[e.pk]
    for customer_id in set(credit) | set(old_credit):
        if credit[customer_id] != old_credit.get(customer_id, ZERO):
            errors.append(f'Kunde {customer_id}: Guthaben {credit[customer_id]} '
                          f'statt {old_credit.get(customer_id, ZERO)}')

    if errors:
        raise RuntimeError('Umstellung auf Ausgleiche fehlgeschlagen:\n' + '\n'.join(errors))


def _carry_over_permissions(apps: Apps) -> None:
    Group: Any = apps.get_model('auth', 'Group')
    Permission: Any = apps.get_model('auth', 'Permission')
    for action in ('view', 'add', 'delete'):
        new = Permission.objects.filter(
            content_type__app_label='billing', codename=f'{action}_customerledgerentry').first()
        if new is None:
            continue  # fresh database: permissions are created after migrating
        for group in Group.objects.filter(
                permissions__content_type__app_label='billing',
                permissions__codename=f'{action}_payment'):
            group.permissions.add(new)


def forwards(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    Entry: Any = apps.get_model('billing', 'CustomerLedgerEntry')
    # Payment exists only in the historical state the type checker cannot see.
    Payment: Any = apps.get_model('billing', 'Payment')  # type: ignore[misc]
    Invoice: Any = apps.get_model('billing', 'Invoice')

    old_balance, old_credit, expected_paid = _snapshot(apps)

    # 1. Sign flip.
    Entry.objects.update(amount=-F('amount'))

    # 2. Payment details onto the entries.
    entry_of: dict[int, Any] = {
        e.payment_id: e for e in Entry.objects.filter(payment__isnull=False)
    }
    for p in Payment.objects.exclude(method=CREDIT):
        entry = entry_of.get(p.pk)
        if entry is None:
            raise RuntimeError(f'Zahlung {p.pk} hat keine Kontobewegung.')
        entry.method = p.method
        entry.note = p.note
        entry.invoice_id = p.invoice_id
        entry.save(update_fields=['method', 'note', 'invoice'])

    ledger = _Ledger(apps)

    # 3. Stornos and reversed fees against what they cancel.
    for storno in Invoice.objects.filter(reverses__isnull=False):
        credit = Entry.objects.filter(
            invoice=storno, entry_type=INVOICE, amount__lt=0).first()
        debit = Entry.objects.filter(
            invoice_id=storno.reverses_id, entry_type=INVOICE, amount__gt=0).first()
        if credit is not None and debit is not None:
            ledger.allocate(debit, credit, ledger.open[credit.pk], credit.entry_date)
    for credit in Entry.objects.filter(entry_type=REMINDER_FEE, amount__lt=0,
                                       reminder__isnull=False):
        debit = Entry.objects.filter(entry_type=REMINDER_FEE, amount__gt=0,
                                     reminder_id=credit.reminder_id).first()
        if debit is not None:
            ledger.allocate(debit, credit, ledger.open[credit.pk], credit.entry_date)

    cancelled: set[int] = set(
        Invoice.objects.filter(status=CANCELLED).values_list('pk', flat=True))

    # 4. Real payments against their invoice.
    for p in (Payment.objects.exclude(method=CREDIT).filter(invoice__isnull=False)
              .order_by('payment_date', 'pk')):
        if p.invoice_id in cancelled:
            continue
        ledger.allocate_to_invoice(entry_of[p.pk], p.invoice_id, p.amount, p.payment_date)

    # 5. Credit applications, FIFO from the oldest money left over.
    for p in Payment.objects.filter(method=CREDIT).order_by('payment_date', 'pk'):
        if p.invoice_id is None or p.invoice_id in cancelled:
            continue
        remaining = p.amount
        sources = (Entry.objects
                   .filter(customer_id=p.customer_id, amount__lt=0,
                           entry_type__in=[PAYMENT, ADJUSTMENT])
                   .order_by('entry_date', 'pk'))
        for source in sources:
            if remaining <= 0:
                break
            if ledger.open[source.pk] <= 0:
                continue
            remaining -= ledger.allocate_to_invoice(
                source, p.invoice_id, min(remaining, ledger.open[source.pk]),
                p.payment_date)

    # 6.
    _verify(apps, old_balance, old_credit, expected_paid)

    # 7.
    _carry_over_permissions(apps)


def backwards(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    Entry: Any = apps.get_model('billing', 'CustomerLedgerEntry')
    Allocation: Any = apps.get_model('billing', 'LedgerAllocation')
    # Payment exists only in the historical state the type checker cannot see.
    Payment: Any = apps.get_model('billing', 'Payment')  # type: ignore[misc]

    # Rolled back from 0016 the Payment table is empty and must be rebuilt;
    # rolled back from here its rows are still the originals.
    if not Payment.objects.exists():
        _rebuild_payments(Entry, Allocation, Payment)

    Allocation.objects.all().delete()
    Entry.objects.update(amount=-F('amount'), method='', note='')


def _rebuild_payments(Entry: Any, Allocation: Any, Payment: Any) -> None:
    for entry in Entry.objects.filter(entry_type=PAYMENT, payment__isnull=True):
        entry.payment = Payment.objects.create(
            customer_id=entry.customer_id,
            invoice_id=entry.invoice_id,
            payment_date=entry.entry_date,
            amount=-entry.amount,
            method=entry.method or 'other',
            note=entry.note,
        )
        entry.save(update_fields=['payment'])

    # Credit applications: money allocated to an invoice it was not booked for.
    applied: dict[tuple[int, int], list[Any]] = defaultdict(list)
    for a in Allocation.objects.select_related('debit_entry', 'credit_entry'):
        credit = a.credit_entry
        if credit.entry_type not in (PAYMENT, ADJUSTMENT):
            continue
        if credit.invoice_id == a.debit_entry.invoice_id:
            continue
        applied[(credit.customer_id, a.debit_entry.invoice_id)].append(a)
    for (customer_id, invoice_id), allocations in applied.items():
        Payment.objects.create(
            customer_id=customer_id,
            invoice_id=invoice_id,
            payment_date=max(a.allocation_date for a in allocations),
            amount=sum((a.amount for a in allocations), ZERO),
            method=CREDIT,
            note='Verrechnung mit Kundenguthaben',
        )


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0014_ledger_allocation'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards, elidable=False),
    ]
