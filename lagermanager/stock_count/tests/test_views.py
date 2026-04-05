from datetime import datetime, timezone
from typing import Any

from core.models import Location, Period
from django.contrib.auth.models import User
from pos_import.models import (
    Article,
    ArticleGroup,
    ArticleMeta,
    WarehouseArticle,
    WarehouseUnit,
)
from rest_framework.test import APITestCase

from stock_count.models import StockCountEntry


class StockCountTestCase(APITestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username='tester', password='pass')
        self.client.force_authenticate(user=self.user)

        self.period = Period.objects.create(
            name='Test 2024',
            start=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end=datetime(2024, 12, 31, tzinfo=timezone.utc),
        )
        self.location = Location.objects.create(name='Bar')
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
        self.unit = WarehouseUnit.objects.create(
            source_id=1,
            name='Stk',
            multiplier=1,
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
        self.article_hidden = Article.objects.create(
            source_id=103, name='Versteckt',
            group=self.group, price_popup=False, ep_price_popup=False,
            rksv=False, external_receipt=False, period=self.period,
        )
        for article in [self.article_beer, self.article_cola, self.article_hidden]:
            WarehouseArticle.objects.create(
                source_id=article.source_id,
                article=article,
                source_article_id=article.source_id,
                supplier_source_id=1,
                priority=0,
                unit=self.unit,
                source_unit_id=1,
                flags=0,
                max_stock=100,
                min_stock=0,
                period=self.period,
            )
        ArticleMeta.objects.create(
            source_id=102, period=self.period, sub_articles='lemon,orange',
        )
        ArticleMeta.objects.create(
            source_id=103, period=self.period, is_hidden=True,
        )
        self.count_date = datetime(2024, 6, 15, 10, 0, 0, tzinfo=timezone.utc)

    def test_expanded_articles_basic(self) -> None:
        resp = self.client.get('/api/stock-count/articles/', {'period_id': self.period.pk})
        self.assertEqual(resp.status_code, 200)
        ids = {r['article_id'] for r in resp.data}
        self.assertIn('101', ids)           # Bier
        self.assertIn('102', ids)           # Cola
        self.assertIn('102-lemon', ids)     # Cola-lemon
        self.assertIn('102-orange', ids)    # Cola-orange
        self.assertEqual(len(resp.data), 4)

    def test_hidden_article_excluded(self) -> None:
        resp = self.client.get('/api/stock-count/articles/', {'period_id': self.period.pk})
        self.assertEqual(resp.status_code, 200)
        ids = {r['article_id'] for r in resp.data}
        self.assertNotIn('103', ids)

    def test_sub_article_names(self) -> None:
        resp = self.client.get('/api/stock-count/articles/', {'period_id': self.period.pk})
        name_by_id = {r['article_id']: r['article_name'] for r in resp.data}
        self.assertEqual(name_by_id['102-lemon'], 'Cola-lemon')
        self.assertEqual(name_by_id['102-orange'], 'Cola-orange')

    def test_include_base_false_omits_base_article(self) -> None:
        resp = self.client.get('/api/stock-count/articles/', {
            'period_id': self.period.pk,
            'include_base': 'false',
        })
        self.assertEqual(resp.status_code, 200)
        ids = {r['article_id'] for r in resp.data}
        # Cola has sub-articles — base row must be absent
        self.assertNotIn('102', ids)
        self.assertIn('102-lemon', ids)
        self.assertIn('102-orange', ids)
        # Bier has no sub-articles — still present
        self.assertIn('101', ids)

    def test_articles_requires_period_id(self) -> None:
        resp = self.client.get('/api/stock-count/articles/')
        self.assertEqual(resp.status_code, 400)

    def test_bulk_save_creates_entries(self) -> None:
        payload = {
            'period_id': self.period.pk,
            'location_id': self.location.pk,
            'location_name': self.location.name,
            'count_date': self.count_date.isoformat(),
            'entries': [
                {'article_id': '101', 'article_name': 'Bier', 'quantity': '5.000'},
                {'article_id': '102-lemon', 'article_name': 'Cola-lemon', 'quantity': '3.000'},
            ],
        }
        resp = self.client.post('/api/stock-count/entries/bulk/', payload, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['saved'], 2)
        self.assertEqual(StockCountEntry.objects.count(), 2)

    def test_bulk_save_upsert(self) -> None:
        payload: dict[str, Any] = {
            'period_id': self.period.pk,
            'location_id': self.location.pk,
            'location_name': self.location.name,
            'count_date': self.count_date.isoformat(),
            'entries': [
                {'article_id': '101', 'article_name': 'Bier', 'quantity': '5.000'},
            ],
        }
        self.client.post('/api/stock-count/entries/bulk/', payload, format='json')
        payload['entries'][0]['quantity'] = '10.000'
        self.client.post('/api/stock-count/entries/bulk/', payload, format='json')
        self.assertEqual(StockCountEntry.objects.count(), 1)
        entry = StockCountEntry.objects.get(article_id='101')
        self.assertEqual(float(entry.quantity), 10.0)

    def test_get_entries_filtered(self) -> None:
        StockCountEntry.objects.create(
            count_date=self.count_date,
            article_id='101', article_name='Bier',
            location_id=self.location.pk, location_name=self.location.name,
            quantity=5, period_id_value=self.period.pk,
        )
        StockCountEntry.objects.create(
            count_date=self.count_date,
            article_id='102', article_name='Cola',
            location_id=999, location_name='Other',
            quantity=2, period_id_value=self.period.pk,
        )
        resp = self.client.get('/api/stock-count/entries/', {
            'period_id': self.period.pk,
            'location_id': self.location.pk,
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]['article_id'], '101')

    def test_bulk_save_empty_entries(self) -> None:
        payload = {
            'period_id': self.period.pk,
            'location_id': self.location.pk,
            'location_name': self.location.name,
            'count_date': self.count_date.isoformat(),
            'entries': [],
        }
        resp = self.client.post('/api/stock-count/entries/bulk/', payload, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['saved'], 0)
        self.assertEqual(StockCountEntry.objects.count(), 0)

    def test_auth_required(self) -> None:
        self.client.force_authenticate(user=None)
        resp = self.client.get('/api/stock-count/articles/', {'period_id': self.period.pk})
        self.assertEqual(resp.status_code, 401)
