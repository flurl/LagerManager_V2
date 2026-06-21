"""
Document rendering service for billing documents.

render_document_html(doc)  → full HTML string (browser preview via iframe)
render_document_pdf(doc)   → PDF bytes (download endpoint)

WeasyPrint is used for HTML→PDF conversion.  The same Django template is used for
both the browser preview and the PDF, ensuring pixel-consistent output.

WeasyPrint is imported lazily inside render_document_pdf so the rest of the app
works even if the system libraries are not yet installed (e.g. before rebuilding
the Docker image).  The /preview/ endpoint works without WeasyPrint; only /pdf/
requires it.
"""
from constance import config
from django.template.loader import render_to_string

from billing.models import Invoice, Offer, Reminder

DocType = Offer | Invoice | Reminder


def _build_context(doc: DocType) -> dict[str, object]:
    """Build the template context common to all document types."""
    return {
        'doc': doc,
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
