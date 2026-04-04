from django.test import TestCase
from django.utils import timezone
from core.models import Period
from pos_import.models import Article, ArticleGroup
from deliveries.models import Partner, TaxRate, StockMovement, StockMovementDetail
from decimal import Decimal
from datetime import date, timedelta

class DeliveriesModelTests(TestCase):
    def setUp(self):
        self.period = Period.objects.create(
            name="Test Period",
            start=timezone.now() - timedelta(days=10),
            end=timezone.now() + timedelta(days=10)
        )
        self.partner = Partner.objects.create(name="Supplier A", partner_type=Partner.Type.SUPPLIER)
        self.tax_rate = TaxRate.objects.create(name="Standard", percent=Decimal("20.00"))
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

    def test_partner_creation(self):
        self.assertEqual(str(self.partner), "Supplier A")

    def test_tax_rate_creation(self):
        self.assertEqual(str(self.tax_rate), "Standard (20.00%)")

    def test_stock_movement_creation(self):
        movement = StockMovement.objects.create(
            partner=self.partner,
            date=date.today(),
            movement_type=StockMovement.Type.DELIVERY,
            period=self.period
        )
        self.assertTrue(str(movement).startswith("Lieferung"))

    def test_stock_movement_totals(self):
        movement = StockMovement.objects.create(
            partner=self.partner,
            date=date.today(),
            movement_type=StockMovement.Type.DELIVERY,
            period=self.period
        )
        StockMovementDetail.objects.create(
            stock_movement=movement,
            article=self.article,
            quantity=Decimal("10.000"),
            unit_price=Decimal("1.5000"),
            tax_rate=self.tax_rate
        )
        # 10 * 1.5 = 15.0000
        self.assertEqual(movement.total_net, Decimal("15.0000"))
        # 15 * 1.2 = 18.0000
        self.assertEqual(movement.total_gross, Decimal("18.0000"))

    def test_apply_skonto(self):
        movement = StockMovement.objects.create(
            partner=self.partner,
            date=date.today(),
            movement_type=StockMovement.Type.DELIVERY,
            period=self.period
        )
        detail = StockMovementDetail.objects.create(
            stock_movement=movement,
            article=self.article,
            quantity=Decimal("10.000"),
            unit_price=Decimal("10.0000"),
            tax_rate=self.tax_rate
        )
        movement.apply_skonto(2.0) # 2% discount
        detail.refresh_from_db()
        # 10.0 * 0.98 = 9.8
        self.assertEqual(detail.unit_price, Decimal("9.8000"))
