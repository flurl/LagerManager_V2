from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import DocumentAttachment


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
