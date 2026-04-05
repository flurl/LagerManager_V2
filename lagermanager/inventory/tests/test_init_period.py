import datetime as dt
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from core.models import Location, Period
from inventory.models import InitialInventory, PhysicalCount, PeriodStartStockLevel
from inventory.services.init_period import (
    init_initial_inventory,
    init_physical_count_date,
    init_stock_levels,
)
from pos_import.models import Article, ArticleGroup, WarehouseArticle


class InitPeriodFixtureMixin:
    """Shared fixtures for init_period service tests."""

    period: Period
    article_group: ArticleGroup
    article_a: Article
    article_b: Article

    def _create_base_fixtures(self) -> None:
        self.period = Period.objects.create(
            name="Init Period",
            start=timezone.now() - dt.timedelta(days=10),
            end=timezone.now() + dt.timedelta(days=10),
        )
        self.article_group = ArticleGroup.objects.create(
            source_id=1, name="Drinks", is_revenue=True,
            show_on_receipt=True, print_recipe=False,
            no_cancellation=False, period=self.period,
            standard_course=1,
        )
        self.article_a = Article.objects.create(
            source_id=101, name="Beer", group=self.article_group, period=self.period,
            price_popup=False, ep_price_popup=False, rksv=False, external_receipt=False,
        )
        self.article_b = Article.objects.create(
            source_id=102, name="Wine", group=self.article_group, period=self.period,
            price_popup=False, ep_price_popup=False, rksv=False, external_receipt=False,
        )

    def _make_warehouse_article(self, article: Article) -> WarehouseArticle:
        return WarehouseArticle.objects.create(
            source_id=article.source_id,
            supplier_source_id=0,
            article=article,
            source_article_id=article.source_id,
            priority=1,
            source_unit_id=0,
            flags=0,
            max_stock=Decimal("999.000"),
            min_stock=Decimal("0.000"),
            period=self.period,
        )


class InitStockLevelsTests(InitPeriodFixtureMixin, TestCase):
    """Tests for init_stock_levels()."""

    def setUp(self) -> None:
        self._create_base_fixtures()
        self._make_warehouse_article(self.article_a)
        self._make_warehouse_article(self.article_b)

    def test_creates_entries_for_all_warehouse_articles(self) -> None:
        """Creates one zero-quantity entry per warehouse article."""
        count = init_stock_levels(self.period.pk)
        self.assertEqual(count, 2)
        entries = PeriodStartStockLevel.objects.filter(period=self.period)
        self.assertEqual(entries.count(), 2)
        self.assertTrue(all(e.quantity == Decimal("0") for e in entries))

    def test_idempotent_second_call_creates_nothing(self) -> None:
        """Calling twice does not duplicate entries."""
        init_stock_levels(self.period.pk)
        count2 = init_stock_levels(self.period.pk)
        self.assertEqual(count2, 0)
        self.assertEqual(PeriodStartStockLevel.objects.filter(period=self.period).count(), 2)

    def test_skips_existing_entries(self) -> None:
        """Pre-existing entries are not recreated; only the missing one is created."""
        PeriodStartStockLevel.objects.create(
            article=self.article_a, period=self.period, quantity=Decimal("50.000")
        )
        count = init_stock_levels(self.period.pk)
        # Only article_b is missing
        self.assertEqual(count, 1)
        # article_a's quantity is unchanged (not overwritten to 0)
        sl_a = PeriodStartStockLevel.objects.get(article=self.article_a, period=self.period)
        self.assertEqual(sl_a.quantity, Decimal("50.000"))

    def test_nonexistent_period_raises(self) -> None:
        """Bogus period_id raises Period.DoesNotExist."""
        with self.assertRaises(Period.DoesNotExist):
            init_stock_levels(999999)


class InitInitialInventoryTests(InitPeriodFixtureMixin, TestCase):
    """Tests for init_initial_inventory()."""

    location_a: Location
    location_b: Location

    def setUp(self) -> None:
        self._create_base_fixtures()
        self._make_warehouse_article(self.article_a)
        self._make_warehouse_article(self.article_b)
        self.location_a = Location.objects.create(name="Bar A")
        self.location_b = Location.objects.create(name="Bar B")

    def test_creates_all_article_location_combos(self) -> None:
        """2 articles x 2 locations = 4 entries, all zero."""
        count = init_initial_inventory(self.period.pk)
        self.assertEqual(count, 4)
        entries = InitialInventory.objects.filter(period=self.period)
        self.assertEqual(entries.count(), 4)
        self.assertTrue(all(e.quantity == Decimal("0") for e in entries))

    def test_copies_quantities_from_source_period(self) -> None:
        """Quantities are copied from the source period when provided."""
        source_period = Period.objects.create(
            name="Source Period",
            start=timezone.now() - dt.timedelta(days=40),
            end=timezone.now() - dt.timedelta(days=10),
        )
        # Create matching warehouse articles and initial inventories in source period
        src_group = ArticleGroup.objects.create(
            source_id=1, name="Drinks", is_revenue=True,
            show_on_receipt=True, print_recipe=False,
            no_cancellation=False, period=source_period,
            standard_course=1,
        )
        src_article_a = Article.objects.create(
            source_id=101, name="Beer", group=src_group, period=source_period,
            price_popup=False, ep_price_popup=False, rksv=False, external_receipt=False,
        )
        WarehouseArticle.objects.create(
            source_id=101, supplier_source_id=0, article=src_article_a,
            source_article_id=101, priority=1, source_unit_id=0, flags=0,
            max_stock=Decimal("999.000"), min_stock=Decimal("0.000"), period=source_period,
        )
        InitialInventory.objects.create(
            article=src_article_a, location=self.location_a,
            quantity=Decimal("42.000"), period=source_period,
        )

        init_initial_inventory(self.period.pk, source_period_id=source_period.pk)

        entry = InitialInventory.objects.get(
            article=self.article_a, location=self.location_a, period=self.period
        )
        self.assertEqual(entry.quantity, Decimal("42.000"))

    def test_idempotent_second_call_creates_nothing(self) -> None:
        """Second call creates no new entries."""
        init_initial_inventory(self.period.pk)
        count2 = init_initial_inventory(self.period.pk)
        self.assertEqual(count2, 0)
        self.assertEqual(InitialInventory.objects.filter(period=self.period).count(), 4)

    def test_no_locations_creates_nothing(self) -> None:
        """When there are no locations, no entries are created."""
        Location.objects.all().delete()
        count = init_initial_inventory(self.period.pk)
        self.assertEqual(count, 0)
        self.assertEqual(InitialInventory.objects.filter(period=self.period).count(), 0)


class InitPhysicalCountDateTests(InitPeriodFixtureMixin, TestCase):
    """Tests for init_physical_count_date()."""

    def setUp(self) -> None:
        self._create_base_fixtures()
        self._make_warehouse_article(self.article_a)
        self._make_warehouse_article(self.article_b)

    def test_creates_entries_for_count_date(self) -> None:
        """Creates one zero-quantity entry per warehouse article for the given date."""
        count_dt = timezone.now().replace(hour=12, minute=0, second=0, microsecond=0)
        count = init_physical_count_date(self.period.pk, count_dt)
        self.assertEqual(count, 2)
        entries = PhysicalCount.objects.filter(period=self.period)
        self.assertEqual(entries.count(), 2)
        self.assertTrue(all(e.quantity == Decimal("0") for e in entries))

    def test_idempotent_same_date(self) -> None:
        """Calling twice for the same date does not create duplicates."""
        count_dt = timezone.now().replace(hour=12, minute=0, second=0, microsecond=0)
        init_physical_count_date(self.period.pk, count_dt)
        count2 = init_physical_count_date(self.period.pk, count_dt)
        self.assertEqual(count2, 0)
        self.assertEqual(PhysicalCount.objects.filter(period=self.period).count(), 2)

    def test_different_dates_create_separate_entries(self) -> None:
        """Each unique date gets its own set of entries."""
        now = timezone.now().replace(hour=12, minute=0, second=0, microsecond=0)
        count1 = init_physical_count_date(self.period.pk, now)
        count2 = init_physical_count_date(self.period.pk, now + dt.timedelta(days=1))
        self.assertEqual(count1, 2)
        self.assertEqual(count2, 2)
        self.assertEqual(PhysicalCount.objects.filter(period=self.period).count(), 4)
