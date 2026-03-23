from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    DeliveryDetailViewSet,
    DeliveryUnitViewSet,
    DeliveryViewSet,
    DocumentTypeViewSet,
    SupplierViewSet,
    TaxRateViewSet,
)

router = DefaultRouter()
router.register(r'suppliers', SupplierViewSet)
router.register(r'tax-rates', TaxRateViewSet)
router.register(r'delivery-units', DeliveryUnitViewSet)
router.register(r'deliveries', DeliveryViewSet, basename='delivery')
router.register(r'document-types', DocumentTypeViewSet)

# Nested: /api/deliveries/{delivery_pk}/details/
delivery_detail_list = DeliveryDetailViewSet.as_view({'get': 'list', 'post': 'create'})
delivery_detail_detail = DeliveryDetailViewSet.as_view({
    'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'
})

urlpatterns = [
    path('', include(router.urls)),
    path('deliveries/<int:delivery_pk>/details/', delivery_detail_list, name='delivery-detail-list'),
    path('deliveries/<int:delivery_pk>/details/<int:pk>/', delivery_detail_detail, name='delivery-detail-detail'),
]
