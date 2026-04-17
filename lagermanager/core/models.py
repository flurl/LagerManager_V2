from django.conf import settings
from django.db import models


class Period(models.Model):
    """Abrechnungsperiode (Geschäftsjahr)"""
    name = models.CharField(
        max_length=255, db_column='periode_bezeichnung')
    checkpoint_year = models.IntegerField(
        null=True, blank=True, db_column='periode_checkpoint_jahr')
    start = models.DateTimeField(
        db_column='periode_start')
    end = models.DateTimeField(
        db_column='periode_ende')

    class Meta:
        db_table = 'perioden'
        ordering = ['-start']

    def __str__(self) -> str:
        return self.name


class GlobalPermission(models.Model):
    """
    A virtual model that exists solely to hold custom permissions that don't
    belong to any specific model — e.g. 'can view reports', 'can run import'.

    Django requires every permission to be attached to a content type (model).
    Using a dedicated model here (rather than bolting permissions onto an
    unrelated model like Period) keeps things explicit and prevents unrelated
    models from accumulating permissions over time.

    managed = False  → no database table is created.
    default_permissions = ()  → suppresses the auto-generated add/change/delete/view
                                permissions that Django would otherwise create for
                                this model, since we only want our explicit ones.
    """

    class Meta:
        managed = False
        default_permissions = ()
        permissions = [
            ('view_reports', 'Can view reports'),
            ('run_import', 'Can run POS data import'),
        ]


class Department(models.Model):
    """Abteilung / Kostenstelle"""
    name = models.CharField(max_length=255)

    class Meta:
        db_table = 'departments'
        ordering = ['name']

    def __str__(self) -> str:
        return self.name


class Location(models.Model):
    """Standort / Arbeitsplatz / Bar / Lager / Abteilung"""
    name = models.CharField(
        max_length=255, db_column='arp_bezeichnung')

    class Meta:
        db_table = 'locations'
        ordering = ['name']

    def __str__(self) -> str:
        return self.name


class UserPreferences(models.Model):
    """Per-user preferences: language and per-period color scheme."""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='preferences',
    )
    language = models.CharField(max_length=10, default='de')
    period_colors = models.JSONField(default=dict)  # {str(period_id): '#rrggbb'}

    class Meta:
        db_table = 'user_preferences'

    def __str__(self) -> str:
        return f'Preferences({self.user})'
