from django.contrib import admin

from .models import Address, Customer, CustomerNumberSequence, Location, Period

admin.site.register(Address)
admin.site.register(Customer)
admin.site.register(CustomerNumberSequence)
admin.site.register(Period)
admin.site.register(Location)
