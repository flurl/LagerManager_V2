import datetime as dt
from collections import defaultdict
from decimal import Decimal
from typing import Any, cast

from core.models import Period
from core.services.period import get_period_for_datetime
from inventory.models import PhysicalCount
from pos_import.models import Article, ArticleMeta, WarehouseArticle

from .models import StockCountEntry


def get_expanded_articles(period_id: int, include_base: bool = True) -> list[dict[str, str | Decimal | None]]:
    """
    Return all countable articles for a period, expanded with sub_articles from ArticleMeta.

    For an article with sub_articles="lemon,orange" and include_base=True (default):
      - Base row:      article_id="123",        article_name="Cola"
      - Sub row:       article_id="123-lemon",   article_name="Cola-lemon"
      - Sub row:       article_id="123-orange",  article_name="Cola-orange"

    With include_base=False the base row is omitted for articles that have sub_articles,
    so only the sub-article rows are returned for those articles.
    Articles without sub_articles are always included regardless of include_base.

    Hidden articles (ArticleMeta.is_hidden=True) are excluded entirely.
    Articles without any ArticleMeta are included as-is.
    """
    warehouse_articles = (
        WarehouseArticle.objects
        .select_related('article')
        .filter(period_id=period_id)
    )

    meta_by_source_id: dict[int, ArticleMeta] = {
        m.source_id: m
        for m in ArticleMeta.objects.filter(period_id=period_id)
    }

    rows: list[dict[str, str | Decimal | None]] = []
    for wa in warehouse_articles:
        source_id = wa.article.source_id
        name = wa.article.name
        meta = meta_by_source_id.get(source_id)

        if meta is not None and meta.is_hidden:
            continue

        package_size: Decimal | None = meta.package_size if meta is not None else None
        has_subs = meta is not None and bool(meta.sub_articles)
        if include_base or not has_subs:
            rows.append({'article_id': str(source_id), 'article_name': name, 'package_size': package_size})

        if has_subs:
            for sub in (s.strip() for s in meta.sub_articles.split(',') if s.strip()):  # type: ignore[union-attr]
                rows.append({
                    'article_id': f'{source_id}-{sub}',
                    'article_name': f'{name}-{sub}',
                    'package_size': package_size,
                })

    rows.sort(key=lambda r: cast(str, r['article_name']).lower())
    return rows


def _aggregate_quantities(entries: list[StockCountEntry]) -> dict[int, Decimal]:
    """Aggregate entry quantities by base source_id (strips sub-article suffix like '102-lemon' → 102)."""
    quantities: dict[int, Decimal] = {}
    for entry in entries:
        try:
            source_id = int(entry.article_id.split('-')[0])
        except (ValueError, IndexError):
            continue
        quantities[source_id] = quantities.get(source_id, Decimal(0)) + Decimal(entry.quantity)
    return quantities


def _write_physical_counts(
    quantities: dict[int, Decimal],
    count_date: dt.datetime,
    period: Period,
) -> dict[str, Any]:
    """Create or update PhysicalCount records from a quantities dict. Returns counts and not_found list."""
    article_by_source_id: dict[int, Article] = {
        a.source_id: a
        for a in Article.objects.filter(source_id__in=list(quantities.keys()), period=period)
    }

    created = 0
    updated = 0
    not_found: list[int] = []

    for source_id, qty in quantities.items():
        article: Article | None = article_by_source_id.get(source_id)
        if article is None:
            not_found.append(source_id)
            continue

        existing: PhysicalCount | None = PhysicalCount.objects.filter(
            article=article,
            period=period,
            date__date=count_date.date(),
        ).first()

        if existing:
            existing.quantity = qty
            existing.save(update_fields=['quantity', 'updated_at'])
            updated += 1
        else:
            PhysicalCount.objects.create(
                article=article,
                date=count_date,
                quantity=qty,
                period=period,
            )
            created += 1

    return {'created': created, 'updated': updated, 'not_found': not_found}


def import_stock_count_entries(
    entry_ids: list[int],
    force: bool = False,
) -> dict[str, Any]:
    """
    Import StockCountEntry records into PhysicalCount.

    Sub-article entries (e.g. article_id='102-lemon') are aggregated into their
    base article (source_id=102) before creating PhysicalCount records.

    Returns:
      {'status': 'ok', 'created': N, 'updated': N, 'not_found': [source_ids]}
      {'status': 'conflict', 'existing_count': N, 'date': 'YYYY-MM-DD'}
      {'status': 'error', 'error': '...'}
    """
    entries: list[StockCountEntry] = list(StockCountEntry.objects.filter(pk__in=entry_ids))
    if not entries:
        return {'status': 'error', 'error': 'No entries found'}

    count_date = entries[0].count_date

    period: Period | None = get_period_for_datetime(count_date)
    if period is None:
        return {'status': 'error', 'error': f'No period found for date {count_date.date()}'}

    quantities = _aggregate_quantities(entries)

    if not force:
        conflict_count = PhysicalCount.objects.filter(
            period=period,
            date__date=count_date.date(),
        ).count()
        if conflict_count > 0:
            return {
                'status': 'conflict',
                'existing_count': conflict_count,
                'date': str(count_date.date()),
            }

    result = _write_physical_counts(quantities, count_date, period)
    return {'status': 'ok', **result}


def import_stock_count_entries_for_date(
    date_str: str,
    force: bool = False,
) -> dict[str, Any]:
    """
    Import all StockCountEntry records for a given date (YYYY-MM-DD) into PhysicalCount,
    accumulating quantities across all locations.

    Issues warnings if any location has entries with more than one distinct count_date on that day.

    Returns:
      {'status': 'ok', 'created': N, 'updated': N, 'not_found': [source_ids], 'warnings': [...]}
      {'status': 'conflict', 'existing_count': N, 'date': 'YYYY-MM-DD', 'warnings': [...]}
      {'status': 'error', 'error': '...'}
    """
    try:
        count_date_date = dt.date.fromisoformat(date_str)
    except ValueError:
        return {'status': 'error', 'error': f'Invalid date: {date_str}'}

    entries: list[StockCountEntry] = list(
        StockCountEntry.objects.filter(count_date__date=count_date_date)
    )
    if not entries:
        return {'status': 'error', 'error': f'No entries found for date {date_str}'}

    # Use the earliest count_date as the representative datetime for the PhysicalCount record
    count_date = min(e.count_date for e in entries)

    period: Period | None = get_period_for_datetime(count_date)
    if period is None:
        return {'status': 'error', 'error': f'No period found for date {date_str}'}

    # Warn if any location has multiple distinct count_dates on this day
    dates_by_location: dict[int, set[dt.datetime]] = defaultdict(set)
    names_by_location: dict[int, str] = {}
    for entry in entries:
        dates_by_location[entry.location_id].add(entry.count_date)
        names_by_location[entry.location_id] = entry.location_name

    warnings: list[str] = []
    for location_id, dates in dates_by_location.items():
        if len(dates) > 1:
            name = names_by_location[location_id]
            warnings.append(
                f'Standort "{name}" hat {len(dates)} Zählungen am {date_str}'
            )

    quantities = _aggregate_quantities(entries)

    if not force:
        conflict_count = PhysicalCount.objects.filter(
            period=period,
            date__date=count_date_date,
        ).count()
        if conflict_count > 0:
            return {
                'status': 'conflict',
                'existing_count': conflict_count,
                'date': date_str,
                'warnings': warnings,
            }

    result = _write_physical_counts(quantities, count_date, period)
    return {'status': 'ok', 'warnings': warnings, **result}
