from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AttachmentViewSet,
    EkModifierViewSet,
    PartnerViewSet,
    StockMovementDetailViewSet,
    StockMovementViewSet,
    TaxRateViewSet,
)

router = DefaultRouter()
router.register(r'partners', PartnerViewSet)
router.register(r'tax-rates', TaxRateViewSet)
router.register(r'stock-movements', StockMovementViewSet, basename='stockmovement')
router.register(r'ek-modifiers', EkModifierViewSet, basename='ekmodifier')
router.register(r'attachments', AttachmentViewSet, basename='attachment')

# Nested: /api/stock-movements/{movement_pk}/details/
movement_detail_list = StockMovementDetailViewSet.as_view(
    {'get': 'list', 'post': 'create'})
movement_detail_detail = StockMovementDetailViewSet.as_view({
    'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'
})

# Nested: /api/stock-movements/{movement_pk}/attachments/
attachment_list = AttachmentViewSet.as_view({'get': 'list', 'post': 'create'})
attachment_detail = AttachmentViewSet.as_view({'get': 'retrieve', 'delete': 'destroy'})

urlpatterns = [
    path('', include(router.urls)),
    path('stock-movements/<int:movement_pk>/details/',
         movement_detail_list, name='movement-detail-list'),
    path('stock-movements/<int:movement_pk>/details/<int:pk>/',
         movement_detail_detail, name='movement-detail-detail'),
    path('stock-movements/<int:movement_pk>/attachments/',
         attachment_list, name='attachment-list'),
    path('stock-movements/<int:movement_pk>/attachments/<int:pk>/',
         attachment_detail, name='attachment-detail'),
]
