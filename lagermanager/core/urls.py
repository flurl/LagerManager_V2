from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ConfigView, PeriodViewSet, WorkplaceViewSet

router = DefaultRouter()
router.register(r'periods', PeriodViewSet)
router.register(r'workplaces', WorkplaceViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('config/', ConfigView.as_view(), name='config'),
]
