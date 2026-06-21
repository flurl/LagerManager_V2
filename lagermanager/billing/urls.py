from django.urls import URLPattern, URLResolver, include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AddressViewSet,
    BillingArticleViewSet,
    InvoiceViewSet,
    OfferViewSet,
    ReminderViewSet,
    WzAddressSyncView,
)

router = DefaultRouter()
router.register('addresses', AddressViewSet, basename='address')
router.register('billing-articles', BillingArticleViewSet, basename='billing-article')
router.register('offers', OfferViewSet, basename='offer')
router.register('invoices', InvoiceViewSet, basename='invoice')
router.register('reminders', ReminderViewSet, basename='reminder')

urlpatterns: list[URLPattern | URLResolver] = [
    # Explicit paths must come before the router include so they aren't swallowed
    # by the router's addresses/{pk}/ pattern treating "sync-wz" as a pk.
    path('addresses/sync-wz/', WzAddressSyncView.as_view(), name='address-sync-wz'),
    path('', include(router.urls)),
]
