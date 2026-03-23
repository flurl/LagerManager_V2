from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from .models import Period, Workplace
from .serializers import PeriodSerializer, WorkplaceSerializer


class PeriodViewSet(viewsets.ModelViewSet):
    queryset = Period.objects.all()
    serializer_class = PeriodSerializer
    permission_classes = [IsAuthenticated]


class WorkplaceViewSet(viewsets.ModelViewSet):
    queryset = Workplace.objects.all()
    serializer_class = WorkplaceSerializer
    permission_classes = [IsAuthenticated]
