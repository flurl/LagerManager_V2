from django.contrib import admin

from .models import InitialInventory, PhysicalCount, StockLevel

admin.site.register(StockLevel)
admin.site.register(InitialInventory)
admin.site.register(PhysicalCount)
