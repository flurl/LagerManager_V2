"""
Link or delete attachments that ended up without a stock movement.

Between the skonto-flow change of April 2026 and its fix, StockMovementDialog
never linked attachments uploaded to a new movement, so they stayed with
stock_movement=None.  Which movement they belong to is not recorded; the user
decides from upload and creation times and passes it explicitly:

    manage.py link_attachments                          # list unlinked ones
    manage.py link_attachments --link 55=214 56=214 --delete 27 28 --dry-run

Only attachments without a movement are accepted, and every argument is checked
before anything is written.  --dry-run writes nothing at all instead of rolling
back: deleting an attachment removes its file in a post_delete signal, which a
rollback would not undo.
"""
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from deliveries.models import Attachment, StockMovement


def _parse_link(value: str) -> tuple[int, int]:
    attachment, sep, movement = value.partition('=')
    if not sep or not attachment.isdigit() or not movement.isdigit():
        raise CommandError(f'--link erwartet ANHANG=BEWEGUNG, nicht "{value}"')
    return int(attachment), int(movement)


class Command(BaseCommand):
    help = 'Link unlinked delivery attachments to their stock movement, or delete them.'

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            '--link', nargs='+', default=[], metavar='ANHANG=BEWEGUNG',
            help='Attach attachment ANHANG to stock movement BEWEGUNG.',
        )
        parser.add_argument(
            '--delete', nargs='+', default=[], type=int, metavar='ANHANG',
            help='Delete the attachment and its file.',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Report what would change without writing anything.',
        )

    def handle(self, *args: Any, **options: Any) -> None:
        links: dict[int, int] = dict(_parse_link(v) for v in options['link'])
        deletes: list[int] = options['delete']
        dry_run: bool = options['dry_run']

        if not links and not deletes:
            self._list_unlinked()
            return

        both: set[int] = set(links) & set(deletes)
        if both:
            raise CommandError(f'Sowohl --link als auch --delete: {sorted(both)}')

        attachments: dict[int, Attachment] = {
            a.pk: a for a in Attachment.objects.filter(pk__in=[*links, *deletes])
        }
        missing: set[int] = {pk for pk in [*links, *deletes] if pk not in attachments}
        if missing:
            raise CommandError(f'Anhänge nicht gefunden: {sorted(missing)}')
        already: list[int] = sorted(
            pk for pk, a in attachments.items() if a.stock_movement_id is not None)
        if already:
            raise CommandError(f'Anhänge haben schon eine Bewegung: {already}')

        movements: dict[int, StockMovement] = StockMovement.objects.in_bulk(
            list(set(links.values())))
        unknown: list[int] = sorted(set(links.values()) - set(movements))
        if unknown:
            raise CommandError(f'Bewegungen nicht gefunden: {unknown}')

        for pk, movement_pk in sorted(links.items()):
            self.stdout.write(f'{self._label(attachments[pk])} → {movements[movement_pk]}')
        for pk in sorted(deletes):
            self.stdout.write(f'{self._label(attachments[pk])} → löschen')

        if dry_run:
            self.stdout.write(self.style.WARNING('Testlauf — nichts wurde gespeichert.'))
            return

        with transaction.atomic():
            for pk, movement_pk in links.items():
                attachment = attachments[pk]
                attachment.stock_movement_id = movement_pk
                attachment.save(update_fields=['stock_movement'])
            for pk in deletes:
                attachments[pk].delete()
        self.stdout.write(self.style.SUCCESS(
            f'Fertig: {len(links)} verknüpft, {len(deletes)} gelöscht.'))

    def _list_unlinked(self) -> None:
        unlinked = Attachment.objects.filter(stock_movement__isnull=True).order_by('created_at')
        if not unlinked:
            self.stdout.write('Keine Anhänge ohne Bewegung.')
            return
        for attachment in unlinked:
            self.stdout.write(self._label(attachment))

    @staticmethod
    def _label(attachment: Attachment) -> str:
        created = attachment.created_at.strftime('%Y-%m-%d %H:%M')
        return f'{attachment.pk} {created} {attachment}'
