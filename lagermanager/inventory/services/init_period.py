"""
Init period services — bulk-create zero entries for warehouse articles.
"""
import datetime as dt
from decimal import Decimal

from pos_import.models import WarehouseArticle
from core.models import Location, Period
from django.db import transaction


def init_stock_levels(period_id: int) -> int:
    """
    Create PeriodStartStockLevel entries (quantity=0) for all warehouse articles
    in the given period that don't already have an entry.
    Returns the number of entries created.
    """
    from inventory.models import PeriodStartStockLevel

    period = Period.objects.get(pk=period_id)
    existing = set(
        PeriodStartStockLevel.objects.filter(
            period=period).values_list('article__source_id', flat=True)
    )
    warehouse_articles = WarehouseArticle.objects.filter(
        period=period
    ).select_related('article')

    to_create = []
    for wa in warehouse_articles:
        if wa.article.source_id not in existing:
            to_create.append(PeriodStartStockLevel(
                article=wa.article,
                quantity=0,
                period=period,
            ))

    with transaction.atomic():
        PeriodStartStockLevel.objects.bulk_create(
            to_create, ignore_conflicts=True)
    return len(to_create)


def init_initial_inventory(period_id: int, source_period_id: int | None = None) -> int:
    """
    Create InitialInventory entries for the given period.
    If source_period_id is provided, copies quantities from that period.
    Otherwise creates zero entries for all article/location combinations.
    Returns the number of entries created.
    """
    from inventory.models import InitialInventory

    period = Period.objects.get(pk=period_id)

    warehouse_articles = WarehouseArticle.objects.filter(
        period=period
    ).select_related('article')
    locations = list(Location.objects.all())
    existing = set(
        InitialInventory.objects.filter(period=period).values_list(
            'article__source_id', 'location_id'
        )
    )

    source_quantities: dict[tuple[int, int], Decimal] = {}
    if source_period_id:
        for entry in InitialInventory.objects.filter(period_id=source_period_id).select_related('article'):
            source_quantities[(entry.article.source_id,
                               entry.location_id)] = entry.quantity

    to_create = []
    for wa in warehouse_articles:
        for loc in locations:
            key = (wa.article.source_id, loc.pk)
            if key not in existing:
                quantity: Decimal = source_quantities.get(key, Decimal(0))
                to_create.append(InitialInventory(
                    article=wa.article,
                    quantity=quantity,
                    location=loc,
                    period=period,
                ))

    with transaction.atomic():
        InitialInventory.objects.bulk_create(to_create, ignore_conflicts=True)
    return len(to_create)


def init_physical_count_date(period_id: int, count_date: dt.datetime) -> int:
    """
    Create PhysicalCount entries (quantity=0) for all warehouse articles
    for the given date, if they don't already exist.
    """
    from inventory.models import PhysicalCount

    period = Period.objects.get(pk=period_id)

    warehouse_articles = WarehouseArticle.objects.filter(
        period=period
    ).select_related('article')

    existing = set(
        PhysicalCount.objects.filter(
            period=period, date__date=count_date.date()
        ).values_list('article__source_id', flat=True)
    )

    to_create = []
    for wa in warehouse_articles:
        if wa.article.source_id not in existing:
            to_create.append(PhysicalCount(
                date=count_date,
                article=wa.article,
                quantity=0,
                period=period,
            ))

    with transaction.atomic():
        PhysicalCount.objects.bulk_create(to_create, ignore_conflicts=True)
    return len(to_create)
