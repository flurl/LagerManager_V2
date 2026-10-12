"""The attachment kinds that ship today.

Ergänzung         — a note (title + text) rendered into the corporate document
                    layout.  Appended to the document PDF by default, or sent as
                    its own PDF.
Berichtigungsnote — like an Ergänzung, but a binding correction of an issued
                    document: always sent, never deleted, never edited.
Zahlungsübersicht — the invoice's payments, reminder fees and open amount,
                    generated once it has payments or an issued reminder: always sent, always right after the invoice,
                    maintained by the system alone.
Datei             — an uploaded file with a short description.  Always its own
                    file: merging arbitrary uploads into the document is out of
                    scope.
"""
from __future__ import annotations

import mimetypes
import os
from decimal import Decimal
from typing import Any, ClassVar, cast

from django.core.files.uploadedfile import UploadedFile
from django.utils import timezone
from emails.services.email import AttachmentSpec
from rest_framework import serializers

from billing.models import MAX_ATTACHMENT_BYTES, DocumentAttachment, Invoice, Reminder
from billing.services.payment_supplement import PAYMENTS_KIND
from billing.services.render import render_attachment_html, render_html_to_pdf

from .base import AttachmentHandler
from .registry import register

SUPPLEMENT_TEMPLATE = 'billing/supplement.html'
CORRECTION_TEMPLATE = 'billing/correction_note.html'
PAYMENTS_TEMPLATE = 'billing/payment_supplement.html'


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
    # Annotated because CorrectionNoteHandler subclasses this: unannotated, mypy
    # would pin the exact two-element shape and reject its one-element tuple.
    delivery_modes: ClassVar[tuple[str, ...]] = (
        DocumentAttachment.Delivery.MERGE, DocumentAttachment.Delivery.SEPARATE)
    default_delivery = DocumentAttachment.Delivery.MERGE
    requires_file = False
    renderable = True
    help_text = 'Freier Text, der im Layout des Dokuments gesetzt wird.'

    def validate(
        self, attrs: dict[str, Any], instance: DocumentAttachment | None
    ) -> dict[str, Any]:
        # Worded with self.label because CorrectionNoteHandler reuses this.
        if attrs.get('file'):
            raise serializers.ValidationError(
                {'file': f'Für Anhänge vom Typ „{self.label}" kann keine Datei '
                         f'hochgeladen werden.'})

        title: str = attrs.get('title', instance.title if instance else '') or ''
        body: str = attrs.get('body', instance.body if instance else '') or ''
        if not title.strip() and not body.strip():
            raise serializers.ValidationError(
                {'body': f'Anhänge vom Typ „{self.label}" brauchen einen Titel '
                         f'oder einen Text.'})
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


def _correction_number(attachment: DocumentAttachment) -> int:
    """This note's running number among its document's Berichtigungsnoten.

    Counted by creation order.  That is only stable because these notes can
    never be deleted — a gap would renumber every later note.
    """
    return DocumentAttachment.objects.filter(
        content_type_id=attachment.content_type_id,
        object_id=attachment.object_id,
        kind=attachment.kind,
        pk__lte=attachment.pk,
    ).count()


@register
class CorrectionNoteHandler(SupplementHandler):
    """Berichtigungsnote — a binding correction of an issued document.

    Written like an Ergänzung, and it inherits its validation and rendering.
    What differs is only declared, not coded: it goes out with every email of
    its document, always merged into the document PDF, can never be deleted,
    and its text never changes.  A further correction is a further
    Berichtigungsnote, numbered per document.
    """

    kind = 'correction'
    label = 'Berichtigungsnote'
    # Always extra pages of the corrected document itself — never a file the
    # recipient could open, forward or file separately from it.
    delivery_modes = (DocumentAttachment.Delivery.MERGE,)
    default_delivery = DocumentAttachment.Delivery.MERGE
    requires_file = False
    renderable = True
    mandatory = True
    deletable = False
    editable = False
    requires_issued_document = True
    # Shown in the dialog before creating one, since the step is irreversible.
    help_text = ('Korrektur eines ausgestellten Dokuments. Wird bei jedem Versand '
                 'als zusätzliche Seite an das Dokument-PDF angehängt und kann '
                 'nach dem Anlegen weder geändert noch gelöscht werden – eine '
                 'weitere Korrektur ist eine weitere Berichtigungsnote.')

    def email_filename(self, attachment: DocumentAttachment) -> str:
        return (f'berichtigungsnote_{_document_slug(attachment)}_'
                f'{_correction_number(attachment)}.pdf')

    def render_html(self, attachment: DocumentAttachment) -> str:
        return render_attachment_html(
            attachment, CORRECTION_TEMPLATE,
            {'correction_number': _correction_number(attachment)})


@register
class PaymentSupplementHandler(AttachmentHandler):
    """Zahlungsübersicht — what was paid on an invoice and what is still open.

    Created, kept and removed by services/payment_supplement.py as payments and
    reminders come and go; nobody else may create, edit or delete one.  It carries no content of
    its own: every rendering reads the invoice's current payments, so whatever
    goes out is the state at the time of sending.
    """

    kind = PAYMENTS_KIND
    label = 'Zahlungsübersicht'
    delivery_modes = (DocumentAttachment.Delivery.MERGE,)
    default_delivery = DocumentAttachment.Delivery.MERGE
    requires_file = False
    renderable = True
    mandatory = True
    deletable = False
    editable = False
    requires_issued_document = True
    creatable = False
    # Directly after the invoice pages, before any Berichtigungsnote or Ergänzung.
    merge_order = 0
    help_text = ('Wird aus den Zahlungen und Mahnungen der Rechnung erzeugt und bei '
                 'jedem Versand direkt nach der Rechnung angehängt.')

    def validate(
        self, attrs: dict[str, Any], instance: DocumentAttachment | None
    ) -> dict[str, Any]:
        # The serializer already refuses to create or edit one; this is the
        # handler's own guard should that ever be bypassed.
        if instance is None:
            raise serializers.ValidationError(
                f'Die {self.label} wird automatisch aus Zahlungen und Mahnungen '
                f'erzeugt.')
        return attrs

    def display_title(self, attachment: DocumentAttachment) -> str:
        return self.label

    def email_filename(self, attachment: DocumentAttachment) -> str:
        return f'zahlungsuebersicht_{_document_slug(attachment)}.pdf'

    def render_html(self, attachment: DocumentAttachment) -> str:
        # Typed Any|None by the GenericForeignKey; only invoices get this kind.
        invoice: Invoice = cast('Invoice', attachment.document)
        open_amount: Decimal = invoice.open_amount
        return render_attachment_html(attachment, PAYMENTS_TEMPLATE, {
            'invoice': invoice,
            'reminders_with_fee': [
                reminder for reminder in invoice.reminders.order_by('level', 'pk')
                if reminder.status != Reminder.Status.DRAFT and reminder.fee
            ],
            'payments': list(invoice.payments.all()),
            'open_amount': max(open_amount, Decimal('0.00')),
            'credit': max(-open_amount, Decimal('0.00')),
            'as_of': timezone.localdate(),
        })

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
    delivery_modes = (DocumentAttachment.Delivery.SEPARATE,)
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

        # Never merged into the document PDF: delivery_modes says so, and the
        # serializer enforces it for every kind alike.
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
