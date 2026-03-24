"""
Init period services — bulk-create zero entries for warehouse articles.
"""
from pos_import.models import WarehouseArticle
from core.models import Period, Workplace
from django.db import transaction


def init_stock_levels(period_id: int) -> int:
    """
    Create StockLevel entries (quantity=0) for all warehouse articles
    in the given period that don't already have an entry.
    Returns the number of entries created.
    """
    from inventory.models import StockLevel

    period = Period.objects.get(pk=period_id)
    existing = set(
        StockLevel.objects.filter(period=period).values_list('article__source_id', flat=True)
    )
    warehouse_articles = WarehouseArticle.objects.filter(
        period=period
    ).select_related('article').distinct('article__source_id')

    to_create = []
    seen = set()
    for wa in warehouse_articles:
        art_source_id = wa.article.source_id
        if art_source_id not in existing and art_source_id not in seen:
            seen.add(art_source_id)
            to_create.append(StockLevel(
                article=wa.article,
                quantity=0,
                period=period,
            ))

    with transaction.atomic():
        StockLevel.objects.bulk_create(to_create, ignore_conflicts=True)
    return len(to_create)


def init_initial_inventory(period_id: int, source_period_id: int = None) -> int:
    """
    Create InitialInventory entries for the given period.
    If source_period_id is provided, copies quantities from that period.
    Otherwise creates zero entries for all article/workplace combinations.
    Returns the number of entries created.
    """
    from inventory.models import InitialInventory

    period = Period.objects.get(pk=period_id)

    if source_period_id:
        source_entries = InitialInventory.objects.filter(period_id=source_period_id)
        to_create = []
        for entry in source_entries:
            to_create.append(InitialInventory(
                article=entry.article,
                quantity=entry.quantity,
                workplace=entry.workplace,
                period=period,
            ))
    else:
        warehouse_articles = WarehouseArticle.objects.filter(
            period=period
        ).select_related('article')
        workplaces = list(Workplace.objects.all())
        existing = set(
            InitialInventory.objects.filter(period=period).values_list(
                'article__source_id', 'workplace_id'
            )
        )
        to_create = []
        for wa in warehouse_articles:
            for wp in workplaces:
                key = (wa.article.source_id, wp.pk)
                if key not in existing:
                    to_create.append(InitialInventory(
                        article=wa.article,
                        quantity=0,
                        workplace=wp,
                        period=period,
                    ))

    with transaction.atomic():
        InitialInventory.objects.bulk_create(to_create, ignore_conflicts=True)
    return len(to_create)


def init_physical_count_date(period_id: int, date: str) -> int:
    """
    Create PhysicalCount entries (quantity=0) for all warehouse articles
    for the given date, if they don't already exist.
    """
    import datetime as dt

    from inventory.models import PhysicalCount

    period = Period.objects.get(pk=period_id)
    count_date = dt.datetime.fromisoformat(date)

    warehouse_articles = WarehouseArticle.objects.filter(
        period=period
    ).select_related('article').distinct('article__source_id')

    existing = set(
        PhysicalCount.objects.filter(
            period=period, date__date=count_date.date()
        ).values_list('article__source_id', flat=True)
    )

    to_create = []
    seen = set()
    for wa in warehouse_articles:
        art_source_id = wa.article.source_id
        if art_source_id not in existing and art_source_id not in seen:
            seen.add(art_source_id)
            to_create.append(PhysicalCount(
                date=count_date,
                article=wa.article,
                quantity=0,
                period=period,
            ))

    with transaction.atomic():
        PhysicalCount.objects.bulk_create(to_create, ignore_conflicts=True)
    return len(to_create)
