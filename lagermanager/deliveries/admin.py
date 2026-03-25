from django.contrib import admin

from .models import (
    Document,
    DocumentType,
    EkModifier,
    Partner,
    StockMovement,
    StockMovementDetail,
    TaxRate,
)

admin.site.register(Partner)
admin.site.register(TaxRate)
admin.site.register(StockMovement)
admin.site.register(StockMovementDetail)
admin.site.register(Document)
admin.site.register(DocumentType)
admin.site.register(EkModifier)
