from django.db.models import ProtectedError
from django.db.models.signals import post_delete, pre_delete
from django.dispatch import receiver

from .attachments.registry import UnknownAttachmentKind, get_handler
from .models import DocumentAttachment


@receiver(pre_delete, sender=DocumentAttachment)
def protect_undeletable_attachments(
    sender: type[DocumentAttachment], instance: DocumentAttachment, **kwargs: object
) -> None:
    """Refuse to delete an attachment whose kind forbids it, by any route.

    The API already answers such a request with a 400.  This covers everything
    that bypasses it — the admin, the shell, and the cascade from deleting the
    document itself — so the rule holds at the model layer, not just in one
    view.  Django sends pre_delete for every object a cascade collects, and
    connecting this receiver also rules out its signal-free fast-delete path.
    """
    try:
        handler = get_handler(instance.kind)
    except UnknownAttachmentKind:
        # Fail closed: the kind's rules can't be checked, and it may be a
        # protected kind whose handler went missing by mistake.  Such a row is
        # resolved deliberately, case by case — by restoring its handler, or by
        # a developer removing it consciously — never by whoever tries first.
        raise ProtectedError(
            f'Anhänge des unbekannten Typs „{instance.kind}" können nicht '
            f'gelöscht werden.',
            {instance},
        ) from None
    if not handler.deletable:
        raise ProtectedError(
            f'Anhänge vom Typ „{handler.label}" können nicht gelöscht werden.',
            {instance},
        )


@receiver(post_delete, sender=DocumentAttachment)
def delete_document_attachment_file(
    sender: type[DocumentAttachment], instance: DocumentAttachment, **kwargs: object
) -> None:
    """Remove the uploaded file from storage when its attachment row goes away.

    Also covers the cascade from deleting a whole document, since Django sends
    post_delete for every collected object.
    """
    if instance.file:
        instance.file.delete(save=False)
