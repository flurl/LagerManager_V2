"""
Consumption report — cumulative daily consumption per article.

Consumption is the sum of:
  - POS/Wiffzack consumption
  - Manually recorded consumption StockMovements
"""
import datetime
from typing import Any, Literal

from core.models import Period
from deliveries.models import StockMovement
from django.db import connection
from inventory.services.stock_calculation import get_daily_stock_delta

RevenueFilter = Literal['all', 'umsatz', 'aufwand']

# Direct-total query for the consumption totals report.
# Returns (article_name, total_amount) per article for the full period.
# Two-part UNION: recipe-decomposed articles + direct articles (no recipe).
_TOTALS_QUERY_RECIPE = """
    SELECT
        art2.artikel_bezeichnung AS article_name,
        SUM(tbd.tisch_bondetail_absmenge * az.zutate_menge / COALESCE(le.lager_einheit_multiplizierer, 1.0)) AS amount
    FROM artikel_basis art1
    JOIN artikel_zutaten az ON az.zutate_master_artikel = art1.artikel_id
    JOIN artikel_basis art2 ON az.zutate_artikel = art2.artikel_id
    JOIN tische_bondetails tbd ON tbd.tisch_bondetail_artikel = art1.artikel_id
    JOIN tische_bons tb ON tbd.tisch_bondetail_bon = tb.tisch_bon_id
    JOIN tische_aktiv ta ON tb.tisch_bon_tisch = ta.tisch_id
    JOIN journal_checkpoints jc ON jc.checkpoint_id = ta.checkpoint_tag
    JOIN lager_artikel la ON la.lager_artikel_artikel = art2.artikel_id
    JOIN lager_einheiten le ON la.lager_artikel_einheit = le.lager_einheit_id
    WHERE az."zutate_istRezept" = TRUE
      AND TRIM(jc.checkpoint_typ) = '1'
      AND ta.tisch_periode = %(period_id)s
      AND tb.tisch_bon_periode = %(period_id)s
      AND tbd.tisch_bondetail_periode = %(period_id)s
      AND jc.checkpoint_periode = %(period_id)s
      AND az.zutate_periode = %(period_id)s
      AND art1.artikel_periode = %(period_id)s
      AND art2.artikel_periode = %(period_id)s
      AND (la.lager_artikel_periode = %(period_id)s OR la.lager_artikel_periode IS NULL)
      AND le.lager_einheit_periode = %(period_id)s
      {ist_umsatz_filter}
    GROUP BY art2.artikel_bezeichnung
"""

_TOTALS_QUERY_DIRECT = """
    SELECT
        a.artikel_bezeichnung AS article_name,
        SUM(tbd.tisch_bondetail_absmenge) AS amount
    FROM artikel_basis a
    LEFT JOIN artikel_zutaten az ON az.zutate_master_artikel = a.artikel_id
    JOIN tische_bondetails tbd ON tbd.tisch_bondetail_artikel = a.artikel_id
    JOIN tische_bons tb ON tbd.tisch_bondetail_bon = tb.tisch_bon_id
    JOIN tische_aktiv ta ON tb.tisch_bon_tisch = ta.tisch_id
    JOIN journal_checkpoints jc ON jc.checkpoint_id = ta.checkpoint_tag
    WHERE az."zutate_istRezept" IS NULL
      AND TRIM(jc.checkpoint_typ) = '1'
      AND ta.tisch_periode = %(period_id)s
      AND tb.tisch_bon_periode = %(period_id)s
      AND tbd.tisch_bondetail_periode = %(period_id)s
      AND jc.checkpoint_periode = %(period_id)s
      AND (az.zutate_periode = %(period_id)s OR az.zutate_periode IS NULL)
      AND a.artikel_periode = %(period_id)s
      {ist_umsatz_filter}
    GROUP BY a.artikel_bezeichnung
"""


def get_consumption_chart_data(period_id: int) -> dict[str, Any]:
    """
    Returns cumulative Chart.js dataset for consumption over the period.
    """
    period = Period.objects.get(pk=period_id)
    daily: dict[datetime.date, dict[str, float]] = get_daily_stock_delta(
        period_id, (StockMovement.Type.CONSUMPTION,)
    )

    # Collect all articles and dates
    articles_set: set[str] = set()
    for day_data in daily.values():
        articles_set.update(day_data.keys())
    all_articles: list[str] = sorted(articles_set)

    current_date = period.start.date()
    end_date = period.end.date()

    dates = []
    cumulative = dict.fromkeys(all_articles, 0.0)
    rows = []

    while current_date <= end_date:
        dates.append(current_date.isoformat())
        for article in all_articles:
            cumulative[article] -= daily.get(current_date, {}).get(article, 0.0)
        rows.append({a: round(cumulative[a], 3) for a in all_articles})
        current_date += datetime.timedelta(days=1)

    datasets: list[dict[str, Any]] = [
        {'label': a, 'data': [row[a] for row in rows]}
        for a in all_articles
    ]

    return {'labels': dates, 'datasets': datasets}


def _get_lm_consumption_totals(period_id: int) -> dict[str, float]:
    """Returns {article_name: total_amount} for manual StockMovement consumption records."""
    period = Period.objects.get(pk=period_id)
    totals: dict[str, float] = {}
    movements = StockMovement.objects.filter(
        period=period, movement_type=StockMovement.Type.CONSUMPTION
    ).prefetch_related('details__article')
    for movement in movements:
        for detail in movement.details.all():
            name = detail.article.name
            totals[name] = totals.get(name, 0.0) + float(detail.quantity)
    return totals


def get_consumption_totals(
    period_id: int,
    *,
    revenue_filter: RevenueFilter = 'all',
    include_lm_data: bool = True,
) -> list[dict[str, Any]]:
    """
    Returns total consumption per article for the period.

    Args:
        period_id: The period to query.
        revenue_filter: 'all' for all POS items, 'umsatz' for revenue items only
            (tisch_bondetail_istUmsatz = TRUE), 'aufwand' for expense items only
            (tisch_bondetail_istUmsatz = FALSE).
        include_lm_data: Whether to include manually recorded StockMovement consumption.
    """
    from .article_enrichment import enrich_with_article_data

    if revenue_filter == 'umsatz':
        ist_umsatz_filter = 'AND tbd."tisch_bondetail_istUmsatz" = TRUE'
    elif revenue_filter == 'aufwand':
        ist_umsatz_filter = 'AND tbd."tisch_bondetail_istUmsatz" = FALSE'
    else:
        ist_umsatz_filter = ''

    query = (
        _TOTALS_QUERY_RECIPE.format(ist_umsatz_filter=ist_umsatz_filter)
        + "\n    UNION ALL\n"
        + _TOTALS_QUERY_DIRECT.format(ist_umsatz_filter=ist_umsatz_filter)
    )

    totals: dict[str, float] = {}
    with connection.cursor() as cur:
        cur.execute(query, {'period_id': period_id})
        for article_name, amount in cur.fetchall():
            totals[article_name] = totals.get(article_name, 0.0) + float(amount)

    if include_lm_data:
        for article_name, amount in _get_lm_consumption_totals(period_id).items():
            totals[article_name] = totals.get(article_name, 0.0) + amount

    rows: list[dict[str, Any]] = [
        {'article': name, 'total': round(total, 3)}
        for name, total in sorted(totals.items())
    ]
    return enrich_with_article_data(rows, period_id, quantity_key='total')
