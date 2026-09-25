"""The attachment kinds that ship today.

Ergänzung — a note (title + text) rendered into the corporate document layout.
             Appended to the document PDF by default, or sent as its own PDF.
Datei      — an uploaded file with a short description.  Always its own file:
             merging arbitrary uploads into the document is out of scope.
"""
from __future__ import annotations

import mimetypes
import os
from typing import Any

from django.core.files.uploadedfile import UploadedFile
from emails.services.email import AttachmentSpec
from rest_framework import serializers

from billing.models import MAX_ATTACHMENT_BYTES, DocumentAttachment
from billing.services.render import render_attachment_html, render_html_to_pdf

from .base import AttachmentHandler
from .registry import register

SUPPLEMENT_TEMPLATE = 'billing/supplement.html'


def _document_slug(attachment: DocumentAttachment) -> str:
    """The document's number, or a draft marker — safe for use in a filename."""
    document: Any = attachment.document
    number: str = getattr(document, 'number', '') or ''
    if not number:
        return f'entwurf-{getattr(document, "pk", attachment.object_id)}'
    return ''.join(c if c.isalnum() or c in '-_' else '-' for c in number)


@register
class SupplementHandler(AttachmentHandler):
    """Ergänzung — free text rendered as extra document pages."""

    kind = 'supplement'
    label = 'Ergänzung'
    supports_merge = True
    default_delivery = DocumentAttachment.Delivery.MERGE
    requires_file = False
    renderable = True
    help_text = 'Freier Text, der im Layout des Dokuments gesetzt wird.'

    def validate(
        self, attrs: dict[str, Any], instance: DocumentAttachment | None
    ) -> dict[str, Any]:
        if attrs.get('file'):
            raise serializers.ValidationError(
                {'file': 'Für eine Ergänzung kann keine Datei hochgeladen werden.'})

        title: str = attrs.get('title', instance.title if instance else '') or ''
        body: str = attrs.get('body', instance.body if instance else '') or ''
        if not title.strip() and not body.strip():
            raise serializers.ValidationError(
                {'body': 'Eine Ergänzung braucht einen Titel oder einen Text.'})
        return attrs

    def email_filename(self, attachment: DocumentAttachment) -> str:
        return f'ergaenzung_{_document_slug(attachment)}_{attachment.position}.pdf'

    def render_html(self, attachment: DocumentAttachment) -> str:
        return render_attachment_html(attachment, SUPPLEMENT_TEMPLATE)

    def render_pdf(self, attachment: DocumentAttachment) -> bytes:
        return render_html_to_pdf(self.render_html(attachment))

    def email_attachments(self, attachment: DocumentAttachment) -> list[AttachmentSpec]:
        return [(
            self.email_filename(attachment),
            self.render_pdf(attachment),
            'application/pdf',
        )]


@register
class FileHandler(AttachmentHandler):
    """Datei — whatever the user uploads, sent unchanged."""

    kind = 'file'
    label = 'Datei'
    supports_merge = False
    default_delivery = DocumentAttachment.Delivery.SEPARATE
    requires_file = True
    renderable = False
    help_text = 'Hochgeladene Datei, die als eigener Anhang mitgeschickt wird.'

    def validate(
        self, attrs: dict[str, Any], instance: DocumentAttachment | None
    ) -> dict[str, Any]:
        uploaded: UploadedFile[Any] | None = attrs.get('file')

        if uploaded is None and instance is None:
            raise serializers.ValidationError({'file': 'Bitte eine Datei auswählen.'})

        if uploaded is not None:
            if uploaded.size and uploaded.size > MAX_ATTACHMENT_BYTES:
                limit_mb = MAX_ATTACHMENT_BYTES // (1024 * 1024)
                raise serializers.ValidationError(
                    {'file': f'Die Datei ist zu groß (maximal {limit_mb} MB).'})
            name: str = os.path.basename(uploaded.name or 'anhang')
            attrs['original_filename'] = name[:255]
            attrs['mime_type'] = (
                uploaded.content_type
                or mimetypes.guess_type(name)[0]
                or 'application/octet-stream'
            )[:100]
            attrs['size_bytes'] = uploaded.size or 0

        # An uploaded file is never merged into the document PDF.
        attrs['delivery'] = DocumentAttachment.Delivery.SEPARATE
        return attrs

    def email_filename(self, attachment: DocumentAttachment) -> str:
        if attachment.original_filename:
            return attachment.original_filename
        return os.path.basename(attachment.file.name or '') or 'anhang'

    def email_attachments(self, attachment: DocumentAttachment) -> list[AttachmentSpec]:
        if not attachment.file:
            raise FileNotFoundError(self.display_title(attachment))
        attachment.file.open('rb')
        try:
            data: bytes = attachment.file.read()
        finally:
            attachment.file.close()
        mime: str = (
            attachment.mime_type
            or mimetypes.guess_type(self.email_filename(attachment))[0]
            or 'application/octet-stream'
        )
        return [(self.email_filename(attachment), data, mime)]
