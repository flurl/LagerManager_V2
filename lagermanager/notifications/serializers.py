from rest_framework import serializers

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer[Notification]):
    is_read = serializers.BooleanField(read_only=True)

    class Meta:
        model = Notification
        fields = ['id', 'severity', 'title', 'message', 'kind', 'link', 'read_at', 'created_at', 'is_read']
        read_only_fields = ['id', 'severity', 'title', 'message', 'kind', 'link', 'read_at', 'created_at', 'is_read']
