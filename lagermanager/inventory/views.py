import csv

from django.db.models import QuerySet
from django.http import HttpResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer

from .models import InitialInventory, PhysicalCount, PeriodStartStockLevel
from .serializers import (
    InitialInventorySerializer,
    PhysicalCountSerializer,
    PeriodStartStockLevelSerializer,
)
from .services.init_period import (
    init_initial_inventory,
    init_physical_count_date,
    init_stock_levels,
)


class PeriodStartStockLevelViewSet(viewsets.ModelViewSet):
    serializer_class = PeriodStartStockLevelSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self) -> QuerySet:
        qs = PeriodStartStockLevel.objects.select_related('article', 'period')
        period_id = self.request.query_params.get('period_id')
        if period_id:
            qs = qs.filter(period_id=period_id)
        return qs

    @action(detail=False, methods=['post'])
    def init_period(self, request: Request) -> Response:
        period_id = request.data.get('period_id')
        if not period_id:
            return Response({'error': 'period_id required'}, status=status.HTTP_400_BAD_REQUEST)
        count = init_stock_levels(int(period_id))
        return Response({'created': count})


class InitialInventoryViewSet(viewsets.ModelViewSet):
    serializer_class = InitialInventorySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self) -> QuerySet:
        qs = InitialInventory.objects.select_related('article', 'workplace', 'period')
        period_id = self.request.query_params.get('period_id')
        workplace_id = self.request.query_params.get('workplace_id')
        if period_id:
            qs = qs.filter(period_id=period_id)
        if workplace_id:
            qs = qs.filter(workplace_id=workplace_id)
        return qs

    @action(detail=False, methods=['post'])
    def init_period(self, request: Request) -> Response:
        period_id = request.data.get('period_id')
        source_period_id = request.data.get('source_period_id')
        if not period_id:
            return Response({'error': 'period_id required'}, status=status.HTTP_400_BAD_REQUEST)
        count = init_initial_inventory(int(period_id), int(source_period_id) if source_period_id else None)
        return Response({'created': count})

    @action(detail=False, methods=['get'])
    def export(self, request: Request) -> HttpResponse:
        period_id = request.query_params.get('period_id')
        qs = self.get_queryset()
        if period_id:
            qs = qs.filter(period_id=period_id)

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="initialer_stand.csv"'
        writer = csv.writer(response)
        writer.writerow(['Artikel', 'Arbeitsplatz', 'Menge', 'Periode'])
        for obj in qs:
            writer.writerow([obj.article.name, obj.workplace.name, obj.quantity, obj.period.name])
        return response


class PhysicalCountViewSet(viewsets.ModelViewSet):
    serializer_class = PhysicalCountSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self) -> QuerySet:
        qs = PhysicalCount.objects.select_related('article', 'period')
        period_id = self.request.query_params.get('period_id')
        date = self.request.query_params.get('date')
        if period_id:
            qs = qs.filter(period_id=period_id)
        if date:
            qs = qs.filter(date__date=date)
        return qs

    def perform_create(self, serializer: BaseSerializer) -> None:
        obj = serializer.save()
        # Auto-assign period from date
        if not obj.period_id:
            from core.models import Period
            period = Period.objects.filter(
                start__lte=obj.date, end__gte=obj.date
            ).first()
            if period:
                obj.period = period
                obj.save(update_fields=['period'])

    @action(detail=False, methods=['post'])
    def init_date(self, request: Request) -> Response:
        period_id = request.data.get('period_id')
        date = request.data.get('date')
        if not period_id or not date:
            return Response({'error': 'period_id and date required'}, status=status.HTTP_400_BAD_REQUEST)
        count = init_physical_count_date(int(period_id), date)
        return Response({'created': count})
