"""Base class and metadata for attachment kinds.

Every attachment kind is one AttachmentHandler subclass.  The handler owns
everything type-specific: how input is validated, how the attachment renders,
and how it leaves the building when the document is emailed.

Adding a kind therefore means adding a handler and registering it — nothing
else.  No migration (DocumentAttachment.kind carries no choices), no API change
(the kinds endpoint is generated from the registry) and no frontend change (the
dialogs and the settings widget read that endpoint).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, ClassVar

from emails.services.email import AttachmentSpec

from billing.models import DocumentAttachment


@dataclass(frozen=True)
class KindInfo:
    """What the frontend needs to know about one kind."""

    kind: str
    label: str
    supports_merge: bool
    default_delivery: str
    requires_file: bool
    renderable: bool
    help_text: str = ''

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class AttachmentHandler:
    """One attachment kind.  Subclass, set the class attributes, @register."""

    kind: ClassVar[str] = ''
    label: ClassVar[str] = ''
    #: May be appended to the document PDF instead of travelling as its own file.
    supports_merge: ClassVar[bool] = False
    default_delivery: ClassVar[str] = DocumentAttachment.Delivery.SEPARATE
    #: The user uploads a file for this kind.
    requires_file: ClassVar[bool] = False
    #: Has an HTML/PDF preview of its own.
    renderable: ClassVar[bool] = False
    help_text: ClassVar[str] = ''

    def info(self) -> KindInfo:
        return KindInfo(
            kind=self.kind,
            label=self.label,
            supports_merge=self.supports_merge,
            default_delivery=self.default_delivery,
            requires_file=self.requires_file,
            renderable=self.renderable,
            help_text=self.help_text,
        )

    # -- write path ---------------------------------------------------------

    def validate(
        self, attrs: dict[str, Any], instance: DocumentAttachment | None
    ) -> dict[str, Any]:
        """Validate and normalise serializer input for this kind.

        Raises rest_framework.serializers.ValidationError on bad input.  May
        add derived values (file metadata, a forced delivery mode) to attrs.
        """
        return attrs

    # -- read / delivery path ----------------------------------------------

    def resolve_delivery(self, attachment: DocumentAttachment) -> str:
        """The delivery mode actually used — merge only where it is supported.

        Defence in depth: a stored 'merge' on a kind that cannot be merged is
        treated as 'separate' rather than trusted.
        """
        if not self.supports_merge:
            return DocumentAttachment.Delivery.SEPARATE
        return attachment.delivery

    def display_title(self, attachment: DocumentAttachment) -> str:
        return attachment.title or attachment.original_filename or self.label

    def email_filename(self, attachment: DocumentAttachment) -> str:
        """Filename this attachment carries in the outgoing email."""
        raise NotImplementedError

    def render_html(self, attachment: DocumentAttachment) -> str:
        """Preview HTML.  Only defined for renderable kinds."""
        raise NotImplementedError

    def render_pdf(self, attachment: DocumentAttachment) -> bytes:
        """PDF bytes — the pages merged into the document, or a standalone PDF."""
        raise NotImplementedError

    def email_attachments(self, attachment: DocumentAttachment) -> list[AttachmentSpec]:
        """Specs for an attachment delivered as its own file."""
        raise NotImplementedError
