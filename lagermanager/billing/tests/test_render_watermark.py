"""Preview environments stamp a VORSCHAU watermark on every billing document."""
import datetime
from decimal import Decimal

import pymupdf
from core.models import Address
from core.services.customers import ensure_customer_for_address
from deliveries.models import TaxRate
from django.test import TestCase, override_settings

from billing.models import Invoice, InvoiceLine, Offer, Reminder
from billing.services.render import render_document_html, render_document_pdf


def _pdf_page_texts(pdf: bytes) -> list[str]:
    # pymupdf ships without type hints
    with pymupdf.open(stream=pdf, filetype='pdf') as document:  # type: ignore[no-untyped-call]
        return [page.get_text() for page in document]


class PreviewWatermarkTests(TestCase):
    def setUp(self) -> None:
        self.address = Address.objects.create(vorname='Max', nachname='Mustermann', ort='Wien')
        ensure_customer_for_address(self.address)
        self.offer = Offer.objects.create(
            customer=self.address.customer, address=self.address,
            document_date=datetime.date(2026, 6, 15),
        )
        self.invoice = Invoice.objects.create(
            customer=self.address.customer, address=self.address,
            document_date=datetime.date(2026, 6, 15), due_date=datetime.date(2026, 6, 29),
        )
        self.reminder = Reminder.objects.create(
            invoice=self.invoice, level=1,
            reminder_date=datetime.date(2026, 7, 1), due_date=datetime.date(2026, 7, 15),
        )

    def _fill_invoice(self, lines: int) -> None:
        tax = TaxRate.objects.create(name='Normal', percent=Decimal('20.00'))
        InvoiceLine.objects.bulk_create(
            InvoiceLine(
                invoice=self.invoice, position=i, description=f'Position {i}',
                quantity=Decimal('1'), unit_price=Decimal('10.00'), tax_rate=tax,
            )
            for i in range(1, lines + 1)
        )

    @override_settings(PREVIEW_BRANCH='feature/foo')
    def test_preview_html_carries_watermark_with_branch(self) -> None:
        """In a preview, offer, invoice and reminder HTML all contain the watermark.

        Each document type has its own template; all must keep extending the
        base template that renders the watermark.
        """
        for doc in (self.offer, self.invoice, self.reminder):
            with self.subTest(doc=type(doc).__name__):
                html = render_document_html(doc)
                self.assertIn('class="preview-watermark"', html)
                self.assertIn('feature/foo', html)

    @override_settings(PREVIEW_BRANCH='')
    def test_production_html_has_no_watermark(self) -> None:
        """Production documents (no PREVIEW_BRANCH) carry no watermark."""
        self.assertNotIn('class="preview-watermark"', render_document_html(self.invoice))

    @override_settings(PREVIEW_BRANCH='feature/foo')
    def test_preview_pdf_watermarks_every_page(self) -> None:
        """Every page of a multi-page preview PDF shows VORSCHAU.

        A preview runs on a copy of real data, so any single page printed or
        forwarded from it must be recognisable as not being a valid document.
        """
        self._fill_invoice(lines=80)

        pages = _pdf_page_texts(render_document_pdf(self.invoice))

        self.assertGreater(len(pages), 1)
        for number, text in enumerate(pages, start=1):
            with self.subTest(page=number):
                self.assertIn('VORSCHAU', text)
                self.assertIn('feature/foo', text)

    @override_settings(PREVIEW_BRANCH='')
    def test_production_pdf_has_no_watermark(self) -> None:
        """A production PDF contains no VORSCHAU text."""
        pages = _pdf_page_texts(render_document_pdf(self.invoice))
        self.assertTrue(all('VORSCHAU' not in text for text in pages))
