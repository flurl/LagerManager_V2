from rest_framework import serializers

from .models import Department, Location, Period, UserPreferences


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
