"""Tests for the backfill_customers_and_ledger management command."""
import datetime
from decimal import Decimal
from io import StringIO

from core.models import Address, Customer
from deliveries.models import TaxRate
from django.contrib.auth.models import Group, Permission
from django.core.management import call_command
from django.test import TestCase

from billing.models import (
    CustomerLedgerEntry,
    Invoice,
    InvoiceLine,
    Offer,
    Payment,
    Reminder,
)
from billing.services import ledger


class BackfillTests(TestCase):
    def setUp(self) -> None:
        self.tax = TaxRate.objects.create(name='Normal', percent=Decimal('20.00'))
        # Addresses and documents as they existed before customers, i.e. with
        # no customer FK anywhere.
        self.address = Address.objects.create(vorname='Max', nachname='Mustermann')
        self.issued = self._make_invoice('RE1', Invoice.Status.ISSUED)
        self.paid = self._make_invoice('RE2', Invoice.Status.PAID)
        self.paid.paid_at = datetime.date(2026, 7, 1)
        self.paid.save(update_fields=['paid_at'])
        self.draft = self._make_invoice('', Invoice.Status.DRAFT)
        self.offer = Offer.objects.create(
            address=self.address, document_date=datetime.date(2026, 6, 15))

    def _make_invoice(self, number: str, status: str) -> Invoice:
        invoice = Invoice.objects.create(
            address=self.address,
            number=number or None,
            document_date=datetime.date(2026, 6, 15),
            due_date=datetime.date(2026, 6, 29),
            status=status,
        )
        InvoiceLine.objects.create(
            invoice=invoice, position=1, description='Leistung',
            quantity=Decimal('1'), unit_price=Decimal('100.00'), tax_rate=self.tax,
        )
        return invoice

    def _run(self, **opts: object) -> str:
        out = StringIO()
        call_command('backfill_customers_and_ledger', stdout=out, **opts)
        return out.getvalue()

    def test_creates_a_customer_for_every_address(self) -> None:
        self._run()
        self.address.refresh_from_db()
        self.assertIsNotNone(self.address.customer)
        self.assertEqual(Customer.objects.count(), 1)
        self.assertEqual(self.address.customer.default_address, self.address)

    def test_documents_inherit_the_address_customer(self) -> None:
        self._run()
        self.address.refresh_from_db()
        for doc in (self.issued, self.paid, self.draft, self.offer):
            doc.refresh_from_db()
            self.assertEqual(doc.customer_id, self.address.customer_id)

    def test_only_non_draft_invoices_are_charged(self) -> None:
        self._run()
        charged = set(
            CustomerLedgerEntry.objects
            .filter(entry_type=CustomerLedgerEntry.EntryType.INVOICE)
            .values_list('invoice_id', flat=True)
        )
        self.assertEqual(charged, {self.issued.pk, self.paid.pk})

    def test_a_paid_invoice_gets_a_payment(self) -> None:
        self._run()
        payment = Payment.objects.get(invoice=self.paid)
        self.assertEqual(payment.amount, Decimal('120.00'))
        self.assertEqual(payment.payment_date, datetime.date(2026, 7, 1))
        self.assertEqual(payment.method, Payment.Method.OTHER)

    def test_resulting_balance(self) -> None:
        self._run()
        self.address.refresh_from_db()
        # −120 issued, −120 paid invoice, +120 its payment
        self.assertEqual(
            ledger.customer_balance(self.address.customer), Decimal('-120.00'))

    def test_issued_reminder_fee_is_charged(self) -> None:
        Reminder.objects.create(
            invoice=self.issued, level=1, number='MA1',
            status=Reminder.Status.ISSUED,
            reminder_date=datetime.date(2026, 7, 1),
            due_date=datetime.date(2026, 7, 15),
            fee=Decimal('12.00'),
        )
        Reminder.objects.create(
            invoice=self.issued, level=2,
            reminder_date=datetime.date(2026, 7, 20),
            due_date=datetime.date(2026, 8, 3),
            fee=Decimal('20.00'),
        )
        self._run()
        fees = CustomerLedgerEntry.objects.filter(
            entry_type=CustomerLedgerEntry.EntryType.REMINDER_FEE)
        self.assertEqual(fees.count(), 1)
        self.assertEqual(fees.first().amount, Decimal('-12.00'))

    def test_is_idempotent(self) -> None:
        self._run()
        entries = CustomerLedgerEntry.objects.count()
        payments = Payment.objects.count()

        self._run()
        self.assertEqual(CustomerLedgerEntry.objects.count(), entries)
        self.assertEqual(Payment.objects.count(), payments)
        self.assertEqual(Customer.objects.count(), 1)

    def test_dry_run_writes_nothing(self) -> None:
        output = self._run(dry_run=True)
        self.assertIn('Testlauf', output)
        self.assertEqual(Customer.objects.count(), 0)
        self.assertEqual(CustomerLedgerEntry.objects.count(), 0)
        self.address.refresh_from_db()
        self.assertIsNone(self.address.customer_id)

    def test_reports_non_zero_balances(self) -> None:
        self.assertIn('Salden ungleich 0', self._run())


class BackfillPermissionsTests(TestCase):
    """Groups that already manage invoices must not lose access to the new views."""

    def setUp(self) -> None:
        self.faktura = Group.objects.create(name='faktura')
        self.faktura.permissions.add(Permission.objects.get(
            content_type__app_label='billing', codename='view_invoice'))
        self.other = Group.objects.create(name='lager')

    def _run(self) -> None:
        call_command('backfill_customers_and_ledger', stdout=StringIO())

    def _codenames(self, group: Group) -> set[str]:
        return set(group.permissions.filter(
            content_type__app_label__in=['core', 'billing'],
        ).values_list('codename', flat=True))

    def test_billing_groups_get_the_new_permissions(self) -> None:
        self._run()
        codenames = self._codenames(self.faktura)
        for expected in (
            'view_customer', 'add_customer', 'change_customer', 'delete_customer',
            'view_payment', 'add_payment', 'change_payment', 'delete_payment',
            'view_customerledgerentry',
        ):
            self.assertIn(expected, codenames)

    def test_unrelated_groups_are_left_alone(self) -> None:
        self._run()
        self.assertEqual(self._codenames(self.other), set())

    def test_is_idempotent(self) -> None:
        self._run()
        before = self._codenames(self.faktura)
        self._run()
        self.assertEqual(self._codenames(self.faktura), before)


class BackfillOrderingTests(TestCase):
    """The ledger must be written oldest-first.

    Invoice.Meta.ordering is newest-first, so iterating it unordered wrote the
    ledger backwards and left a Storno above the invoice it reverses.
    """

    def setUp(self) -> None:
        self.tax = TaxRate.objects.create(name='Ohne', percent=Decimal('0.00'))
        self.address = Address.objects.create(vorname='Max', nachname='Mustermann')

    def _invoice(self, number: str, day: int, amount: str) -> Invoice:
        invoice = Invoice.objects.create(
            address=self.address,
            number=number,
            document_date=datetime.date(2026, 6, day),
            due_date=datetime.date(2026, 6, day),
            status=Invoice.Status.ISSUED,
        )
        InvoiceLine.objects.create(
            invoice=invoice, position=1, description='X',
            quantity=Decimal('1'), unit_price=Decimal(amount), tax_rate=self.tax,
        )
        return invoice

    def test_entries_are_created_oldest_first(self) -> None:
        self._invoice('PG260610', 10, '100.00')
        self._invoice('PG260612', 12, '200.00')
        self._invoice('PG260613', 13, '300.00')

        call_command('backfill_customers_and_ledger', stdout=StringIO())

        booked = list(
            CustomerLedgerEntry.objects
            .filter(entry_type=CustomerLedgerEntry.EntryType.INVOICE)
            .order_by('pk')
            .values_list('description', flat=True)
        )
        self.assertEqual(booked, [
            'Rechnung PG260610', 'Rechnung PG260612', 'Rechnung PG260613',
        ])
