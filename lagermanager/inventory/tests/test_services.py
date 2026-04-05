from django.test import TestCase
from django.utils import timezone
from core.models import Period
from pos_import.models import Article, ArticleGroup, WarehouseArticle, WarehouseUnit
from deliveries.models import Partner, TaxRate, StockMovement, StockMovementDetail
from inventory.models import PeriodStartStockLevel
from inventory.services.stock_calculation import compute_running_stock
from decimal import Decimal
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch


class StockCalculationTests(TestCase):
    period: Period
    partner: Partner
    tax_rate: TaxRate
    article_group: ArticleGroup
    article: Article
    start_date: datetime
    end_date: datetime

    def setUp(self) -> None:
        self.start_date = timezone.now().replace(
            hour=0, minute=0, second=0, microsecond=0)
        self.end_date = self.start_date + timedelta(days=2)
        self.period = Period.objects.create(
            name="Test Period",
            start=self.start_date,
            end=self.end_date
        )
        self.partner = Partner.objects.create(name="Supplier A")
        self.tax_rate = TaxRate.objects.create(
            name="Standard", percent=Decimal("20"))
        self.article_group = ArticleGroup.objects.create(
            source_id=1, name="Drinks", is_revenue=True,
            show_on_receipt=True, print_recipe=False,
            no_cancellation=False, period=self.period,
            standard_course=1
        )
        self.article = Article.objects.create(
            source_id=101, name="Beer", group=self.article_group, period=self.period,
            price_popup=False, ep_price_popup=False, rksv=False, external_receipt=False
        )

    @patch('inventory.services.stock_calculation.get_daily_pos_consumption')
    def test_compute_running_stock(self, mock_pos_consumption: MagicMock) -> None:
        # Mock POS consumption: 0 for all days
        mock_pos_consumption.return_value = {}

        # 1. Initial stock: 10
        PeriodStartStockLevel.objects.create(
            article=self.article,
            period=self.period,
            quantity=Decimal("10.000")
        )

        # 2. Delivery on Day 1: 20
        m1 = StockMovement.objects.create(
            partner=self.partner,
            date=self.start_date.date() + timedelta(days=1),
            movement_type=StockMovement.Type.DELIVERY,
            period=self.period
        )
        StockMovementDetail.objects.create(
            stock_movement=m1,
            article=self.article,
            quantity=Decimal("20.000"),
            unit_price=Decimal("1.0"),
            tax_rate=self.tax_rate
        )

        # 3. Manual consumption on Day 2: 5
        m2 = StockMovement.objects.create(
            partner=self.partner,
            date=self.start_date.date() + timedelta(days=2),
            movement_type=StockMovement.Type.CONSUMPTION,
            period=self.period
        )
        StockMovementDetail.objects.create(
            stock_movement=m2,
            article=self.article,
            quantity=Decimal("5.000"),
            unit_price=Decimal("1.0"),
            tax_rate=self.tax_rate
        )

        results = compute_running_stock(self.period.id)

        # Day 0: Start 10, End 10
        # Day 1: Start 10, Delivery 20, End 30
        # Day 2: Start 30, Consumption 5, End 25

        # results contains one entry per day per article
        # Filter for our article
        article_results = [r for r in results if r['article'] == "Beer"]
        self.assertEqual(len(article_results), 3)

        self.assertEqual(article_results[0]['stock'], 10.0)  # Day 0
        self.assertEqual(article_results[1]['stock'], 30.0)  # Day 1
        self.assertEqual(article_results[2]['stock'], 25.0)  # Day 2
