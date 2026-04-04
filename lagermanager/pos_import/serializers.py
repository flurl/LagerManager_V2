from rest_framework import serializers

from core.fields import CommaSeparatedListField

from .models import Article, ArticleGroup, ArticleMeta, Recipe, WarehouseArticle, WarehouseUnit


class ArticleMetaSerializer(serializers.ModelSerializer[ArticleMeta]):
    sub_articles = CommaSeparatedListField()

    class Meta:
        model = ArticleMeta
        fields = ['id', 'source_id', 'period', 'is_hidden', 'sub_articles', 'extra']


class ArticleGroupSerializer(serializers.ModelSerializer[ArticleGroup]):
    class Meta:
        model = ArticleGroup
        fields = ['id', 'source_id', 'parent_source_id', 'name', 'period']


class ArticleSerializer(serializers.ModelSerializer[Article]):
    class Meta:
        model = Article
        fields = ['id', 'source_id', 'name', 'group', 'sales_price', 'note', 'period']


class RecipeSerializer(serializers.ModelSerializer[Recipe]):
    class Meta:
        model = Recipe
        fields = ['id', 'master_article', 'ingredient_article', 'quantity', 'is_recipe', 'period']


class WarehouseUnitSerializer(serializers.ModelSerializer[WarehouseUnit]):
    class Meta:
        model = WarehouseUnit
        fields = ['id', 'source_id', 'name', 'multiplier', 'base_unit', 'period']


class WarehouseArticleSerializer(serializers.ModelSerializer[WarehouseArticle]):
    article_name = serializers.CharField(source='article.name', read_only=True)

    class Meta:
        model = WarehouseArticle
        fields = [
            'id', 'source_id', 'article', 'article_name', 'source_article_id',
            'supplier_source_id', 'supplier_article_number', 'priority', 'unit', 'warehouse',
            'min_stock', 'max_stock', 'period',
        ]
