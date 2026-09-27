"""Tests for the document attachment endpoints."""
import shutil
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APITestCase

from billing.attachments import AttachmentHandler, register
from billing.attachments import registry as attachment_registry
from billing.models import DocumentAttachment, Invoice
from billing.tests.test_email_actions import (
    _create_user,
    _make_address,
    _make_invoice,
    _make_offer,
    _make_reminder,
)

MEDIA_ROOT = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class DocumentAttachmentApiTests(APITestCase):
    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def setUp(self) -> None:
        self.user = _create_user()
        self.client.force_authenticate(user=self.user)
        self.address = _make_address()
        self.invoice = _make_invoice(self.address)
        self.url = f'/api/invoices/{self.invoice.pk}/attachments/'

    # -- helpers -----------------------------------------------------------

    def _post_supplement(self, **overrides: Any) -> Any:
        payload: dict[str, Any] = {
            'kind': 'supplement',
            'title': 'Hinweis',
            'body': 'Ein erklärender Text.',
        }
        payload.update(overrides)
        return self.client.post(self.url, payload, format='json')

    def _post_file(self, name: str = 'lieferschein.pdf', **overrides: Any) -> Any:
        payload: dict[str, Any] = {
            'kind': 'file',
            'title': 'Lieferschein',
            'file': SimpleUploadedFile(name, b'%PDF-1.4 fake', content_type='application/pdf'),
        }
        payload.update(overrides)
        return self.client.post(self.url, payload, format='multipart')

    # -- create ------------------------------------------------------------

    def test_create_supplement_defaults_to_merge(self) -> None:
        response = self._post_supplement()

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['kind'], 'supplement')
        self.assertEqual(response.data['kind_label'], 'Ergänzung')
        self.assertEqual(response.data['delivery'], DocumentAttachment.Delivery.MERGE)
        self.assertEqual(response.data['effective_delivery'], DocumentAttachment.Delivery.MERGE)
        self.assertTrue(response.data['supports_merge'])
        self.assertEqual(response.data['position'], 1)

    def test_supplement_can_be_sent_separately(self) -> None:
        response = self._post_supplement(delivery=DocumentAttachment.Delivery.SEPARATE)

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['effective_delivery'],
                         DocumentAttachment.Delivery.SEPARATE)

    def test_positions_increment_per_document(self) -> None:
        self._post_supplement()
        second = self._post_supplement(title='Zweiter Hinweis')

        self.assertEqual(second.data['position'], 2)

    def test_supplement_without_title_and_body_is_rejected(self) -> None:
        response = self._post_supplement(title='', body='   ')

        self.assertEqual(response.status_code, 400)
        self.assertIn('body', response.data)

    def test_supplement_rejects_an_uploaded_file(self) -> None:
        response = self.client.post(
            self.url,
            {'kind': 'supplement', 'title': 'Mit Datei',
             'file': SimpleUploadedFile('x.pdf', b'%PDF-1.4', content_type='application/pdf')},
            format='multipart',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('file', response.data)

    def test_create_file_stores_metadata(self) -> None:
        response = self._post_file()

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['original_filename'], 'lieferschein.pdf')
        self.assertEqual(response.data['mime_type'], 'application/pdf')
        self.assertEqual(response.data['size_bytes'], len(b'%PDF-1.4 fake'))
        self.assertTrue(response.data['file_url'])
        self.assertFalse(response.data['supports_merge'])

    def test_file_is_never_merged_even_if_requested(self) -> None:
        response = self._post_file(delivery=DocumentAttachment.Delivery.MERGE)

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['delivery'], DocumentAttachment.Delivery.SEPARATE)
        self.assertEqual(response.data['effective_delivery'],
                         DocumentAttachment.Delivery.SEPARATE)

    def test_file_without_upload_is_rejected(self) -> None:
        response = self.client.post(
            self.url, {'kind': 'file', 'title': 'Ohne Datei'}, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertIn('file', response.data)

    def test_oversized_file_is_rejected(self) -> None:
        # Patching the limit beats uploading 25 MB in a test.
        with patch('billing.attachments.handlers.MAX_ATTACHMENT_BYTES', 8):
            response = self._post_file()

        self.assertEqual(response.status_code, 400)
        self.assertIn('file', response.data)

    def test_unknown_kind_is_rejected(self) -> None:
        response = self.client.post(
            self.url, {'kind': 'zeitreise', 'title': 'Hm'}, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertIn('kind', response.data)

    # -- read --------------------------------------------------------------

    def test_list_is_scoped_to_the_document_and_ordered(self) -> None:
        self._post_supplement(title='Erste')
        self._post_supplement(title='Zweite')
        other_invoice = _make_invoice(self.address)
        self.client.post(
            f'/api/invoices/{other_invoice.pk}/attachments/',
            {'kind': 'supplement', 'title': 'Fremde', 'body': 'x'}, format='json')

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual([row['title'] for row in response.data], ['Erste', 'Zweite'])

    def test_works_for_offers_and_reminders(self) -> None:
        offer = _make_offer(self.address)
        reminder = _make_reminder(self.invoice)

        for path in (f'/api/offers/{offer.pk}/attachments/',
                     f'/api/reminders/{reminder.pk}/attachments/'):
            with self.subTest(path=path):
                created = self.client.post(
                    path, {'kind': 'supplement', 'title': 'Hinweis', 'body': 'Text'},
                    format='json')
                self.assertEqual(created.status_code, 201, created.data)
                listed = self.client.get(path)
                self.assertEqual(len(listed.data), 1)

    def test_attachment_count_is_exposed_on_the_list_views(self) -> None:
        self._post_supplement()
        self._post_file()

        response = self.client.get('/api/invoices/')

        rows = response.data['results']
        row = next(r for r in rows if r['id'] == self.invoice.pk)
        self.assertEqual(row['attachment_count'], 2)

    def test_supplement_preview_renders_html(self) -> None:
        attachment_id = self._post_supplement().data['id']

        response = self.client.get(f'{self.url}{attachment_id}/preview/')

        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn('Hinweis', body)
        self.assertIn('RE2601-001', body)

    def test_file_has_no_preview(self) -> None:
        attachment_id = self._post_file().data['id']

        response = self.client.get(f'{self.url}{attachment_id}/preview/')

        self.assertEqual(response.status_code, 400)

    def test_kinds_endpoint_lists_the_registry(self) -> None:
        response = self.client.get('/api/document-attachment-kinds/')

        self.assertEqual(response.status_code, 200)
        by_kind = {row['kind']: row for row in response.data}
        self.assertEqual(set(by_kind), {'supplement', 'correction', 'payments', 'file'})
        self.assertTrue(by_kind['supplement']['supports_merge'])
        self.assertTrue(by_kind['file']['requires_file'])

    # -- update / delete ---------------------------------------------------

    def test_patch_updates_text_and_delivery(self) -> None:
        attachment_id = self._post_supplement().data['id']

        response = self.client.patch(
            f'{self.url}{attachment_id}/',
            {'title': 'Neuer Titel', 'delivery': DocumentAttachment.Delivery.SEPARATE},
            format='json')

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['title'], 'Neuer Titel')
        self.assertEqual(response.data['effective_delivery'],
                         DocumentAttachment.Delivery.SEPARATE)

    def test_kind_cannot_be_changed(self) -> None:
        attachment_id = self._post_supplement().data['id']

        response = self.client.patch(
            f'{self.url}{attachment_id}/', {'kind': 'file'}, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertIn('kind', response.data)

    def test_delete_removes_the_row_and_the_file(self) -> None:
        attachment_id = self._post_file().data['id']
        stored = Path(DocumentAttachment.objects.get(pk=attachment_id).file.path)
        self.assertTrue(stored.exists())

        response = self.client.delete(f'{self.url}{attachment_id}/')

        self.assertEqual(response.status_code, 204)
        self.assertFalse(DocumentAttachment.objects.filter(pk=attachment_id).exists())
        self.assertFalse(stored.exists())

    def test_deleting_the_document_takes_its_attachments_with_it(self) -> None:
        draft = _make_invoice(self.address, status='draft')
        self.client.post(
            f'/api/invoices/{draft.pk}/attachments/',
            {'kind': 'supplement', 'title': 'Hinweis', 'body': 'Text'}, format='json')
        self.assertEqual(DocumentAttachment.objects.count(), 1)

        draft.delete()

        self.assertEqual(DocumentAttachment.objects.count(), 0)

    def test_attachments_can_be_managed_on_a_paid_invoice(self) -> None:
        self.invoice.status = Invoice.Status.PAID
        self.invoice.save(update_fields=['status'])

        self.assertEqual(self._post_supplement().status_code, 201)

    # -- isolation / permissions -------------------------------------------

    def test_another_documents_attachment_is_not_reachable(self) -> None:
        attachment_id = self._post_supplement().data['id']
        other_invoice = _make_invoice(self.address)

        response = self.client.get(
            f'/api/invoices/{other_invoice.pk}/attachments/{attachment_id}/')

        self.assertEqual(response.status_code, 404)

    def test_attaching_to_a_foreign_object_via_payload_is_ignored(self) -> None:
        other_invoice = _make_invoice(self.address)

        response = self.client.post(
            self.url,
            {'kind': 'supplement', 'title': 'Hinweis', 'body': 'Text',
             'object_id': other_invoice.pk,
             'content_type': ContentType.objects.get_for_model(Invoice).pk},
            format='json')

        self.assertEqual(response.status_code, 201)
        attachment = DocumentAttachment.objects.get(pk=response.data['id'])
        self.assertEqual(attachment.object_id, self.invoice.pk)

    def test_unauthenticated_access_is_refused(self) -> None:
        self.client.force_authenticate(user=None)

        self.assertEqual(self.client.get(self.url).status_code, 401)

    def test_read_only_user_may_look_but_not_write(self) -> None:
        reader = User.objects.create_user('reader', 'reader@example.com', 'password')
        reader.user_permissions.add(
            Permission.objects.get(codename='view_invoice'))
        self.client.force_authenticate(user=reader)

        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertEqual(self._post_supplement().status_code, 403)

    def test_user_who_may_change_the_invoice_may_manage_attachments(self) -> None:
        editor = User.objects.create_user('editor', 'editor@example.com', 'password')
        editor.user_permissions.add(
            Permission.objects.get(codename='view_invoice'),
            Permission.objects.get(codename='change_invoice'),
        )
        self.client.force_authenticate(user=editor)

        response = self._post_supplement()

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['created_by_name'], 'editor')


class _SeparateByDefaultHandler(AttachmentHandler):
    """A kind that may be merged but normally travels as its own file.

    Neither shipping kind has this combination, which is exactly why it is the
    case that shows whether the handler's default is honoured or the model's.
    """

    kind = 'test-separate-by-default'
    label = 'Testart'
    delivery_modes = (DocumentAttachment.Delivery.MERGE, DocumentAttachment.Delivery.SEPARATE)
    default_delivery = DocumentAttachment.Delivery.SEPARATE


class HandlerDefaultDeliveryTests(APITestCase):
    """The handler, not the model field, decides a new attachment's delivery."""

    def setUp(self) -> None:
        # Registered per test and removed again, so the global registry that
        # every other test sees stays untouched.
        register(_SeparateByDefaultHandler)
        self.addCleanup(
            attachment_registry._HANDLERS.pop, _SeparateByDefaultHandler.kind, None)

        self.client.force_authenticate(user=_create_user())
        self.invoice = _make_invoice(_make_address())
        self.url = f'/api/invoices/{self.invoice.pk}/attachments/'

    def test_omitted_delivery_falls_back_to_the_handlers_default(self) -> None:
        response = self.client.post(
            self.url, {'kind': _SeparateByDefaultHandler.kind, 'title': 'Bericht'},
            format='json')

        self.assertEqual(response.status_code, 201, response.data)
        # The model field defaults to MERGE; the handler says SEPARATE.
        self.assertEqual(response.data['delivery'], DocumentAttachment.Delivery.SEPARATE)

    def test_an_explicit_delivery_still_wins(self) -> None:
        response = self.client.post(
            self.url,
            {'kind': _SeparateByDefaultHandler.kind, 'title': 'Bericht',
             'delivery': DocumentAttachment.Delivery.MERGE},
            format='json')

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['delivery'], DocumentAttachment.Delivery.MERGE)

    def test_supplement_still_defaults_to_merge(self) -> None:
        response = self.client.post(
            self.url, {'kind': 'supplement', 'title': 'Hinweis', 'body': 'Text'},
            format='json')

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['delivery'], DocumentAttachment.Delivery.MERGE)

    def test_an_update_does_not_reset_the_delivery_to_the_default(self) -> None:
        created = self.client.post(
            self.url,
            {'kind': 'supplement', 'title': 'Hinweis', 'body': 'Text',
             'delivery': DocumentAttachment.Delivery.SEPARATE},
            format='json')

        response = self.client.patch(
            f'{self.url}{created.data["id"]}/', {'title': 'Neu'}, format='json')

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['delivery'], DocumentAttachment.Delivery.SEPARATE)
