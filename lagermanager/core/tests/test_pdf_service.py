"""Tests for core.services.pdf.merge_pdfs."""
import pymupdf
from django.test import SimpleTestCase

from core.services.pdf import merge_pdfs


def _pdf_bytes(pages: int = 1, text: str = 'Seite') -> bytes:
    doc = pymupdf.open()
    try:
        for index in range(pages):
            page = doc.new_page()
            page.insert_text((72, 72), f'{text} {index + 1}')
        return bytes(doc.tobytes())
    finally:
        doc.close()


def _png_bytes() -> bytes:
    doc = pymupdf.open()
    try:
        page = doc.new_page()
        return bytes(page.get_pixmap().tobytes('png'))
    finally:
        doc.close()


def _page_count(data: bytes) -> int:
    doc = pymupdf.open(stream=data, filetype='pdf')
    try:
        return int(doc.page_count)
    finally:
        doc.close()


class MergePdfsTests(SimpleTestCase):
    def test_concatenates_pdfs_in_order(self) -> None:
        merged = merge_pdfs([_pdf_bytes(1, 'A'), _pdf_bytes(2, 'B')])

        self.assertEqual(_page_count(merged), 3)

    def test_single_part_round_trips(self) -> None:
        self.assertEqual(_page_count(merge_pdfs([_pdf_bytes(2)])), 2)

    def test_converts_images_to_pages(self) -> None:
        merged = merge_pdfs([_pdf_bytes(), _png_bytes()])

        self.assertEqual(_page_count(merged), 2)

    def test_accepts_an_explicit_filetype_hint(self) -> None:
        merged = merge_pdfs([_pdf_bytes(), (_png_bytes(), 'png')])

        self.assertEqual(_page_count(merged), 2)

    def test_empty_input_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            merge_pdfs([])

    def test_unreadable_part_raises_runtime_error_naming_it(self) -> None:
        with self.assertRaises(RuntimeError) as ctx:
            merge_pdfs([_pdf_bytes(), b'nicht wirklich ein PDF'])

        self.assertIn('Teil 2', str(ctx.exception))
