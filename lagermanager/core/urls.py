from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ConfigView, LocationViewSet, PeriodByDateView, PeriodViewSet

router = DefaultRouter()
router.register(r'periods', PeriodViewSet)
router.register(r'locations', LocationViewSet)

urlpatterns = [
    path('periods/by-date/', PeriodByDateView.as_view(), name='period-by-date'),
    path('', include(router.urls)),
    path('config/', ConfigView.as_view(), name='config'),
]
