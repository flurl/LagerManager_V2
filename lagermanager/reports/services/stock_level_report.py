"""
Stock level report — wraps inventory.services.stock_calculation.compute_running_stock
into Chart.js-compatible format.
"""
from typing import Any

from inventory.services.stock_calculation import compute_running_stock


def get_stock_level_chart_data(period_id: int) -> dict[str, Any]:
    """
    Returns Chart.js dataset structure:
    {
        labels: [dates],
        datasets: [{label: article_name, data: [stock values]}, ...]
        counted_datasets: [{label: article_name + '-gezaehlt', data: [...]}]
    }
    """
    records: list[dict[str, Any]] = compute_running_stock(period_id)

    # Collect unique dates and articles
    dates: list[str] = sorted(set(r['date'] for r in records))
    articles: list[str] = sorted(set(r['article'] for r in records))

    # Build lookup {date: {article: record}}
    lookup: dict[str, dict[str, dict[str, Any]]] = {}
    for r in records:
        lookup.setdefault(r['date'], {})[r['article']] = r

    datasets = []
    counted_datasets = []

    for article in articles:
        stock_data = [lookup.get(d, {}).get(article, {}).get('stock') for d in dates]
        counted_data = [lookup.get(d, {}).get(article, {}).get('counted') for d in dates]

        datasets.append({'label': article, 'data': stock_data})
        counted_datasets.append({'label': f"{article}-gezaehlt", 'data': counted_data})

    return {
        'labels': dates,
        'datasets': datasets,
        'counted_datasets': counted_datasets,
    }
