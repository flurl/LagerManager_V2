"""
Total deliveries report — aggregated by article with purchase price.
"""
from decimal import Decimal

from core.models import Period
from core.services.purchase_price import get_purchase_price
from deliveries.models import StockMovement, StockMovementDetail
from django.db.models import DecimalField, ExpressionWrapper, F, Sum
from pos_import.models import WarehouseArticle


def get_total_deliveries_report(period_id: int) -> dict[str, object]:
    """
    Returns deliveries aggregated by article with total quantity, total value,
    and weighted-average purchase price (EK) per article.
    """
    period: Period = Period.objects.get(pk=period_id)
    year: str = str(period.checkpoint_year or period.start.year)

    details = (
        StockMovementDetail.objects
        .filter(
            stock_movement__period_id=period_id,
            stock_movement__movement_type=StockMovement.Type.DELIVERY,
        )
        .values('article_id', 'article__name')
        .annotate(
            total_quantity=Sum('quantity'),
            total_value=Sum(
                ExpressionWrapper(
                    F('quantity') * F('unit_price'),
                    output_field=DecimalField(max_digits=18, decimal_places=4),
                )
            ),
        )
        .order_by('article__name')
    )

    unit_map: dict[int, str] = {
        wa.article_id: wa.unit.name if wa.unit else ''
        for wa in WarehouseArticle.objects.filter(period_id=period_id).select_related('unit')
    }

    rows: list[dict[str, object]] = []
    for d in details:
        article_pk: int = d['article_id']
        avg_price: Decimal = get_purchase_price(article_pk, period_id)
        rows.append({
            'date': year,
            'article': d['article__name'],
            'quantity': float(d['total_quantity'] or 0),
            'unit': unit_map.get(article_pk, ''),
            'total_value': float(d['total_value'] or 0),
            'avg_price': float(avg_price),
        })

    return {'deliveries': rows}
