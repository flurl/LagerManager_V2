from django.contrib import admin

from .models import (
    BillingArticle,
    Invoice,
    InvoiceLine,
    InvoiceTemplate,
    InvoiceTemplateLine,
    NumberSequence,
    Offer,
    OfferLine,
    Reminder,
)

admin.site.register(BillingArticle)
admin.site.register(NumberSequence)
admin.site.register(Offer)
admin.site.register(OfferLine)
admin.site.register(Invoice)
admin.site.register(InvoiceLine)
admin.site.register(InvoiceTemplate)
admin.site.register(InvoiceTemplateLine)
admin.site.register(Reminder)
