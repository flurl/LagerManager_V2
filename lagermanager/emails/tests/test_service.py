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
