"""Tests for the import_legacy management command."""

import datetime
from decimal import Decimal
from io import StringIO
from typing import Any
from unittest.mock import MagicMock, patch

from core.models import Period
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from pos_import.models import Article, ArticleGroup

from deliveries.models import (
    Partner,
    StockMovement,
    StockMovementDetail,
    TaxRate,
)

# ---------------------------------------------------------------------------
# Helpers to build fake MySQL rows
# ---------------------------------------------------------------------------

def _make_lieferanten() -> list[dict[str, Any]]:
    return [
        {'lieferant_id': 1, 'lieferant_name': 'Lieferant GmbH', 'lft_ist_verbraucher': 0},
        {'lieferant_id': 2, 'lieferant_name': 'Bar Intern', 'lft_ist_verbraucher': 1},
    ]


def _make_steuersaetze() -> list[dict[str, Any]]:
    return [
        {'sts_id': 1, 'sts_bezeichnung': 'Ermaessigt', 'sts_prozent': 10.0},
        {'sts_id': 2, 'sts_bezeichnung': 'Normal', 'sts_prozent': 20.0},
    ]


def _make_lieferungen() -> list[dict[str, Any]]:
    return [
        {
            'lieferung_id': 1,
            'lieferant_id': 1,
            'datum': datetime.datetime(2024, 1, 15, 10, 0, 0),
            'lie_ist_verbrauch': 0,
            'lie_kommentar': 'Rechnung 001',
        },
        {
            'lieferung_id': 2,
            'lieferant_id': 2,
            'datum': datetime.datetime(2024, 1, 20, 12, 0, 0),
            'lie_ist_verbrauch': 1,
            'lie_kommentar': None,
        },
    ]


def _make_lieferungen_details(artikel_id_1: int, artikel_id_2: int) -> list[dict[str, Any]]:
    return [
        {
            'lieferung_detail_id': 1,
            'lieferung_id': 1,
            'artikel_id': artikel_id_1,
            'anzahl': 10.0,
            'einkaufspreis': 5.5,
            'lde_stsid': 1,
        },
        {
            'lieferung_detail_id': 2,
            'lieferung_id': 2,
            'artikel_id': artikel_id_2,
            'anzahl': 3.0,
            'einkaufspreis': 12.0,
            'lde_stsid': 2,
        },
    ]


def _build_mock_conn(
    lieferanten: list[dict[str, Any]],
    steuersaetze: list[dict[str, Any]],
    lieferungen: list[dict[str, Any]],
    lieferungen_details: list[dict[str, Any]],
) -> MagicMock:
    """Build a mock pymysql connection whose cursor().fetchall() returns the given rows."""
    conn = MagicMock()

    # Each call to conn.cursor() returns a context-manager mock.
    # We'll drive calls by query keyword.
    call_results: dict[str, list[dict[str, Any]]] = {
        'lieferanten': lieferanten,
        'steuersaetze': steuersaetze,
        'lieferungen ORDER': lieferungen,
        'lieferungen_details': lieferungen_details,
    }

    def _cursor_factory() -> MagicMock:
        cur = MagicMock()
        cur.__enter__ = lambda s: s
        cur.__exit__ = MagicMock(return_value=False)
        last_sql: list[str] = []

        def _execute(sql: str, *args: Any) -> None:
            last_sql.clear()
            last_sql.append(sql)

        def _fetchall() -> list[dict[str, Any]]:
            sql = last_sql[0] if last_sql else ''
            for key, rows in call_results.items():
                if key in sql:
                    return list(rows)
            return []

        cur.execute.side_effect = _execute
        cur.fetchall.side_effect = _fetchall
        return cur

    conn.cursor.side_effect = _cursor_factory
    return conn


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

class ImportLegacyCommandTest(TestCase):
    period: Period
    article_group: ArticleGroup
    article1: Article
    article2: Article

    def setUp(self) -> None:
        self.period = Period.objects.create(
            name='Test Period',
            start=timezone.make_aware(datetime.datetime(2024, 1, 1)),
            end=timezone.make_aware(datetime.datetime(2024, 12, 31, 23, 59, 59)),
        )
        self.article_group = ArticleGroup.objects.create(
            source_id=10,
            name='Getränke',
            is_revenue=True,
            show_on_receipt=True,
            print_recipe=False,
            no_cancellation=False,
            period=self.period,
            standard_course=1,
        )
        self.article1 = Article.objects.create(
            source_id=100,
            name='Bier',
            group=self.article_group,
            period=self.period,
            price_popup=False,
            ep_price_popup=False,
            rksv=False,
            external_receipt=False,
        )
        self.article2 = Article.objects.create(
            source_id=200,
            name='Wein',
            group=self.article_group,
            period=self.period,
            price_popup=False,
            ep_price_popup=False,
            rksv=False,
            external_receipt=False,
        )

    def _call_command(self, mock_conn: MagicMock) -> tuple[str, str]:
        """Call import_legacy with --no-input and capture stdout/stderr."""
        out = StringIO()
        err = StringIO()
        with (
            patch('deliveries.management.commands.import_legacy._connect', return_value=mock_conn),
            # Suppress the second SSDictCursor connection used for documents
            patch('deliveries.management.commands.import_legacy.pymysql.connect', return_value=MagicMock(
                __enter__=lambda s: s,
                __exit__=MagicMock(return_value=False),
                cursor=MagicMock(return_value=MagicMock(
                    __enter__=lambda s: s,
                    __exit__=MagicMock(return_value=False),
                    execute=MagicMock(),
                    __iter__=lambda s: iter([]),
                )),
                close=MagicMock(),
            )),
        ):
            call_command(
                'import_legacy',
                '--user', 'u',
                '--password', 'p',
                '--database', 'db',
                '--period', str(self.period.pk),
                '--no-input',
                stdout=out,
                stderr=err,
            )
        return out.getvalue(), err.getvalue()

    def test_imports_partners(self) -> None:
        conn = _build_mock_conn(
            _make_lieferanten(),
            _make_steuersaetze(),
            _make_lieferungen(),
            _make_lieferungen_details(self.article1.source_id, self.article2.source_id),
        )
        self._call_command(conn)

        self.assertEqual(Partner.objects.count(), 2)
        supplier = Partner.objects.get(name='Lieferant GmbH')
        self.assertEqual(supplier.partner_type, Partner.Type.SUPPLIER)
        consumer = Partner.objects.get(name='Bar Intern')
        self.assertEqual(consumer.partner_type, Partner.Type.CONSUMER)

    def test_imports_tax_rates(self) -> None:
        conn = _build_mock_conn(
            _make_lieferanten(),
            _make_steuersaetze(),
            _make_lieferungen(),
            _make_lieferungen_details(self.article1.source_id, self.article2.source_id),
        )
        self._call_command(conn)

        self.assertEqual(TaxRate.objects.count(), 2)
        self.assertTrue(TaxRate.objects.filter(percent=Decimal('10.00')).exists())
        self.assertTrue(TaxRate.objects.filter(percent=Decimal('20.00')).exists())

    def test_imports_movements_and_details(self) -> None:
        conn = _build_mock_conn(
            _make_lieferanten(),
            _make_steuersaetze(),
            _make_lieferungen(),
            _make_lieferungen_details(self.article1.source_id, self.article2.source_id),
        )
        self._call_command(conn)

        self.assertEqual(StockMovement.objects.count(), 2)
        delivery = StockMovement.objects.get(movement_type=StockMovement.Type.DELIVERY)
        self.assertEqual(delivery.date, datetime.date(2024, 1, 15))
        self.assertEqual(delivery.comment, 'Rechnung 001')
        self.assertEqual(delivery.partner.name, 'Lieferant GmbH')

        consumption = StockMovement.objects.get(movement_type=StockMovement.Type.CONSUMPTION)
        self.assertIsNone(consumption.comment)
        self.assertEqual(consumption.partner.name, 'Bar Intern')

        self.assertEqual(StockMovementDetail.objects.count(), 2)
        detail1 = StockMovementDetail.objects.get(stock_movement=delivery)
        self.assertEqual(detail1.article, self.article1)
        self.assertEqual(detail1.quantity, Decimal('10.000'))
        self.assertEqual(detail1.unit_price, Decimal('5.5000'))

    def test_skips_detail_with_unknown_article(self) -> None:
        # Use a source_id that doesn't exist in the DB
        conn = _build_mock_conn(
            _make_lieferanten(),
            _make_steuersaetze(),
            _make_lieferungen(),
            _make_lieferungen_details(9999, self.article2.source_id),
        )
        _, err = self._call_command(conn)

        # detail for article 9999 should be skipped
        self.assertEqual(StockMovementDetail.objects.count(), 1)
        self.assertIn('9999', err)

    def test_deletes_existing_data_before_import(self) -> None:
        # Pre-create some data that should be wiped
        partner = Partner.objects.create(name='Old Partner', partner_type=Partner.Type.SUPPLIER)
        tax_rate = TaxRate.objects.create(name='Old Rate', percent=Decimal('5.00'))
        movement = StockMovement.objects.create(
            partner=partner,
            date=datetime.date(2024, 1, 1),
            movement_type=StockMovement.Type.DELIVERY,
            period=self.period,
        )
        StockMovementDetail.objects.create(
            stock_movement=movement,
            article=self.article1,
            quantity=Decimal('1'),
            unit_price=Decimal('1'),
            tax_rate=tax_rate,
        )

        conn = _build_mock_conn(
            _make_lieferanten(),
            _make_steuersaetze(),
            _make_lieferungen(),
            _make_lieferungen_details(self.article1.source_id, self.article2.source_id),
        )
        self._call_command(conn)

        # After import, only newly imported data exists
        self.assertFalse(Partner.objects.filter(name='Old Partner').exists())
        self.assertFalse(TaxRate.objects.filter(name='Old Rate').exists())

    def test_uses_fallback_tax_rate_when_stsid_missing(self) -> None:
        # Pass an lde_stsid that won't be in the imported tax_rate_map
        details_with_bad_sts = [
            {
                'lieferung_detail_id': 1,
                'lieferung_id': 1,
                'artikel_id': self.article1.source_id,
                'anzahl': 1.0,
                'einkaufspreis': 1.0,
                'lde_stsid': 999,  # does not exist
            },
        ]
        conn = _build_mock_conn(
            _make_lieferanten(),
            _make_steuersaetze(),
            [_make_lieferungen()[0]],  # only first movement
            details_with_bad_sts,
        )
        _, err = self._call_command(conn)

        # Detail should still be created (using fallback)
        self.assertEqual(StockMovementDetail.objects.count(), 1)
        # Warning should mention the fallback
        self.assertIn('fallback', err)
