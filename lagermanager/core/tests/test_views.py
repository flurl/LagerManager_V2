from datetime import datetime, timezone

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from core.models import Period


class PeriodByDateViewTest(APITestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username='tester', password='pass')
        self.client.force_authenticate(user=self.user)

        self.period = Period.objects.create(
            name='Q1 2024',
            start=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end=datetime(2024, 3, 31, 23, 59, 59, tzinfo=timezone.utc),
        )

    def test_returns_period_for_date_within_range(self) -> None:
        resp = self.client.get('/api/periods/by-date/', {'date': '2024-02-15'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['id'], self.period.pk)
        self.assertEqual(resp.data['name'], 'Q1 2024')

    def test_returns_period_for_start_date(self) -> None:
        resp = self.client.get('/api/periods/by-date/', {'date': '2024-01-01'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['id'], self.period.pk)

    def test_returns_period_for_end_date(self) -> None:
        resp = self.client.get('/api/periods/by-date/', {'date': '2024-03-31'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['id'], self.period.pk)

    def test_404_when_no_period_for_date(self) -> None:
        resp = self.client.get('/api/periods/by-date/', {'date': '2025-06-01'})
        self.assertEqual(resp.status_code, 404)

    def test_400_when_date_missing(self) -> None:
        resp = self.client.get('/api/periods/by-date/')
        self.assertEqual(resp.status_code, 400)

    def test_401_when_unauthenticated(self) -> None:
        self.client.force_authenticate(user=None)
        resp = self.client.get('/api/periods/by-date/', {'date': '2024-02-15'})
        self.assertEqual(resp.status_code, 401)

    def test_returns_most_recent_when_periods_overlap(self) -> None:
        later_period = Period.objects.create(
            name='Overlap',
            start=datetime(2024, 2, 1, tzinfo=timezone.utc),
            end=datetime(2024, 4, 30, tzinfo=timezone.utc),
        )
        resp = self.client.get('/api/periods/by-date/', {'date': '2024-02-15'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['id'], later_period.pk)
