import datetime
import zoneinfo

from django.core.management.base import BaseCommand
from notifications.models import InvoiceAlertSubscription, Notification
from notifications.services.dispatcher import notify

from billing.models import Invoice

_TZ = zoneinfo.ZoneInfo('Europe/Vienna')


def _get_today() -> datetime.date:
    return datetime.datetime.now(tz=_TZ).date()


class Command(BaseCommand):
    help = 'Send overdue-invoice notifications to all active subscribers'

    def handle(self, *args: object, **options: object) -> None:
        today: datetime.date = _get_today()

        overdue: list[Invoice] = list(
            Invoice.objects.filter(
                status__in=[Invoice.Status.ISSUED, Invoice.Status.SENT],
                due_date__lt=today,
            ).select_related('address').order_by('due_date')
        )

        if not overdue:
            self.stdout.write('No overdue invoices.')
            return

        subscribers = InvoiceAlertSubscription.objects.filter(active=True).select_related('user')
        if not subscribers.exists():
            self.stdout.write('No active subscribers — skipping.')
            return

        count_label = (
            '1 überfällige Rechnung'
            if len(overdue) == 1
            else f'{len(overdue)} überfällige Rechnungen'
        )
        title = count_label
        lines = [
            f"- {inv}: fällig {inv.due_date.strftime('%d.%m.%Y')}"
            for inv in overdue
        ]
        message = '\n'.join(lines)

        count = 0
        for sub in subscribers:
            notify(
                sub.user,
                title=title,
                message=message,
                severity=Notification.Severity.WARNING,
                kind='invoice_alert',
                link='/invoices',
            )
            count += 1

        self.stdout.write(
            self.style.SUCCESS(f'Notified {count} user(s): {len(overdue)} overdue invoice(s).')
        )
