from rest_framework import serializers

from .models import StockCountEntry


class StockCountEntrySerializer(serializers.ModelSerializer[StockCountEntry]):
    class Meta:
        model = StockCountEntry
        fields = [
            'id', 'count_date', 'article_id', 'article_name',
            'location_id', 'location_name', 'package_count', 'units_per_package', 'unit_count',
            'quantity', 'created_at',
        ]
        read_only_fields = ['id', 'quantity', 'created_at']


class ExpandedArticleSerializer(serializers.Serializer[dict]):  # type: ignore[type-arg]
    article_id = serializers.CharField()
    article_name = serializers.CharField()
    package_size = serializers.DecimalField(max_digits=10, decimal_places=4, allow_null=True)


class BulkEntrySerializer(serializers.Serializer[dict]):  # type: ignore[type-arg]
    article_id = serializers.CharField(max_length=100)
    article_name = serializers.CharField(max_length=200)
    package_count = serializers.IntegerField(min_value=0, default=0)
    units_per_package = serializers.IntegerField(min_value=0, default=0)
    unit_count = serializers.IntegerField(min_value=0, default=0)


class BulkStockCountSerializer(serializers.Serializer[dict]):  # type: ignore[type-arg]
    location_id = serializers.IntegerField()
    location_name = serializers.CharField(max_length=255)
    count_date = serializers.DateTimeField()
    entries = BulkEntrySerializer(many=True)
