"""Turning a document's attachments into the files of an outgoing email.

The selection policy lives here rather than in the view, so the send dialog
stays dumb: the backend decides which attachments are preselected and which
ones are mandatory, and returns plain id lists.
"""
from __future__ import annotations

from typing import Any

from constance import config
from core.services.pdf import merge_pdfs
from django.contrib.contenttypes.models import ContentType
from django.db.models import QuerySet
from emails.services.email import AttachmentSpec

from billing.models import DocumentAttachment

from .registry import UnknownAttachmentKind, all_handlers, get_handler, known_kinds

DEFAULT_KINDS_SETTING = 'EMAIL_DEFAULT_ATTACHMENT_KINDS'


def parse_kind_setting(value: str) -> list[str]:
    """Split a comma-separated Constance value into registered kinds.

    Unknown entries are dropped: /api/config/ does no per-key validation, and a
    typo in the settings page must not break sending mail.
    """
    known = set(known_kinds())
    return [kind for kind in (part.strip() for part in (value or '').split(','))
            if kind in known]


def attachments_for(doc: Any) -> QuerySet[DocumentAttachment]:
    """Every attachment of one document, in display order."""
    content_type = ContentType.objects.get_for_model(doc)
    return DocumentAttachment.objects.filter(
        content_type=content_type, object_id=doc.pk)


def default_selection_ids(doc: Any) -> list[int]:
    """Attachments preselected in the send dialog, per Constance setting."""
    kinds = parse_kind_setting(getattr(config, DEFAULT_KINDS_SETTING, ''))
    if not kinds:
        return []
    return list(
        attachments_for(doc).filter(kind__in=kinds).values_list('pk', flat=True))


def mandatory_selection_ids(doc: Any) -> list[int]:
    """Attachments that must always be sent: every one whose kind is mandatory.

    A property of the kind rather than a setting — a Berichtigungsnote has to
    accompany its document by rule, so it must not be switchable off.
    build_send_attachments() adds these ids to any selection, so a client that
    leaves one out still sends it.
    """
    kinds = [handler.kind for handler in all_handlers() if handler.mandatory]
    if not kinds:
        return []
    return list(
        attachments_for(doc).filter(kind__in=kinds).values_list('pk', flat=True))


def _unique_filename(filename: str, used: set[str]) -> str:
    """Append _2, _3 … so two attachments never share a filename in one mail."""
    if filename not in used:
        used.add(filename)
        return filename
    stem, dot, suffix = filename.rpartition('.')
    if not dot:
        stem, suffix = filename, ''
    counter = 2
    while True:
        candidate = f'{stem}_{counter}{"." + suffix if suffix else ""}'
        if candidate not in used:
            used.add(candidate)
            return candidate
        counter += 1


def build_send_attachments(
    doc: Any,
    attachment_ids: list[int],
    *,
    base_pdf: bytes,
    base_filename: str,
) -> list[AttachmentSpec]:
    """Build the full attachment list for one outgoing document email.

    A selected attachment is appended to the document PDF when its own
    ``delivery`` says ``merge`` and its kind supports merging — the kind only
    grants the option, the attachment decides.  Everything else becomes its own
    file.  The document PDF is always the first spec.

    Raises ValueError (→ 400) for an invalid selection or an unreadable file,
    and RuntimeError (→ 500) when rendering or merging fails.
    """
    wanted: set[int] = set(attachment_ids) | set(mandatory_selection_ids(doc))
    if not wanted:
        return [(base_filename, base_pdf, 'application/pdf')]

    selected = list(attachments_for(doc).filter(pk__in=wanted))
    if len(selected) != len(wanted):
        raise ValueError('Ungültige Anhang-Auswahl.')

    merge_parts: list[bytes] = []
    separate_specs: list[AttachmentSpec] = []

    for attachment in selected:
        try:
            handler = get_handler(attachment.kind)
        except UnknownAttachmentKind:
            raise ValueError(
                f'Unbekannter Anhangstyp „{attachment.kind}".') from None

        if handler.resolve_delivery(attachment) == DocumentAttachment.Delivery.MERGE:
            merge_parts.append(handler.render_pdf(attachment))
            continue

        try:
            separate_specs.extend(handler.email_attachments(attachment))
        except (OSError, ValueError) as exc:
            raise ValueError(
                f'Der Anhang „{handler.display_title(attachment)}" '
                f'konnte nicht gelesen werden: {exc}'
            ) from exc

    document_pdf: bytes = (
        merge_pdfs([base_pdf, *merge_parts]) if merge_parts else base_pdf)

    used: set[str] = {base_filename}
    specs: list[AttachmentSpec] = [(base_filename, document_pdf, 'application/pdf')]
    specs.extend(
        (_unique_filename(filename, used), data, mime)
        for filename, data, mime in separate_specs
    )
    return specs
