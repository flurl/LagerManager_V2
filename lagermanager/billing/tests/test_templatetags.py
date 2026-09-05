"""Tests for the billing template filters."""
from decimal import Decimal

from django.template import Context, Template
from django.test import TestCase

from billing.templatetags.billing_extras import trim_zeros


class TrimZerosTests(TestCase):
    """The quantity column drops trailing decimal zeros (de-at separator)."""

    def test_trims_trailing_zeros(self) -> None:
        self.assertEqual(trim_zeros(Decimal('19.5000')), '19,5')
        self.assertEqual(trim_zeros(Decimal('8.1250')), '8,125')
        self.assertEqual(trim_zeros(Decimal('0.0500')), '0,05')

    def test_whole_numbers_lose_the_decimal_part(self) -> None:
        self.assertEqual(trim_zeros(Decimal('3.0000')), '3')
        self.assertEqual(trim_zeros(Decimal('1')), '1')
        self.assertEqual(trim_zeros(Decimal('100.0000')), '100')

    def test_keeps_four_decimals_when_significant(self) -> None:
        self.assertEqual(trim_zeros(Decimal('0.1234')), '0,1234')
        self.assertEqual(trim_zeros(Decimal('12.3456')), '12,3456')

    def test_rounds_beyond_four_decimals(self) -> None:
        self.assertEqual(trim_zeros(Decimal('1.00005')), '1,0001')

    def test_negative_values(self) -> None:
        self.assertEqual(trim_zeros(Decimal('-2.5000')), '-2,5')

    def test_non_numeric_values_render_empty(self) -> None:
        """Same fallback as ``floatformat``, which these templates used before."""
        self.assertEqual(trim_zeros(None), '')
        self.assertEqual(trim_zeros(''), '')
        self.assertEqual(trim_zeros('abc'), '')

    def test_usable_as_a_template_filter(self) -> None:
        template = Template("{% load billing_extras %}{{ value|trim_zeros }}")
        rendered: str = template.render(Context({'value': Decimal('19.5000')}))
        self.assertEqual(rendered, '19,5')
