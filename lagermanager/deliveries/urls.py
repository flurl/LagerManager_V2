from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    DeliveryUnitViewSet,
    DocumentTypeViewSet,
    EkModifierViewSet,
    PartnerViewSet,
    StockMovementDetailViewSet,
    StockMovementViewSet,
    TaxRateViewSet,
)

router = DefaultRouter()
router.register(r'partners', PartnerViewSet)
router.register(r'tax-rates', TaxRateViewSet)
router.register(r'delivery-units', DeliveryUnitViewSet)
router.register(r'stock-movements', StockMovementViewSet, basename='stockmovement')
router.register(r'document-types', DocumentTypeViewSet)
router.register(r'ek-modifiers', EkModifierViewSet, basename='ekmodifier')

# Nested: /api/stock-movements/{movement_pk}/details/
movement_detail_list = StockMovementDetailViewSet.as_view({'get': 'list', 'post': 'create'})
movement_detail_detail = StockMovementDetailViewSet.as_view({
    'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'
})

urlpatterns = [
    path('', include(router.urls)),
    path('stock-movements/<int:movement_pk>/details/', movement_detail_list, name='movement-detail-list'),
    path('stock-movements/<int:movement_pk>/details/<int:pk>/', movement_detail_detail, name='movement-detail-detail'),
]
