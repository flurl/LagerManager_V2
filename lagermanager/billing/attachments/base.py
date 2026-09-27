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
    delivery_modes: tuple[str, ...]
    has_delivery_choice: bool
    default_delivery: str
    requires_file: bool
    renderable: bool
    mandatory: bool
    deletable: bool
    editable: bool
    requires_issued_document: bool
    creatable: bool
    help_text: str = ''

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class AttachmentHandler:
    """One attachment kind.  Subclass, set the class attributes, @register."""

    kind: ClassVar[str] = ''
    label: ClassVar[str] = ''
    #: How this kind may travel.  Several modes give the user a choice; a
    #: single mode is fixed (a Datei never merges, a Berichtigungsnote always
    #: does).  default_delivery must be one of them — register() checks.
    delivery_modes: ClassVar[tuple[str, ...]] = (DocumentAttachment.Delivery.SEPARATE,)
    default_delivery: ClassVar[str] = DocumentAttachment.Delivery.SEPARATE
    #: The user uploads a file for this kind.
    requires_file: ClassVar[bool] = False
    #: Has an HTML/PDF preview of its own.
    renderable: ClassVar[bool] = False
    #: Goes out with every email of its document, whether selected or not.
    mandatory: ClassVar[bool] = False
    #: May be deleted.  False is enforced by the API and at the model layer.
    deletable: ClassVar[bool] = True
    #: Title, body and data may change after creation (delivery always may).
    editable: ClassVar[bool] = True
    #: May only be attached once the document is no longer a draft.
    requires_issued_document: ClassVar[bool] = False
    #: May be created through the API.  False for kinds the system maintains
    #: itself (the Zahlungsübersicht follows the invoice's payments).
    creatable: ClassVar[bool] = True
    #: Where the merged pages go among the document's other merged
    #: attachments: ascending, ties broken by position.  Lets a kind claim the
    #: pages right after the document regardless of when it was created.
    merge_order: ClassVar[int] = 100
    help_text: ClassVar[str] = ''

    @property
    def supports_merge(self) -> bool:
        """May be appended to the document PDF (possibly as its only option)."""
        return DocumentAttachment.Delivery.MERGE in self.delivery_modes

    @property
    def has_delivery_choice(self) -> bool:
        """The user picks the delivery mode — only with more than one mode."""
        return len(self.delivery_modes) > 1

    def info(self) -> KindInfo:
        return KindInfo(
            kind=self.kind,
            label=self.label,
            supports_merge=self.supports_merge,
            delivery_modes=self.delivery_modes,
            has_delivery_choice=self.has_delivery_choice,
            default_delivery=self.default_delivery,
            requires_file=self.requires_file,
            renderable=self.renderable,
            mandatory=self.mandatory,
            deletable=self.deletable,
            editable=self.editable,
            requires_issued_document=self.requires_issued_document,
            creatable=self.creatable,
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
        """The delivery mode actually used — only ever one the kind allows.

        Defence in depth: a stored mode the kind does not allow (a Datei set to
        merge, a Berichtigungsnote set to separate) is replaced by the kind's
        default rather than trusted.  The serializer already prevents such rows;
        this covers any that were written some other way.
        """
        if attachment.delivery in self.delivery_modes:
            return attachment.delivery
        return self.default_delivery

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
