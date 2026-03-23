from django.contrib import admin

from .models import JournalCheckpoint, KellnerBasis, MwstGruppe

admin.site.register(JournalCheckpoint)
admin.site.register(MwstGruppe)
admin.site.register(KellnerBasis)
