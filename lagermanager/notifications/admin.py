from django.contrib import admin

from .models import InvoiceAlertSubscription, Notification, StockAlertSubscription


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ('user', 'severity', 'title', 'kind', 'created_at', 'read_at')
    list_filter = ('severity', 'kind', 'read_at')
    search_fields = ('title', 'message', 'user__username')
    readonly_fields = ('created_at',)


@admin.register(StockAlertSubscription)
class StockAlertSubscriptionAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ('user', 'active', 'email_enabled', 'created_at')
    list_filter = ('active', 'email_enabled')
    search_fields = ('user__username',)
    readonly_fields = ('created_at',)


@admin.register(InvoiceAlertSubscription)
class InvoiceAlertSubscriptionAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ('user', 'active', 'email_enabled', 'created_at')
    list_filter = ('active', 'email_enabled')
    search_fields = ('user__username',)
    readonly_fields = ('created_at',)
