import datetime as dt

from core.models import Department, Period
from core.permissions import require_perm
from core.services.period import get_period_for_datetime
from pos_import.models import WarehouseArticle
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import StaffConsumptionEntry
from .serializers import BulkStaffConsumptionSerializer

_add_consumption = require_perm("staff_consumption.add_staffconsumptionentry")


class StaffConsumptionDepartmentListView(APIView):
    """Public endpoint — returns all departments for the consumption form."""

    permission_classes = [AllowAny]

    def get(self, request: Request) -> Response:
        departments = list(Department.objects.values("id", "name"))
        return Response(departments)


class StaffConsumptionArticleListView(APIView):
    """Public endpoint — returns warehouse articles for a period (base articles only, no sub-variants).

    Accepts ``period_id=<int>`` or falls back to the period active at the current datetime.
    """

    permission_classes = [AllowAny]

    def get(self, request: Request) -> Response:
        period_id_str = request.query_params.get("period_id")
        if period_id_str:
            period_id = int(period_id_str)
        else:
            period: Period | None = get_period_for_datetime(dt.datetime.now(tz=dt.timezone.utc))
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
            .values("article__source_id", "article__name")
        )
        return Response([
            {"article_id": str(a["article__source_id"]), "article_name": a["article__name"]}
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
