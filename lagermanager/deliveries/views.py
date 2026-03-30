from django.db.models import QuerySet
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer

from .models import (
    DocumentType,
    EkModifier,
    Partner,
    StockMovement,
    StockMovementDetail,
    TaxRate,
)
from .serializers import (
    DocumentTypeSerializer,
    EkModifierSerializer,
    PartnerSerializer,
    StockMovementDetailSerializer,
    StockMovementListSerializer,
    StockMovementSerializer,
    TaxRateSerializer,
)


class PartnerViewSet(viewsets.ModelViewSet[Partner]):
    queryset = Partner.objects.all()
    serializer_class = PartnerSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self) -> QuerySet[Partner]:
        qs = Partner.objects.all()
        partner_type = self.request.query_params.get('partner_type')
        if partner_type:
            qs = qs.filter(partner_type=partner_type)
        return qs


class TaxRateViewSet(viewsets.ModelViewSet[TaxRate]):
    queryset = TaxRate.objects.all()
    serializer_class = TaxRateSerializer
    permission_classes = [IsAuthenticated]


class DocumentTypeViewSet(viewsets.ModelViewSet[DocumentType]):
    queryset = DocumentType.objects.all()
    serializer_class = DocumentTypeSerializer
    permission_classes = [IsAuthenticated]


class StockMovementViewSet(viewsets.ModelViewSet[StockMovement]):
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self) -> type[BaseSerializer[StockMovement]]:
        if self.action == 'list':
            return StockMovementListSerializer
        return StockMovementSerializer

    def get_queryset(self) -> QuerySet[StockMovement]:
        qs = StockMovement.objects.select_related(
            'partner', 'period').prefetch_related('details__tax_rate')
        period_id = self.request.query_params.get('period_id')
        movement_type = self.request.query_params.get('movement_type')
        if period_id:
            qs = qs.filter(period_id=period_id)
        if movement_type:
            qs = qs.filter(movement_type=movement_type)
        partner_id = self.request.query_params.get('partner_id')
        if partner_id:
            qs = qs.filter(partner_id=partner_id)
        date = self.request.query_params.get('date')
        if date:
            qs = qs.filter(date=date)
        article_ids = self.request.query_params.getlist('article_id')
        if article_ids:
            qs = qs.filter(details__article__in=article_ids).distinct()
        return qs

    def perform_create(self, serializer: BaseSerializer[StockMovement]) -> None:
        serializer.save()

    @action(detail=True, methods=['post'])
    def apply_discount(self, request: Request, pk: int | None = None) -> Response:
        movement = self.get_object()
        percent = request.data.get('percent')
        if percent is None:
            return Response({'error': 'percent required'}, status=status.HTTP_400_BAD_REQUEST)
        movement.apply_skonto(float(percent))
        return Response(StockMovementSerializer(movement, context={'request': request}).data)


class StockMovementDetailViewSet(viewsets.ModelViewSet[StockMovementDetail]):
    serializer_class = StockMovementDetailSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self) -> QuerySet[StockMovementDetail]:
        movement_pk = self.kwargs.get('movement_pk')
        return StockMovementDetail.objects.filter(
            stock_movement_id=movement_pk
        ).select_related('article', 'tax_rate')


class EkModifierViewSet(viewsets.ModelViewSet[EkModifier]):
    serializer_class = EkModifierSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self) -> QuerySet[EkModifier]:
        qs = EkModifier.objects.all()
        period_id = self.request.query_params.get('period_id')
        if period_id:
            qs = qs.filter(period_id=period_id)
        return qs
