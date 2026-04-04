from django.test import TestCase
from django.utils import timezone
from core.models import Period, Location
from pos_import.models import Article, ArticleGroup
from inventory.models import PeriodStartStockLevel, InitialInventory, PhysicalCount
from decimal import Decimal
from datetime import timedelta

class InventoryModelTests(TestCase):
    def setUp(self):
        self.period = Period.objects.create(
            name="Test Period",
            start=timezone.now() - timedelta(days=10),
            end=timezone.now() + timedelta(days=10)
        )
        self.location = Location.objects.create(name="Main Bar")
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

    def test_period_start_stock_level(self):
        sl = PeriodStartStockLevel.objects.create(
            article=self.article,
            quantity=Decimal("50.000"),
            period=self.period
        )
        self.assertEqual(sl.quantity, Decimal("50.000"))
        self.assertEqual(sl.article, self.article)

    def test_initial_inventory(self):
        ii = InitialInventory.objects.create(
            article=self.article,
            quantity=Decimal("10.500"),
            location=self.location,
            period=self.period
        )
        self.assertEqual(ii.quantity, Decimal("10.500"))
        self.assertEqual(ii.location, self.location)

    def test_physical_count(self):
        pc = PhysicalCount.objects.create(
            date=timezone.now(),
            article=self.article,
            quantity=Decimal("45.000"),
            period=self.period
        )
        self.assertEqual(pc.quantity, Decimal("45.000"))
        self.assertEqual(pc.article, self.article)
