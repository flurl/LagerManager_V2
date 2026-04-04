from typing import Any

from rest_framework import serializers


class CommaSeparatedListField(serializers.Field):
    """Converts between a comma-separated string stored in the DB and a list in the API."""

    def to_representation(self, value: str) -> list[str]:
        if not value:
            return []
        return [item.strip() for item in value.split(',') if item.strip()]

    def to_internal_value(self, data: Any) -> str:
        if isinstance(data, list):
            return ','.join(str(item).strip() for item in data)
        if isinstance(data, str):
            return data
        raise serializers.ValidationError('Expected a list or comma-separated string.')
