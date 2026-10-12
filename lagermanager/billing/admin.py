from django.contrib import admin
from django.http import HttpRequest

from .attachments import UnknownAttachmentKind, get_handler
from .models import (
    BillingArticle,
    ContinuousNumberSequence,
    CustomerLedgerEntry,
    DocumentAttachment,
    Invoice,
    InvoiceLine,
    InvoiceTemplate,
    InvoiceTemplateLine,
    NumberSequence,
    Offer,
    OfferLine,
    Payment,
    Reminder,
)

admin.site.register(BillingArticle)
admin.site.register(NumberSequence)
admin.site.register(ContinuousNumberSequence)
admin.site.register(Offer)
admin.site.register(OfferLine)
admin.site.register(Invoice)
admin.site.register(InvoiceLine)
admin.site.register(InvoiceTemplate)
admin.site.register(InvoiceTemplateLine)
admin.site.register(Reminder)
admin.site.register(Payment)
admin.site.register(CustomerLedgerEntry)


@admin.register(DocumentAttachment)
# Unparameterised like the other admins here: ModelAdmin is generic only in
# django-stubs, not at runtime, and django-stubs-ext is not installed.
class DocumentAttachmentAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    def has_delete_permission(
        self, request: HttpRequest, obj: DocumentAttachment | None = None
    ) -> bool:
        # Hide the button for kinds that may never be deleted; the pre_delete
        # signal would refuse it anyway, but as an error page rather than a
        # missing button.
        if obj is not None:
            try:
                if not get_handler(obj.kind).deletable:
                    return False
            except UnknownAttachmentKind:
                return False  # fail closed, like the pre_delete signal
        return super().has_delete_permission(request, obj)
