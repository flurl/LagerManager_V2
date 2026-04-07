"""
Stock level report — wraps inventory.services.stock_calculation.compute_running_stock
into Chart.js-compatible format.
"""
from typing import Any

from inventory.services.stock_calculation import compute_running_stock

# TODO: this report is just plain wrong, must be fixed


def _get_movement_meta(period_id: int) -> dict[str, dict[str, list[dict[str, Any]]]]:
    """
    Returns {date_str: {article_name: [{partner, type, quantity}, ...]}} for all
    StockMovements (deliveries and consumptions) in the period.
    Used to enrich the chart tooltip with movement details.
    """
    from core.models import Period
    from deliveries.models import StockMovement

    period = Period.objects.get(pk=period_id)
    movements = (
        StockMovement.objects
        .filter(period=period)
        .select_related('partner')
        .prefetch_related('details__article')
    )

    meta: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for movement in movements:
        date_str: str = movement.date.isoformat()
        partner_name: str = movement.partner.name
        movement_type: str = movement.movement_type
        for detail in movement.details.all():
            article_name: str = detail.article.name
            meta.setdefault(date_str, {}).setdefault(article_name, []).append({
                'partner': partner_name,
                'type': movement_type,
                'quantity': float(detail.quantity),
            })
    return meta


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
        stock_data = [lookup.get(d, {}).get(
            article, {}).get('stock') for d in dates]
        counted_data = [lookup.get(d, {}).get(
            article, {}).get('counted') for d in dates]

        datasets.append({'label': article, 'data': stock_data})
        counted_datasets.append(
            {'label': f"{article}-gezaehlt", 'data': counted_data})

    return {
        'labels': dates,
        'datasets': datasets,
        'counted_datasets': counted_datasets,
        'movement_meta': _get_movement_meta(period_id),
    }


def get_current_stock_levels(period_id: int) -> list[dict[str, Any]]:
    """
    Returns the current stock level for each article — i.e. the running stock
    accumulated from the start of the period up to the most recent date with data.

    Builds on get_stock_level_chart_data() and extracts the last date's value
    from each dataset, returning a flat list of records sorted by article name.
    Each record includes: article, stock, purchase_price, total_value,
    warehouse_unit, warehouse_unit_multiplier.
    """
    from .article_enrichment import enrich_with_article_data

    chart_data: dict[str, Any] = get_stock_level_chart_data(period_id)
    if not chart_data['labels']:
        return []

    rows: list[dict[str, Any]] = [
        {'article': ds['label'], 'stock': ds['data'][-1]}
        for ds in chart_data['datasets']
        if ds['data'] and ds['data'][-1] is not None
    ]
    rows.sort(key=lambda r: r['article'])
    return enrich_with_article_data(rows, period_id, quantity_key='stock')
