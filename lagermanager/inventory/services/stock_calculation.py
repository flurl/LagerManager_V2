"""
Stock calculation service.

Current Stock[day] = Initial Inventory + Σ Deliveries[1..day] - Σ Consumption[1..day]

The consumption query is the UNION of:
  1. Recipe-based consumption: bondetail_amount * recipe_qty / unit_multiplier
  2. Direct consumption: bondetail_amount (articles with no recipe)
"""
import datetime
import logging

from django.db import connection

logger = logging.getLogger(__name__)

CONSUMPTION_QUERY = """
    SELECT
        checkpoint_datum::date AS day,
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
        checkpoint_datum::date AS day,
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


def get_daily_consumption(period_id: int) -> dict[datetime.date, dict[str, float]]:
    """
    Returns {date: {article_name: amount}} for all consumption in the period.
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


def get_daily_deliveries(period_id: int) -> dict[datetime.date, dict[str, float]]:
    """
    Returns {date: {article_name: amount}} for all deliveries in the period.
    """
    from core.models import Period
    from deliveries.models import StockMovement

    period = Period.objects.get(pk=period_id)
    result: dict[datetime.date, dict[str, float]] = {}
    deliveries = StockMovement.objects.filter(
        period=period, movement_type=StockMovement.Type.DELIVERY
    ).prefetch_related('details__article')

    for delivery in deliveries:
        day = delivery.date
        for detail in delivery.details.all():
            name = detail.article.name
            day_data = result.setdefault(day, {})
            day_data[name] = day_data.get(name, 0) + float(detail.quantity)
    return result


def compute_running_stock(period_id: int) -> list[dict[str, object]]:
    """
    Compute day-by-day running stock for all articles in the period.

    Returns list of {date, article_name, stock, counted, diff} records.
    """
    from core.models import Period

    from inventory.models import PhysicalCount, PeriodStartStockLevel

    period = Period.objects.get(pk=period_id)

    # Initial stock (day 0)
    initial: dict[str, float] = {}
    for sl in PeriodStartStockLevel.objects.filter(period=period).select_related('article'):
        initial[sl.article.name] = float(sl.quantity)

    daily_deliveries: dict[datetime.date,
                           dict[str, float]] = get_daily_deliveries(period_id)
    daily_consumption: dict[datetime.date,
                            dict[str, float]] = get_daily_consumption(period_id)

    # Physical counts keyed by (date, article_name)
    counts: dict[tuple[datetime.date, str], float] = {}
    for pc in PhysicalCount.objects.filter(period=period).select_related('article'):
        counts[(pc.date.date(), pc.article.name)] = float(pc.quantity)

    # Build set of all articles
    all_articles = set(initial.keys())
    for day_data in daily_deliveries.values():
        all_articles.update(day_data.keys())
    for day_data in daily_consumption.values():
        all_articles.update(day_data.keys())

    # Iterate day by day
    current_date = period.start.date()
    end_date = period.end.date()
    running: dict[str, float] = {a: initial.get(a, 0.0) for a in all_articles}
    result = []

    while current_date <= end_date:
        for article in all_articles:
            running[article] = (
                running[article]
                + daily_deliveries.get(current_date, {}).get(article, 0.0)
                - daily_consumption.get(current_date, {}).get(article, 0.0)
            )
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
