from typing import cast

from django.contrib.auth.models import User
from django.db.models.query import QuerySet
from django.utils import timezone
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from .models import Notification
from .serializers import NotificationSerializer


class NotificationViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet[Notification],
):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self) -> QuerySet[Notification, Notification]:
        user = cast(User, self.request.user)
        qs: QuerySet[Notification, Notification] = Notification.objects.filter(user=user)
        if self.request.query_params.get('unread') == 'true':
            qs = qs.filter(read_at__isnull=True)
        return qs

    @action(detail=True, methods=['post'], url_path='mark-read')
    def mark_read(self, request: Request, pk: int | None = None) -> Response:
        notification: Notification = self.get_object()
        if notification.read_at is None:
            notification.read_at = timezone.now()
            notification.save(update_fields=['read_at'])
        serializer = self.get_serializer(notification)
        return Response(serializer.data)

    @action(detail=False, methods=['post'], url_path='mark-all-read')
    def mark_all_read(self, request: Request) -> Response:
        updated: int = (
            self.get_queryset()
            .filter(read_at__isnull=True)
            .update(read_at=timezone.now())
        )
        return Response({'updated': updated})

    @action(detail=False, methods=['get'], url_path='unread-count')
    def unread_count(self, request: Request) -> Response:
        user = cast(User, request.user)
        count: int = Notification.objects.filter(user=user, read_at__isnull=True).count()
        return Response({'count': count})
