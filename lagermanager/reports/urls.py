from django.urls import path

from .views import (
    ConsumptionReportView,
    InventoryReportView,
    PurchasePriceView,
    StockLevelReportView,
    TotalDeliveriesReportView,
)

urlpatterns = [
    path('reports/stock-level/', StockLevelReportView.as_view(), name='report-stock-level'),
    path('reports/inventory/', InventoryReportView.as_view(), name='report-inventory'),
    path('reports/consumption/', ConsumptionReportView.as_view(), name='report-consumption'),
    path('reports/total-deliveries/', TotalDeliveriesReportView.as_view(), name='report-total-deliveries'),
    path('purchase-price/', PurchasePriceView.as_view(), name='purchase-price'),
]
