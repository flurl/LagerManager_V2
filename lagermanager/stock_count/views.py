import datetime as dt
from typing import Any

from core.permissions import DjangoModelPermissionsWithView, require_perm
from django.db.models import Count, QuerySet
from django.db.models.functions import TruncDate
from django.utils import timezone
from inventory.models import InitialInventory
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import StockCountEntry
from .serializers import (
    BulkStockCountSerializer,
    ExpandedArticleSerializer,
    StockCountEntrySerializer,
)
from .services import (
    get_expanded_articles,
    import_stock_count_entries,
    import_stock_count_entries_for_date,
)

_view_stock_count = require_perm('stock_count.view_stockcountentry')
_add_stock_count = require_perm('stock_count.add_stockcountentry')


class ExpandedArticleListView(APIView):
    permission_classes = [IsAuthenticated, _view_stock_count]

    def get(self, request: Request) -> Response:
        period_id = request.query_params.get('period_id')
        if not period_id:
            return Response({'error': 'period_id required'}, status=status.HTTP_400_BAD_REQUEST)
        include_base = request.query_params.get('include_base', 'true').lower() != 'false'
        articles = get_expanded_articles(int(period_id), include_base=include_base)
        serializer = ExpandedArticleSerializer(articles, many=True)  # type: ignore[arg-type]
        return Response(serializer.data)


class BulkStockCountView(APIView):
    permission_classes = [IsAuthenticated, _add_stock_count]

    def post(self, request: Request) -> Response:
        serializer = BulkStockCountSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        location_id: int = data['location_id']
        location_name: str = data['location_name']
        count_date = data['count_date']

        saved: list[int] = []
        for entry in data['entries']:
            obj, _ = StockCountEntry.objects.update_or_create(
                article_id=entry['article_id'],
                location_id=location_id,
                count_date=count_date,
                defaults={
                    'article_name': entry['article_name'],
                    'location_name': location_name,
                    'package_count': entry['package_count'],
                    'units_per_package': entry['units_per_package'],
                    'unit_count': entry['unit_count'],
                },
            )
            saved.append(obj.pk)

        return Response({'saved': len(saved)}, status=status.HTTP_200_OK)


class ImportStockCountView(APIView):
    permission_classes = [IsAuthenticated, _add_stock_count]

    def post(self, request: Request) -> Response:
        force = bool(request.data.get('force', False))
        cumulative_date = request.data.get('cumulative_date')

        if cumulative_date:
            result: dict[str, Any] = import_stock_count_entries_for_date(cumulative_date, force=force)
        else:
            entry_ids = request.data.get('entry_ids')
            if not entry_ids or not isinstance(entry_ids, list):
                return Response({'error': 'entry_ids required'}, status=status.HTTP_400_BAD_REQUEST)
            result = import_stock_count_entries(entry_ids, force=force)

        if result.get('status') == 'conflict':
            return Response(result, status=status.HTTP_409_CONFLICT)
        if result.get('status') == 'error':
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
        return Response(result, status=status.HTTP_200_OK)


class FromInitialInventoryView(APIView):
    permission_classes = [IsAuthenticated, _add_stock_count]

    def post(self, request: Request) -> Response:
        location_ids = request.data.get('location_ids')
        count_date_str = request.data.get('count_date')
        period_id = request.data.get('period_id')

        if not location_ids or not isinstance(location_ids, list):
            return Response({'error': 'location_ids required'}, status=status.HTTP_400_BAD_REQUEST)
        if not count_date_str:
            return Response({'error': 'count_date required'}, status=status.HTTP_400_BAD_REQUEST)
        if not period_id:
            return Response({'error': 'period_id required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            count_date = dt.datetime.fromisoformat(str(count_date_str))
            if count_date.tzinfo is None:
                count_date = timezone.make_aware(count_date)
        except (ValueError, TypeError):
            return Response({'error': 'Invalid count_date'}, status=status.HTTP_400_BAD_REQUEST)

        initial_items = (
            InitialInventory.objects
            .select_related('article', 'location')
            .filter(location_id__in=location_ids, period_id=period_id)
        )

        created = 0
        updated = 0
        for item in initial_items:
            _, was_created = StockCountEntry.objects.update_or_create(
                article_id=str(item.article.source_id),
                location_id=item.location_id,
                count_date=count_date,
                defaults={
                    'article_name': item.article.name,
                    'location_name': item.location.name,
                    'package_count': 0,
                    'units_per_package': 0,
                    'unit_count': int(round(item.quantity)),
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1

        return Response({'created': created, 'updated': updated})


class StockCountEntryViewSet(viewsets.ModelViewSet[StockCountEntry]):
    serializer_class = StockCountEntrySerializer
    permission_classes = [IsAuthenticated, DjangoModelPermissionsWithView]
    pagination_class = None

    def get_queryset(self) -> QuerySet[StockCountEntry]:
        qs = StockCountEntry.objects.all()
        location_id = self.request.query_params.get('location_id')
        count_date = self.request.query_params.get('count_date')
        if location_id:
            qs = qs.filter(location_id=location_id)
        if count_date:
            qs = qs.filter(count_date__date=count_date)
        return qs

    @action(detail=False, methods=['get'], url_path='dates')
    def dates(self, request: Request) -> Response:
        qs = (
            StockCountEntry.objects
            .annotate(day=TruncDate('count_date'))
            .values('day', 'location_id', 'location_name')
            .annotate(count=Count('id'))
            .order_by('-day', 'location_name')
        )
        return Response(list(qs))

    @action(detail=False, methods=['delete'], url_path='by-day')
    def by_day(self, request: Request) -> Response:
        day = request.query_params.get('day')
        location_id = request.query_params.get('location_id')
        if not day or not location_id:
            return Response(
                {'error': 'day and location_id required'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        count, _ = StockCountEntry.objects.filter(
            count_date__date=day, location_id=location_id,
        ).delete()
        return Response({'deleted': count})
