"""Registry of attachment kinds.

The registry — not the database — is the source of truth for which kinds exist.
DocumentAttachment.kind is a plain CharField without choices, so a kind that is
no longer registered leaves its rows readable; the serializer simply refuses to
create new ones.
"""
from __future__ import annotations

from django.core.exceptions import ImproperlyConfigured

from .base import AttachmentHandler, KindInfo


class UnknownAttachmentKind(LookupError):
    """Raised for a kind that is not registered."""


_HANDLERS: dict[str, AttachmentHandler] = {}


def register(handler_class: type[AttachmentHandler]) -> type[AttachmentHandler]:
    """Class decorator registering one attachment kind."""
    kind = handler_class.kind
    if not kind:
        raise ImproperlyConfigured(
            f'{handler_class.__name__} must define a non-empty kind.')
    if kind in _HANDLERS:
        raise ImproperlyConfigured(f'Duplicate attachment kind: {kind!r}')
    _HANDLERS[kind] = handler_class()
    return handler_class


def get_handler(kind: str) -> AttachmentHandler:
    try:
        return _HANDLERS[kind]
    except KeyError as exc:
        raise UnknownAttachmentKind(kind) from exc


def all_handlers() -> list[AttachmentHandler]:
    """Every registered handler, in registration order."""
    return list(_HANDLERS.values())


def known_kinds() -> list[str]:
    return list(_HANDLERS)


def kind_infos() -> list[KindInfo]:
    return [handler.info() for handler in _HANDLERS.values()]
