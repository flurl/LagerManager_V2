from datetime import datetime, timezone
from typing import Any

from core.models import Period
from django.db import IntegrityError
from django.test import TestCase
from pos_import.models import (
    Article,
    ArticleGroup,
    ArticleMeta,
    WarehouseArticle,
    WarehouseUnit,
)

from stock_count.models import StockCountEntry
from stock_count.services import get_expanded_articles


class StockCountEntryModelTest(TestCase):
    def setUp(self) -> None:
        self.count_date = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)

    def _make_entry(self, **kwargs: Any) -> StockCountEntry:
        defaults: dict[str, Any] = {
            'count_date': self.count_date,
            'article_id': '101',
            'article_name': 'Bier',
            'location_id': 1,
            'location_name': 'Bar',
            'quantity': 5,
        }
        defaults.update(kwargs)
        return StockCountEntry.objects.create(**defaults)

    def test_create_entry(self) -> None:
        entry = self._make_entry()
        self.assertIsNotNone(entry.pk)
        self.assertEqual(entry.article_id, '101')
        self.assertEqual(entry.article_name, 'Bier')
        self.assertEqual(entry.location_id, 1)
        self.assertEqual(entry.location_name, 'Bar')
        self.assertEqual(float(entry.quantity), 5.0)
        self.assertEqual(entry.count_date, self.count_date)

    def test_created_at_auto_set(self) -> None:
        entry = self._make_entry()
        self.assertIsNotNone(entry.created_at)

    def test_str(self) -> None:
        entry = self._make_entry(article_name='Bier', location_name='Bar', quantity=5)
        self.assertIn('Bier', str(entry))
        self.assertIn('Bar', str(entry))
        self.assertIn('2024-06-15', str(entry))
        self.assertIn('5', str(entry))

    def test_unique_together_enforced(self) -> None:
        self._make_entry()
        with self.assertRaises(IntegrityError):
            # Same article_id / location_id / count_date
            self._make_entry()

    def test_unique_together_allows_different_location(self) -> None:
        self._make_entry(location_id=1)
        # Different location_id — must succeed
        entry2 = self._make_entry(location_id=2)
        self.assertIsNotNone(entry2.pk)

    def test_unique_together_allows_different_article(self) -> None:
        self._make_entry(article_id='101')
        entry2 = self._make_entry(article_id='102')
        self.assertIsNotNone(entry2.pk)

    def test_unique_together_allows_different_date(self) -> None:
        self._make_entry(count_date=datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc))
        entry2 = self._make_entry(count_date=datetime(2024, 6, 16, 12, 0, 0, tzinfo=timezone.utc))
        self.assertIsNotNone(entry2.pk)

    def test_sub_article_id_stored_as_string(self) -> None:
        entry = self._make_entry(article_id='101-lemon', article_name='Bier-lemon')
        self.assertEqual(entry.article_id, '101-lemon')
        self.assertEqual(entry.article_name, 'Bier-lemon')


class GetExpandedArticlesServiceTest(TestCase):
    def setUp(self) -> None:
        self.period = Period.objects.create(
            name='2024',
            start=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end=datetime(2024, 12, 31, tzinfo=timezone.utc),
        )
        self.group = ArticleGroup.objects.create(
            source_id=1, name='Getränke', standard_course=1,
            is_revenue=True, show_on_receipt=True, print_recipe=False,
            no_cancellation=False, period=self.period,
        )
        self.unit = WarehouseUnit.objects.create(
            source_id=1, name='Stk', multiplier=1, period=self.period,
        )

    def _make_article(self, source_id: int, name: str) -> Article:
        a = Article.objects.create(
            source_id=source_id, name=name, group=self.group,
            price_popup=False, ep_price_popup=False,
            rksv=False, external_receipt=False, period=self.period,
        )
        WarehouseArticle.objects.create(
            source_id=source_id, article=a, source_article_id=source_id,
            supplier_source_id=1, priority=0, unit=self.unit, source_unit_id=1,
            flags=0, max_stock=100, min_stock=0, period=self.period,
        )
        return a

    def test_article_without_meta_included(self) -> None:
        self._make_article(201, 'Wasser')
        rows = get_expanded_articles(self.period.pk)
        ids = [r['article_id'] for r in rows]
        self.assertIn('201', ids)
        self.assertEqual(len(rows), 1)

    def test_article_with_sub_articles_expanded(self) -> None:
        self._make_article(202, 'Cola')
        ArticleMeta.objects.create(source_id=202, period=self.period, sub_articles='lemon,orange')
        rows = get_expanded_articles(self.period.pk)
        ids = [r['article_id'] for r in rows]
        self.assertIn('202', ids)
        self.assertIn('202-lemon', ids)
        self.assertIn('202-orange', ids)
        self.assertEqual(len(rows), 3)

    def test_include_base_false_omits_base_row(self) -> None:
        self._make_article(202, 'Cola')
        ArticleMeta.objects.create(source_id=202, period=self.period, sub_articles='lemon,orange')
        rows = get_expanded_articles(self.period.pk, include_base=False)
        ids = [r['article_id'] for r in rows]
        self.assertNotIn('202', ids)
        self.assertIn('202-lemon', ids)
        self.assertIn('202-orange', ids)
        self.assertEqual(len(rows), 2)

    def test_include_base_false_keeps_article_without_subs(self) -> None:
        self._make_article(208, 'Wasser')
        rows = get_expanded_articles(self.period.pk, include_base=False)
        ids = [r['article_id'] for r in rows]
        self.assertIn('208', ids)
        self.assertEqual(len(rows), 1)

    def test_article_with_empty_sub_articles_no_expansion(self) -> None:
        self._make_article(203, 'Bier')
        ArticleMeta.objects.create(source_id=203, period=self.period, sub_articles='')
        rows = get_expanded_articles(self.period.pk)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['article_id'], '203')

    def test_sub_articles_whitespace_trimmed(self) -> None:
        self._make_article(204, 'Saft')
        ArticleMeta.objects.create(source_id=204, period=self.period, sub_articles=' apple , mango ')
        rows = get_expanded_articles(self.period.pk)
        ids = [r['article_id'] for r in rows]
        self.assertIn('204-apple', ids)
        self.assertIn('204-mango', ids)

    def test_hidden_article_excluded(self) -> None:
        self._make_article(205, 'Intern')
        ArticleMeta.objects.create(source_id=205, period=self.period, is_hidden=True)
        rows = get_expanded_articles(self.period.pk)
        self.assertEqual(len(rows), 0)

    def test_results_sorted_by_name(self) -> None:
        self._make_article(206, 'Zitronade')
        self._make_article(207, 'Apfelsaft')
        rows = get_expanded_articles(self.period.pk)
        names = [r['article_name'] for r in rows]
        self.assertEqual(names, sorted(names, key=str.lower))

    def test_empty_period_returns_empty_list(self) -> None:
        other_period = Period.objects.create(
            name='Empty', start=datetime(2025, 1, 1, tzinfo=timezone.utc),
            end=datetime(2025, 12, 31, tzinfo=timezone.utc),
        )
        rows = get_expanded_articles(other_period.pk)
        self.assertEqual(rows, [])
