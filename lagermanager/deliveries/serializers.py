from rest_framework import serializers

from .models import (
    Delivery,
    DeliveryDetail,
    DeliveryUnit,
    DocumentType,
    EkModifier,
    Supplier,
    TaxRate,
)


class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = ['id', 'name', 'is_consumer']


class TaxRateSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaxRate
        fields = ['id', 'name', 'percent']


class DeliveryUnitSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliveryUnit
        fields = ['id', 'name', 'quantity']


class DocumentTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentType
        fields = ['id', 'name']


class DeliveryDetailSerializer(serializers.ModelSerializer):
    article_name = serializers.CharField(source='article.name', read_only=True)
    tax_rate_percent = serializers.DecimalField(
        source='tax_rate.percent', max_digits=5, decimal_places=2, read_only=True
    )
    line_net = serializers.DecimalField(max_digits=18, decimal_places=4, read_only=True)
    line_gross = serializers.DecimalField(max_digits=18, decimal_places=4, read_only=True)

    class Meta:
        model = DeliveryDetail
        fields = [
            'id', 'delivery', 'article', 'article_name', 'quantity',
            'unit_price', 'tax_rate', 'tax_rate_percent', 'delivery_unit',
            'line_net', 'line_gross',
        ]


class DeliverySerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    total_net = serializers.DecimalField(max_digits=18, decimal_places=4, read_only=True)
    total_gross = serializers.DecimalField(max_digits=18, decimal_places=4, read_only=True)
    details = DeliveryDetailSerializer(many=True, read_only=True)

    class Meta:
        model = Delivery
        fields = [
            'id', 'supplier', 'supplier_name', 'date', 'is_consumption',
            'comment', 'period', 'total_net', 'total_gross', 'details',
            'created_at', 'updated_at',
        ]


class EkModifierSerializer(serializers.ModelSerializer):
    class Meta:
        model = EkModifier
        fields = ['id', 'article', 'operator', 'modifier', 'period']


class DeliveryListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views (no nested details)."""
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    total_net = serializers.DecimalField(max_digits=18, decimal_places=4, read_only=True)
    total_gross = serializers.DecimalField(max_digits=18, decimal_places=4, read_only=True)

    class Meta:
        model = Delivery
        fields = [
            'id', 'supplier', 'supplier_name', 'date', 'is_consumption',
            'comment', 'period', 'total_net', 'total_gross',
            'created_at', 'updated_at',
        ]
