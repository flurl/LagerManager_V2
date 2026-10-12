"""Rendering of attachments in the document layout."""
from django.contrib.contenttypes.models import ContentType
from django.db.models import Model
from django.test import TestCase

from billing.attachments.handlers import SUPPLEMENT_TEMPLATE
from billing.models import DocumentAttachment
from billing.services.render import (
    document_address,
    recipient_block,
    render_attachment_html,
)
from billing.tests.test_email_actions import (
    _make_address,
    _make_invoice,
    _make_reminder,
)


def _supplement(doc: Model, **kwargs: object) -> DocumentAttachment:
    defaults: dict[str, object] = {
        'kind': 'supplement',
        'position': 1,
        'title': 'Hinweis zur Lieferung',
        'body': 'Die Lieferung erfolgte in zwei Teillieferungen.',
    }
    defaults.update(kwargs)
    return DocumentAttachment.objects.create(
        content_type=ContentType.objects.get_for_model(doc),
        object_id=doc.pk,
        **defaults,
    )


class RecipientBlockTests(TestCase):
    def setUp(self) -> None:
        self.address = _make_address()
        self.invoice = _make_invoice(self.address)

    def test_uses_the_snapshot_when_the_document_has_one(self) -> None:
        self.invoice.recipient_text = 'Snapshot GmbH\nHauptstraße 1'
        self.invoice.save(update_fields=['recipient_text'])

        self.assertEqual(recipient_block(self.invoice), 'Snapshot GmbH\nHauptstraße 1')

    def test_falls_back_to_the_live_address(self) -> None:
        self.assertIn('Mustermann', recipient_block(self.invoice))

    def test_reminder_uses_the_dunned_invoices_address(self) -> None:
        reminder = _make_reminder(self.invoice)
        address, customer = document_address(reminder)

        self.assertEqual(address, self.address)
        self.assertEqual(customer, self.address.customer)
        # A Reminder has neither recipient_text nor address of its own, so this
        # is the assertion that keeps its supplement pages addressed.
        self.assertIn('Mustermann', recipient_block(reminder))


class SupplementRenderTests(TestCase):
    def setUp(self) -> None:
        self.address = _make_address()
        self.invoice = _make_invoice(self.address)
        self.invoice.notes = 'Anmerkung nur für die Rechnung'
        self.invoice.save(update_fields=['notes'])

    def test_renders_title_body_and_document_reference(self) -> None:
        html = render_attachment_html(_supplement(self.invoice), SUPPLEMENT_TEMPLATE)

        self.assertIn('Ergänzung', html)
        self.assertIn('Hinweis zur Lieferung', html)
        self.assertIn('Die Lieferung erfolgte in zwei Teillieferungen.', html)
        self.assertIn('Rechnung', html)
        self.assertIn('RE2601-001', html)
        self.assertIn('Mustermann', html)

    def test_does_not_repeat_the_documents_notes(self) -> None:
        html = render_attachment_html(_supplement(self.invoice), SUPPLEMENT_TEMPLATE)

        self.assertNotIn('Anmerkung nur für die Rechnung', html)

    def test_document_itself_still_shows_its_notes(self) -> None:
        from billing.services.render import render_document_html

        self.assertIn('Anmerkung nur für die Rechnung',
                      render_document_html(self.invoice))

    def test_renders_for_a_reminder(self) -> None:
        reminder = _make_reminder(self.invoice)

        html = render_attachment_html(_supplement(reminder), SUPPLEMENT_TEMPLATE)

        self.assertIn('Mahnung', html)
        self.assertIn('MA2601-001', html)
        self.assertIn('Mustermann', html)

    def test_storno_invoice_is_labelled_as_such(self) -> None:
        storno = _make_invoice(self.address)
        storno.reverses = self.invoice
        storno.save(update_fields=['reverses'])

        html = render_attachment_html(_supplement(storno), SUPPLEMENT_TEMPLATE)

        self.assertIn('Stornorechnung', html)
