"""API view tests for the billing app."""
import datetime
from decimal import Decimal
from unittest.mock import patch

from core.models import Address
from deliveries.models import TaxRate
from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from billing.models import (
    BillingArticle,
    Invoice,
    InvoiceLine,
    Offer,
    OfferLine,
    Reminder,
)


def _create_user() -> User:
    return User.objects.create_superuser('test', 'test@example.com', 'password')


def _make_tax() -> TaxRate:
    return TaxRate.objects.create(name='Normal', percent=Decimal('20.00'))


def _make_address(**kwargs: object) -> Address:
    defaults: dict[str, object] = {'vorname': 'Max', 'nachname': 'Mustermann', 'ort': 'Wien'}
    defaults.update(kwargs)
    return Address.objects.create(**defaults)


def _make_offer(address: Address, status: str = 'draft') -> Offer:
    return Offer.objects.create(
        address=address,
        document_date=datetime.date(2026, 6, 15),
        status=status,
    )


def _make_invoice(address: Address, status: str = 'draft') -> Invoice:
    return Invoice.objects.create(
        address=address,
        document_date=datetime.date(2026, 6, 15),
        due_date=datetime.date(2026, 6, 29),
        status=status,
    )


# ---------------------------------------------------------------------------
# Address
# ---------------------------------------------------------------------------

class AddressViewSetTests(APITestCase):
    def setUp(self) -> None:
        self.user = _create_user()
        self.client.force_authenticate(user=self.user)

    def test_list(self) -> None:
        _make_address()
        resp = self.client.get('/api/addresses/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()['results']), 1)

    def test_create(self) -> None:
        resp = self.client.post('/api/addresses/', {
            'vorname': 'Maria', 'nachname': 'Muster', 'ort': 'Graz',
        })
        self.assertEqual(resp.status_code, 201)
        self.assertIsNone(resp.json()['wz_source_id'])

    def test_update(self) -> None:
        addr = _make_address()
        resp = self.client.patch(f'/api/addresses/{addr.pk}/', {'ort': 'Salzburg'})
        self.assertEqual(resp.status_code, 200)
        addr.refresh_from_db()
        self.assertEqual(addr.ort, 'Salzburg')

    def test_delete(self) -> None:
        addr = _make_address()
        resp = self.client.delete(f'/api/addresses/{addr.pk}/')
        self.assertEqual(resp.status_code, 204)

    def test_filter_by_query(self) -> None:
        _make_address(vorname='Max')
        _make_address(vorname='Maria', nachname='Muster')
        resp = self.client.get('/api/addresses/?q=maria')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()['results']), 1)


# ---------------------------------------------------------------------------
# BillingArticle
# ---------------------------------------------------------------------------

class BillingArticleViewSetTests(APITestCase):
    def setUp(self) -> None:
        self.user = _create_user()
        self.client.force_authenticate(user=self.user)
        self.tax = _make_tax()

    def test_create_and_list(self) -> None:
        resp = self.client.post('/api/billing-articles/', {
            'name': 'Beratungsleistung', 'unit_price': '150.00',
            'tax_rate': self.tax.pk, 'unit': 'Stunde',
        })
        self.assertEqual(resp.status_code, 201)
        resp_list = self.client.get('/api/billing-articles/')
        self.assertEqual(len(resp_list.json()['results']), 1)

    def test_auto_number_assigned_when_blank(self) -> None:
        resp = self.client.post('/api/billing-articles/', {
            'name': 'AutoArtikel', 'unit_price': '10.00',
        })
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()['article_number'], '#0001')

    def test_auto_numbers_sequential(self) -> None:
        r1 = self.client.post('/api/billing-articles/', {'name': 'A', 'unit_price': '1.00'})
        r2 = self.client.post('/api/billing-articles/', {'name': 'B', 'unit_price': '2.00'})
        self.assertEqual(r1.json()['article_number'], '#0001')
        self.assertEqual(r2.json()['article_number'], '#0002')

    def test_manual_number_preserved(self) -> None:
        resp = self.client.post('/api/billing-articles/', {
            'name': 'ManuellerArtikel', 'unit_price': '50.00', 'article_number': 'ART-42',
        })
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()['article_number'], 'ART-42')

    def test_manual_number_hash_prefix_rejected(self) -> None:
        resp = self.client.post('/api/billing-articles/', {
            'name': 'HashArtikel', 'unit_price': '5.00', 'article_number': '#manual',
        })
        self.assertEqual(resp.status_code, 400)
        self.assertIn('article_number', resp.json())

    def test_active_filter(self) -> None:
        BillingArticle.objects.create(name='Aktiv', unit_price=Decimal('10'), is_active=True)
        BillingArticle.objects.create(name='Inaktiv', unit_price=Decimal('5'), is_active=False)
        resp = self.client.get('/api/billing-articles/?active=true')
        self.assertEqual(len(resp.json()['results']), 1)
        self.assertEqual(resp.json()['results'][0]['name'], 'Aktiv')


# ---------------------------------------------------------------------------
# Offer + lines + actions
# ---------------------------------------------------------------------------

class OfferViewSetTests(APITestCase):
    def setUp(self) -> None:
        self.user = _create_user()
        self.client.force_authenticate(user=self.user)
        self.tax = _make_tax()
        self.address = _make_address()

    def test_create_offer(self) -> None:
        resp = self.client.post('/api/offers/', {
            'address': self.address.pk,
            'document_date': '2026-06-15',
        })
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()['status'], 'draft')
        self.assertIsNone(resp.json()['number'])

    def test_lines_replace(self) -> None:
        offer = _make_offer(self.address)
        lines_data = [
            {
                'offer': offer.pk, 'position': 1, 'description': 'Pos 1',
                'quantity': '2.0000', 'unit_price': '50.00', 'tax_rate': self.tax.pk,
            },
        ]
        resp = self.client.post(f'/api/offers/{offer.pk}/lines/', lines_data, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 1)

        # Replace with two lines
        lines_data2 = [
            {'offer': offer.pk, 'position': 1, 'description': 'A', 'quantity': '1', 'unit_price': '10.00', 'tax_rate': self.tax.pk},
            {'offer': offer.pk, 'position': 2, 'description': 'B', 'quantity': '1', 'unit_price': '20.00', 'tax_rate': self.tax.pk},
        ]
        resp2 = self.client.post(f'/api/offers/{offer.pk}/lines/', lines_data2, format='json')
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(len(resp2.json()), 2)
        self.assertEqual(OfferLine.objects.filter(offer=offer).count(), 2)

    @patch('billing.views.allocate_number', return_value='AN260601')
    def test_issue_assigns_number(self, mock_alloc: object) -> None:
        offer = _make_offer(self.address)
        resp = self.client.post(f'/api/offers/{offer.pk}/issue/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['number'], 'AN260601')
        self.assertEqual(resp.json()['status'], 'issued')

    def test_issue_non_draft_fails(self) -> None:
        offer = _make_offer(self.address, status='sent')
        resp = self.client.post(f'/api/offers/{offer.pk}/issue/')
        self.assertEqual(resp.status_code, 400)

    def test_convert_creates_invoice(self) -> None:
        offer = _make_offer(self.address, status='issued')
        OfferLine.objects.create(
            offer=offer, position=1, description='Test',
            quantity=Decimal('1'), unit_price=Decimal('100'), tax_rate=self.tax,
        )
        resp = self.client.post(f'/api/offers/{offer.pk}/convert/')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()['status'], 'draft')
        # Invoice lines copied
        invoice_pk = resp.json()['id']
        inv_lines = self.client.get(f'/api/invoices/{invoice_pk}/lines/')
        self.assertEqual(len(inv_lines.json()), 1)
        self.assertEqual(inv_lines.json()[0]['description'], 'Test')
        # Offer status changed
        offer.refresh_from_db()
        self.assertEqual(offer.status, 'converted')

    def test_convert_draft_fails(self) -> None:
        offer = _make_offer(self.address)
        resp = self.client.post(f'/api/offers/{offer.pk}/convert/')
        self.assertEqual(resp.status_code, 400)

    def test_preview_returns_html(self) -> None:
        offer = _make_offer(self.address)
        resp = self.client.get(f'/api/offers/{offer.pk}/preview/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('text/html', resp['Content-Type'])


# ---------------------------------------------------------------------------
# Invoice + actions
# ---------------------------------------------------------------------------

class InvoiceViewSetTests(APITestCase):
    def setUp(self) -> None:
        self.user = _create_user()
        self.client.force_authenticate(user=self.user)
        self.tax = _make_tax()
        self.address = _make_address()

    def test_create_invoice(self) -> None:
        resp = self.client.post('/api/invoices/', {
            'address': self.address.pk,
            'document_date': '2026-06-15',
            'due_date': '2026-06-29',
        })
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()['status'], 'draft')

    @patch('billing.views.allocate_number', return_value='RE260601')
    def test_issue_invoice(self, mock_alloc: object) -> None:
        invoice = _make_invoice(self.address)
        resp = self.client.post(f'/api/invoices/{invoice.pk}/issue/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['number'], 'RE260601')
        self.assertEqual(resp.json()['status'], 'issued')

    @patch('billing.views.allocate_number', return_value='RE260601')
    def test_mark_paid(self, mock_alloc: object) -> None:
        invoice = _make_invoice(self.address, status='issued')
        invoice.number = 'RE260601'
        invoice.save()
        resp = self.client.post(f'/api/invoices/{invoice.pk}/mark-paid/', {'paid_at': '2026-07-01'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['status'], 'paid')
        self.assertEqual(resp.json()['paid_at'], '2026-07-01')

    def test_update_draft_allowed(self) -> None:
        invoice = _make_invoice(self.address)
        resp = self.client.patch(f'/api/invoices/{invoice.pk}/', {'notes': 'Updated'})
        self.assertEqual(resp.status_code, 200)

    def test_update_non_draft_rejected(self) -> None:
        invoice = _make_invoice(self.address, status='issued')
        resp = self.client.patch(f'/api/invoices/{invoice.pk}/', {'notes': 'Updated'})
        self.assertEqual(resp.status_code, 400)

    def test_delete_draft_allowed(self) -> None:
        invoice = _make_invoice(self.address)
        resp = self.client.delete(f'/api/invoices/{invoice.pk}/')
        self.assertEqual(resp.status_code, 204)

    def test_delete_non_draft_rejected(self) -> None:
        for st in ('issued', 'sent', 'paid', 'cancelled'):
            invoice = _make_invoice(self.address, status=st)
            resp = self.client.delete(f'/api/invoices/{invoice.pk}/')
            self.assertEqual(resp.status_code, 400, msg=f'Expected 400 for status={st}')

    def test_lines_post_non_draft_rejected(self) -> None:
        invoice = _make_invoice(self.address, status='issued')
        resp = self.client.post(f'/api/invoices/{invoice.pk}/lines/', [], format='json')
        self.assertEqual(resp.status_code, 400)

    @patch('billing.views.allocate_number', return_value='RE260699')
    def test_cancel_issued_invoice(self, mock_alloc: object) -> None:
        invoice = _make_invoice(self.address, status='issued')
        invoice.number = 'RE260601'
        invoice.save()
        resp = self.client.post(
            f'/api/invoices/{invoice.pk}/cancel/',
            {'reason': 'Falsche Adresse'},
            format='json',
        )
        self.assertEqual(resp.status_code, 201)
        # Original becomes cancelled
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, 'cancelled')
        # Response contains the reverse invoice
        self.assertIn('reverse', resp.json())
        self.assertEqual(resp.json()['reverse']['status'], 'issued')

    @patch('billing.views.allocate_number', return_value='RE260699')
    def test_cancel_sent_invoice(self, mock_alloc: object) -> None:
        invoice = _make_invoice(self.address, status='sent')
        invoice.number = 'RE260602'
        invoice.save()
        resp = self.client.post(
            f'/api/invoices/{invoice.pk}/cancel/',
            {'reason': 'Storno auf Kundenwunsch'},
            format='json',
        )
        self.assertEqual(resp.status_code, 201)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, 'cancelled')

    def test_cancel_draft_fails(self) -> None:
        invoice = _make_invoice(self.address)
        resp = self.client.post(
            f'/api/invoices/{invoice.pk}/cancel/',
            {'reason': 'Irrtum'},
            format='json',
        )
        self.assertEqual(resp.status_code, 400)

    def test_cancel_requires_reason(self) -> None:
        invoice = _make_invoice(self.address, status='issued')
        # No reason at all
        resp = self.client.post(f'/api/invoices/{invoice.pk}/cancel/', {}, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('Stornierungsgrund', resp.json()['detail'])
        # Empty string reason
        resp2 = self.client.post(
            f'/api/invoices/{invoice.pk}/cancel/', {'reason': '   '}, format='json',
        )
        self.assertEqual(resp2.status_code, 400)
        # Nothing was cancelled
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, 'issued')

    @patch('billing.views.allocate_number', return_value='RE260699')
    def test_cancel_creates_reverse_invoice(self, mock_alloc: object) -> None:
        """Reverse invoice has negated lines, issued status, and links back to original."""
        invoice = _make_invoice(self.address, status='issued')
        invoice.number = 'RE260603'
        invoice.save()
        InvoiceLine.objects.create(
            invoice=invoice, position=1, description='Beratung',
            quantity=Decimal('2.0000'), unit_price=Decimal('100.00'), tax_rate=self.tax,
        )
        resp = self.client.post(
            f'/api/invoices/{invoice.pk}/cancel/',
            {'reason': 'Doppelt erfasst', 'create_draft': False},
            format='json',
        )
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertIsNone(data['draft'])
        reverse_data = data['reverse']
        self.assertEqual(reverse_data['status'], 'issued')
        self.assertEqual(reverse_data['reverses'], invoice.pk)
        self.assertEqual(reverse_data['number'], 'RE260699')
        self.assertIn('Stornorechnung für Rechnung RE260603', reverse_data['notes'])
        self.assertIn('Doppelt erfasst', reverse_data['notes'])
        # Line quantities are negated
        reverse_id = reverse_data['id']
        lines_resp = self.client.get(f'/api/invoices/{reverse_id}/lines/')
        lines = lines_resp.json()
        self.assertEqual(len(lines), 1)
        self.assertEqual(Decimal(lines[0]['quantity']), Decimal('-2.0000'))
        self.assertEqual(Decimal(lines[0]['unit_price']), Decimal('100.00'))
        # Totals are negative
        self.assertLess(Decimal(reverse_data['net_total']), Decimal('0'))

    @patch('billing.views.allocate_number', return_value='RE260699')
    def test_cancel_with_create_draft(self, mock_alloc: object) -> None:
        """When create_draft=True, a draft copy of the original is also returned."""
        invoice = _make_invoice(self.address, status='issued')
        invoice.number = 'RE260604'
        invoice.save()
        InvoiceLine.objects.create(
            invoice=invoice, position=1, description='Test',
            quantity=Decimal('1.0000'), unit_price=Decimal('50.00'), tax_rate=self.tax,
        )
        resp = self.client.post(
            f'/api/invoices/{invoice.pk}/cancel/',
            {'reason': 'Korrektur erforderlich', 'create_draft': True},
            format='json',
        )
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        draft_data = data['draft']
        self.assertIsNotNone(draft_data)
        self.assertEqual(draft_data['status'], 'draft')
        self.assertIsNone(draft_data['reverses'])
        # Draft has positive lines (copy of original)
        draft_id = draft_data['id']
        lines_resp = self.client.get(f'/api/invoices/{draft_id}/lines/')
        lines = lines_resp.json()
        self.assertEqual(len(lines), 1)
        self.assertEqual(Decimal(lines[0]['quantity']), Decimal('1.0000'))

    @patch('billing.views.allocate_number', return_value='RE260699')
    def test_cancel_sets_original_cancelled(self, mock_alloc: object) -> None:
        """Original invoice status must be cancelled after the reversal."""
        invoice = _make_invoice(self.address, status='issued')
        invoice.number = 'RE260605'
        invoice.save()
        self.client.post(
            f'/api/invoices/{invoice.pk}/cancel/',
            {'reason': 'Storno'},
            format='json',
        )
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.Status.CANCELLED)

    @patch('billing.views.allocate_number', return_value='RE260699')
    def test_cancel_reversal_heading_in_preview(self, mock_alloc: object) -> None:
        """Preview HTML for a reversal invoice must contain 'Stornorechnung'."""
        invoice = _make_invoice(self.address, status='issued')
        invoice.number = 'RE260606'
        invoice.save()
        resp = self.client.post(
            f'/api/invoices/{invoice.pk}/cancel/',
            {'reason': 'Test'},
            format='json',
        )
        reverse_id = resp.json()['reverse']['id']
        preview = self.client.get(f'/api/invoices/{reverse_id}/preview/')
        self.assertEqual(preview.status_code, 200)
        self.assertIn('Stornorechnung', preview.content.decode())

    def test_mark_paid_from_sent(self) -> None:
        invoice = _make_invoice(self.address, status='sent')
        resp = self.client.post(f'/api/invoices/{invoice.pk}/mark-paid/', {'paid_at': '2026-07-01'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['status'], 'paid')

    def test_preview_returns_html(self) -> None:
        invoice = _make_invoice(self.address)
        resp = self.client.get(f'/api/invoices/{invoice.pk}/preview/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('text/html', resp['Content-Type'])


# ---------------------------------------------------------------------------
# Reminder
# ---------------------------------------------------------------------------

class ReminderViewSetTests(APITestCase):
    def setUp(self) -> None:
        self.user = _create_user()
        self.client.force_authenticate(user=self.user)
        self.address = _make_address()
        self.invoice = _make_invoice(self.address, status='issued')
        self.invoice.number = 'RE260601'
        self.invoice.save()

    def test_create_reminder(self) -> None:
        resp = self.client.post('/api/reminders/', {
            'invoice': self.invoice.pk,
            'level': 1,
            'reminder_date': '2026-07-01',
            'due_date': '2026-07-15',
            'fee': '5.00',
        })
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()['status'], 'draft')

    @patch('billing.views.allocate_number', return_value='MA260701')
    def test_issue_reminder(self, mock_alloc: object) -> None:
        reminder = Reminder.objects.create(
            invoice=self.invoice,
            level=1,
            reminder_date=datetime.date(2026, 7, 1),
            due_date=datetime.date(2026, 7, 15),
        )
        resp = self.client.post(f'/api/reminders/{reminder.pk}/issue/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['number'], 'MA260701')

    def test_filter_by_invoice(self) -> None:
        Reminder.objects.create(
            invoice=self.invoice, level=1,
            reminder_date=datetime.date(2026, 7, 1),
            due_date=datetime.date(2026, 7, 15),
        )
        resp = self.client.get(f'/api/reminders/?invoice_id={self.invoice.pk}')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()['results']), 1)

    def test_preview_returns_html(self) -> None:
        reminder = Reminder.objects.create(
            invoice=self.invoice, level=1,
            reminder_date=datetime.date(2026, 7, 1),
            due_date=datetime.date(2026, 7, 15),
        )
        resp = self.client.get(f'/api/reminders/{reminder.pk}/preview/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('text/html', resp['Content-Type'])
