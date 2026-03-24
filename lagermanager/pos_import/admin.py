from django.contrib import admin

from .models import (
    Article,
    ArticleGroup,
    JournalCheckpoint,
    KellnerBasis,
    MwstGruppe,
    Recipe,
    WarehouseArticle,
    WarehouseUnit,
)

admin.site.register(JournalCheckpoint)
admin.site.register(MwstGruppe)
admin.site.register(KellnerBasis)
admin.site.register(ArticleGroup)
admin.site.register(Article)
admin.site.register(Recipe)
admin.site.register(WarehouseUnit)
admin.site.register(WarehouseArticle)
