"""
General-purpose outgoing email log.

EmailLog records every email sent by the application, regardless of trigger.
EmailAttachment stores the actual file sent (filesystem via FileField) so the
exact sent attachment is preserved even if the source document changes later.
"""
import os

from django.contrib.auth.models import User
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models


def email_attachment_upload_path(instance: "EmailAttachment", filename: str) -> str:
    """Store under email_attachments/<email_log_pk>/<filename>."""
    return os.path.join('email_attachments', str(instance.email_id), filename)


class EmailLog(models.Model):
    """Records a single outbound email attempt (sent or failed)."""

    class Status(models.TextChoices):
        SENT = 'sent', 'Versendet'
        FAILED = 'failed', 'Fehlgeschlagen'

    from_email = models.CharField(max_length=255)
    recipient = models.CharField(max_length=255)
    cc = models.CharField(max_length=255, blank=True)
    subject = models.CharField(max_length=500)
    body = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices)
    error_message = models.TextField(blank=True)

    sent_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='sent_emails',
    )
    sent_at = models.DateTimeField(auto_now_add=True)

    # Optional link to the document / object that triggered this email.
    # Using GenericForeignKey keeps this model decoupled from billing.
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True, blank=True,
    )
    object_id = models.CharField(max_length=64, null=True, blank=True)
    related_object = GenericForeignKey('content_type', 'object_id')

    class Meta:
        ordering = ['-sent_at']
        verbose_name = 'E-Mail'
        verbose_name_plural = 'E-Mails'

    def __str__(self) -> str:
        return f'{self.sent_at:%Y-%m-%d %H:%M} → {self.recipient}: {self.subject[:60]}'


class EmailAttachment(models.Model):
    """A file attached to a sent email, stored on the filesystem."""

    email = models.ForeignKey(
        EmailLog,
        on_delete=models.CASCADE,
        related_name='attachments',
    )
    file = models.FileField(upload_to=email_attachment_upload_path)
    original_filename = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=100, blank=True)

    class Meta:
        verbose_name = 'E-Mail-Anhang'
        verbose_name_plural = 'E-Mail-Anhänge'

    def __str__(self) -> str:
        return self.original_filename
