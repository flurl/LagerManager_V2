from typing import Any

from constance import config as constance_cfg
from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser
from django.db.models.query import QuerySet
from pos_import.models import ArticleMeta
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer
from rest_framework.views import APIView

from .models import Department, Location, Period, UserPreferences
from .permissions import DjangoModelPermissionsWithView
from .serializers import DepartmentSerializer, LocationSerializer, PeriodSerializer, UserPreferencesSerializer


class PeriodViewSet(viewsets.ModelViewSet[Period]):
    queryset: QuerySet[Period, Period] = Period.objects.all()
    serializer_class = PeriodSerializer
    permission_classes = [IsAuthenticated, DjangoModelPermissionsWithView]

    def perform_create(self, serializer: BaseSerializer[Period]) -> None:
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


class DepartmentViewSet(viewsets.ModelViewSet[Department]):
    queryset: QuerySet[Department, Department] = Department.objects.all()
    serializer_class = DepartmentSerializer
    permission_classes = [IsAuthenticated, DjangoModelPermissionsWithView]


class LocationViewSet(viewsets.ModelViewSet[Location]):
    queryset: QuerySet[Location, Location] = Location.objects.all()
    serializer_class = LocationSerializer
    permission_classes = [IsAuthenticated, DjangoModelPermissionsWithView]


class PeriodByDateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        date_str = request.query_params.get('date')
        if not date_str:
            return Response({'error': 'date required'}, status=status.HTTP_400_BAD_REQUEST)
        period: Period | None = (
            Period.objects
            .filter(start__date__lte=date_str, end__date__gte=date_str)
            .order_by('-start')
            .first()
        )
        if period is None:
            return Response({'error': 'No period found for date'}, status=status.HTTP_404_NOT_FOUND)
        return Response(PeriodSerializer(period).data)


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


class MeView(APIView):
    """Returns the current user's profile, permissions, and preferences.
    PATCH updates preferences only.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        user: AbstractBaseUser = request.user
        prefs, _ = UserPreferences.objects.get_or_create(user=user)
        return Response({
            'id': user.pk,
            'username': user.username,  # type: ignore[attr-defined]
            'first_name': user.first_name,  # type: ignore[attr-defined]
            'last_name': user.last_name,  # type: ignore[attr-defined]
            'groups': list(user.groups.values_list('name', flat=True)),  # type: ignore[attr-defined]
            'permissions': sorted(user.get_all_permissions()),
            'preferences': UserPreferencesSerializer(prefs).data,
        })

    def patch(self, request: Request) -> Response:
        prefs, _ = UserPreferences.objects.get_or_create(user=request.user)
        serializer = UserPreferencesSerializer(prefs, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
