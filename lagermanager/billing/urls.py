from django.urls import URLPattern, URLResolver, include, path
from rest_framework.routers import DefaultRouter

from .views import (
    BillingArticleViewSet,
    InvoiceViewSet,
    OfferViewSet,
    ReminderViewSet,
)

router = DefaultRouter()
router.register('billing-articles', BillingArticleViewSet, basename='billing-article')
router.register('offers', OfferViewSet, basename='offer')
router.register('invoices', InvoiceViewSet, basename='invoice')
router.register('reminders', ReminderViewSet, basename='reminder')

urlpatterns: list[URLPattern | URLResolver] = [
    path('', include(router.urls)),
]
