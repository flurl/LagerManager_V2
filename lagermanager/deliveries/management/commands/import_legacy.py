"""Management command to import data from the legacy LagerManager MySQL database.

Imports in order:
  1. Partners (lieferanten)
  2. Tax rates (steuersaetze)
  3. Stock movements + details (lieferungen + lieferungen_details)
  4. Documents as attachments (dokumente)

All existing partners, tax rates, stock movements, and attachments are deleted before
importing. A confirmation prompt is shown unless --no-input is passed.

USAGE
-----
    python manage.py import_legacy \\
        --host <mysql_host> \\
        --user <mysql_user> \\
        --password <mysql_password> \\
        --database <mysql_db> \\
        --period <django_period_pk>
"""

import getpass
from argparse import ArgumentParser
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pymysql
import pymysql.cursors
from core.models import Period
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from pos_import.models import Article

from deliveries.models import (
    Attachment,
    Partner,
    StockMovement,
    StockMovementDetail,
    TaxRate,
)


def _connect(host: str, port: int, user: str, password: str, database: str) -> pymysql.Connection:
    return pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor,
    )


class Command(BaseCommand):
    help = 'Import data from the legacy LagerManager MySQL database.'

    _mysql_kwargs: dict[str, Any]

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument('--host', type=str, default='localhost', help='MySQL host (default: localhost)')
        parser.add_argument('--port', type=int, default=3306, help='MySQL port (default: 3306)')
        parser.add_argument('--user', type=str, required=True, help='MySQL user')
        parser.add_argument(
            '--password', type=str, default=None,
            help='MySQL password (prompted interactively if omitted)',
        )
        parser.add_argument('--database', type=str, required=True, help='MySQL database name')
        parser.add_argument(
            '--period', type=int, default=None,
            help='Django Period PK to assign movements to (prompted interactively if omitted)',
        )
        parser.add_argument('--no-input', action='store_true', help='Skip confirmation prompt')

    def handle(self, *args: Any, **options: Any) -> None:
        period = self._resolve_period(options['period'])

        self.stdout.write(
            self.style.WARNING(
                "\nWARNING: This will permanently delete ALL existing:\n"
                "  - Partners\n"
                "  - Tax rates\n"
                "  - Stock movements and their details\n"
                "  - Attachments (including files on disk)\n"
                "\nThis action cannot be undone.\n"
            )
        )

        if not options['no_input']:
            answer = input("Type 'yes' to continue: ").strip()
            if answer != 'yes':
                self.stdout.write("Aborted.")
                return

        password = options['password'] or getpass.getpass('MySQL password: ')
        self._mysql_kwargs = {
            'host': options['host'],
            'port': options['port'],
            'user': options['user'],
            'password': password,
            'database': options['database'],
        }

        conn = _connect(**self._mysql_kwargs)
        try:
            with transaction.atomic():
                self._delete_existing()

                partner_map = self._import_partners(conn)
                tax_rate_map, fallback_tax_rate_pk = self._import_tax_rates(conn)
                movement_map, warnings = self._import_movements(
                    conn, period, partner_map, tax_rate_map, fallback_tax_rate_pk
                )
                attachment_warnings = self._import_documents(movement_map)
                warnings.extend(attachment_warnings)

            self._print_summary(partner_map, tax_rate_map, movement_map, warnings)
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Period selection
    # ------------------------------------------------------------------

    def _resolve_period(self, period_pk: int | None) -> Period:
        if period_pk is not None:
            try:
                return Period.objects.get(pk=period_pk)
            except Period.DoesNotExist as exc:
                raise CommandError(f"Period with pk={period_pk} does not exist.") from exc

        periods = list(Period.objects.order_by('-start'))
        if not periods:
            raise CommandError("No periods found. Create a period in the Django admin first.")

        self.stdout.write(
            "\nAvailable periods (the period is used to match articles to delivery line items):\n"
        )
        for p in periods:
            self.stdout.write(
                f"  [{p.pk:>4}]  {p.name}  ({p.start.date()} – {p.end.date()})"
            )

        self.stdout.write("")
        raw = input("Enter period ID: ").strip()
        try:
            chosen_pk = int(raw)
        except ValueError as exc:
            raise CommandError(f"Invalid period ID: {raw!r}") from exc

        try:
            return Period.objects.get(pk=chosen_pk)
        except Period.DoesNotExist as exc:
            raise CommandError(f"Period with pk={chosen_pk} does not exist.") from exc

    # ------------------------------------------------------------------
    # Delete existing data
    # ------------------------------------------------------------------

    def _delete_existing(self) -> None:
        self.stdout.write("Deleting existing data…")
        # Attachments: post_delete signal removes files from disk
        count_att, _ = Attachment.objects.all().delete()
        count_det, _ = StockMovementDetail.objects.all().delete()
        count_mov, _ = StockMovement.objects.all().delete()
        count_tax, _ = TaxRate.objects.all().delete()
        count_par, _ = Partner.objects.all().delete()
        self.stdout.write(
            f"  Deleted: {count_att} attachments, {count_det} details, "
            f"{count_mov} movements, {count_tax} tax rates, {count_par} partners"
        )

    # ------------------------------------------------------------------
    # Import partners
    # ------------------------------------------------------------------

    def _import_partners(self, conn: pymysql.Connection) -> dict[int, int]:
        """Returns mapping: old lieferant_id → new Partner pk."""
        self.stdout.write("Importing partners…")
        partner_map: dict[int, int] = {}
        with conn.cursor() as cur:
            cur.execute(
                "SELECT lieferant_id, lieferant_name, lft_ist_verbraucher "
                "FROM lieferanten ORDER BY lieferant_id"
            )
            # DictCursor returns dicts at runtime; stubs only know the base tuple type
            rows = cast(list[dict[str, Any]], cur.fetchall())

        for row in rows:
            partner = Partner.objects.create(name=row['lieferant_name'])
            partner_map[row['lieferant_id']] = partner.pk

        self.stdout.write(f"  {len(partner_map)} partners imported.")
        return partner_map

    # ------------------------------------------------------------------
    # Import tax rates
    # ------------------------------------------------------------------

    def _import_tax_rates(self, conn: pymysql.Connection) -> tuple[dict[int, int], int]:
        """Returns (mapping: old sts_id → new TaxRate pk, fallback_tax_rate_pk)."""
        self.stdout.write("Importing tax rates…")
        tax_rate_map: dict[int, int] = {}
        with conn.cursor() as cur:
            cur.execute(
                "SELECT sts_id, sts_bezeichnung, sts_prozent "
                "FROM steuersaetze ORDER BY sts_id"
            )
            # DictCursor returns dicts at runtime; stubs only know the base tuple type
            rows = cast(list[dict[str, Any]], cur.fetchall())

        for row in rows:
            tax_rate = TaxRate.objects.create(
                name=row['sts_bezeichnung'],
                percent=Decimal(str(row['sts_prozent'])),
            )
            tax_rate_map[row['sts_id']] = tax_rate.pk

        # Fallback: tax rate with the highest new PK (corresponds to highest sts_id)
        fallback_pk = max(tax_rate_map.values()) if tax_rate_map else 0

        self.stdout.write(f"  {len(tax_rate_map)} tax rates imported.")
        return tax_rate_map, fallback_pk

    # ------------------------------------------------------------------
    # Import stock movements and details
    # ------------------------------------------------------------------

    def _import_movements(
        self,
        conn: pymysql.Connection,
        period: Period,
        partner_map: dict[int, int],
        tax_rate_map: dict[int, int],
        fallback_tax_rate_pk: int,
    ) -> tuple[dict[int, int], list[str]]:
        """Returns (movement_map, warnings). movement_map: old lieferung_id → new StockMovement pk."""
        self.stdout.write("Importing stock movements…")
        warnings: list[str] = []

        # Article lookup for the period
        article_map: dict[int, Article] = {
            a.source_id: a for a in Article.objects.filter(period=period)
        }
        self.stdout.write(f"  Loaded {len(article_map)} articles for period '{period}'.")

        # Fetch all movements
        with conn.cursor() as cur:
            cur.execute(
                "SELECT lieferung_id, lieferant_id, datum, lie_ist_verbrauch, lie_kommentar "
                "FROM lieferungen ORDER BY lieferung_id"
            )
            # DictCursor returns dicts at runtime; stubs only know the base tuple type
            movement_rows = cast(list[dict[str, Any]], cur.fetchall())

        # Fetch all details and group by lieferung_id
        with conn.cursor() as cur:
            cur.execute(
                "SELECT lieferung_detail_id, lieferung_id, artikel_id, anzahl, "
                "einkaufspreis, lde_stsid "
                "FROM lieferungen_details ORDER BY lieferung_id, lieferung_detail_id"
            )
            # DictCursor returns dicts at runtime; stubs only know the base tuple type
            detail_rows = cast(list[dict[str, Any]], cur.fetchall())

        details_by_movement: dict[int, list[dict[str, Any]]] = {}
        for dr in detail_rows:
            details_by_movement.setdefault(dr['lieferung_id'], []).append(dr)

        movement_map: dict[int, int] = {}
        movements_created = 0
        details_created = 0
        missing_articles: set[int] = set()
        fallback_tax_details: list[int] = []

        for mrow in movement_rows:
            old_lid = mrow['lieferung_id']
            partner_pk = partner_map.get(mrow['lieferant_id'])
            if partner_pk is None:
                warnings.append(
                    f"Movement {old_lid}: lieferant_id {mrow['lieferant_id']} not found in partner_map — skipped."
                )
                continue

            movement_type = (
                StockMovement.Type.CONSUMPTION if mrow['lie_ist_verbrauch']
                else StockMovement.Type.DELIVERY
            )
            movement = StockMovement.objects.create(
                partner_id=partner_pk,
                date=mrow['datum'].date(),
                movement_type=movement_type,
                comment=mrow['lie_kommentar'] or None,
                period=period,
            )
            movement_map[old_lid] = movement.pk
            movements_created += 1

            for drow in details_by_movement.get(old_lid, []):
                source_id: int = drow['artikel_id']
                article = article_map.get(source_id)
                if article is None:
                    missing_articles.add(source_id)
                    warnings.append(
                        f"Detail {drow['lieferung_detail_id']} (movement {old_lid}): "
                        f"article source_id {source_id} not found — skipped."
                    )
                    continue

                old_sts_id = drow['lde_stsid']
                if old_sts_id is not None and old_sts_id in tax_rate_map:
                    tax_rate_pk = tax_rate_map[old_sts_id]
                    used_fallback = False
                else:
                    tax_rate_pk = fallback_tax_rate_pk
                    used_fallback = True

                detail = StockMovementDetail.objects.create(
                    stock_movement=movement,
                    article=article,
                    quantity=abs(Decimal(str(drow['anzahl']))),
                    unit_price=Decimal(str(drow['einkaufspreis'])),
                    tax_rate_id=tax_rate_pk,
                )
                details_created += 1

                if used_fallback:
                    fallback_tax_details.append(detail.pk)
                    warnings.append(
                        f"Detail {drow['lieferung_detail_id']} (new pk={detail.pk}, "
                        f"movement {old_lid}): lde_stsid={old_sts_id} not found — "
                        f"used fallback tax_rate pk={tax_rate_pk}."
                    )

        self.stdout.write(
            f"  {movements_created} movements, {details_created} details imported."
        )
        return movement_map, warnings

    # ------------------------------------------------------------------
    # Import documents
    # ------------------------------------------------------------------

    def _import_documents(
        self,
        movement_map: dict[int, int],
    ) -> list[str]:
        """Returns list of warning strings for any skipped or anomalous documents."""
        self.stdout.write("Importing documents…")
        warnings: list[str] = []

        # Use SSDictCursor to stream large BLOBs row-by-row to avoid memory exhaustion
        ss_conn = pymysql.connect(
            **self._mysql_kwargs,
            charset='utf8mb4',
            cursorclass=pymysql.cursors.SSDictCursor,
        )
        try:
            attachments_created = 0
            with ss_conn.cursor() as cur:
                cur.execute(
                    "SELECT dok_id, dok_bezeichnung, dok_data, dok_datum, dok_lieferung_id "
                    "FROM dokumente ORDER BY dok_id"
                )
                for row in cur:
                    dok_id: int = row['dok_id']
                    blob: bytes | None = row['dok_data']

                    if not blob:
                        warnings.append(f"Document {dok_id}: empty dok_data — skipped.")
                        continue

                    # Strip path separators from filename for safety
                    raw_name: str = row['dok_bezeichnung'] or f"document_{dok_id}"
                    filename = Path(raw_name).name or f"document_{dok_id}"

                    old_lid: int | None = row['dok_lieferung_id']
                    if old_lid is not None and old_lid not in movement_map:
                        warnings.append(
                            f"Document {dok_id}: lieferung_id {old_lid} not found in movement_map — "
                            f"saved as orphaned attachment."
                        )

                    movement_pk: int | None = movement_map.get(old_lid) if old_lid is not None else None

                    attachment = Attachment(
                        stock_movement_id=movement_pk,
                        original_filename=filename,
                        source_filename=filename,
                        page_number=None,
                    )
                    # file.save() stores the blob and sets attachment.file; save=True persists the model
                    attachment.file.save(filename, ContentFile(blob), save=True)
                    attachments_created += 1

            self.stdout.write(f"  {attachments_created} attachments imported.")
        finally:
            ss_conn.close()

        return warnings

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def _print_summary(
        self,
        partner_map: dict[int, int],
        tax_rate_map: dict[int, int],
        movement_map: dict[int, int],
        warnings: list[str],
    ) -> None:
        self.stdout.write(self.style.SUCCESS(
            f"\nImport complete:\n"
            f"  Partners:   {len(partner_map)}\n"
            f"  Tax rates:  {len(tax_rate_map)}\n"
            f"  Movements:  {len(movement_map)}\n"
        ))

        if warnings:
            self.stderr.write(self.style.WARNING(f"\n{len(warnings)} warning(s):\n"))
            for w in warnings:
                self.stderr.write(f"  - {w}")
        else:
            self.stdout.write("  No warnings.")
