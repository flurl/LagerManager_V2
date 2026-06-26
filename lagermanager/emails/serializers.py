from rest_framework import serializers

from emails.models import EmailAttachment, EmailLog


class EmailAttachmentSerializer(serializers.ModelSerializer[EmailAttachment]):
    # DRF FileField serializes to the full URL when a request is in context.
    file_url = serializers.FileField(source='file', read_only=True)

    class Meta:
        model = EmailAttachment
        fields = ['id', 'original_filename', 'mime_type', 'file_url']


class EmailLogSerializer(serializers.ModelSerializer[EmailLog]):
    sent_by_name = serializers.SerializerMethodField()
    attachments = EmailAttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = EmailLog
        fields = [
            'id',
            'recipient',
            'cc',
            'subject',
            'status',
            'error_message',
            'sent_by_name',
            'sent_at',
            'attachments',
        ]

    def get_sent_by_name(self, obj: EmailLog) -> str | None:
        if obj.sent_by is None:
            return None
        return obj.sent_by.get_full_name() or obj.sent_by.username
