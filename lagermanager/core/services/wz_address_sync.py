"""
Wiffzack POS address sync — imports adressen_basis into core.Address and
creates one core.Customer per imported address.

Unlike the period-scoped pos_import tables, addresses are global master data.
The sync:
  - upserts rows by wz_source_id (bulk_create with update_conflicts=True)
  - creates a matching Customer 1:1 for every WZ address, keyed on the same
    wz_source_id, so that every address a document can be billed to has a
    customer to keep a balance for — unless the address already has a
    customer, which it keeps (and which takes over the wz_source_id if it has
    none yet); the sync never moves an address to another customer
  - NEVER deletes — preserves locally-created addresses (wz_source_id=None)
    and WZ rows referenced by existing documents
  - is idempotent (can be run repeatedly without side-effects)

Returns the number of WZ address rows processed.
"""
import logging
from typing import Any

from django.db import transaction
from pos_import.services.mssql_import import connect_mssql

from core.models import Address, Customer
from core.services.numbering import allocate_customer_numbers

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

    if not rows:
        logger.info('WZ address sync: processed 0 rows')
        return 0

    with transaction.atomic():
        customer_ids = _upsert_customers(rows)
        _upsert_addresses(rows, customer_ids)
        _set_default_addresses(rows)

    count = len(rows)
    logger.info('WZ address sync: processed %d rows', count)
    return count


def _wz_customer_name(row: Any) -> str:
    """Company if present, else the person's name, else the postal address.

    Mirrors Address.display_name, which cannot be reused here because the
    addresses do not exist as model instances yet.  A nameless row falls back to
    street and city rather than to an opaque "WZ-Adresse 123", so the customer
    list stays readable.
    """
    firma: str | None = row[4] or None
    if firma:
        return firma[:255]
    name = ' '.join(p for p in (row[2], row[3]) if p)
    if name:
        return name[:255]
    city = ' '.join(p for p in (row[7], row[8]) if p)
    postal = ', '.join(p for p in (row[6], city) if p)
    return (postal or f'WZ-Adresse {row[0]}')[:255]


def _adopt_address_customers(wz_ids: list[int]) -> dict[int, int]:
    """Return {wz_source_id: customer pk} for WZ addresses that already have a customer.

    Such an address keeps its customer: it may come from
    backfill_customers_and_ledger, or the user may have moved the address to a
    customer of their choice.  A customer that has no wz_source_id yet takes
    over the one of its (first) WZ address, so its name and contact details are
    refreshed from then on and it is found by wz_source_id like any synced one.
    """
    linked: dict[int, int] = {
        wz_id: customer_pk
        for wz_id, customer_pk in
        Address.objects.filter(wz_source_id__in=wz_ids, customer__isnull=False)
        .order_by('wz_source_id')
        .values_list('wz_source_id', 'customer_id')
        if wz_id is not None and customer_pk is not None
    }
    claimed: set[int | None] = set(
        Customer.objects.filter(wz_source_id__in=wz_ids)
        .values_list('wz_source_id', flat=True)
    )
    adoptable: dict[int, Customer] = {
        c.pk: c for c in Customer.objects.filter(
            pk__in=linked.values(), wz_source_id__isnull=True)
    }
    adopted: list[Customer] = []
    for wz_id, customer_pk in linked.items():
        customer: Customer | None = adoptable.pop(customer_pk, None)
        if customer is not None and wz_id not in claimed:
            customer.wz_source_id = wz_id
            adopted.append(customer)
    if adopted:
        Customer.objects.bulk_update(adopted, ['wz_source_id'], batch_size=BATCH_SIZE)
    return linked


def _upsert_customers(rows: list[Any]) -> dict[int, int]:
    """Create/update one Customer per WZ address; return {wz_source_id: pk}.

    An address that already has a customer keeps it (see
    _adopt_address_customers); a customer is only created for one that has
    neither a customer nor a customer keyed on its wz_source_id.

    Numbers are allocated in a single locked bump for all new customers rather
    than one lock per row — a first sync creates thousands at once.
    """
    wz_ids: list[int] = [r[0] for r in rows]
    linked: dict[int, int] = _adopt_address_customers(wz_ids)
    existing: dict[int, int] = dict(
        Customer.objects.filter(wz_source_id__in=wz_ids)
        .values_list('wz_source_id', 'pk')
    )
    new_rows: list[Any] = [r for r in rows if r[0] not in existing and r[0] not in linked]
    numbers: list[str] = allocate_customer_numbers(len(new_rows))

    to_create = [
        Customer(
            wz_source_id=r[0],
            customer_number=number,
            name=_wz_customer_name(r),
            email=r[10] or '',
            telefon=r[9] or '',
            uid=r[11] or '',
        )
        for r, number in zip(new_rows, numbers, strict=True)
    ]
    if to_create:
        Customer.objects.bulk_create(to_create, batch_size=BATCH_SIZE)

    # Refresh the name/contact details of customers that already existed.
    if existing:
        by_wz: dict[int, Any] = {r[0]: r for r in rows}
        updates: list[Customer] = []
        for customer in Customer.objects.filter(wz_source_id__in=list(existing)):
            r = by_wz[customer.wz_source_id]
            customer.name = _wz_customer_name(r)
            customer.email = r[10] or ''
            customer.telefon = r[9] or ''
            customer.uid = r[11] or ''
            updates.append(customer)
        if updates:
            Customer.objects.bulk_update(
                updates, ['name', 'email', 'telefon', 'uid'], batch_size=BATCH_SIZE)

    keyed: dict[int, int] = dict(
        Customer.objects.filter(wz_source_id__in=wz_ids)
        .values_list('wz_source_id', 'pk')
    )
    # The address's own customer wins, so the upsert never re-points an address.
    return {**keyed, **linked}


def _upsert_addresses(rows: list[Any], customer_ids: dict[int, int]) -> None:
    objs = [
        Address(
            wz_source_id=r[0],
            customer_id=customer_ids.get(r[0]),
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
    Address.objects.bulk_create(
        objs,
        batch_size=BATCH_SIZE,
        update_conflicts=True,
        unique_fields=['wz_source_id'],
        update_fields=[
            'customer', 'anrede', 'vorname', 'nachname', 'firma', 'abteilung',
            'strasse', 'plz', 'ort', 'telefon', 'email', 'uid', 'anmerkung',
        ],
    )


def _set_default_addresses(rows: list[Any]) -> None:
    """Point each synced customer at its own address, unless already set.

    Runs after the address upsert because the address PKs are only known then.
    An existing default is left alone — the user may have picked a different
    address for this customer in the meantime.
    """
    wz_ids: list[int] = [r[0] for r in rows]
    address_by_wz: dict[int, int] = dict(
        Address.objects.filter(wz_source_id__in=wz_ids)
        .values_list('wz_source_id', 'pk')
    )
    updates: list[Customer] = []
    for customer in Customer.objects.filter(
            wz_source_id__in=wz_ids, default_address__isnull=True):
        address_pk = address_by_wz.get(customer.wz_source_id)
        if address_pk is not None:
            customer.default_address_id = address_pk
            updates.append(customer)
    if updates:
        Customer.objects.bulk_update(updates, ['default_address'], batch_size=BATCH_SIZE)
