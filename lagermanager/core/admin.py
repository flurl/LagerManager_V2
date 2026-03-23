from django.contrib import admin

from .models import Config, Period, Workplace

admin.site.register(Period)
admin.site.register(Workplace)
admin.site.register(Config)
