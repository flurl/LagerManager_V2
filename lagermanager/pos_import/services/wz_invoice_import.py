"""
Service helpers for the WZ → invoice import feature.

These functions query the locally-mirrored Wiffzack POS tables and return
data ready for the three import API endpoints.  All inter-table links are
plain integer source_id references (no Django FKs), so every join is done
manually and scoped to the same period.
"""
from __future__ import annotations

from django.db.models import QuerySet, Sum

from pos_import.models import (
    JournalCheckpoint,
    TischAktiv,
    TischBereich,
    TischBon,
    TischBonDetail,
)


def get_aufwand_checkpoints(period_id: int) -> QuerySet[JournalCheckpoint]:
    """Return daily-close checkpoints (typ='1') for the given period, newest first."""
    return (
        JournalCheckpoint.objects
        .filter(typ="1", period_id=period_id)
        .order_by("-datum")
    )


def get_aufwand_tische(period_id: int, checkpoint_source_id: int) -> list[dict[str, int | str]]:
    """
    Return active tables that belong to the given checkpoint and whose area
    (TischBereich) has ist_aufwand=True.

    Returns a list of dicts: [{id, label}] where id=TischAktiv.source_id.
    """
    # Build a {source_id: kurz_name} map for Aufwand areas in this period.
    aufwand_bereiche: dict[int, str] = {
        b.source_id: b.kurz_name
        for b in TischBereich.objects.filter(period_id=period_id, ist_aufwand=True)
    }
    if not aufwand_bereiche:
        return []

    tische = TischAktiv.objects.filter(
        period_id=period_id,
        checkpoint_tag=checkpoint_source_id,
        bereich__in=aufwand_bereiche.keys(),
    ).order_by("bereich", "pri_nummer")

    return [
        {
            "id": t.source_id,
            "label": f"{aufwand_bereiche[t.bereich]}-{t.pri_nummer}",
        }
        for t in tische
    ]


def get_tisch_aufwand_lines(period_id: int, tisch_source_id: int) -> list[dict[str, int | str]]:
    """
    Return the bon-details for a single table, grouped by article name.
    Each entry: {name, quantity} where quantity = SUM(absmenge).
    """
    bon_source_ids = list(
        TischBon.objects
        .filter(period_id=period_id, tisch=tisch_source_id)
        .values_list("source_id", flat=True)
    )
    if not bon_source_ids:
        return []

    rows = (
        TischBonDetail.objects
        .filter(period_id=period_id, bon__in=bon_source_ids)
        .values("text")
        .annotate(quantity=Sum("absmenge"))
        .order_by("text")
    )
    return [{"name": r["text"], "quantity": r["quantity"]} for r in rows]
