"""
Wiffzack POS address sync — imports adressen_basis into core.Address.

Unlike the period-scoped pos_import tables, addresses are global master data.
The sync:
  - upserts rows by wz_source_id (bulk_create with update_conflicts=True)
  - NEVER deletes — preserves locally-created addresses (wz_source_id=None)
    and WZ rows referenced by existing documents
  - is idempotent (can be run repeatedly without side-effects)

Returns the number of WZ address rows processed.
"""
import logging
from typing import Any

from core.models import Address
from pos_import.services.mssql_import import connect_mssql

logger = logging.getLogger(__name__)

BATCH_SIZE = 1000

_QUERY = """
SELECT
    adresse_id,
    adresse_anrede,
    adresse_vorname,
    adresse_nachname,
    adresse_firma,
    adresse_abteilung,
    adresse_strasse,
    adresse_plz,
    adresse_ort,
    adresse_telefon,
    adresse_email,
    adresse_uid,
    adresse_anmerkung
FROM dbo.adressen_basis
"""


def sync_addresses(host: str, database: str, user: str, password: str) -> int:
    """
    Sync addresses from the Wiffzack MSSQL database into core.Address.
    Returns the count of WZ address rows processed.
    """
    conn = connect_mssql(host, database, user, password)
    try:
        cur = conn.cursor()
        cur.execute(_QUERY)
        rows: list[Any] = list(cur.fetchall())
    finally:
        conn.close()

    objs = [
        Address(
            wz_source_id=r[0],
            anrede=r[1] or None,
            vorname=r[2] or None,
            nachname=r[3] or None,
            firma=r[4] or None,
            abteilung=r[5] or None,
            strasse=r[6] or None,
            plz=r[7] or None,
            ort=r[8] or None,
            telefon=r[9] or None,
            email=r[10] or None,
            uid=r[11] or None,
            anmerkung=r[12] or None,
        )
        for r in rows
    ]

    if objs:
        Address.objects.bulk_create(
            objs,
            batch_size=BATCH_SIZE,
            update_conflicts=True,
            unique_fields=['wz_source_id'],
            update_fields=[
                'anrede', 'vorname', 'nachname', 'firma', 'abteilung',
                'strasse', 'plz', 'ort', 'telefon', 'email', 'uid', 'anmerkung',
            ],
        )

    count = len(objs)
    logger.info('WZ address sync: processed %d rows', count)
    return count
