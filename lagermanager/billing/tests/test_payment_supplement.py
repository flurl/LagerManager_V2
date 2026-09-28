"""The Zahlungsübersicht — the system-maintained payment list of an invoice.

Once an invoice has payments or an issued reminder it carries exactly one
attachment of kind ``payments``, kept in step by services/payment_supplement.py.
It goes out with every email and download of the invoice, always as the pages
right after the invoice itself, and users can neither create, edit nor delete
it.  invoice.html no longer prints the payments itself.
"""
import datetime
import importlib
from decimal import Decimal
from typing import Any
from unittest.mock import patch

from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Model, ProtectedError
from django.test import TestCase
from rest_framework.test import APITestCase

from billing.attachments import get_handler
from billing.models import DocumentAttachment, Invoice, Payment, Reminder
from billing.services import ledger
from billing.services.payment_supplement import PAYMENTS_KIND, sync_payment_supplement
from billing.tests.test_email_actions import _create_user, _make_address, _make_invoice


def _supplements(invoice: Invoice) -> list[DocumentAttachment]:
    return list(DocumentAttachment.objects.filter(
        content_type=ContentType.objects.get_for_model(Invoice),
        object_id=invoice.pk,
        kind=PAYMENTS_KIND,
    ))


def _attachment(doc: Model, **kwargs: Any) -> DocumentAttachment:
    """Create an attachment directly, bypassing the API's rules."""
    defaults: dict[str, Any] = {
        'position': 1,
        'delivery': DocumentAttachment.Delivery.MERGE,
    }
    defaults.update(kwargs)
    return DocumentAttachment.objects.create(
        content_type=ContentType.objects.get_for_model(doc),
        object_id=doc.pk,
        **defaults,
    )


def _pay(invoice: Invoice, amount: str, **kwargs: Any) -> Payment:
    """Book a payment the way the API does: payment, ledger entry, resync."""
    assert invoice.customer is not None
    payment = Payment.objects.create(
        customer=invoice.customer,
        invoice=invoice,
        payment_date=kwargs.pop('payment_date', datetime.date(2026, 2, 1)),
        amount=Decimal(amount),
        **kwargs,
    )
    ledger.record_payment(payment)
    ledger.recalculate_invoice_status(invoice)
    return payment


def _fake_pdf(html: str) -> bytes:
    """Stand-in for WeasyPrint that tells the rendered pages apart."""
    if 'Zahlungsübersicht' in html:
        return b'%PDF-payments'
    if 'Berichtigungsnote' in html:
        return b'%PDF-correction'
    return b'%PDF-supplement'


class PaymentSupplementKindTests(APITestCase):
    def test_registered_with_its_rules(self) -> None:
        """The 'payments' kind is merge-only, mandatory, issued-only, and can
        neither be created, edited nor deleted by users.

        These flags are the kind's whole definition; every layer only enforces
        them, so they are pinned here.
        """
        handler = get_handler(PAYMENTS_KIND)

        self.assertEqual(handler.label, 'Zahlungsübersicht')
        self.assertEqual(handler.delivery_modes, (DocumentAttachment.Delivery.MERGE,))
        self.assertTrue(handler.renderable)
        self.assertTrue(handler.mandatory)
        self.assertFalse(handler.deletable)
        self.assertFalse(handler.editable)
        self.assertFalse(handler.creatable)
        self.assertTrue(handler.requires_issued_document)

    def test_it_merges_before_every_other_kind(self) -> None:
        """Its merge_order is below every other kind's, so its pages always come
        right after the invoice.
        """
        handler = get_handler(PAYMENTS_KIND)
        for kind in ('supplement', 'correction', 'file'):
            with self.subTest(kind=kind):
                self.assertLess(handler.merge_order, get_handler(kind).merge_order)

    def test_the_kinds_endpoint_reports_it_as_not_creatable(self) -> None:
        """The kinds endpoint carries creatable=False for it and True for the
        others — the attachment dialog hides kinds it may not create.
        """
        self.client.force_authenticate(user=_create_user())
        infos = {info['kind']: info for info in
                 self.client.get('/api/document-attachment-kinds/').json()}

        self.assertFalse(infos[PAYMENTS_KIND]['creatable'])
        self.assertTrue(infos['supplement']['creatable'])


class PaymentSupplementLifecycleTests(APITestCase):
    """The attachment follows the payments, through every route that books them."""

    def setUp(self) -> None:
        self.client.force_authenticate(user=_create_user())
        self.address = _make_address()
        self.invoice = _make_invoice(self.address, status='issued')

    def _post_payment(self, invoice: Invoice, amount: str) -> int:
        response = self.client.post('/api/payments/', {
            'customer': invoice.customer_id,
            'invoice': invoice.pk,
            'payment_date': '2026-02-01',
            'amount': amount,
            'method': 'transfer',
        })
        self.assertEqual(response.status_code, 201, response.data)
        return int(response.data['id'])

    def test_first_payment_creates_it(self) -> None:
        """Booking the first payment creates one Zahlungsübersicht, merged, at
        position 0 so it also lists first in the attachment dialog.
        """
        self.assertEqual(_supplements(self.invoice), [])

        self._post_payment(self.invoice, '50.00')

        [supplement] = _supplements(self.invoice)
        self.assertEqual(supplement.position, 0)
        self.assertEqual(supplement.delivery, DocumentAttachment.Delivery.MERGE)

    def test_further_payments_keep_a_single_one(self) -> None:
        """A second payment updates the existing Zahlungsübersicht instead of
        adding another one.
        """
        self._post_payment(self.invoice, '50.00')
        first = _supplements(self.invoice)[0]

        self._post_payment(self.invoice, '20.00')

        self.assertEqual([s.pk for s in _supplements(self.invoice)], [first.pk])

    def test_it_goes_with_the_last_payment(self) -> None:
        """Deleting (cancelling) a payment keeps it while payments remain, and
        removes it with the last one when no Mahnung was issued — the invoice
        then goes out without it.
        """
        first = self._post_payment(self.invoice, '50.00')
        second = self._post_payment(self.invoice, '20.00')

        self.assertEqual(self.client.delete(f'/api/payments/{first}/').status_code, 204)
        self.assertEqual(len(_supplements(self.invoice)), 1)

        self.assertEqual(self.client.delete(f'/api/payments/{second}/').status_code, 204)
        self.assertEqual(_supplements(self.invoice), [])

    def test_moving_a_payment_moves_it(self) -> None:
        """Rebooking a payment onto another invoice of the customer removes the
        Zahlungsübersicht from the old invoice and creates one on the new.
        """
        other = _make_invoice(self.address, status='issued')
        payment_id = self._post_payment(self.invoice, '50.00')

        response = self.client.patch(
            f'/api/payments/{payment_id}/', {'invoice': other.pk})

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(_supplements(self.invoice), [])
        self.assertEqual(len(_supplements(other)), 1)

    def test_mark_paid_creates_it(self) -> None:
        """The mark-paid shortcut books a payment, so it creates one too."""
        response = self.client.post(f'/api/invoices/{self.invoice.pk}/mark-paid/', {})

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(_supplements(self.invoice)), 1)

    def test_applying_credit_creates_it(self) -> None:
        """Offsetting a prepayment against the invoice books a credit payment,
        which the Zahlungsübersicht lists like any other.
        """
        assert self.invoice.customer is not None
        prepayment = Payment.objects.create(
            customer=self.invoice.customer, payment_date=datetime.date(2026, 1, 20),
            amount=Decimal('30.00'))
        ledger.record_payment(prepayment)
        ledger.record_invoice_issued(self.invoice)

        response = self.client.post(
            f'/api/invoices/{self.invoice.pk}/apply-credit/', {}, format='json')

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(_supplements(self.invoice)), 1)

    def _draft_reminder(self, fee: str = '12.00') -> Reminder:
        return Reminder.objects.create(
            invoice=self.invoice, level=1, status='draft',
            reminder_date=datetime.date(2026, 2, 1), due_date=datetime.date(2026, 2, 14),
            fee=Decimal(fee))

    def test_issuing_a_reminder_creates_it(self) -> None:
        """Issuing a Mahnung on an invoice without payments creates the
        Zahlungsübersicht: the fee raises what is owed, and the invoice page no
        longer shows fees, so the recipient would otherwise not see the claim.
        """
        reminder = self._draft_reminder()

        response = self.client.post(f'/api/reminders/{reminder.pk}/issue/')

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(_supplements(self.invoice)), 1)

    def test_issuing_a_reminder_without_fee_creates_it_too(self) -> None:
        """A fee-free Mahnung also creates it — it is the issued reminder that
        counts, not the fee — so the recipient sees what is still open.
        """
        reminder = self._draft_reminder(fee='0.00')

        self.client.post(f'/api/reminders/{reminder.pk}/issue/')

        self.assertEqual(len(_supplements(self.invoice)), 1)

    def test_a_draft_reminder_does_not_create_it(self) -> None:
        """A Mahnung still in draft is not owed yet and creates nothing, even
        when a sync runs (e.g. triggered by an unrelated payment change).
        """
        self._draft_reminder()

        sync_payment_supplement(self.invoice)

        self.assertEqual(_supplements(self.invoice), [])

    def test_an_issued_reminder_keeps_it_after_the_last_payment(self) -> None:
        """Deleting the last payment keeps the Zahlungsübersicht while an issued
        Mahnung still needs it.
        """
        payment_id = self._post_payment(self.invoice, '50.00')
        reminder = self._draft_reminder()
        issued = self.client.post(f'/api/reminders/{reminder.pk}/issue/')
        self.assertEqual(issued.status_code, 200, issued.data)

        deleted = self.client.delete(f'/api/payments/{payment_id}/')

        self.assertEqual(deleted.status_code, 204)
        self.assertEqual(len(_supplements(self.invoice)), 1)

    def test_sync_is_idempotent_without_payments(self) -> None:
        """Syncing an invoice that never had payments creates nothing."""
        self.assertIsNone(sync_payment_supplement(self.invoice))
        self.assertEqual(_supplements(self.invoice), [])


class PaymentSupplementProtectionTests(APITestCase):
    """Users can neither create, edit nor delete a Zahlungsübersicht."""

    def setUp(self) -> None:
        self.client.force_authenticate(user=_create_user())
        self.invoice = _make_invoice(_make_address(), status='issued')
        self.base = f'/api/invoices/{self.invoice.pk}/attachments'

    def test_creating_one_is_refused(self) -> None:
        """POSTing kind=payments is a 400: it only ever comes from the payments."""
        response = self.client.post(
            f'{self.base}/', {'kind': PAYMENTS_KIND, 'title': 'Zahlungen'}, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertIn('kind', response.json())
        self.assertEqual(_supplements(self.invoice), [])

    def test_editing_it_is_refused(self) -> None:
        """PATCHing its content is a 400 and leaves it unchanged."""
        _pay(self.invoice, '50.00')
        [supplement] = _supplements(self.invoice)

        response = self.client.patch(
            f'{self.base}/{supplement.pk}/', {'title': 'Anders'}, format='json')

        self.assertEqual(response.status_code, 400)
        supplement.refresh_from_db()
        self.assertEqual(supplement.title, '')

    def test_deleting_it_through_the_api_is_refused(self) -> None:
        """DELETE is a 400 while the invoice has payments; the row stays."""
        _pay(self.invoice, '50.00')
        [supplement] = _supplements(self.invoice)

        response = self.client.delete(f'{self.base}/{supplement.pk}/')

        self.assertEqual(response.status_code, 400)
        self.assertEqual(len(_supplements(self.invoice)), 1)

    def test_deleting_it_directly_is_refused(self) -> None:
        """Deleting the row outside its service (admin, shell) raises
        ProtectedError — the exception for the service does not leak.
        """
        _pay(self.invoice, '50.00')
        [supplement] = _supplements(self.invoice)

        with self.assertRaises(ProtectedError), transaction.atomic():
            supplement.delete()


class PaymentSupplementRenderTests(APITestCase):
    def setUp(self) -> None:
        # 100.00 net + 20 % → 120.00 gross
        self.invoice = _make_invoice(_make_address(), status='issued')

    def _html(self) -> str:
        [supplement] = _supplements(self.invoice)
        return get_handler(PAYMENTS_KIND).render_html(supplement)

    def test_lists_payments_and_the_open_amount(self) -> None:
        """The page lists the invoice total, every payment with date and method,
        their sum, and the open amount — and no credit line.
        """
        _pay(self.invoice, '50.00', payment_date=datetime.date(2026, 2, 1))
        _pay(self.invoice, '20.00', payment_date=datetime.date(2026, 2, 10),
             method=Payment.Method.CASH)

        html = self._html()

        self.assertIn('Zahlungsübersicht', html)
        self.assertIn('RE2601-001', html)
        self.assertIn('120,00', html)
        self.assertIn('01.02.2026', html)
        self.assertIn('10.02.2026', html)
        self.assertIn('Bar', html)
        self.assertIn('−70,00', html)
        self.assertIn('Offener Betrag', html)
        self.assertIn('50,00', html)
        self.assertNotIn('Guthaben (Überzahlung)', html)

    def test_an_overpayment_shows_the_credit(self) -> None:
        """Paying more than is due shows the surplus as credit instead of a
        negative open amount.
        """
        _pay(self.invoice, '150.00')

        html = self._html()

        self.assertIn('Guthaben (Überzahlung)', html)
        self.assertIn('30,00', html)
        self.assertNotIn('Offener Betrag', html)

    def test_issued_reminder_fees_are_listed(self) -> None:
        """Fees of issued reminders are listed and counted into the total claim;
        a draft reminder's fee is not owed yet and stays off the page.
        """
        Reminder.objects.create(
            invoice=self.invoice, level=1, number='MA2601-001', status='issued',
            reminder_date=datetime.date(2026, 2, 1), due_date=datetime.date(2026, 2, 14),
            fee=Decimal('12.00'))
        Reminder.objects.create(
            invoice=self.invoice, level=2, status='draft',
            reminder_date=datetime.date(2026, 2, 20), due_date=datetime.date(2026, 3, 6),
            fee=Decimal('25.00'))
        _pay(self.invoice, '50.00')

        html = self._html()

        self.assertIn('MA2601-001', html)
        self.assertIn('12,00', html)
        self.assertIn('Gesamtforderung', html)
        self.assertIn('132,00', html)
        self.assertNotIn('25,00', html)
        self.assertIn('82,00', html)

    def test_reminder_fees_without_payments(self) -> None:
        """With an issued Mahnung but no payments the page shows the invoice,
        the fee, the total claim and the full open amount — and no payment sum.
        """
        Reminder.objects.create(
            invoice=self.invoice, level=1, number='MA2601-001', status='issued',
            reminder_date=datetime.date(2026, 2, 1), due_date=datetime.date(2026, 2, 14),
            fee=Decimal('12.00'))
        sync_payment_supplement(self.invoice)

        html = self._html()

        self.assertIn('Gesamtforderung', html)
        self.assertIn('132,00', html)
        self.assertIn('Offener Betrag', html)
        self.assertNotIn('Summe der Zahlungen', html)

    def test_the_invoice_itself_no_longer_lists_payments(self) -> None:
        """The invoice page shows no payment block: payments now live only on
        the Zahlungsübersicht, so they are not printed twice.
        """
        _pay(self.invoice, '50.00')
        self.client.force_authenticate(user=_create_user())

        response = self.client.get(f'/api/invoices/{self.invoice.pk}/preview/')
        html = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertNotIn('Bereits bezahlt', html)
        self.assertNotIn('Offener Betrag', html)


class PaymentSupplementSendTests(APITestCase):
    def setUp(self) -> None:
        self.client.force_authenticate(user=_create_user())
        self.invoice = _make_invoice(_make_address(), status='issued')
        self.base = f'/api/invoices/{self.invoice.pk}'

    def test_email_info_reports_it_as_mandatory(self) -> None:
        """email-info lists it in mandatory_attachment_ids, so the send dialog
        shows it ticked and locked.
        """
        _pay(self.invoice, '50.00')
        [supplement] = _supplements(self.invoice)

        data = self.client.get(f'{self.base}/email-info/').json()

        self.assertEqual(data['mandatory_attachment_ids'], [supplement.pk])

    def test_its_pages_come_right_after_the_invoice(self) -> None:
        """The document PDF (send-pdf, which the download uses too) is invoice,
        then Zahlungsübersicht, then the other merged attachments — even when
        those were created earlier and positioned before it.
        """
        _attachment(self.invoice, kind='correction', position=1, title='Korrektur')
        extra = _attachment(self.invoice, kind='supplement', position=2, title='Hinweis')
        _pay(self.invoice, '50.00')
        # Even a position that would sort it last does not move its pages.
        [supplement] = _supplements(self.invoice)
        supplement.position = 99
        supplement.save(update_fields=['position'])

        with patch('billing.views.render_document_pdf', return_value=b'%PDF-doc'), \
             patch('billing.attachments.handlers.render_html_to_pdf', side_effect=_fake_pdf), \
             patch('billing.attachments.send.merge_pdfs',
                   return_value=b'%PDF-merged') as merge:
            response = self.client.get(
                f'{self.base}/send-pdf/', {'attachment_ids': [extra.pk]})

        self.assertEqual(response.status_code, 200)
        merge.assert_called_once_with(
            [b'%PDF-doc', b'%PDF-payments', b'%PDF-correction', b'%PDF-supplement'])


class PaymentSupplementBackfillTests(TestCase):
    def setUp(self) -> None:
        self.migration = importlib.import_module(
            'billing.migrations.0013_backfill_payment_supplements')
        self.address = _make_address()

    def test_backfills_invoices_with_payments_or_reminders_only_once(self) -> None:
        """The data migration gives every invoice with payments or an issued
        Mahnung exactly one Zahlungsübersicht.  It skips invoices with neither
        (a draft Mahnung does not count) and ones that already have it, and
        ignores prepayments without an invoice.
        """
        paid = _make_invoice(self.address, status='issued')
        already = _make_invoice(self.address, status='issued')
        unpaid = _make_invoice(self.address, status='issued')
        reminded = _make_invoice(self.address, status='issued')
        drafted = _make_invoice(self.address, status='issued')
        for dunned, status in ((reminded, 'issued'), (drafted, 'draft')):
            Reminder.objects.create(
                invoice=dunned, level=1, status=status,
                reminder_date=datetime.date(2026, 2, 1),
                due_date=datetime.date(2026, 2, 14))
        assert self.address.customer is not None
        for invoice in (paid, already, None):
            Payment.objects.create(
                customer=self.address.customer, invoice=invoice,
                payment_date=datetime.date(2026, 2, 1), amount=Decimal('10.00'))
        sync_payment_supplement(already)

        self.migration.create_payment_supplements(apps, None)

        self.assertEqual(len(_supplements(paid)), 1)
        self.assertEqual(len(_supplements(already)), 1)
        self.assertEqual(_supplements(unpaid), [])
        self.assertEqual(len(_supplements(reminded)), 1)
        self.assertEqual(_supplements(drafted), [])
