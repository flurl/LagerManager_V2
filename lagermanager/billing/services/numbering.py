"""
Gapless document number allocation for offers, invoices and reminders.

Format: {PREFIX}{YY}{MM}{NN}
  PREFIX  — per-document-type prefix from Constance (e.g. AN / RE / MA)
  YY      — 2-digit year  (e.g. 26 for 2026)
  MM      — 2-digit month (e.g. 06 for June)
  NN      — sequential counter, zero-padded to ≥2 digits, widening past 99 automatically

The counter resets every month (keyed on doc_type + year + month).
Numbers are only allocated on document *issue*; drafts never consume a number.

Example: 3rd offer issued in June 2026 with prefix AN → AN260603
"""
import datetime

from constance import config
from django.db import transaction

from billing.models import NumberSequence

_PREFIX_ATTR: dict[str, str] = {
    NumberSequence.DocType.OFFER: 'OFFER_NUMBER_PREFIX',
    NumberSequence.DocType.INVOICE: 'INVOICE_NUMBER_PREFIX',
    NumberSequence.DocType.REMINDER: 'REMINDER_NUMBER_PREFIX',
}


def allocate_article_number() -> str:
    """
    Allocate the next auto-assigned billing article number.

    Format: _NNNN (zero-padded to 4 digits, widens automatically beyond 9999).
    Must be called inside a transaction.atomic() so that both the sequence
    increment and the article row are created or rolled back together.
    """
    from billing.models import ArticleNumberSequence

    with transaction.atomic():
        seq, _ = (
            ArticleNumberSequence.objects
            .select_for_update()
            .get_or_create(pk=1, defaults={'last_value': 0})
        )
        seq.last_value += 1
        seq.save(update_fields=['last_value'])
        n = seq.last_value

    return f'#{n:04d}'


def allocate_number(doc_type: str, document_date: datetime.date) -> str:
    """
    Allocate the next sequential number for the given document type and date.

    Raises ValueError for an unknown doc_type.
    Must be called inside (or starts its own) transaction.atomic() with select_for_update
    to prevent concurrent allocation of the same number.
    """
    if doc_type not in _PREFIX_ATTR:
        raise ValueError(f'Unknown doc_type: {doc_type!r}')

    prefix: str = getattr(config, _PREFIX_ATTR[doc_type], '') or ''
    year = document_date.year % 100  # 2026 → 26
    month = document_date.month

    with transaction.atomic():
        seq, _ = (
            NumberSequence.objects
            .select_for_update()
            .get_or_create(
                doc_type=doc_type,
                year=document_date.year,
                month=month,
                defaults={'last_value': 0},
            )
        )
        seq.last_value += 1
        seq.save(update_fields=['last_value'])
        n = seq.last_value

    # Zero-pad to at least 2 digits; widens automatically for values ≥ 100
    nn = f'{n:02d}'
    return f'{prefix}{year:02d}{month:02d}{nn}'
