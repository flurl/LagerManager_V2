from django.contrib import admin

from .models import InitialInventory, PhysicalCount, PeriodStartStockLevel

admin.site.register(PeriodStartStockLevel)
admin.site.register(InitialInventory)
admin.site.register(PhysicalCount)
