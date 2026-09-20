"""API tests for partial payments and the invoice status they drive."""
import datetime
from decimal import Decimal

from core.models import Address, Customer
from core.services.customers import ensure_customer_for_address
from deliveries.models import TaxRate
from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from billing.models import CustomerLedgerEntry, Invoice, InvoiceLine, Payment, Reminder
from billing.services import ledger


def _make_customer(**kwargs: object) -> Customer:
    defaults: dict[str, object] = {'vorname': 'Max', 'nachname': 'Mustermann'}
    defaults.update(kwargs)
    address: Address = Address.objects.create(**defaults)
    return ensure_customer_for_address(address)


class PaymentApiTests(APITestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_superuser('test', 'test@example.com', 'password')
        self.client.force_authenticate(user=self.user)
        self.tax = TaxRate.objects.create(name='Normal', percent=Decimal('20.00'))
        self.customer = _make_customer()
        self.invoice = self._make_invoice()

    def _make_invoice(
        self,
        *,
        unit_price: str = '100.00',
        status: str = Invoice.Status.ISSUED,
        number: str = 'RE260601-00001',
    ) -> Invoice:
        invoice = Invoice.objects.create(
            customer=self.customer,
            address=self.customer.default_address,
            number=number,
            document_date=datetime.date(2026, 6, 15),
            due_date=datetime.date(2026, 6, 29),
            status=status,
        )
        InvoiceLine.objects.create(
            invoice=invoice,
            position=1,
            description='Leistung',
            quantity=Decimal('1'),
            unit_price=Decimal(unit_price),
            tax_rate=self.tax,
        )
        ledger.record_invoice_issued(invoice)
        return invoice

    def _pay(self, amount: str, date: str = '2026-07-01', **extra: object) -> object:
        payload: dict[str, object] = {
            'customer': self.customer.pk,
            'invoice': self.invoice.pk,
            'payment_date': date,
            'amount': amount,
            'method': 'transfer',
        }
        payload.update(extra)
        return self.client.post('/api/payments/', payload)

    # -- status transitions ------------------------------------------------

    def test_partial_then_full_payment_drives_the_status(self) -> None:
        self.assertEqual(self._pay('50.00').status_code, 201)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.Status.PARTIALLY_PAID)
        self.assertIsNone(self.invoice.paid_at)
        self.assertEqual(self.invoice.open_amount, Decimal('70.00'))

        self.assertEqual(self._pay('70.00', date='2026-07-15').status_code, 201)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.Status.PAID)
        # paid_at is the date of the payment that settled it, not the first one.
        self.assertEqual(self.invoice.paid_at, datetime.date(2026, 7, 15))
        self.assertEqual(self.invoice.open_amount, Decimal('0.00'))

    def test_deleting_a_payment_reopens_the_invoice(self) -> None:
        resp = self._pay('120.00')
        payment_id = resp.json()['id']
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.Status.PAID)

        self.assertEqual(
            self.client.delete(f'/api/payments/{payment_id}/').status_code, 204)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.Status.ISSUED)
        self.assertIsNone(self.invoice.paid_at)
        # The ledger entry goes with it, or the balance would keep counting it.
        self.assertEqual(ledger.customer_balance(self.customer), Decimal('-120.00'))

    def test_deleting_one_of_two_payments_leaves_it_partially_paid(self) -> None:
        first = self._pay('50.00').json()['id']
        self._pay('70.00', date='2026-07-15')
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.Status.PAID)

        self.client.delete(f'/api/payments/{first}/')
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.Status.PARTIALLY_PAID)

    def test_editing_a_payment_rebooks_the_ledger(self) -> None:
        payment_id = self._pay('50.00').json()['id']
        resp = self.client.patch(f'/api/payments/{payment_id}/', {'amount': '120.00'})
        self.assertEqual(resp.status_code, 200)

        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.Status.PAID)
        self.assertEqual(ledger.customer_balance(self.customer), Decimal('0.00'))
        self.assertEqual(
            CustomerLedgerEntry.objects.filter(payment_id=payment_id).count(), 1)

    def test_overpayment_leaves_the_customer_in_credit(self) -> None:
        self.assertEqual(self._pay('150.00').status_code, 201)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.Status.PAID)
        self.assertEqual(ledger.customer_balance(self.customer), Decimal('30.00'))
        self.assertEqual(ledger.available_credit(self.customer), Decimal('30.00'))

    # -- validation --------------------------------------------------------

    def test_zero_amount_rejected(self) -> None:
        resp = self._pay('0.00')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('amount', resp.json())

    def test_negative_amount_rejected(self) -> None:
        self.assertEqual(self._pay('-10.00').status_code, 400)

    def test_customer_mismatch_rejected(self) -> None:
        other = _make_customer(vorname='Erika', nachname='Musterfrau')
        resp = self._pay('50.00', customer=other.pk)
        self.assertEqual(resp.status_code, 400)
        self.assertIn('invoice', resp.json())

    def test_payment_on_a_draft_invoice_rejected(self) -> None:
        draft = self._make_invoice(status=Invoice.Status.DRAFT, number='')
        resp = self.client.post('/api/payments/', {
            'customer': self.customer.pk,
            'invoice': draft.pk,
            'payment_date': '2026-07-01',
            'amount': '50.00',
        })
        self.assertEqual(resp.status_code, 400)

    def test_payment_on_a_cancelled_invoice_rejected(self) -> None:
        self.invoice.status = Invoice.Status.CANCELLED
        self.invoice.save(update_fields=['status'])
        self.assertEqual(self._pay('50.00').status_code, 400)

    def test_unauthenticated_rejected(self) -> None:
        self.client.force_authenticate(user=None)
        self.assertEqual(self._pay('50.00').status_code, 401)

    # -- standalone prepayments -------------------------------------------

    def test_payment_without_invoice_becomes_credit(self) -> None:
        resp = self.client.post('/api/payments/', {
            'customer': self.customer.pk,
            'payment_date': '2026-06-01',
            'amount': '50.00',
        })
        self.assertEqual(resp.status_code, 201)
        self.assertIsNone(resp.json()['invoice'])
        self.assertEqual(ledger.available_credit(self.customer), Decimal('50.00'))

    def test_standalone_payment_raises_the_balance_and_becomes_credit(self) -> None:
        """What the "Zahlung erfassen" button in the Kundenkonto dialog posts."""
        before = ledger.customer_balance(self.customer)

        resp = self.client.post('/api/payments/', {
            'customer': self.customer.pk,
            'payment_date': '2026-06-01',
            'amount': '50.00',
            'method': 'transfer',
            'note': 'Anzahlung',
        })
        self.assertEqual(resp.status_code, 201)
        self.assertIsNone(resp.json()['invoice'])

        self.assertEqual(
            ledger.customer_balance(self.customer), before + Decimal('50.00'))
        self.assertEqual(ledger.available_credit(self.customer), Decimal('50.00'))
        # It settles nothing on its own — that is the "… verrechnen" step.
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.Status.ISSUED)
        self.assertEqual(self.invoice.open_amount, Decimal('120.00'))

    def test_standalone_payment_shows_up_on_the_ledger_endpoint(self) -> None:
        self.client.post('/api/payments/', {
            'customer': self.customer.pk,
            'payment_date': '2026-06-01',
            'amount': '50.00',
        })
        data = self.client.get(f'/api/customers/{self.customer.pk}/ledger/').json()
        standalone = [e for e in data['entries'] if e['invoice'] is None]
        self.assertEqual(len(standalone), 1)
        self.assertEqual(standalone[0]['amount'], '50.00')
        self.assertEqual(standalone[0]['description'], 'Zahlung ohne Rechnungsbezug')
        self.assertFalse(standalone[0]['is_reversal'])

    def test_filter_by_invoice_and_customer(self) -> None:
        self._pay('50.00')
        other = _make_customer(vorname='Erika', nachname='Musterfrau')
        Payment.objects.create(
            customer=other,
            payment_date=datetime.date(2026, 7, 1),
            amount=Decimal('10.00'),
        )
        by_invoice = self.client.get(f'/api/payments/?invoice_id={self.invoice.pk}')
        self.assertEqual(len(by_invoice.json()['results']), 1)
        by_customer = self.client.get(f'/api/payments/?customer_id={other.pk}')
        self.assertEqual(len(by_customer.json()['results']), 1)
        unallocated = self.client.get('/api/payments/?unallocated=true')
        self.assertEqual(len(unallocated.json()['results']), 1)

    # -- reminder fees -----------------------------------------------------

    def _draft_reminder(self, fee: str = '12.00') -> Reminder:
        return Reminder.objects.create(
            invoice=self.invoice,
            level=1,
            reminder_date=datetime.date(2026, 7, 20),
            due_date=datetime.date(2026, 8, 3),
            fee=Decimal(fee),
        )

    def test_a_stale_draft_cannot_be_issued_once_the_invoice_is_paid(self) -> None:
        """A draft written while the invoice was open goes stale when it is paid."""
        reminder = self._draft_reminder()
        self._pay('120.00')
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.Status.PAID)

        resp = self.client.post(f'/api/reminders/{reminder.pk}/issue/')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('nicht mehr offen', resp.json()['detail'])

        # No number burned, no fee charged, invoice untouched.
        reminder.refresh_from_db()
        self.assertEqual(reminder.status, Reminder.Status.DRAFT)
        self.assertIsNone(reminder.number)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.Status.PAID)
        self.assertEqual(self.invoice.open_amount, Decimal('0.00'))
        self.assertEqual(self.invoice.reminder_fee_total, Decimal('0.00'))
        self.assertEqual(ledger.customer_balance(self.customer), Decimal('0.00'))

    def test_a_stale_draft_cannot_be_issued_once_the_invoice_is_cancelled(self) -> None:
        reminder = self._draft_reminder()
        self.invoice.status = Invoice.Status.CANCELLED
        self.invoice.save(update_fields=['status'])

        resp = self.client.post(f'/api/reminders/{reminder.pk}/issue/')
        self.assertEqual(resp.status_code, 400)

    def test_a_partially_paid_invoice_can_still_be_dunned(self) -> None:
        """There is still an open amount, so dunning remains legitimate."""
        self._pay('50.00')
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.Status.PARTIALLY_PAID)

        reminder = self._draft_reminder()
        resp = self.client.post(f'/api/reminders/{reminder.pk}/issue/')
        self.assertEqual(resp.status_code, 200)

        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.Status.PARTIALLY_PAID)
        # 120 invoice + 12 fee − 50 paid
        self.assertEqual(self.invoice.open_amount, Decimal('82.00'))

    def test_a_reminder_cannot_be_created_for_a_paid_invoice(self) -> None:
        self._pay('120.00')
        resp = self.client.post('/api/reminders/', {
            'invoice': self.invoice.pk,
            'level': 1,
            'reminder_date': '2026-07-20',
            'due_date': '2026-08-03',
            'fee': '12.00',
        })
        self.assertEqual(resp.status_code, 400)
        self.assertIn('invoice', resp.json())

    def test_an_existing_reminder_stays_editable_after_the_invoice_is_paid(self) -> None:
        """Only issuing is refused — the draft must remain correctable."""
        reminder = self._draft_reminder()
        self._pay('120.00')
        resp = self.client.patch(
            f'/api/reminders/{reminder.pk}/', {'notes': 'Hinfällig, bezahlt'})
        self.assertEqual(resp.status_code, 200)

    def test_reminder_fee_cannot_be_changed_after_issue(self) -> None:
        reminder = Reminder.objects.create(
            invoice=self.invoice,
            level=1,
            reminder_date=datetime.date(2026, 7, 20),
            due_date=datetime.date(2026, 8, 3),
            fee=Decimal('12.00'),
        )
        self.client.post(f'/api/reminders/{reminder.pk}/issue/')
        resp = self.client.patch(f'/api/reminders/{reminder.pk}/', {'fee': '20.00'})
        self.assertEqual(resp.status_code, 400)
        self.assertIn('Mahngebühr', resp.json()['detail'])

    def test_reminder_fee_can_be_changed_while_draft(self) -> None:
        reminder = Reminder.objects.create(
            invoice=self.invoice,
            level=1,
            reminder_date=datetime.date(2026, 7, 20),
            due_date=datetime.date(2026, 8, 3),
            fee=Decimal('12.00'),
        )
        resp = self.client.patch(f'/api/reminders/{reminder.pk}/', {'fee': '20.00'})
        self.assertEqual(resp.status_code, 200)

    def test_resending_an_unchanged_fee_is_allowed(self) -> None:
        """A PATCH that echoes the current fee must not trip the guard."""
        reminder = Reminder.objects.create(
            invoice=self.invoice,
            level=1,
            reminder_date=datetime.date(2026, 7, 20),
            due_date=datetime.date(2026, 8, 3),
            fee=Decimal('12.00'),
        )
        self.client.post(f'/api/reminders/{reminder.pk}/issue/')
        resp = self.client.patch(
            f'/api/reminders/{reminder.pk}/', {'fee': '12.00', 'notes': 'Hinweis'})
        self.assertEqual(resp.status_code, 200)

    # -- payment-info ------------------------------------------------------

    def test_payment_info(self) -> None:
        self._pay('50.00')
        resp = self.client.get(f'/api/invoices/{self.invoice.pk}/payment-info/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['gross_total'], '120.00')
        self.assertEqual(data['paid_amount'], '50.00')
        self.assertEqual(data['open_amount'], '70.00')
        self.assertEqual(len(data['payments']), 1)

    def test_reminder_preview_lists_payments_and_the_open_amount(self) -> None:
        self._pay('50.00')
        reminder = Reminder.objects.create(
            invoice=self.invoice,
            level=1,
            reminder_date=datetime.date(2026, 7, 20),
            due_date=datetime.date(2026, 8, 3),
            fee=Decimal('12.00'),
        )
        self.client.post(f'/api/reminders/{reminder.pk}/issue/')
        html = self.client.get(
            f'/api/reminders/{reminder.pk}/preview/').content.decode()

        self.assertIn('Bereits bezahlt', html)
        self.assertIn('01.07.2026', html)
        self.assertIn('Mahngebühr', html)
        # 120.00 invoice + 12.00 fee − 50.00 paid
        self.assertIn('82,00', html)

    def test_reminder_preview_shows_cumulative_fees(self) -> None:
        first = Reminder.objects.create(
            invoice=self.invoice, level=1,
            reminder_date=datetime.date(2026, 7, 20),
            due_date=datetime.date(2026, 8, 3),
            fee=Decimal('12.00'),
        )
        self.client.post(f'/api/reminders/{first.pk}/issue/')
        second = Reminder.objects.create(
            invoice=self.invoice, level=2,
            reminder_date=datetime.date(2026, 8, 10),
            due_date=datetime.date(2026, 8, 24),
            fee=Decimal('20.00'),
        )
        self.client.post(f'/api/reminders/{second.pk}/issue/')
        html = self.client.get(
            f'/api/reminders/{second.pk}/preview/').content.decode()

        self.assertIn('Mahngebühren (gesamt)', html)
        self.assertIn('32,00', html)
        self.assertIn('152,00', html)
