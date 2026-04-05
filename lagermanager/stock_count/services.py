from decimal import Decimal

from pos_import.models import ArticleMeta, WarehouseArticle


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

    rows.sort(key=lambda r: r['article_name'].lower())
    return rows
