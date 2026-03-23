from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from .models import (
    Article,
    ArticleGroup,
    EkModifier,
    Recipe,
    WarehouseArticle,
    WarehouseUnit,
)
from .serializers import (
    ArticleGroupSerializer,
    ArticleSerializer,
    EkModifierSerializer,
    RecipeSerializer,
    WarehouseArticleSerializer,
    WarehouseUnitSerializer,
)


class ArticleViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ArticleSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Article.objects.all()
        period_id = self.request.query_params.get('period_id')
        if period_id:
            qs = qs.filter(period_id=period_id)
        return qs.select_related('period')


class ArticleGroupViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ArticleGroupSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = ArticleGroup.objects.all()
        period_id = self.request.query_params.get('period_id')
        if period_id:
            qs = qs.filter(period_id=period_id)
        return qs


class RecipeViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = RecipeSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Recipe.objects.all()
        period_id = self.request.query_params.get('period_id')
        if period_id:
            qs = qs.filter(period_id=period_id)
        return qs


class WarehouseArticleViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = WarehouseArticleSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = WarehouseArticle.objects.all()
        period_id = self.request.query_params.get('period_id')
        if period_id:
            qs = qs.filter(period_id=period_id)
        return qs.select_related('article')


class WarehouseUnitViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = WarehouseUnitSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = WarehouseUnit.objects.all()
        period_id = self.request.query_params.get('period_id')
        if period_id:
            qs = qs.filter(period_id=period_id)
        return qs


class EkModifierViewSet(viewsets.ModelViewSet):
    serializer_class = EkModifierSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = EkModifier.objects.all()
        period_id = self.request.query_params.get('period_id')
        if period_id:
            qs = qs.filter(period_id=period_id)
        return qs
