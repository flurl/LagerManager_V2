from django.contrib import admin

from .models import (
    Attachment,
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
admin.site.register(Attachment)
admin.site.register(EkModifier)
