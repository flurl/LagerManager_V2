from rest_framework import serializers

from .models import Period, Workplace


class PeriodSerializer(serializers.ModelSerializer):
    class Meta:
        model = Period
        fields = ['id', 'name', 'checkpoint_year', 'start', 'end']


class WorkplaceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Workplace
        fields = ['id', 'name', 'default_shift_duration']
