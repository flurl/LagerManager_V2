from django.db.models import QuerySet
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Article, ArticleGroup, ArticleMeta, Recipe, WarehouseArticle, WarehouseUnit
from .serializers import (
    ArticleGroupSerializer,
    ArticleMetaSerializer,
    ArticleSerializer,
    RecipeSerializer,
    WarehouseArticleSerializer,
    WarehouseUnitSerializer,
)
from .services.mssql_import import run_import


class ArticleMetaViewSet(viewsets.ModelViewSet[ArticleMeta]):
    """CRUD for per-article metadata scoped to a period."""
    serializer_class = ArticleMetaSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self) -> QuerySet[ArticleMeta]:
        qs = ArticleMeta.objects.all()
        period_id = self.request.query_params.get('period_id')
        if period_id:
            qs = qs.filter(period_id=period_id)
        return qs


class ArticleGroupViewSet(viewsets.ReadOnlyModelViewSet[ArticleGroup]):
    serializer_class = ArticleGroupSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self) -> QuerySet[ArticleGroup]:
        qs = ArticleGroup.objects.all()
        period_id = self.request.query_params.get('period_id')
        if period_id:
            qs = qs.filter(period_id=period_id)
        return qs


class ArticleViewSet(viewsets.ReadOnlyModelViewSet[Article]):
    serializer_class = ArticleSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self) -> QuerySet[Article]:
        qs = Article.objects.all()
        period_id = self.request.query_params.get('period_id')
        if period_id:
            qs = qs.filter(period_id=period_id)
        return qs.select_related('period')


class RecipeViewSet(viewsets.ReadOnlyModelViewSet[Recipe]):
    serializer_class = RecipeSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self) -> QuerySet[Recipe]:
        qs = Recipe.objects.all()
        period_id = self.request.query_params.get('period_id')
        if period_id:
            qs = qs.filter(period_id=period_id)
        return qs


class WarehouseUnitViewSet(viewsets.ReadOnlyModelViewSet[WarehouseUnit]):
    serializer_class = WarehouseUnitSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self) -> QuerySet[WarehouseUnit]:
        qs = WarehouseUnit.objects.all()
        period_id = self.request.query_params.get('period_id')
        if period_id:
            qs = qs.filter(period_id=period_id)
        return qs


class WarehouseArticleViewSet(viewsets.ReadOnlyModelViewSet[WarehouseArticle]):
    serializer_class = WarehouseArticleSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self) -> QuerySet[WarehouseArticle]:
        qs = WarehouseArticle.objects.all()
        period_id = self.request.query_params.get('period_id')
        if period_id:
            qs = qs.filter(period_id=period_id)
        return qs.select_related('article')


class ImportRunView(APIView):
    """
    POST /api/import/run/
    Body: {period_id, host, database, user, password}
    Runs the MSSQL import synchronously; returns when complete.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        period_id = request.data.get('period_id')
        host = request.data.get('host', '')
        database = request.data.get('database', '')
        user = request.data.get('user', '')
        password = request.data.get('password', '')

        if period_id is None or not host or not database or not user:
            return Response(
                {'error': 'period_id, host, database, user are required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            summary = run_import(int(period_id), host, database, user, password)
            return Response({'status': 'ok', 'summary': summary})
        except Exception as exc:
            return Response(
                {'error': str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
