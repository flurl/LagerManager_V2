from rest_framework import serializers

from .models import Location, Period


class PeriodSerializer(serializers.ModelSerializer):
    class Meta:
        model = Period
        fields: list[str] = ['id', 'name', 'checkpoint_year', 'start', 'end']


class LocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Location
        fields: list[str] = ['id', 'name']
