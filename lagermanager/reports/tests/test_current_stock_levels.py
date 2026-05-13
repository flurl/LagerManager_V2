from decimal import Decimal
from unittest.mock import MagicMock, patch

from core.models import Location, Period
from django.test import TestCase
from django.utils import timezone
from inventory.models import InitialInventory
from pos_import.models import Article, ArticleGroup

from reports.services.stock_level_report import (
    _build_initial_inventory_map,
    get_current_stock_levels,
)


class BuildInitialInventoryMapTest(TestCase):
    def setUp(self) -> None:
        self.period = Period.objects.create(
            name="Test", start=timezone.now(), end=timezone.now()
        )
        self.loc1 = Location.objects.create(name="Bar")
        self.loc2 = Location.objects.create(name="Keller")
        group = ArticleGroup.objects.create(
            source_id=1, name="Drinks", is_revenue=True, show_on_receipt=True,
            print_recipe=False, no_cancellation=False, period=self.period, standard_course=1,
        )
        self.article = Article.objects.create(
            source_id=101, name="Bier", group=group, period=self.period,
            price_popup=False, ep_price_popup=False, rksv=False, external_receipt=False,
        )

    def test_sums_across_locations(self) -> None:
        InitialInventory.objects.create(
            article=self.article, location=self.loc1, period=self.period, quantity=Decimal(
                "10.000")
        )
        InitialInventory.objects.create(
            article=self.article, location=self.loc2, period=self.period, quantity=Decimal(
                "5.500")
        )
        result = _build_initial_inventory_map(self.period.pk)
        self.assertAlmostEqual(result["Bier"], 15.5)

    def test_empty_returns_empty_dict(self) -> None:
        result = _build_initial_inventory_map(self.period.pk)
        self.assertEqual(result, {})

    def test_ignores_other_period(self) -> None:
        other_period = Period.objects.create(
            name="Other", start=timezone.now(), end=timezone.now()
        )
        InitialInventory.objects.create(
            article=self.article, location=self.loc1, period=other_period, quantity=Decimal(
                "99.000")
        )
        result = _build_initial_inventory_map(self.period.pk)
        self.assertEqual(result, {})


class GetCurrentStockLevelsInitialInventoryTest(TestCase):
    def setUp(self) -> None:
        self.period = Period.objects.create(
            name="Test", start=timezone.now(), end=timezone.now()
        )
        self.loc = Location.objects.create(name="Bar")
        group = ArticleGroup.objects.create(
            source_id=2, name="Drinks", is_revenue=True, show_on_receipt=True,
            print_recipe=False, no_cancellation=False, period=self.period, standard_course=1,
        )
        self.article = Article.objects.create(
            source_id=202, name="Wein", group=group, period=self.period,
            price_popup=False, ep_price_popup=False, rksv=False, external_receipt=False,
        )
        InitialInventory.objects.create(
            article=self.article, location=self.loc, period=self.period, quantity=Decimal(
                "20.000")
        )

    @patch("reports.services.article_enrichment.enrich_with_article_data")
    @patch("reports.services.stock_level_report.get_stock_level_chart_data")
    def test_initial_inventory_and_stock_minus_initial_added(
        self, mock_chart: MagicMock, mock_enrich: MagicMock
    ) -> None:
        mock_chart.return_value = {
            "labels": ["2024-01-01"],
            "datasets": [{"label": "Wein", "data": [12.0]}],
        }
        mock_enrich_instance = MagicMock()
        mock_enrich_instance.return_value = [
            {
                "article": "Wein",
                "stock": 12.0,
                "purchase_price": None,
                "total_value": None,
                "warehouse_unit": None,
                "warehouse_unit_multiplier": None,
            }
        ]
        mock_enrich.return_value = mock_enrich_instance.return_value

        rows = get_current_stock_levels(self.period.pk)

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertAlmostEqual(row["initial_inventory"], 20.0)
        self.assertAlmostEqual(row["stock_minus_initial"], -8.0)

    @patch("reports.services.article_enrichment.enrich_with_article_data")
    @patch("reports.services.stock_level_report.get_stock_level_chart_data")
    def test_article_without_initial_inventory_defaults_to_zero(
        self, mock_chart: MagicMock, mock_enrich: MagicMock
    ) -> None:
        mock_chart.return_value = {
            "labels": ["2024-01-01"],
            "datasets": [{"label": "Saft", "data": [5.0]}],
        }
        mock_enrich.return_value = [
            {
                "article": "Saft",
                "stock": 5.0,
                "purchase_price": None,
                "total_value": None,
                "warehouse_unit": None,
                "warehouse_unit_multiplier": None,
            }
        ]

        rows = get_current_stock_levels(self.period.pk)
        row = rows[0]
        self.assertAlmostEqual(row["initial_inventory"], 0.0)
        self.assertAlmostEqual(row["stock_minus_initial"], 5.0)
