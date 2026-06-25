from auditlog.registry import auditlog
from django.conf import settings
from django.db import models


# ---------------------------------------------------------------------------
# Address
# ---------------------------------------------------------------------------

class Address(models.Model):
    """
    Customer/partner address master table.

    Rows imported from the Wiffzack POS system carry a wz_source_id (the legacy
    adresse_id).  Locally-created rows leave wz_source_id=None.  The sync service
    upserts by wz_source_id and never deletes, so FK references from documents always
    remain valid.
    """

    wz_source_id = models.IntegerField(
        null=True, blank=True, unique=True,
        help_text='adresse_id from adressen_basis in Wiffzack; null for locally-created addresses.',
    )

    # Name / company
    anrede = models.CharField(max_length=255, blank=True, null=True)
    vorname = models.CharField(max_length=50, blank=True, null=True)
    nachname = models.CharField(max_length=50, blank=True, null=True)
    firma = models.TextField(blank=True, null=True)
    abteilung = models.TextField(blank=True, null=True)

    # Contact / address
    strasse = models.CharField(max_length=100, blank=True, null=True)
    plz = models.CharField(max_length=10, blank=True, null=True)
    ort = models.CharField(max_length=50, blank=True, null=True)
    telefon = models.CharField(max_length=50, blank=True, null=True)
    email = models.CharField(max_length=50, blank=True, null=True)

    # Business details
    uid = models.TextField(blank=True, null=True, verbose_name='UID-Nummer')
    anmerkung = models.TextField(blank=True, null=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['nachname', 'vorname', 'firma']
        verbose_name = 'Adresse'
        verbose_name_plural = 'Adressen'

    def __str__(self) -> str:
        if self.firma:
            return self.firma
        parts = [p for p in (self.vorname, self.nachname) if p]
        return ' '.join(parts) if parts else f'Adresse #{self.pk}'

    @property
    def display_name(self) -> str:
        """Formatted single-line display name including company if set."""
        name_parts = [p for p in (self.vorname, self.nachname) if p]
        name = ' '.join(name_parts)
        if self.firma and name:
            return f'{self.firma} ({name})'
        return self.firma or name or f'Adresse #{self.pk}'

    def format_address_block(self) -> str:
        """Multi-line address block suitable for document headers."""
        lines: list[str] = []
        if self.anrede:
            lines.append(self.anrede)
        if self.firma:
            lines.append(self.firma)
        if self.abteilung:
            lines.append(self.abteilung)
        name_parts = [p for p in (self.vorname, self.nachname) if p]
        if name_parts:
            lines.append(' '.join(name_parts))
        if self.strasse:
            lines.append(self.strasse)
        plz_ort = ' '.join(p for p in (self.plz, self.ort) if p)
        if plz_ort:
            lines.append(plz_ort)
        return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Period
# ---------------------------------------------------------------------------

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
    """Per-user preferences: language, theme, and per-period color scheme."""

    class Theme(models.TextChoices):
        LIGHT = 'light', 'Light'
        DARK = 'dark', 'Dark'
        AUTO = 'auto', 'Auto'

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='preferences',
    )
    language = models.CharField(max_length=10, default='de')
    theme = models.CharField(max_length=10, choices=Theme.choices, default=Theme.AUTO)
    period_colors = models.JSONField(default=dict)  # {str(period_id): '#rrggbb'}

    class Meta:
        db_table = 'user_preferences'

    def __str__(self) -> str:
        return f'Preferences({self.user})'


auditlog.register(Address)
