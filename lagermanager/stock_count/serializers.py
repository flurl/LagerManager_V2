from rest_framework import serializers

from .models import StockCountEntry


class StockCountEntrySerializer(serializers.ModelSerializer[StockCountEntry]):
    class Meta:
        model = StockCountEntry
        fields = [
            'id', 'count_date', 'article_id', 'article_name',
            'location_id', 'location_name', 'quantity', 'period_id_value', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class ExpandedArticleSerializer(serializers.Serializer[dict]):  # type: ignore[type-arg]
    article_id = serializers.CharField()
    article_name = serializers.CharField()


class BulkEntrySerializer(serializers.Serializer[dict]):  # type: ignore[type-arg]
    article_id = serializers.CharField(max_length=100)
    article_name = serializers.CharField(max_length=200)
    quantity = serializers.DecimalField(max_digits=10, decimal_places=3)


class BulkStockCountSerializer(serializers.Serializer[dict]):  # type: ignore[type-arg]
    period_id = serializers.IntegerField()
    location_id = serializers.IntegerField()
    location_name = serializers.CharField(max_length=255)
    count_date = serializers.DateTimeField()
    entries = BulkEntrySerializer(many=True)
