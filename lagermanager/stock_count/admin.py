from django.contrib import admin

from .models import StockCountEntry


@admin.register(StockCountEntry)
class StockCountEntryAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ['article_name', 'article_id', 'location_name', 'quantity', 'count_date']
    list_filter = ['location_name', 'count_date']
    search_fields = ['article_name', 'article_id', 'location_name']
    ordering = ['-count_date', 'article_name']
