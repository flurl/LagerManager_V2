from django.contrib import admin

from .models import StaffConsumptionEntry


@admin.register(StaffConsumptionEntry)
class StaffConsumptionEntryAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = [
        "article_name",
        "department_name",
        "count",
        "consumption_date",
        "year_month",
        "created_at",
    ]
    list_filter = ["department_name", "year_month"]
    search_fields = ["article_name", "department_name"]
    ordering = ["-consumption_date"]
