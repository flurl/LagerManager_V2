from datetime import datetime, timezone
from decimal import Decimal

from core.models import Location, Period
from django.contrib.auth.models import User
from pos_import.models import Article, ArticleGroup
from rest_framework.test import APITestCase

from inventory.models import PhysicalCount


class PhysicalCountViewTestCase(APITestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_superuser(username='tester', password='pass')
        self.client.force_authenticate(user=self.user)

        self.period = Period.objects.create(
            name='Test 2024',
            start=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end=datetime(2024, 12, 31, tzinfo=timezone.utc),
        )
        self.location = Location.objects.create(name='Bar')
        self.group = ArticleGroup.objects.create(
            source_id=1, name='Getränke', standard_course=1,
            is_revenue=True, show_on_receipt=True,
            print_recipe=False, no_cancellation=False,
            period=self.period,
        )
        self.article = Article.objects.create(
            source_id=101, name='Bier',
            group=self.group, period=self.period,
            price_popup=False, ep_price_popup=False,
            rksv=False, external_receipt=False,
        )
        self.article2 = Article.objects.create(
            source_id=102, name='Cola',
            group=self.group, period=self.period,
            price_popup=False, ep_price_popup=False,
            rksv=False, external_receipt=False,
        )

    def _make_count(self, article: Article, date: datetime, quantity: Decimal = Decimal('5')) -> PhysicalCount:
        return PhysicalCount.objects.create(
            article=article, date=date, quantity=quantity, period=self.period,
        )

    def test_dates_groups_by_day(self) -> None:
        day1 = datetime(2024, 6, 15, 10, 0, tzinfo=timezone.utc)
        day2 = datetime(2024, 6, 16, 10, 0, tzinfo=timezone.utc)
        self._make_count(self.article, day1)
        self._make_count(self.article2, day1)
        self._make_count(self.article, day2)

        resp = self.client.get('/api/physical-counts/dates/', {'period_id': self.period.pk})
        self.assertEqual(resp.status_code, 200)
        rows = resp.data
        self.assertEqual(len(rows), 2)
        self.assertEqual(str(rows[0]['day']), '2024-06-16')
        self.assertEqual(rows[0]['count'], 1)
        self.assertEqual(str(rows[1]['day']), '2024-06-15')
        self.assertEqual(rows[1]['count'], 2)

    def test_dates_filters_by_period(self) -> None:
        other_period = Period.objects.create(
            name='Other 2023',
            start=datetime(2023, 1, 1, tzinfo=timezone.utc),
            end=datetime(2023, 12, 31, tzinfo=timezone.utc),
        )
        day = datetime(2024, 6, 15, 10, 0, tzinfo=timezone.utc)
        self._make_count(self.article, day)
        PhysicalCount.objects.create(
            article=self.article, date=datetime(2023, 3, 1, tzinfo=timezone.utc),
            quantity=Decimal('3'), period=other_period,
        )

        resp = self.client.get('/api/physical-counts/dates/', {'period_id': self.period.pk})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(str(resp.data[0]['day']), '2024-06-15')

    def test_dates_requires_auth(self) -> None:
        self.client.force_authenticate(user=None)
        resp = self.client.get('/api/physical-counts/dates/')
        self.assertEqual(resp.status_code, 401)

    def test_by_day_delete_removes_entries_for_day_and_period(self) -> None:
        day = datetime(2024, 6, 15, 10, 0, tzinfo=timezone.utc)
        self._make_count(self.article, day)
        self._make_count(self.article2, day)
        self._make_count(self.article, datetime(2024, 6, 16, 10, 0, tzinfo=timezone.utc))
        resp = self.client.delete(
            f'/api/physical-counts/by-day/?day=2024-06-15&period_id={self.period.pk}',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['deleted'], 2)
        self.assertEqual(PhysicalCount.objects.count(), 1)

    def test_by_day_delete_requires_day_and_period(self) -> None:
        resp = self.client.delete('/api/physical-counts/by-day/?day=2024-06-15')
        self.assertEqual(resp.status_code, 400)
        resp = self.client.delete(f'/api/physical-counts/by-day/?period_id={self.period.pk}')
        self.assertEqual(resp.status_code, 400)
