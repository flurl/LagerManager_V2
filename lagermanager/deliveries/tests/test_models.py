from django.test import TestCase
from django.utils import timezone
from core.models import Period
from pos_import.models import Article, ArticleGroup
from deliveries.models import Partner, TaxRate, StockMovement, StockMovementDetail
from decimal import Decimal
from datetime import date, timedelta

class DeliveriesModelTests(TestCase):
    period: Period
    partner: Partner
    tax_rate: TaxRate
    article_group: ArticleGroup
    article: Article

    def setUp(self) -> None:
        self.period = Period.objects.create(
            name="Test Period",
            start=timezone.now() - timedelta(days=10),
            end=timezone.now() + timedelta(days=10)
        )
        self.partner = Partner.objects.create(name="Supplier A")
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

    def test_partner_creation(self) -> None:
        self.assertEqual(str(self.partner), "Supplier A")

    def test_tax_rate_creation(self) -> None:
        self.assertEqual(str(self.tax_rate), "Standard (20.00%)")

    def test_stock_movement_creation(self) -> None:
        movement = StockMovement.objects.create(
            partner=self.partner,
            date=date.today(),
            movement_type=StockMovement.Type.DELIVERY,
            period=self.period
        )
        self.assertTrue(str(movement).startswith("Lieferung"))

    def test_stock_movement_totals(self) -> None:
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

    def test_apply_skonto(self) -> None:
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


class StockMovementCalculationTests(TestCase):
    """Edge-case tests for StockMovement/StockMovementDetail calculations."""

    period: Period
    partner: Partner
    tax_rate: TaxRate
    tax_rate_10: TaxRate
    article_group: ArticleGroup
    article: Article

    def setUp(self) -> None:
        self.period = Period.objects.create(
            name="Calc Period",
            start=timezone.now() - timedelta(days=10),
            end=timezone.now() + timedelta(days=10),
        )
        self.partner = Partner.objects.create(name="Supplier B")
        self.tax_rate = TaxRate.objects.create(name="Standard 20%", percent=Decimal("20.00"))
        self.tax_rate_10 = TaxRate.objects.create(name="Reduced 10%", percent=Decimal("10.00"))
        self.article_group = ArticleGroup.objects.create(
            source_id=2, name="Food", is_revenue=True,
            show_on_receipt=True, print_recipe=False,
            no_cancellation=False, period=self.period,
            standard_course=1,
        )
        self.article = Article.objects.create(
            source_id=201, name="Water", group=self.article_group, period=self.period,
            price_popup=False, ep_price_popup=False, rksv=False, external_receipt=False,
        )

    def _make_movement(self) -> StockMovement:
        return StockMovement.objects.create(
            partner=self.partner,
            date=date.today(),
            movement_type=StockMovement.Type.DELIVERY,
            period=self.period,
        )

    # ── total_net / total_gross ───────────────────────────────────────────────

    def test_total_net_multiple_details(self) -> None:
        """total_net sums across all detail lines."""
        movement = self._make_movement()
        StockMovementDetail.objects.create(
            stock_movement=movement, article=self.article,
            quantity=Decimal("10.000"), unit_price=Decimal("1.5000"), tax_rate=self.tax_rate,
        )
        StockMovementDetail.objects.create(
            stock_movement=movement, article=self.article,
            quantity=Decimal("5.000"), unit_price=Decimal("3.0000"), tax_rate=self.tax_rate,
        )
        # 10*1.5 + 5*3 = 15 + 15 = 30
        self.assertEqual(movement.total_net, Decimal("30.0000"))

    def test_total_gross_mixed_tax_rates(self) -> None:
        """total_gross applies each line's own tax rate."""
        movement = self._make_movement()
        StockMovementDetail.objects.create(
            stock_movement=movement, article=self.article,
            quantity=Decimal("10.000"), unit_price=Decimal("1.0000"), tax_rate=self.tax_rate,
        )
        StockMovementDetail.objects.create(
            stock_movement=movement, article=self.article,
            quantity=Decimal("10.000"), unit_price=Decimal("1.0000"), tax_rate=self.tax_rate_10,
        )
        # line 1: 10 * 1.00 * 1.20 = 12.00
        # line 2: 10 * 1.00 * 1.10 = 11.00
        # total  = 23.00
        self.assertAlmostEqual(float(movement.total_gross), 23.0, places=4)

    def test_total_net_no_details(self) -> None:
        """Movement with no details returns total_net == 0."""
        movement = self._make_movement()
        self.assertEqual(movement.total_net, Decimal(0))

    def test_total_gross_no_details(self) -> None:
        """Movement with no details returns total_gross == 0."""
        movement = self._make_movement()
        self.assertEqual(movement.total_gross, Decimal(0))

    # ── line_net / line_gross ─────────────────────────────────────────────────

    def test_line_net_property(self) -> None:
        """line_net == quantity * unit_price."""
        movement = self._make_movement()
        detail = StockMovementDetail.objects.create(
            stock_movement=movement, article=self.article,
            quantity=Decimal("7.000"), unit_price=Decimal("2.5000"), tax_rate=self.tax_rate,
        )
        self.assertEqual(detail.line_net, Decimal("7.000") * Decimal("2.5000"))

    def test_line_gross_property(self) -> None:
        """line_gross == line_net * (1 + percent/100)."""
        movement = self._make_movement()
        detail = StockMovementDetail.objects.create(
            stock_movement=movement, article=self.article,
            quantity=Decimal("4.000"), unit_price=Decimal("5.0000"), tax_rate=self.tax_rate,
        )
        expected = Decimal("4.000") * Decimal("5.0000") * (1 + Decimal("20.00") / 100)
        self.assertEqual(detail.line_gross, expected)

    # ── clean() validation ────────────────────────────────────────────────────

    def test_clean_date_outside_period_raises(self) -> None:
        """full_clean() raises ValidationError when date is outside the period."""
        from django.core.exceptions import ValidationError
        movement = StockMovement(
            partner=self.partner,
            date=date.today() - timedelta(days=20),  # before period.start
            movement_type=StockMovement.Type.DELIVERY,
            period=self.period,
        )
        with self.assertRaises(ValidationError) as ctx:
            movement.full_clean()
        self.assertIn('date', ctx.exception.message_dict)

    def test_clean_date_inside_period_passes(self) -> None:
        """full_clean() does not raise when date is within the period."""
        movement = StockMovement(
            partner=self.partner,
            date=date.today(),
            movement_type=StockMovement.Type.DELIVERY,
            period=self.period,
        )
        movement.full_clean()  # must not raise

    # ── apply_skonto edge cases ───────────────────────────────────────────────

    def test_apply_skonto_multiple_details(self) -> None:
        """apply_skonto updates all detail lines."""
        movement = self._make_movement()
        detail_a = StockMovementDetail.objects.create(
            stock_movement=movement, article=self.article,
            quantity=Decimal("1.000"), unit_price=Decimal("10.0000"), tax_rate=self.tax_rate,
        )
        detail_b = StockMovementDetail.objects.create(
            stock_movement=movement, article=self.article,
            quantity=Decimal("1.000"), unit_price=Decimal("20.0000"), tax_rate=self.tax_rate,
        )
        movement.apply_skonto(3.0)  # 3% discount
        detail_a.refresh_from_db()
        detail_b.refresh_from_db()
        # 10.0 * 0.97 = 9.7000;  20.0 * 0.97 = 19.4000
        self.assertEqual(detail_a.unit_price, Decimal("9.7000"))
        self.assertEqual(detail_b.unit_price, Decimal("19.4000"))

    def test_apply_skonto_zero_percent(self) -> None:
        """apply_skonto with 0% leaves prices unchanged."""
        movement = self._make_movement()
        detail = StockMovementDetail.objects.create(
            stock_movement=movement, article=self.article,
            quantity=Decimal("1.000"), unit_price=Decimal("10.0000"), tax_rate=self.tax_rate,
        )
        movement.apply_skonto(0.0)
        detail.refresh_from_db()
        self.assertEqual(detail.unit_price, Decimal("10.0000"))
