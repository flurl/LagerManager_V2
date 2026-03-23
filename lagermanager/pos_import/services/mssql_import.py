"""
MSSQL import service — Django port of forms/dbImport.py.

Replaces QSqlQuery inserts with Model.objects.bulk_create(batch_size=1000).
Runs synchronously inside transaction.atomic() — the view holds the HTTP
connection open until the import completes.

Import order (preserving FK dependencies):
  1. journal_checkpoints
  2. tische_bereiche
  3. tische_aktiv
  4. tische_bons
  5. tische_bondetails
  6. rechnungen_basis
  7. rechnungen_details
  8. artikel_basis  (+ artikel_gruppen)
  9. lager_artikel
 10. lager_einheiten
 11. artikel_gruppen
 12. artikel_zutaten
 13. meta_mwstgruppen
 14. kellner_basis
"""
import logging

import pymssql
from articles.models import (
    Article,
    ArticleGroup,
    Recipe,
    WarehouseArticle,
    WarehouseUnit,
)
from core.models import Period
from django.db import transaction

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
)

logger = logging.getLogger(__name__)

BATCH_SIZE = 1000


def connect_mssql(host: str, database: str, user: str, password: str):
    return pymssql.connect(
        host=host,
        user=user,
        password=password,
        database=database,
        charset='cp1252',
        tds_version='7.0',
    )


def run_import(period_id: int, host: str, database: str, user: str, password: str) -> dict:
    """
    Run the full MSSQL import for the given period.
    Returns a summary dict with counts per table.
    Raises on error (caller should catch and return HTTP 500).
    """
    period = Period.objects.get(pk=period_id)
    conn = connect_mssql(host, database, user, password)
    summary = {}

    with transaction.atomic():
        # 1. journal_checkpoints
        logger.info("Importing journal_checkpoints")
        JournalCheckpoint.objects.filter(period=period).delete()
        rows = _query(
            conn, "SELECT * FROM journal_checkpoints ORDER BY checkpoint_id")
        objs = [
            JournalCheckpoint(
                source_id=r[0], typ=r[1], datum=r[2], anmerkung=r[3],
                info=r[4], num=r[5], kassenbuch_verarbeitet=bool(r[6]),
                period=period,
            )
            for r in rows
        ]
        JournalCheckpoint.objects.bulk_create(objs, batch_size=BATCH_SIZE)
        summary['journal_checkpoints'] = len(objs)

        # 2. tische_bereiche
        logger.info("Importing tische_bereiche")
        TischBereich.objects.filter(period=period).delete()
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
        TischBereich.objects.bulk_create(objs, batch_size=BATCH_SIZE)
        summary['tische_bereiche'] = len(objs)

        # checkpoint_id for this period
        checkpoint_id = period.checkpoint_year
        checkpoint_filter = (
            f"= {checkpoint_id}" if checkpoint_id is not None else "IS NULL"
        )

        # 3. tische_aktiv
        logger.info("Importing tische_aktiv")
        TischAktiv.objects.filter(period=period).delete()
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
        TischAktiv.objects.bulk_create(objs, batch_size=BATCH_SIZE)
        summary['tische_aktiv'] = len(objs)

        # 4. tische_bons
        logger.info("Importing tische_bons")
        TischBon.objects.filter(period=period).delete()
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
        TischBon.objects.bulk_create(objs, batch_size=BATCH_SIZE)
        summary['tische_bons'] = len(objs)

        # 5. tische_bondetails
        logger.info("Importing tische_bondetails")
        TischBonDetail.objects.filter(period=period).delete()
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
        TischBonDetail.objects.bulk_create(objs, batch_size=BATCH_SIZE)
        summary['tische_bondetails'] = len(objs)

        # 6. rechnungen_basis
        logger.info("Importing rechnungen_basis")
        RechnungBasis.objects.filter(period=period).delete()
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
        RechnungBasis.objects.bulk_create(objs, batch_size=BATCH_SIZE)
        summary['rechnungen_basis'] = len(objs)

        # 7. rechnungen_details
        logger.info("Importing rechnungen_details")
        RechnungDetail.objects.filter(period=period).delete()
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
        RechnungDetail.objects.bulk_create(objs, batch_size=BATCH_SIZE)
        summary['rechnungen_details'] = len(objs)

        # 8. artikel_gruppen
        logger.info("Importing artikel_gruppen")
        ArticleGroup.objects.filter(period=period).delete()
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
        ArticleGroup.objects.bulk_create(objs, batch_size=BATCH_SIZE)
        summary['artikel_gruppen'] = len(objs)

        # 9. artikel_basis
        logger.info("Importing artikel_basis")
        Article.objects.filter(period=period).delete()
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
                period=period,
            )
            for r in rows
        ]
        Article.objects.bulk_create(objs, batch_size=BATCH_SIZE)
        # Set group FK (source_id based)
        group_map = {
            g.source_id: g
            for g in ArticleGroup.objects.filter(period=period)
        }
        for obj, row in zip(Article.objects.filter(period=period).order_by('id'), rows):
            if row[2] in group_map:
                Article.objects.filter(pk=obj.pk).update(
                    group=group_map[row[2]])
        summary['artikel_basis'] = len(objs)

        # 10. lager_einheiten
        logger.info("Importing lager_einheiten")
        WarehouseUnit.objects.filter(period=period).delete()
        rows = _query(
            conn,
            "SELECT lager_einheit_id, lager_einheit_name, lager_einheit_multiplizierer, lager_einheit_basis FROM lager_einheiten"
        )
        objs = [
            WarehouseUnit(
                source_id=r[0], name=r[1] or '',
                multiplier=r[2], period=period,
            )
            for r in rows
        ]
        WarehouseUnit.objects.bulk_create(objs, batch_size=BATCH_SIZE)
        # Set base_unit FK
        unit_map = {
            u.source_id: u for u in WarehouseUnit.objects.filter(period=period)}
        for obj, row in zip(WarehouseUnit.objects.filter(period=period).order_by('id'), rows):
            if row[3] and row[3] in unit_map:
                WarehouseUnit.objects.filter(pk=obj.pk).update(
                    base_unit=unit_map[row[3]])
        summary['lager_einheiten'] = len(objs)

        # 11. lager_artikel
        logger.info("Importing lager_artikel")
        WarehouseArticle.objects.filter(period=period).delete()
        rows = _query(
            conn,
            """SELECT lager_artikel_lagerartikel, lager_artikel_lieferant,
                      lager_artikel_lieferant_artikel, lager_artikel_artikel,
                      lager_artikel_prioritaet, lager_artikel_einheit,
                      lager_artikel_lager, lager_artikel_flags,
                      lager_artikel_maxStand, lager_artikel_minStand
               FROM lager_artikel"""
        )
        article_map = {
            a.source_id: a for a in Article.objects.filter(period=period)}
        objs = []
        for r in rows:
            art = article_map.get(r[3])
            if art:
                objs.append(WarehouseArticle(
                    source_id=r[0], supplier_source_id=r[1],
                    supplier_article_number=r[2], article=art,
                    priority=r[4], warehouse=r[6], flags=r[7],
                    max_stock=r[8], min_stock=r[9], period=period,
                ))
        WarehouseArticle.objects.bulk_create(objs, batch_size=BATCH_SIZE)
        # Set unit FK
        wa_map = {
            w.source_id: w for w in WarehouseArticle.objects.filter(period=period)}
        unit_map = {
            u.source_id: u for u in WarehouseUnit.objects.filter(period=period)}
        for obj, row in zip(WarehouseArticle.objects.filter(period=period).order_by('id'), rows):
            if row[5] and row[5] in unit_map:
                WarehouseArticle.objects.filter(
                    pk=obj.pk).update(unit=unit_map[row[5]])
        summary['lager_artikel'] = len(objs)

        # 12. artikel_zutaten
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
            master = article_map.get(r[0])
            ingredient = article_map.get(r[1])
            if master and ingredient:
                objs.append(Recipe(
                    master_article=master, ingredient_article=ingredient,
                    quantity=r[2], is_fixed=bool(r[3]), is_ingredient=bool(r[4]),
                    is_recipe=bool(r[5]), always_show=bool(r[6]),
                    is_mandatory=bool(r[7]), use_price=bool(r[8]),
                    period=period,
                ))
        Recipe.objects.bulk_create(objs, batch_size=BATCH_SIZE)
        summary['artikel_zutaten'] = len(objs)

        # 13. meta_mwstgruppen
        logger.info("Importing meta_mwstgruppen")
        MwstGruppe.objects.filter(period=period).delete()
        rows = _query(
            conn, "SELECT mwst_id, mwst_satz, mwst_bezeichnung FROM meta_mwstgruppen")
        objs = [
            MwstGruppe(
                source_id=r[0], satz=r[1], bezeichnung=r[2] or '',
                period=period,
            )
            for r in rows
        ]
        MwstGruppe.objects.bulk_create(objs, batch_size=BATCH_SIZE)
        summary['meta_mwstgruppen'] = len(objs)

        # 14. kellner_basis
        logger.info("Importing kellner_basis")
        KellnerBasis.objects.filter(period=period).delete()
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
        KellnerBasis.objects.bulk_create(objs, batch_size=BATCH_SIZE)
        summary['kellner_basis'] = len(objs)

    conn.close()
    logger.info("Import complete: %s", summary)
    return summary


def _query(conn, sql: str) -> list:
    cur = conn.cursor()
    cur.execute(sql)
    return cur.fetchall()
