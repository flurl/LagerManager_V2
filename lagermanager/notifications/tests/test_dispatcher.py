from django.contrib.auth.models import User
from django.test import TestCase

from notifications.models import Notification
from notifications.services.dispatcher import notify


class DispatcherTest(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username='tester', password='pass')

    def test_creates_notification_with_defaults(self) -> None:
        n = notify(user=self.user, title='Hello')
        self.assertEqual(n.user, self.user)
        self.assertEqual(n.title, 'Hello')
        self.assertEqual(n.severity, Notification.Severity.INFO)
        self.assertEqual(n.message, '')
        self.assertEqual(n.kind, '')
        self.assertEqual(n.link, '')
        self.assertIsNone(n.read_at)

    def test_creates_notification_with_all_fields(self) -> None:
        n = notify(
            user=self.user,
            title='Low stock',
            severity=Notification.Severity.WARNING,
            message='Article X is below minimum',
            kind='stock_below_min',
            link='/below-minimum-stock',
        )
        self.assertEqual(n.severity, Notification.Severity.WARNING)
        self.assertEqual(n.message, 'Article X is below minimum')
        self.assertEqual(n.kind, 'stock_below_min')
        self.assertEqual(n.link, '/below-minimum-stock')

    def test_notification_is_persisted(self) -> None:
        n = notify(user=self.user, title='Persisted')
        self.assertIsNotNone(n.pk)
        self.assertTrue(Notification.objects.filter(pk=n.pk).exists())
