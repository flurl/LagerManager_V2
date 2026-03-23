from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import (
    Delivery,
    DeliveryDetail,
    DeliveryUnit,
    DocumentType,
    Supplier,
    TaxRate,
)
from .serializers import (
    DeliveryDetailSerializer,
    DeliveryListSerializer,
    DeliverySerializer,
    DeliveryUnitSerializer,
    DocumentTypeSerializer,
    SupplierSerializer,
    TaxRateSerializer,
)
from .services.discount import apply_skonto


class SupplierViewSet(viewsets.ModelViewSet):
    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer
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


class DeliveryViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action == 'list':
            return DeliveryListSerializer
        return DeliverySerializer

    def get_queryset(self):
        qs = Delivery.objects.select_related('supplier', 'period').prefetch_related('details__tax_rate')
        period_id = self.request.query_params.get('period_id')
        is_consumption = self.request.query_params.get('is_consumption')
        if period_id:
            qs = qs.filter(period_id=period_id)
        if is_consumption is not None:
            qs = qs.filter(is_consumption=is_consumption == '1')
        return qs

    def perform_create(self, serializer):
        delivery = serializer.save()
        # Auto-assign period from date if not provided
        if not delivery.period_id:
            from core.models import Period
            period = Period.objects.filter(
                start__lte=delivery.date, end__gte=delivery.date
            ).first()
            if period:
                delivery.period = period
                delivery.save(update_fields=['period'])

    @action(detail=True, methods=['post'])
    def apply_discount(self, request, pk=None):
        delivery = self.get_object()
        percent = request.data.get('percent')
        if percent is None:
            return Response({'error': 'percent required'}, status=status.HTTP_400_BAD_REQUEST)
        apply_skonto(delivery, float(percent))
        return Response(DeliverySerializer(delivery, context={'request': request}).data)


class DeliveryDetailViewSet(viewsets.ModelViewSet):
    serializer_class = DeliveryDetailSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        delivery_pk = self.kwargs.get('delivery_pk')
        return DeliveryDetail.objects.filter(delivery_id=delivery_pk).select_related('article', 'tax_rate')
