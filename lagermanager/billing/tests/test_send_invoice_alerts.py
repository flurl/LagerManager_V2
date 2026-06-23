import datetime
from io import StringIO
from unittest.mock import patch

from core.models import Address
from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from notifications.models import InvoiceAlertSubscription, Notification

from billing.models import Invoice

_TODAY = datetime.date(2026, 6, 23)
_YESTERDAY = _TODAY - datetime.timedelta(days=1)
_TOMORROW = _TODAY + datetime.timedelta(days=1)


def _make_address() -> Address:
    return Address.objects.create(vorname='Max', nachname='Mustermann')


def _make_invoice(
    *,
    status: str = Invoice.Status.ISSUED,
    due_date: datetime.date = _YESTERDAY,
    address: Address | None = None,
) -> Invoice:
    if address is None:
        address = _make_address()
    return Invoice.objects.create(
        status=status,
        due_date=due_date,
        document_date=due_date - datetime.timedelta(days=14),
        address=address,
    )


class SendInvoiceAlertsCommandTest(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username='testuser', password='x')
        self.stdout = StringIO()

    def _call(self) -> str:
        with patch(
            'billing.management.commands.send_invoice_alerts._get_today',
            return_value=_TODAY,
        ):
            call_command('send_invoice_alerts', stdout=self.stdout)
        return self.stdout.getvalue()

    def _subscribe(self, *, user: User | None = None, active: bool = True) -> InvoiceAlertSubscription:
        return InvoiceAlertSubscription.objects.create(
            user=user or self.user, active=active
        )

    # ------------------------------------------------------------------
    # no overdue invoices
    # ------------------------------------------------------------------
    def test_no_overdue_invoices_skips(self) -> None:
        _make_invoice(due_date=_TOMORROW)  # not yet overdue
        self._subscribe()

        out = self._call()
        self.assertIn('No overdue invoices', out)
        self.assertEqual(Notification.objects.count(), 0)

    def test_paid_invoice_not_counted(self) -> None:
        _make_invoice(status=Invoice.Status.PAID, due_date=_YESTERDAY)
        self._subscribe()

        out = self._call()
        self.assertIn('No overdue invoices', out)
        self.assertEqual(Notification.objects.count(), 0)

    def test_cancelled_invoice_not_counted(self) -> None:
        _make_invoice(status=Invoice.Status.CANCELLED, due_date=_YESTERDAY)
        self._subscribe()

        out = self._call()
        self.assertIn('No overdue invoices', out)
        self.assertEqual(Notification.objects.count(), 0)

    def test_draft_invoice_not_counted(self) -> None:
        _make_invoice(status=Invoice.Status.DRAFT, due_date=_YESTERDAY)
        self._subscribe()

        out = self._call()
        self.assertIn('No overdue invoices', out)
        self.assertEqual(Notification.objects.count(), 0)

    # ------------------------------------------------------------------
    # no active subscribers
    # ------------------------------------------------------------------
    def test_no_active_subscribers_skips(self) -> None:
        _make_invoice(due_date=_YESTERDAY)
        self._subscribe(active=False)

        out = self._call()
        self.assertIn('No active subscribers', out)
        self.assertEqual(Notification.objects.count(), 0)

    # ------------------------------------------------------------------
    # happy path
    # ------------------------------------------------------------------
    def test_notifications_created_for_active_subscribers(self) -> None:
        addr = _make_address()
        _make_invoice(due_date=_YESTERDAY, address=addr)
        _make_invoice(status=Invoice.Status.SENT, due_date=_YESTERDAY, address=addr)

        second_user = User.objects.create_user(username='user2', password='x')
        InvoiceAlertSubscription.objects.create(user=second_user, active=True)
        self._subscribe()

        out = self._call()

        self.assertIn('Notified 2 user(s)', out)
        notifications = Notification.objects.all()
        self.assertEqual(notifications.count(), 2)

        n = notifications.filter(user=self.user).get()
        self.assertEqual(n.severity, Notification.Severity.WARNING)
        self.assertEqual(n.kind, 'invoice_alert')
        self.assertIn('2 überfällige Rechnungen', n.title)

    def test_singular_title_for_one_invoice(self) -> None:
        _make_invoice(due_date=_YESTERDAY)
        self._subscribe()

        self._call()

        n = Notification.objects.get(user=self.user)
        self.assertIn('1 überfällige Rechnung', n.title)
        self.assertNotIn('Rechnungen', n.title)

    def test_message_contains_due_date(self) -> None:
        _make_invoice(due_date=datetime.date(2026, 6, 1))
        self._subscribe()

        self._call()

        n = Notification.objects.get(user=self.user)
        self.assertIn('01.06.2026', n.message)

    # ------------------------------------------------------------------
    # inactive subscriber excluded
    # ------------------------------------------------------------------
    def test_inactive_subscriber_excluded(self) -> None:
        _make_invoice(due_date=_YESTERDAY)
        active_user = User.objects.create_user(username='active', password='x')
        InvoiceAlertSubscription.objects.create(user=active_user, active=True)
        self._subscribe(active=False)

        self._call()

        self.assertEqual(Notification.objects.filter(user=self.user).count(), 0)
        self.assertEqual(Notification.objects.filter(user=active_user).count(), 1)


class InvoiceAlertSubscriptionModelTest(TestCase):
    def test_str_active(self) -> None:
        user = User.objects.create_user(username='alice', password='x')
        sub = InvoiceAlertSubscription(user=user, active=True)
        self.assertIn('aktiv', str(sub))

    def test_str_inactive(self) -> None:
        user = User.objects.create_user(username='bob', password='x')
        sub = InvoiceAlertSubscription(user=user, active=False)
        self.assertIn('inaktiv', str(sub))

    def test_one_subscription_per_user(self) -> None:
        user = User.objects.create_user(username='carol', password='x')
        InvoiceAlertSubscription.objects.create(user=user)
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            InvoiceAlertSubscription.objects.create(user=user)
