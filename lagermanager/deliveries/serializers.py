from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework.exceptions import ValidationError as DRFValidationError

from .models import (
    Attachment,
    EkModifier,
    Partner,
    PartnerAiInstruction,
    StockMovement,
    StockMovementDetail,
    TaxRate,
)


class PartnerAiInstructionSerializer(serializers.ModelSerializer[PartnerAiInstruction]):
    class Meta:
        model = PartnerAiInstruction
        fields = ['provider', 'instructions']


class PartnerSerializer(serializers.ModelSerializer[Partner]):
    ai_instructions = PartnerAiInstructionSerializer(many=True, required=False)

    class Meta:
        model = Partner
        fields = ['id', 'name', 'partner_type', 'ai_instructions']

    def create(self, validated_data: dict[str, Any]) -> Partner:
        ai_instructions: list[dict[str, Any]] = validated_data.pop('ai_instructions', [])
        partner = super().create(validated_data)
        for instr in ai_instructions:
            if instr.get('instructions'):
                PartnerAiInstruction.objects.create(partner=partner, **instr)
        return partner

    def update(self, instance: Partner, validated_data: dict[str, Any]) -> Partner:
        ai_instructions: list[dict[str, Any]] | None = validated_data.pop('ai_instructions', None)
        instance = super().update(instance, validated_data)
        if ai_instructions is not None:
            instance.ai_instructions.all().delete()
            for instr in ai_instructions:
                if instr.get('instructions'):
                    PartnerAiInstruction.objects.create(partner=instance, **instr)
        return instance


class TaxRateSerializer(serializers.ModelSerializer[TaxRate]):
    class Meta:
        model = TaxRate
        fields = ['id', 'name', 'percent']


class AttachmentSerializer(serializers.ModelSerializer["Attachment"]):
    class Meta:
        model = Attachment
        fields = [
            'id', 'stock_movement', 'file', 'original_filename',
            'source_filename', 'page_number', 'created_at',
        ]
        read_only_fields = [
            'id', 'stock_movement', 'original_filename',
            'source_filename', 'page_number', 'created_at',
        ]


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

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        # Build an unsaved instance to run model-level clean()
        instance = self.instance or StockMovement()
        for field, value in attrs.items():
            setattr(instance, field if not field.endswith('_id') else field, value)
        # Resolve FK id attributes expected by clean()
        if 'period' in attrs:
            instance.period = attrs['period']
        if 'date' in attrs:
            instance.date = attrs['date']
        try:
            instance.clean()
        except DjangoValidationError as exc:
            raise DRFValidationError(exc.message_dict) from exc
        return attrs


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
    attachment_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = StockMovement
        fields = [
            'id', 'partner', 'partner_name', 'date', 'movement_type',
            'comment', 'period', 'total_net', 'total_gross',
            'attachment_count', 'created_at', 'updated_at',
        ]
