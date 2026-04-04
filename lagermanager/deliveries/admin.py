from django.contrib import admin

from .models import (
    Attachment,
    Partner,
    PartnerAiInstruction,
    StockMovement,
    StockMovementDetail,
    TaxRate,
)


class PartnerAiInstructionInline(admin.TabularInline):
    model = PartnerAiInstruction
    extra = 1


@admin.register(Partner)
class PartnerAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    inlines = [PartnerAiInstructionInline]
admin.site.register(TaxRate)
admin.site.register(StockMovement)
admin.site.register(StockMovementDetail)
admin.site.register(Attachment)
