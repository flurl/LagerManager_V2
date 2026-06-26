from typing import Any

from rest_framework import serializers

from .models import Address, Department, Location, Period, UserPreferences


class PeriodSerializer(serializers.ModelSerializer):
    class Meta:
        model = Period
        fields: list[str] = ['id', 'name', 'checkpoint_year', 'start', 'end']


class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields: list[str] = ['id', 'name']


class LocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Location
        fields: list[str] = ['id', 'name']


class UserPreferencesSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserPreferences
        fields: list[str] = ['language', 'theme', 'period_colors']


class AddressSerializer(serializers.ModelSerializer[Address]):
    display_name = serializers.CharField(read_only=True)

    class Meta:
        model = Address
        fields = [
            'id', 'wz_source_id', 'display_name',
            'anrede', 'vorname', 'nachname', 'firma', 'abteilung',
            'strasse', 'plz', 'ort', 'telefon', 'email', 'uid', 'anmerkung',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'wz_source_id', 'display_name', 'created_at', 'updated_at']


class SyncWzSerializer(serializers.Serializer[Any]):
    """Request body for WZ address sync."""
    host = serializers.CharField()
    database = serializers.CharField()
    user = serializers.CharField()
    password = serializers.CharField()
