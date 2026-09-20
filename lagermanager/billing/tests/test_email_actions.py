"""Tests for the email-info and send-email viewset actions."""
import datetime
from decimal import Decimal
from unittest.mock import patch

from core.models import Address
from core.services.customers import ensure_customer_for_address
from deliveries.models import TaxRate
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from emails.models import EmailLog
from rest_framework.test import APITestCase

from billing.models import Invoice, InvoiceLine, Offer, Reminder
from billing.services.render import build_email_defaults


def _create_user() -> User:
    return User.objects.create_superuser('test', 'test@example.com', 'password')


def _make_address(**kwargs: object) -> Address:
    defaults: dict[str, object] = {
        'vorname': 'Max', 'nachname': 'Mustermann', 'ort': 'Wien',
        'email': 'max@mustermann.at',
    }
    defaults.update(kwargs)
    address = Address.objects.create(**defaults)
    # Mirrors the API and the WZ sync: every address has a customer.
    ensure_customer_for_address(address)
    return address


def _make_tax() -> TaxRate:
    return TaxRate.objects.create(name='Normal', percent=Decimal('20.00'))


def _make_offer(address: Address, status: str = 'issued', number: str = 'AN2601-001') -> Offer:
    offer = Offer.objects.create(
        customer=address.customer,
        address=address,
        document_date=datetime.date(2026, 1, 15),
        status=status,
        number=number if status != 'draft' else None,
    )
    return offer


def _make_invoice(address: Address, status: str = 'issued') -> Invoice:
    inv = Invoice.objects.create(
        customer=address.customer,
        address=address,
        document_date=datetime.date(2026, 1, 15),
        due_date=datetime.date(2026, 1, 29),
        status=status,
        number='RE2601-001' if status != 'draft' else None,
    )
    tax = _make_tax()
    InvoiceLine.objects.create(
        invoice=inv, position=1, description='Dienstleistung',
        unit_price=Decimal('100.00'), quantity=Decimal('1'), tax_rate=tax,
    )
    return inv


def _make_reminder(invoice: Invoice) -> Reminder:
    return Reminder.objects.create(
        invoice=invoice,
        level=1,
        number='MA2601-001',
        status='issued',
        reminder_date=datetime.date(2026, 2, 1),
        due_date=datetime.date(2026, 2, 14),
    )


# ---------------------------------------------------------------------------
# email-info
# ---------------------------------------------------------------------------

class EmailInfoActionTests(APITestCase):
    def setUp(self) -> None:
        self.user = _create_user()
        self.client.force_authenticate(user=self.user)
        self.address = _make_address()
        self.invoice = _make_invoice(self.address)

    def test_returns_defaults_and_empty_log(self) -> None:
        resp = self.client.get(f'/api/invoices/{self.invoice.pk}/email-info/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('defaults', data)
        self.assertIn('log', data)
        self.assertEqual(data['log'], [])
        # defaults should prefill recipient from address
        self.assertEqual(data['defaults']['recipient'], 'max@mustermann.at')

    def test_log_contains_previous_sends(self) -> None:
        from django.contrib.contenttypes.models import ContentType
        ct = ContentType.objects.get_for_model(self.invoice)
        EmailLog.objects.create(
            from_email='from@co.at', recipient='x@y.com', subject='Test',
            status=EmailLog.Status.SENT, content_type=ct, object_id=str(self.invoice.pk),
        )
        resp = self.client.get(f'/api/invoices/{self.invoice.pk}/email-info/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()['log']), 1)


# ---------------------------------------------------------------------------
# send-email
# ---------------------------------------------------------------------------

@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class SendEmailActionTests(APITestCase):
    def setUp(self) -> None:
        self.user = _create_user()
        self.client.force_authenticate(user=self.user)
        self.address = _make_address()

    # ---- Invoice ------------------------------------------------------------

    def test_send_invoice_creates_log_and_flips_status(self) -> None:
        invoice = _make_invoice(self.address, status='issued')
        with patch('billing.views.render_document_pdf', return_value=b'%PDF'):
            resp = self.client.post(
                f'/api/invoices/{invoice.pk}/send-email/',
                {'recipient': 'client@example.com', 'subject': 'Ihre Rechnung', 'body': 'Hallo'},
                format='json',
            )
        self.assertEqual(resp.status_code, 200)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, 'sent')
        log = EmailLog.objects.get(recipient='client@example.com')
        self.assertEqual(log.status, EmailLog.Status.SENT)

    def test_send_invoice_twice_creates_two_log_entries(self) -> None:
        invoice = _make_invoice(self.address, status='issued')
        with patch('billing.views.render_document_pdf', return_value=b'%PDF'):
            self.client.post(
                f'/api/invoices/{invoice.pk}/send-email/',
                {'recipient': 'a@b.com', 'subject': 'S', 'body': ''},
                format='json',
            )
            # Now status is 'sent' — second send should also succeed
            self.client.post(
                f'/api/invoices/{invoice.pk}/send-email/',
                {'recipient': 'c@d.com', 'subject': 'S2', 'body': ''},
                format='json',
            )
        self.assertEqual(EmailLog.objects.count(), 2)

    def test_draft_invoice_returns_400(self) -> None:
        invoice = _make_invoice(self.address, status='draft')
        resp = self.client.post(
            f'/api/invoices/{invoice.pk}/send-email/',
            {'recipient': 'x@example.com', 'subject': 'S', 'body': ''},
            format='json',
        )
        self.assertEqual(resp.status_code, 400)

    def test_missing_recipient_returns_400(self) -> None:
        invoice = _make_invoice(self.address, status='issued')
        resp = self.client.post(
            f'/api/invoices/{invoice.pk}/send-email/',
            {'recipient': '', 'subject': 'S', 'body': ''},
            format='json',
        )
        self.assertEqual(resp.status_code, 400)

    def test_smtp_failure_records_failed_log_and_returns_502(self) -> None:
        invoice = _make_invoice(self.address, status='issued')
        with patch('billing.views.render_document_pdf', return_value=b'%PDF'), \
             patch('django.core.mail.EmailMessage.send', side_effect=OSError('SMTP down')):
            resp = self.client.post(
                f'/api/invoices/{invoice.pk}/send-email/',
                {'recipient': 'x@example.com', 'subject': 'S', 'body': ''},
                format='json',
            )
        self.assertEqual(resp.status_code, 502)
        self.assertEqual(EmailLog.objects.filter(status=EmailLog.Status.FAILED).count(), 1)

    # ---- Offer --------------------------------------------------------------

    def test_send_offer_creates_log_and_flips_status(self) -> None:
        offer = _make_offer(self.address)
        with patch('billing.views.render_document_pdf', return_value=b'%PDF'):
            resp = self.client.post(
                f'/api/offers/{offer.pk}/send-email/',
                {'recipient': 'client@example.com', 'subject': 'Ihr Angebot', 'body': ''},
                format='json',
            )
        self.assertEqual(resp.status_code, 200)
        offer.refresh_from_db()
        self.assertEqual(offer.status, 'sent')
        self.assertTrue(EmailLog.objects.filter(recipient='client@example.com').exists())

    # ---- Reminder -----------------------------------------------------------

    def test_send_reminder_logs_without_status_change(self) -> None:
        invoice = _make_invoice(self.address, status='issued')
        reminder = _make_reminder(invoice)
        self.assertEqual(reminder.status, 'issued')
        with patch('billing.views.render_document_pdf', return_value=b'%PDF'):
            resp = self.client.post(
                f'/api/reminders/{reminder.pk}/send-email/',
                {'recipient': 'late@payer.com', 'subject': 'Mahnung', 'body': ''},
                format='json',
            )
        self.assertEqual(resp.status_code, 200)
        reminder.refresh_from_db()
        # Reminder has no SENT status — should remain issued
        self.assertEqual(reminder.status, 'issued')
        self.assertEqual(EmailLog.objects.count(), 1)


class NamelessAddressLabelTests(TestCase):
    """A nameless address must not leak "Adresse #<pk>" to the customer."""

    def test_email_defaults_use_the_postal_address_as_the_name(self) -> None:
        from billing.services.render import build_email_defaults

        address = Address.objects.create(
            strasse='Papiermühlgasse 18/2/4', plz='8020', ort='Graz',
            email='kunde@example.com')
        ensure_customer_for_address(address)
        invoice = _make_invoice(address)

        defaults = build_email_defaults(invoice)
        blob = f'{defaults["subject"]} {defaults["body"]}'
        self.assertNotIn(f'Adresse #{address.pk}', blob)

    def test_invoice_list_shows_the_postal_address(self) -> None:
        from billing.serializers import InvoiceListSerializer

        address = Address.objects.create(
            strasse='Papiermühlgasse 18/2/4', plz='8020', ort='Graz')
        ensure_customer_for_address(address)
        invoice = _make_invoice(address)

        data = InvoiceListSerializer(invoice).data
        self.assertEqual(data['address_display'], 'Papiermühlgasse 18/2/4, 8020 Graz')


class RecipientResolutionTests(TestCase):
    """Address first, customer's billing e-mail as the fallback."""

    def _address(self, **kwargs: object) -> Address:
        defaults: dict[str, object] = {'vorname': 'Max', 'nachname': 'Mustermann'}
        defaults.update(kwargs)
        address = Address.objects.create(**defaults)
        ensure_customer_for_address(address)
        return address

    def test_the_documents_address_wins(self) -> None:
        address = self._address(email='addr@example.com')
        customer = address.customer
        customer.email = 'kunde@example.com'
        customer.save(update_fields=['email'])

        invoice = _make_invoice(address)
        self.assertEqual(
            build_email_defaults(invoice)['recipient'], 'addr@example.com')

    def test_falls_back_to_the_customers_own_email(self) -> None:
        address = self._address()  # no e-mail on the address
        customer = address.customer
        customer.email = 'kunde@example.com'
        customer.save(update_fields=['email'])

        invoice = _make_invoice(address)
        self.assertEqual(
            build_email_defaults(invoice)['recipient'], 'kunde@example.com')

    def test_falls_back_to_the_customers_default_address(self) -> None:
        """A second address without an e-mail borrows the default address's."""
        default = self._address(email='default@example.com')
        customer = default.customer
        delivery = Address.objects.create(
            customer=customer, strasse='Lieferstr. 1', plz='1010', ort='Wien')

        invoice = _make_invoice(delivery)
        self.assertEqual(
            build_email_defaults(invoice)['recipient'], 'default@example.com')

    def test_empty_when_nothing_is_on_file(self) -> None:
        address = self._address()
        invoice = _make_invoice(address)
        self.assertEqual(build_email_defaults(invoice)['recipient'], '')

    def test_a_reminder_uses_its_invoices_address(self) -> None:
        address = self._address(email='addr@example.com')
        invoice = _make_invoice(address)
        reminder = Reminder.objects.create(
            invoice=invoice, level=1, number='MA1',
            status=Reminder.Status.ISSUED,
            reminder_date=datetime.date(2026, 7, 1),
            due_date=datetime.date(2026, 7, 15),
        )
        self.assertEqual(
            build_email_defaults(reminder)['recipient'], 'addr@example.com')

    def test_a_reminder_falls_back_through_the_customer_too(self) -> None:
        address = self._address()
        customer = address.customer
        customer.email = 'kunde@example.com'
        customer.save(update_fields=['email'])

        invoice = _make_invoice(address)
        reminder = Reminder.objects.create(
            invoice=invoice, level=1, number='MA1',
            status=Reminder.Status.ISSUED,
            reminder_date=datetime.date(2026, 7, 1),
            due_date=datetime.date(2026, 7, 15),
        )
        self.assertEqual(
            build_email_defaults(reminder)['recipient'], 'kunde@example.com')
