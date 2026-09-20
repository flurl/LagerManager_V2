from typing import TYPE_CHECKING

from auditlog.registry import auditlog
from django.conf import settings
from django.db import models

if TYPE_CHECKING:
    from billing.models import CustomerLedgerEntry, Invoice, Offer, Payment
    from django.db.models.fields.related_descriptors import RelatedManager


# ---------------------------------------------------------------------------
# Customer
# ---------------------------------------------------------------------------

class Customer(models.Model):
    """
    Kunde — the party that owes money.

    A customer owns one or more Address rows (billing address, delivery address,
    …), one of which is the default_address used to prefill new documents.
    Offers and invoices carry an explicit FK to the customer so that later
    re-assigning an address to a different customer never re-attributes
    historic documents or their ledger entries.

    Rows created by the Wiffzack address sync carry a wz_source_id (the legacy
    adresse_id of the address they were created for) and map 1:1 to the synced
    address.  Locally-created customers leave wz_source_id=None.
    """

    wz_source_id = models.IntegerField(
        null=True, blank=True, unique=True,
        help_text='adresse_id of the Wiffzack address this customer was created for; '
                  'null for locally-created customers.',
    )
    customer_number = models.CharField(
        max_length=20, null=True, blank=True, unique=True, db_index=True,
        verbose_name='Kundennummer',
    )
    name = models.CharField(max_length=255)

    default_address = models.ForeignKey(
        'Address',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='+',
        verbose_name='Standardadresse',
    )

    # Optional overrides; fall back to the default address when empty.
    email = models.CharField(max_length=100, blank=True)
    telefon = models.CharField(max_length=50, blank=True)

    uid = models.CharField(max_length=50, blank=True, verbose_name='UID-Nummer')
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    if TYPE_CHECKING:
        addresses: RelatedManager["Address"]
        offers: RelatedManager["Offer"]
        invoices: RelatedManager["Invoice"]
        payments: RelatedManager["Payment"]
        ledger_entries: RelatedManager["CustomerLedgerEntry"]

    class Meta:
        ordering = ['name']
        verbose_name = 'Kunde'
        verbose_name_plural = 'Kunden'

    def __str__(self) -> str:
        if self.customer_number:
            return f'{self.customer_number} – {self.name}'
        return self.name or f'Kunde #{self.pk}'

    @property
    def display_name(self) -> str:
        """Single-line display name, falling back to the default address."""
        if self.name:
            return self.name
        if self.default_address_id and self.default_address:
            return self.default_address.display_name
        return f'Kunde #{self.pk}'

    @property
    def billing_email(self) -> str:
        """Preferred e-mail: the customer's own, else the default address's.

        Address.email is a legacy nullable CharField, so both None and '' must
        be treated as empty.
        """
        if self.email:
            return self.email
        if self.default_address_id and self.default_address:
            return self.default_address.email or ''
        return ''


class CustomerNumberSequence(models.Model):
    """
    Single-row global counter for auto-assigned customer numbers.
    allocate_customer_number()/allocate_customer_numbers() in
    services/numbering.py are the only code that should mutate last_value.
    Format: K0001, K0002, …
    """

    last_value = models.IntegerField(default=0)

    class Meta:
        verbose_name = 'Kunden-Nummernfolge'

    def __str__(self) -> str:
        return f'Kunden-Nummernfolge: {self.last_value}'


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

    customer = models.ForeignKey(
        Customer,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='addresses',
        verbose_name='Kunde',
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
        # Deliberately terser than display_name: prefers the company alone.
        if self.firma:
            return self.firma
        parts = [p for p in (self.vorname, self.nachname) if p]
        if parts:
            return ' '.join(parts)
        return self.postal_line or f'Adresse #{self.pk}'

    # -- Single-line labels -------------------------------------------------
    #
    # Every field below is nullable (legacy schema), so each label falls through
    # to the next-best thing it has.  "Adresse #<pk>" is the last resort only:
    # the primary key means nothing to a person, and it reaches e-mail subjects
    # and invoice lists, so it must never win while real data exists.

    @property
    def name_line(self) -> str:
        """Company and/or person, empty when the address carries no name."""
        parts = [p for p in (self.vorname, self.nachname) if p]
        name = ' '.join(parts)
        if self.firma and name:
            return f'{self.firma} ({name})'
        return self.firma or name or ''

    @property
    def postal_line(self) -> str:
        """Street and city, empty when neither is set."""
        city = ' '.join(p for p in (self.plz, self.ort) if p)
        return ', '.join(p for p in (self.strasse, city) if p)

    @property
    def has_name(self) -> bool:
        """False for a pure postal address, identified by its street instead."""
        return bool(self.name_line)

    @property
    def display_name(self) -> str:
        """Shortest label that still identifies the address.

        The name when there is one; otherwise the postal address, which beats
        an opaque row id for anyone reading an invoice list or an e-mail.
        """
        return self.name_line or self.postal_line or f'Adresse #{self.pk}'

    @property
    def postal_label(self) -> str:
        """Fullest single-line label: name *and* postal address.

        Used where one customer's addresses have to be told apart, since they
        usually share a name and differ only by street.
        """
        if self.name_line and self.postal_line:
            return f'{self.name_line}, {self.postal_line}'
        return self.display_name

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
auditlog.register(Customer)
