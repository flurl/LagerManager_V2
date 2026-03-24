"""
Purchase price service — Python port of sf_getPurchasePrice.sql.

Computes weighted average purchase price (EK) for an article in a period,
recursively expanding recipes via artikel_zutaten.
EK modifiers (+, -, *, /) from ek_modifikatoren are applied afterwards.

NOTE: All FKs in the new schema use Django auto-id (not MSSQL source_id).
The article argument is the Django PK.
"""
from datetime import date
from decimal import Decimal

from django.db import connection

from core.models import Period


def get_purchase_price(article_pk: int, period_id: int, max_date: date | None = None) -> Decimal:
    """
    Return weighted-average purchase price for article (Django PK) in period_id.

    For recipe articles (no direct lager_artikel entry) the price is
    computed as the sum of component prices weighted by recipe quantities
    and unit multipliers.

    EK modifiers are applied in definition order.

    Returns Decimal (0 when no deliveries exist).
    """
    period = Period.objects.get(pk=period_id)
    p_start = period.start
    p_end = period.end

    # Determine if the article is a direct warehouse article or a recipe
    with connection.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM lager_artikel "
            "WHERE lager_artikel_artikel = %s AND lager_artikel_periode = %s",
            [article_pk, period_id],
        )
        is_direct = cur.fetchone()[0] > 0

    if is_direct:
        components = [(article_pk, Decimal('1.0'))]
    else:
        # Expand one level of recipe (zutate_istRezept = true)
        with connection.cursor() as cur:
            cur.execute(
                """
                SELECT az.zutate_artikel,
                       az.zutate_menge / COALESCE(le.lager_einheit_multiplizierer, 1.0) AS faktor
                FROM artikel_zutaten az
                JOIN lager_artikel la ON la.lager_artikel_artikel = az.zutate_artikel
                    AND la.lager_artikel_periode = %s
                LEFT JOIN lager_einheiten le ON la.lager_artikel_einheit = le.id
                    AND le.lager_einheit_periode = %s
                WHERE az.zutate_master_artikel = %s
                  AND az.zutate_istRezept = TRUE
                  AND az.zutate_periode = %s
                """,
                [period_id, period_id, article_pk, period_id],
            )
            rows = cur.fetchall()
        components = [(row[0], Decimal(str(row[1]))) for row in rows]

    if not components:
        return Decimal('0.00')

    total_ek = Decimal('0.00')
    for comp_pk, factor in components:
        date_filter = ""
        params = [comp_pk, p_start, p_end]
        if max_date is not None:
            date_filter = " AND l.datum <= %s"
            params.append(max_date)

        with connection.cursor() as cur:
            cur.execute(
                f"""
                SELECT SUM(ld.anzahl * ld.einkaufspreis) / NULLIF(SUM(ld.anzahl), 0)
                FROM lieferungen_details ld
                JOIN lieferungen l ON l.lieferung_id = ld.lieferung_id
                WHERE ld.artikel_id = %s
                  AND l.datum BETWEEN %s AND %s
                  AND ld.anzahl > 0
                  {date_filter}
                """,
                params,
            )
            row = cur.fetchone()

        ek = Decimal(str(row[0])) if row and row[0] is not None else Decimal('0.00')
        total_ek += ek * factor

    # Apply EK modifiers
    with connection.cursor() as cur:
        cur.execute(
            "SELECT emo_operator, emo_modifikator FROM ek_modifikatoren "
            "WHERE emo_artikel_id = %s AND emo_periode_id = %s ORDER BY id",
            [article_pk, period_id],
        )
        modifiers = cur.fetchall()

    for operator, mod_value in modifiers:
        mod = Decimal(str(mod_value))
        if operator == '+':
            total_ek += mod
        elif operator == '-':
            total_ek -= mod
        elif operator == '*':
            total_ek *= mod
        elif operator == '/':
            if mod != 0:
                total_ek /= mod

    return total_ek.quantize(Decimal('0.0001'))
