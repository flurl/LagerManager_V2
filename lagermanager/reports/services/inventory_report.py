"""
Inventory report service (Inventur).
Returns {article_name, quantity, purchase_price, total_value} per article.
"""
from core.services.purchase_price import get_purchase_price
from inventory.models import PeriodStartStockLevel


def get_inventory_report(period_id: int) -> list[dict[str, object]]:
    """
    For each article with a stock level in the period, compute
    quantity * purchase_price and return a list of dicts.
    """
    rows = []
    stock_levels = PeriodStartStockLevel.objects.filter(
        period_id=period_id
    ).select_related('article').order_by('article__name')

    for sl in stock_levels:
        price = get_purchase_price(sl.article.source_id, period_id)
        rows.append({
            'article_id': sl.article.source_id,
            'article_name': sl.article.name,
            'quantity': float(sl.quantity),
            'purchase_price': float(price),
            'total_value': float(sl.quantity * price),
        })
    return rows
