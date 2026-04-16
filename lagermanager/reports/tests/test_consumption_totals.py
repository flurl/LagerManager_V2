"""
Tests for get_consumption_totals() with revenue_filter and include_lm_data parameters.

The POS SQL query is mocked (too complex to set up the full POS import schema in tests).
Manual StockMovement consumption is tested via real Django ORM objects.
"""
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.utils import timezone

from core.models import Period
from deliveries.models import Partner, StockMovement, StockMovementDetail, TaxRate
from pos_import.models import Article, ArticleGroup
from reports.services.consumption_report import get_consumption_totals


class ConsumptionTotalsFilterTests(TestCase):
    """Tests for get_consumption_totals() filter parameters."""

    period: Period
    partner: Partner
    tax_rate: TaxRate
    article_group: ArticleGroup
    article: Article

    def setUp(self) -> None:
        start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        end = start
        self.period = Period.objects.create(
            name="Totals Test Period",
            start=start,
            end=end,
        )
        self.partner = Partner.objects.create(name="Test Partner")
        self.tax_rate = TaxRate.objects.create(name="Standard", percent=Decimal("20.00"))
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

    def _make_consumption_movement(self, quantity: Decimal) -> None:
        m = StockMovement.objects.create(
            partner=self.partner,
            date=self.period.start.date(),
            movement_type=StockMovement.Type.CONSUMPTION,
            period=self.period,
        )
        StockMovementDetail.objects.create(
            stock_movement=m,
            article=self.article,
            quantity=quantity,
            unit_price=Decimal("1.0000"),
            tax_rate=self.tax_rate,
        )

    @patch('reports.services.consumption_report.connection')
    def test_default_params_includes_pos_and_lm(self, mock_conn: MagicMock) -> None:
        """Default call (revenue_filter='all', include_lm_data=True) sums both sources."""
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = lambda s: mock_cursor
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchall.return_value = [('Beer', 5.0)]

        self._make_consumption_movement(Decimal('3.000'))

        result = get_consumption_totals(self.period.pk)

        totals = {r['article']: r['total'] for r in result}
        self.assertAlmostEqual(totals['Beer'], 8.0)

    @patch('reports.services.consumption_report.connection')
    def test_include_lm_data_false_excludes_manual_movements(self, mock_conn: MagicMock) -> None:
        """include_lm_data=False omits manual StockMovement consumption."""
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = lambda s: mock_cursor
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchall.return_value = [('Beer', 5.0)]

        self._make_consumption_movement(Decimal('3.000'))

        result = get_consumption_totals(self.period.pk, include_lm_data=False)

        totals = {r['article']: r['total'] for r in result}
        self.assertAlmostEqual(totals['Beer'], 5.0)

    @patch('reports.services.consumption_report.connection')
    def test_include_lm_data_true_includes_manual_movements(self, mock_conn: MagicMock) -> None:
        """include_lm_data=True (default) adds StockMovement consumption to POS total."""
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = lambda s: mock_cursor
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchall.return_value = []

        self._make_consumption_movement(Decimal('4.000'))

        result = get_consumption_totals(self.period.pk, include_lm_data=True)

        totals = {r['article']: r['total'] for r in result}
        self.assertAlmostEqual(totals['Beer'], 4.0)

    @patch('reports.services.consumption_report.connection')
    def test_revenue_filter_umsatz_adds_filter_clause(self, mock_conn: MagicMock) -> None:
        """revenue_filter='umsatz' passes the ist_umsatz=TRUE filter in the SQL."""
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = lambda s: mock_cursor
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchall.return_value = [('Beer', 2.0)]

        result = get_consumption_totals(self.period.pk, revenue_filter='umsatz', include_lm_data=False)

        # Verify the SQL passed to execute contains the umsatz filter
        executed_sql: str = mock_cursor.execute.call_args[0][0]
        self.assertIn('tisch_bondetail_istUmsatz" = TRUE', executed_sql)
        totals = {r['article']: r['total'] for r in result}
        self.assertAlmostEqual(totals['Beer'], 2.0)

    @patch('reports.services.consumption_report.connection')
    def test_revenue_filter_aufwand_adds_filter_clause(self, mock_conn: MagicMock) -> None:
        """revenue_filter='aufwand' passes the ist_umsatz=FALSE filter in the SQL."""
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = lambda s: mock_cursor
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchall.return_value = [('Wine', 1.5)]

        result = get_consumption_totals(self.period.pk, revenue_filter='aufwand', include_lm_data=False)

        executed_sql: str = mock_cursor.execute.call_args[0][0]
        self.assertIn('tisch_bondetail_istUmsatz" = FALSE', executed_sql)
        totals = {r['article']: r['total'] for r in result}
        self.assertAlmostEqual(totals['Wine'], 1.5)

    @patch('reports.services.consumption_report.connection')
    def test_revenue_filter_all_has_no_umsatz_clause(self, mock_conn: MagicMock) -> None:
        """revenue_filter='all' does not add an istUmsatz filter to the SQL."""
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = lambda s: mock_cursor
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchall.return_value = []

        get_consumption_totals(self.period.pk, revenue_filter='all', include_lm_data=False)

        executed_sql: str = mock_cursor.execute.call_args[0][0]
        self.assertNotIn('tisch_bondetail_istUmsatz', executed_sql)

    @patch('reports.services.consumption_report.connection')
    def test_no_lm_data_no_pos_returns_empty(self, mock_conn: MagicMock) -> None:
        """No POS data and no LM data returns an empty list."""
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = lambda s: mock_cursor
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchall.return_value = []

        result = get_consumption_totals(self.period.pk, include_lm_data=False)

        self.assertEqual(result, [])

    @patch('reports.services.consumption_report.connection')
    def test_multiple_lm_movements_same_article_summed(self, mock_conn: MagicMock) -> None:
        """Multiple manual consumption movements for same article are summed."""
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = lambda s: mock_cursor
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchall.return_value = []

        self._make_consumption_movement(Decimal('2.000'))
        self._make_consumption_movement(Decimal('3.500'))

        result = get_consumption_totals(self.period.pk, include_lm_data=True)

        totals = {r['article']: r['total'] for r in result}
        self.assertAlmostEqual(totals['Beer'], 5.5)
