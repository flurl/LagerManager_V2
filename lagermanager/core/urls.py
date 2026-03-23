from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import PeriodViewSet, WorkplaceViewSet

router = DefaultRouter()
router.register(r'periods', PeriodViewSet)
router.register(r'workplaces', WorkplaceViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
