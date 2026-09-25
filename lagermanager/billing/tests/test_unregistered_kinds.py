"""Attachments whose kind is not registered are never deleted automatically.

A kind can go missing from the registry through a mistake — a renamed kind, a
removed or broken handler.  Such a row's rules cannot be checked, and it may be
a protected kind (a Berichtigungsnote), so every deletion path fails closed and
the row is dealt with deliberately, case by case.
"""
from typing import Any

from django.contrib.admin.sites import site
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Model, ProtectedError
from django.test import RequestFactory, TestCase
from rest_framework.test import APITestCase

from billing.admin import DocumentAttachmentAdmin
from billing.models import DocumentAttachment, Invoice
from billing.tests.test_email_actions import _create_user, _make_address, _make_invoice

UNREGISTERED = 'no-longer-registered'


def _orphan(doc: Model, **kwargs: Any) -> DocumentAttachment:
    """An attachment of a kind the registry does not know (created directly)."""
    defaults: dict[str, Any] = {'kind': UNREGISTERED, 'position': 1, 'title': 'Altlast'}
    defaults.update(kwargs)
    return DocumentAttachment.objects.create(
        content_type=ContentType.objects.get_for_model(doc),
        object_id=doc.pk,
        **defaults,
    )


class UnregisteredKindApiTests(APITestCase):
    def setUp(self) -> None:
        self.client.force_authenticate(user=_create_user())
        self.invoice = _make_invoice(_make_address(), status='issued')
        self.url = f'/api/invoices/{self.invoice.pk}/attachments/'
        self.orphan = _orphan(self.invoice)

    def test_reported_as_not_deletable(self) -> None:
        """The list reports deletable=False for an unknown kind, so the dialog
        shows the lock instead of the bin."""
        rows = self.client.get(self.url).data

        self.assertFalse(rows[0]['deletable'])

    def test_delete_through_the_api_is_refused(self) -> None:
        """DELETE on an unknown-kind row is refused with 400 and the row survives.

        Without a handler its rules can't be checked; it may be a protected kind
        whose handler failed to register, so refusing is the safe answer.
        """
        response = self.client.delete(f'{self.url}{self.orphan.pk}/')

        self.assertEqual(response.status_code, 400)
        self.assertIn(UNREGISTERED, response.data['detail'])
        self.assertTrue(DocumentAttachment.objects.filter(pk=self.orphan.pk).exists())


class UnregisteredKindModelTests(TestCase):
    """Deletes run in their own atomic block — see CorrectionNoteModelProtectionTests."""

    def setUp(self) -> None:
        self.invoice = _make_invoice(_make_address(), status='issued')
        self.orphan = _orphan(self.invoice)

    def test_instance_delete_is_refused(self) -> None:
        """Deleting the row directly (shell, scripts) raises ProtectedError; the
        row survives — the pre_delete guard covers every path, not just the API."""
        with self.assertRaises(ProtectedError), transaction.atomic():
            self.orphan.delete()

        self.assertTrue(DocumentAttachment.objects.filter(pk=self.orphan.pk).exists())

    def test_deleting_its_document_is_refused_too(self) -> None:
        """Deleting even a draft invoice that carries such a row raises
        ProtectedError.

        Deliberate consequence of failing closed: the cascade would otherwise
        remove the row silently.  The case has to be resolved by hand first.
        """
        draft = _make_invoice(_make_address(), status='draft')
        _orphan(draft)

        with self.assertRaises(ProtectedError), transaction.atomic():
            Invoice.objects.filter(pk=draft.pk).delete()

        self.assertTrue(Invoice.objects.filter(pk=draft.pk).exists())


class UnregisteredKindAdminTests(TestCase):
    def test_admin_offers_no_delete(self) -> None:
        """The admin hides the delete button for an unknown-kind row, even for a
        superuser, instead of offering a delete the signal would refuse."""
        orphan = _orphan(_make_invoice(_make_address(), status='issued'))
        request = RequestFactory().get('/')
        request.user = _create_user()  # a superuser: would pass any permission check

        model_admin = DocumentAttachmentAdmin(DocumentAttachment, site)

        self.assertFalse(model_admin.has_delete_permission(request, orphan))
