from django.db.models.query import QuerySet
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from .models import Period, Workplace
from .serializers import PeriodSerializer, WorkplaceSerializer


class PeriodViewSet(viewsets.ModelViewSet):
    queryset: QuerySet[Period, Period] = Period.objects.all()
    serializer_class = PeriodSerializer
    permission_classes: list[type[IsAuthenticated]] = [IsAuthenticated]


class WorkplaceViewSet(viewsets.ModelViewSet):
    queryset: QuerySet[Workplace, Workplace] = Workplace.objects.all()
    serializer_class = WorkplaceSerializer
    permission_classes: list[type[IsAuthenticated]] = [IsAuthenticated]
