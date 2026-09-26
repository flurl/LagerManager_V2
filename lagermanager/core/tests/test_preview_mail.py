from django.core import mail
from django.core.mail import EmailMessage, EmailMultiAlternatives, get_connection
from django.test import SimpleTestCase, override_settings


@override_settings(
    EMAIL_BACKEND='core.mail.PreviewRedirectEmailBackend',
    PREVIEW_EMAIL_INNER_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    PREVIEW_BRANCH='feature/foo',
    PREVIEW_EMAIL_REDIRECT_TO='self@example.com',
)
class PreviewRedirectEmailBackendTest(SimpleTestCase):
    def _send(self, message: EmailMessage) -> int:
        return get_connection().send_messages([message])

    def test_all_recipients_replaced_by_redirect_address(self) -> None:
        """to/cc/bcc all collapse to the redirect address and nothing else.

        A preview runs on a copy of the production data, so a customer address
        must never receive the (fake) invoices and reminders sent from it.
        """
        sent = self._send(EmailMessage(
            subject='Rechnung', body='Hallo', from_email='noreply@example.com',
            to=['customer@example.com'], cc=['boss@example.com'], bcc=['audit@example.com'],
        ))

        self.assertEqual(sent, 1)
        self.assertEqual(len(mail.outbox), 1)
        out = mail.outbox[0]
        self.assertEqual(out.to, ['self@example.com'])
        self.assertEqual(out.cc, [])
        self.assertEqual(out.bcc, [])
        self.assertEqual(out.recipients(), ['self@example.com'])

    def test_subject_and_body_name_branch_and_original_recipients(self) -> None:
        """Subject is prefixed with the branch; body starts with the original recipients.

        Without that, the redirected mail gives no clue whom it was meant for.
        """
        self._send(EmailMessage(
            subject='Rechnung', body='Hallo', from_email='noreply@example.com',
            to=['customer@example.com'], cc=['boss@example.com'],
        ))

        out = mail.outbox[0]
        self.assertEqual(out.subject, '[VORSCHAU feature/foo] Rechnung')
        self.assertIn('customer@example.com', out.body)
        self.assertIn('boss@example.com', out.body)
        self.assertTrue(out.body.endswith('Hallo'))
        self.assertEqual(
            out.extra_headers['X-Original-Recipients'], 'customer@example.com, boss@example.com'
        )

    def test_caller_message_left_unchanged(self) -> None:
        """The redirect works on a copy; the caller's message object keeps its recipients."""
        message = EmailMessage(subject='S', body='B', to=['customer@example.com'])

        self._send(message)

        self.assertEqual(message.to, ['customer@example.com'])
        self.assertEqual(message.subject, 'S')
        self.assertEqual(message.extra_headers, {})

    def test_attachments_and_alternatives_preserved(self) -> None:
        """PDF attachments and HTML alternatives still reach the redirect address."""
        message = EmailMultiAlternatives(subject='S', body='B', to=['customer@example.com'])
        message.attach('rechnung.pdf', b'%PDF-1.4', 'application/pdf')
        message.attach_alternative('<p>B</p>', 'text/html')

        self._send(message)

        out = mail.outbox[0]
        self.assertEqual(out.attachments[0][0], 'rechnung.pdf')
        self.assertEqual(out.alternatives[0][1], 'text/html')
