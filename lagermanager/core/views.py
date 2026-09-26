import logging
import subprocess
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

from auditlog.models import LogEntry
from constance import config as constance_cfg
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Case, DecimalField, F, IntegerField, Q, Sum, Value, When
from django.db.models.functions import Coalesce
from django.db.models.query import QuerySet
from pos_import.models import ArticleMeta
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer
from rest_framework.views import APIView

from .models import Address, Customer, Department, Location, Period, UserPreferences
from .permissions import DjangoModelPermissionsWithView, require_perm
from .serializers import (
    AddressSerializer,
    CustomerSerializer,
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
        # The settings form always sends a JSON object; DRF types data as dict | list.
        data: dict[str, Any] = cast(dict[str, Any], request.data)
        for key, value in data.items():
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


_ALLOWED_LOGO_MIME_PREFIXES = ('image/png', 'image/jpeg', 'image/gif', 'image/webp', 'image/svg+xml')
_LOGO_DEST = Path('billing') / 'logo' / 'company'


class ConfigLogoView(APIView):
    parser_classes = [MultiPartParser]

    def get(self, request: Request) -> Response:
        logo_path: str = getattr(constance_cfg, 'COMPANY_LOGO', '')
        if logo_path and (Path(settings.MEDIA_ROOT) / logo_path).is_file():
            url: str | None = request.build_absolute_uri(settings.MEDIA_URL + logo_path)
        else:
            url = None
        return Response({'url': url, 'path': logo_path})

    def post(self, request: Request) -> Response:
        if not request.user.has_perm('constance.change_config'):
            return Response({'detail': 'Keine Berechtigung.'}, status=status.HTTP_403_FORBIDDEN)
        upload = request.FILES.get('logo')
        if not upload:
            return Response({'detail': 'Keine Datei übermittelt.'}, status=status.HTTP_400_BAD_REQUEST)
        content_type: str = upload.content_type or ''
        if not any(content_type.startswith(p) for p in _ALLOWED_LOGO_MIME_PREFIXES):
            return Response({'detail': 'Nur Bilddateien erlaubt (PNG, JPEG, GIF, WebP, SVG).'}, status=status.HTTP_400_BAD_REQUEST)
        suffix = Path(upload.name).suffix.lower() or '.png'
        dest_rel = str(_LOGO_DEST) + suffix
        dest_abs = Path(settings.MEDIA_ROOT) / dest_rel
        dest_abs.parent.mkdir(parents=True, exist_ok=True)
        with dest_abs.open('wb') as fh:
            for chunk in upload.chunks():
                fh.write(chunk)
        constance_cfg.COMPANY_LOGO = dest_rel
        return Response({'url': request.build_absolute_uri(settings.MEDIA_URL + dest_rel), 'path': dest_rel})

    def delete(self, request: Request) -> Response:
        if not request.user.has_perm('constance.change_config'):
            return Response({'detail': 'Keine Berechtigung.'}, status=status.HTTP_403_FORBIDDEN)
        logo_path: str = getattr(constance_cfg, 'COMPANY_LOGO', '')
        if logo_path:
            abs_path = Path(settings.MEDIA_ROOT) / logo_path
            if abs_path.is_file():
                abs_path.unlink()
            constance_cfg.COMPANY_LOGO = ''
        return Response({'success': True})


class VersionView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        try:
            commit_count = int(settings.GIT_COMMIT_COUNT or subprocess.check_output(
                ["git", "rev-list", "--count", "HEAD"],
                stderr=subprocess.DEVNULL,
            ).decode().strip())
        except Exception:
            commit_count = 0
        try:
            commit_hash = settings.GIT_COMMIT or subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                stderr=subprocess.DEVNULL,
            ).decode().strip()
        except Exception:
            commit_hash = "unknown"
        return Response({
            "version": f"V2.{commit_count}",
            "hash": commit_hash,
            "preview_branch": settings.PREVIEW_BRANCH,
        })


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
        user: User = cast(User, request.user)  # IsAuthenticated guarantees a real User
        prefs, _ = UserPreferences.objects.get_or_create(user=user)
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
        qs = Address.objects.select_related('customer')
        q: str | None = self.request.query_params.get('q')
        if q:
            qs = qs.filter(
                Q(vorname__icontains=q)
                | Q(nachname__icontains=q)
                | Q(firma__icontains=q)
                | Q(email__icontains=q)
            )
        customer_id: str | None = self.request.query_params.get('customer_id')
        if customer_id:
            try:
                qs = qs.filter(customer_id=int(customer_id))
            except ValueError:
                pass
        unassigned: str | None = self.request.query_params.get('unassigned')
        if unassigned is not None and unassigned.lower() in ('1', 'true', 'yes'):
            qs = qs.filter(customer__isnull=True)
        return qs

    def perform_create(self, serializer: BaseSerializer[Address]) -> None:
        """Every address belongs to a customer.

        When none is supplied, create one 1:1 from the address itself — the same
        guarantee the Wiffzack sync gives for imported addresses — so a balance
        can always be kept for whoever the document is billed to.
        """
        from .services.customers import ensure_customer_for_address

        with transaction.atomic():
            address: Address = serializer.save()
            ensure_customer_for_address(address)


class CustomerViewSet(AuditLogHistoryMixin, viewsets.ModelViewSet[Customer]):
    """Kunden — the party a document is billed to and the balance is kept for."""

    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    permission_classes = [IsAuthenticated, DjangoModelPermissionsWithView]

    def get_queryset(self) -> Any:
        qs = (
            Customer.objects
            .select_related('default_address')
            .prefetch_related('addresses')
            .annotate(
                balance_sum=Coalesce(
                    Sum('ledger_entries__amount'),
                    Decimal('0.00'),
                    output_field=DecimalField(max_digits=18, decimal_places=2),
                ),
            )
        )
        q: str | None = self.request.query_params.get('q')
        if q:
            qs = qs.filter(
                Q(name__icontains=q)
                | Q(customer_number__icontains=q)
                | Q(email__icontains=q)
                | Q(addresses__email__icontains=q)
            ).distinct()
        active: str | None = self.request.query_params.get('active')
        if active is not None:
            qs = qs.filter(is_active=active.lower() in ('1', 'true', 'yes'))
        return qs

    def perform_create(self, serializer: BaseSerializer[Customer]) -> None:
        from .services.numbering import allocate_customer_number
        with transaction.atomic():
            serializer.save(customer_number=allocate_customer_number())

    def destroy(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Refuse to delete a customer that documents or money still point at.

        The FKs are PROTECT, so without this the ProtectedError would surface as
        a 500 instead of a message the user can act on.
        """
        customer: Customer = self.get_object()
        blockers: list[str] = []
        if customer.invoices.exists():
            blockers.append('Rechnungen')
        if customer.offers.exists():
            blockers.append('Angebote')
        if customer.payments.exists():
            blockers.append('Zahlungen')
        if customer.ledger_entries.exists():
            blockers.append('Kontobewegungen')
        if blockers:
            return Response(
                {'detail': 'Kunde kann nicht gelöscht werden — es gibt noch '
                           f'{", ".join(blockers)}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=['get'], url_path='balance')
    def balance(self, request: Request, pk: str | None = None) -> Response:
        # Lazy import: core must not depend on billing at module level.
        from billing.services.ledger import available_credit, customer_balance
        customer: Customer = self.get_object()
        return Response({
            'balance': str(customer_balance(customer)),
            'available_credit': str(available_credit(customer)),
        })

    @action(detail=True, methods=['get'], url_path='ledger')
    def ledger(self, request: Request, pk: str | None = None) -> Response:
        """Every movement on this customer's account, with a running balance.

        The acting user comes from the audit log's CREATE entry for each row, so
        the dialog can show who booked what without duplicating the actor on the
        ledger model itself.
        """
        from billing.models import CustomerLedgerEntry

        customer: Customer = self.get_object()
        # Ordered by content rather than by insertion: entry_date, then the
        # invoice the movement belongs to, then what kind of movement it is.
        # Grouping by invoice number keeps a Storno directly under the invoice
        # it reverses, and the type rank keeps a charge above the payment that
        # settles it on the same day.  entry_date is only a date, so insertion
        # order carries no intra-day truth worth preserving — and the backfill
        # wrote historic rows newest-first, so pk order is actively misleading.
        entries = (
            CustomerLedgerEntry.objects
            .filter(customer=customer)
            .select_related('invoice', 'reminder')
            .annotate(type_rank=Case(
                When(entry_type=CustomerLedgerEntry.EntryType.INVOICE, then=Value(0)),
                When(entry_type=CustomerLedgerEntry.EntryType.REMINDER_FEE, then=Value(1)),
                When(entry_type=CustomerLedgerEntry.EntryType.PAYMENT, then=Value(2)),
                default=Value(3),
                output_field=IntegerField(),
            ))
            .order_by(
                'entry_date',
                F('invoice__number').asc(nulls_last=True),
                'type_rank',
                'pk',
            )
        )
        actors = _create_actors(CustomerLedgerEntry, [e.pk for e in entries])

        running = Decimal('0.00')
        data: list[dict[str, Any]] = []
        for e in entries:
            running += e.amount
            data.append({
                'id': e.pk,
                'entry_date': e.entry_date,
                'entry_type': e.entry_type,
                'entry_type_display': e.get_entry_type_display(),
                'description': e.description,
                'amount': str(e.amount),
                'running_balance': str(running),
                'invoice': e.invoice_id,
                'invoice_number': e.invoice.number if e.invoice_id and e.invoice else None,
                # A reminder-fee movement links to the Mahnung that charged it,
                # not only to the invoice it was charged against.
                'reminder': e.reminder_id,
                'reminder_number': e.reminder.number if e.reminder_id and e.reminder else None,
                'is_reversal': e.is_reversal,
                'actor': actors.get(str(e.pk)),
            })
        return Response({'balance': str(running), 'entries': data})


def _create_actors(model: type[Any], pks: list[int]) -> dict[str, str | None]:
    """Map object_pk → actor name, taken from each object's CREATE log entry."""
    if not pks:
        return {}
    ct = ContentType.objects.get_for_model(model)
    entries = (
        LogEntry.objects
        .filter(content_type=ct, object_pk__in=[str(pk) for pk in pks],
                action=LogEntry.Action.CREATE)
        .select_related('actor')
    )
    return {
        e.object_pk: (e.actor.get_full_name() or e.actor.username) if e.actor else None
        for e in entries
    }


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
