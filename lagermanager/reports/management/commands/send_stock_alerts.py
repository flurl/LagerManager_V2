import datetime
import zoneinfo
from typing import Any

from core.services.period import get_period_for_datetime
from django.core.management.base import BaseCommand
from notifications.models import Notification, StockAlertSubscription
from notifications.services.dispatcher import notify

from reports.services.stock_level_report import get_below_minimum_stock

_TZ = zoneinfo.ZoneInfo('Europe/Vienna')


class Command(BaseCommand):
    help = 'Send below-minimum-stock notifications to all active subscribers'

    def handle(self, *args: object, **options: object) -> None:
        now: datetime.datetime = datetime.datetime.now(tz=_TZ)
        period = get_period_for_datetime(now)
        if period is None:
            self.stdout.write(self.style.WARNING('No active period for today — skipping.'))
            return

        rows: list[dict[str, Any]] = get_below_minimum_stock(period.pk)
        if not rows:
            self.stdout.write('No articles below minimum stock.')
            return

        subscribers = StockAlertSubscription.objects.filter(active=True).select_related('user')
        if not subscribers.exists():
            self.stdout.write('No active subscribers — skipping.')
            return

        title = f'{len(rows)} Artikel unter Mindestbestand'
        lines = [
            f"- {r['article']}: {r['stock']} (Minimum: {r['minimum_inventory']}, Fehlmenge: {r['shortage']})"
            for r in rows
        ]
        message = '\n'.join(lines)

        count = 0
        for sub in subscribers:
            notify(
                sub.user,
                title=title,
                message=message,
                severity=Notification.Severity.WARNING,
                kind='stock_alert',
                link='/reports/below-minimum-stock',
            )
            count += 1

        self.stdout.write(
            self.style.SUCCESS(f'Notified {count} user(s): {len(rows)} articles below minimum.')
        )
