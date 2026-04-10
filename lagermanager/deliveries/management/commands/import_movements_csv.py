"""Management command to import stock movements from a prepared CSV file.

CSV FORMAT
----------
Expected columns (comma-separated, header row required):

    movement date     — date/datetime of the movement (e.g. "2026-01-08 00:00:00")
    is consumption    — 1 = consumption (Verbrauch), 0 = delivery (Lieferung)
    comment           — free-text note (invoice/delivery-note number, event name, etc.)
    article source id — POS source ID of the article (pos_import.Article.source_id),
                        NOT the Django primary key
    amount            — quantity; negative values are accepted and made positive automatically
    price             — unit purchase price; German decimal format (comma as separator, e.g. "1,79")

Encoding: latin-1 (Windows-1252 compatible).

GROUPING
--------
Rows are grouped into StockMovement records by (movement date, is consumption, comment).
Each unique combination creates one movement header; all matching rows become its detail lines.

REQUIRED ARGUMENTS
------------------
    csv_file              path to the CSV file
    --period              Django Period ID to assign all movements to
    --delivery-partner    Django Partner ID for delivery movements
    --consumption-partner Django Partner ID for consumption movements
    --tax-rate            Django TaxRate ID applied to every detail line
"""

import csv
from argparse import ArgumentParser
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from pos_import.models import Article

from deliveries.models import StockMovement, StockMovementDetail


def _parse_price(value: str) -> Decimal:
    """Parse a German-locale decimal string (comma separator) to Decimal."""
    cleaned = value.strip().replace(',', '.')
    if not cleaned:
        return Decimal('0')
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return Decimal('0')


class Command(BaseCommand):
    help = 'Import stock movements from a prepared CSV file.'

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument('csv_file', type=str, help='Path to the CSV file')
        parser.add_argument(
            '--period', type=int, required=True,
            help='Django Period ID to assign all movements to',
        )
        parser.add_argument(
            '--delivery-partner', type=int, required=True,
            help='Django Partner ID for delivery movements (is_consumption=0)',
        )
        parser.add_argument(
            '--consumption-partner', type=int, required=True,
            help='Django Partner ID for consumption movements (is_consumption=1)',
        )
        parser.add_argument(
            '--tax-rate', type=int, required=True,
            help='Django TaxRate ID applied to every detail line',
        )

    def handle(self, *args: Any, **options: Any) -> None:
        csv_path = Path(options['csv_file'])
        if not csv_path.exists():
            raise CommandError(f'File not found: {csv_path}')

        period_id: int = options['period']
        delivery_partner_id: int = options['delivery_partner']
        consumption_partner_id: int = options['consumption_partner']
        tax_rate_id: int = options['tax_rate']

        # Build article lookup: source_id -> Article for the given period
        article_map: dict[int, Article] = {
            a.source_id: a
            for a in Article.objects.filter(period_id=period_id)
        }
        self.stdout.write(f'Loaded {len(article_map)} articles for period {period_id}')

        # Parse CSV rows
        rows: list[dict[str, str]] = []
        with csv_path.open(encoding='latin-1', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)
        self.stdout.write(f'Read {len(rows)} rows from CSV')

        # Group rows into movements by (date, is_consumption, comment).
        # Insertion order is preserved so movements are created in file order.
        movement_keys: list[tuple[str, str, str]] = []
        movement_groups: dict[tuple[str, str, str], list[dict[str, str]]] = {}
        for row in rows:
            key = (
                row['movement date'].strip()[:10],  # date part only
                row['is consumption'].strip(),
                row['comment'].strip(),
            )
            if key not in movement_groups:
                movement_keys.append(key)
                movement_groups[key] = []
            movement_groups[key].append(row)

        self.stdout.write(f'Found {len(movement_keys)} distinct movements')

        missing_articles: set[int] = set()
        movements_created = 0
        details_created = 0

        with transaction.atomic():
            for key in movement_keys:
                date_str, is_consumption_str, comment = key
                group = movement_groups[key]

                is_consumption = is_consumption_str == '1'
                movement_type = (
                    StockMovement.Type.CONSUMPTION
                    if is_consumption
                    else StockMovement.Type.DELIVERY
                )
                partner_id = consumption_partner_id if is_consumption else delivery_partner_id

                movement = StockMovement.objects.create(
                    date=date_str,
                    movement_type=movement_type,
                    comment=comment or None,
                    partner_id=partner_id,
                    period_id=period_id,
                )
                movements_created += 1

                for row in group:
                    source_id = int(row['article source id'].strip())
                    article = article_map.get(source_id)
                    if article is None:
                        missing_articles.add(source_id)
                        self.stderr.write(
                            f'  WARNING: article source_id {source_id} not found — skipping detail'
                        )
                        continue

                    quantity = abs(_parse_price(row['amount']))
                    unit_price = _parse_price(row['price'])

                    StockMovementDetail.objects.create(
                        stock_movement=movement,
                        article=article,
                        quantity=quantity,
                        unit_price=unit_price,
                        tax_rate_id=tax_rate_id,
                    )
                    details_created += 1

        self.stdout.write(self.style.SUCCESS(
            f'Done. Created {movements_created} movements, {details_created} details.'
        ))
        if missing_articles:
            self.stderr.write(
                f'Missing article source IDs (skipped): {sorted(missing_articles)}'
            )
