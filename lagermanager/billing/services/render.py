"""
Document rendering service for billing documents.

render_document_html(doc)  → full HTML string (browser preview via iframe)
render_document_pdf(doc)   → PDF bytes (download endpoint)
build_email_defaults(doc)  → {recipient, subject, body} prefilled from Constance templates

WeasyPrint is used for HTML→PDF conversion.  The same Django template is used for
both the browser preview and the PDF, ensuring pixel-consistent output.

WeasyPrint is imported lazily inside render_document_pdf so the rest of the app
works even if the system libraries are not yet installed (e.g. before rebuilding
the Docker image).  The /preview/ endpoint works without WeasyPrint; only /pdf/
requires it.
"""
import base64
import mimetypes
from pathlib import Path

from constance import config
from django.conf import settings
from django.template.loader import render_to_string

from billing.models import Invoice, Offer, Reminder

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
    }


def _template_name(doc: DocType) -> str:
    if isinstance(doc, Offer):
        return 'billing/offer.html'
    if isinstance(doc, Invoice):
        return 'billing/invoice.html'
    if isinstance(doc, Reminder):
        return 'billing/reminder.html'
    raise TypeError(f'Unknown document type: {type(doc)}')


def render_document_html(doc: DocType) -> str:
    """Render the document to a full HTML string for browser preview."""
    ctx = _build_context(doc)
    # Prefetch lines to avoid N+1 in templates
    if isinstance(doc, (Offer, Invoice)):
        doc.lines.select_related(
            'tax_rate', 'billing_article').all()  # force evaluation
    return render_to_string(_template_name(doc), ctx)


def build_email_defaults(doc: DocType) -> dict[str, str]:
    """Return prefilled {recipient, subject, body} for the send-email dialog.

    Subject and body come from Constance config templates and have placeholders
    ({number}, {company}, {recipient_name}) replaced with the actual document values.
    recipient is the email address from the document's associated Address (may be empty).
    """
    company: str = getattr(config, 'COMPANY_NAME', '')

    if isinstance(doc, Offer):
        subject_tpl: str = getattr(config, 'EMAIL_SUBJECT_OFFER', 'Ihr Angebot {number}')
        body_tpl: str = getattr(config, 'EMAIL_BODY_OFFER', '')
        number: str = doc.number or ''
        recipient_email: str = doc.address.email or ''
        recipient_name: str = doc.address.display_name or ''
    elif isinstance(doc, Invoice):
        subject_tpl = getattr(config, 'EMAIL_SUBJECT_INVOICE', 'Ihre Rechnung {number}')
        body_tpl = getattr(config, 'EMAIL_BODY_INVOICE', '')
        number = doc.number or ''
        recipient_email = doc.address.email or ''
        recipient_name = doc.address.display_name or ''
    elif isinstance(doc, Reminder):
        subject_tpl = getattr(config, 'EMAIL_SUBJECT_REMINDER', 'Zahlungserinnerung {number}')
        body_tpl = getattr(config, 'EMAIL_BODY_REMINDER', '')
        number = doc.number or ''
        recipient_email = doc.invoice.address.email or ''
        recipient_name = doc.invoice.address.display_name or ''
    else:
        raise TypeError(f'Unknown document type: {type(doc)}')

    fmt = _SafeFormatMap(number=number, company=company, recipient_name=recipient_name)
    return {
        'recipient': recipient_email,
        'subject': subject_tpl.format_map(fmt),
        'body': body_tpl.format_map(fmt),
    }


def render_document_pdf(doc: DocType) -> bytes:
    """Render the document to PDF bytes via WeasyPrint."""
    try:
        import weasyprint  # noqa: PLC0415 — lazy import (system libs may not be present)
    except ImportError as exc:
        raise RuntimeError(
            'WeasyPrint is not installed. Rebuild the Docker image to enable PDF export.'
        ) from exc
    html = render_document_html(doc)
    return weasyprint.HTML(string=html).write_pdf()  # type: ignore[no-any-return]
