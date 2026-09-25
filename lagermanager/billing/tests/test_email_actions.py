"""Tests for the email-info and send-email viewset actions."""
import datetime
import shutil
import tempfile
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import patch

from constance.test import override_config
from core.models import Address
from core.services.customers import ensure_customer_for_address
from deliveries.models import TaxRate
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.core import mail
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from emails.models import EmailLog
from rest_framework.test import APITestCase

from billing.models import DocumentAttachment, Invoice, InvoiceLine, Offer, Reminder
from billing.services.render import build_email_defaults

ATTACHMENT_MEDIA_ROOT = tempfile.mkdtemp()


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


# ---------------------------------------------------------------------------
# send-email with document attachments
# ---------------------------------------------------------------------------

@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    MEDIA_ROOT=ATTACHMENT_MEDIA_ROOT,
)
class SendEmailAttachmentTests(APITestCase):
    """Which attachments the outgoing mail carries, and in what shape."""

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(ATTACHMENT_MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def setUp(self) -> None:
        self.user = _create_user()
        self.client.force_authenticate(user=self.user)
        self.address = _make_address()
        self.invoice = _make_invoice(self.address, status='issued')
        mail.outbox.clear()

    # -- helpers -----------------------------------------------------------

    def _supplement(self, delivery: str = DocumentAttachment.Delivery.MERGE,
                    **kwargs: object) -> DocumentAttachment:
        defaults: dict[str, object] = {
            'kind': 'supplement', 'title': 'Hinweis', 'body': 'Text',
            'delivery': delivery, 'position': 1,
        }
        defaults.update(kwargs)
        return DocumentAttachment.objects.create(
            content_type=ContentType.objects.get_for_model(self.invoice),
            object_id=self.invoice.pk,
            **defaults,
        )

    def _file(self, name: str = 'lieferschein.pdf',
              content: bytes = b'%PDF-1.4 datei') -> DocumentAttachment:
        attachment = DocumentAttachment(
            content_type=ContentType.objects.get_for_model(self.invoice),
            object_id=self.invoice.pk,
            kind='file', title='Lieferschein', position=2,
            delivery=DocumentAttachment.Delivery.SEPARATE,
            original_filename=name, mime_type='application/pdf',
            size_bytes=len(content),
        )
        attachment.file.save(name, ContentFile(content), save=False)
        attachment.save()
        return attachment

    def _send(self, **extra: object) -> Any:
        payload: dict[str, object] = {
            'recipient': 'client@example.com', 'subject': 'Ihre Rechnung', 'body': 'Hallo',
        }
        payload.update(extra)
        with patch('billing.views.render_document_pdf', return_value=b'%PDF-document'):
            return self.client.post(
                f'/api/invoices/{self.invoice.pk}/send-email/', payload, format='json')

    # -- email-info --------------------------------------------------------

    def test_email_info_lists_attachments(self) -> None:
        supplement = self._supplement()

        resp = self.client.get(f'/api/invoices/{self.invoice.pk}/email-info/')

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual([row['id'] for row in data['attachments']], [supplement.pk])
        self.assertEqual(data['mandatory_attachment_ids'], [])

    @override_config(EMAIL_DEFAULT_ATTACHMENT_KINDS='supplement')  # type: ignore[untyped-decorator]
    def test_default_selection_follows_the_setting(self) -> None:
        supplement = self._supplement()
        self._file()

        data = self.client.get(f'/api/invoices/{self.invoice.pk}/email-info/').json()

        self.assertEqual(data['default_attachment_ids'], [supplement.pk])

    @override_config(EMAIL_DEFAULT_ATTACHMENT_KINDS='')  # type: ignore[untyped-decorator]
    def test_empty_setting_preselects_nothing(self) -> None:
        self._supplement()

        data = self.client.get(f'/api/invoices/{self.invoice.pk}/email-info/').json()

        self.assertEqual(data['default_attachment_ids'], [])

    # -- sending -----------------------------------------------------------

    def test_without_attachment_ids_only_the_document_is_sent(self) -> None:
        self._supplement()

        resp = self._send()

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(mail.outbox[0].attachments), 1)
        self.assertEqual(mail.outbox[0].attachments[0][0], 'rechnung_RE2601-001.pdf')

    def test_merge_supplement_stays_one_pdf(self) -> None:
        supplement = self._supplement(delivery=DocumentAttachment.Delivery.MERGE)

        with patch('billing.attachments.handlers.render_html_to_pdf',
                   return_value=b'%PDF-supplement'), \
             patch('billing.attachments.send.merge_pdfs',
                   return_value=b'%PDF-merged') as merge:
            resp = self._send(attachment_ids=[supplement.pk])

        self.assertEqual(resp.status_code, 200, resp.data)
        merge.assert_called_once_with([b'%PDF-document', b'%PDF-supplement'])
        attachments = mail.outbox[0].attachments
        self.assertEqual(len(attachments), 1)
        self.assertEqual(attachments[0][1], b'%PDF-merged')

    def test_separate_supplement_travels_as_its_own_pdf(self) -> None:
        supplement = self._supplement(delivery=DocumentAttachment.Delivery.SEPARATE)

        with patch('billing.attachments.handlers.render_html_to_pdf',
                   return_value=b'%PDF-supplement'):
            resp = self._send(attachment_ids=[supplement.pk])

        self.assertEqual(resp.status_code, 200, resp.data)
        attachments = mail.outbox[0].attachments
        self.assertEqual(len(attachments), 2)
        self.assertEqual(attachments[0][1], b'%PDF-document')
        self.assertTrue(attachments[1][0].startswith('ergaenzung_RE2601-001'))
        self.assertEqual(attachments[1][1], b'%PDF-supplement')

    def test_file_attachment_round_trips_bytes_and_mime(self) -> None:
        uploaded = self._file()

        resp = self._send(attachment_ids=[uploaded.pk])

        self.assertEqual(resp.status_code, 200, resp.data)
        attachments = mail.outbox[0].attachments
        self.assertEqual(len(attachments), 2)
        self.assertEqual(attachments[1][0], 'lieferschein.pdf')
        self.assertEqual(attachments[1][1], b'%PDF-1.4 datei')
        self.assertEqual(attachments[1][2], 'application/pdf')

    def test_every_sent_file_is_recorded_on_the_log(self) -> None:
        supplement = self._supplement(delivery=DocumentAttachment.Delivery.SEPARATE)
        uploaded = self._file()

        with patch('billing.attachments.handlers.render_html_to_pdf',
                   return_value=b'%PDF-supplement'):
            self._send(attachment_ids=[supplement.pk, uploaded.pk])

        log = EmailLog.objects.get(recipient='client@example.com')
        self.assertEqual(log.attachments.count(), 3)

    def test_colliding_filenames_are_made_unique(self) -> None:
        first = self._file('beleg.pdf', b'%PDF-eins')
        second = self._file('beleg.pdf', b'%PDF-zwei')

        self._send(attachment_ids=[first.pk, second.pk])

        names = [name for name, _content, _mime in mail.outbox[0].attachments]
        self.assertEqual(names[1:], ['beleg.pdf', 'beleg_2.pdf'])

    def test_a_foreign_attachment_id_is_refused_and_nothing_is_sent(self) -> None:
        other_invoice = _make_invoice(self.address, status='issued')
        foreign = DocumentAttachment.objects.create(
            content_type=ContentType.objects.get_for_model(other_invoice),
            object_id=other_invoice.pk,
            kind='supplement', title='Fremd', body='Text', position=1,
        )

        resp = self._send(attachment_ids=[foreign.pk])

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(EmailLog.objects.count(), 0)

    def test_non_numeric_attachment_ids_are_refused(self) -> None:
        resp = self._send(attachment_ids=['nope'])

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(len(mail.outbox), 0)

    def test_a_missing_file_on_disk_is_reported_not_swallowed(self) -> None:
        uploaded = self._file()
        Path(uploaded.file.path).unlink()

        resp = self._send(attachment_ids=[uploaded.pk])

        self.assertEqual(resp.status_code, 400)
        self.assertIn('Lieferschein', resp.data['detail'])
        self.assertEqual(len(mail.outbox), 0)

    def test_attachments_work_for_offers_and_reminders(self) -> None:
        offer = _make_offer(self.address)
        reminder = _make_reminder(self.invoice)

        for doc, path in ((offer, f'/api/offers/{offer.pk}'),
                          (reminder, f'/api/reminders/{reminder.pk}')):
            with self.subTest(document=type(doc).__name__):
                mail.outbox.clear()
                attachment = DocumentAttachment.objects.create(
                    content_type=ContentType.objects.get_for_model(doc),
                    object_id=doc.pk, kind='supplement', title='Hinweis',
                    body='Text', position=1,
                    delivery=DocumentAttachment.Delivery.SEPARATE,
                )
                with patch('billing.views.render_document_pdf', return_value=b'%PDF-doc'), \
                     patch('billing.attachments.handlers.render_html_to_pdf',
                           return_value=b'%PDF-supp'):
                    resp = self.client.post(
                        f'{path}/send-email/',
                        {'recipient': 'client@example.com', 'subject': 'S', 'body': '',
                         'attachment_ids': [attachment.pk]},
                        format='json',
                    )
                self.assertEqual(resp.status_code, 200, resp.data)
                self.assertEqual(len(mail.outbox[0].attachments), 2)

    # -- send-pdf preview --------------------------------------------------

    def test_send_pdf_without_selection_is_the_bare_document(self) -> None:
        self._supplement()

        with patch('billing.views.render_document_pdf', return_value=b'%PDF-document'):
            resp = self.client.get(f'/api/invoices/{self.invoice.pk}/send-pdf/')

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/pdf')
        self.assertIn('inline', resp['Content-Disposition'])
        self.assertEqual(resp.content, b'%PDF-document')

    def test_send_pdf_includes_merged_attachments(self) -> None:
        supplement = self._supplement(delivery=DocumentAttachment.Delivery.MERGE)

        with patch('billing.views.render_document_pdf', return_value=b'%PDF-document'), \
             patch('billing.attachments.handlers.render_html_to_pdf',
                   return_value=b'%PDF-supplement'), \
             patch('billing.attachments.send.merge_pdfs',
                   return_value=b'%PDF-merged') as merge:
            resp = self.client.get(
                f'/api/invoices/{self.invoice.pk}/send-pdf/',
                {'attachment_ids': [supplement.pk]})

        self.assertEqual(resp.status_code, 200)
        merge.assert_called_once_with([b'%PDF-document', b'%PDF-supplement'])
        self.assertEqual(resp.content, b'%PDF-merged')

    def test_send_pdf_leaves_separate_attachments_out(self) -> None:
        supplement = self._supplement(delivery=DocumentAttachment.Delivery.SEPARATE)

        with patch('billing.views.render_document_pdf', return_value=b'%PDF-document'), \
             patch('billing.attachments.handlers.render_html_to_pdf',
                   return_value=b'%PDF-supplement'):
            resp = self.client.get(
                f'/api/invoices/{self.invoice.pk}/send-pdf/',
                {'attachment_ids': [supplement.pk]})

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content, b'%PDF-document')

    def test_send_pdf_refuses_a_foreign_attachment(self) -> None:
        other_invoice = _make_invoice(self.address, status='issued')
        foreign = DocumentAttachment.objects.create(
            content_type=ContentType.objects.get_for_model(other_invoice),
            object_id=other_invoice.pk,
            kind='supplement', title='Fremd', body='Text', position=1,
        )

        with patch('billing.views.render_document_pdf', return_value=b'%PDF-document'):
            resp = self.client.get(
                f'/api/invoices/{self.invoice.pk}/send-pdf/',
                {'attachment_ids': [foreign.pk]})

        self.assertEqual(resp.status_code, 400)

    def test_send_pdf_rejects_non_numeric_ids(self) -> None:
        resp = self.client.get(
            f'/api/invoices/{self.invoice.pk}/send-pdf/', {'attachment_ids': ['x']})

        self.assertEqual(resp.status_code, 400)

    def test_send_pdf_works_for_offers_and_reminders(self) -> None:
        offer = _make_offer(self.address)
        reminder = _make_reminder(self.invoice)

        for path in (f'/api/offers/{offer.pk}', f'/api/reminders/{reminder.pk}'):
            with self.subTest(path=path):
                with patch('billing.views.render_document_pdf', return_value=b'%PDF-doc'):
                    resp = self.client.get(f'{path}/send-pdf/')
                self.assertEqual(resp.status_code, 200)
                self.assertEqual(resp.content, b'%PDF-doc')

    def test_email_info_marks_which_attachments_render(self) -> None:
        self._supplement()
        self._file()

        data = self.client.get(f'/api/invoices/{self.invoice.pk}/email-info/').json()

        by_kind = {row['kind']: row for row in data['attachments']}
        self.assertTrue(by_kind['supplement']['renderable'])
        self.assertFalse(by_kind['file']['renderable'])
        self.assertEqual(by_kind['file']['mime_type'], 'application/pdf')
        self.assertTrue(by_kind['file']['file_url'])
