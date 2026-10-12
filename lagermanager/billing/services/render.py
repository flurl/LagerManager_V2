"""
Document rendering service for billing documents.

render_document_html(doc)  → full HTML string (browser preview via iframe)
render_document_pdf(doc)   → PDF bytes (download endpoint)
render_attachment_html(attachment, template)
                           → one attachment rendered in the document's layout
render_html_to_pdf(html)   → PDF bytes for any already-rendered HTML
build_email_defaults(doc)  → {recipient, subject, body} prefilled from Constance templates

WeasyPrint is used for HTML→PDF conversion.  The same Django template is used for
both the browser preview and the PDF, ensuring pixel-consistent output.

WeasyPrint is imported lazily inside render_document_pdf so the rest of the app
works even if the system libraries are not yet installed (e.g. before rebuilding
the Docker image).  The /preview/ endpoint works without WeasyPrint; only /pdf/
requires it.
"""
import base64
import datetime
import mimetypes
from pathlib import Path
from typing import cast

from constance import config
from core.models import Address, Customer
from django.conf import settings
from django.template.loader import render_to_string

from billing.models import DocumentAttachment, Invoice, Offer, Reminder

DocType = Offer | Invoice | Reminder


def _logo_data_uri() -> str:
    logo_path: str = getattr(config, 'COMPANY_LOGO', '')
    if not logo_path:
        return ''
    file_path = Path(settings.MEDIA_ROOT) / logo_path
    if not file_path.is_file():
        return ''
    mime = mimetypes.guess_type(str(file_path))[0] or 'image/png'
    data = base64.b64encode(file_path.read_bytes()).decode('ascii')
    return f'data:{mime};base64,{data}'


class _SafeFormatMap(dict):  # type: ignore[type-arg]
    """dict subclass that returns '{key}' unchanged for missing keys."""

    def __missing__(self, key: str) -> str:
        return '{' + key + '}'


def _build_context(doc: DocType) -> dict[str, object]:
    """Build the template context common to all document types."""
    return {
        'doc': doc,
        'company_logo_data_uri': _logo_data_uri(),
        # Company / issuer data from Constance
        'company_name': getattr(config, 'COMPANY_NAME', ''),
        'company_address': getattr(config, 'COMPANY_ADDRESS', ''),
        'company_zip': getattr(config, 'COMPANY_ZIP', ''),
        'company_city': getattr(config, 'COMPANY_CITY', ''),
        'company_uid': getattr(config, 'COMPANY_UID', ''),
        'company_iban': getattr(config, 'COMPANY_IBAN', ''),
        'company_bic': getattr(config, 'COMPANY_BIC', ''),
        'company_bank': getattr(config, 'COMPANY_BANK', ''),
        'company_email': getattr(config, 'COMPANY_EMAIL', ''),
        'company_phone': getattr(config, 'COMPANY_PHONE', ''),
        'invoice_footer_text': getattr(config, 'INVOICE_FOOTER_TEXT', ''),
        'reminder_max_level': getattr(config, 'REMINDER_MAX_LEVEL', 3),
        # Set only in preview environments: stamps a VORSCHAU watermark on every page.
        'preview_branch': settings.PREVIEW_BRANCH,
    }


def _template_name(doc: DocType) -> str:
    if isinstance(doc, Offer):
        return 'billing/offer.html'
    if isinstance(doc, Invoice):
        return 'billing/invoice.html'
    if isinstance(doc, Reminder):
        return 'billing/reminder.html'
    raise TypeError(f'Unknown document type: {type(doc)}')


def _doc_type_label(doc: DocType) -> str:
    """What the document calls itself, for cross-references on attachments."""
    if isinstance(doc, Offer):
        return 'Angebot'
    if isinstance(doc, Invoice):
        return 'Stornorechnung' if doc.is_reversal else 'Rechnung'
    if isinstance(doc, Reminder):
        return 'Mahnung'
    raise TypeError(f'Unknown document type: {type(doc)}')


def _document_date(doc: DocType) -> datetime.date | None:
    """The date printed on the document itself (None for an unissued draft)."""
    if isinstance(doc, (Offer, Invoice)):
        return doc.document_date
    if isinstance(doc, Reminder):
        return doc.reminder_date
    raise TypeError(f'Unknown document type: {type(doc)}')


def document_address(doc: DocType) -> tuple[Address, Customer | None]:
    """The address a document is sent to, and the customer behind it.

    A reminder carries no address of its own — it duns the invoice's.
    """
    if isinstance(doc, (Offer, Invoice)):
        return doc.address, doc.customer
    if isinstance(doc, Reminder):
        return doc.invoice.address, doc.invoice.customer
    raise TypeError(f'Unknown document type: {type(doc)}')


def recipient_block(doc: DocType) -> str:
    """The recipient block as printed on the document.

    Mirrors base_document.html: the snapshot taken at issue time wins, the live
    address fills in for drafts.  Resolved in Python rather than in the
    template so it also works for reminders, which have neither field.
    """
    snapshot: str = getattr(doc, 'recipient_text', '') or ''
    if snapshot:
        return snapshot
    address, _customer = document_address(doc)
    return address.format_address_block()


def render_document_html(doc: DocType) -> str:
    """Render the document to a full HTML string for browser preview."""
    ctx = _build_context(doc)
    # Prefetch lines to avoid N+1 in templates
    if isinstance(doc, (Offer, Invoice)):
        doc.lines.select_related(
            'tax_rate', 'billing_article').all()  # force evaluation
    return render_to_string(_template_name(doc), ctx)


def resolve_recipient_email(address: Address, customer: Customer | None) -> str:
    """Where a document should be sent.

    The address the document is addressed to wins: it is the one the user picked
    for this document, and a customer may well have a separate delivery address
    with its own contact.  Only when that address carries no e-mail does the
    customer's billing e-mail fill the gap (their own, else their default
    address's).  Address.email is a legacy nullable column, so None and '' both
    count as missing.  Returns '' when nothing is on file — the send dialog then
    asks for an address instead of sending somewhere wrong.
    """
    return (address.email or '') or (customer.billing_email if customer else '')


def build_email_defaults(doc: DocType) -> dict[str, str]:
    """Return prefilled {recipient, subject, body} for the send-email dialog.

    Subject and body come from Constance config templates and have placeholders
    ({number}, {company}, {recipient_name}) replaced with the actual document values.
    recipient is resolved by resolve_recipient_email() and may be empty.
    """
    company: str = getattr(config, 'COMPANY_NAME', '')
    address: Address
    customer: Customer | None
    address, customer = document_address(doc)

    if isinstance(doc, Offer):
        subject_tpl: str = getattr(config, 'EMAIL_SUBJECT_OFFER', 'Ihr Angebot {number}')
        body_tpl: str = getattr(config, 'EMAIL_BODY_OFFER', '')
    elif isinstance(doc, Invoice):
        subject_tpl = getattr(config, 'EMAIL_SUBJECT_INVOICE', 'Ihre Rechnung {number}')
        body_tpl = getattr(config, 'EMAIL_BODY_INVOICE', '')
    elif isinstance(doc, Reminder):
        subject_tpl = getattr(config, 'EMAIL_SUBJECT_REMINDER', 'Zahlungserinnerung {number}')
        body_tpl = getattr(config, 'EMAIL_BODY_REMINDER', '')
    else:
        raise TypeError(f'Unknown document type: {type(doc)}')

    fmt = _SafeFormatMap(
        number=doc.number or '',
        company=company,
        recipient_name=address.display_name,
    )
    return {
        'recipient': resolve_recipient_email(address, customer),
        'subject': subject_tpl.format_map(fmt),
        'body': body_tpl.format_map(fmt),
    }


def render_attachment_html(
    attachment: DocumentAttachment,
    template: str,
    extra: dict[str, object] | None = None,
) -> str:
    """Render one attachment as a standalone page in the document's layout.

    The parent document supplies logo, company block, recipient, number and
    date, so the page is recognisably part of the same document.  ``extra`` is
    for context only one kind needs (e.g. a Berichtigungsnote's own number).
    """
    # The GenericForeignKey is typed as Any|None; an attachment always has a
    # document, the FK is not nullable.
    doc: DocType = cast('DocType', attachment.document)
    ctx = _build_context(doc)
    ctx.update({
        'attachment': attachment,
        'recipient_text': recipient_block(doc),
        'doc_label': _doc_type_label(doc),
        'doc_number': doc.number or '',
        'doc_date': _document_date(doc),
    })
    ctx.update(extra or {})
    return render_to_string(template, ctx)


def render_html_to_pdf(html: str) -> bytes:
    """Convert rendered HTML to PDF bytes via WeasyPrint."""
    try:
        import weasyprint  # noqa: PLC0415 — lazy import (system libs may not be present)
    except ImportError as exc:
        raise RuntimeError(
            'WeasyPrint is not installed. Rebuild the Docker image to enable PDF export.'
        ) from exc
    return weasyprint.HTML(string=html).write_pdf()  # type: ignore[no-any-return]


def render_document_pdf(doc: DocType) -> bytes:
    """Render the document to PDF bytes via WeasyPrint."""
    return render_html_to_pdf(render_document_html(doc))
