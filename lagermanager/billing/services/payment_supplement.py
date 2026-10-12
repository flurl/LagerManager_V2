"""The Zahlungsübersicht — the payment list that travels with an invoice.

Once an invoice has payments or an issued reminder, it carries exactly one
attachment of kind ``payments``: a page listing the invoice total, the reminder
fees, every payment and what is still open (or, after an overpayment, the
credit).  Its content is rendered from the live payments at send time, so the
row itself only records *that* the invoice has one; sync_payment_supplement()
keeps that in step with the payments and reminders.

The attachment is maintained here and nowhere else: users can neither create,
edit nor delete it (see PaymentSupplementHandler).
"""
from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar

from django.contrib.contenttypes.models import ContentType

from billing.models import DocumentAttachment, Invoice, Reminder

PAYMENTS_KIND = 'payments'

# Set while this module removes a Zahlungsübersicht whose invoice lost its last
# payment — the one deletion the pre_delete guard in billing/signals.py lets
# through for a kind that is otherwise undeletable.
_system_delete: ContextVar[bool] = ContextVar('payment_supplement_system_delete',
                                              default=False)


def system_delete_in_progress() -> bool:
    return _system_delete.get()


@contextmanager
def _allow_system_delete() -> Generator[None, None, None]:
    token = _system_delete.set(True)
    try:
        yield
    finally:
        _system_delete.reset(token)


def needs_payment_supplement(invoice: Invoice) -> bool:
    """True once the invoice has a payment or a reminder that was issued."""
    return (
        invoice.payments.exists()
        or invoice.reminders.exclude(status=Reminder.Status.DRAFT).exists()
    )


def sync_payment_supplement(invoice: Invoice) -> DocumentAttachment | None:
    """Create, refresh or remove the invoice's Zahlungsübersicht.

    The invoice needs one once it has payments or an issued reminder — a
    reminder's fee raises what is owed, and the invoice page no longer shows it.

    - needed but missing → create it, at position 0 so it also lists first in
      the attachment dialog;
    - needed and present → touch it, so its "changed" date follows the latest
      payment or reminder;
    - no longer needed (the last payment is gone, no reminder issued) → remove
      it: the invoice then goes out without one.

    Returns the attachment, or None when the invoice does not need one.
    """
    content_type = ContentType.objects.get_for_model(Invoice)
    existing: DocumentAttachment | None = DocumentAttachment.objects.filter(
        content_type=content_type, object_id=invoice.pk, kind=PAYMENTS_KIND,
    ).first()

    if not needs_payment_supplement(invoice):
        if existing is not None:
            with _allow_system_delete():
                existing.delete()
        return None

    if existing is not None:
        existing.save(update_fields=['updated_at'])
        return existing

    return DocumentAttachment.objects.create(
        content_type=content_type,
        object_id=invoice.pk,
        kind=PAYMENTS_KIND,
        position=0,
        delivery=DocumentAttachment.Delivery.MERGE,
    )
