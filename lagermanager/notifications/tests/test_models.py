from django.contrib.auth.models import User
from django.test import TestCase

from notifications.models import Notification


class NotificationModelTest(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username='tester', password='pass')

    def test_default_severity_is_info(self) -> None:
        n = Notification.objects.create(user=self.user, title='Test')
        self.assertEqual(n.severity, Notification.Severity.INFO)

    def test_default_message_and_kind_and_link_are_empty(self) -> None:
        n = Notification.objects.create(user=self.user, title='Test')
        self.assertEqual(n.message, '')
        self.assertEqual(n.kind, '')
        self.assertEqual(n.link, '')

    def test_is_read_false_when_read_at_is_none(self) -> None:
        n = Notification.objects.create(user=self.user, title='Test')
        self.assertFalse(n.is_read)

    def test_is_read_true_when_read_at_is_set(self) -> None:
        from django.utils import timezone
        n = Notification.objects.create(user=self.user, title='Test', read_at=timezone.now())
        self.assertTrue(n.is_read)

    def test_str_returns_title(self) -> None:
        n = Notification.objects.create(user=self.user, title='My Notification')
        self.assertEqual(str(n), 'My Notification')

    def test_ordering_newest_first(self) -> None:
        n1 = Notification.objects.create(user=self.user, title='First')
        n2 = Notification.objects.create(user=self.user, title='Second')
        notifications: list[Notification] = list(Notification.objects.filter(user=self.user))
        self.assertEqual(notifications[0].pk, n2.pk)
        self.assertEqual(notifications[1].pk, n1.pk)
