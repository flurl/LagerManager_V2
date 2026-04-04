from typing import Any

from constance import config as constance_cfg
from django.conf import settings
from django.db.models.query import QuerySet
from rest_framework import status, viewsets
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from pos_import.models import ArticleMeta

from .models import Location, Period
from .serializers import LocationSerializer, PeriodSerializer


class PeriodViewSet(viewsets.ModelViewSet[Period]):
    queryset: QuerySet[Period, Period] = Period.objects.all()
    serializer_class = PeriodSerializer

    def perform_create(self, serializer: PeriodSerializer) -> None:
        new_period: Period = serializer.save()
        source_period: Period | None = Period.objects.exclude(pk=new_period.pk).order_by('-start').first()
        if source_period is not None:
            metas = ArticleMeta.objects.filter(period=source_period)
            ArticleMeta.objects.bulk_create([
                ArticleMeta(
                    source_id=m.source_id,
                    period=new_period,
                    is_hidden=m.is_hidden,
                    sub_articles=m.sub_articles,
                    extra=m.extra,
                )
                for m in metas
            ])


class LocationViewSet(viewsets.ModelViewSet[Location]):
    queryset: QuerySet[Location, Location] = Location.objects.all()
    serializer_class = LocationSerializer


class ConfigView(APIView):

    def get(self, request: Request) -> Response:
        can_edit = request.user.has_perm('constance.change_config')
        cfg: dict[str, Any] = {}
        for key, (default, help_text, field_type) in settings.CONSTANCE_CONFIG.items():
            cfg[key] = {
                'value': getattr(constance_cfg, key),
                'default': default,
                'help_text': help_text,
                'type': field_type.__name__,
            }
        return Response({'can_edit': can_edit, 'config': cfg})

    def patch(self, request: Request) -> Response:
        if not request.user.has_perm('constance.change_config'):
            return Response({'detail': 'Keine Berechtigung.'}, status=status.HTTP_403_FORBIDDEN)
        errors: dict[str, str] = {}
        for key, value in request.data.items():
            if key not in settings.CONSTANCE_CONFIG:
                errors[key] = 'Unbekannter Schlüssel.'
                continue
            _, _, field_type = settings.CONSTANCE_CONFIG[key]
            try:
                setattr(constance_cfg, key, field_type(value))
            except (ValueError, TypeError):
                errors[key] = f'Ungültiger Wert für Typ {field_type.__name__}.'
        if errors:
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)
        return Response({'success': True})
