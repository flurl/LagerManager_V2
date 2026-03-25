"""
MSSQL import service — Django port of forms/dbImport.py.

Replaces QSqlQuery inserts with bulk_create(update_conflicts=True) upserts keyed on
(source_id, period). This keeps Django PKs stable across reimports, so FK references
from DeliveryDetail, StockLevel, InitialInventory, and PhysicalCount to Article survive.

Import order (preserving FK dependencies):
  1. journal_checkpoints
  2. tische_bereiche
  3. tische_aktiv
  4. tische_bons
  5. tische_bondetails
  6. rechnungen_basis
  7. rechnungen_details
  8. artikel_gruppen
  9. artikel_basis
 10. lager_einheiten
 11. lager_artikel
 12. artikel_zutaten
 13. meta_mwstgruppen
 14. kellner_basis
"""
import logging
from typing import Any

import pymssql

from core.models import Period
from django.db import transaction
from django.db.models import Model, ProtectedError

from pos_import.models import (
    JournalCheckpoint,
    KellnerBasis,
    MwstGruppe,
    RechnungBasis,
    RechnungDetail,
    TischAktiv,
    TischBereich,
    TischBon,
    TischBonDetail,
    Article,
    ArticleGroup,
    Recipe,
    WarehouseArticle,
    WarehouseUnit,
)

logger = logging.getLogger(__name__)

BATCH_SIZE = 1000


def connect_mssql(host: str, database: str, user: str, password: str) -> pymssql.Connection:
    return pymssql.connect(
        host=host,
        user=user,
        password=password,
        database=database,
        charset='cp1252',
        tds_version='7.0',
    )


def _upsert_and_cleanup(
    model: type[Model],
    period: Period,
    objs: list[Any],
    update_fields: list[str],
) -> int:
    """
    Upsert objects via bulk_create(update_conflicts=True) keyed on (source_id, period),
    then delete stale rows for this period whose source_id is no longer in the imported set.
    Returns count of imported objects.
    """
    if objs:
        model.objects.bulk_create(  # type: ignore[attr-defined]
            objs,
            batch_size=BATCH_SIZE,
            update_conflicts=True,
            unique_fields=['source_id', 'period'],
            update_fields=update_fields,
        )
    imported_ids = {o.source_id for o in objs}
    model.objects.filter(period=period).exclude(  # type: ignore[attr-defined]
        source_id__in=imported_ids).delete()
    return len(objs)


def _cleanup_stale_articles(period: Period, imported_source_ids: set[int]) -> int:
    """
    Delete stale articles for this period (no longer in MSSQL), skipping any that
    are protected by FK references (e.g. DeliveryDetail.article with on_delete=PROTECT).
    """
    stale_qs = Article.objects.filter(period=period).exclude(
        source_id__in=imported_source_ids)
    count = 0
    for article in stale_qs.iterator():
        try:
            article.delete()
            count += 1
        except ProtectedError:
            logger.warning(
                "Cannot delete stale Article pk=%s source_id=%s — protected by FK references (delivery details exist)",
                article.pk, article.source_id,
            )
    return count


def run_import(period_id: int, host: str, database: str, user: str, password: str) -> dict[str, Any]:
    """
    Run the full MSSQL import for the given period.
    Returns a summary dict with counts per table.
    Raises on error (caller should catch and return HTTP 500).
    """
    period = Period.objects.get(pk=period_id)
    conn = connect_mssql(host, database, user, password)
    summary: dict[str, Any] = {}

    with transaction.atomic():
        # 1. journal_checkpoints
        logger.info("Importing journal_checkpoints")
        rows = _query(
            conn, "SELECT * FROM journal_checkpoints ORDER BY checkpoint_id")
        objs: list[Any] = [
            JournalCheckpoint(
                source_id=r[0], typ=r[1], datum=r[2], anmerkung=r[3],
                info=r[4], num=r[5], kassenbuch_verarbeitet=bool(r[6]),
                period=period,
            )
            for r in rows
        ]
        summary['journal_checkpoints'] = _upsert_and_cleanup(
            JournalCheckpoint, period, objs,
            ['typ', 'datum', 'anmerkung', 'info', 'num', 'kassenbuch_verarbeitet'],
        )

        # 2. tische_bereiche
        logger.info("Importing tische_bereiche")
        rows = _query(conn, "SELECT * FROM tische_bereiche")
        objs = [
            TischBereich(
                source_id=r[0], kurz_name=r[1], name=r[2],
                ist_gast_bereich=bool(r[3]), min_nummer=r[4], max_nummer=r[5],
                ist_aufwand=bool(r[6]), ist_sammelbereich=bool(r[7]),
                benoetigt_adresse=bool(r[8]), rechnungs_anzahl=r[9],
                extern=bool(r[10]), ist_ordercard_bereich=bool(r[11]),
                vorgangsart=r[12], temp=bool(r[13]),
                verstecke_sammeltisch=bool(r[14]), sammeltisch_optional=bool(r[15]),
                rksv=bool(r[16]), period=period,
            )
            for r in rows
        ]
        summary['tische_bereiche'] = _upsert_and_cleanup(
            TischBereich, period, objs,
            ['kurz_name', 'name', 'ist_gast_bereich', 'min_nummer', 'max_nummer',
             'ist_aufwand', 'ist_sammelbereich', 'benoetigt_adresse', 'rechnungs_anzahl',
             'extern', 'ist_ordercard_bereich', 'vorgangsart', 'temp',
             'verstecke_sammeltisch', 'sammeltisch_optional', 'rksv'],
        )

        # checkpoint_id for this period
        checkpoint_id = period.checkpoint_year
        checkpoint_filter = (
            f"= {checkpoint_id}" if checkpoint_id is not None else "IS NULL"
        )

        # 3. tische_aktiv
        logger.info("Importing tische_aktiv")
        rows = _query(
            conn,
            f"SELECT * FROM tische_aktiv WHERE checkpoint_jahr {checkpoint_filter} ORDER BY tisch_id"
        )
        objs = [
            TischAktiv(
                source_id=r[0], bereich=r[1], pri_nummer=r[2], sek_nummer=r[3],
                gast=r[4], dt_erstellung=r[5], dt_aktivitaet=r[6], kellner=r[7],
                fertig=bool(r[8]), zahlungsart=r[9], rechnung=r[10],
                dt_zusatz=r[11], adresse=r[12], kellner_abrechnung=r[13],
                client=r[14], reservierung=r[15], reservierung_check=bool(
                    r[16]),
                zusatz_text=r[17], checkpoint_tag=r[18], checkpoint_monat=r[19],
                checkpoint_jahr=r[20], externer_beleg=bool(r[21]), period=period,
            )
            for r in rows
        ]
        summary['tische_aktiv'] = _upsert_and_cleanup(
            TischAktiv, period, objs,
            ['bereich', 'pri_nummer', 'sek_nummer', 'gast', 'dt_erstellung', 'dt_aktivitaet',
             'kellner', 'fertig', 'zahlungsart', 'rechnung', 'dt_zusatz', 'adresse',
             'kellner_abrechnung', 'client', 'reservierung', 'reservierung_check',
             'zusatz_text', 'checkpoint_tag', 'checkpoint_monat', 'checkpoint_jahr',
             'externer_beleg'],
        )

        # 4. tische_bons
        logger.info("Importing tische_bons")
        rows = _query(
            conn,
            f"""SELECT tisch_bon_id, tisch_bon_dt_erstellung, tisch_bon_tisch, tisch_bon_kellner,
                       tisch_bon_client, tisch_bon_typ, tisch_bon_bestellkarte, tisch_bon_vorgangsart
                FROM tische_bons tb
                JOIN tische_aktiv ta ON tb.tisch_bon_tisch = ta.tisch_id
                WHERE ta.checkpoint_jahr {checkpoint_filter}
                ORDER BY tisch_bon_id"""
        )
        objs = [
            TischBon(
                source_id=r[0], dt_erstellung=r[1], tisch=r[2], kellner=r[3],
                client=r[4] or '', typ=r[5], bestellkarte=r[6], vorgangsart=r[7],
                period=period,
            )
            for r in rows
        ]
        summary['tische_bons'] = _upsert_and_cleanup(
            TischBon, period, objs,
            ['dt_erstellung', 'tisch', 'kellner', 'client',
                'typ', 'bestellkarte', 'vorgangsart'],
        )

        # 5. tische_bondetails
        logger.info("Importing tische_bondetails")
        rows = _query(
            conn,
            f"""SELECT tisch_bondetail_id, tisch_bondetail_bon, tisch_bondetail_master_id,
                       tisch_bondetail_menge, tisch_bondetail_absmenge, tisch_bondetail_istUmsatz,
                       tisch_bondetail_artikel, tisch_bondetail_preis, tisch_bondetail_text,
                       tisch_bondetail_mwst, tisch_bondetail_gangfolge, tisch_bondetail_hatRabatt,
                       tisch_bondetail_istRabatt, tisch_bondetail_autoEintrag, tisch_bondetail_stornoFaehig,
                       tisch_bondetail_ep, tisch_bondetail_ep_mwst, tisch_bondetail_preisgruppe,
                       tisch_bondetail_gutschein_log, journal_preisgruppe, journal_gruppe, journal_mwst,
                       tisch_bondetail_istExternerBeleg
                FROM tische_bondetails tbd
                JOIN tische_bons tb ON tbd.tisch_bondetail_bon = tb.tisch_bon_id
                JOIN tische_aktiv ta ON tb.tisch_bon_tisch = ta.tisch_id
                WHERE ta.checkpoint_jahr {checkpoint_filter}
                ORDER BY tisch_bondetail_id"""
        )
        objs = [
            TischBonDetail(
                source_id=r[0], bon=r[1], master_id=r[2], menge=r[3], absmenge=r[4],
                ist_umsatz=bool(r[5]), artikel=r[6], preis=r[7], text=r[8] or '',
                mwst=r[9], gangfolge=r[10], hat_rabatt=bool(r[11]),
                ist_rabatt=bool(r[12]), auto_eintrag=bool(r[13]),
                storno_faehig=bool(r[14]), ep=r[15], ep_mwst=r[16],
                preisgruppe=r[17], gutschein_log=r[18],
                journal_preisgruppe=r[19], journal_gruppe=r[20],
                journal_mwst=r[21], ist_externer_beleg=bool(r[22]),
                period=period,
            )
            for r in rows
        ]
        summary['tische_bondetails'] = _upsert_and_cleanup(
            TischBonDetail, period, objs,
            ['bon', 'master_id', 'menge', 'absmenge', 'ist_umsatz', 'artikel', 'preis', 'text',
             'mwst', 'gangfolge', 'hat_rabatt', 'ist_rabatt', 'auto_eintrag', 'storno_faehig',
             'ep', 'ep_mwst', 'preisgruppe', 'gutschein_log', 'journal_preisgruppe',
             'journal_gruppe', 'journal_mwst', 'ist_externer_beleg'],
        )

        # 6. rechnungen_basis
        logger.info("Importing rechnungen_basis")
        rows = _query(
            conn,
            f"""SELECT rechnung_id, rechnung_typ, rechnung_nr, rechnung_dt_erstellung,
                       rechnung_kellnerKurzName, rechnung_tischCode, rechnung_tischBereich,
                       rechnung_adresse, rechnung_istStorno, rechnung_retour, rechnung_dt_zusatz,
                       checkpoint_tag, checkpoint_monat, checkpoint_jahr, rechnung_kassenidentifikation,
                       rechnung_barumsatz_nr, rechnung_gesamt_umsatz, rechnung_zertifikat_id,
                       rechnung_referenz, rechnung_signatur, rechnung_druckpfad, rechnung_mwst_normal,
                       rechnung_mwst_ermaessigt1, rechnung_mwst_ermaessigt2, rechnung_mwst_null,
                       rechnung_mwst_besonders, rechnung_gesamt_umsatz_enc, rechnung_rka,
                       rechnung_vorherige_signatur, rechnung_beleg_kennzeichen, rechnung_istTrainingsBeleg
                FROM rechnungen_basis
                WHERE checkpoint_jahr {checkpoint_filter}
                ORDER BY rechnung_id"""
        )
        objs = [
            RechnungBasis(
                source_id=r[0], typ=r[1], nr=r[2], dt_erstellung=r[3],
                kellner_kurz_name=r[4] or '', tisch_code=r[5] or '',
                tisch_bereich=r[6] or '', adresse=r[7], ist_storno=bool(r[8]),
                retour=r[9], dt_zusatz=r[10], checkpoint_tag=r[11],
                checkpoint_monat=r[12], checkpoint_jahr=r[13],
                kassenidentifikation=r[14], barumsatz_nr=r[15],
                gesamt_umsatz=r[16], zertifikat_id=r[17], referenz=r[18],
                signatur=r[19], druckpfad=r[20], mwst_normal=r[21],
                mwst_ermaessigt1=r[22], mwst_ermaessigt2=r[23],
                mwst_null=r[24], mwst_besonders=r[25],
                gesamt_umsatz_enc=r[26], rka=r[27],
                vorherige_signatur=r[28], beleg_kennzeichen=r[29],
                ist_trainings_beleg=bool(r[30]), period=period,
            )
            for r in rows
        ]
        summary['rechnungen_basis'] = _upsert_and_cleanup(
            RechnungBasis, period, objs,
            ['typ', 'nr', 'dt_erstellung', 'kellner_kurz_name', 'tisch_code', 'tisch_bereich',
             'adresse', 'ist_storno', 'retour', 'dt_zusatz', 'checkpoint_tag', 'checkpoint_monat',
             'checkpoint_jahr', 'kassenidentifikation', 'barumsatz_nr', 'gesamt_umsatz',
             'zertifikat_id', 'referenz', 'signatur', 'druckpfad', 'mwst_normal',
             'mwst_ermaessigt1', 'mwst_ermaessigt2', 'mwst_null', 'mwst_besonders',
             'gesamt_umsatz_enc', 'rka', 'vorherige_signatur', 'beleg_kennzeichen',
             'ist_trainings_beleg'],
        )

        # 7. rechnungen_details
        logger.info("Importing rechnungen_details")
        rows = _query(
            conn,
            f"""SELECT rd.rechnung_detail_id, rechnung_detail_rechnung, rechnung_detail_master_detail,
                       rechnung_detail_menge, rechnung_detail_absmenge, rechnung_detail_text,
                       rechnung_detail_mwst, rechnung_detail_preis, rechnung_detail_artikel_gruppe,
                       rechnung_detail_text_2, rechnung_detail_bonierdatum
                FROM rechnungen_details rd
                JOIN rechnungen_basis rb ON rd.rechnung_detail_rechnung = rb.rechnung_id
                WHERE rb.checkpoint_jahr {checkpoint_filter}
                ORDER BY rechnung_detail_id"""
        )
        objs = [
            RechnungDetail(
                source_id=r[0], rechnung=r[1], master_detail=r[2],
                menge=r[3], absmenge=r[4], text=r[5] or '',
                mwst=r[6], preis=r[7], artikel_gruppe=r[8],
                text_2=r[9], bonierdatum=r[10], period=period,
            )
            for r in rows
        ]
        summary['rechnungen_details'] = _upsert_and_cleanup(
            RechnungDetail, period, objs,
            ['rechnung', 'master_detail', 'menge', 'absmenge', 'text', 'mwst', 'preis',
             'artikel_gruppe', 'text_2', 'bonierdatum'],
        )

        # 8. artikel_gruppen
        logger.info("Importing artikel_gruppen")
        rows = _query(
            conn,
            """SELECT artikel_gruppe_id, artikel_gruppe_parent_id, artikel_gruppe_name,
                      artikel_gruppe_standard_gangfolge, artikel_gruppe_bontyp,
                      artikel_gruppe_istUmsatz, artikel_gruppe_zeigeAufRechnung,
                      artikel_gruppe_druckeRezeptur, artikel_gruppe_keinStorno
               FROM artikel_gruppen"""
        )
        objs = [
            ArticleGroup(
                source_id=r[0], parent_source_id=r[1], name=r[2] or '',
                standard_course=r[3], bon_type=r[4],
                is_revenue=bool(r[5]), show_on_receipt=bool(r[6]),
                print_recipe=bool(r[7]), no_cancellation=bool(r[8]),
                period=period,
            )
            for r in rows
        ]
        summary['artikel_gruppen'] = _upsert_and_cleanup(
            ArticleGroup, period, objs,
            ['parent_source_id', 'name', 'standard_course', 'bon_type',
             'is_revenue', 'show_on_receipt', 'print_recipe', 'no_cancellation'],
        )
        group_map = {
            g.source_id: g.pk
            for g in ArticleGroup.objects.filter(period=period).only('source_id', 'id')
        }

        # 9. artikel_basis
        logger.info("Importing artikel_basis")
        rows = _query(
            conn,
            """SELECT artikel_id, artikel_bezeichnung, artikel_gruppe,
                      ISNULL(artikel_ep, 0.0), artikel_ep_mwst,
                      artikel_preis_popup, artikel_ep_preis_popup,
                      artikel_bemerkung, artikel_bezeichnung_2,
                      artikel_rksv, artikel_externer_beleg
               FROM artikel_basis"""
        )
        objs = [
            Article(
                source_id=r[0], name=r[1] or '', sales_price=r[3],
                sales_price_vat=r[4], price_popup=bool(r[5]),
                ep_price_popup=bool(r[6]), note=r[7], name_2=r[8],
                rksv=bool(r[9]), external_receipt=bool(r[10]),
                group_id=group_map.get(r[2]),
                period=period,
            )
            for r in rows
        ]
        if objs:
            Article.objects.bulk_create(
                objs,
                batch_size=BATCH_SIZE,
                update_conflicts=True,
                unique_fields=['source_id', 'period'],
                update_fields=['name', 'sales_price', 'sales_price_vat', 'price_popup',
                               'ep_price_popup', 'note', 'name_2', 'rksv', 'external_receipt',
                               'group'],
            )
        imported_article_ids = {o.source_id for o in objs}
        _cleanup_stale_articles(period, imported_article_ids)
        summary['artikel_basis'] = len(objs)

        article_map = {
            a.source_id: a.pk
            for a in Article.objects.filter(period=period).only('source_id', 'id')
        }

        # 10. lager_einheiten (two-pass: upsert first, then set self-referential base_unit)
        logger.info("Importing lager_einheiten")
        rows = _query(
            conn,
            "SELECT lager_einheit_id, lager_einheit_name, lager_einheit_multiplizierer, lager_einheit_basis FROM lager_einheiten"
        )
        objs = [
            WarehouseUnit(
                source_id=r[0], name=r[1] or '',
                multiplier=r[2], base_unit=None, period=period,
            )
            for r in rows
        ]
        summary['lager_einheiten'] = _upsert_and_cleanup(
            WarehouseUnit, period, objs,
            ['name', 'multiplier', 'base_unit'],
        )
        unit_map = {
            u.source_id: u.pk
            for u in WarehouseUnit.objects.filter(period=period).only('source_id', 'id')
        }
        # Second pass: set base_unit (self-referential FK)
        units_to_update = []
        for r in rows:
            if r[3] and r[3] in unit_map and r[0] in unit_map:
                units_to_update.append(WarehouseUnit(
                    pk=unit_map[r[0]], base_unit_id=unit_map[r[3]]))
        if units_to_update:
            WarehouseUnit.objects.bulk_update(
                units_to_update, ['base_unit'], batch_size=BATCH_SIZE)

        # 11. lager_artikel
        logger.info("Importing lager_artikel")
        rows = _query(
            conn,
            """SELECT lager_artikel_lagerartikel, lager_artikel_lieferant,
                      lager_artikel_lieferant_artikel, lager_artikel_artikel,
                      lager_artikel_prioritaet, lager_artikel_einheit,
                      lager_artikel_lager, lager_artikel_flags,
                      lager_artikel_maxStand, lager_artikel_minStand
               FROM lager_artikel"""
        )
        objs = []
        for r in rows:
            art_pk = article_map.get(r[3])
            unit_pk = unit_map.get(r[5])
            if art_pk:
                objs.append(WarehouseArticle(
                    source_id=r[0], supplier_source_id=r[1],
                    supplier_article_number=r[2], source_article_id=r[3],
                    priority=r[4], source_unit_id=r[5],
                    warehouse=r[6], flags=r[7],
                    max_stock=r[8], min_stock=r[9], period=period,
                    article_id=art_pk, unit_id=unit_pk,
                ))
        summary['lager_artikel'] = _upsert_and_cleanup(
            WarehouseArticle, period, objs,
            ['supplier_source_id', 'supplier_article_number', 'source_article_id', 'priority',
             'unit', 'warehouse', 'flags', 'max_stock', 'min_stock', 'article'],
        )

        # 12. artikel_zutaten (no source_id — delete+recreate)
        logger.info("Importing artikel_zutaten")
        Recipe.objects.filter(period=period).delete()
        rows = _query(
            conn,
            """SELECT zutate_master_artikel, zutate_artikel, zutate_menge,
                      zutate_istFixiert, zutate_istZutat, zutate_istRezept,
                      zutate_immerAnzeigen, zutate_istZwangsAbfrage, zutate_preisVerwenden
               FROM artikel_zutaten"""
        )
        objs = []
        for r in rows:
            master_pk = article_map.get(r[0])
            ingredient_pk = article_map.get(r[1])
            if master_pk and ingredient_pk:
                objs.append(Recipe(
                    source_master_article_id=r[0], source_ingredient_article_id=r[1],
                    quantity=r[2], is_fixed=bool(r[3]), is_ingredient=bool(r[4]),
                    is_recipe=bool(r[5]), always_show=bool(r[6]),
                    is_mandatory=bool(r[7]), use_price=bool(r[8]),
                    period=period, master_article_id=master_pk,
                    ingredient_article_id=ingredient_pk,
                ))
        Recipe.objects.bulk_create(objs, batch_size=BATCH_SIZE)
        summary['artikel_zutaten'] = len(objs)

        # 13. meta_mwstgruppen
        logger.info("Importing meta_mwstgruppen")
        rows = _query(
            conn, "SELECT mwst_id, mwst_satz, mwst_bezeichnung FROM meta_mwstgruppen")
        objs = [
            MwstGruppe(
                source_id=r[0], satz=r[1], bezeichnung=r[2] or '',
                period=period,
            )
            for r in rows
        ]
        summary['meta_mwstgruppen'] = _upsert_and_cleanup(
            MwstGruppe, period, objs,
            ['satz', 'bezeichnung'],
        )

        # 14. kellner_basis
        logger.info("Importing kellner_basis")
        rows = _query(conn, "SELECT * FROM kellner_basis")
        objs = [
            KellnerBasis(
                source_id=r[0], kurz_name=r[1] or '', uid=r[2], person=r[3],
                lager=r[4], schnell_tisch_bereich=r[5],
                schnell_tisch_pri_nummer=r[6], schnell_tisch_sek_nummer=r[7],
                zeige_auswahl=bool(r[8]), kasse=r[9], period=period,
            )
            for r in rows
        ]
        summary['kellner_basis'] = _upsert_and_cleanup(
            KellnerBasis, period, objs,
            ['kurz_name', 'uid', 'person', 'lager', 'schnell_tisch_bereich',
             'schnell_tisch_pri_nummer', 'schnell_tisch_sek_nummer', 'zeige_auswahl', 'kasse'],
        )

    conn.close()
    logger.info("Import complete: %s", summary)
    return summary


def _query(conn: pymssql.Connection, sql: str) -> list[Any]:
    cur = conn.cursor()
    cur.execute(sql)
    return list(cur.fetchall())
