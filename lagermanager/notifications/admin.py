from django.contrib import admin

from .models import Notification, StockAlertSubscription


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ('user', 'severity', 'title', 'kind', 'created_at', 'read_at')
    list_filter = ('severity', 'kind', 'read_at')
    search_fields = ('title', 'message', 'user__username')
    readonly_fields = ('created_at',)


@admin.register(StockAlertSubscription)
class StockAlertSubscriptionAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ('user', 'active', 'created_at')
    list_filter = ('active',)
    search_fields = ('user__username',)
    readonly_fields = ('created_at',)
