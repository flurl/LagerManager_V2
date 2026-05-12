from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APITestCase

from notifications.models import Notification
from notifications.services.dispatcher import notify


class NotificationViewSetTest(APITestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username='owner', password='pass')
        self.other = User.objects.create_user(username='other', password='pass')
        self.client.force_authenticate(user=self.user)
        self.n1: Notification = notify(user=self.user, title='First', severity=Notification.Severity.INFO)
        self.n2: Notification = notify(user=self.user, title='Second', severity=Notification.Severity.WARNING)

    def test_list_returns_only_own_notifications(self) -> None:
        notify(user=self.other, title='Other user notif')
        resp = self.client.get('/api/notifications/')
        self.assertEqual(resp.status_code, 200)
        ids: list[int] = [r['id'] for r in resp.data['results']]
        self.assertIn(self.n1.pk, ids)
        self.assertIn(self.n2.pk, ids)
        self.assertEqual(len(ids), 2)

    def test_list_unread_filter(self) -> None:
        self.n1.read_at = timezone.now()
        self.n1.save()
        resp = self.client.get('/api/notifications/', {'unread': 'true'})
        self.assertEqual(resp.status_code, 200)
        ids: list[int] = [r['id'] for r in resp.data['results']]
        self.assertNotIn(self.n1.pk, ids)
        self.assertIn(self.n2.pk, ids)

    def test_retrieve_own_notification(self) -> None:
        resp = self.client.get(f'/api/notifications/{self.n1.pk}/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['id'], self.n1.pk)

    def test_retrieve_other_user_notification_returns_404(self) -> None:
        other_n: Notification = notify(user=self.other, title='Other')
        resp = self.client.get(f'/api/notifications/{other_n.pk}/')
        self.assertEqual(resp.status_code, 404)

    def test_delete_own_notification(self) -> None:
        resp = self.client.delete(f'/api/notifications/{self.n1.pk}/')
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(Notification.objects.filter(pk=self.n1.pk).exists())

    def test_delete_other_user_notification_returns_404(self) -> None:
        other_n: Notification = notify(user=self.other, title='Other')
        resp = self.client.delete(f'/api/notifications/{other_n.pk}/')
        self.assertEqual(resp.status_code, 404)
        self.assertTrue(Notification.objects.filter(pk=other_n.pk).exists())

    def test_create_is_not_allowed(self) -> None:
        resp = self.client.post('/api/notifications/', {'title': 'Hack'})
        self.assertEqual(resp.status_code, 405)

    def test_mark_read_sets_read_at(self) -> None:
        resp = self.client.post(f'/api/notifications/{self.n1.pk}/mark-read/')
        self.assertEqual(resp.status_code, 200)
        self.n1.refresh_from_db()
        self.assertIsNotNone(self.n1.read_at)
        self.assertTrue(resp.data['is_read'])

    def test_mark_read_is_idempotent(self) -> None:
        self.client.post(f'/api/notifications/{self.n1.pk}/mark-read/')
        self.n1.refresh_from_db()
        first_read_at = self.n1.read_at
        self.client.post(f'/api/notifications/{self.n1.pk}/mark-read/')
        self.n1.refresh_from_db()
        self.assertEqual(self.n1.read_at, first_read_at)

    def test_mark_all_read_updates_all_unread(self) -> None:
        resp = self.client.post('/api/notifications/mark-all-read/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['updated'], 2)
        self.n1.refresh_from_db()
        self.n2.refresh_from_db()
        self.assertIsNotNone(self.n1.read_at)
        self.assertIsNotNone(self.n2.read_at)

    def test_mark_all_read_skips_already_read(self) -> None:
        self.n1.read_at = timezone.now()
        self.n1.save()
        resp = self.client.post('/api/notifications/mark-all-read/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['updated'], 1)

    def test_mark_all_read_does_not_touch_other_users(self) -> None:
        other_n: Notification = notify(user=self.other, title='Other')
        self.client.post('/api/notifications/mark-all-read/')
        other_n.refresh_from_db()
        self.assertIsNone(other_n.read_at)

    def test_unread_count(self) -> None:
        resp = self.client.get('/api/notifications/unread-count/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['count'], 2)

    def test_unread_count_decrements_after_read(self) -> None:
        self.n1.read_at = timezone.now()
        self.n1.save()
        resp = self.client.get('/api/notifications/unread-count/')
        self.assertEqual(resp.data['count'], 1)

    def test_unauthenticated_returns_401(self) -> None:
        self.client.force_authenticate(user=None)
        resp = self.client.get('/api/notifications/')
        self.assertEqual(resp.status_code, 401)
