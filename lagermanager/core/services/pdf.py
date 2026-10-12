"""PDF helpers shared across apps.

merge_pdfs() concatenates already-rendered PDFs (and images) into one document.
PyMuPDF is imported lazily inside the function, the same way the rest of the
codebase treats it.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

_PDF_MAGIC = b'%PDF-'

# Enough to tell the common uploads apart; PyMuPDF sniffs the rest itself.
_IMAGE_MAGIC: tuple[tuple[bytes, str], ...] = (
    (b'\x89PNG', 'png'),
    (b'\xff\xd8', 'jpeg'),
    (b'GIF8', 'gif'),
    (b'BM', 'bmp'),
)


def _sniff_image_type(data: bytes) -> str:
    for magic, filetype in _IMAGE_MAGIC:
        if data.startswith(magic):
            return filetype
    return 'png'  # PyMuPDF's image handler copes with a wrong-but-plausible hint


def merge_pdfs(parts: Sequence[bytes | tuple[bytes, str]]) -> bytes:
    """Concatenate PDFs and images into a single PDF, in the given order.

    Each part is raw bytes, or a (bytes, filetype-hint) pair for images.  Parts
    that already are PDFs are inserted page for page; anything else is converted
    to a one-page PDF first.

    Raises ValueError for an empty sequence and RuntimeError when a part cannot
    be read, so a corrupt attachment surfaces as a clean error instead of an
    unhandled exception halfway through sending an email.
    """
    import pymupdf as _pymupdf  # noqa: PLC0415 — lazy import (matches deliveries/views.py)

    # PyMuPDF ships no type information, so every call into it reads as untyped
    # under mypy --strict.  Binding the module as Any once beats scattering
    # per-call ignores over the whole function.
    pymupdf: Any = _pymupdf

    if not parts:
        raise ValueError('merge_pdfs() braucht mindestens ein Dokument.')

    merged = pymupdf.open()
    try:
        for index, part in enumerate(parts, start=1):
            data, hint = part if isinstance(part, tuple) else (part, '')
            try:
                if data.startswith(_PDF_MAGIC):
                    source = pymupdf.open(stream=data, filetype='pdf')
                else:
                    image = pymupdf.open(
                        stream=data, filetype=hint or _sniff_image_type(data))
                    try:
                        source = pymupdf.open('pdf', image.convert_to_pdf())
                    finally:
                        image.close()
                try:
                    merged.insert_pdf(source)
                finally:
                    source.close()
            except Exception as exc:
                raise RuntimeError(
                    f'Teil {index} konnte nicht als PDF verarbeitet werden: {exc}'
                ) from exc
        return bytes(merged.tobytes())
    finally:
        merged.close()
