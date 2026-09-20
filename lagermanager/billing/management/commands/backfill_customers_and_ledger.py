"""
One-off (but idempotent) backfill for the customer/partial-payment feature.

Written as a management command rather than a data migration because the
amounts come from Invoice.gross_total, a Python property that does not exist on
the historical models a migration sees.  Being a command also makes it
re-runnable and --dry-run-able.

Steps, each skipped for rows that already have their data:
  0. groups that may already manage invoices get the new model permissions
  1. every Address without a customer gets one, 1:1, with itself as default
  2. every Offer/Invoice without a customer inherits its address's
  3. every non-draft Invoice gets its ledger charge
  4. every non-draft Reminder with a fee gets its ledger charge
  5. every Invoice already marked PAID gets a Payment for its total, so that the
     old boolean-style paid flag survives as a real payment record
"""
from decimal import Decimal
from typing import Any

from core.models import Address, Customer
from core.services.customers import ensure_customers_for_addresses
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q, Sum

from billing.models import CustomerLedgerEntry, Invoice, Offer, Payment, Reminder

ZERO = Decimal('0.00')


class Command(BaseCommand):
    help = 'Create customers for existing addresses and rebuild the customer ledger.'

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Report what would change without writing anything.',
        )

    def handle(self, *args: Any, **options: Any) -> None:
        dry_run: bool = options['dry_run']

        with transaction.atomic():
            perms = self._grant_new_permissions()
            customers = self._backfill_customers()
            documents = self._backfill_document_customers()
            invoices = self._backfill_invoice_charges()
            fees = self._backfill_reminder_fees()
            payments = self._backfill_paid_invoices()

            self.stdout.write(f'Rechte vergeben:            {perms}')
            self.stdout.write(f'Kunden angelegt:            {customers}')
            self.stdout.write(f'Dokumente zugeordnet:       {documents}')
            self.stdout.write(f'Rechnungsbuchungen:         {invoices}')
            self.stdout.write(f'Mahngebührenbuchungen:      {fees}')
            self.stdout.write(f'Zahlungen aus "bezahlt":    {payments}')

            self._print_balances()

            if dry_run:
                transaction.set_rollback(True)
                self.stdout.write(self.style.WARNING(
                    'Testlauf — nichts wurde gespeichert.'))
            else:
                self.stdout.write(self.style.SUCCESS('Fertig.'))

    # -- 0. permissions ----------------------------------------------------

    def _grant_new_permissions(self) -> int:
        """Give the new models' permissions to groups that already bill.

        DjangoModelPermissionsWithView guards the new endpoints, so without this
        the customer, payment and ledger views 403 for everyone who could
        previously manage invoices.  Keyed on billing.view_invoice so unrelated
        groups are left alone.
        """
        new_perms = list(Permission.objects.filter(
            Q(content_type__app_label='core',
              content_type__model__in=['customer', 'customernumbersequence'])
            | Q(content_type__app_label='billing',
                content_type__model__in=['payment', 'customerledgerentry'])
        ))
        if not new_perms:
            return 0

        granted = 0
        groups = Group.objects.filter(
            permissions__codename='view_invoice',
            permissions__content_type__app_label='billing',
        ).distinct()
        for group in groups:
            existing = set(group.permissions.values_list('pk', flat=True))
            missing = [p for p in new_perms if p.pk not in existing]
            if missing:
                group.permissions.add(*missing)
                granted += len(missing)
        return granted

    # -- 1. customers ------------------------------------------------------

    def _backfill_customers(self) -> int:
        return ensure_customers_for_addresses(
            list(Address.objects.filter(customer__isnull=True).order_by('pk')))

    # -- 2. documents ------------------------------------------------------

    def _backfill_document_customers(self) -> int:
        count = 0
        for model in (Offer, Invoice):
            for doc in model.objects.filter(
                    customer__isnull=True).select_related('address__customer'):
                if doc.address.customer_id is None:
                    continue
                doc.customer_id = doc.address.customer_id
                doc.save(update_fields=['customer'])
                count += 1
        return count

    # -- 3. invoice charges ------------------------------------------------

    def _backfill_invoice_charges(self) -> int:
        booked: set[int] = set(
            CustomerLedgerEntry.objects
            .filter(entry_type=CustomerLedgerEntry.EntryType.INVOICE,
                    invoice__isnull=False)
            .values_list('invoice_id', flat=True)
        )
        count = 0
        # Oldest first: Invoice.Meta.ordering is newest-first, which would write
        # the ledger backwards and leave a Storno sitting above the invoice it
        # reverses for anyone reading by insertion order.
        invoices = (
            Invoice.objects
            .exclude(status=Invoice.Status.DRAFT)
            .exclude(pk__in=booked)
            .filter(customer__isnull=False)
            .prefetch_related('lines__tax_rate')
            .order_by('document_date', 'pk')
        )
        for invoice in invoices:
            gross = invoice.gross_total
            if gross == 0:
                continue
            CustomerLedgerEntry.objects.create(
                customer=invoice.customer,
                entry_type=CustomerLedgerEntry.EntryType.INVOICE,
                entry_date=invoice.document_date,
                amount=-gross,
                description=f'Rechnung {invoice.number or f"#{invoice.pk}"}',
                invoice=invoice,
            )
            count += 1
        return count

    # -- 4. reminder fees --------------------------------------------------

    def _backfill_reminder_fees(self) -> int:
        booked: set[int] = set(
            CustomerLedgerEntry.objects
            .filter(entry_type=CustomerLedgerEntry.EntryType.REMINDER_FEE,
                    reminder__isnull=False)
            .values_list('reminder_id', flat=True)
        )
        count = 0
        reminders = (
            Reminder.objects
            .exclude(status=Reminder.Status.DRAFT)
            .exclude(pk__in=booked)
            .exclude(fee=ZERO)
            .select_related('invoice__customer')
            .order_by('reminder_date', 'pk')
        )
        for reminder in reminders:
            invoice = reminder.invoice
            if invoice.customer_id is None:
                continue
            CustomerLedgerEntry.objects.create(
                customer=invoice.customer,
                entry_type=CustomerLedgerEntry.EntryType.REMINDER_FEE,
                entry_date=reminder.reminder_date,
                amount=-reminder.fee,
                description=f'Mahngebühr {reminder.number or f"#{reminder.pk}"} '
                            f'(Rechnung {invoice.number or f"#{invoice.pk}"})',
                invoice=invoice,
                reminder=reminder,
            )
            count += 1
        return count

    # -- 5. payments for already-paid invoices -----------------------------

    def _backfill_paid_invoices(self) -> int:
        count = 0
        invoices = (
            Invoice.objects
            .filter(status=Invoice.Status.PAID, customer__isnull=False)
            .prefetch_related('lines__tax_rate', 'reminders', 'payments')
            .order_by('document_date', 'pk')
        )
        for invoice in invoices:
            if invoice.payments.exists():
                continue
            total_due = invoice.total_due
            if total_due <= 0:
                continue
            payment = Payment.objects.create(
                customer=invoice.customer,
                invoice=invoice,
                payment_date=invoice.paid_at or invoice.document_date,
                amount=total_due,
                method=Payment.Method.OTHER,
                note='Migriert aus Rechnungsstatus',
            )
            CustomerLedgerEntry.objects.create(
                customer=invoice.customer,
                entry_type=CustomerLedgerEntry.EntryType.PAYMENT,
                entry_date=payment.payment_date,
                amount=payment.amount,
                description=f'Zahlung Rechnung {invoice.number or f"#{invoice.pk}"}',
                invoice=invoice,
                payment=payment,
            )
            count += 1
        return count

    # -- summary -----------------------------------------------------------

    def _print_balances(self) -> None:
        rows = (
            Customer.objects
            .annotate(total=Sum('ledger_entries__amount'))
            .exclude(total=None)
            .exclude(total=ZERO)
            .order_by('customer_number')
        )
        if not rows:
            self.stdout.write('Alle Salden sind 0.')
            return
        self.stdout.write('\nSalden ungleich 0:')
        for customer in rows:
            self.stdout.write(f'  {customer}: {customer.total} €')
