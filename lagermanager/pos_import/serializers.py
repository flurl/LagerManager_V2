from rest_framework import serializers

from .models import Article, ArticleGroup, Recipe, WarehouseArticle, WarehouseUnit


class ArticleGroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = ArticleGroup
        fields = ['id', 'source_id', 'parent_source_id', 'name', 'period']


class ArticleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Article
        fields = ['id', 'source_id', 'name', 'group', 'sales_price', 'note', 'period']


class RecipeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Recipe
        fields = ['id', 'master_article', 'ingredient_article', 'quantity', 'is_recipe', 'period']


class WarehouseUnitSerializer(serializers.ModelSerializer):
    class Meta:
        model = WarehouseUnit
        fields = ['id', 'source_id', 'name', 'multiplier', 'base_unit', 'period']


class WarehouseArticleSerializer(serializers.ModelSerializer):
    article_name = serializers.CharField(source='article.name', read_only=True)

    class Meta:
        model = WarehouseArticle
        fields = [
            'id', 'source_id', 'article', 'article_name', 'supplier_source_id',
            'supplier_article_number', 'priority', 'unit', 'warehouse',
            'min_stock', 'max_stock', 'period',
        ]
