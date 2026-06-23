"""Tests for billing models — totals, address __str__, recipient snapshot."""
import datetime
from decimal import Decimal

from core.models import Address
from deliveries.models import TaxRate
from django.test import TestCase

from billing.models import (
    Invoice,
    InvoiceLine,
    Offer,
    OfferLine,
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
    return Address.objects.create(**defaults)


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
