"""Tests for the customer ledger — balances, charges, allocations, credit.

Sign convention throughout: positive = Soll (the customer owes), negative =
Haben (money in, Storno).  A positive balance is what the customer owes.
"""
import datetime
from decimal import Decimal
from typing import Any

from core.models import Address, Customer
from core.services.customers import ensure_customer_for_address
from deliveries.models import TaxRate
from django.test import TestCase

from billing.models import (
    CustomerLedgerEntry,
    Invoice,
    InvoiceLine,
    LedgerAllocation,
    Reminder,
)
from billing.services import ledger


def _make_customer(**kwargs: object) -> Customer:
    defaults: dict[str, object] = {'vorname': 'Max', 'nachname': 'Mustermann'}
    defaults.update(kwargs)
    address: Address = Address.objects.create(**defaults)
    return ensure_customer_for_address(address)


def _make_tax() -> TaxRate:
    return TaxRate.objects.create(name='Normal', percent=Decimal('20.00'))


def _make_invoice(
    customer: Customer,
    tax: TaxRate,
    *,
    unit_price: str = '100.00',
    status: str = Invoice.Status.ISSUED,
    number: str = 'RE260601-00001',
    quantity: str = '1',
    reverses: Invoice | None = None,
) -> Invoice:
    invoice = Invoice.objects.create(
        customer=customer,
        address=customer.default_address,
        number=number,
        document_date=datetime.date(2026, 6, 15),
        due_date=datetime.date(2026, 6, 29),
        status=status,
        reverses=reverses,
    )
    InvoiceLine.objects.create(
        invoice=invoice,
        position=1,
        description='Leistung',
        quantity=Decimal(quantity),
        unit_price=Decimal(unit_price),
        tax_rate=tax,
    )
    return invoice


def _make_storno(invoice: Invoice, tax: TaxRate, unit_price: str = '100.00') -> Invoice:
    assert invoice.customer is not None
    return _make_invoice(invoice.customer, tax, unit_price=unit_price,
                         number='RE260601-00099', quantity='-1', reverses=invoice)


def _issue_reminder(invoice: Invoice, fee: str = '12.00', level: int = 1) -> Reminder:
    reminder = Reminder.objects.create(
        invoice=invoice,
        level=level,
        number=f'MA26070{level}',
        status=Reminder.Status.ISSUED,
        reminder_date=datetime.date(2026, 7, level),
        due_date=datetime.date(2026, 7, 15),
        fee=Decimal(fee),
    )
    ledger.record_reminder_issued(reminder)
    return reminder


def _pay(customer: Customer, amount: str, *, invoice: Invoice | None = None,
         date: datetime.date = datetime.date(2026, 7, 1)) -> CustomerLedgerEntry:
    return ledger.record_payment(customer, date, Decimal(amount), invoice=invoice)


def _fresh(invoice: Invoice) -> Invoice:
    return Invoice.objects.get(pk=invoice.pk)


class CustomerBalanceTests(TestCase):
    def setUp(self) -> None:
        self.tax = _make_tax()
        self.customer = _make_customer()

    def test_fresh_customer_starts_at_zero(self) -> None:
        """A customer without movements has neither a balance nor credit."""
        self.assertEqual(ledger.customer_balance(self.customer), Decimal('0.00'))
        self.assertEqual(ledger.available_credit(self.customer), Decimal('0.00'))

    def test_issued_invoice_charges_the_customer(self) -> None:
        """An issued invoice is Soll: the balance rises by its gross total."""
        invoice = _make_invoice(self.customer, self.tax)
        ledger.record_invoice_issued(invoice)
        self.assertEqual(ledger.customer_balance(self.customer), Decimal('120.00'))

    def test_payment_lowers_the_balance(self) -> None:
        """A payment is Haben and brings the balance back to 0."""
        invoice = _make_invoice(self.customer, self.tax)
        ledger.record_invoice_issued(invoice)
        entry = _pay(self.customer, '120.00', invoice=invoice)
        self.assertEqual(entry.amount, Decimal('-120.00'))
        self.assertEqual(ledger.customer_balance(self.customer), Decimal('0.00'))

    def test_issued_reminder_fee_raises_the_balance(self) -> None:
        """A reminder fee is a further Soll entry on top of the invoice."""
        invoice = _make_invoice(self.customer, self.tax)
        ledger.record_invoice_issued(invoice)
        _issue_reminder(invoice)
        self.assertEqual(ledger.customer_balance(self.customer), Decimal('132.00'))

    def test_reminder_without_fee_books_nothing(self) -> None:
        """No fee, no movement — a zero entry would only clutter the account."""
        invoice = _make_invoice(self.customer, self.tax)
        reminder = Reminder.objects.create(
            invoice=invoice,
            level=1,
            reminder_date=datetime.date(2026, 7, 1),
            due_date=datetime.date(2026, 7, 15),
            fee=Decimal('0.00'),
        )
        self.assertIsNone(ledger.record_reminder_issued(reminder))

    def test_cancellation_restores_the_balance(self) -> None:
        """The Storno has negated lines, so its entry is Haben and cancels the charge."""
        invoice = _make_invoice(self.customer, self.tax)
        ledger.record_invoice_issued(invoice)
        ledger.record_cancellation(invoice, _make_storno(invoice, self.tax))
        self.assertEqual(ledger.customer_balance(self.customer), Decimal('0.00'))

    def test_cancellation_credits_the_reminder_fees_back(self) -> None:
        """The Storno only covers the invoice amount; fees are reversed separately."""
        invoice = _make_invoice(self.customer, self.tax)
        ledger.record_invoice_issued(invoice)
        _issue_reminder(invoice)
        self.assertEqual(ledger.customer_balance(self.customer), Decimal('132.00'))

        ledger.record_cancellation(invoice, _make_storno(invoice, self.tax))
        self.assertEqual(ledger.customer_balance(self.customer), Decimal('0.00'))

    def test_draft_reminder_fee_is_not_reversed(self) -> None:
        """A draft's fee was never charged, so cancelling must not credit it back."""
        invoice = _make_invoice(self.customer, self.tax)
        Reminder.objects.create(
            invoice=invoice,
            level=1,
            reminder_date=datetime.date(2026, 7, 1),
            due_date=datetime.date(2026, 7, 15),
            fee=Decimal('12.00'),
        )
        ledger.record_cancellation(invoice, _make_storno(invoice, self.tax))
        self.assertFalse(CustomerLedgerEntry.objects.filter(
            entry_type=CustomerLedgerEntry.EntryType.REMINDER_FEE).exists())


class AvailableCreditTests(TestCase):
    def setUp(self) -> None:
        self.tax = _make_tax()
        self.customer = _make_customer()

    def test_credit_is_zero_while_the_customer_owes_money(self) -> None:
        """An open invoice alone gives no credit."""
        invoice = _make_invoice(self.customer, self.tax)
        ledger.record_invoice_issued(invoice)
        self.assertEqual(ledger.customer_balance(self.customer), Decimal('120.00'))
        self.assertEqual(ledger.available_credit(self.customer), Decimal('0.00'))

    def test_prepayment_becomes_credit(self) -> None:
        """A payment without an invoice is unallocated, so all of it is credit."""
        _pay(self.customer, '50.00', date=datetime.date(2026, 6, 1))
        self.assertEqual(ledger.available_credit(self.customer), Decimal('50.00'))


class ApplyCreditTests(TestCase):
    def setUp(self) -> None:
        self.tax = _make_tax()
        self.customer = _make_customer()
        _pay(self.customer, '50.00', date=datetime.date(2026, 6, 1))

    def test_applying_credit_does_not_double_count_it(self) -> None:
        """The credit is already on the ledger; applying it only allocates it."""
        invoice = _make_invoice(self.customer, self.tax, unit_price='100.00')
        ledger.record_invoice_issued(invoice)
        # 120 invoice − 50 credit
        self.assertEqual(ledger.customer_balance(self.customer), Decimal('70.00'))

        ledger.apply_credit(invoice, Decimal('50.00'), datetime.date(2026, 6, 15))
        invoice = _fresh(invoice)

        # The balance is unchanged — the money was already counted …
        self.assertEqual(ledger.customer_balance(self.customer), Decimal('70.00'))
        # … but the invoice is now partly settled.
        self.assertEqual(invoice.paid_amount, Decimal('50.00'))
        self.assertEqual(invoice.open_amount, Decimal('70.00'))

    def test_applying_credit_books_an_allocation_not_an_entry(self) -> None:
        """No new ledger movement; one allocation from the prepayment to the invoice."""
        invoice = _make_invoice(self.customer, self.tax)
        ledger.record_invoice_issued(invoice)
        entries_before = CustomerLedgerEntry.objects.count()

        ledger.apply_credit(invoice, Decimal('50.00'))

        self.assertEqual(CustomerLedgerEntry.objects.count(), entries_before)
        allocation = LedgerAllocation.objects.get()
        self.assertEqual(allocation.amount, Decimal('50.00'))
        self.assertEqual(allocation.debit_entry.invoice_id, invoice.pk)

    def test_without_an_amount_it_applies_as_much_as_possible(self) -> None:
        """amount=None takes the smaller of credit and open amount."""
        invoice = _make_invoice(self.customer, self.tax, unit_price='20.00')
        ledger.record_invoice_issued(invoice)  # 24.00 gross
        self.assertEqual(ledger.apply_credit(invoice), Decimal('24.00'))
        self.assertEqual(ledger.available_credit(self.customer), Decimal('26.00'))

    def test_more_than_available_credit_is_rejected(self) -> None:
        """Only 50 are available; asking for 80 must fail, not over-allocate."""
        invoice = _make_invoice(self.customer, self.tax)
        ledger.record_invoice_issued(invoice)
        with self.assertRaises(ledger.CreditError):
            ledger.apply_credit(invoice, Decimal('80.00'))

    def test_more_than_the_open_amount_is_rejected(self) -> None:
        """Credit beyond what the invoice still owes is refused."""
        invoice = _make_invoice(self.customer, self.tax, unit_price='20.00')
        ledger.record_invoice_issued(invoice)  # 24.00 gross
        with self.assertRaises(ledger.CreditError):
            ledger.apply_credit(invoice, Decimal('50.00'))

    def test_zero_or_negative_is_rejected(self) -> None:
        """An explicit zero amount is an error, not a silent no-op."""
        invoice = _make_invoice(self.customer, self.tax)
        ledger.record_invoice_issued(invoice)
        with self.assertRaises(ledger.CreditError):
            ledger.apply_credit(invoice, Decimal('0.00'))


class AvailableCreditEdgeCaseTests(TestCase):
    """available_credit is unallocated money, not simply a negative balance."""

    def setUp(self) -> None:
        self.tax = _make_tax()
        self.customer = _make_customer()

    def test_prepayment_stays_available_while_an_invoice_is_outstanding(self) -> None:
        """The customer owes overall, yet the prepayment is still unallocated."""
        _pay(self.customer, '50.00', date=datetime.date(2026, 6, 1))
        invoice = _make_invoice(self.customer, self.tax)
        ledger.record_invoice_issued(invoice)

        self.assertEqual(ledger.customer_balance(self.customer), Decimal('70.00'))
        self.assertEqual(ledger.available_credit(self.customer), Decimal('50.00'))

    def test_credit_cannot_be_applied_twice(self) -> None:
        """Once allocated, the same money is not available for a second invoice."""
        _pay(self.customer, '50.00', date=datetime.date(2026, 6, 1))
        invoice = _make_invoice(self.customer, self.tax)
        ledger.record_invoice_issued(invoice)

        ledger.apply_credit(invoice, Decimal('50.00'))
        self.assertEqual(ledger.available_credit(self.customer), Decimal('0.00'))

        second = _make_invoice(self.customer, self.tax, number='RE260601-00002')
        ledger.record_invoice_issued(second)
        with self.assertRaises(ledger.CreditError):
            ledger.apply_credit(second, Decimal('50.00'))

    def test_overpayment_stays_available(self) -> None:
        """Only 120 can be allocated to the invoice; the other 30 stay credit."""
        invoice = _make_invoice(self.customer, self.tax)  # 120.00 gross
        ledger.record_invoice_issued(invoice)
        _pay(self.customer, '150.00', invoice=invoice)

        self.assertEqual(ledger.customer_balance(self.customer), Decimal('-30.00'))
        self.assertEqual(ledger.available_credit(self.customer), Decimal('30.00'))
        self.assertEqual(_fresh(invoice).paid_amount, Decimal('120.00'))

    def test_a_fully_paid_invoice_consumes_its_payment(self) -> None:
        """A payment of exactly the invoice total leaves no credit."""
        invoice = _make_invoice(self.customer, self.tax)
        ledger.record_invoice_issued(invoice)
        _pay(self.customer, '120.00', invoice=invoice)
        self.assertEqual(ledger.available_credit(self.customer), Decimal('0.00'))

    def test_cancelling_a_paid_invoice_frees_the_money_again(self) -> None:
        """The Storno hands the money back: the payment is released to credit."""
        invoice = _make_invoice(self.customer, self.tax)
        ledger.record_invoice_issued(invoice)
        _pay(self.customer, '120.00', invoice=invoice)
        self.assertEqual(ledger.available_credit(self.customer), Decimal('0.00'))

        ledger.record_cancellation(invoice, _make_storno(invoice, self.tax))

        self.assertEqual(ledger.available_credit(self.customer), Decimal('120.00'))
        self.assertEqual(ledger.customer_balance(self.customer), Decimal('-120.00'))
        self.assertEqual(_fresh(invoice).paid_amount, Decimal('0.00'))

    def test_reminder_fee_is_consumed_by_a_payment_covering_it(self) -> None:
        """Invoice plus fee paid in one amount: nothing owed, nothing left over."""
        invoice = _make_invoice(self.customer, self.tax)
        ledger.record_invoice_issued(invoice)
        _issue_reminder(invoice)
        _pay(self.customer, '132.00', invoice=invoice, date=datetime.date(2026, 7, 20))

        self.assertEqual(ledger.customer_balance(self.customer), Decimal('0.00'))
        self.assertEqual(ledger.available_credit(self.customer), Decimal('0.00'))


class AllocationTests(TestCase):
    """Which money settles which charge."""

    def setUp(self) -> None:
        self.tax = _make_tax()
        self.customer = _make_customer()
        self.invoice = _make_invoice(self.customer, self.tax)  # 120.00
        entry = ledger.record_invoice_issued(self.invoice)
        assert entry is not None
        self.invoice_entry: CustomerLedgerEntry = entry

    def _open(self, entry: CustomerLedgerEntry) -> Decimal:
        return ledger.entry_open_amount(CustomerLedgerEntry.objects.get(pk=entry.pk))

    def test_a_partial_payment_settles_the_fees_first(self) -> None:
        """§1416 ABGB: costs before principal — 50 settle the 12 fee, then 38 of the invoice."""
        _issue_reminder(self.invoice)
        fee_entry = CustomerLedgerEntry.objects.get(
            entry_type=CustomerLedgerEntry.EntryType.REMINDER_FEE)

        _pay(self.customer, '50.00', invoice=self.invoice)

        self.assertEqual(self._open(fee_entry), Decimal('0.00'))
        self.assertEqual(self._open(self.invoice_entry), Decimal('82.00'))
        self.assertEqual(_fresh(self.invoice).paid_amount, Decimal('50.00'))

    def test_older_dunning_levels_are_settled_first(self) -> None:
        """With two fees, the level-1 fee is settled before the level-2 fee."""
        _issue_reminder(self.invoice, fee='5.00', level=1)
        _issue_reminder(self.invoice, fee='10.00', level=2)
        _pay(self.customer, '8.00', invoice=self.invoice)

        level1 = CustomerLedgerEntry.objects.get(reminder__level=1)
        level2 = CustomerLedgerEntry.objects.get(reminder__level=2)
        self.assertEqual(self._open(level1), Decimal('0.00'))
        self.assertEqual(self._open(level2), Decimal('7.00'))

    def test_credit_is_applied_from_the_oldest_payment_first(self) -> None:
        """FIFO: 50 credit from a 30 and a 40 prepayment take all of the 30 first."""
        older = _pay(self.customer, '30.00', date=datetime.date(2026, 6, 1))
        newer = _pay(self.customer, '40.00', date=datetime.date(2026, 6, 5))

        ledger.apply_credit(self.invoice, Decimal('50.00'))

        self.assertEqual(self._open(older), Decimal('0.00'))
        self.assertEqual(self._open(newer), Decimal('20.00'))

    def test_allocations_never_exceed_either_side(self) -> None:
        """A 200 payment on a 120 invoice allocates 120, not 200."""
        payment = _pay(self.customer, '200.00', invoice=self.invoice)
        self.assertEqual(LedgerAllocation.objects.get().amount, Decimal('120.00'))
        self.assertEqual(self._open(payment), Decimal('80.00'))

    def test_entries_of_different_customers_cannot_be_allocated(self) -> None:
        """Money of one customer must never settle another customer's invoice."""
        other = _make_customer(vorname='Erika')
        payment = _pay(other, '50.00')
        with self.assertRaises(ledger.CreditError):
            ledger.allocate(self.invoice_entry, payment, Decimal('50.00'),
                            datetime.date(2026, 7, 1))

    def test_cancellation_settles_the_invoice_with_the_storno(self) -> None:
        """After the Storno both entries are fully allocated against each other."""
        storno = _make_storno(self.invoice, self.tax)
        ledger.record_cancellation(self.invoice, storno)
        storno_entry = CustomerLedgerEntry.objects.get(invoice=storno)

        self.assertEqual(self._open(self.invoice_entry), Decimal('0.00'))
        self.assertEqual(self._open(storno_entry), Decimal('0.00'))
        # A Storno is not a payment.
        self.assertEqual(_fresh(self.invoice).paid_amount, Decimal('0.00'))

    def test_released_credit_is_available_again(self) -> None:
        """Releasing applied credit removes the allocation and reopens the invoice."""
        prepayment = _pay(self.customer, '50.00', date=datetime.date(2026, 6, 1))
        ledger.apply_credit(self.invoice, Decimal('50.00'))

        released = ledger.release_credit(self.invoice, prepayment)

        self.assertEqual(released, Decimal('50.00'))
        self.assertEqual(ledger.available_credit(self.customer), Decimal('50.00'))
        self.assertEqual(_fresh(self.invoice).paid_amount, Decimal('0.00'))

    def test_a_payment_booked_for_the_invoice_is_not_released(self) -> None:
        """That payment is deleted instead — releasing it would leave a stray credit."""
        payment = _pay(self.customer, '50.00', invoice=self.invoice)
        with self.assertRaises(ledger.CreditError):
            ledger.release_credit(self.invoice, payment)

    def test_deleting_a_payment_reopens_what_it_settled(self) -> None:
        """Its allocations go with it and the invoice drops back to unpaid."""
        payment = _pay(self.customer, '120.00', invoice=self.invoice)
        ledger.recalculate_invoice_status(self.invoice)
        self.assertEqual(_fresh(self.invoice).status, Invoice.Status.PAID)

        ledger.delete_payment(payment)

        self.assertFalse(LedgerAllocation.objects.exists())
        self.assertEqual(_fresh(self.invoice).status, Invoice.Status.ISSUED)
        self.assertEqual(ledger.customer_balance(self.customer), Decimal('120.00'))

    def test_applied_payments_tell_payments_from_credit(self) -> None:
        """A payment booked for the invoice is a payment; a prepayment applied to it is credit."""
        _pay(self.customer, '20.00', date=datetime.date(2026, 6, 1))
        ledger.apply_credit(self.invoice, Decimal('20.00'), datetime.date(2026, 6, 16))
        _pay(self.customer, '30.00', invoice=self.invoice, date=datetime.date(2026, 7, 1))

        rows = _fresh(self.invoice).applied_payments

        self.assertEqual([(r.amount, r.is_credit) for r in rows],
                         [(Decimal('20.00'), True), (Decimal('30.00'), False)])
        # Credit rows carry the day it was applied, not the day it arrived.
        self.assertEqual(rows[0].payment_date, datetime.date(2026, 6, 16))
        self.assertEqual(rows[0].get_method_display(), 'Guthaben')


class CreditWorkedExampleTests(TestCase):
    """The worked example in docs/fakturierung-handbuch.md, section 6.3.

    Credit of 10, issue an invoice of 5, settle it from the credit.  Pinned as a
    test so the documented figures cannot drift away from the behaviour.
    """

    def setUp(self) -> None:
        self.customer = _make_customer()
        # 0 % tax keeps the example arithmetic identical to the handbook.
        self.tax = TaxRate.objects.create(name='Ohne', percent=Decimal('0.00'))

    def test_worked_example(self) -> None:
        """Balance −10 → −5 after the invoice; applying credit leaves it at −5, invoice paid."""
        _pay(self.customer, '10.00', date=datetime.date(2026, 9, 1))
        self.assertEqual(ledger.customer_balance(self.customer), Decimal('-10.00'))
        self.assertEqual(ledger.available_credit(self.customer), Decimal('10.00'))

        invoice = _make_invoice(self.customer, self.tax, unit_price='5.00')
        ledger.record_invoice_issued(invoice)
        # Issuing the invoice is what moves the balance — −10 + 5.
        self.assertEqual(ledger.customer_balance(self.customer), Decimal('-5.00'))
        # The prepayment is untouched so far, so all of it is still applicable.
        self.assertEqual(ledger.available_credit(self.customer), Decimal('10.00'))

        ledger.apply_credit(invoice, Decimal('5.00'), datetime.date(2026, 9, 16))
        ledger.recalculate_invoice_status(invoice)
        invoice = _fresh(invoice)

        # Applying the credit books no further movement: the balance stays −5.
        self.assertEqual(ledger.customer_balance(self.customer), Decimal('-5.00'))
        self.assertEqual(ledger.available_credit(self.customer), Decimal('5.00'))
        self.assertEqual(invoice.status, Invoice.Status.PAID)
        self.assertEqual(invoice.paid_at, datetime.date(2026, 9, 16))
        self.assertEqual(invoice.open_amount, Decimal('0.00'))
        # Exactly two movements: the prepayment and the invoice.
        self.assertEqual(
            CustomerLedgerEntry.objects.filter(customer=self.customer).count(), 2)


class SaldoVersusCreditOrderingTests(TestCase):
    """The ordering table in docs/fakturierung-handbuch.md, section 3.0.

    Same two movements (50 prepayment, 120 invoice) in both orders: the saldo is
    identical, only whether the money is already assigned to an invoice differs.
    """

    def setUp(self) -> None:
        self.customer = _make_customer()
        # 0 % tax keeps the example arithmetic identical to the handbook.
        self.tax = TaxRate.objects.create(name='Ohne', percent=Decimal('0.00'))

    def _prepay(self) -> None:
        _pay(self.customer, '50.00', date=datetime.date(2026, 9, 1))

    def _issue_invoice(self) -> Invoice:
        invoice = _make_invoice(self.customer, self.tax, unit_price='120.00')
        ledger.record_invoice_issued(invoice)
        return invoice

    def test_credit_before_the_invoice_is_offset_immediately(self) -> None:
        """Mirrors InvoiceViewSet.issue(): the prepayment is applied right away."""
        self._prepay()
        invoice = self._issue_invoice()
        ledger.apply_credit(invoice, Decimal('50.00'), invoice.document_date)

        self.assertEqual(ledger.customer_balance(self.customer), Decimal('70.00'))
        self.assertEqual(ledger.available_credit(self.customer), Decimal('0.00'))
        self.assertEqual(_fresh(invoice).open_amount, Decimal('70.00'))

    def test_credit_after_the_invoice_stays_unassigned(self) -> None:
        """Same saldo, but the money is not assigned to the invoice yet."""
        invoice = self._issue_invoice()
        self._prepay()

        self.assertEqual(ledger.customer_balance(self.customer), Decimal('70.00'))
        self.assertEqual(ledger.available_credit(self.customer), Decimal('50.00'))
        self.assertEqual(_fresh(invoice).open_amount, Decimal('120.00'))

    def test_offsetting_afterwards_reaches_the_same_state(self) -> None:
        """Applying the credit later ends where the other ordering started."""
        invoice = self._issue_invoice()
        self._prepay()
        ledger.apply_credit(invoice, Decimal('50.00'), datetime.date(2026, 9, 20))

        self.assertEqual(ledger.customer_balance(self.customer), Decimal('70.00'))
        self.assertEqual(ledger.available_credit(self.customer), Decimal('0.00'))
        self.assertEqual(_fresh(invoice).open_amount, Decimal('70.00'))


class IsReversalTests(TestCase):
    """Reversals must not read as ordinary charges next to what they cancel."""

    def setUp(self) -> None:
        self.tax = _make_tax()
        self.customer = _make_customer()
        self.invoice = _make_invoice(self.customer, self.tax)

    def test_a_normal_invoice_charge_is_not_a_reversal(self) -> None:
        """An ordinary invoice entry is a plain charge."""
        entry = ledger.record_invoice_issued(self.invoice)
        assert entry is not None
        self.assertFalse(entry.is_reversal)

    def test_a_storno_charge_is_a_reversal(self) -> None:
        """The Storno invoice's entry is flagged as a reversal."""
        entry = ledger.record_invoice_issued(_make_storno(self.invoice, self.tax))
        assert entry is not None
        self.assertTrue(entry.is_reversal)

    def test_a_charged_reminder_fee_is_not_a_reversal(self) -> None:
        """A fee charged by a reminder is Soll, not a reversal."""
        _issue_reminder(self.invoice)
        entry = CustomerLedgerEntry.objects.get()
        self.assertFalse(entry.is_reversal)

    def test_a_credited_back_reminder_fee_is_a_reversal(self) -> None:
        """The Haben fee entry written on cancellation is a reversal."""
        _issue_reminder(self.invoice)
        ledger.record_cancellation(self.invoice, _make_storno(self.invoice, self.tax))
        entry = CustomerLedgerEntry.objects.get(
            entry_type=CustomerLedgerEntry.EntryType.REMINDER_FEE, amount__lt=0)
        self.assertTrue(entry.is_reversal)

    def test_a_payment_is_never_a_reversal(self) -> None:
        """Money in is never shown as a reversal, even though it is Haben."""
        entry = _pay(self.customer, '120.00', invoice=self.invoice)
        self.assertFalse(entry.is_reversal)

    def test_the_ledger_endpoint_reports_it(self) -> None:
        """The endpoint exposes is_reversal so the dialog can label the Storno."""
        from django.contrib.auth.models import User
        from rest_framework.test import APIClient

        ledger.record_invoice_issued(self.invoice)
        ledger.record_invoice_issued(_make_storno(self.invoice, self.tax))

        client = APIClient()
        client.force_authenticate(
            user=User.objects.create_superuser('t', 't@example.com', 'p'))
        entries = client.get(
            f'/api/customers/{self.customer.pk}/ledger/').json()['entries']

        self.assertEqual([e['is_reversal'] for e in entries], [False, True])


class LedgerEndpointFieldsTests(TestCase):
    """The ledger dialog links by document number and shows open amounts."""

    def setUp(self) -> None:
        from django.contrib.auth.models import User
        from rest_framework.test import APIClient

        self.tax = _make_tax()
        self.customer = _make_customer()
        self.client = APIClient()
        self.client.force_authenticate(
            user=User.objects.create_superuser('t', 't@example.com', 'p'))

    def _entries(self) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = self.client.get(
            f'/api/customers/{self.customer.pk}/ledger/').json()['entries']
        return entries

    def test_an_invoice_charge_carries_its_invoice_number(self) -> None:
        """Invoice entries link to the invoice and to no reminder."""
        invoice = _make_invoice(self.customer, self.tax)
        ledger.record_invoice_issued(invoice)

        entry = self._entries()[0]
        self.assertEqual(entry['invoice_number'], 'RE260601-00001')
        self.assertIsNone(entry['reminder'])
        self.assertIsNone(entry['reminder_number'])

    def test_a_reminder_fee_carries_its_reminder_number(self) -> None:
        """A fee links to the Mahnung that charged it and to its invoice."""
        invoice = _make_invoice(self.customer, self.tax)
        _issue_reminder(invoice)

        entry = next(e for e in self._entries() if e['entry_type'] == 'reminder_fee')
        self.assertEqual(entry['reminder_number'], 'MA260701')
        self.assertEqual(entry['invoice_number'], 'RE260601-00001')

    def test_a_standalone_payment_has_nothing_to_link_to(self) -> None:
        """A prepayment has neither invoice nor reminder number."""
        _pay(self.customer, '50.00', date=datetime.date(2026, 6, 1))

        entry = self._entries()[0]
        self.assertIsNone(entry['invoice_number'])
        self.assertIsNone(entry['reminder_number'])

    def test_open_amounts_show_what_is_not_yet_settled(self) -> None:
        """120 invoice, 50 paid: the invoice has 70 open, the payment nothing left."""
        invoice = _make_invoice(self.customer, self.tax)
        ledger.record_invoice_issued(invoice)
        _pay(self.customer, '50.00', invoice=invoice)

        by_type = {e['entry_type']: e for e in self._entries()}
        self.assertEqual(by_type['invoice']['open_amount'], '70.00')
        self.assertEqual(by_type['payment']['open_amount'], '0.00')
        self.assertEqual(by_type['payment']['amount'], '-50.00')
        self.assertEqual(by_type['payment']['method'], 'transfer')
