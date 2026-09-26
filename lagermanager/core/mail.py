"""Mail backend for preview environments.

A preview (see scripts/preview.sh) runs a feature branch on a copy of the
production database, so every customer, invoice and reminder in it is real.
PreviewRedirectEmailBackend makes sure nothing sent from there reaches those
customers: each message goes to PREVIEW_EMAIL_REDIRECT_TO instead (by default
the sender address, i.e. mail to self), with the branch in the subject and the
original recipients at the top of the body.

The actual delivery is delegated to PREVIEW_EMAIL_INNER_BACKEND, the backend
production would have used.
"""
from __future__ import annotations

import copy
from collections.abc import Sequence
from typing import Any

from django.conf import settings
from django.core.mail import EmailMessage, get_connection
from django.core.mail.backends.base import BaseEmailBackend


def redirect_message(message: EmailMessage) -> EmailMessage:
    """Return a copy of *message* addressed only to PREVIEW_EMAIL_REDIRECT_TO."""
    original: list[str] = [*message.to, *message.cc, *message.bcc]
    branch: str = settings.PREVIEW_BRANCH

    redirected: EmailMessage = copy.copy(message)
    redirected.to = [settings.PREVIEW_EMAIL_REDIRECT_TO]
    redirected.cc = []
    redirected.bcc = []
    redirected.subject = f'[VORSCHAU {branch}] {message.subject}'
    redirected.body = (
        f'--- Vorschau-Umgebung (Branch {branch}) ---\n'
        f'Ursprüngliche Empfänger: {", ".join(original)}\n\n'
        f'{message.body}'
    )
    redirected.extra_headers = {
        **message.extra_headers,
        'X-Original-Recipients': ', '.join(original),
    }
    return redirected


class PreviewRedirectEmailBackend(BaseEmailBackend):
    """Redirects every message to one address, then delivers via the inner backend."""

    def __init__(self, fail_silently: bool = False, **kwargs: Any) -> None:
        super().__init__(fail_silently=fail_silently)
        self._inner: BaseEmailBackend = get_connection(
            settings.PREVIEW_EMAIL_INNER_BACKEND, fail_silently=fail_silently, **kwargs
        )

    def open(self) -> bool | None:
        return self._inner.open()

    def close(self) -> None:
        self._inner.close()

    def send_messages(self, email_messages: Sequence[EmailMessage]) -> int:
        if not email_messages:
            return 0
        return self._inner.send_messages([redirect_message(m) for m in email_messages])
