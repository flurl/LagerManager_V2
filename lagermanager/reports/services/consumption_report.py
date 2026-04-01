"""
Consumption report — cumulative daily consumption per article.

Consumption is the sum of:
  - POS/Wiffzack consumption (via get_daily_pos_consumption)
  - Manually recorded consumption StockMovements (via get_daily_movements)
"""
import datetime
from typing import Any

from core.models import Period
from deliveries.models import StockMovement
from inventory.services.stock_calculation import (
    get_daily_movements,
    get_daily_pos_consumption,
)


def get_consumption_chart_data(period_id: int) -> dict[str, Any]:
    """
    Returns cumulative Chart.js dataset for consumption over the period.
    """
    period = Period.objects.get(pk=period_id)
    pos_daily: dict[datetime.date, dict[str, float]] = get_daily_pos_consumption(period_id)
    manual_daily: dict[datetime.date, dict[str, float]] = get_daily_movements(
        period_id, (StockMovement.Type.CONSUMPTION,)
    )

    # Merge manual consumption into POS consumption
    daily: dict[datetime.date, dict[str, float]] = dict(pos_daily)
    for day, articles in manual_daily.items():
        day_data = daily.setdefault(day, {})
        for article, amount in articles.items():
            day_data[article] = day_data.get(article, 0.0) + amount

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
            cumulative[article] += daily.get(current_date,
                                             {}).get(article, 0.0)
        rows.append({a: round(cumulative[a], 3) for a in all_articles})
        current_date += datetime.timedelta(days=1)

    datasets: list[dict[str, Any]] = [
        {'label': a, 'data': [row[a] for row in rows]}
        for a in all_articles
    ]

    return {'labels': dates, 'datasets': datasets}


def get_consumption_totals(period_id: int) -> list[dict[str, Any]]:
    """
    Returns total consumption per article for the period.
    Derived from get_consumption_chart_data: the last cumulative value per dataset is the total.
    Each record includes: article, total, purchase_price, total_value,
    warehouse_unit, warehouse_unit_multiplier.
    """
    from .article_enrichment import enrich_with_article_data

    chart_data: dict[str, Any] = get_consumption_chart_data(period_id)
    rows: list[dict[str, Any]] = [
        {'article': ds['label'], 'total': ds['data'][-1] if ds['data'] else 0.0}
        for ds in chart_data['datasets']
    ]
    return enrich_with_article_data(rows, period_id, quantity_key='total')
