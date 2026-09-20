#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Computes the legacy LagerManager "Lagerstand" (stock level) as of a given date,
for one or more dates, replicating the calculation from
lagerManager/reports/lagerstandTextuell.py + lagerManager/reports/inventur.py:

    Lagerstand[artikel, date] = InitialStock[artikel]        (lagerstand table, period start)
                               + Deliveries[artikel, <= date]  (lieferungen / lieferungen_details)
                               - Consumption[artikel, <= date] (POS bons via journal_checkpoints,
                                                                 checkpoint_typ = 1, recipe-decomposed)

The relevant `perioden` row for each date is resolved automatically, so this works
across period boundaries.

Compatible with Python 2.7.12 and Python 3.5.2 (the target's interpreter versions) —
no f-strings, no PEP 526/3107 type annotations, no stdlib APIs newer than 3.5.

Usage:
    python scripts/legacy_lagerstand_at_date.py \
        --host db.example.com --user lager --password secret --database lagermanager \
        --start 2022-01-01 --weekday 2 \
        --out lagerstand_first_wednesdays.csv

    --weekday: 0=Monday .. 6=Sunday (default 2 = Wednesday)
    --start/--end: default start=2022-01-01, end=today
    Dates without a matching `perioden` row are skipped with a warning.
"""
from __future__ import division, print_function, unicode_literals

import argparse
import csv
import datetime
import sys

import pymysql
import pymysql.cursors

PY2 = sys.version_info[0] == 2
TEXT_TYPE = type(u'')  # unicode on Py2, str on Py3 — avoids referencing the removed `unicode` name

DEBUG = False

CONSUMPTION_QUERY = """
    SELECT art2.artikel_bezeichnung AS article,
           SUM(tb.tisch_bondetail_absmenge * az.zutate_menge / le.lager_einheit_multiplizierer) AS amount
    FROM artikel_basis art1
    JOIN artikel_zutaten az ON az.zutate_master_artikel = art1.artikel_id
    JOIN artikel_basis art2 ON az.zutate_artikel = art2.artikel_id
    JOIN tische_bondetails tb ON tb.tisch_bondetail_artikel = art1.artikel_id
    JOIN tische_bons tbo ON tb.tisch_bondetail_bon = tbo.tisch_bon_id
    JOIN tische_aktiv ta ON tbo.tisch_bon_tisch = ta.tisch_id
    JOIN journal_checkpoints jc ON ta.checkpoint_tag = jc.checkpoint_id
    JOIN lager_artikel la ON la.lager_artikel_artikel = art2.artikel_id
    JOIN lager_einheiten le ON la.lager_artikel_einheit = le.lager_einheit_id
    WHERE az.zutate_istRezept = 1
      AND jc.checkpoint_typ = 1
      AND ta.tisch_periode = %(period_id)s
      AND tbo.tisch_bon_periode = %(period_id)s
      AND tb.tisch_bondetail_periode = %(period_id)s
      AND jc.checkpoint_periode = %(period_id)s
      AND az.zutate_periode = %(period_id)s
      AND art1.artikel_periode = %(period_id)s
      AND art2.artikel_periode = %(period_id)s
      AND (la.lager_artikel_periode = %(period_id)s OR la.lager_artikel_periode IS NULL)
      AND le.lager_einheit_periode = %(period_id)s
      AND STR_TO_DATE(jc.checkpoint_info, '%%d.%%m.%%Y') <= %(as_of)s
    GROUP BY art2.artikel_bezeichnung

    UNION ALL

    SELECT a.artikel_bezeichnung AS article,
           SUM(tb.tisch_bondetail_absmenge) AS amount
    FROM artikel_basis a
    LEFT JOIN artikel_zutaten az ON az.zutate_master_artikel = a.artikel_id
    JOIN tische_bondetails tb ON tb.tisch_bondetail_artikel = a.artikel_id
    JOIN tische_bons tbo ON tb.tisch_bondetail_bon = tbo.tisch_bon_id
    JOIN tische_aktiv ta ON tbo.tisch_bon_tisch = ta.tisch_id
    JOIN journal_checkpoints jc ON ta.checkpoint_tag = jc.checkpoint_id
    WHERE az.zutate_istRezept IS NULL
      AND jc.checkpoint_typ = 1
      AND ta.tisch_periode = %(period_id)s
      AND tbo.tisch_bon_periode = %(period_id)s
      AND tb.tisch_bondetail_periode = %(period_id)s
      AND jc.checkpoint_periode = %(period_id)s
      AND (az.zutate_periode = %(period_id)s OR az.zutate_periode IS NULL)
      AND a.artikel_periode = %(period_id)s
      AND STR_TO_DATE(jc.checkpoint_info, '%%d.%%m.%%Y') <= %(as_of)s
    GROUP BY a.artikel_bezeichnung
"""

INITIAL_STOCK_QUERY = """
    SELECT artikel_basis.artikel_bezeichnung AS article, SUM(lagerstand.anzahl) AS amount
    FROM artikel_basis
    JOIN lagerstand ON lagerstand.artikel_id = artikel_basis.artikel_id
    WHERE artikel_basis.artikel_periode = %(period_id)s
      AND lagerstand.periode_id = %(period_id)s
    GROUP BY artikel_basis.artikel_bezeichnung
"""

DELIVERIES_QUERY = """
    SELECT artikel_basis.artikel_bezeichnung AS article, SUM(lieferungen_details.anzahl) AS amount
    FROM artikel_basis
    JOIN lager_artikel ON lager_artikel.lager_artikel_artikel = artikel_basis.artikel_id
    JOIN lieferungen_details ON lieferungen_details.artikel_id = lager_artikel.lager_artikel_artikel
    JOIN lieferungen ON lieferungen.lieferung_id = lieferungen_details.lieferung_id
    JOIN perioden ON perioden.periode_id = %(period_id)s
    WHERE artikel_basis.artikel_periode = %(period_id)s
      AND lager_artikel.lager_artikel_periode = %(period_id)s
      AND lieferungen.datum BETWEEN perioden.periode_start AND perioden.periode_ende
      AND lieferungen.datum <= %(as_of)s
    GROUP BY artikel_basis.artikel_bezeichnung
"""

PERIOD_FOR_DATE_QUERY = """
    SELECT periode_id
    FROM perioden
    WHERE DATE(periode_start) <= %(as_of)s AND DATE(periode_ende) >= %(as_of)s
    ORDER BY periode_start DESC
    LIMIT 1
"""

CSV_FIELDS = ['date', 'period_id', 'article', 'initial_stock', 'deliveries', 'consumption', 'lagerstand']


def parse_date(value):
    return datetime.datetime.strptime(value, '%Y-%m-%d').date()


def first_weekdays(start, end, weekday):
    """First occurrence of `weekday` (0=Mon..6=Sun) in every month from start's to end's month."""
    dates = []
    year, month = start.year, start.month
    while True:
        d = datetime.date(year, month, 1)
        d += datetime.timedelta(days=(weekday - d.weekday()) % 7)
        if d > end:
            break
        if d >= start:
            dates.append(d)
        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1
    return dates


def execute(cur, query, params):
    cur.execute(query, params)
    if DEBUG:
        sys.stderr.write('-- executed query:\n{0}\n'.format(cur._executed))


def fetch_period_id(cur, as_of):
    execute(cur, PERIOD_FOR_DATE_QUERY, {'as_of': as_of})
    row = cur.fetchone()
    return row['periode_id'] if row else None


def fetch_amounts(cur, query, params):
    """Sums duplicate article keys — CONSUMPTION_QUERY UNIONs two independently
    grouped branches, and the same article can appear in both (e.g. sold directly
    and also used as a recipe ingredient elsewhere)."""
    execute(cur, query, params)
    amounts = {}
    for row in cur.fetchall():
        amounts[row['article']] = amounts.get(row['article'], 0.0) + float(row['amount'] or 0.0)
    return amounts


def compute_lagerstand(cur, as_of):
    period_id = fetch_period_id(cur, as_of)
    if period_id is None:
        return None

    initial = fetch_amounts(cur, INITIAL_STOCK_QUERY, {'period_id': period_id})
    deliveries = fetch_amounts(cur, DELIVERIES_QUERY, {'period_id': period_id, 'as_of': as_of})
    consumption = fetch_amounts(cur, CONSUMPTION_QUERY, {'period_id': period_id, 'as_of': as_of})

    articles = set(initial) | set(deliveries) | set(consumption)
    rows = []
    for article in sorted(articles):
        i = initial.get(article, 0.0)
        d = deliveries.get(article, 0.0)
        c = consumption.get(article, 0.0)
        rows.append({
            'date': as_of.isoformat(),
            'period_id': period_id,
            'article': article,
            'initial_stock': round(i, 3),
            'deliveries': round(d, 3),
            'consumption': round(c, 3),
            'lagerstand': round(i + d - c, 3),
        })
    return {'period_id': period_id, 'rows': rows}


def encode_row(row):
    """csv.writer needs str/bytes on Py2 and str (text) on Py3; article names may contain umlauts."""
    values = [row[field] for field in CSV_FIELDS]
    if PY2:
        values = [v.encode('utf-8') if isinstance(v, TEXT_TYPE) else v for v in values]
    return values


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--host', required=True)
    parser.add_argument('--port', type=int, default=3306)
    parser.add_argument('--user', required=True)
    parser.add_argument('--password', required=True)
    parser.add_argument('--database', required=True)
    parser.add_argument('--start', type=parse_date, default=datetime.date(2022, 1, 1))
    parser.add_argument('--end', type=parse_date, default=datetime.date.today())
    parser.add_argument('--weekday', type=int, default=2, help='0=Monday .. 6=Sunday, default 2=Wednesday')
    parser.add_argument('--out', default=None, help='CSV output path; defaults to stdout')
    parser.add_argument('--debug', action='store_true', help='print each executed SQL query to stderr')
    args = parser.parse_args()

    global DEBUG
    DEBUG = args.debug

    target_dates = first_weekdays(args.start, args.end, args.weekday)

    conn = pymysql.connect(
        host=args.host, port=args.port, user=args.user, password=args.password,
        db=args.database, charset='utf8', cursorclass=pymysql.cursors.DictCursor,
    )

    all_rows = []
    try:
        cur = conn.cursor()
        try:
            for as_of in target_dates:
                result = compute_lagerstand(cur, as_of)
                if result is None:
                    sys.stderr.write('warning: no period found for {0}, skipping\n'.format(as_of.isoformat()))
                    continue
                all_rows.extend(result['rows'])
        finally:
            cur.close()
    finally:
        conn.close()

    if args.out:
        out = open(args.out, 'wb') if PY2 else open(args.out, 'w', newline='', encoding='utf-8')
    else:
        out = sys.stdout

    try:
        writer = csv.writer(out)
        header = CSV_FIELDS
        writer.writerow([f.encode('utf-8') for f in header] if PY2 else header)
        for row in all_rows:
            writer.writerow(encode_row(row))
    finally:
        if args.out:
            out.close()


if __name__ == '__main__':
    main()
