import datetime as dt
from collections import defaultdict
from decimal import Decimal
from typing import Any

from core.models import Department, Period
from core.permissions import require_perm
from core.services.period import get_period_for_datetime
from deliveries.models import StockMovement, StockMovementDetail
from pos_import.models import WarehouseArticle
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import StaffConsumptionEntry
from .serializers import (
    BulkStaffConsumptionSerializer,
    StaffConsumptionEntrySerializer,
    StaffConsumptionImportRequestSerializer,
)

_add_consumption = require_perm("staff_consumption.add_staffconsumptionentry")
_add_movement = require_perm("deliveries.add_stockmovement")


class StaffConsumptionDepartmentListView(APIView):
    """Public endpoint — returns all departments for the consumption form."""

    permission_classes = [AllowAny]

    def get(self, request: Request) -> Response:
        departments = list(Department.objects.values("id", "name"))
        return Response(departments)


class StaffConsumptionArticleListView(APIView):
    """Public endpoint — returns warehouse articles for a period (base articles only, no sub-variants).

    Accepts ``period_id=<int>`` or ``year_month=<YYYY-M>`` or falls back to the period active
    at the current datetime.
    """

    permission_classes = [AllowAny]

    def get(self, request: Request) -> Response:
        period_id_str = request.query_params.get("period_id")
        year_month_str = request.query_params.get("year_month")

        if period_id_str:
            period_id = int(period_id_str)
        elif year_month_str:
            parts = year_month_str.split("-")
            if len(parts) != 2:
                return Response(
                    {"error": "Ungültiges year_month Format."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            try:
                first_day_dt = dt.datetime(int(parts[0]), int(
                    parts[1]), 1, tzinfo=dt.timezone.utc)
            except ValueError:
                return Response(
                    {"error": "Ungültiges year_month Format."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            period: Period | None = get_period_for_datetime(first_day_dt)
            if period is None:
                return Response(
                    {"error": f"Keine Periode für {year_month_str} gefunden."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            period_id = period.pk
        else:
            period = get_period_for_datetime(
                dt.datetime.now(tz=dt.timezone.utc))
            if period is None:
                return Response(
                    {"error": "Keine aktive Periode für das heutige Datum gefunden."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            period_id = period.pk

        articles = (
            WarehouseArticle.objects.select_related("article")
            .filter(period_id=period_id)
            .order_by("article__name")
            .values("article__source_id", "article__name", "article__id")
        )
        return Response([
            {
                "article_id": str(a["article__source_id"]),
                "article_pk": a["article__id"],
                "article_name": a["article__name"],
            }
            for a in articles
        ])


class BulkStaffConsumptionView(APIView):
    permission_classes = [IsAuthenticated, _add_consumption]

    def post(self, request: Request) -> Response:
        serializer = BulkStaffConsumptionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        consumption_date = data["consumption_date"]
        department_name: str = data["department_name"]
        year_month: str = data["year_month"]

        saved: list[int] = []
        for entry in data["entries"]:
            obj, _ = StaffConsumptionEntry.objects.update_or_create(
                consumption_date=consumption_date,
                department_name=department_name,
                article_id=entry["article_id"],
                defaults={
                    "article_name": entry["article_name"],
                    "count": entry["count"],
                    "year_month": year_month,
                },
            )
            saved.append(obj.pk)

        return Response({"saved": len(saved)}, status=status.HTTP_200_OK)


class StaffConsumptionGroupedView(APIView):
    """Returns StaffConsumptionEntry records grouped by year_month with department names."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:  # noqa: ARG002
        raw_year_months: list[str] = list(
            StaffConsumptionEntry.objects.order_by().values_list(
                "year_month", flat=True).distinct()
        )
        year_months = sorted(
            raw_year_months,
            key=lambda ym: tuple(int(x) for x in ym.split("-")),
            reverse=True,
        )

        result: list[dict[str, Any]] = []
        for ym in year_months:
            entries_qs = StaffConsumptionEntry.objects.filter(year_month=ym)
            departments: list[str] = list(
                entries_qs.values_list("department_name", flat=True)
                .distinct()
                .order_by("department_name")
            )
            entry_count: int = entries_qs.count()

            # Resolve the period for this year_month so the frontend has the period_id
            period_id: int | None = None
            parts = ym.split("-")
            if len(parts) == 2:
                try:
                    first_day_dt = dt.datetime(int(parts[0]), int(
                        parts[1]), 1, tzinfo=dt.timezone.utc)
                    period = get_period_for_datetime(first_day_dt)
                    period_id = period.pk if period else None
                except ValueError:
                    pass

            result.append({
                "year_month": ym,
                "departments": departments,
                "entry_count": entry_count,
                "period_id": period_id,
            })

        return Response(result)


class StaffConsumptionEntriesListView(APIView):
    """GET/DELETE StaffConsumptionEntry records for a given year_month."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        year_month = request.query_params.get("year_month")
        if not year_month:
            return Response(
                {"error": "year_month query parameter is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        entries = StaffConsumptionEntry.objects.filter(year_month=year_month)
        serializer = StaffConsumptionEntrySerializer(entries, many=True)
        return Response(serializer.data)

    def delete(self, request: Request) -> Response:
        """Delete entries for a year_month.

        If ``department_name`` and ``article_id`` are also provided, only the
        matching article rows are deleted; otherwise all entries for the
        year_month are removed.
        """
        year_month = request.query_params.get("year_month")
        if not year_month:
            return Response(
                {"error": "year_month query parameter is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        qs = StaffConsumptionEntry.objects.filter(year_month=year_month)

        department_name = request.query_params.get("department_name")
        article_id = request.query_params.get("article_id")
        if department_name and article_id:
            qs = qs.filter(department_name=department_name, article_id=article_id)

        deleted, _ = qs.delete()
        return Response({"deleted": deleted})


class StaffConsumptionImportCreateView(APIView):
    """Creates consumption StockMovements from StaffConsumptionEntry records.

    The frontend is responsible for:
    - Resolving article source_ids to Article PKs
    - Resolving the 20% tax rate to its PK
    - Mapping departments to partner IDs

    This endpoint resolves year_month → period and creates the movements + details.
    """

    permission_classes = [IsAuthenticated, _add_movement]

    def post(self, request: Request) -> Response:
        serializer = StaffConsumptionImportRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        year_month: str = data["year_month"]

        parts = year_month.split("-")
        if len(parts) != 2:
            return Response(
                {"error": "Ungültiges year_month Format."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            first_day = dt.date(int(parts[0]), int(parts[1]), 1)
            first_day_dt = dt.datetime(int(parts[0]), int(
                parts[1]), 1, tzinfo=dt.timezone.utc)
        except ValueError:
            return Response(
                {"error": "Ungültiges year_month Format."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        period: Period | None = get_period_for_datetime(first_day_dt)
        if period is None:
            return Response(
                {"error": f"Keine Periode für {year_month} gefunden."},
                status=status.HTTP_404_NOT_FOUND,
            )

        created_ids: list[int] = []
        skipped: list[str] = []

        # Group mappings by partner so all departments sharing the same partner
        # end up in a single StockMovement.
        by_partner: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for mapping in data["mappings"]:
            if not mapping["entries"]:
                skipped.append(mapping["department_name"])
            else:
                by_partner[mapping["partner_id"]].append(mapping)

        for partner_id, partner_mappings in by_partner.items():
            dept_names: list[str] = [m["department_name"] for m in partner_mappings]
            movement = StockMovement.objects.create(
                partner_id=partner_id,
                date=first_day,
                movement_type=StockMovement.Type.CONSUMPTION,
                comment=f"Personalverbrauch {year_month} – {', '.join(dept_names)}",
                period=period,
            )

            # Aggregate quantities per (article_id, tax_rate_id) across all departments
            # mapped to this partner so each article appears only once.
            totals: dict[tuple[int, int], int] = {}
            for mapping in partner_mappings:
                for entry in mapping["entries"]:
                    key = (int(entry["article_id"]), int(entry["tax_rate_id"]))
                    totals[key] = totals.get(key, 0) + int(entry["quantity"])

            for (article_id, tax_rate_id), quantity in totals.items():
                StockMovementDetail.objects.create(
                    stock_movement=movement,
                    article_id=article_id,
                    quantity=quantity,
                    unit_price=Decimal("0"),
                    tax_rate_id=tax_rate_id,
                )

            created_ids.append(movement.pk)

        return Response(
            {"created": len(created_ids), "movement_ids": created_ids,
             "skipped_departments": skipped},
            status=status.HTTP_201_CREATED,
        )
