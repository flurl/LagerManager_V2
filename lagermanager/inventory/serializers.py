from rest_framework import serializers

from .models import InitialInventory, PhysicalCount, StockLevel


class StockLevelSerializer(serializers.ModelSerializer):
    article_name = serializers.CharField(source='article.name', read_only=True)

    class Meta:
        model = StockLevel
        fields = ['id', 'article', 'article_name', 'quantity', 'period', 'updated_at']


class InitialInventorySerializer(serializers.ModelSerializer):
    article_name = serializers.CharField(source='article.name', read_only=True)
    workplace_name = serializers.CharField(source='workplace.name', read_only=True)

    class Meta:
        model = InitialInventory
        fields = [
            'id', 'article', 'article_name', 'quantity',
            'workplace', 'workplace_name', 'period', 'updated_at',
        ]


class PhysicalCountSerializer(serializers.ModelSerializer):
    article_name = serializers.CharField(source='article.name', read_only=True)

    class Meta:
        model = PhysicalCount
        fields = ['id', 'date', 'article', 'article_name', 'quantity', 'period', 'updated_at']
