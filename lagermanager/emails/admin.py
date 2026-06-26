from django.contrib import admin

from emails.models import EmailAttachment, EmailLog


class EmailAttachmentInline(admin.TabularInline):
    model = EmailAttachment
    extra = 0
    readonly_fields = ['original_filename', 'mime_type', 'file']
    can_delete = False

    def has_add_permission(self, request, obj=None) -> bool:  # type: ignore[override]
        return False


@admin.register(EmailLog)
class EmailLogAdmin(admin.ModelAdmin):
    list_display = ['sent_at', 'status', 'recipient', 'subject', 'sent_by']
    list_filter = ['status']
    search_fields = ['recipient', 'subject', 'sent_by__username']
    readonly_fields = [
        'from_email', 'recipient', 'cc', 'subject', 'body',
        'status', 'error_message', 'sent_by', 'sent_at',
        'content_type', 'object_id',
    ]
    inlines = [EmailAttachmentInline]
    ordering = ['-sent_at']

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False
