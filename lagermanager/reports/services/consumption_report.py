"""
Consumption report — cumulative daily consumption per article.
"""
import datetime
from typing import Any

from core.models import Period
from inventory.services.stock_calculation import get_daily_consumption


def get_consumption_chart_data(period_id: int) -> dict[str, Any]:
    """
    Returns cumulative Chart.js dataset for consumption over the period.
    """
    period = Period.objects.get(pk=period_id)
    daily = get_daily_consumption(period_id)

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
            cumulative[article] += daily.get(current_date, {}).get(article, 0.0)
        rows.append({a: round(cumulative[a], 3) for a in all_articles})
        current_date += datetime.timedelta(days=1)

    datasets = [
        {'label': a, 'data': [row[a] for row in rows]}
        for a in all_articles
    ]

    return {'labels': dates, 'datasets': datasets}
