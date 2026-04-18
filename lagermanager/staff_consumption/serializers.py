from typing import Any

from rest_framework import serializers

from .models import StaffConsumptionEntry


class StaffConsumptionEntrySerializer(
    serializers.ModelSerializer[StaffConsumptionEntry]
):
    class Meta:
        model = StaffConsumptionEntry
        fields = [
            "id",
            "consumption_date",
            "department_name",
            "article_id",
            "article_name",
            "count",
            "year_month",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class BulkConsumptionEntrySerializer(serializers.Serializer[dict[str, Any]]):
    article_id = serializers.CharField(max_length=100)
    article_name = serializers.CharField(max_length=200)
    count = serializers.IntegerField(min_value=1)


class BulkStaffConsumptionSerializer(serializers.Serializer[dict[str, Any]]):
    consumption_date = serializers.DateTimeField()
    department_name = serializers.CharField(max_length=255)
    year_month = serializers.CharField(max_length=7)
    entries = BulkConsumptionEntrySerializer(many=True)
