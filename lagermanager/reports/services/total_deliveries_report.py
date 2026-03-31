"""
Total deliveries report — aggregated by article with purchase price.
"""
from decimal import Decimal
from enum import StrEnum

from core.models import Period
from core.services.purchase_price import get_purchase_price
from deliveries.models import StockMovement, StockMovementDetail
from django.db.models import DecimalField, ExpressionWrapper, F, Sum
from django.db.models.functions import TruncMonth, TruncYear
from pos_import.models import WarehouseArticle


class DateGrouping(StrEnum):
    YEAR = 'year'
    YEAR_MONTH = 'year_month'


def get_total_deliveries_report(
    period_id: int,
    date_grouping: DateGrouping | None = None,
    group_by_partner: bool = False,
) -> dict[str, object]:
    """
    Returns deliveries aggregated by article with total quantity, total value,
    and weighted-average purchase price (EK) per article.

    Args:
        period_id: The period to report on.
        date_grouping: When set, adds a date bucket to each row grouped by
            year (``DateGrouping.YEAR``) or year-month (``DateGrouping.YEAR_MONTH``).
            When ``None`` the period year is used as a single date label.
        group_by_partner: When ``True``, the result is additionally grouped by
            the movement partner (supplier).
    """
    period: Period = Period.objects.get(pk=period_id)
    fallback_year: str = period.name

    qs = StockMovementDetail.objects.filter(
        stock_movement__period_id=period_id,
        stock_movement__movement_type=StockMovement.Type.DELIVERY,
    )

    group_fields: list[str] = ['article_id', 'article__name']

    if date_grouping == DateGrouping.YEAR:
        qs = qs.annotate(_date_bucket=TruncYear('stock_movement__date'))
        group_fields.insert(0, '_date_bucket')
    elif date_grouping == DateGrouping.YEAR_MONTH:
        qs = qs.annotate(_date_bucket=TruncMonth('stock_movement__date'))
        group_fields.insert(0, '_date_bucket')

    if group_by_partner:
        group_fields += ['stock_movement__partner_id',
                         'stock_movement__partner__name']

    details = (
        qs
        .values(*group_fields)
        .annotate(
            total_quantity=Sum('quantity'),
            total_value=Sum(
                ExpressionWrapper(
                    F('quantity') * F('unit_price'),
                    output_field=DecimalField(max_digits=18, decimal_places=4),
                )
            ),
        )
        .order_by(*[f for f in group_fields if f != 'article_id'])
    )

    unit_map: dict[int, str] = {
        wa.article_id: wa.unit.name if wa.unit else ''
        for wa in WarehouseArticle.objects.filter(period_id=period_id).select_related('unit')
    }

    rows: list[dict[str, object]] = []
    for d in details:
        article_pk: int = d['article_id']
        avg_price: Decimal = get_purchase_price(article_pk, period_id)

        if date_grouping == DateGrouping.YEAR:
            date_label = d['_date_bucket'].strftime('%Y')
        elif date_grouping == DateGrouping.YEAR_MONTH:
            date_label = d['_date_bucket'].strftime('%Y-%m')
        else:
            date_label = fallback_year

        row: dict[str, object] = {
            'date': date_label,
            'article': d['article__name'],
            'quantity': float(d['total_quantity'] or 0),
            'unit': unit_map.get(article_pk, ''),
            'total_value': float(d['total_value'] or 0),
            'avg_price': float(avg_price),
        }

        if group_by_partner:
            row['partner_id'] = d['stock_movement__partner_id']
            row['partner'] = d['stock_movement__partner__name']

        rows.append(row)

    return {'deliveries': rows}
