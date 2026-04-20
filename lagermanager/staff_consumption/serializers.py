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


# --- Import serializers ---

class ImportEntrySerializer(serializers.Serializer[dict[str, Any]]):
    """A single resolved article line — article PK and tax rate PK are resolved by the frontend."""

    article_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)
    tax_rate_id = serializers.IntegerField()


class ImportDepartmentMappingSerializer(serializers.Serializer[dict[str, Any]]):
    department_name = serializers.CharField()
    partner_id = serializers.IntegerField()
    entries = ImportEntrySerializer(many=True)


class StaffConsumptionImportRequestSerializer(serializers.Serializer[dict[str, Any]]):
    year_month = serializers.CharField(max_length=7)
    mappings = ImportDepartmentMappingSerializer(many=True)
