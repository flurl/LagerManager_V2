from django.db.models import QuerySet
from rest_framework import status, viewsets
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
from .services import get_expanded_articles


class ExpandedArticleListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        period_id = request.query_params.get('period_id')
        if not period_id:
            return Response({'error': 'period_id required'}, status=status.HTTP_400_BAD_REQUEST)
        include_base = request.query_params.get('include_base', 'true').lower() != 'false'
        articles = get_expanded_articles(int(period_id), include_base=include_base)
        serializer = ExpandedArticleSerializer(articles, many=True)  # type: ignore[arg-type]
        return Response(serializer.data)


class BulkStockCountView(APIView):
    permission_classes = [IsAuthenticated]

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
                    'quantity': entry['quantity'],
                },
            )
            saved.append(obj.pk)

        return Response({'saved': len(saved)}, status=status.HTTP_200_OK)


class StockCountEntryViewSet(viewsets.ModelViewSet[StockCountEntry]):
    serializer_class = StockCountEntrySerializer
    permission_classes = [IsAuthenticated]
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
