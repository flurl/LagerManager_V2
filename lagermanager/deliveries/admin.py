from django.contrib import admin

from .models import (
    Delivery,
    DeliveryDetail,
    DeliveryUnit,
    Document,
    DocumentType,
    EkModifier,
    Supplier,
    TaxRate,
)

admin.site.register(Supplier)
admin.site.register(TaxRate)
admin.site.register(DeliveryUnit)
admin.site.register(Delivery)
admin.site.register(DeliveryDetail)
admin.site.register(Document)
admin.site.register(DocumentType)
admin.site.register(EkModifier)
