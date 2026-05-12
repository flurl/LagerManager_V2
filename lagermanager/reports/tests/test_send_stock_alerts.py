import datetime
from io import StringIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase

from notifications.models import Notification, StockAlertSubscription


class SendStockAlertsCommandTest(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username='testuser', password='x')
        self.stdout = StringIO()

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _call(self) -> str:
        call_command('send_stock_alerts', stdout=self.stdout)
        return self.stdout.getvalue()

    def _subscribe(self, *, active: bool = True) -> StockAlertSubscription:
        return StockAlertSubscription.objects.create(user=self.user, active=active)

    # ------------------------------------------------------------------
    # no active period
    # ------------------------------------------------------------------
    @patch('reports.management.commands.send_stock_alerts.get_period_for_datetime', return_value=None)
    def test_no_active_period_skips(self, _mock_period: object) -> None:
        out = self._call()
        self.assertIn('No active period', out)
        self.assertEqual(Notification.objects.count(), 0)

    # ------------------------------------------------------------------
    # no articles below minimum
    # ------------------------------------------------------------------
    @patch('reports.management.commands.send_stock_alerts.get_below_minimum_stock', return_value=[])
    @patch('reports.management.commands.send_stock_alerts.get_period_for_datetime')
    def test_no_articles_below_minimum_skips(self, mock_period: object, _mock_rows: object) -> None:
        from unittest.mock import MagicMock
        mock_period.return_value = MagicMock(pk=1)
        self._subscribe()

        out = self._call()
        self.assertIn('No articles below minimum', out)
        self.assertEqual(Notification.objects.count(), 0)

    # ------------------------------------------------------------------
    # no active subscribers
    # ------------------------------------------------------------------
    @patch('reports.management.commands.send_stock_alerts.get_below_minimum_stock')
    @patch('reports.management.commands.send_stock_alerts.get_period_for_datetime')
    def test_no_active_subscribers_skips(self, mock_period: object, mock_rows: object) -> None:
        from unittest.mock import MagicMock
        mock_period.return_value = MagicMock(pk=1)
        mock_rows.return_value = [{'article': 'Bier', 'stock': 1.0, 'minimum_inventory': 10, 'shortage': 9.0}]
        self._subscribe(active=False)

        out = self._call()
        self.assertIn('No active subscribers', out)
        self.assertEqual(Notification.objects.count(), 0)

    # ------------------------------------------------------------------
    # happy path
    # ------------------------------------------------------------------
    @patch('reports.management.commands.send_stock_alerts.get_below_minimum_stock')
    @patch('reports.management.commands.send_stock_alerts.get_period_for_datetime')
    def test_notifications_created_for_active_subscribers(
        self, mock_period: object, mock_rows: object
    ) -> None:
        from unittest.mock import MagicMock
        mock_period.return_value = MagicMock(pk=1)
        mock_rows.return_value = [
            {'article': 'Bier', 'stock': 1.0, 'minimum_inventory': 10, 'shortage': 9.0},
            {'article': 'Wein', 'stock': 0.0, 'minimum_inventory': 5, 'shortage': 5.0},
        ]
        self._subscribe()
        second_user = User.objects.create_user(username='user2', password='x')
        StockAlertSubscription.objects.create(user=second_user, active=True)

        out = self._call()

        self.assertIn('Notified 2 user(s)', out)
        notifications = Notification.objects.all()
        self.assertEqual(notifications.count(), 2)
        n = notifications.filter(user=self.user).get()
        self.assertEqual(n.severity, Notification.Severity.WARNING)
        self.assertEqual(n.kind, 'stock_alert')
        self.assertIn('2 Artikel', n.title)
        self.assertIn('Bier', n.message)
        self.assertIn('Wein', n.message)

    # ------------------------------------------------------------------
    # inactive subscriber receives no notification
    # ------------------------------------------------------------------
    @patch('reports.management.commands.send_stock_alerts.get_below_minimum_stock')
    @patch('reports.management.commands.send_stock_alerts.get_period_for_datetime')
    def test_inactive_subscriber_excluded(
        self, mock_period: object, mock_rows: object
    ) -> None:
        from unittest.mock import MagicMock
        mock_period.return_value = MagicMock(pk=1)
        mock_rows.return_value = [
            {'article': 'Bier', 'stock': 1.0, 'minimum_inventory': 10, 'shortage': 9.0},
        ]
        active_user = User.objects.create_user(username='active', password='x')
        StockAlertSubscription.objects.create(user=active_user, active=True)
        self._subscribe(active=False)

        self._call()

        self.assertEqual(Notification.objects.filter(user=self.user).count(), 0)
        self.assertEqual(Notification.objects.filter(user=active_user).count(), 1)


class StockAlertSubscriptionModelTest(TestCase):
    def test_str_active(self) -> None:
        user = User.objects.create_user(username='alice', password='x')
        sub = StockAlertSubscription(user=user, active=True)
        self.assertIn('aktiv', str(sub))

    def test_str_inactive(self) -> None:
        user = User.objects.create_user(username='bob', password='x')
        sub = StockAlertSubscription(user=user, active=False)
        self.assertIn('inaktiv', str(sub))

    def test_one_subscription_per_user(self) -> None:
        user = User.objects.create_user(username='carol', password='x')
        StockAlertSubscription.objects.create(user=user)
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            StockAlertSubscription.objects.create(user=user)
