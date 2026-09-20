"""Tests for the customer ledger — balances, charges, credit."""
import datetime
from decimal import Decimal

from core.models import Address, Customer
from core.services.customers import ensure_customer_for_address
from deliveries.models import TaxRate
from django.test import TestCase

from billing.models import (
    CustomerLedgerEntry,
    Invoice,
    InvoiceLine,
    Payment,
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
) -> Invoice:
    invoice = Invoice.objects.create(
        customer=customer,
        address=customer.default_address,
        number=number,
        document_date=datetime.date(2026, 6, 15),
        due_date=datetime.date(2026, 6, 29),
        status=status,
    )
    InvoiceLine.objects.create(
        invoice=invoice,
        position=1,
        description='Leistung',
        quantity=Decimal('1'),
        unit_price=Decimal(unit_price),
        tax_rate=tax,
    )
    return invoice


class CustomerBalanceTests(TestCase):
    def setUp(self) -> None:
        self.tax = _make_tax()
        self.customer = _make_customer()

    def test_fresh_customer_starts_at_zero(self) -> None:
        self.assertEqual(ledger.customer_balance(self.customer), Decimal('0.00'))
        self.assertEqual(ledger.available_credit(self.customer), Decimal('0.00'))

    def test_issued_invoice_charges_the_customer(self) -> None:
        invoice = _make_invoice(self.customer, self.tax)
        ledger.record_invoice_issued(invoice)
        self.assertEqual(ledger.customer_balance(self.customer), Decimal('-120.00'))

    def test_payment_raises_the_balance(self) -> None:
        invoice = _make_invoice(self.customer, self.tax)
        ledger.record_invoice_issued(invoice)
        payment = Payment.objects.create(
            customer=self.customer,
            invoice=invoice,
            payment_date=datetime.date(2026, 7, 1),
            amount=Decimal('120.00'),
        )
        ledger.record_payment(payment)
        self.assertEqual(ledger.customer_balance(self.customer), Decimal('0.00'))

    def test_issued_reminder_fee_lowers_the_balance(self) -> None:
        invoice = _make_invoice(self.customer, self.tax)
        ledger.record_invoice_issued(invoice)
        reminder = Reminder.objects.create(
            invoice=invoice,
            level=1,
            number='MA260701',
            status=Reminder.Status.ISSUED,
            reminder_date=datetime.date(2026, 7, 1),
            due_date=datetime.date(2026, 7, 15),
            fee=Decimal('12.00'),
        )
        ledger.record_reminder_issued(reminder)
        self.assertEqual(ledger.customer_balance(self.customer), Decimal('-132.00'))

    def test_reminder_without_fee_books_nothing(self) -> None:
        invoice = _make_invoice(self.customer, self.tax)
        reminder = Reminder.objects.create(
            invoice=invoice,
            level=1,
            reminder_date=datetime.date(2026, 7, 1),
            due_date=datetime.date(2026, 7, 15),
            fee=Decimal('0.00'),
        )
        self.assertIsNone(ledger.record_reminder_issued(reminder))

    def test_storno_restores_the_balance(self) -> None:
        """A reversal invoice has negated lines, so its charge is positive."""
        invoice = _make_invoice(self.customer, self.tax)
        ledger.record_invoice_issued(invoice)
        storno = Invoice.objects.create(
            customer=self.customer,
            address=self.customer.default_address,
            number='RE260601-00002',
            document_date=datetime.date(2026, 6, 20),
            due_date=datetime.date(2026, 6, 20),
            reverses=invoice,
            status=Invoice.Status.ISSUED,
        )
        InvoiceLine.objects.create(
            invoice=storno,
            position=1,
            description='Leistung',
            quantity=Decimal('-1'),
            unit_price=Decimal('100.00'),
            tax_rate=self.tax,
        )
        ledger.record_invoice_issued(storno)
        self.assertEqual(ledger.customer_balance(self.customer), Decimal('0.00'))

    def test_reverse_reminder_fees_credits_them_back(self) -> None:
        invoice = _make_invoice(self.customer, self.tax)
        reminder = Reminder.objects.create(
            invoice=invoice,
            level=1,
            number='MA260701',
            status=Reminder.Status.ISSUED,
            reminder_date=datetime.date(2026, 7, 1),
            due_date=datetime.date(2026, 7, 15),
            fee=Decimal('12.00'),
        )
        ledger.record_reminder_issued(reminder)
        self.assertEqual(ledger.customer_balance(self.customer), Decimal('-12.00'))

        ledger.reverse_reminder_fees(invoice)
        self.assertEqual(ledger.customer_balance(self.customer), Decimal('0.00'))

    def test_draft_reminder_fee_is_not_reversed(self) -> None:
        invoice = _make_invoice(self.customer, self.tax)
        Reminder.objects.create(
            invoice=invoice,
            level=1,
            reminder_date=datetime.date(2026, 7, 1),
            due_date=datetime.date(2026, 7, 15),
            fee=Decimal('12.00'),
        )
        self.assertEqual(ledger.reverse_reminder_fees(invoice), [])


class AvailableCreditTests(TestCase):
    def setUp(self) -> None:
        self.tax = _make_tax()
        self.customer = _make_customer()

    def test_credit_is_zero_while_the_customer_owes_money(self) -> None:
        invoice = _make_invoice(self.customer, self.tax)
        ledger.record_invoice_issued(invoice)
        self.assertEqual(ledger.customer_balance(self.customer), Decimal('-120.00'))
        self.assertEqual(ledger.available_credit(self.customer), Decimal('0.00'))

    def test_prepayment_becomes_credit(self) -> None:
        payment = Payment.objects.create(
            customer=self.customer,
            payment_date=datetime.date(2026, 6, 1),
            amount=Decimal('50.00'),
        )
        ledger.record_payment(payment)
        self.assertEqual(ledger.available_credit(self.customer), Decimal('50.00'))


class ApplyCreditTests(TestCase):
    def setUp(self) -> None:
        self.tax = _make_tax()
        self.customer = _make_customer()
        prepayment = Payment.objects.create(
            customer=self.customer,
            payment_date=datetime.date(2026, 6, 1),
            amount=Decimal('50.00'),
        )
        ledger.record_payment(prepayment)

    def test_applying_credit_does_not_double_count_it(self) -> None:
        """The credit is already on the ledger; earmarking it must not re-book it."""
        invoice = _make_invoice(self.customer, self.tax, unit_price='100.00')
        ledger.record_invoice_issued(invoice)
        # 50 credit − 120 invoice
        self.assertEqual(ledger.customer_balance(self.customer), Decimal('-70.00'))

        ledger.apply_credit(invoice, Decimal('50.00'), datetime.date(2026, 6, 15))
        invoice.refresh_from_db()

        # The balance is unchanged — the money was already counted …
        self.assertEqual(ledger.customer_balance(self.customer), Decimal('-70.00'))
        # … but the invoice is now partly settled.
        self.assertEqual(invoice.paid_amount, Decimal('50.00'))
        self.assertEqual(invoice.open_amount, Decimal('70.00'))

    def test_credit_payment_books_no_ledger_entry(self) -> None:
        invoice = _make_invoice(self.customer, self.tax)
        ledger.record_invoice_issued(invoice)
        payment = ledger.apply_credit(invoice, Decimal('50.00'))
        self.assertFalse(payment.affects_balance)
        self.assertFalse(
            CustomerLedgerEntry.objects.filter(payment=payment).exists())

    def test_more_than_available_credit_is_rejected(self) -> None:
        invoice = _make_invoice(self.customer, self.tax)
        ledger.record_invoice_issued(invoice)
        with self.assertRaises(ledger.CreditError):
            ledger.apply_credit(invoice, Decimal('80.00'))

    def test_more_than_the_open_amount_is_rejected(self) -> None:
        invoice = _make_invoice(self.customer, self.tax, unit_price='20.00')
        ledger.record_invoice_issued(invoice)  # 24.00 gross
        with self.assertRaises(ledger.CreditError):
            ledger.apply_credit(invoice, Decimal('50.00'))

    def test_zero_or_negative_is_rejected(self) -> None:
        invoice = _make_invoice(self.customer, self.tax)
        ledger.record_invoice_issued(invoice)
        with self.assertRaises(ledger.CreditError):
            ledger.apply_credit(invoice, Decimal('0.00'))


class AvailableCreditEdgeCaseTests(TestCase):
    """available_credit is unconsumed money, not simply a positive balance."""

    def setUp(self) -> None:
        self.tax = _make_tax()
        self.customer = _make_customer()

    def test_prepayment_stays_available_while_an_invoice_is_outstanding(self) -> None:
        prepayment = Payment.objects.create(
            customer=self.customer,
            payment_date=datetime.date(2026, 6, 1),
            amount=Decimal('50.00'),
        )
        ledger.record_payment(prepayment)
        invoice = _make_invoice(self.customer, self.tax)
        ledger.record_invoice_issued(invoice)

        # The customer owes money overall …
        self.assertEqual(ledger.customer_balance(self.customer), Decimal('-70.00'))
        # … but the prepayment is still unused and can be earmarked.
        self.assertEqual(ledger.available_credit(self.customer), Decimal('50.00'))

    def test_credit_cannot_be_applied_twice(self) -> None:
        prepayment = Payment.objects.create(
            customer=self.customer,
            payment_date=datetime.date(2026, 6, 1),
            amount=Decimal('50.00'),
        )
        ledger.record_payment(prepayment)
        invoice = _make_invoice(self.customer, self.tax)
        ledger.record_invoice_issued(invoice)

        ledger.apply_credit(invoice, Decimal('50.00'))
        self.assertEqual(ledger.available_credit(self.customer), Decimal('0.00'))

        second = _make_invoice(self.customer, self.tax, number='RE260601-00002')
        ledger.record_invoice_issued(second)
        with self.assertRaises(ledger.CreditError):
            ledger.apply_credit(second, Decimal('50.00'))

    def test_overpayment_stays_available(self) -> None:
        invoice = _make_invoice(self.customer, self.tax)  # 120.00 gross
        ledger.record_invoice_issued(invoice)
        payment = Payment.objects.create(
            customer=self.customer,
            invoice=invoice,
            payment_date=datetime.date(2026, 7, 1),
            amount=Decimal('150.00'),
        )
        ledger.record_payment(payment)

        self.assertEqual(ledger.customer_balance(self.customer), Decimal('30.00'))
        self.assertEqual(ledger.available_credit(self.customer), Decimal('30.00'))

    def test_a_fully_paid_invoice_consumes_its_payment(self) -> None:
        invoice = _make_invoice(self.customer, self.tax)
        ledger.record_invoice_issued(invoice)
        payment = Payment.objects.create(
            customer=self.customer,
            invoice=invoice,
            payment_date=datetime.date(2026, 7, 1),
            amount=Decimal('120.00'),
        )
        ledger.record_payment(payment)
        self.assertEqual(ledger.available_credit(self.customer), Decimal('0.00'))

    def test_cancelling_a_paid_invoice_frees_the_money_again(self) -> None:
        invoice = _make_invoice(self.customer, self.tax)
        ledger.record_invoice_issued(invoice)
        payment = Payment.objects.create(
            customer=self.customer,
            invoice=invoice,
            payment_date=datetime.date(2026, 7, 1),
            amount=Decimal('120.00'),
        )
        ledger.record_payment(payment)
        self.assertEqual(ledger.available_credit(self.customer), Decimal('0.00'))

        invoice.status = Invoice.Status.CANCELLED
        invoice.save(update_fields=['status'])
        self.assertEqual(ledger.available_credit(self.customer), Decimal('120.00'))

    def test_reminder_fee_is_consumed_by_a_payment_covering_it(self) -> None:
        invoice = _make_invoice(self.customer, self.tax)
        ledger.record_invoice_issued(invoice)
        reminder = Reminder.objects.create(
            invoice=invoice,
            level=1,
            number='MA260701',
            status=Reminder.Status.ISSUED,
            reminder_date=datetime.date(2026, 7, 1),
            due_date=datetime.date(2026, 7, 15),
            fee=Decimal('12.00'),
        )
        ledger.record_reminder_issued(reminder)
        payment = Payment.objects.create(
            customer=self.customer,
            invoice=invoice,
            payment_date=datetime.date(2026, 7, 20),
            amount=Decimal('132.00'),
        )
        ledger.record_payment(payment)

        self.assertEqual(ledger.customer_balance(self.customer), Decimal('0.00'))
        self.assertEqual(ledger.available_credit(self.customer), Decimal('0.00'))


class CreditWorkedExampleTests(TestCase):
    """The worked example in docs/fakturierung-handbuch.md, section 6.3.

    Balance +10, issue an invoice of 5, settle it from the credit.  Pinned as a
    test so the documented figures cannot drift away from the behaviour.
    """

    def setUp(self) -> None:
        self.customer = _make_customer()
        # 0 % tax keeps the example arithmetic identical to the handbook.
        self.tax = TaxRate.objects.create(name='Ohne', percent=Decimal('0.00'))

    def test_worked_example(self) -> None:
        prepayment = Payment.objects.create(
            customer=self.customer,
            payment_date=datetime.date(2026, 9, 1),
            amount=Decimal('10.00'),
        )
        ledger.record_payment(prepayment)
        self.assertEqual(ledger.customer_balance(self.customer), Decimal('10.00'))
        self.assertEqual(ledger.available_credit(self.customer), Decimal('10.00'))

        invoice = _make_invoice(self.customer, self.tax, unit_price='5.00')
        ledger.record_invoice_issued(invoice)
        # Issuing the invoice is what moves the balance — 10 − 5.
        self.assertEqual(ledger.customer_balance(self.customer), Decimal('5.00'))
        # The prepayment is untouched so far, so all of it is still applicable.
        self.assertEqual(ledger.available_credit(self.customer), Decimal('10.00'))

        ledger.apply_credit(invoice, Decimal('5.00'), datetime.date(2026, 9, 16))
        invoice.refresh_from_db()
        ledger.recalculate_invoice_status(invoice)
        invoice.refresh_from_db()

        # Applying the credit books no further movement: the balance stays +5.
        # Booking one would leave 0.00 and deduct the prepayment twice.
        self.assertEqual(ledger.customer_balance(self.customer), Decimal('5.00'))
        self.assertEqual(ledger.available_credit(self.customer), Decimal('5.00'))
        self.assertEqual(invoice.status, Invoice.Status.PAID)
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
        payment = Payment.objects.create(
            customer=self.customer,
            payment_date=datetime.date(2026, 9, 1),
            amount=Decimal('50.00'),
        )
        ledger.record_payment(payment)

    def _issue_invoice(self) -> Invoice:
        invoice = _make_invoice(self.customer, self.tax, unit_price='120.00')
        ledger.record_invoice_issued(invoice)
        return invoice

    def test_credit_before_the_invoice_is_offset_immediately(self) -> None:
        self._prepay()
        invoice = self._issue_invoice()
        # Mirrors what InvoiceViewSet.issue() does after recording the charge.
        ledger.apply_credit(invoice, Decimal('50.00'), invoice.document_date)
        invoice.refresh_from_db()

        self.assertEqual(ledger.customer_balance(self.customer), Decimal('-70.00'))
        self.assertEqual(ledger.available_credit(self.customer), Decimal('0.00'))
        self.assertEqual(invoice.open_amount, Decimal('70.00'))

    def test_credit_after_the_invoice_stays_unassigned(self) -> None:
        invoice = self._issue_invoice()
        self._prepay()
        invoice.refresh_from_db()

        # Same saldo as the other ordering …
        self.assertEqual(ledger.customer_balance(self.customer), Decimal('-70.00'))
        # … but the money is not assigned to the invoice yet.
        self.assertEqual(ledger.available_credit(self.customer), Decimal('50.00'))
        self.assertEqual(invoice.open_amount, Decimal('120.00'))

    def test_offsetting_afterwards_reaches_the_same_state(self) -> None:
        invoice = self._issue_invoice()
        self._prepay()
        ledger.apply_credit(invoice, Decimal('50.00'), datetime.date(2026, 9, 20))
        invoice.refresh_from_db()

        self.assertEqual(ledger.customer_balance(self.customer), Decimal('-70.00'))
        self.assertEqual(ledger.available_credit(self.customer), Decimal('0.00'))
        self.assertEqual(invoice.open_amount, Decimal('70.00'))


class IsReversalTests(TestCase):
    """Reversals must not read as ordinary charges next to what they cancel."""

    def setUp(self) -> None:
        self.tax = _make_tax()
        self.customer = _make_customer()
        self.invoice = _make_invoice(self.customer, self.tax)

    def test_a_normal_invoice_charge_is_not_a_reversal(self) -> None:
        entry = ledger.record_invoice_issued(self.invoice)
        self.assertFalse(entry.is_reversal)

    def test_a_storno_charge_is_a_reversal(self) -> None:
        storno = Invoice.objects.create(
            customer=self.customer,
            address=self.customer.default_address,
            number='RE260601-00002',
            document_date=datetime.date(2026, 6, 20),
            due_date=datetime.date(2026, 6, 20),
            reverses=self.invoice,
            status=Invoice.Status.ISSUED,
        )
        InvoiceLine.objects.create(
            invoice=storno, position=1, description='Leistung',
            quantity=Decimal('-1'), unit_price=Decimal('100.00'), tax_rate=self.tax,
        )
        entry = ledger.record_invoice_issued(storno)
        self.assertTrue(entry.is_reversal)

    def test_a_charged_reminder_fee_is_not_a_reversal(self) -> None:
        reminder = Reminder.objects.create(
            invoice=self.invoice, level=1, number='MA1',
            status=Reminder.Status.ISSUED,
            reminder_date=datetime.date(2026, 7, 1),
            due_date=datetime.date(2026, 7, 15),
            fee=Decimal('12.00'),
        )
        entry = ledger.record_reminder_issued(reminder)
        self.assertFalse(entry.is_reversal)

    def test_a_credited_back_reminder_fee_is_a_reversal(self) -> None:
        Reminder.objects.create(
            invoice=self.invoice, level=1, number='MA1',
            status=Reminder.Status.ISSUED,
            reminder_date=datetime.date(2026, 7, 1),
            due_date=datetime.date(2026, 7, 15),
            fee=Decimal('12.00'),
        )
        entries = ledger.reverse_reminder_fees(self.invoice)
        self.assertTrue(all(e.is_reversal for e in entries))

    def test_a_payment_is_never_a_reversal(self) -> None:
        payment = Payment.objects.create(
            customer=self.customer, invoice=self.invoice,
            payment_date=datetime.date(2026, 7, 1), amount=Decimal('120.00'),
        )
        entry = ledger.record_payment(payment)
        self.assertFalse(entry.is_reversal)

    def test_the_ledger_endpoint_reports_it(self) -> None:
        from django.contrib.auth.models import User
        from rest_framework.test import APIClient

        ledger.record_invoice_issued(self.invoice)
        storno = Invoice.objects.create(
            customer=self.customer,
            address=self.customer.default_address,
            number='RE260601-00002',
            document_date=datetime.date(2026, 6, 20),
            due_date=datetime.date(2026, 6, 20),
            reverses=self.invoice,
            status=Invoice.Status.ISSUED,
        )
        InvoiceLine.objects.create(
            invoice=storno, position=1, description='Leistung',
            quantity=Decimal('-1'), unit_price=Decimal('100.00'), tax_rate=self.tax,
        )
        ledger.record_invoice_issued(storno)

        client = APIClient()
        client.force_authenticate(
            user=User.objects.create_superuser('t', 't@example.com', 'p'))
        entries = client.get(
            f'/api/customers/{self.customer.pk}/ledger/').json()['entries']

        self.assertEqual([e['is_reversal'] for e in entries], [False, True])
