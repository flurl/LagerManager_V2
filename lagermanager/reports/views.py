from typing import cast

from core.permissions import require_perm
from core.services.purchase_price import get_purchase_price
from deliveries.models import StockMovement
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .services.consumption_report import (
    RevenueFilter,
    get_consumption_chart_data,
    get_consumption_totals,
)
from .services.inventory_report import get_inventory_report
from .services.stock_level_report import (
    get_current_stock_levels,
    get_stock_level_chart_data,
)
from .services.total_movements_report import DateGrouping, get_total_movements_report

_view_reports = require_perm('core.view_reports')


class StockLevelReportView(APIView):
    permission_classes = [IsAuthenticated, _view_reports]

    def get(self, request: Request) -> Response:
        period_id = request.query_params.get('period_id')
        if not period_id:
            return Response({'error': 'period_id required'}, status=status.HTTP_400_BAD_REQUEST)
        data = get_stock_level_chart_data(int(period_id))
        return Response(data)


class CurrentStockLevelReportView(APIView):
    permission_classes = [IsAuthenticated, _view_reports]

    def get(self, request: Request) -> Response:
        period_id = request.query_params.get('period_id')
        if not period_id:
            return Response({'error': 'period_id required'}, status=status.HTTP_400_BAD_REQUEST)
        data = get_current_stock_levels(int(period_id))
        return Response(data)


class InventoryReportView(APIView):
    permission_classes = [IsAuthenticated, _view_reports]

    def get(self, request: Request) -> Response:
        period_id = request.query_params.get('period_id')
        if not period_id:
            return Response({'error': 'period_id required'}, status=status.HTTP_400_BAD_REQUEST)
        data = get_inventory_report(int(period_id))
        return Response(data)


class ConsumptionReportView(APIView):
    permission_classes = [IsAuthenticated, _view_reports]

    def get(self, request: Request) -> Response:
        period_id = request.query_params.get('period_id')
        if not period_id:
            return Response({'error': 'period_id required'}, status=status.HTTP_400_BAD_REQUEST)
        data = get_consumption_chart_data(int(period_id))
        return Response(data)


class ConsumptionTotalsReportView(APIView):
    permission_classes = [IsAuthenticated, _view_reports]

    def get(self, request: Request) -> Response:
        period_id = request.query_params.get('period_id')
        if not period_id:
            return Response({'error': 'period_id required'}, status=status.HTTP_400_BAD_REQUEST)
        raw_revenue_filter = request.query_params.get('revenue_filter', 'all')
        if raw_revenue_filter not in ('all', 'umsatz', 'aufwand'):
            return Response({'error': 'invalid revenue_filter'}, status=status.HTTP_400_BAD_REQUEST)
        revenue_filter = cast(RevenueFilter, raw_revenue_filter)
        include_lm_data = request.query_params.get('include_lm_data', '1') != '0'
        show_table_code = request.query_params.get('show_table_code') == '1'
        data = get_consumption_totals(
            int(period_id),
            revenue_filter=revenue_filter,
            include_lm_data=include_lm_data,
            show_table_code=show_table_code,
        )
        return Response(data)


class TotalMovementsReportView(APIView):
    permission_classes = [IsAuthenticated, _view_reports]

    def get(self, request: Request) -> Response:
        period_id = request.query_params.get('period_id')
        if not period_id:
            return Response({'error': 'period_id required'}, status=status.HTTP_400_BAD_REQUEST)
        movement_type_raw = request.query_params.get('movement_type', StockMovement.Type.DELIVERY)
        if movement_type_raw in StockMovement.Type.values:
            movement_type = StockMovement.Type(movement_type_raw)
        else:
            movement_type = StockMovement.Type.DELIVERY
        date_grouping_raw = request.query_params.get('date_grouping')
        date_grouping: DateGrouping | None = None
        if date_grouping_raw is not None and date_grouping_raw in DateGrouping._value2member_map_:
            date_grouping = DateGrouping(date_grouping_raw)
        group_by_partner = request.query_params.get('group_by_partner', '').lower() in ('1', 'true')
        data = get_total_movements_report(
            int(period_id),
            movement_type=movement_type,
            date_grouping=date_grouping,
            group_by_partner=group_by_partner,
        )
        return Response(data)


class PurchasePriceView(APIView):
    permission_classes = [IsAuthenticated, _view_reports]

    def get(self, request: Request) -> Response:
        article_id = request.query_params.get('article')
        period_id = request.query_params.get('period_id')
        if not article_id or not period_id:
            return Response({'error': 'article and period_id required'}, status=status.HTTP_400_BAD_REQUEST)
        price = get_purchase_price(int(article_id), int(period_id))
        return Response({'article_id': article_id, 'period_id': period_id, 'purchase_price': str(price)})
