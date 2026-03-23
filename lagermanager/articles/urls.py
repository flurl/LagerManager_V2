from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    ArticleGroupViewSet,
    ArticleViewSet,
    EkModifierViewSet,
    RecipeViewSet,
    WarehouseArticleViewSet,
    WarehouseUnitViewSet,
)

router = DefaultRouter()
router.register(r'articles', ArticleViewSet, basename='article')
router.register(r'article-groups', ArticleGroupViewSet, basename='articlegroup')
router.register(r'recipes', RecipeViewSet, basename='recipe')
router.register(r'warehouse-articles', WarehouseArticleViewSet, basename='warehousearticle')
router.register(r'warehouse-units', WarehouseUnitViewSet, basename='warehouseunit')
router.register(r'ek-modifiers', EkModifierViewSet, basename='ekmodifier')

urlpatterns = [
    path('', include(router.urls)),
]
