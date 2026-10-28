"""
One-off (but idempotent) repair of the customers the WZ address sync duplicated.

backfill_customers_and_ledger created a customer for every address without a
wz_source_id.  The WZ sync, which then looked customers up by wz_source_id only,
created a second customer for every WZ address and moved the address over to
it.  So for each WZ address there is now

  - the old customer: no wz_source_id, the address still its default address,
    holding the backfilled documents, ledger entries and payments, and
  - the duplicate: the address's wz_source_id, owning the address and whatever
    was billed to it since.

The old customer is kept, because its number is the one on the documents issued
before.  The duplicate's addresses, offers, invoices, payments and ledger entries
move to it, empty contact fields are filled from the duplicate, its notes are
appended, it takes over the wz_source_id and the duplicate is deleted.  Documents
issued under the duplicate show the old customer's number from then on; the
command lists them.
"""
from typing import Any

from core.models import Address, Customer
from django.core.management.base import BaseCommand
from django.db import models, transaction
from django.db.models import F

from billing.models import CustomerLedgerEntry, Invoice, Offer, Payment

# Everything that points at a customer.  All but Address are PROTECT, so the
# delete of the duplicate fails rather than lose anything that was missed here.
_REFERENCING_MODELS: tuple[type[models.Model], ...] = (
    Address, Offer, Invoice, Payment, CustomerLedgerEntry,
)


class Command(BaseCommand):
    help = 'Merge the customers the WZ address sync duplicated into the original ones.'

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Report what would change without writing anything.',
        )

    def handle(self, *args: Any, **options: Any) -> None:
        dry_run: bool = options['dry_run']

        with transaction.atomic():
            pairs: list[tuple[Customer, Customer]] = self._find_pairs()
            for keep, dup in pairs:
                self._report(keep, dup)
                self._merge(keep, dup)

            self.stdout.write(f'Zusammengeführt:            {len(pairs)}')

            if dry_run:
                transaction.set_rollback(True)
                self.stdout.write(self.style.WARNING(
                    'Testlauf — nichts wurde gespeichert.'))
            else:
                self.stdout.write(self.style.SUCCESS('Fertig.'))

    def _find_pairs(self) -> list[tuple[Customer, Customer]]:
        """(old, duplicate) for every old customer whose WZ default address the
        sync gave to a customer keyed on that address."""
        olds = (
            Customer.objects
            .filter(wz_source_id__isnull=True, default_address__wz_source_id__isnull=False)
            .exclude(default_address__customer=F('pk'))
            .select_related('default_address')
            .order_by('customer_number', 'pk')
        )
        pairs: list[tuple[Customer, Customer]] = []
        for old in olds:
            address: Address | None = old.default_address
            assert address is not None
            dup: Customer | None = None if address.customer_id is None else (
                Customer.objects.filter(
                    wz_source_id=address.wz_source_id, pk=address.customer_id).first())
            if dup is None:
                self.stdout.write(self.style.WARNING(
                    f'Übersprungen: {old} — Standardadresse {address.pk} gehört '
                    f'Kunde #{address.customer_id}, der nicht zu ihr synchronisiert wurde.'))
                continue
            pairs.append((old, dup))
        return pairs

    def _report(self, keep: Customer, dup: Customer) -> None:
        counts = ', '.join(
            f'{model._meta.verbose_name_plural}: {model._default_manager.filter(customer=dup).count()}'
            for model in _REFERENCING_MODELS
        )
        self.stdout.write(f'{dup} → {keep} ({counts})')
        issued: list[str] = [
            *(str(inv.number) for inv in
              Invoice.objects.filter(customer=dup).exclude(status=Invoice.Status.DRAFT)),
            *(str(offer.number) for offer in
              Offer.objects.filter(customer=dup, number__isnull=False).exclude(number='')),
        ]
        if issued:
            self.stdout.write(self.style.WARNING(
                f'  Achtung: ausgestellt unter {dup.customer_number}, zeigen künftig '
                f'{keep.customer_number}: {", ".join(issued)}'))

    def _merge(self, keep: Customer, dup: Customer) -> None:
        # Saved one by one rather than with update() so auditlog records each move.
        for model in _REFERENCING_MODELS:
            for obj in model._default_manager.filter(customer=dup):
                obj.customer = keep  # type: ignore[attr-defined]
                obj.save(update_fields=['customer'])

        for field in ('email', 'telefon', 'uid'):
            if not getattr(keep, field) and getattr(dup, field):
                setattr(keep, field, getattr(dup, field))
        if dup.notes and dup.notes not in keep.notes:
            keep.notes = f'{keep.notes}\n\n{dup.notes}' if keep.notes else dup.notes

        wz_source_id = dup.wz_source_id
        dup.delete()  # frees the unique wz_source_id for keep
        keep.wz_source_id = wz_source_id
        keep.save(update_fields=['wz_source_id', 'email', 'telefon', 'uid', 'notes'])
