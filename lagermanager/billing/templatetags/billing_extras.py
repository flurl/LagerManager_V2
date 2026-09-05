from decimal import Decimal

from django import template
from django.template.defaultfilters import floatformat
from django.utils.formats import get_format
from django.utils.html import conditional_escape
from django.utils.safestring import SafeString, mark_safe

register = template.Library()


@register.filter
def trim_zeros(value: Decimal | float | str | None, arg: int | str = -4) -> str:
    """Format a number like ``floatformat`` but drop trailing decimal zeros.

    ``19.5000`` renders as ``19,5``, ``8.1250`` as ``8,125`` and ``3.0000``
    as ``3``.
    """
    text: str = floatformat(value, arg)
    if not text:
        return text
    separator: str = get_format('DECIMAL_SEPARATOR')
    if separator not in text:
        # No decimal part (or localisation turned off) — nothing to trim.
        separator = '.' if '.' in text and ',' not in text else separator
    if separator in text:
        return text.rstrip('0').rstrip(separator)
    return text


@register.filter(is_safe=True, needs_autoescape=True)
def render_description(value: str | None, autoescape: bool = True) -> SafeString:
    """Split a description on newlines; render continuation lines at 75% size."""
    esc = conditional_escape if autoescape else str
    if not value:
        return mark_safe('')
    lines = str(value).split('\n')
    first = esc(lines[0])
    rest = [esc(line) for line in lines[1:]]
    if not rest:
        return mark_safe(first)
    continuation = '<br>'.join(
        f'<span class="description-continuation">{line}</span>' for line in rest
    )
    return mark_safe(f'{first}<br>{continuation}')
