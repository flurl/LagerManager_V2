from datetime import datetime, timezone

from core.models import Period
from django.contrib.auth.models import User
from inventory.models import PhysicalCount
from pos_import.models import Article, ArticleGroup
from rest_framework.test import APITestCase

from stock_count.models import StockCountEntry


class ImportStockCountTestCase(APITestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username='tester', password='pass')
        self.client.force_authenticate(user=self.user)

        self.period = Period.objects.create(
            name='Test 2024',
            start=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end=datetime(2024, 12, 31, tzinfo=timezone.utc),
        )
        self.group = ArticleGroup.objects.create(
            source_id=1,
            name='Getränke',
            standard_course=1,
            is_revenue=True,
            show_on_receipt=True,
            print_recipe=False,
            no_cancellation=False,
            period=self.period,
        )
        self.article_beer = Article.objects.create(
            source_id=101, name='Bier',
            group=self.group, price_popup=False, ep_price_popup=False,
            rksv=False, external_receipt=False, period=self.period,
        )
        self.article_cola = Article.objects.create(
            source_id=102, name='Cola',
            group=self.group, price_popup=False, ep_price_popup=False,
            rksv=False, external_receipt=False, period=self.period,
        )
        self.count_date = datetime(2024, 6, 15, 10, 0, 0, tzinfo=timezone.utc)

    def _make_entry(self, article_id: str, quantity: int) -> StockCountEntry:
        return StockCountEntry.objects.create(
            count_date=self.count_date,
            article_id=article_id,
            article_name=article_id,
            location_id=1,
            location_name='Bar',
            unit_count=quantity,
        )

    def test_import_single_entry(self) -> None:
        entry = self._make_entry('101', 5)
        resp = self.client.post(
            '/api/stock-count/entries/import/',
            {'entry_ids': [entry.pk]},
            format='json',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['status'], 'ok')
        self.assertEqual(resp.data['created'], 1)
        self.assertEqual(resp.data['updated'], 0)
        count = PhysicalCount.objects.get(article=self.article_beer)
        self.assertEqual(int(count.quantity), 5)
        self.assertEqual(count.period, self.period)

    def test_import_batch_same_count_date(self) -> None:
        entry1 = self._make_entry('101', 5)
        entry2 = self._make_entry('102', 3)
        resp = self.client.post(
            '/api/stock-count/entries/import/',
            {'entry_ids': [entry1.pk, entry2.pk]},
            format='json',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['created'], 2)
        self.assertEqual(PhysicalCount.objects.count(), 2)

    def test_import_sub_article_aggregation(self) -> None:
        entry_lemon = self._make_entry('102-lemon', 3)
        entry_orange = self._make_entry('102-orange', 5)
        resp = self.client.post(
            '/api/stock-count/entries/import/',
            {'entry_ids': [entry_lemon.pk, entry_orange.pk]},
            format='json',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['created'], 1)
        count = PhysicalCount.objects.get(article=self.article_cola)
        self.assertEqual(int(count.quantity), 8)

    def test_import_conflict_returns_409(self) -> None:
        PhysicalCount.objects.create(
            article=self.article_beer,
            date=self.count_date,
            quantity=10,
            period=self.period,
        )
        entry = self._make_entry('101', 5)
        resp = self.client.post(
            '/api/stock-count/entries/import/',
            {'entry_ids': [entry.pk]},
            format='json',
        )
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.data['status'], 'conflict')
        self.assertEqual(resp.data['existing_count'], 1)
        self.assertEqual(resp.data['date'], '2024-06-15')

    def test_import_force_overwrites(self) -> None:
        PhysicalCount.objects.create(
            article=self.article_beer,
            date=self.count_date,
            quantity=10,
            period=self.period,
        )
        entry = self._make_entry('101', 7)
        resp = self.client.post(
            '/api/stock-count/entries/import/',
            {'entry_ids': [entry.pk], 'force': True},
            format='json',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['updated'], 1)
        self.assertEqual(resp.data['created'], 0)
        count = PhysicalCount.objects.get(article=self.article_beer)
        self.assertEqual(int(count.quantity), 7)
        self.assertEqual(PhysicalCount.objects.count(), 1)

    def test_import_missing_article_reported(self) -> None:
        entry = self._make_entry('999', 5)
        resp = self.client.post(
            '/api/stock-count/entries/import/',
            {'entry_ids': [entry.pk]},
            format='json',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(999, resp.data['not_found'])
        self.assertEqual(PhysicalCount.objects.count(), 0)

    def test_import_no_period_returns_400(self) -> None:
        outside_period = StockCountEntry.objects.create(
            count_date=datetime(2020, 1, 1, tzinfo=timezone.utc),
            article_id='101',
            article_name='Bier',
            location_id=1,
            location_name='Bar',
            unit_count=5,
        )
        resp = self.client.post(
            '/api/stock-count/entries/import/',
            {'entry_ids': [outside_period.pk]},
            format='json',
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn('error', resp.data)

    def test_import_requires_auth(self) -> None:
        self.client.force_authenticate(user=None)
        resp = self.client.post(
            '/api/stock-count/entries/import/',
            {'entry_ids': [1]},
            format='json',
        )
        self.assertEqual(resp.status_code, 401)

    def test_import_missing_entry_ids_returns_400(self) -> None:
        resp = self.client.post(
            '/api/stock-count/entries/import/',
            {},
            format='json',
        )
        self.assertEqual(resp.status_code, 400)
