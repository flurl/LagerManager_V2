from rest_framework import serializers

from .models import (
    DocumentType,
    EkModifier,
    Partner,
    StockMovement,
    StockMovementDetail,
    TaxRate,
)


class PartnerSerializer(serializers.ModelSerializer[Partner]):
    class Meta:
        model = Partner
        fields = ['id', 'name', 'partner_type']


class TaxRateSerializer(serializers.ModelSerializer[TaxRate]):
    class Meta:
        model = TaxRate
        fields = ['id', 'name', 'percent']


class DocumentTypeSerializer(serializers.ModelSerializer[DocumentType]):
    class Meta:
        model = DocumentType
        fields = ['id', 'name']


class StockMovementDetailSerializer(serializers.ModelSerializer[StockMovementDetail]):
    article_name = serializers.CharField(source='article.name', read_only=True)
    tax_rate_percent = serializers.DecimalField(
        source='tax_rate.percent', max_digits=5, decimal_places=2, read_only=True
    )
    line_net = serializers.DecimalField(
        max_digits=18, decimal_places=4, read_only=True)
    line_gross = serializers.DecimalField(
        max_digits=18, decimal_places=4, read_only=True)

    class Meta:
        model = StockMovementDetail
        fields = [
            'id', 'stock_movement', 'article', 'article_name', 'quantity',
            'unit_price', 'tax_rate', 'tax_rate_percent',
            'line_net', 'line_gross',
        ]


class StockMovementSerializer(serializers.ModelSerializer[StockMovement]):
    partner_name = serializers.CharField(source='partner.name', read_only=True)
    total_net = serializers.DecimalField(
        max_digits=18, decimal_places=4, read_only=True)
    total_gross = serializers.DecimalField(
        max_digits=18, decimal_places=4, read_only=True)
    details = StockMovementDetailSerializer(many=True, read_only=True)

    class Meta:
        model = StockMovement
        fields = [
            'id', 'partner', 'partner_name', 'date', 'movement_type',
            'comment', 'period', 'total_net', 'total_gross', 'details',
            'created_at', 'updated_at',
        ]


class EkModifierSerializer(serializers.ModelSerializer[EkModifier]):
    class Meta:
        model = EkModifier
        fields = ['id', 'article', 'operator', 'modifier', 'period']


class StockMovementListSerializer(serializers.ModelSerializer[StockMovement]):
    """Lightweight serializer for list views (no nested details)."""
    partner_name = serializers.CharField(source='partner.name', read_only=True)
    total_net = serializers.DecimalField(
        max_digits=18, decimal_places=4, read_only=True)
    total_gross = serializers.DecimalField(
        max_digits=18, decimal_places=4, read_only=True)

    class Meta:
        model = StockMovement
        fields = [
            'id', 'partner', 'partner_name', 'date', 'movement_type',
            'comment', 'period', 'total_net', 'total_gross',
            'created_at', 'updated_at',
        ]
