from django.urls import path

from .views import (
    ConsumptionReportView,
    ConsumptionTotalsReportView,
    InventoryReportView,
    PurchasePriceView,
    StockLevelReportView,
    TotalMovementsReportView,
)

urlpatterns = [
    path('reports/stock-level/', StockLevelReportView.as_view(), name='report-stock-level'),
    path('reports/inventory/', InventoryReportView.as_view(), name='report-inventory'),
    path('reports/consumption/', ConsumptionReportView.as_view(), name='report-consumption'),
    path('reports/consumption-totals/', ConsumptionTotalsReportView.as_view(), name='report-consumption-totals'),
    path('reports/total-movements/', TotalMovementsReportView.as_view(), name='report-total-movements'),
    path('purchase-price/', PurchasePriceView.as_view(), name='purchase-price'),
]
