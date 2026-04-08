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
        self.user = User.objects.create_superuser(username='tester', password='pass')
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
            'period_id': str(self.period.pk),
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
            'location_id': self.location.pk,
            'location_name': self.location.name,
            'count_date': self.count_date.isoformat(),
            'entries': [
                {'article_id': '101', 'article_name': 'Bier', 'unit_count': 5},
                {'article_id': '102-lemon', 'article_name': 'Cola-lemon', 'unit_count': 3},
            ],
        }
        resp = self.client.post('/api/stock-count/entries/bulk/', payload, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['saved'], 2)
        self.assertEqual(StockCountEntry.objects.count(), 2)

    def test_bulk_save_upsert(self) -> None:
        payload: dict[str, Any] = {
            'location_id': self.location.pk,
            'location_name': self.location.name,
            'count_date': self.count_date.isoformat(),
            'entries': [
                {'article_id': '101', 'article_name': 'Bier', 'unit_count': 5},
            ],
        }
        self.client.post('/api/stock-count/entries/bulk/', payload, format='json')
        payload['entries'][0]['unit_count'] = 10
        self.client.post('/api/stock-count/entries/bulk/', payload, format='json')
        self.assertEqual(StockCountEntry.objects.count(), 1)
        entry = StockCountEntry.objects.get(article_id='101')
        self.assertEqual(entry.quantity, 10)

    def test_get_entries_filtered(self) -> None:
        StockCountEntry.objects.create(
            count_date=self.count_date,
            article_id='101', article_name='Bier',
            location_id=self.location.pk, location_name=self.location.name,
            unit_count=5,
        )
        StockCountEntry.objects.create(
            count_date=self.count_date,
            article_id='102', article_name='Cola',
            location_id=999, location_name='Other',
            unit_count=2,
        )
        resp = self.client.get('/api/stock-count/entries/', {
            'location_id': self.location.pk,
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]['article_id'], '101')

    def test_bulk_save_empty_entries(self) -> None:
        payload = {
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

    def test_package_size_returned_when_set(self) -> None:
        ArticleMeta.objects.filter(source_id=101, period=self.period).delete()
        ArticleMeta.objects.create(source_id=101, period=self.period, package_size='6.0000')
        resp = self.client.get('/api/stock-count/articles/', {'period_id': self.period.pk})
        self.assertEqual(resp.status_code, 200)
        by_id = {r['article_id']: r for r in resp.data}
        self.assertEqual(float(by_id['101']['package_size']), 6.0)

    def test_package_size_null_when_not_set(self) -> None:
        resp = self.client.get('/api/stock-count/articles/', {'period_id': self.period.pk})
        self.assertEqual(resp.status_code, 200)
        by_id = {r['article_id']: r for r in resp.data}
        # Bier has no ArticleMeta → package_size should be null
        self.assertIsNone(by_id['101']['package_size'])

    def test_package_size_propagated_to_sub_articles(self) -> None:
        ArticleMeta.objects.filter(source_id=102, period=self.period).update(package_size='12.0000')
        resp = self.client.get('/api/stock-count/articles/', {'period_id': self.period.pk})
        self.assertEqual(resp.status_code, 200)
        by_id = {r['article_id']: r for r in resp.data}
        self.assertEqual(float(by_id['102-lemon']['package_size']), 12.0)
        self.assertEqual(float(by_id['102-orange']['package_size']), 12.0)

    # --- StockCountEntry CRUD (ModelViewSet) ---

    def _make_entry(self) -> StockCountEntry:
        return StockCountEntry.objects.create(
            count_date=self.count_date,
            article_id='101',
            article_name='Bier',
            location_id=self.location.pk,
            location_name=self.location.name,
            unit_count=5,
        )

    def test_entry_create(self) -> None:
        payload = {
            'count_date': self.count_date.isoformat(),
            'article_id': '101',
            'article_name': 'Bier',
            'location_id': self.location.pk,
            'location_name': self.location.name,
            'unit_count': 3,
        }
        resp = self.client.post('/api/stock-count/entries/', payload, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(StockCountEntry.objects.count(), 1)
        self.assertEqual(StockCountEntry.objects.get().quantity, 3)

    def test_entry_update(self) -> None:
        entry = self._make_entry()
        payload = {
            'count_date': self.count_date.isoformat(),
            'article_id': '101',
            'article_name': 'Bier',
            'location_id': self.location.pk,
            'location_name': self.location.name,
            'package_count': 2,
            'units_per_package': 6,
            'unit_count': 0,
        }
        resp = self.client.put(f'/api/stock-count/entries/{entry.pk}/', payload, format='json')
        self.assertEqual(resp.status_code, 200)
        entry.refresh_from_db()
        self.assertEqual(entry.quantity, 12)

    def test_entry_partial_update(self) -> None:
        entry = self._make_entry()
        resp = self.client.patch(
            f'/api/stock-count/entries/{entry.pk}/',
            {'unit_count': 7},
            format='json',
        )
        self.assertEqual(resp.status_code, 200)
        entry.refresh_from_db()
        self.assertEqual(entry.quantity, 7)

    def test_entry_delete(self) -> None:
        entry = self._make_entry()
        resp = self.client.delete(f'/api/stock-count/entries/{entry.pk}/')
        self.assertEqual(resp.status_code, 204)
        self.assertEqual(StockCountEntry.objects.count(), 0)

    def test_entry_crud_requires_auth(self) -> None:
        self.client.force_authenticate(user=None)
        resp = self.client.post('/api/stock-count/entries/', {}, format='json')
        self.assertEqual(resp.status_code, 401)

    def test_bulk_save_stores_breakdown(self) -> None:
        payload = {
            'location_id': self.location.pk,
            'location_name': self.location.name,
            'count_date': self.count_date.isoformat(),
            'entries': [
                {
                    'article_id': '101', 'article_name': 'Bier',
                    'package_count': 2, 'units_per_package': 10, 'unit_count': 3,
                },
            ],
        }
        resp = self.client.post('/api/stock-count/entries/bulk/', payload, format='json')
        self.assertEqual(resp.status_code, 200)
        entry = StockCountEntry.objects.get(article_id='101')
        self.assertEqual(entry.package_count, 2)
        self.assertEqual(entry.units_per_package, 10)
        self.assertEqual(entry.unit_count, 3)
        self.assertEqual(entry.quantity, 23)

    def test_bulk_save_defaults_breakdown_to_zero(self) -> None:
        payload = {
            'location_id': self.location.pk,
            'location_name': self.location.name,
            'count_date': self.count_date.isoformat(),
            'entries': [
                {'article_id': '101', 'article_name': 'Bier'},
            ],
        }
        resp = self.client.post('/api/stock-count/entries/bulk/', payload, format='json')
        self.assertEqual(resp.status_code, 200)
        entry = StockCountEntry.objects.get(article_id='101')
        self.assertEqual(entry.package_count, 0)
        self.assertEqual(entry.units_per_package, 0)
        self.assertEqual(entry.unit_count, 0)
        self.assertEqual(entry.quantity, 0)

    def test_bulk_save_upsert_updates_breakdown(self) -> None:
        payload: dict[str, Any] = {
            'location_id': self.location.pk,
            'location_name': self.location.name,
            'count_date': self.count_date.isoformat(),
            'entries': [
                {'article_id': '101', 'article_name': 'Bier', 'package_count': 1, 'units_per_package': 10, 'unit_count': 4},
            ],
        }
        self.client.post('/api/stock-count/entries/bulk/', payload, format='json')
        payload['entries'][0].update({'package_count': 3, 'units_per_package': 10, 'unit_count': 0})
        self.client.post('/api/stock-count/entries/bulk/', payload, format='json')
        self.assertEqual(StockCountEntry.objects.count(), 1)
        entry = StockCountEntry.objects.get(article_id='101')
        self.assertEqual(entry.package_count, 3)
        self.assertEqual(entry.unit_count, 0)
        self.assertEqual(entry.quantity, 30)

    def test_get_entries_returns_breakdown_fields(self) -> None:
        StockCountEntry.objects.create(
            count_date=self.count_date,
            article_id='101', article_name='Bier',
            location_id=self.location.pk, location_name=self.location.name,
            package_count=2, units_per_package=10, unit_count=3,
        )
        resp = self.client.get('/api/stock-count/entries/')
        self.assertEqual(resp.status_code, 200)
        data = resp.data[0]
        self.assertEqual(data['package_count'], 2)
        self.assertEqual(data['units_per_package'], 10)
        self.assertEqual(data['unit_count'], 3)
        self.assertEqual(data['quantity'], 23)

    def test_entry_create_with_breakdown(self) -> None:
        payload = {
            'count_date': self.count_date.isoformat(),
            'article_id': '101',
            'article_name': 'Bier',
            'location_id': self.location.pk,
            'location_name': self.location.name,
            'package_count': 4,
            'units_per_package': 10,
            'unit_count': 1,
        }
        resp = self.client.post('/api/stock-count/entries/', payload, format='json')
        self.assertEqual(resp.status_code, 201)
        entry = StockCountEntry.objects.get()
        self.assertEqual(entry.package_count, 4)
        self.assertEqual(entry.units_per_package, 10)
        self.assertEqual(entry.unit_count, 1)
        self.assertEqual(entry.quantity, 41)
