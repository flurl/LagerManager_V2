from core.services.purchase_price import get_purchase_price
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .services.consumption_report import get_consumption_chart_data
from .services.inventory_report import get_inventory_report
from .services.stock_level_report import get_stock_level_chart_data
from .services.total_deliveries_report import get_total_deliveries_report


class StockLevelReportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        period_id = request.query_params.get('period_id')
        if not period_id:
            return Response({'error': 'period_id required'}, status=status.HTTP_400_BAD_REQUEST)
        data = get_stock_level_chart_data(int(period_id))
        return Response(data)


class InventoryReportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        period_id = request.query_params.get('period_id')
        if not period_id:
            return Response({'error': 'period_id required'}, status=status.HTTP_400_BAD_REQUEST)
        data = get_inventory_report(int(period_id))
        return Response(data)


class ConsumptionReportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        period_id = request.query_params.get('period_id')
        if not period_id:
            return Response({'error': 'period_id required'}, status=status.HTTP_400_BAD_REQUEST)
        data = get_consumption_chart_data(int(period_id))
        return Response(data)


class TotalDeliveriesReportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        period_id = request.query_params.get('period_id')
        if not period_id:
            return Response({'error': 'period_id required'}, status=status.HTTP_400_BAD_REQUEST)
        data = get_total_deliveries_report(int(period_id))
        return Response(data)


class PurchasePriceView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        article_id = request.query_params.get('article')
        period_id = request.query_params.get('period_id')
        if not article_id or not period_id:
            return Response({'error': 'article and period_id required'}, status=status.HTTP_400_BAD_REQUEST)
        price = get_purchase_price(int(article_id), int(period_id))
        return Response({'article_id': article_id, 'period_id': period_id, 'purchase_price': str(price)})
