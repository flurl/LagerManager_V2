from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import InitialInventoryViewSet, PhysicalCountViewSet, StockLevelViewSet

router = DefaultRouter()
router.register(r'stock-levels', StockLevelViewSet, basename='stocklevel')
router.register(r'initial-inventory', InitialInventoryViewSet, basename='initialinventory')
router.register(r'physical-counts', PhysicalCountViewSet, basename='physicalcount')

urlpatterns = [
    path('', include(router.urls)),
]
