from django.contrib import admin

from .models import Address, Location, Period

admin.site.register(Address)
admin.site.register(Period)
admin.site.register(Location)
