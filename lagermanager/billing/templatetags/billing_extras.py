from django import template
from django.utils.html import conditional_escape
from django.utils.safestring import SafeString, mark_safe

register = template.Library()


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
