"""Tests for the link_attachments management command."""
import shutil
import tempfile
from datetime import date, timedelta
from io import StringIO

from core.models import Period
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone

from deliveries.models import Attachment, Partner, StockMovement

MEDIA_ROOT = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class LinkAttachmentsTests(TestCase):
    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def setUp(self) -> None:
        period = Period.objects.create(
            name='P', start=timezone.now() - timedelta(days=10),
            end=timezone.now() + timedelta(days=10))
        self.movement = StockMovement.objects.create(
            partner=Partner.objects.create(name='Morandell'),
            date=date(2026, 5, 22), period=period)
        self.orphan = self._attachment(None)
        self.linked = self._attachment(self.movement)

    def _attachment(self, movement: StockMovement | None) -> Attachment:
        attachment = Attachment(stock_movement=movement, original_filename='r.png')
        attachment.file.save('r.png', ContentFile(b'png'), save=True)
        return attachment

    def _run(self, *args: str) -> str:
        out = StringIO()
        call_command('link_attachments', *args, stdout=out)
        return out.getvalue()

    def test_links_an_orphan_to_the_given_movement(self) -> None:
        """--link A=M sets the attachment's movement."""
        self._run('--link', f'{self.orphan.pk}={self.movement.pk}')
        self.orphan.refresh_from_db()
        self.assertEqual(self.orphan.stock_movement_id, self.movement.pk)

    def test_deletes_an_orphan_with_its_file(self) -> None:
        """--delete removes the row and, via the post_delete signal, the file."""
        name = str(self.orphan.file.name)
        storage = self.orphan.file.storage
        self._run('--delete', str(self.orphan.pk))
        self.assertFalse(Attachment.objects.filter(pk=self.orphan.pk).exists())
        self.assertFalse(storage.exists(name))

    def test_dry_run_changes_nothing_and_keeps_the_file(self) -> None:
        """A rollback cannot restore a deleted file, so the dry run must not delete at all."""
        name = str(self.orphan.file.name)
        self._run('--delete', str(self.orphan.pk), '--dry-run')
        self.assertTrue(Attachment.objects.filter(pk=self.orphan.pk).exists())
        self.assertTrue(self.orphan.file.storage.exists(name))

    def test_refuses_attachments_that_already_have_a_movement(self) -> None:
        """Only unlinked attachments may be touched; a typo must not re-home a linked one."""
        with self.assertRaises(CommandError):
            self._run('--delete', str(self.linked.pk))
        self.assertTrue(Attachment.objects.filter(pk=self.linked.pk).exists())

    def test_refuses_unknown_movements_and_writes_nothing(self) -> None:
        """All arguments are checked before anything is written."""
        other = self._attachment(None)
        with self.assertRaisesMessage(CommandError, 'Bewegungen nicht gefunden'):
            self._run('--link', f'{self.orphan.pk}=999999', '--delete', str(other.pk))
        self.assertTrue(Attachment.objects.filter(pk=other.pk).exists())

    def test_lists_unlinked_attachments_without_arguments(self) -> None:
        """Without --link/--delete it only reports what is still unlinked."""
        listed: list[str] = [line.split()[0] for line in self._run().splitlines()]
        self.assertEqual(listed, [str(self.orphan.pk)])
