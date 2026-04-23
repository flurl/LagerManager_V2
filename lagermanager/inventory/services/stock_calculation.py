"""
Stock calculation service.

Current Stock[day] = Initial Inventory + Σ Deliveries[1..day] - Σ Consumption[1..day]

Consumption has two sources:
  1. POS/Wiffzack consumption (get_daily_pos_consumption): raw SQL UNION of recipe-based
     and direct consumption from POS import tables.
  2. Manual consumption (get_daily_movements with CONSUMPTION type): StockMovement records
     entered manually in the app.
"""
import datetime
import logging
from collections.abc import Sequence

from django.db import connection

logger = logging.getLogger(__name__)

CONSUMPTION_QUERY = """
    SELECT
        to_date(checkpoint_info, 'DD.MM.YYYY') AS day,
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
    GROUP BY day, art2.artikel_bezeichnung

    UNION ALL

    SELECT
        to_date(checkpoint_info, 'DD.MM.YYYY') AS day,
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
    GROUP BY day, a.artikel_bezeichnung
"""


def get_daily_pos_consumption(period_id: int) -> dict[datetime.date, dict[str, float]]:
    """
    Returns {date: {article_name: amount}} for POS/Wiffzack consumption in the period.
    Uses recipe decomposition for articles with recipes, direct amounts otherwise.
    """
    result: dict[datetime.date, dict[str, float]] = {}
    with connection.cursor() as cur:
        params = {'period_id': period_id}
        logger.debug("CONSUMPTION_QUERY (period_id=%s):\n%s",
                     period_id, cur.mogrify(CONSUMPTION_QUERY, params).decode())
        cur.execute(CONSUMPTION_QUERY, params)
        rows = cur.fetchall()
        logger.debug("CONSUMPTION_QUERY returned %d rows", len(rows))
        for row in rows:
            day, article, amount = row
            day_data = result.setdefault(day, {})
            day_data[article] = day_data.get(article, 0) + float(amount)
    return result


def get_daily_movements(
    period_id: int,
    movement_types: Sequence[str],
) -> dict[datetime.date, dict[str, float]]:
    """
    Returns {date: {article_name: amount}} for StockMovements of the given types.

    Quantities are always positive — the caller is responsible for applying the correct
    sign (add for DELIVERY, subtract for CONSUMPTION).
    """
    from core.models import Period
    from deliveries.models import StockMovement

    period = Period.objects.get(pk=period_id)
    result: dict[datetime.date, dict[str, float]] = {}
    movements = StockMovement.objects.filter(
        period=period, movement_type__in=movement_types
    ).prefetch_related('details__article')

    for movement in movements:
        day = movement.date
        for detail in movement.details.all():
            name = detail.article.name
            day_data = result.setdefault(day, {})
            day_data[name] = day_data.get(name, 0) + float(detail.quantity)
    return result


def get_daily_stock_delta(
    period_id: int,
    movement_types: Sequence[str] = (),
) -> dict[datetime.date, dict[str, float]]:
    """
    Returns {date: {article_name: stock_delta}} where positive means stock increases
    (delivery) and negative means stock decreases (consumption).

    POS/Wiffzack consumption is always included as a negative base.
    DELIVERY movements add to the delta; CONSUMPTION movements subtract.

    Pass movement_types=() for POS consumption only.
    """
    from deliveries.models import StockMovement

    _SIGNS: dict[str, float] = {
        StockMovement.Type.CONSUMPTION: -1.0,
        StockMovement.Type.DELIVERY: 1.0,
    }
    for mt in movement_types:
        if mt not in _SIGNS:
            raise ValueError(
                f"Unsupported movement_type {mt!r} for get_daily_stock_delta. "
                f"Allowed: {list(_SIGNS)}"
            )

    pos = get_daily_pos_consumption(period_id)
    result: dict[datetime.date, dict[str, float]] = {
        day: {article: -amount for article, amount in articles.items()}
        for day, articles in pos.items()
    }

    for movement_type in movement_types:
        sign = _SIGNS[movement_type]
        for day, articles in get_daily_movements(period_id, (movement_type,)).items():
            day_data = result.setdefault(day, {})
            for article, amount in articles.items():
                day_data[article] = day_data.get(article, 0.0) + sign * amount

    return result


def compute_running_stock(period_id: int) -> list[dict[str, object]]:
    """
    Compute day-by-day running stock for all articles in the period.

    Returns list of {date, article_name, stock, counted, diff} records.
    """
    from core.models import Period
    from deliveries.models import StockMovement

    from inventory.models import PeriodStartStockLevel, PhysicalCount

    period = Period.objects.get(pk=period_id)

    # Initial stock (day 0)
    initial: dict[str, float] = {}
    for sl in PeriodStartStockLevel.objects.filter(period=period).select_related('article'):
        initial[sl.article.name] = float(sl.quantity)

    daily_delta: dict[datetime.date, dict[str, float]] = get_daily_stock_delta(
        period_id, (StockMovement.Type.CONSUMPTION,
                    StockMovement.Type.DELIVERY)
    )

    # Physical counts keyed by (date, article_name)
    counts: dict[tuple[datetime.date, str], float] = {}
    for pc in PhysicalCount.objects.filter(period=period).select_related('article'):
        counts[(pc.date.date(), pc.article.name)] = float(pc.quantity)

    # Build set of all articles
    all_articles: set[str] = set(initial.keys())
    for day_data in daily_delta.values():
        all_articles.update(day_data.keys())

    # Iterate day by day
    current_date = period.start.date()
    end_date = period.end.date()
    running: dict[str, float] = {a: initial.get(a, 0.0) for a in all_articles}
    result = []

    while current_date <= end_date:
        for article in all_articles:
            running[article] += daily_delta.get(current_date,
                                                {}).get(article, 0.0)
            counted = counts.get((current_date, article))
            result.append({
                'date': current_date.isoformat(),
                'article': article,
                'stock': round(running[article], 3),
                'counted': counted,
                'diff': round(counted - running[article], 3) if counted is not None else None,
            })
        current_date += datetime.timedelta(days=1)

    return result
