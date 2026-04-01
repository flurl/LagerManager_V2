"""
Shared helper to enrich report rows with article metadata:
purchase price, total value, warehouse unit name, and unit multiplier.
"""
from decimal import Decimal
from typing import Any

from core.services.purchase_price import get_purchase_price
from pos_import.models import Article, WarehouseArticle


def enrich_with_article_data(
    rows: list[dict[str, Any]],
    period_id: int,
    quantity_key: str,
) -> list[dict[str, Any]]:
    """
    Enriches each row (which must have an 'article' key containing the article name)
    with purchase_price, total_value, warehouse_unit, and warehouse_unit_multiplier.

    Rows without a matching Article are left with None for all enrichment fields.
    """
    # Build name → article pk lookup
    name_to_pk: dict[str, int] = {
        a.name: a.pk
        for a in Article.objects.filter(period_id=period_id).only('id', 'name')
    }

    # Build article pk → (unit_name, unit_multiplier) lookup
    wa_lookup: dict[int, tuple[str | None, Decimal | None]] = {}
    for wa in (
        WarehouseArticle.objects.filter(period_id=period_id)
        .select_related('unit')
        .only('article_id', 'unit__name', 'unit__multiplier')
    ):
        unit_name: str | None = wa.unit.name if wa.unit else None
        unit_mult: Decimal | None = wa.unit.multiplier if wa.unit else None
        wa_lookup[wa.article_id] = (unit_name, unit_mult)

    result: list[dict[str, Any]] = []
    for row in rows:
        article_pk: int | None = name_to_pk.get(row['article'])
        if article_pk is None:
            result.append({
                **row,
                'purchase_price': None,
                'total_value': None,
                'warehouse_unit': None,
                'warehouse_unit_multiplier': None,
            })
            continue

        purchase_price: Decimal = get_purchase_price(article_pk, period_id)
        quantity: float = row.get(quantity_key) or 0.0
        total_value: Decimal = (purchase_price * Decimal(str(quantity))).quantize(Decimal('0.0001'))

        unit_name, unit_mult = wa_lookup.get(article_pk, (None, None))
        result.append({
            **row,
            'purchase_price': float(purchase_price),
            'total_value': float(total_value),
            'warehouse_unit': unit_name,
            'warehouse_unit_multiplier': float(unit_mult) if unit_mult is not None else None,
        })

    return result
