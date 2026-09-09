"""Tests for the document numbering service."""
import datetime
from unittest.mock import patch

from django.test import TestCase

from billing.models import (
    ArticleNumberSequence,
    ContinuousNumberSequence,
    NumberSequence,
)
from billing.services.numbering import allocate_article_number, allocate_number


class AllocateNumberTests(TestCase):
    """Test monthly-resetting gapless numbering."""

    def _date(self, year: int, month: int, day: int = 1) -> datetime.date:
        return datetime.date(year, month, day)

    @patch('billing.services.numbering.config')
    def test_first_number_in_month(self, mock_config: object) -> None:
        mock_config.OFFER_NUMBER_PREFIX = 'AN'
        n = allocate_number(NumberSequence.DocType.OFFER, self._date(2026, 6))
        self.assertEqual(n, 'AN260601')

    @patch('billing.services.numbering.config')
    def test_sequential_within_month(self, mock_config: object) -> None:
        mock_config.INVOICE_NUMBER_PREFIX = 'RE'
        d = self._date(2026, 6)
        n1 = allocate_number(NumberSequence.DocType.INVOICE, d)
        n2 = allocate_number(NumberSequence.DocType.INVOICE, d)
        n3 = allocate_number(NumberSequence.DocType.INVOICE, d)
        self.assertEqual(n1, 'RE260601-00001')
        self.assertEqual(n2, 'RE260602-00002')
        self.assertEqual(n3, 'RE260603-00003')

    @patch('billing.services.numbering.config')
    def test_resets_each_month(self, mock_config: object) -> None:
        mock_config.INVOICE_NUMBER_PREFIX = 'RE'
        n_june = allocate_number(NumberSequence.DocType.INVOICE, self._date(2026, 6))
        n_july = allocate_number(NumberSequence.DocType.INVOICE, self._date(2026, 7))
        self.assertEqual(n_june, 'RE260601-00001')
        self.assertEqual(n_july, 'RE260701-00002')

    @patch('billing.services.numbering.config')
    def test_resets_each_year(self, mock_config: object) -> None:
        mock_config.INVOICE_NUMBER_PREFIX = 'RE'
        n_2025 = allocate_number(NumberSequence.DocType.INVOICE, self._date(2025, 12))
        n_2026 = allocate_number(NumberSequence.DocType.INVOICE, self._date(2026, 1))
        self.assertEqual(n_2025, 'RE251201-00001')
        self.assertEqual(n_2026, 'RE260101-00002')

    @patch('billing.services.numbering.config')
    def test_widens_past_99(self, mock_config: object) -> None:
        mock_config.REMINDER_NUMBER_PREFIX = 'MA'
        d = self._date(2026, 3)
        # Allocate 99 numbers first
        for _ in range(99):
            allocate_number(NumberSequence.DocType.REMINDER, d)
        n100 = allocate_number(NumberSequence.DocType.REMINDER, d)
        self.assertEqual(n100, 'MA2603100')

    @patch('billing.services.numbering.config')
    def test_different_doc_types_independent(self, mock_config: object) -> None:
        mock_config.OFFER_NUMBER_PREFIX = 'AN'
        mock_config.INVOICE_NUMBER_PREFIX = 'RE'
        d = self._date(2026, 6)
        o1 = allocate_number(NumberSequence.DocType.OFFER, d)
        i1 = allocate_number(NumberSequence.DocType.INVOICE, d)
        o2 = allocate_number(NumberSequence.DocType.OFFER, d)
        self.assertEqual(o1, 'AN260601')
        self.assertEqual(i1, 'RE260601-00001')
        self.assertEqual(o2, 'AN260602')

    def test_unknown_doc_type_raises(self) -> None:
        with self.assertRaises(ValueError):
            allocate_number('bogus', self._date(2026, 1))


class ContinuousInvoiceSuffixTests(TestCase):
    """The continuous suffix is invoice-only and never resets."""

    def _date(self, year: int, month: int, day: int = 1) -> datetime.date:
        return datetime.date(year, month, day)

    @patch('billing.services.numbering.config')
    def test_first_invoice_starts_at_one(self, mock_config: object) -> None:
        mock_config.INVOICE_NUMBER_PREFIX = 'PG'
        n = allocate_number(NumberSequence.DocType.INVOICE, self._date(2026, 9))
        self.assertEqual(n, 'PG260901-00001')

    @patch('billing.services.numbering.config')
    def test_suffix_survives_month_and_year_rollover(self, mock_config: object) -> None:
        mock_config.INVOICE_NUMBER_PREFIX = 'PG'
        numbers: list[str] = [
            allocate_number(NumberSequence.DocType.INVOICE, self._date(2026, 11)),
            allocate_number(NumberSequence.DocType.INVOICE, self._date(2026, 12)),
            allocate_number(NumberSequence.DocType.INVOICE, self._date(2027, 1)),
            allocate_number(NumberSequence.DocType.INVOICE, self._date(2027, 1)),
        ]
        self.assertEqual(numbers, [
            'PG261101-00001',
            'PG261201-00002',
            'PG270101-00003',
            'PG270102-00004',
        ])

    @patch('billing.services.numbering.config')
    def test_offers_and_reminders_get_no_suffix(self, mock_config: object) -> None:
        mock_config.OFFER_NUMBER_PREFIX = 'AN'
        mock_config.REMINDER_NUMBER_PREFIX = 'MA'
        d = self._date(2026, 9)
        offer = allocate_number(NumberSequence.DocType.OFFER, d)
        reminder = allocate_number(NumberSequence.DocType.REMINDER, d)
        self.assertEqual(offer, 'AN260901')
        self.assertEqual(reminder, 'MA260901')
        self.assertFalse(ContinuousNumberSequence.objects.exists())

    @patch('billing.services.numbering.config')
    def test_other_doc_types_do_not_consume_counter(self, mock_config: object) -> None:
        mock_config.OFFER_NUMBER_PREFIX = 'AN'
        mock_config.INVOICE_NUMBER_PREFIX = 'PG'
        d = self._date(2026, 9)
        allocate_number(NumberSequence.DocType.OFFER, d)
        allocate_number(NumberSequence.DocType.REMINDER, d)
        self.assertEqual(
            allocate_number(NumberSequence.DocType.INVOICE, d), 'PG260901-00001')

    @patch('billing.services.numbering.config')
    def test_widens_past_99999(self, mock_config: object) -> None:
        mock_config.INVOICE_NUMBER_PREFIX = 'PG'
        ContinuousNumberSequence.objects.create(
            doc_type=NumberSequence.DocType.INVOICE, last_value=99999)
        n = allocate_number(NumberSequence.DocType.INVOICE, self._date(2026, 9))
        self.assertEqual(n, 'PG260901-100000')

    @patch('billing.services.numbering.config')
    def test_continues_from_existing_sequence_row(self, mock_config: object) -> None:
        mock_config.INVOICE_NUMBER_PREFIX = 'PG'
        ContinuousNumberSequence.objects.create(
            doc_type=NumberSequence.DocType.INVOICE, last_value=41)
        n = allocate_number(NumberSequence.DocType.INVOICE, self._date(2026, 9))
        self.assertEqual(n, 'PG260901-00042')
        seq: ContinuousNumberSequence = ContinuousNumberSequence.objects.get(
            doc_type=NumberSequence.DocType.INVOICE)
        self.assertEqual(seq.last_value, 42)


class AllocateArticleNumberTests(TestCase):
    """Test auto article number allocation."""

    def test_first_number(self) -> None:
        self.assertEqual(allocate_article_number(), '#0001')

    def test_sequential(self) -> None:
        n1 = allocate_article_number()
        n2 = allocate_article_number()
        n3 = allocate_article_number()
        self.assertEqual(n1, '#0001')
        self.assertEqual(n2, '#0002')
        self.assertEqual(n3, '#0003')

    def test_widens_past_9999(self) -> None:
        ArticleNumberSequence.objects.create(pk=1, last_value=9999)
        n = allocate_article_number()
        self.assertEqual(n, '#10000')

    def test_sequence_row_created(self) -> None:
        allocate_article_number()
        seq = ArticleNumberSequence.objects.get(pk=1)
        self.assertEqual(seq.last_value, 1)

    @patch('billing.services.numbering.config')
    def test_number_sequence_row_created(self, mock_config: object) -> None:
        mock_config.OFFER_NUMBER_PREFIX = 'AN'
        allocate_number(NumberSequence.DocType.OFFER, datetime.date(2026, 9, 15))
        seq = NumberSequence.objects.get(
            doc_type=NumberSequence.DocType.OFFER, year=2026, month=9)
        self.assertEqual(seq.last_value, 1)
