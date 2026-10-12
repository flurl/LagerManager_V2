"""Attachment kinds for billing documents.

Importing this package registers every shipping handler, which is why
BillingConfig.ready() imports it.  See base.py for how to add a kind.
"""
from .base import AttachmentHandler, KindInfo
from .registry import (
    UnknownAttachmentKind,
    all_handlers,
    get_handler,
    kind_infos,
    known_kinds,
    register,
)

# Registers SupplementHandler and FileHandler as a side effect of the import.
from . import handlers  # noqa: F401  isort:skip

__all__ = [
    'AttachmentHandler',
    'KindInfo',
    'UnknownAttachmentKind',
    'all_handlers',
    'get_handler',
    'kind_infos',
    'known_kinds',
    'register',
]
