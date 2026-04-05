from datetime import timedelta
from decimal import Decimal
from typing import cast
from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.utils import timezone

from core.models import Period
from deliveries.models import Partner, StockMovement, StockMovementDetail, TaxRate
from inventory.models import PeriodStartStockLevel, PhysicalCount
from inventory.services.stock_calculation import compute_running_stock, get_daily_movements
from pos_import.models import Article, ArticleGroup


class GetDailyMovementsTests(TestCase):
    """Unit tests for get_daily_movements()."""

    period: Period
    partner: Partner
    tax_rate: TaxRate
    article_group: ArticleGroup
    article: Article

    def setUp(self) -> None:
        self.start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        self.end = self.start + timedelta(days=5)
        self.period = Period.objects.create(
            name="Movement Test Period",
            start=self.start,
            end=self.end,
        )
        self.partner = Partner.objects.create(name="Supplier X")
        self.tax_rate = TaxRate.objects.create(
            name="Standard", percent=Decimal("20.00"))
        self.article_group = ArticleGroup.objects.create(
            source_id=1, name="Drinks", is_revenue=True,
            show_on_receipt=True, print_recipe=False,
            no_cancellation=False, period=self.period,
            standard_course=1,
        )
        self.article = Article.objects.create(
            source_id=101, name="Beer", group=self.article_group, period=self.period,
            price_popup=False, ep_price_popup=False, rksv=False, external_receipt=False,
        )

    def _make_movement(
        self,
        movement_type: str = StockMovement.Type.DELIVERY,
        day_offset: int = 1,
    ) -> StockMovement:
        return StockMovement.objects.create(
            partner=self.partner,
            date=self.start.date() + timedelta(days=day_offset),
            movement_type=movement_type,
            period=self.period,
        )

    def _add_detail(
        self, movement: StockMovement, article: Article, quantity: Decimal
    ) -> StockMovementDetail:
        return StockMovementDetail.objects.create(
            stock_movement=movement,
            article=article,
            quantity=quantity,
            unit_price=Decimal("1.0000"),
            tax_rate=self.tax_rate,
        )

    def test_single_delivery(self) -> None:
        """Single delivery returns correct date/article/amount mapping."""
        m = self._make_movement(day_offset=1)
        self._add_detail(m, self.article, Decimal("10.000"))

        result = get_daily_movements(
            self.period.pk, [StockMovement.Type.DELIVERY])
        day = self.start.date() + timedelta(days=1)
        self.assertIn(day, result)
        self.assertAlmostEqual(result[day]["Beer"], 10.0)

    def test_multiple_movements_same_day_sum(self) -> None:
        """Two deliveries of same article on same day are summed."""
        m1 = self._make_movement(day_offset=2)
        m2 = self._make_movement(day_offset=2)
        self._add_detail(m1, self.article, Decimal("7.000"))
        self._add_detail(m2, self.article, Decimal("3.000"))

        result = get_daily_movements(
            self.period.pk, [StockMovement.Type.DELIVERY])
        day = self.start.date() + timedelta(days=2)
        self.assertAlmostEqual(result[day]["Beer"], 10.0)

    def test_filters_by_movement_type(self) -> None:
        """Only the requested movement type is included."""
        delivery = self._make_movement(
            StockMovement.Type.DELIVERY, day_offset=1)
        consumption = self._make_movement(
            StockMovement.Type.CONSUMPTION, day_offset=1)
        self._add_detail(delivery, self.article, Decimal("20.000"))
        self._add_detail(consumption, self.article, Decimal("5.000"))

        deliveries = get_daily_movements(
            self.period.pk, [StockMovement.Type.DELIVERY])
        consumptions = get_daily_movements(
            self.period.pk, [StockMovement.Type.CONSUMPTION])
        day = self.start.date() + timedelta(days=1)
        self.assertAlmostEqual(deliveries[day]["Beer"], 20.0)
        self.assertAlmostEqual(consumptions[day]["Beer"], 5.0)

    def test_empty_period_returns_empty_dict(self) -> None:
        """No movements → empty dict."""
        result = get_daily_movements(
            self.period.pk, [StockMovement.Type.DELIVERY])
        self.assertEqual(result, {})

    def test_multiple_articles_tracked_separately(self) -> None:
        """Different articles on the same day are tracked independently."""
        article2 = Article.objects.create(
            source_id=102, name="Wine", group=self.article_group, period=self.period,
            price_popup=False, ep_price_popup=False, rksv=False, external_receipt=False,
        )
        m = self._make_movement(day_offset=1)
        self._add_detail(m, self.article, Decimal("10.000"))
        self._add_detail(m, article2, Decimal("5.000"))

        result = get_daily_movements(
            self.period.pk, [StockMovement.Type.DELIVERY])
        day = self.start.date() + timedelta(days=1)
        self.assertAlmostEqual(result[day]["Beer"], 10.0)
        self.assertAlmostEqual(result[day]["Wine"], 5.0)


class ComputeRunningStockExtendedTests(TestCase):
    """Extended tests for compute_running_stock()."""

    period: Period
    partner: Partner
    tax_rate: TaxRate
    article_group: ArticleGroup
    article: Article

    def setUp(self) -> None:
        self.start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        self.end = self.start + timedelta(days=2)
        self.period = Period.objects.create(
            name="Running Stock Period",
            start=self.start,
            end=self.end,
        )
        self.partner = Partner.objects.create(name="Supplier Y")
        self.tax_rate = TaxRate.objects.create(
            name="Standard", percent=Decimal("20.00"))
        self.article_group = ArticleGroup.objects.create(
            source_id=1, name="Drinks", is_revenue=True,
            show_on_receipt=True, print_recipe=False,
            no_cancellation=False, period=self.period,
            standard_course=1,
        )
        self.article = Article.objects.create(
            source_id=101, name="Beer", group=self.article_group, period=self.period,
            price_popup=False, ep_price_popup=False, rksv=False, external_receipt=False,
        )

    def _make_delivery(self, article: Article, quantity: Decimal, day_offset: int) -> None:
        m = StockMovement.objects.create(
            partner=self.partner,
            date=self.start.date() + timedelta(days=day_offset),
            movement_type=StockMovement.Type.DELIVERY,
            period=self.period,
        )
        StockMovementDetail.objects.create(
            stock_movement=m, article=article,
            quantity=quantity, unit_price=Decimal("1.0000"), tax_rate=self.tax_rate,
        )

    def _make_consumption(self, article: Article, quantity: Decimal, day_offset: int) -> None:
        m = StockMovement.objects.create(
            partner=self.partner,
            date=self.start.date() + timedelta(days=day_offset),
            movement_type=StockMovement.Type.CONSUMPTION,
            period=self.period,
        )
        StockMovementDetail.objects.create(
            stock_movement=m, article=article,
            quantity=quantity, unit_price=Decimal("1.0000"), tax_rate=self.tax_rate,
        )

    @patch('inventory.services.stock_calculation.get_daily_pos_consumption')
    def test_multiple_articles_simultaneously(self, mock_pos: MagicMock) -> None:
        """Two articles are tracked independently throughout the period."""
        mock_pos.return_value = {}
        article2 = Article.objects.create(
            source_id=102, name="Wine", group=self.article_group, period=self.period,
            price_popup=False, ep_price_popup=False, rksv=False, external_receipt=False,
        )
        PeriodStartStockLevel.objects.create(
            article=self.article, period=self.period, quantity=Decimal(
                "10.000")
        )
        PeriodStartStockLevel.objects.create(
            article=article2, period=self.period, quantity=Decimal("5.000")
        )
        self._make_delivery(self.article, Decimal("10.000"), day_offset=1)
        self._make_delivery(article2, Decimal("20.000"), day_offset=1)

        results = compute_running_stock(self.period.pk)
        beer = [r for r in results if r['article'] == "Beer"]
        wine = [r for r in results if r['article'] == "Wine"]

        # Beer: day0=10, day1=20, day2=20
        self.assertEqual(beer[0]['stock'], 10.0)
        self.assertEqual(beer[1]['stock'], 20.0)
        self.assertEqual(beer[2]['stock'], 20.0)

        # Wine: day0=5, day1=25, day2=25
        self.assertEqual(wine[0]['stock'], 5.0)
        self.assertEqual(wine[1]['stock'], 25.0)
        self.assertEqual(wine[2]['stock'], 25.0)

    @patch('inventory.services.stock_calculation.get_daily_pos_consumption')
    def test_physical_count_diff_calculation(self, mock_pos: MagicMock) -> None:
        """diff = counted - running_stock on the physical count date."""
        mock_pos.return_value = {}
        PeriodStartStockLevel.objects.create(
            article=self.article, period=self.period, quantity=Decimal(
                "10.000")
        )
        self._make_delivery(self.article, Decimal("5.000"), day_offset=1)
        # Running stock on day 1 = 15; physical count = 12 → diff = -3
        PhysicalCount.objects.create(
            date=self.start + timedelta(days=1),
            article=self.article,
            quantity=Decimal("12.000"),
            period=self.period,
        )

        results = compute_running_stock(self.period.pk)
        beer = [r for r in results if r['article'] == "Beer"]
        day1 = beer[1]
        self.assertEqual(day1['stock'], 15.0)
        self.assertEqual(day1['counted'], 12.0)
        self.assertAlmostEqual(cast(float, day1['diff']), -3.0)

    @patch('inventory.services.stock_calculation.get_daily_pos_consumption')
    def test_article_only_in_consumption_goes_negative(self, mock_pos: MagicMock) -> None:
        """Article with no initial stock goes negative when consumed."""
        mock_pos.return_value = {}
        # No PeriodStartStockLevel — article starts at 0
        self._make_consumption(self.article, Decimal("5.000"), day_offset=1)

        results = compute_running_stock(self.period.pk)
        beer = [r for r in results if r['article'] == "Beer"]
        self.assertEqual(beer[0]['stock'], 0.0)   # day 0
        self.assertEqual(beer[1]['stock'], -5.0)  # day 1 after consumption
        self.assertEqual(beer[2]['stock'], -5.0)  # day 2 unchanged

    @patch('inventory.services.stock_calculation.get_daily_pos_consumption')
    def test_empty_period_no_articles_returns_empty_list(self, mock_pos: MagicMock) -> None:
        """Period with no stock levels and no movements returns []."""
        mock_pos.return_value = {}
        results = compute_running_stock(self.period.pk)
        self.assertEqual(results, [])

    @patch('inventory.services.stock_calculation.get_daily_pos_consumption')
    def test_pos_consumption_subtracted(self, mock_pos: MagicMock) -> None:
        """POS consumption (mocked) is subtracted from running stock."""
        day1 = self.start.date() + timedelta(days=1)
        mock_pos.return_value = {day1: {"Beer": 3.0}}

        PeriodStartStockLevel.objects.create(
            article=self.article, period=self.period, quantity=Decimal(
                "10.000")
        )

        results = compute_running_stock(self.period.pk)
        beer = [r for r in results if r['article'] == "Beer"]
        self.assertEqual(beer[0]['stock'], 10.0)   # day 0
        self.assertEqual(beer[1]['stock'], 7.0)    # day 1: 10 - 3 POS
        self.assertEqual(beer[2]['stock'], 7.0)    # day 2: no more POS
