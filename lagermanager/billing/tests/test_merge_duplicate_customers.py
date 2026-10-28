"""Tests for the merge_duplicate_customers management command."""
import datetime
from decimal import Decimal
from io import StringIO

from core.models import Address, Customer
from django.core.management import call_command
from django.test import TestCase

from billing.models import CustomerLedgerEntry, Invoice, Offer, Payment


class MergeDuplicateCustomersTests(TestCase):
    """The state a WZ sync left after backfill_customers_and_ledger.

    The backfilled customer (no wz_source_id) still has the old documents and
    its default address; the sync's duplicate (with wz_source_id) owns the
    address and whatever was billed to it since.
    """

    def setUp(self) -> None:
        self.address = Address.objects.create(wz_source_id=7, firma='Muster GmbH')
        self.old = Customer.objects.create(
            customer_number='K0001', name='Muster GmbH', default_address=self.address,
            notes='Stammkunde')
        self.dup = Customer.objects.create(
            customer_number='K0002', name='Muster GmbH', wz_source_id=7,
            default_address=self.address, email='info@muster.at', notes='Neu')
        self.address.customer = self.dup
        self.address.save(update_fields=['customer'])

        self.old_invoice = self._invoice(self.old, 'RE1')
        self.new_invoice = self._invoice(self.dup, 'RE2')
        self.offer = Offer.objects.create(
            customer=self.dup, address=self.address, document_date=datetime.date(2026, 10, 1))
        self.payment = Payment.objects.create(
            customer=self.dup, invoice=self.new_invoice, amount=Decimal('10.00'),
            payment_date=datetime.date(2026, 10, 2), method=Payment.Method.OTHER)
        self.entry = CustomerLedgerEntry.objects.create(
            customer=self.dup, entry_type=CustomerLedgerEntry.EntryType.PAYMENT,
            entry_date=datetime.date(2026, 10, 2), amount=Decimal('10.00'),
            description='Zahlung', invoice=self.new_invoice, payment=self.payment)

    def _invoice(self, customer: Customer, number: str) -> Invoice:
        return Invoice.objects.create(
            customer=customer, address=self.address, number=number,
            document_date=datetime.date(2026, 10, 1), due_date=datetime.date(2026, 10, 15),
            status=Invoice.Status.ISSUED)

    def _run(self, **opts: object) -> str:
        out = StringIO()
        call_command('merge_duplicate_customers', stdout=out, **opts)
        return out.getvalue()

    def test_moves_everything_to_the_old_customer_and_deletes_the_duplicate(self) -> None:
        """The old customer keeps its number, gets the address, documents and ledger."""
        self._run()
        self.assertFalse(Customer.objects.filter(pk=self.dup.pk).exists())
        self.old.refresh_from_db()
        self.assertEqual(self.old.wz_source_id, 7)
        self.assertEqual(self.old.customer_number, 'K0001')
        for obj in (self.address, self.new_invoice, self.offer, self.payment, self.entry):
            obj.refresh_from_db()
            self.assertEqual(obj.customer_id, self.old.pk, obj)

    def test_fills_empty_fields_and_keeps_both_notes(self) -> None:
        """Nothing the user entered on either customer is lost."""
        self._run()
        self.old.refresh_from_db()
        self.assertEqual(self.old.email, 'info@muster.at')
        self.assertIn('Stammkunde', self.old.notes)
        self.assertIn('Neu', self.old.notes)

    def test_dry_run_changes_nothing_and_warns_about_issued_invoices(self) -> None:
        """RE2 was issued under K0002, so the dry run must say its number changes."""
        out = self._run(dry_run=True)
        self.assertEqual(Customer.objects.count(), 2)
        self.assertIn('K0002', out)
        self.assertIn('RE2', out)

    def test_is_idempotent(self) -> None:
        """A second run finds nothing left to merge."""
        self._run()
        out = self._run()
        self.assertEqual(Customer.objects.count(), 1)
        self.assertIn('Zusammengeführt:            0', out)

    def test_leaves_unrelated_customers_alone(self) -> None:
        """A local customer whose default address it still owns is no duplicate."""
        local_address = Address.objects.create(wz_source_id=8, firma='Andere KG')
        local = Customer.objects.create(
            customer_number='K0003', name='Andere KG', default_address=local_address)
        local_address.customer = local
        local_address.save(update_fields=['customer'])
        self._run()
        self.assertTrue(Customer.objects.filter(pk=local.pk).exists())
        local.refresh_from_db()
        self.assertIsNone(local.wz_source_id)
