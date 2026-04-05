from pos_import.models import ArticleMeta, WarehouseArticle


def get_expanded_articles(period_id: int) -> list[dict[str, str]]:
    """
    Return all countable articles for a period, expanded with sub_articles from ArticleMeta.

    For an article with sub_articles="lemon,orange":
      - Base row:      article_id="123",        article_name="Cola"
      - Sub row:       article_id="123-lemon",   article_name="Cola-lemon"
      - Sub row:       article_id="123-orange",  article_name="Cola-orange"

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

    rows: list[dict[str, str]] = []
    for wa in warehouse_articles:
        source_id = wa.article.source_id
        name = wa.article.name
        meta = meta_by_source_id.get(source_id)

        if meta is not None and meta.is_hidden:
            continue

        rows.append({'article_id': str(source_id), 'article_name': name})

        if meta is not None and meta.sub_articles:
            for sub in (s.strip() for s in meta.sub_articles.split(',') if s.strip()):
                rows.append({
                    'article_id': f'{source_id}-{sub}',
                    'article_name': f'{name}-{sub}',
                })

    rows.sort(key=lambda r: r['article_name'].lower())
    return rows
