from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ConfigView, LocationViewSet, PeriodViewSet

router = DefaultRouter()
router.register(r'periods', PeriodViewSet)
router.register(r'locations', LocationViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('config/', ConfigView.as_view(), name='config'),
]
