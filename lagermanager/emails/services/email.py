"""
Email sending service.

send_document_email() is the single entry-point for sending application emails.
It sends the message via Django's configured mail backend, then always writes an
EmailLog row (status SENT or FAILED) and persists any attachments to the filesystem.
On failure it re-raises the original exception after logging so the caller can
surface an appropriate error response.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.files.base import ContentFile
from django.core.mail import EmailMessage
from django.db import transaction

from emails.models import EmailAttachment, EmailLog

if TYPE_CHECKING:
    from django.contrib.auth.models import User
    from django.db.models import Model

logger = logging.getLogger(__name__)

# A single attachment spec: (filename, bytes, mime_type)
AttachmentSpec = tuple[str, bytes, str]


def send_document_email(
    *,
    subject: str,
    body: str,
    recipient: str,
    cc: str = '',
    sent_by: User | None = None,
    related_object: Model | None = None,
    attachments: list[AttachmentSpec] | None = None,
) -> EmailLog:
    """Send an email and record the attempt in EmailLog.

    Parameters
    ----------
    subject:        Email subject line.
    body:           Plain-text email body.
    recipient:      Primary recipient address.
    cc:             Optional CC address(es), comma-separated.
    sent_by:        The User who triggered the send (stored on the log).
    related_object: Optional Django model instance the email concerns
                    (e.g. an Offer, Invoice or Reminder).
    attachments:    List of (filename, bytes, mime_type) tuples.

    Returns
    -------
    EmailLog instance (status SENT or FAILED).

    Raises
    ------
    Re-raises any exception thrown by the mail backend after recording the
    FAILED log entry.
    """
    from_email: str = settings.DEFAULT_FROM_EMAIL
    cc_list: list[str] = [a.strip() for a in cc.split(',') if a.strip()] if cc else []

    content_type_obj: ContentType | None = None
    object_id: str | None = None
    if related_object is not None:
        content_type_obj = ContentType.objects.get_for_model(related_object)
        object_id = str(related_object.pk)

    try:
        msg = EmailMessage(
            subject=subject,
            body=body,
            from_email=from_email,
            to=[recipient],
            cc=cc_list,
        )
        for filename, data, mime in (attachments or []):
            msg.attach(filename, data, mime)
        msg.send(fail_silently=False)
    except Exception as exc:
        logger.exception(
            'Failed to send email to %s (subject: %r): %s', recipient, subject, exc
        )
        with transaction.atomic():
            log = EmailLog.objects.create(
                from_email=from_email,
                recipient=recipient,
                cc=cc,
                subject=subject,
                body=body,
                status=EmailLog.Status.FAILED,
                error_message=str(exc),
                sent_by=sent_by,
                content_type=content_type_obj,
                object_id=object_id,
            )
        raise

    with transaction.atomic():
        log = EmailLog.objects.create(
            from_email=from_email,
            recipient=recipient,
            cc=cc,
            subject=subject,
            body=body,
            status=EmailLog.Status.SENT,
            sent_by=sent_by,
            content_type=content_type_obj,
            object_id=object_id,
        )
        for filename, data, mime in (attachments or []):
            attachment = EmailAttachment(
                email=log,
                original_filename=filename,
                mime_type=mime,
            )
            # Save the bytes as a file via Django's storage backend
            attachment.file.save(filename, ContentFile(data), save=False)
            attachment.save()

    return log
