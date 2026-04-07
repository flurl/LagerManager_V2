from django.urls import URLPattern, URLResolver, include, path
from rest_framework.routers import DefaultRouter

from .views import (
    BulkStockCountView,
    ExpandedArticleListView,
    ImportStockCountView,
    StockCountEntryViewSet,
)

router = DefaultRouter()
router.register(r'stock-count/entries', StockCountEntryViewSet, basename='stockcountentry')

urlpatterns: list[URLPattern | URLResolver] = [
    path('stock-count/articles/', ExpandedArticleListView.as_view(), name='stock-count-articles'),
    path('stock-count/entries/bulk/', BulkStockCountView.as_view(), name='stock-count-bulk'),
    path('stock-count/entries/import/', ImportStockCountView.as_view(), name='stock-count-import'),
    path('', include(router.urls)),
]
