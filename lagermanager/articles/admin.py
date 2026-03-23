from django.contrib import admin

from .models import (
    Article,
    ArticleGroup,
    EkModifier,
    Recipe,
    WarehouseArticle,
    WarehouseUnit,
)

admin.site.register(Article)
admin.site.register(ArticleGroup)
admin.site.register(Recipe)
admin.site.register(WarehouseArticle)
admin.site.register(WarehouseUnit)
admin.site.register(EkModifier)
