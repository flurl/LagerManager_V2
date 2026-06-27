from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AddressViewSet,
    ConfigLogoView,
    ConfigView,
    DepartmentViewSet,
    LocationViewSet,
    MeView,
    PeriodByDateView,
    PeriodViewSet,
    VersionView,
    WzAddressSyncView,
)

router = DefaultRouter()
router.register(r'periods', PeriodViewSet)
router.register(r'locations', LocationViewSet)
router.register(r'departments', DepartmentViewSet)
router.register(r'addresses', AddressViewSet, basename='address')

urlpatterns = [
    # Explicit path must come before the router include so it isn't swallowed
    # by the router's addresses/{pk}/ pattern treating "sync-wz" as a pk.
    path('addresses/sync-wz/', WzAddressSyncView.as_view(), name='address-sync-wz'),
    path('periods/by-date/', PeriodByDateView.as_view(), name='period-by-date'),
    path('', include(router.urls)),
    path('config/', ConfigView.as_view(), name='config'),
    path('config/logo/', ConfigLogoView.as_view(), name='config-logo'),
    path('me/', MeView.as_view(), name='me'),
    path('version/', VersionView.as_view(), name='version'),
]
