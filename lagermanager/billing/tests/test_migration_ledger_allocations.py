"""The data migration from Payments to ledger allocations (billing 0015).

Builds the old state — old sign (negative = charge), Payment rows, credit
applications as method=credit payments without a ledger entry — on the
historical models, migrates forward and checks that every invoice is paid by
exactly what it was before and every customer keeps the same credit.
"""
import datetime
from decimal import Decimal
from typing import Any

from django.apps.registry import Apps
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

BEFORE = [('billing', '0014_ledger_allocation')]
AFTER = [('billing', '0015_payments_to_ledger_allocations')]
DAY = datetime.date(2026, 6, 15)


class PaymentsToAllocationsMigrationTests(TransactionTestCase):

    def setUp(self) -> None:
        executor = MigrationExecutor(connection)
        self.leaf = executor.loader.graph.leaf_nodes()
        executor.migrate(BEFORE)
        old: Apps = executor.loader.project_state(BEFORE).apps
        self._build_old_state(old)

        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(AFTER)
        self.apps: Apps = executor.loader.project_state(AFTER).apps

    def tearDown(self) -> None:
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(self.leaf)

    # -- the old world ------------------------------------------------------

    def _build_old_state(self, apps: Apps) -> None:
        Address: Any = apps.get_model('core', 'Address')
        Customer: Any = apps.get_model('core', 'Customer')
        Invoice: Any = apps.get_model('billing', 'Invoice')
        Reminder: Any = apps.get_model('billing', 'Reminder')
        # Payment exists only in the historical state the type checker cannot see.
        Payment: Any = apps.get_model('billing', 'Payment')  # type: ignore[misc]
        Entry: Any = apps.get_model('billing', 'CustomerLedgerEntry')

        address = Address.objects.create(vorname='Max', nachname='Mustermann')
        customer = Customer.objects.create(customer_number='K0001', name='Max')
        self.customer_id = customer.pk

        def invoice(number: str, gross: str, status: str = 'issued', **kw: Any) -> Any:
            inv = Invoice.objects.create(
                customer=customer, address=address, number=number,
                document_date=DAY, due_date=DAY, status=status, **kw)
            Entry.objects.create(customer=customer, entry_type='invoice', entry_date=DAY,
                                 amount=-Decimal(gross), invoice=inv)
            return inv

        def pay(amount: str, inv: Any = None, method: str = 'transfer') -> Any:
            p = Payment.objects.create(customer=customer, invoice=inv, payment_date=DAY,
                                       amount=Decimal(amount), method=method, note='n')
            if method != 'credit':
                Entry.objects.create(customer=customer, entry_type='payment', entry_date=DAY,
                                     amount=Decimal(amount), invoice=inv, payment=p)
            return p

        # Partly paid.
        self.partly = invoice('RE1', '120.00')
        pay('50.00', self.partly)
        # Paid together with its reminder fee.
        self.dunned = invoice('RE2', '120.00')
        reminder = Reminder.objects.create(
            invoice=self.dunned, level=1, number='MA1', status='issued',
            reminder_date=DAY, due_date=DAY, fee=Decimal('12.00'))
        Entry.objects.create(customer=customer, entry_type='reminder_fee', entry_date=DAY,
                             amount=Decimal('-12.00'), invoice=self.dunned, reminder=reminder)
        pay('132.00', self.dunned)
        # Settled from a prepayment.
        pay('30.00')
        self.from_credit = invoice('RE3', '24.00')
        pay('24.00', self.from_credit, method='credit')
        # Cancelled after a partial payment.
        self.cancelled = invoice('RE4', '120.00', status='cancelled')
        pay('40.00', self.cancelled)
        storno = Invoice.objects.create(
            customer=customer, address=address, number='RE5', document_date=DAY,
            due_date=DAY, status='issued', reverses=self.cancelled)
        Entry.objects.create(customer=customer, entry_type='invoice', entry_date=DAY,
                             amount=Decimal('120.00'), invoice=storno)
        # Overpaid.
        self.overpaid = invoice('RE6', '10.00')
        pay('15.00', self.overpaid)

        # A group that could book payments.
        payment_ct, _ = ContentType.objects.get_or_create(app_label='billing', model='payment')
        add_payment, _ = Permission.objects.get_or_create(
            content_type=payment_ct, codename='add_payment', defaults={'name': 'Can add'})
        self.group = Group.objects.create(name='Faktura')
        self.group.permissions.add(add_payment)

    # -- helpers --------------------------------------------------------------

    def _paid(self, invoice: Any) -> Decimal:
        """Money (not Storno) allocated onto the invoice's charges."""
        Allocation: Any = self.apps.get_model('billing', 'LedgerAllocation')
        total = Decimal('0.00')
        for a in Allocation.objects.filter(debit_entry__invoice_id=invoice.pk,
                                           debit_entry__amount__gt=0):
            if a.credit_entry.entry_type in ('payment', 'adjustment'):
                total += a.amount
        return total

    def _open(self, entry: Any) -> Decimal:
        Allocation: Any = self.apps.get_model('billing', 'LedgerAllocation')
        side = {'debit_entry': entry} if entry.amount > 0 else {'credit_entry': entry}
        allocated: Decimal = sum(
            (a.amount for a in Allocation.objects.filter(**side)), Decimal('0.00'))
        return Decimal(abs(entry.amount)) - allocated

    # -- tests ----------------------------------------------------------------

    def test_the_sign_is_flipped(self) -> None:
        """Charges become positive (Soll), payments negative (Haben); the balance
        flips from −(owed) to +(owed): 120+132+24+120−120+10 charged − 267 paid = 19."""
        Entry: Any = self.apps.get_model('billing', 'CustomerLedgerEntry')
        total = sum((e.amount for e in Entry.objects.filter(customer_id=self.customer_id)),
                    Decimal('0.00'))
        self.assertEqual(total, Decimal('19.00'))
        self.assertFalse(Entry.objects.filter(entry_type='payment', amount__gt=0).exists())

    def test_invoices_are_paid_by_what_they_were_paid_before(self) -> None:
        """Paid amounts survive; overpayment is capped at the charges, a cancelled
        invoice is settled by its Storno and owns no payment any more."""
        self.assertEqual(self._paid(self.partly), Decimal('50.00'))
        self.assertEqual(self._paid(self.dunned), Decimal('132.00'))
        self.assertEqual(self._paid(self.from_credit), Decimal('24.00'))
        self.assertEqual(self._paid(self.cancelled), Decimal('0.00'))
        self.assertEqual(self._paid(self.overpaid), Decimal('10.00'))

    def test_the_fee_is_settled_first(self) -> None:
        """The 132 payment covers fee and invoice; the fee entry is fully settled."""
        Entry: Any = self.apps.get_model('billing', 'CustomerLedgerEntry')
        fee = Entry.objects.get(entry_type='reminder_fee', invoice_id=self.dunned.pk)
        self.assertEqual(self._open(fee), Decimal('0.00'))

    def test_the_storno_settles_the_cancelled_invoice(self) -> None:
        """Storno and cancelled invoice are allocated against each other in full."""
        Entry: Any = self.apps.get_model('billing', 'CustomerLedgerEntry')
        charge = Entry.objects.get(invoice_id=self.cancelled.pk, entry_type='invoice')
        self.assertEqual(self._open(charge), Decimal('0.00'))

    def test_unused_money_is_still_credit(self) -> None:
        """6 left of the prepayment, 40 released by the Storno, 5 overpaid = 51 —
        the same figure the old available_credit() gave."""
        Entry: Any = self.apps.get_model('billing', 'CustomerLedgerEntry')
        credit = sum(
            (self._open(e) for e in Entry.objects.filter(entry_type='payment')),
            Decimal('0.00'))
        self.assertEqual(credit, Decimal('51.00'))

    def test_payment_details_move_onto_the_entries(self) -> None:
        """Method and note of each payment are kept on its ledger entry."""
        Entry: Any = self.apps.get_model('billing', 'CustomerLedgerEntry')
        entry = Entry.objects.get(entry_type='payment', invoice_id=self.partly.pk)
        self.assertEqual((entry.method, entry.note), ('transfer', 'n'))

    def test_payment_permissions_carry_over_to_ledger_entries(self) -> None:
        """A group that could add payments can add ledger entries, or the
        payments endpoint would refuse it from now on."""
        self.assertTrue(self.group.permissions.filter(
            codename='add_customerledgerentry').exists())

    def test_it_can_be_rolled_back(self) -> None:
        """A full rollback (through 0016, which empties Payment) restores the old
        sign and rebuilds the payments — the credit application again as a
        method=credit payment of the same amount."""
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(self.leaf)
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(BEFORE)
        old: Apps = executor.loader.project_state(BEFORE).apps
        # Payment exists only in the historical state the type checker cannot see.
        Payment: Any = old.get_model('billing', 'Payment')  # type: ignore[misc]
        Entry: Any = old.get_model('billing', 'CustomerLedgerEntry')

        self.assertEqual(Payment.objects.exclude(method='credit').count(), 5)
        credit = Payment.objects.get(method='credit')
        self.assertEqual(
            (credit.invoice_id, credit.amount), (self.from_credit.pk, Decimal('24.00')))
        total = sum((e.amount for e in Entry.objects.all()), Decimal('0.00'))
        self.assertEqual(total, Decimal('-19.00'))
