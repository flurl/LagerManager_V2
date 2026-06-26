import logging
import subprocess
from typing import Any, cast

from auditlog.models import LogEntry
from constance import config as constance_cfg
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.db.models.query import QuerySet
from pos_import.models import ArticleMeta
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer
from rest_framework.views import APIView

from .models import Address, Department, Location, Period, UserPreferences
from .permissions import DjangoModelPermissionsWithView, require_perm
from .serializers import (
    AddressSerializer,
    DepartmentSerializer,
    LocationSerializer,
    PeriodSerializer,
    SyncWzSerializer,
    UserPreferencesSerializer,
)

logger = logging.getLogger(__name__)


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
        fieldsets = getattr(settings, 'CONSTANCE_CONFIG_FIELDSETS', {})
        groups = [{'label': label, 'keys': list(keys)} for label, keys in fieldsets.items()]
        return Response({'can_edit': can_edit, 'config': cfg, 'groups': groups})

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


class VersionView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        try:
            commit_count = int(subprocess.check_output(
                ["git", "rev-list", "--count", "HEAD"],
                stderr=subprocess.DEVNULL,
            ).decode().strip())
        except Exception:
            commit_count = 0
        try:
            commit_hash = subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                stderr=subprocess.DEVNULL,
            ).decode().strip()
        except Exception:
            commit_hash = "unknown"
        return Response({"version": f"V2.{commit_count}", "hash": commit_hash})


class MeView(APIView):
    """Returns the current user's profile, permissions, and preferences.
    PATCH updates preferences only.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        user: User = cast(User, request.user)
        prefs, _ = UserPreferences.objects.get_or_create(user=user)
        return Response({
            'id': user.pk,
            'username': user.username,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'groups': list(user.groups.values_list('name', flat=True)),
            'permissions': sorted(user.get_all_permissions()),
            'preferences': UserPreferencesSerializer(prefs).data,
        })

    def patch(self, request: Request) -> Response:
        prefs, _ = UserPreferences.objects.get_or_create(user=request.user)
        serializer = UserPreferencesSerializer(prefs, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


# ---------------------------------------------------------------------------
# Audit-log helpers (also imported by billing.views for document history)
# ---------------------------------------------------------------------------

def _serialize_log_entry(e: LogEntry, source: str = 'document') -> dict[str, Any]:
    # Plain dict instead of a DRF serializer: this is a read-only, fixed-shape
    # response with no validation or write path, so the overhead of a serializer
    # class adds nothing. LogEntry also lacks stubs, making a typed ModelSerializer
    # awkward. Revisit if a schema generator (e.g. drf-spectacular) is added.
    actor = (e.actor.get_full_name() or e.actor.username) if e.actor else None
    return {
        'id': e.pk,
        'timestamp': e.timestamp,
        'actor': actor,
        'action': e.action,
        'changes': e.changes,
        'source': source,
        'object_repr': e.object_repr,
    }


class AuditLogHistoryMixin:
    """Adds GET /{pk}/history/ returning django-auditlog entries for this object."""

    @action(detail=True, methods=['get'], url_path='history')
    def history(self, request: Request, pk: str | None = None) -> Response:
        obj = self.get_object()  # type: ignore[attr-defined]
        ct = ContentType.objects.get_for_model(obj)
        entries = (
            LogEntry.objects
            .filter(content_type=ct, object_pk=str(obj.pk))
            .select_related('actor')
            .order_by('-timestamp')
        )
        data = [_serialize_log_entry(e) for e in entries if e.changes]
        return Response(data)


# ---------------------------------------------------------------------------
# Address
# ---------------------------------------------------------------------------

class AddressViewSet(AuditLogHistoryMixin, viewsets.ModelViewSet[Address]):
    queryset = Address.objects.all()
    serializer_class = AddressSerializer
    permission_classes = [IsAuthenticated, DjangoModelPermissionsWithView]

    def get_queryset(self) -> Any:
        qs = Address.objects.all()
        q: str | None = self.request.query_params.get('q')
        if q:
            qs = qs.filter(
                Q(vorname__icontains=q)
                | Q(nachname__icontains=q)
                | Q(firma__icontains=q)
                | Q(email__icontains=q)
            )
        return qs


class WzAddressSyncView(APIView):
    """POST /api/addresses/sync-wz/ — sync addresses from Wiffzack MSSQL."""

    permission_classes = [IsAuthenticated, require_perm('core.run_import')]

    def post(self, request: Request) -> Response:
        ser = SyncWzSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data: dict[str, str] = ser.validated_data

        try:
            from core.services.wz_address_sync import sync_addresses
            count: int = sync_addresses(
                host=data['host'],
                database=data['database'],
                user=data['user'],
                password=data['password'],
            )
        except Exception as exc:
            logger.exception('WZ address sync failed')
            return Response({'error': str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({'status': 'ok', 'count': count})
