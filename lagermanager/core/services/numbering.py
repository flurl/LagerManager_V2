"""
Auto-assigned number allocation for core models.

Only customers need a number so far; the names here are qualified per model so
a second sequence can be added alongside without renaming anything or shadowing
what is already here.

Customer numbers: K{NNNN} — zero-padded to 4 digits, widening automatically
beyond 9999 (K0001, K0002, … K9999, K10000).

CustomerNumberSequence is a single-row counter; the two allocate functions here
are the only code that should mutate it.  Both take a row-level lock, so the
bulk variant exists to let the Wiffzack sync allocate thousands of numbers with
a single lock instead of one per customer.
"""
from django.db import transaction

from core.models import CustomerNumberSequence

CUSTOMER_NUMBER_PREFIX = 'K'
CUSTOMER_NUMBER_DIGITS = 4


def _format_customer_number(value: int) -> str:
    return f'{CUSTOMER_NUMBER_PREFIX}{value:0{CUSTOMER_NUMBER_DIGITS}d}'


def allocate_customer_numbers(count: int) -> list[str]:
    """
    Allocate `count` consecutive customer numbers in one locked bump.

    Returns them in ascending order.  An empty list is returned for count <= 0.
    """
    if count <= 0:
        return []

    with transaction.atomic():
        seq, _ = (
            CustomerNumberSequence.objects
            .select_for_update()
            .get_or_create(pk=1, defaults={'last_value': 0})
        )
        first = seq.last_value + 1
        seq.last_value += count
        seq.save(update_fields=['last_value'])
        last = seq.last_value

    return [_format_customer_number(n) for n in range(first, last + 1)]


def allocate_customer_number() -> str:
    """Allocate the next single customer number."""
    return allocate_customer_numbers(1)[0]
