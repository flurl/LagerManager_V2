"""Berichtigungsnoten — correction notes that are mandatory, undeletable and immutable.

A Berichtigungsnote corrects an issued document.  Once one exists it has to go
out with every email of that document — always as extra pages of the document
PDF, never as a file of its own — it can never be deleted, and its text cannot
be changed: a further correction is a further Berichtigungsnote.
"""
import datetime
from typing import Any
from unittest.mock import patch

from django.contrib.contenttypes.models import ContentType
from django.core import mail
from django.db import transaction
from django.db.models import Model, ProtectedError
from django.test import TestCase, override_settings
from emails.models import EmailLog
from rest_framework.test import APITestCase

from billing.attachments import get_handler
from billing.models import DocumentAttachment, Invoice, Reminder
from billing.tests.test_email_actions import (
    _create_user,
    _make_address,
    _make_invoice,
    _make_offer,
    _make_reminder,
)

CORRECTION = 'correction'


def _correction(doc: Model, **kwargs: Any) -> DocumentAttachment:
    """Create a note directly, bypassing the API's issued-document check."""
    defaults: dict[str, Any] = {
        'kind': CORRECTION,
        'position': 1,
        'title': 'Korrektur Leistungszeitraum',
        'body': 'Der Leistungszeitraum lautet richtig 1.–31. Jänner.',
        'delivery': DocumentAttachment.Delivery.MERGE,
    }
    defaults.update(kwargs)
    return DocumentAttachment.objects.create(
        content_type=ContentType.objects.get_for_model(doc),
        object_id=doc.pk,
        **defaults,
    )


class CorrectionKindTests(TestCase):
    def test_registered_with_its_rules(self) -> None:
        """The 'correction' kind is registered with all of its rules.

        Expects merge as its only delivery mode, mandatory, neither deletable nor
        editable, issued documents only.  These flags are the kind's entire
        definition — every other layer just enforces them — so they are pinned here.
        """
        handler = get_handler(CORRECTION)

        self.assertEqual(handler.label, 'Berichtigungsnote')
        self.assertTrue(handler.supports_merge)
        self.assertTrue(handler.renderable)
        self.assertEqual(handler.default_delivery, DocumentAttachment.Delivery.MERGE)
        self.assertEqual(handler.delivery_modes, (DocumentAttachment.Delivery.MERGE,))
        self.assertFalse(handler.has_delivery_choice)
        self.assertTrue(handler.mandatory)
        self.assertFalse(handler.deletable)
        self.assertFalse(handler.editable)
        self.assertTrue(handler.requires_issued_document)

    def test_the_other_kinds_keep_their_permissive_defaults(self) -> None:
        """Ergänzung and Datei keep the base-class defaults for the new rule flags:
        not mandatory, deletable, editable, allowed on drafts.
        """
        for kind in ('supplement', 'file'):
            with self.subTest(kind=kind):
                handler = get_handler(kind)
                self.assertFalse(handler.mandatory)
                self.assertTrue(handler.deletable)
                self.assertTrue(handler.editable)
                self.assertFalse(handler.requires_issued_document)

    def test_rules_are_exposed_to_the_frontend(self) -> None:
        """The rules reach the kinds endpoint's payload (KindInfo) unchanged.

        The dialog decides what to show — lock icon, disabled toggle, no delivery
        switch — purely from these fields.
        """
        info = get_handler(CORRECTION).info().as_dict()

        self.assertTrue(info['mandatory'])
        self.assertFalse(info['deletable'])
        self.assertFalse(info['editable'])
        self.assertTrue(info['requires_issued_document'])
        self.assertEqual(list(info['delivery_modes']), [DocumentAttachment.Delivery.MERGE])


class CorrectionNoteApiTests(APITestCase):
    def setUp(self) -> None:
        self.client.force_authenticate(user=_create_user())
        self.address = _make_address()
        self.invoice = _make_invoice(self.address, status='issued')
        self.url = f'/api/invoices/{self.invoice.pk}/attachments/'

    def _post(self, url: str | None = None, **overrides: Any) -> Any:
        payload: dict[str, Any] = {
            'kind': CORRECTION, 'title': 'Korrektur', 'body': 'Richtig ist …',
        }
        payload.update(overrides)
        return self.client.post(url or self.url, payload, format='json')

    # -- creation ------------------------------------------------------------

    def test_create_on_an_issued_invoice(self) -> None:
        """Creating a note on an issued invoice succeeds (201), merged, and the
        response carries the rule flags the dialog renders from.
        """
        response = self._post()

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['kind_label'], 'Berichtigungsnote')
        self.assertEqual(response.data['delivery'], DocumentAttachment.Delivery.MERGE)
        self.assertTrue(response.data['mandatory'])
        self.assertFalse(response.data['deletable'])
        self.assertFalse(response.data['editable'])

    def test_cannot_be_created_on_a_draft(self) -> None:
        """A note on a draft is refused (400) and nothing is stored.

        Drafts can be deleted, which would cascade away the note and break its
        "never deleted" guarantee — and a draft is simply edited instead.
        """
        draft = _make_invoice(self.address, status='draft')

        response = self._post(url=f'/api/invoices/{draft.pk}/attachments/')

        self.assertEqual(response.status_code, 400)
        self.assertFalse(DocumentAttachment.objects.filter(kind=CORRECTION).exists())

    def test_supplements_are_still_allowed_on_drafts(self) -> None:
        """The issued-only rule is per kind: an Ergänzung on a draft still gets 201."""
        draft = _make_invoice(self.address, status='draft')

        response = self._post(url=f'/api/invoices/{draft.pk}/attachments/',
                              kind='supplement')

        self.assertEqual(response.status_code, 201, response.data)

    def test_works_on_offers_and_reminders(self) -> None:
        """Notes can be created on issued offers and reminders too (201 each), not
        only on invoices.
        """
        offer = _make_offer(self.address)  # issued by default
        reminder = _make_reminder(self.invoice)  # issued

        for url in (f'/api/offers/{offer.pk}/attachments/',
                    f'/api/reminders/{reminder.pk}/attachments/'):
            with self.subTest(url=url):
                self.assertEqual(self._post(url=url).status_code, 201)

    def test_several_notes_per_document(self) -> None:
        """A document carries any number of notes: a correction of a correction is a
        further note, so a second one is stored next to the first.
        """
        self._post(title='Erste')
        self._post(title='Zweite')

        self.assertEqual(
            DocumentAttachment.objects.filter(kind=CORRECTION).count(), 2)

    # -- immutability --------------------------------------------------------

    def test_cannot_be_deleted_through_the_api(self) -> None:
        """DELETE on a note is refused with 400 and the row survives."""
        note_id = self._post().data['id']

        response = self.client.delete(f'{self.url}{note_id}/')

        self.assertEqual(response.status_code, 400)
        self.assertTrue(DocumentAttachment.objects.filter(pk=note_id).exists())

    def test_text_cannot_be_changed(self) -> None:
        """Changing title or body is refused (400 each) and the stored text is
        untouched — a correction is corrected by a new note, not by editing.
        """
        note_id = self._post(title='Original', body='Originaltext').data['id']

        for change in ({'title': 'Geändert'}, {'body': 'Geänderter Text'}):
            with self.subTest(change=change):
                response = self.client.patch(
                    f'{self.url}{note_id}/', change, format='json')
                self.assertEqual(response.status_code, 400)

        note = DocumentAttachment.objects.get(pk=note_id)
        self.assertEqual((note.title, note.body), ('Original', 'Originaltext'))

    def test_created_merged_even_if_separate_is_requested(self) -> None:
        """A note posted with delivery=separate is stored as merge (201).

        Merge is its only mode.  A mode the kind doesn't offer is replaced by its
        default rather than refused — the same rule that forces uploads to separate.
        """
        response = self._post(delivery=DocumentAttachment.Delivery.SEPARATE)

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['delivery'], DocumentAttachment.Delivery.MERGE)
        self.assertEqual(list(response.data['delivery_modes']),
                         [DocumentAttachment.Delivery.MERGE])

    def test_delivery_cannot_be_switched_to_separate(self) -> None:
        """PATCHing delivery to separate leaves the note merged (200, still merge),
        and the database confirms nothing changed — the kind's only mode wins,
        just as for a Datei asked to merge.
        """
        note_id = self._post().data['id']

        response = self.client.patch(
            f'{self.url}{note_id}/',
            {'delivery': DocumentAttachment.Delivery.SEPARATE}, format='json')

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['delivery'], DocumentAttachment.Delivery.MERGE)
        self.assertEqual(
            DocumentAttachment.objects.get(pk=note_id).delivery,
            DocumentAttachment.Delivery.MERGE)

    def test_resending_unchanged_text_is_not_a_change(self) -> None:
        """Resending the unchanged title together with another field is accepted (200).

        Only a real change to the text counts, so a client that sends the whole
        object back is not refused for fields it didn't alter.
        """
        note_id = self._post(title='Original').data['id']

        response = self.client.patch(
            f'{self.url}{note_id}/',
            {'title': 'Original', 'delivery': DocumentAttachment.Delivery.SEPARATE},
            format='json')

        self.assertEqual(response.status_code, 200, response.data)

    def test_supplements_stay_editable_and_deletable(self) -> None:
        """The immutability rules are per kind: an Ergänzung can still be edited (200)
        and deleted (204).
        """
        supplement_id = self._post(kind='supplement').data['id']

        edited = self.client.patch(
            f'{self.url}{supplement_id}/', {'title': 'Neu'}, format='json')
        deleted = self.client.delete(f'{self.url}{supplement_id}/')

        self.assertEqual(edited.status_code, 200)
        self.assertEqual(deleted.status_code, 204)


class CorrectionNoteModelProtectionTests(TestCase):
    """No code path — admin, shell, cascade — may delete a Berichtigungsnote.

    Each delete runs in its own atomic block: Django sends pre_delete inside
    ``atomic(savepoint=False)``, so without a savepoint the refused delete
    would poison the test's transaction and the follow-up query would fail.
    """

    def setUp(self) -> None:
        self.invoice = _make_invoice(_make_address(), status='issued')
        self.note = _correction(self.invoice)

    def test_instance_delete_is_refused(self) -> None:
        """instance.delete() raises ProtectedError and the row survives."""
        with self.assertRaises(ProtectedError), transaction.atomic():
            self.note.delete()

        self.assertTrue(DocumentAttachment.objects.filter(pk=self.note.pk).exists())

    def test_queryset_delete_is_refused(self) -> None:
        """A queryset delete — the path the admin's bulk "delete selected" takes —
        raises ProtectedError too, and the row survives.
        """
        with self.assertRaises(ProtectedError), transaction.atomic():
            DocumentAttachment.objects.filter(pk=self.note.pk).delete()

        self.assertTrue(DocumentAttachment.objects.filter(pk=self.note.pk).exists())

    def test_deleting_the_document_is_refused_too(self) -> None:
        """Deleting the invoice raises ProtectedError: the cascade reaches the note's
        pre_delete guard, so a note cannot be deleted indirectly via its document.
        """
        with self.assertRaises(ProtectedError), transaction.atomic():
            Invoice.objects.filter(pk=self.invoice.pk).delete()

        self.assertTrue(Invoice.objects.filter(pk=self.invoice.pk).exists())


class ReminderDeletionTests(APITestCase):
    """Issued reminders were deletable through the API; the handbook says not."""

    def setUp(self) -> None:
        self.client.force_authenticate(user=_create_user())
        self.invoice = _make_invoice(_make_address(), status='issued')

    def test_an_issued_reminder_cannot_be_deleted(self) -> None:
        """DELETE on an issued reminder is refused with 400; the reminder survives.

        Regression: the API used to allow it, leaving the reminder's fee on the
        customer ledger (whose FK is SET_NULL) with no reminder behind it.
        """
        reminder = _make_reminder(self.invoice)

        response = self.client.delete(f'/api/reminders/{reminder.pk}/')

        self.assertEqual(response.status_code, 400)
        self.assertTrue(Reminder.objects.filter(pk=reminder.pk).exists())

    def test_a_draft_reminder_still_can(self) -> None:
        """A draft reminder can still be deleted (204) — the guard only protects issued
        ones, the same rule offers and invoices already had.
        """
        reminder = Reminder.objects.create(
            invoice=self.invoice, level=1, status=Reminder.Status.DRAFT,
            reminder_date=datetime.date(2026, 2, 1),
            due_date=datetime.date(2026, 2, 14),
        )

        response = self.client.delete(f'/api/reminders/{reminder.pk}/')

        self.assertEqual(response.status_code, 204)

    def test_a_reminder_carrying_a_correction_is_refused_cleanly(self) -> None:
        """Deleting an issued reminder that has a note gives a clean 400.

        The reminder guard answers before any delete runs.  Without it the cascade
        would hit the note's pre_delete guard and surface as a 500.
        """
        reminder = _make_reminder(self.invoice)
        note = _correction(reminder)

        response = self.client.delete(f'/api/reminders/{reminder.pk}/')

        self.assertEqual(response.status_code, 400)
        self.assertTrue(DocumentAttachment.objects.filter(pk=note.pk).exists())


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class CorrectionNoteSendingTests(APITestCase):
    def setUp(self) -> None:
        self.client.force_authenticate(user=_create_user())
        self.invoice = _make_invoice(_make_address(), status='issued')
        self.base = f'/api/invoices/{self.invoice.pk}'
        mail.outbox.clear()

    def _send(self, attachment_ids: list[int]) -> Any:
        return self.client.post(
            f'{self.base}/send-email/',
            {'recipient': 'kunde@example.com', 'subject': 'Rechnung', 'body': '',
             'attachment_ids': attachment_ids},
            format='json')

    def test_email_info_reports_it_as_mandatory(self) -> None:
        """email-info lists the note — and only the note, not the Ergänzung — in
        mandatory_attachment_ids, which the send dialog shows ticked and locked.
        """
        note = _correction(self.invoice)
        _correction(self.invoice, kind='supplement', title='Nur Ergänzung')

        data = self.client.get(f'{self.base}/email-info/').json()

        self.assertEqual(data['mandatory_attachment_ids'], [note.pk])

    def test_a_merged_note_goes_out_even_when_not_selected(self) -> None:
        """Sending with an empty selection still merges the note into the document.

        Expects one merge of document + note and a single attached PDF: mandatory
        notes are added server-side, whatever the client selected.
        """
        _correction(self.invoice, delivery=DocumentAttachment.Delivery.MERGE)

        with patch('billing.views.render_document_pdf', return_value=b'%PDF-doc'), \
             patch('billing.attachments.handlers.render_html_to_pdf',
                   return_value=b'%PDF-note'), \
             patch('billing.attachments.send.merge_pdfs',
                   return_value=b'%PDF-merged') as merge:
            response = self._send([])

        self.assertEqual(response.status_code, 200, response.data)
        merge.assert_called_once_with([b'%PDF-doc', b'%PDF-note'])
        self.assertEqual(len(mail.outbox[0].attachments), 1)

    def test_a_row_stored_as_separate_is_still_merged(self) -> None:
        """A note row stored as separate (written around the API) is still merged.

        Defence in depth: resolve_delivery does not trust a mode the kind doesn't
        offer, so a note never goes out as a file of its own.
        """
        _correction(self.invoice, delivery=DocumentAttachment.Delivery.SEPARATE)

        with patch('billing.views.render_document_pdf', return_value=b'%PDF-doc'), \
             patch('billing.attachments.handlers.render_html_to_pdf',
                   return_value=b'%PDF-note'), \
             patch('billing.attachments.send.merge_pdfs',
                   return_value=b'%PDF-merged') as merge:
            self._send([])

        merge.assert_called_once_with([b'%PDF-doc', b'%PDF-note'])
        self.assertEqual(len(mail.outbox[0].attachments), 1)

    def test_every_note_is_merged_into_the_one_document_pdf(self) -> None:
        """Two notes both become pages of the one document PDF: one merge of three
        parts, one attached file, one EmailAttachment recorded in the log.
        """
        for number in (1, 2):
            _correction(self.invoice, position=number, title=f'Korrektur {number}')

        with patch('billing.views.render_document_pdf', return_value=b'%PDF-doc'), \
             patch('billing.attachments.handlers.render_html_to_pdf',
                   return_value=b'%PDF-note'), \
             patch('billing.attachments.send.merge_pdfs',
                   return_value=b'%PDF-merged') as merge:
            self._send([])

        merge.assert_called_once_with([b'%PDF-doc', b'%PDF-note', b'%PDF-note'])
        self.assertEqual(len(mail.outbox[0].attachments), 1)
        self.assertEqual(EmailLog.objects.get().attachments.count(), 1)

    def test_the_send_preview_includes_it_without_selection(self) -> None:
        """send-pdf with no selection returns the merged PDF, note included — the
        preview shows what is actually sent, mandatory attachments and all.
        """
        _correction(self.invoice, delivery=DocumentAttachment.Delivery.MERGE)

        with patch('billing.views.render_document_pdf', return_value=b'%PDF-doc'), \
             patch('billing.attachments.handlers.render_html_to_pdf',
                   return_value=b'%PDF-note'), \
             patch('billing.attachments.send.merge_pdfs',
                   return_value=b'%PDF-merged'):
            response = self.client.get(f'{self.base}/send-pdf/')

        self.assertEqual(response.content, b'%PDF-merged')


class CorrectionNoteRenderTests(TestCase):
    def setUp(self) -> None:
        self.invoice = _make_invoice(_make_address(), status='issued')

    def test_page_names_itself_and_references_the_document(self) -> None:
        """The rendered page says "Berichtigungsnote" and shows the note text plus the
        corrected invoice's number and date — a correction has to identify what it
        corrects unambiguously.
        """
        note = _correction(self.invoice)

        html = get_handler(CORRECTION).render_html(note)

        self.assertIn('Berichtigungsnote', html)
        self.assertIn('RE2601-001', html)
        self.assertIn('15.01.2026', html)  # the corrected invoice's date
        self.assertIn('Der Leistungszeitraum lautet richtig', html)

    def test_notes_are_numbered_per_document(self) -> None:
        """Notes are numbered per document, counting only notes.

        The third attachment is the second note, so it shows "Berichtigung Nr. 2"
        and its filename ends in _2 — the Ergänzung in between doesn't count.
        """
        _correction(self.invoice, position=1)
        _correction(self.invoice, position=2, kind='supplement', title='Dazwischen')
        second = _correction(self.invoice, position=3, title='Zweite Korrektur')

        handler = get_handler(CORRECTION)

        self.assertInHTML(
            '<tr><td>Berichtigung Nr.</td><td>2</td></tr>', handler.render_html(second))
        self.assertTrue(handler.email_filename(second).endswith('_2.pdf'))
