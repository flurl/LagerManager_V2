import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

from core.models import Location, Period
from django.test import TestCase
from django.utils import timezone
from inventory.models import InitialInventory, PhysicalCount
from pos_import.models import Article, ArticleGroup

from reports.services.stock_level_report import (
    _build_initial_inventory_map,
    _build_last_physical_count_map,
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


class BuildLastPhysicalCountMapTest(TestCase):
    def setUp(self) -> None:
        self.period = Period.objects.create(
            name="Test", start=timezone.now(), end=timezone.now()
        )
        group = ArticleGroup.objects.create(
            source_id=3, name="Drinks", is_revenue=True, show_on_receipt=True,
            print_recipe=False, no_cancellation=False, period=self.period, standard_course=1,
        )
        self.article = Article.objects.create(
            source_id=303, name="Schnaps", group=group, period=self.period,
            price_popup=False, ep_price_popup=False, rksv=False, external_receipt=False,
        )

    def test_returns_most_recent_count(self) -> None:
        PhysicalCount.objects.create(
            article=self.article, period=self.period, quantity=Decimal("10.000"),
            date=datetime.datetime(2024, 1, 1, tzinfo=timezone.get_current_timezone()),
        )
        PhysicalCount.objects.create(
            article=self.article, period=self.period, quantity=Decimal("7.500"),
            date=datetime.datetime(2024, 1, 5, tzinfo=timezone.get_current_timezone()),
        )
        result = _build_last_physical_count_map(self.period.pk)
        quantity, date_iso = result["Schnaps"]
        self.assertAlmostEqual(quantity, 7.5)
        self.assertEqual(date_iso, "2024-01-05")

    def test_returns_none_for_article_without_count(self) -> None:
        result = _build_last_physical_count_map(self.period.pk)
        self.assertNotIn("Schnaps", result)

    def test_ignores_other_period(self) -> None:
        other_period = Period.objects.create(
            name="Other", start=timezone.now(), end=timezone.now()
        )
        PhysicalCount.objects.create(
            article=self.article, period=other_period, quantity=Decimal("99.000"),
            date=datetime.datetime(2024, 1, 1, tzinfo=timezone.get_current_timezone()),
        )
        result = _build_last_physical_count_map(self.period.pk)
        self.assertNotIn("Schnaps", result)


class GetCurrentStockLevelsLastPhysicalCountTest(TestCase):
    def setUp(self) -> None:
        self.period = Period.objects.create(
            name="Test", start=timezone.now(), end=timezone.now()
        )
        group = ArticleGroup.objects.create(
            source_id=4, name="Drinks", is_revenue=True, show_on_receipt=True,
            print_recipe=False, no_cancellation=False, period=self.period, standard_course=1,
        )
        self.article = Article.objects.create(
            source_id=404, name="Bier", group=group, period=self.period,
            price_popup=False, ep_price_popup=False, rksv=False, external_receipt=False,
        )
        PhysicalCount.objects.create(
            article=self.article, period=self.period, quantity=Decimal("8.000"),
            date=datetime.datetime(2024, 1, 10, tzinfo=timezone.get_current_timezone()),
        )

    @patch("reports.services.article_enrichment.enrich_with_article_data")
    @patch("reports.services.stock_level_report.get_stock_level_chart_data")
    def test_last_physical_count_and_stock_minus_count_added(
        self, mock_chart: MagicMock, mock_enrich: MagicMock
    ) -> None:
        mock_chart.return_value = {
            "labels": ["2024-01-10"],
            "datasets": [{"label": "Bier", "data": [12.0]}],
        }
        mock_enrich.return_value = [
            {
                "article": "Bier",
                "stock": 12.0,
                "purchase_price": None,
                "total_value": None,
                "warehouse_unit": None,
                "warehouse_unit_multiplier": None,
            }
        ]

        rows = get_current_stock_levels(self.period.pk)
        row = rows[0]
        self.assertAlmostEqual(row["last_physical_count"], 8.0)
        self.assertEqual(row["last_physical_count_date"], "2024-01-10")
        self.assertAlmostEqual(row["stock_minus_count"], 4.0)

    @patch("reports.services.article_enrichment.enrich_with_article_data")
    @patch("reports.services.stock_level_report.get_stock_level_chart_data")
    def test_article_without_count_gets_none(
        self, mock_chart: MagicMock, mock_enrich: MagicMock
    ) -> None:
        mock_chart.return_value = {
            "labels": ["2024-01-10"],
            "datasets": [{"label": "Wasser", "data": [3.0]}],
        }
        mock_enrich.return_value = [
            {
                "article": "Wasser",
                "stock": 3.0,
                "purchase_price": None,
                "total_value": None,
                "warehouse_unit": None,
                "warehouse_unit_multiplier": None,
            }
        ]

        rows = get_current_stock_levels(self.period.pk)
        row = rows[0]
        self.assertIsNone(row["last_physical_count"])
        self.assertIsNone(row["last_physical_count_date"])
        self.assertIsNone(row["stock_minus_count"])
