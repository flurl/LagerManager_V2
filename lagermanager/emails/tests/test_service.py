"""Tests for the emails.services.email send_document_email service."""
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase, override_settings

from emails.models import EmailAttachment, EmailLog
from emails.services.email import send_document_email


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class SendDocumentEmailTests(TestCase):

    def setUp(self) -> None:
        self.user = User.objects.create_user('sender', 'sender@example.com', 'password')

    def test_sends_email_and_creates_sent_log(self) -> None:
        log = send_document_email(
            subject='Test subject',
            body='Hello world',
            recipient='recipient@example.com',
            sent_by=self.user,
        )

        self.assertEqual(log.status, EmailLog.Status.SENT)
        self.assertEqual(log.recipient, 'recipient@example.com')
        self.assertEqual(log.subject, 'Test subject')
        self.assertEqual(log.sent_by, self.user)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['recipient@example.com'])
        self.assertEqual(mail.outbox[0].subject, 'Test subject')

    def test_attaches_pdf_and_creates_attachment_row(self) -> None:
        pdf_bytes = b'%PDF-1.4 fake'
        log = send_document_email(
            subject='With attachment',
            body='',
            recipient='x@example.com',
            attachments=[('test.pdf', pdf_bytes, 'application/pdf')],
        )

        self.assertEqual(log.status, EmailLog.Status.SENT)
        self.assertEqual(log.attachments.count(), 1)
        att: EmailAttachment = log.attachments.first()
        self.assertEqual(att.original_filename, 'test.pdf')
        self.assertEqual(att.mime_type, 'application/pdf')
        # File should be stored on disk
        self.assertTrue(att.file.name)
        att.file.open('rb')
        self.assertEqual(att.file.read(), pdf_bytes)
        att.file.close()

        # Mail also has the attachment
        self.assertEqual(len(mail.outbox[0].attachments), 1)
        fname, fdata, fmime = mail.outbox[0].attachments[0]
        self.assertEqual(fname, 'test.pdf')
        self.assertEqual(fdata, pdf_bytes)

    def test_links_related_object_via_generic_fk(self) -> None:
        from django.contrib.contenttypes.models import ContentType
        # Use User as a stand-in for any model
        related = User.objects.create_user('target', 'target@example.com', 'pw')
        log = send_document_email(
            subject='Linked',
            body='',
            recipient='x@example.com',
            related_object=related,
        )
        ct = ContentType.objects.get_for_model(related)
        self.assertEqual(log.content_type, ct)
        self.assertEqual(log.object_id, str(related.pk))

    def test_creates_failed_log_and_reraises_on_send_error(self) -> None:
        with patch('django.core.mail.EmailMessage.send', side_effect=ConnectionError('no route')):
            with self.assertRaises(ConnectionError):
                send_document_email(
                    subject='Failing',
                    body='',
                    recipient='x@example.com',
                )

        log = EmailLog.objects.get(subject='Failing')
        self.assertEqual(log.status, EmailLog.Status.FAILED)
        self.assertIn('no route', log.error_message)
        # No attachment rows created on failure
        self.assertEqual(log.attachments.count(), 0)

    def test_cc_is_passed_through(self) -> None:
        send_document_email(
            subject='CC test',
            body='',
            recipient='a@example.com',
            cc='b@example.com',
        )
        self.assertEqual(mail.outbox[0].cc, ['b@example.com'])
        log = EmailLog.objects.get(subject='CC test')
        self.assertEqual(log.cc, 'b@example.com')


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    EMAIL_ARCHIVE_BCC='faktura+Sent@example.com',
)
class ArchiveBccTests(TestCase):
    """Every billing mail is BCC'd to EMAIL_ARCHIVE_BCC so a copy lands in the Sent folder."""

    def _send(self) -> None:
        send_document_email(subject='Rechnung', body='', recipient='customer@example.com')

    def test_archive_address_is_bcc_recipient(self) -> None:
        """The archive address is an envelope recipient of the sent message."""
        self._send()

        self.assertEqual(mail.outbox[0].bcc, ['faktura+Sent@example.com'])
        self.assertIn('faktura+Sent@example.com', mail.outbox[0].recipients())

    def test_archive_address_is_not_in_headers(self) -> None:
        """The archive address never appears in the message headers.

        As a visible To/Cc the customer would see it, and a "reply all" would be
        filed straight into the Sent folder where nobody reads it.
        """
        self._send()

        raw: str = mail.outbox[0].message().as_string()
        self.assertNotIn('faktura+Sent@example.com', raw)

    @override_settings(EMAIL_ARCHIVE_BCC='')
    def test_empty_setting_disables_archive_bcc(self) -> None:
        """An empty EMAIL_ARCHIVE_BCC sends the mail without any BCC."""
        self._send()

        self.assertEqual(mail.outbox[0].bcc, [])

    @override_settings(
        EMAIL_BACKEND='core.mail.PreviewRedirectEmailBackend',
        PREVIEW_EMAIL_INNER_BACKEND='django.core.mail.backends.locmem.EmailBackend',
        PREVIEW_BRANCH='feature/foo',
        PREVIEW_EMAIL_REDIRECT_TO='self@example.com',
    )
    def test_preview_drops_archive_bcc(self) -> None:
        """On a preview the mail goes only to the redirect address, not to the archive.

        Preview test mail must not clutter the production Sent folder.
        """
        self._send()

        self.assertEqual(mail.outbox[0].recipients(), ['self@example.com'])
