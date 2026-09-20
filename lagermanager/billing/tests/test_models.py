"""Tests for billing models — totals, address __str__, recipient snapshot."""
import datetime
from decimal import Decimal

from core.models import Address
from core.services.customers import ensure_customer_for_address
from deliveries.models import TaxRate
from django.test import TestCase

from billing.models import (
    Invoice,
    InvoiceLine,
    InvoiceTemplate,
    InvoiceTemplateLine,
    Offer,
    OfferLine,
    Payment,
    Reminder,
)


def _make_tax_rate(name: str = 'Normal', percent: str = '20.00') -> TaxRate:
    return TaxRate.objects.create(name=name, percent=Decimal(percent))


def _make_address(**kwargs: object) -> Address:
    defaults: dict[str, object] = {
        'vorname': 'Max',
        'nachname': 'Mustermann',
        'strasse': 'Musterstraße 1',
        'plz': '1010',
        'ort': 'Wien',
    }
    defaults.update(kwargs)
    address = Address.objects.create(**defaults)
    # Mirrors the API and the WZ sync: every address has a customer.
    ensure_customer_for_address(address)
    return address


class AddressStrTests(TestCase):
    def test_firma_preferred_over_name(self) -> None:
        a = Address(firma='Mustermann GmbH', vorname='Max', nachname='Muster')
        self.assertEqual(str(a), 'Mustermann GmbH')

    def test_full_name_fallback(self) -> None:
        a = Address(vorname='Max', nachname='Mustermann')
        self.assertEqual(str(a), 'Max Mustermann')

    def test_fallback_to_pk(self) -> None:
        a = Address.objects.create()
        self.assertIn(str(a.pk), str(a))

    def test_format_address_block(self) -> None:
        a = Address(
            anrede='Herr', vorname='Max', nachname='Mustermann',
            strasse='Musterstr. 1', plz='1010', ort='Wien',
        )
        block = a.format_address_block()
        self.assertIn('Herr', block)
        self.assertIn('Max Mustermann', block)
        self.assertIn('Musterstr. 1', block)
        self.assertIn('1010 Wien', block)


class OfferTotalTests(TestCase):
    def setUp(self) -> None:
        self.tax = _make_tax_rate('Normal', '20.00')
        self.tax_reduced = _make_tax_rate('Ermäßigt', '10.00')
        self.address = _make_address()
        self.offer = Offer.objects.create(
            customer=self.address.customer,
            address=self.address,
            document_date=datetime.date(2026, 6, 1),
        )

    def test_net_total_empty(self) -> None:
        self.assertEqual(self.offer.net_total, Decimal('0.00'))

    def test_gross_total_empty(self) -> None:
        self.assertEqual(self.offer.gross_total, Decimal('0.00'))

    def test_single_line_totals(self) -> None:
        OfferLine.objects.create(
            offer=self.offer,
            position=1,
            description='Produkt A',
            quantity=Decimal('2'),
            unit_price=Decimal('50.00'),
            tax_rate=self.tax,
        )
        self.offer.refresh_from_db()
        self.assertEqual(self.offer.net_total, Decimal('100.00'))
        self.assertEqual(self.offer.gross_total, Decimal('120.00'))
        self.assertEqual(self.offer.tax_total, Decimal('20.00'))

    def test_mixed_tax_rates(self) -> None:
        OfferLine.objects.create(
            offer=self.offer, position=1, description='A',
            quantity=Decimal('1'), unit_price=Decimal('100.00'), tax_rate=self.tax,
        )
        OfferLine.objects.create(
            offer=self.offer, position=2, description='B',
            quantity=Decimal('1'), unit_price=Decimal('100.00'), tax_rate=self.tax_reduced,
        )
        self.assertEqual(self.offer.net_total, Decimal('200.00'))
        self.assertEqual(self.offer.gross_total, Decimal('230.00'))
        self.assertEqual(self.offer.tax_total, Decimal('30.00'))

    def test_line_without_tax(self) -> None:
        line = OfferLine.objects.create(
            offer=self.offer, position=1, description='Dienstleistung',
            quantity=Decimal('1'), unit_price=Decimal('50.00'), tax_rate=None,
        )
        self.assertEqual(line.net_amount, Decimal('50.00'))
        self.assertEqual(line.gross_amount, Decimal('50.00'))


class InvoiceTotalTests(TestCase):
    def setUp(self) -> None:
        self.tax = _make_tax_rate()
        self.address = _make_address(firma='Test GmbH')
        self.invoice = Invoice.objects.create(
            customer=self.address.customer,
            address=self.address,
            document_date=datetime.date(2026, 6, 15),
        )

    def test_invoice_totals(self) -> None:
        InvoiceLine.objects.create(
            invoice=self.invoice, position=1, description='Service',
            quantity=Decimal('3'), unit_price=Decimal('100.00'), tax_rate=self.tax,
        )
        self.assertEqual(self.invoice.net_total, Decimal('300.00'))
        self.assertEqual(self.invoice.gross_total, Decimal('360.00'))

    def test_recipient_text_snapshot(self) -> None:
        """Snapshot is empty until issue action sets it; here we test the address block helper."""
        block = self.address.format_address_block()
        self.assertIn('Test GmbH', block)


class InvoiceTemplateTotalTests(TestCase):
    def setUp(self) -> None:
        self.tax = _make_tax_rate()
        self.template = InvoiceTemplate.objects.create(name='Monatliche Wartung')

    def test_totals_empty(self) -> None:
        self.assertEqual(self.template.net_total, Decimal('0.00'))
        self.assertEqual(self.template.gross_total, Decimal('0.00'))
        self.assertEqual(self.template.tax_total, Decimal('0.00'))

    def test_totals_with_lines(self) -> None:
        InvoiceTemplateLine.objects.create(
            template=self.template, position=1, description='Wartung',
            quantity=Decimal('2'), unit_price=Decimal('50.00'), tax_rate=self.tax,
        )
        self.assertEqual(self.template.net_total, Decimal('100.00'))
        self.assertEqual(self.template.gross_total, Decimal('120.00'))
        self.assertEqual(self.template.tax_total, Decimal('20.00'))

    def test_str(self) -> None:
        self.assertEqual(str(self.template), 'Monatliche Wartung')


class InvoicePaymentStateTests(TestCase):
    """total_due / paid_amount / open_amount across fees and payments."""

    def setUp(self) -> None:
        self.tax = _make_tax_rate('Normal', '20.00')
        self.address = _make_address()
        self.invoice = Invoice.objects.create(
            customer=self.address.customer,
            address=self.address,
            number='RE260601-00001',
            document_date=datetime.date(2026, 6, 15),
            due_date=datetime.date(2026, 6, 29),
            status=Invoice.Status.ISSUED,
        )
        InvoiceLine.objects.create(
            invoice=self.invoice, position=1, description='Leistung',
            quantity=Decimal('1'), unit_price=Decimal('100.00'), tax_rate=self.tax,
        )

    def _reminder(self, level: int, fee: str, status: str) -> Reminder:
        return Reminder.objects.create(
            invoice=self.invoice,
            level=level,
            status=status,
            number=f'MA{level}' if status != Reminder.Status.DRAFT else None,
            reminder_date=datetime.date(2026, 7, level),
            due_date=datetime.date(2026, 8, level),
            fee=Decimal(fee),
        )

    def _pay(self, amount: str, day: int = 1) -> Payment:
        return Payment.objects.create(
            customer=self.address.customer,
            invoice=self.invoice,
            payment_date=datetime.date(2026, 7, day),
            amount=Decimal(amount),
        )

    def test_without_fees_or_payments(self) -> None:
        self.assertEqual(self.invoice.reminder_fee_total, Decimal('0.00'))
        self.assertEqual(self.invoice.total_due, Decimal('120.00'))
        self.assertEqual(self.invoice.paid_amount, Decimal('0.00'))
        self.assertEqual(self.invoice.open_amount, Decimal('120.00'))
        self.assertFalse(self.invoice.is_fully_paid)

    def test_only_issued_reminder_fees_count(self) -> None:
        self._reminder(1, '12.00', Reminder.Status.ISSUED)
        self._reminder(2, '20.00', Reminder.Status.DRAFT)
        self.assertEqual(self.invoice.reminder_fee_total, Decimal('12.00'))
        self.assertEqual(self.invoice.total_due, Decimal('132.00'))

    def test_partial_payments_sum(self) -> None:
        self._pay('50.00')
        self._pay('30.00', day=15)
        self.assertEqual(self.invoice.paid_amount, Decimal('80.00'))
        self.assertEqual(self.invoice.open_amount, Decimal('40.00'))
        self.assertFalse(self.invoice.is_fully_paid)

    def test_fully_paid_once_the_sum_reaches_the_total(self) -> None:
        self._pay('120.00')
        self.assertTrue(self.invoice.is_fully_paid)

    def test_a_fee_reopens_a_paid_invoice(self) -> None:
        self._pay('120.00')
        self._reminder(1, '12.00', Reminder.Status.ISSUED)
        self.assertEqual(self.invoice.open_amount, Decimal('12.00'))
        self.assertFalse(self.invoice.is_fully_paid)

    def test_a_zero_total_invoice_is_not_fully_paid(self) -> None:
        empty = Invoice.objects.create(
            customer=self.address.customer,
            address=self.address,
            document_date=datetime.date(2026, 6, 15),
            due_date=datetime.date(2026, 6, 29),
        )
        self.assertEqual(empty.total_due, Decimal('0.00'))
        self.assertFalse(empty.is_fully_paid)


class ReminderOpenAmountTests(InvoicePaymentStateTests):
    """Reminder.open_amount accumulates earlier levels' fees and nets payments."""

    def test_level_1(self) -> None:
        reminder = self._reminder(1, '12.00', Reminder.Status.ISSUED)
        self.assertEqual(reminder.cumulative_fee, Decimal('12.00'))
        self.assertEqual(reminder.open_amount, Decimal('132.00'))

    def test_level_2_includes_the_level_1_fee(self) -> None:
        self._reminder(1, '12.00', Reminder.Status.ISSUED)
        second = self._reminder(2, '20.00', Reminder.Status.ISSUED)
        self.assertEqual(second.cumulative_fee, Decimal('32.00'))
        self.assertEqual(second.open_amount, Decimal('152.00'))

    def test_a_higher_level_does_not_count_towards_a_lower_one(self) -> None:
        first = self._reminder(1, '12.00', Reminder.Status.ISSUED)
        self._reminder(2, '20.00', Reminder.Status.ISSUED)
        self.assertEqual(first.cumulative_fee, Decimal('12.00'))

    def test_own_fee_counts_while_still_a_draft(self) -> None:
        """So that a preview shows what the customer will be asked to pay."""
        draft = self._reminder(1, '12.00', Reminder.Status.DRAFT)
        self.assertEqual(draft.cumulative_fee, Decimal('12.00'))

    def test_another_draft_does_not_count(self) -> None:
        self._reminder(1, '12.00', Reminder.Status.DRAFT)
        second = self._reminder(2, '20.00', Reminder.Status.ISSUED)
        self.assertEqual(second.cumulative_fee, Decimal('20.00'))

    def test_payments_are_subtracted(self) -> None:
        self._pay('50.00')
        reminder = self._reminder(1, '12.00', Reminder.Status.ISSUED)
        self.assertEqual(reminder.open_amount, Decimal('82.00'))

    def test_payments_listed_for_the_pdf(self) -> None:
        self._pay('50.00')
        reminder = self._reminder(1, '12.00', Reminder.Status.ISSUED)
        self.assertEqual([p.amount for p in reminder.payments], [Decimal('50.00')])
