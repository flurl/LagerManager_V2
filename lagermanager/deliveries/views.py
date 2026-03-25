from django.db.models import QuerySet
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer

from .models import (
    DeliveryUnit,
    DocumentType,
    EkModifier,
    Partner,
    StockMovement,
    StockMovementDetail,
    TaxRate,
)
from .serializers import (
    DeliveryUnitSerializer,
    DocumentTypeSerializer,
    EkModifierSerializer,
    PartnerSerializer,
    StockMovementDetailSerializer,
    StockMovementListSerializer,
    StockMovementSerializer,
    TaxRateSerializer,
)


class PartnerViewSet(viewsets.ModelViewSet):
    queryset = Partner.objects.all()
    serializer_class = PartnerSerializer
    permission_classes = [IsAuthenticated]


class TaxRateViewSet(viewsets.ModelViewSet):
    queryset = TaxRate.objects.all()
    serializer_class = TaxRateSerializer
    permission_classes = [IsAuthenticated]


class DeliveryUnitViewSet(viewsets.ModelViewSet):
    queryset = DeliveryUnit.objects.all()
    serializer_class = DeliveryUnitSerializer
    permission_classes = [IsAuthenticated]


class DocumentTypeViewSet(viewsets.ModelViewSet):
    queryset = DocumentType.objects.all()
    serializer_class = DocumentTypeSerializer
    permission_classes = [IsAuthenticated]


class StockMovementViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self) -> type[BaseSerializer]:
        if self.action == 'list':
            return StockMovementListSerializer
        return StockMovementSerializer

    def get_queryset(self) -> QuerySet:
        qs = StockMovement.objects.select_related('partner', 'period').prefetch_related('details__tax_rate')
        period_id = self.request.query_params.get('period_id')
        movement_type = self.request.query_params.get('movement_type')
        if period_id:
            qs = qs.filter(period_id=period_id)
        if movement_type:
            qs = qs.filter(movement_type=movement_type)
        return qs

    def perform_create(self, serializer: BaseSerializer) -> None:
        movement = serializer.save()
        # Auto-assign period from date if not provided
        if not movement.period_id:
            from core.models import Period
            period = Period.objects.filter(
                start__lte=movement.date, end__gte=movement.date
            ).first()
            if period:
                movement.period = period
                movement.save(update_fields=['period'])

    @action(detail=True, methods=['post'])
    def apply_discount(self, request: Request, pk: int | None = None) -> Response:
        movement = self.get_object()
        percent = request.data.get('percent')
        if percent is None:
            return Response({'error': 'percent required'}, status=status.HTTP_400_BAD_REQUEST)
        movement.apply_skonto(float(percent))
        return Response(StockMovementSerializer(movement, context={'request': request}).data)


class StockMovementDetailViewSet(viewsets.ModelViewSet):
    serializer_class = StockMovementDetailSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self) -> QuerySet:
        movement_pk = self.kwargs.get('movement_pk')
        return StockMovementDetail.objects.filter(
            stock_movement_id=movement_pk
        ).select_related('article', 'tax_rate')


class EkModifierViewSet(viewsets.ModelViewSet):
    serializer_class = EkModifierSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self) -> QuerySet:
        qs = EkModifier.objects.all()
        period_id = self.request.query_params.get('period_id')
        if period_id:
            qs = qs.filter(period_id=period_id)
        return qs
