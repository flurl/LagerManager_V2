from django.urls import URLPattern, URLResolver, include, path
from rest_framework.routers import DefaultRouter

from .views import (
    BillingArticleViewSet,
    DocumentAttachmentKindsView,
    InvoiceTemplateViewSet,
    InvoiceViewSet,
    OfferViewSet,
    PaymentViewSet,
    ReminderViewSet,
)

router = DefaultRouter()
router.register('billing-articles', BillingArticleViewSet, basename='billing-article')
router.register('offers', OfferViewSet, basename='offer')
router.register('invoices', InvoiceViewSet, basename='invoice')
router.register('invoice-templates', InvoiceTemplateViewSet, basename='invoice-template')
router.register('reminders', ReminderViewSet, basename='reminder')
router.register('payments', PaymentViewSet, basename='payment')

urlpatterns: list[URLPattern | URLResolver] = [
    path('document-attachment-kinds/', DocumentAttachmentKindsView.as_view(),
         name='document-attachment-kinds'),
    path('', include(router.urls)),
]
