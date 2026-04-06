from datetime import date, timedelta
from decimal import Decimal

from deliveries.models import Partner, StockMovement, StockMovementDetail, TaxRate
from django.test import TestCase
from django.utils import timezone
from pos_import.models import (
    Article,
    ArticleGroup,
    Recipe,
    WarehouseArticle,
    WarehouseUnit,
)

from core.models import Period
from core.services.purchase_price import get_purchase_price


class PurchasePriceTests(TestCase):
    """Tests for get_purchase_price() — weighted average EK calculation."""

    period: Period
    partner: Partner
    tax_rate: TaxRate
    article_group: ArticleGroup

    def setUp(self) -> None:
        self.period = Period.objects.create(
            name="Test Period",
            start=timezone.now() - timedelta(days=30),
            end=timezone.now() + timedelta(days=30),
        )
        self.partner = Partner.objects.create(name="Supplier A")
        self.tax_rate = TaxRate.objects.create(name="Standard", percent=Decimal("20.00"))
        self.article_group = ArticleGroup.objects.create(
            source_id=1,
            name="Drinks",
            is_revenue=True,
            show_on_receipt=True,
            print_recipe=False,
            no_cancellation=False,
            period=self.period,
            standard_course=1,
        )

    def _make_article(self, source_id: int, name: str) -> Article:
        return Article.objects.create(
            source_id=source_id,
            name=name,
            group=self.article_group,
            period=self.period,
            price_popup=False,
            ep_price_popup=False,
            rksv=False,
            external_receipt=False,
        )

    def _make_warehouse_article(
        self, article: Article, unit: WarehouseUnit | None = None
    ) -> WarehouseArticle:
        return WarehouseArticle.objects.create(
            source_id=article.source_id,
            supplier_source_id=0,
            article=article,
            source_article_id=article.source_id,
            priority=1,
            unit=unit,
            source_unit_id=unit.source_id if unit else 0,
            flags=0,
            max_stock=Decimal("999.000"),
            min_stock=Decimal("0.000"),
            period=self.period,
        )

    def _make_delivery(
        self,
        article: Article,
        quantity: Decimal,
        unit_price: Decimal,
        delivery_date: date | None = None,
    ) -> StockMovementDetail:
        if delivery_date is None:
            delivery_date = timezone.now().date()
        movement = StockMovement.objects.create(
            partner=self.partner,
            date=delivery_date,
            movement_type=StockMovement.Type.DELIVERY,
            period=self.period,
        )
        return StockMovementDetail.objects.create(
            stock_movement=movement,
            article=article,
            quantity=quantity,
            unit_price=unit_price,
            tax_rate=self.tax_rate,
        )

    def _make_unit(self, source_id: int, multiplier: Decimal) -> WarehouseUnit:
        return WarehouseUnit.objects.create(
            source_id=source_id,
            name=f"Unit-{source_id}",
            multiplier=multiplier,
            period=self.period,
        )

    # ── Direct warehouse article tests ───────────────────────────────────────

    def test_direct_article_single_delivery(self) -> None:
        """Single delivery: weighted avg == delivery price."""
        article = self._make_article(101, "Beer")
        self._make_warehouse_article(article)
        self._make_delivery(article, Decimal("10.000"), Decimal("5.0000"))

        result = get_purchase_price(article.pk, self.period.pk)
        self.assertEqual(result, Decimal("5.0000"))

    def test_direct_article_weighted_average(self) -> None:
        """Two deliveries: (10*2 + 20*5) / 30 = 4.0000."""
        article = self._make_article(102, "Wine")
        self._make_warehouse_article(article)
        self._make_delivery(article, Decimal("10.000"), Decimal("2.0000"))
        self._make_delivery(article, Decimal("20.000"), Decimal("5.0000"))

        result = get_purchase_price(article.pk, self.period.pk)
        self.assertEqual(result, Decimal("4.0000"))

    def test_direct_article_no_deliveries_returns_zero(self) -> None:
        """Warehouse article with no deliveries returns 0."""
        article = self._make_article(103, "Vodka")
        self._make_warehouse_article(article)

        result = get_purchase_price(article.pk, self.period.pk)
        self.assertEqual(result, Decimal("0.0000"))

    def test_direct_article_max_date_filter(self) -> None:
        """max_date excludes deliveries after the cutoff date."""
        article = self._make_article(104, "Rum")
        self._make_warehouse_article(article)

        today = timezone.now().date()
        yesterday = today - timedelta(days=1)
        tomorrow = today + timedelta(days=1)

        # Delivery before cutoff: price 2.00
        self._make_delivery(article, Decimal("10.000"), Decimal("2.0000"), delivery_date=yesterday)
        # Delivery after cutoff: price 8.00 — should be excluded
        self._make_delivery(article, Decimal("10.000"), Decimal("8.0000"), delivery_date=tomorrow)

        result = get_purchase_price(article.pk, self.period.pk, max_date=today)
        self.assertEqual(result, Decimal("2.0000"))

    # ── Recipe article tests ──────────────────────────────────────────────────

    def test_recipe_article_single_component(self) -> None:
        """Recipe A -> B (qty=2, multiplier=1): EK = 2 * price_B."""
        master = self._make_article(201, "Gin Tonic")
        ingredient = self._make_article(202, "Gin")
        self._make_warehouse_article(ingredient)
        self._make_delivery(ingredient, Decimal("10.000"), Decimal("3.0000"))

        Recipe.objects.create(
            source_master_article_id=master.source_id,
            master_article=master,
            source_ingredient_article_id=ingredient.source_id,
            ingredient_article=ingredient,
            quantity=Decimal("2.0000"),
            is_fixed=False,
            is_ingredient=True,
            is_recipe=True,
            always_show=False,
            is_mandatory=False,
            use_price=False,
            period=self.period,
        )

        # factor = 2.0 / 1.0 (no unit, COALESCE returns 1.0)
        # EK = 3.0000 * 2.0 = 6.0000
        result = get_purchase_price(master.pk, self.period.pk)
        self.assertEqual(result, Decimal("6.0000"))

    def test_recipe_article_unit_multiplier(self) -> None:
        """Unit multiplier affects factor: qty=2, multiplier=0.5 → factor=4."""
        master = self._make_article(211, "Large Gin Tonic")
        ingredient = self._make_article(212, "Gin Bottle")
        unit = self._make_unit(1, Decimal("0.5000"))
        self._make_warehouse_article(ingredient, unit=unit)
        self._make_delivery(ingredient, Decimal("10.000"), Decimal("3.0000"))

        Recipe.objects.create(
            source_master_article_id=master.source_id,
            master_article=master,
            source_ingredient_article_id=ingredient.source_id,
            ingredient_article=ingredient,
            quantity=Decimal("2.0000"),
            is_fixed=False,
            is_ingredient=True,
            is_recipe=True,
            always_show=False,
            is_mandatory=False,
            use_price=False,
            period=self.period,
        )

        # factor = 2.0 / 0.5 = 4.0; EK = 3.0000 * 4.0 = 12.0000
        result = get_purchase_price(master.pk, self.period.pk)
        self.assertEqual(result, Decimal("12.0000"))

    def test_recipe_article_multiple_components(self) -> None:
        """Sum of (factor * price) across two recipe components."""
        master = self._make_article(221, "Cocktail Mix")
        comp_a = self._make_article(222, "Spirit A")
        comp_b = self._make_article(223, "Spirit B")
        self._make_warehouse_article(comp_a)
        self._make_warehouse_article(comp_b)
        self._make_delivery(comp_a, Decimal("10.000"), Decimal("3.0000"))
        self._make_delivery(comp_b, Decimal("10.000"), Decimal("10.0000"))

        for ingredient, qty in [(comp_a, "2.0000"), (comp_b, "1.0000")]:
            Recipe.objects.create(
                source_master_article_id=master.source_id,
                master_article=master,
                source_ingredient_article_id=ingredient.source_id,
                ingredient_article=ingredient,
                quantity=Decimal(qty),
                is_fixed=False,
                is_ingredient=True,
                is_recipe=True,
                always_show=False,
                is_mandatory=False,
                use_price=False,
                period=self.period,
            )

        # comp_a: 3.0 * 2 = 6.0; comp_b: 10.0 * 1 = 10.0; total = 16.0000
        result = get_purchase_price(master.pk, self.period.pk)
        self.assertEqual(result, Decimal("16.0000"))

    def test_recipe_no_components_returns_zero(self) -> None:
        """Article that is neither a warehouse article nor has recipe entries returns 0."""
        article = self._make_article(301, "Ghost Article")

        result = get_purchase_price(article.pk, self.period.pk)
        self.assertEqual(result, Decimal("0.00"))

    def test_recipe_component_no_deliveries(self) -> None:
        """Recipe exists but component has no deliveries — component EK = 0."""
        master = self._make_article(311, "Empty Cocktail")
        ingredient = self._make_article(312, "Rare Spirit")
        self._make_warehouse_article(ingredient)
        # No delivery for ingredient

        Recipe.objects.create(
            source_master_article_id=master.source_id,
            master_article=master,
            source_ingredient_article_id=ingredient.source_id,
            ingredient_article=ingredient,
            quantity=Decimal("1.0000"),
            is_fixed=False,
            is_ingredient=True,
            is_recipe=True,
            always_show=False,
            is_mandatory=False,
            use_price=False,
            period=self.period,
        )

        result = get_purchase_price(master.pk, self.period.pk)
        self.assertEqual(result, Decimal("0.0000"))

    def test_nonexistent_period_raises(self) -> None:
        """Bogus period_id raises Period.DoesNotExist."""
        article = self._make_article(401, "Any Article")
        with self.assertRaises(Period.DoesNotExist):
            get_purchase_price(article.pk, 999999)
