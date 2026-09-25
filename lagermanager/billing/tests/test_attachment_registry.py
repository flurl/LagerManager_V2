"""Unit tests for the attachment kind registry and the send-selection helpers."""
from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase

from billing.attachments import (
    AttachmentHandler,
    UnknownAttachmentKind,
    get_handler,
    kind_infos,
    known_kinds,
    register,
)
from billing.attachments.handlers import FileHandler, SupplementHandler
from billing.attachments.send import _unique_filename, parse_kind_setting
from billing.models import DocumentAttachment


class RegistryTests(TestCase):
    def test_ships_both_kinds(self) -> None:
        self.assertEqual(set(known_kinds()), {'supplement', 'file'})
        self.assertIsInstance(get_handler('supplement'), SupplementHandler)
        self.assertIsInstance(get_handler('file'), FileHandler)

    def test_unknown_kind_raises(self) -> None:
        with self.assertRaises(UnknownAttachmentKind):
            get_handler('does-not-exist')

    def test_kind_infos_expose_the_ui_flags(self) -> None:
        infos = {info.kind: info for info in kind_infos()}

        self.assertEqual(infos['supplement'].label, 'Ergänzung')
        self.assertTrue(infos['supplement'].supports_merge)
        self.assertTrue(infos['supplement'].renderable)
        self.assertFalse(infos['supplement'].requires_file)
        self.assertEqual(
            infos['supplement'].default_delivery, DocumentAttachment.Delivery.MERGE)

        self.assertEqual(infos['file'].label, 'Datei')
        self.assertFalse(infos['file'].supports_merge)
        self.assertFalse(infos['file'].renderable)
        self.assertTrue(infos['file'].requires_file)
        self.assertEqual(
            infos['file'].default_delivery, DocumentAttachment.Delivery.SEPARATE)

    def test_kind_info_is_json_serialisable(self) -> None:
        info = get_handler('supplement').info().as_dict()
        self.assertEqual(info['kind'], 'supplement')
        self.assertIn('help_text', info)

    def test_duplicate_registration_is_rejected(self) -> None:
        with self.assertRaises(ImproperlyConfigured):
            @register
            class Duplicate(AttachmentHandler):
                kind = 'supplement'
                label = 'Nochmal'

    def test_registration_requires_a_kind(self) -> None:
        with self.assertRaises(ImproperlyConfigured):
            @register
            class Nameless(AttachmentHandler):
                label = 'Ohne kind'


class ResolveDeliveryTests(TestCase):
    """A stored delivery mode is never trusted beyond what the kind supports."""

    def test_supplement_honours_both_modes(self) -> None:
        handler = get_handler('supplement')
        for mode in (DocumentAttachment.Delivery.MERGE,
                     DocumentAttachment.Delivery.SEPARATE):
            attachment = DocumentAttachment(kind='supplement', delivery=mode)
            self.assertEqual(handler.resolve_delivery(attachment), mode)

    def test_file_is_always_separate_even_if_the_row_says_merge(self) -> None:
        attachment = DocumentAttachment(
            kind='file', delivery=DocumentAttachment.Delivery.MERGE)
        self.assertEqual(
            get_handler('file').resolve_delivery(attachment),
            DocumentAttachment.Delivery.SEPARATE,
        )


class ParseKindSettingTests(TestCase):
    def test_drops_unknown_and_blank_entries(self) -> None:
        self.assertEqual(
            parse_kind_setting('supplement, bogus ,file, '),
            ['supplement', 'file'],
        )

    def test_empty_setting_selects_nothing(self) -> None:
        self.assertEqual(parse_kind_setting(''), [])
        self.assertEqual(parse_kind_setting('   '), [])


class UniqueFilenameTests(TestCase):
    def test_suffixes_collisions_and_keeps_the_extension(self) -> None:
        used: set[str] = set()
        self.assertEqual(_unique_filename('beleg.pdf', used), 'beleg.pdf')
        self.assertEqual(_unique_filename('beleg.pdf', used), 'beleg_2.pdf')
        self.assertEqual(_unique_filename('beleg.pdf', used), 'beleg_3.pdf')

    def test_handles_names_without_extension(self) -> None:
        used: set[str] = {'beleg'}
        self.assertEqual(_unique_filename('beleg', used), 'beleg_2')
