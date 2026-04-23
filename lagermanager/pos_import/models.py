"""
POS imported models — all tables that come from the MSSQL Wiffzack system.
These are write-only from the import service; read-only via API.
"""
from core.models import Period
from django.db import models


class JournalCheckpoint(models.Model):
    source_id = models.IntegerField(db_column='checkpoint_id')
    typ = models.CharField(max_length=10, db_column='checkpoint_typ')
    datum = models.DateTimeField(db_column='checkpoint_datum')
    anmerkung = models.TextField(
        null=True, blank=True, db_column='checkpoint_anmerkung')
    info = models.TextField(db_column='checkpoint_info')
    num = models.IntegerField(db_column='checkpoint_num')
    kassenbuch_verarbeitet = models.BooleanField(
        db_column='checkpoint_kassenbuch_verarbeitet')
    period = models.ForeignKey(
        Period, on_delete=models.CASCADE, db_column='checkpoint_periode')

    class Meta:
        db_table = 'journal_checkpoints'
        unique_together = [('source_id', 'period')]

    def __str__(self) -> str:
        return f"CP {self.source_id}"


class TischBereich(models.Model):
    source_id = models.IntegerField(db_column='tischbereich_id')
    kurz_name = models.CharField(
        max_length=8, db_column='tischbereich_kurzName')
    name = models.CharField(max_length=50, db_column='tischbereich_name')
    ist_gast_bereich = models.BooleanField(
        db_column='tischbereich_istGastBereich')
    min_nummer = models.IntegerField(db_column='tischbereich_minNummer')
    max_nummer = models.IntegerField(db_column='tischbereich_maxNummer')
    ist_aufwand = models.BooleanField(db_column='tischbereich_istAufwand')
    ist_sammelbereich = models.BooleanField(
        db_column='tischbereich_istSammelbereich')
    benoetigt_adresse = models.BooleanField(
        db_column='tischbereich_benoetigtAdresse')
    rechnungs_anzahl = models.IntegerField(
        db_column='tischbereich_rechnungsAnzahl')
    extern = models.BooleanField(db_column='tischbereich_extern')
    ist_ordercard_bereich = models.BooleanField(
        db_column='tischbereich_istOrdercardBereich')
    vorgangsart = models.IntegerField(
        null=True, blank=True, db_column='tischbereich_vorgangsart')
    temp = models.BooleanField(db_column='tischbereich_temp')
    verstecke_sammeltisch = models.BooleanField(
        db_column='tischbereich_versteckeSammeltisch')
    sammeltisch_optional = models.BooleanField(
        db_column='tischbereich_sammeltischOptional')
    rksv = models.BooleanField(db_column='tischbereich_rksv')
    period = models.ForeignKey(
        Period, on_delete=models.CASCADE, db_column='tischbereich_periode')

    class Meta:
        db_table = 'tische_bereiche'
        unique_together = [('source_id', 'period')]


class TischAktiv(models.Model):
    source_id = models.IntegerField(db_column='tisch_id')
    bereich = models.IntegerField(db_column='tisch_bereich')
    pri_nummer = models.IntegerField(db_column='tisch_pri_nummer')
    sek_nummer = models.IntegerField(db_column='tisch_sek_nummer')
    gast = models.IntegerField(null=True, blank=True, db_column='tisch_gast')
    dt_erstellung = models.DateTimeField(db_column='tisch_dt_erstellung')
    dt_aktivitaet = models.DateTimeField(db_column='tisch_dt_aktivitaet')
    kellner = models.IntegerField(db_column='tisch_kellner')
    fertig = models.BooleanField(db_column='tisch_fertig')
    zahlungsart = models.IntegerField(
        null=True, blank=True, db_column='tisch_zahlungsart')
    rechnung = models.IntegerField(
        null=True, blank=True, db_column='tisch_rechnung')
    dt_zusatz = models.DateTimeField(
        null=True, blank=True, db_column='tisch_dt_zusatz')
    adresse = models.IntegerField(
        null=True, blank=True, db_column='tisch_adresse')
    kellner_abrechnung = models.IntegerField(
        null=True, blank=True, db_column='tisch_kellner_abrechnung')
    client = models.CharField(max_length=50, null=True,
                              blank=True, db_column='tisch_client')
    reservierung = models.IntegerField(
        null=True, blank=True, db_column='tisch_reservierung')
    reservierung_check = models.BooleanField(
        db_column='tisch_reservierung_check')
    zusatz_text = models.TextField(
        null=True, blank=True, db_column='tisch_zusatz_text')
    checkpoint_tag = models.IntegerField(
        null=True, blank=True, db_column='checkpoint_tag')
    checkpoint_monat = models.IntegerField(
        null=True, blank=True, db_column='checkpoint_monat')
    checkpoint_jahr = models.IntegerField(
        null=True, blank=True, db_column='checkpoint_jahr')
    externer_beleg = models.BooleanField(db_column='tisch_externer_beleg')
    period = models.ForeignKey(
        Period, on_delete=models.CASCADE, db_column='tisch_periode')

    class Meta:
        db_table = 'tische_aktiv'
        unique_together = [('source_id', 'period')]
        indexes = [models.Index(fields=['checkpoint_tag'],
                                name='tische_aktiv_chkpt_tag_idx')]


class TischBon(models.Model):
    source_id = models.IntegerField(db_column='tisch_bon_id')
    dt_erstellung = models.DateTimeField(db_column='tisch_bon_dt_erstellung')
    tisch = models.IntegerField(db_column='tisch_bon_tisch')
    kellner = models.IntegerField(db_column='tisch_bon_kellner')
    client = models.CharField(max_length=50, db_column='tisch_bon_client')
    typ = models.IntegerField(db_column='tisch_bon_typ')
    bestellkarte = models.IntegerField(
        null=True, blank=True, db_column='tisch_bon_bestellkarte')
    vorgangsart = models.IntegerField(
        null=True, blank=True, db_column='tisch_bon_vorgangsart')
    period = models.ForeignKey(
        Period, on_delete=models.CASCADE, db_column='tisch_bon_periode')

    class Meta:
        db_table = 'tische_bons'
        unique_together = [('source_id', 'period')]


class TischBonDetail(models.Model):
    source_id = models.IntegerField(db_column='tisch_bondetail_id')
    bon = models.IntegerField(db_column='tisch_bondetail_bon')
    master_id = models.IntegerField(
        null=True, blank=True, db_column='tisch_bondetail_master_id')
    menge = models.IntegerField(db_column='tisch_bondetail_menge')
    absmenge = models.IntegerField(db_column='tisch_bondetail_absmenge')
    ist_umsatz = models.BooleanField(db_column='tisch_bondetail_istUmsatz')
    artikel = models.IntegerField(db_column='tisch_bondetail_artikel')
    preis = models.DecimalField(
        max_digits=18, decimal_places=3, db_column='tisch_bondetail_preis')
    text = models.CharField(max_length=50, db_column='tisch_bondetail_text')
    mwst = models.IntegerField(db_column='tisch_bondetail_mwst')
    gangfolge = models.IntegerField(db_column='tisch_bondetail_gangfolge')
    hat_rabatt = models.BooleanField(db_column='tisch_bondetail_hatRabatt')
    ist_rabatt = models.BooleanField(db_column='tisch_bondetail_istRabatt')
    auto_eintrag = models.BooleanField(db_column='tisch_bondetail_autoEintrag')
    storno_faehig = models.BooleanField(
        db_column='tisch_bondetail_stornoFaehig')
    ep = models.DecimalField(max_digits=18, decimal_places=2,
                             null=True, blank=True, db_column='tisch_bondetail_ep')
    ep_mwst = models.IntegerField(
        null=True, blank=True, db_column='tisch_bondetail_ep_mwst')
    preisgruppe = models.IntegerField(
        null=True, blank=True, db_column='tisch_bondetail_preisgruppe')
    gutschein_log = models.IntegerField(
        null=True, blank=True, db_column='tisch_bondetail_gutschein_log')
    journal_preisgruppe = models.CharField(
        max_length=50, null=True, blank=True, db_column='journal_preisgruppe')
    journal_gruppe = models.CharField(
        max_length=2000, null=True, blank=True, db_column='journal_gruppe')
    journal_mwst = models.DecimalField(
        max_digits=18, decimal_places=3, null=True, blank=True, db_column='journal_mwst')
    ist_externer_beleg = models.BooleanField(
        db_column='tisch_bondetail_istExternerBeleg')
    period = models.ForeignKey(
        Period, on_delete=models.CASCADE, db_column='tisch_bondetail_periode')

    class Meta:
        db_table = 'tische_bondetails'
        unique_together = [('source_id', 'period')]


class RechnungBasis(models.Model):
    source_id = models.IntegerField(db_column='rechnung_id')
    typ = models.IntegerField(db_column='rechnung_typ')
    nr = models.IntegerField(db_column='rechnung_nr')
    dt_erstellung = models.DateTimeField(db_column='rechnung_dt_erstellung')
    kellner_kurz_name = models.CharField(
        max_length=50, db_column='rechnung_kellnerKurzName')
    tisch_code = models.CharField(
        max_length=50, db_column='rechnung_tischCode')
    tisch_bereich = models.CharField(
        max_length=50, db_column='rechnung_tischBereich')
    adresse = models.IntegerField(
        null=True, blank=True, db_column='rechnung_adresse')
    ist_storno = models.BooleanField(db_column='rechnung_istStorno')
    retour = models.DecimalField(
        max_digits=18, decimal_places=2, null=True, blank=True, db_column='rechnung_retour')
    dt_zusatz = models.DateTimeField(
        null=True, blank=True, db_column='rechnung_dt_zusatz')
    checkpoint_tag = models.IntegerField(
        null=True, blank=True, db_column='checkpoint_tag')
    checkpoint_monat = models.IntegerField(
        null=True, blank=True, db_column='checkpoint_monat')
    checkpoint_jahr = models.IntegerField(
        null=True, blank=True, db_column='checkpoint_jahr')
    kassenidentifikation = models.CharField(
        max_length=2000, null=True, blank=True, db_column='rechnung_kassenidentifikation')
    barumsatz_nr = models.IntegerField(
        null=True, blank=True, db_column='rechnung_barumsatz_nr')
    gesamt_umsatz = models.DecimalField(
        max_digits=18, decimal_places=3, null=True, blank=True, db_column='rechnung_gesamt_umsatz')
    zertifikat_id = models.CharField(
        max_length=2000, null=True, blank=True, db_column='rechnung_zertifikat_id')
    referenz = models.IntegerField(
        null=True, blank=True, db_column='rechnung_referenz')
    signatur = models.CharField(
        max_length=2000, null=True, blank=True, db_column='rechnung_signatur')
    druckpfad = models.CharField(
        max_length=2000, null=True, blank=True, db_column='rechnung_druckpfad')
    mwst_normal = models.DecimalField(
        max_digits=18, decimal_places=3, null=True, blank=True, db_column='rechnung_mwst_normal')
    mwst_ermaessigt1 = models.DecimalField(
        max_digits=18, decimal_places=3, null=True, blank=True, db_column='rechnung_mwst_ermaessigt1')
    mwst_ermaessigt2 = models.DecimalField(
        max_digits=18, decimal_places=3, null=True, blank=True, db_column='rechnung_mwst_ermaessigt2')
    mwst_null = models.DecimalField(
        max_digits=18, decimal_places=3, null=True, blank=True, db_column='rechnung_mwst_null')
    mwst_besonders = models.DecimalField(
        max_digits=18, decimal_places=3, null=True, blank=True, db_column='rechnung_mwst_besonders')
    gesamt_umsatz_enc = models.CharField(
        max_length=2000, null=True, blank=True, db_column='rechnung_gesamt_umsatz_enc')
    rka = models.CharField(max_length=2000, null=True,
                           blank=True, db_column='rechnung_rka')
    vorherige_signatur = models.CharField(
        max_length=2000, null=True, blank=True, db_column='rechnung_vorherige_signatur')
    beleg_kennzeichen = models.CharField(
        max_length=2000, null=True, blank=True, db_column='rechnung_beleg_kennzeichen')
    ist_trainings_beleg = models.BooleanField(
        db_column='rechnung_istTrainingsBeleg')
    period = models.ForeignKey(
        Period, on_delete=models.CASCADE, db_column='rechnung_periode')

    class Meta:
        db_table = 'rechnungen_basis'
        unique_together = [('source_id', 'period')]


class RechnungDetail(models.Model):
    source_id = models.IntegerField(db_column='rechnung_detail_id')
    rechnung = models.IntegerField(db_column='rechnung_detail_rechnung')
    master_detail = models.IntegerField(
        null=True, blank=True, db_column='rechnung_detail_master_detail')
    menge = models.IntegerField(db_column='rechnung_detail_menge')
    absmenge = models.IntegerField(db_column='rechnung_detail_absmenge')
    text = models.CharField(max_length=50, db_column='rechnung_detail_text')
    mwst = models.IntegerField(db_column='rechnung_detail_mwst')
    preis = models.DecimalField(
        max_digits=18, decimal_places=3, db_column='rechnung_detail_preis')
    artikel_gruppe = models.TextField(
        null=True, blank=True, db_column='rechnung_detail_artikel_gruppe')
    text_2 = models.TextField(null=True, blank=True,
                              db_column='rechnung_detail_text_2')
    bonierdatum = models.DateTimeField(
        null=True, blank=True, db_column='rechnung_detail_bonierdatum')
    period = models.ForeignKey(
        Period, on_delete=models.CASCADE, db_column='rechnung_detail_periode')

    class Meta:
        db_table = 'rechnungen_details'
        unique_together = [('source_id', 'period')]


class MwstGruppe(models.Model):
    source_id = models.IntegerField(db_column='mwst_id')
    satz = models.DecimalField(
        max_digits=18, decimal_places=2, db_column='mwst_satz')
    bezeichnung = models.CharField(max_length=50, db_column='mwst_bezeichnung')
    period = models.ForeignKey(
        Period, on_delete=models.CASCADE, db_column='mwst_periode')

    class Meta:
        db_table = 'meta_mwstgruppen'
        unique_together = [('source_id', 'period')]

    def __str__(self) -> str:
        return f"{self.bezeichnung} ({self.satz}%)"


class KellnerBasis(models.Model):
    source_id = models.IntegerField(db_column='kellner_id')
    kurz_name = models.CharField(max_length=50, db_column='kellner_kurzName')
    uid = models.IntegerField(db_column='kellner_uid')
    person = models.IntegerField(db_column='kellner_person')
    lager = models.IntegerField(
        null=True, blank=True, db_column='kellner_lager')
    schnell_tisch_bereich = models.IntegerField(
        null=True, blank=True, db_column='kellner_schnellTisch_bereich')
    schnell_tisch_pri_nummer = models.IntegerField(
        null=True, blank=True, db_column='kellner_schnellTisch_pri_nummer')
    schnell_tisch_sek_nummer = models.IntegerField(
        null=True, blank=True, db_column='kellner_schnellTisch_sek_nummer')
    zeige_auswahl = models.BooleanField(db_column='kellner_zeigeAuswahl')
    kasse = models.IntegerField(
        null=True, blank=True, db_column='kellner_kasse')
    period = models.ForeignKey(
        Period, on_delete=models.CASCADE, db_column='kellner_periode')

    class Meta:
        db_table = 'kellner_basis'
        unique_together = [('source_id', 'period')]


class ArticleGroup(models.Model):
    """artikel_gruppen — imported from MSSQL."""
    source_id = models.IntegerField(db_column='artikel_gruppe_id')
    parent_source_id = models.IntegerField(
        null=True, blank=True, db_column='artikel_gruppe_parent_id')
    name = models.CharField(max_length=50, db_column='artikel_gruppe_name')
    standard_course = models.IntegerField(
        db_column='artikel_gruppe_standard_gangfolge')
    bon_type = models.IntegerField(
        null=True, blank=True, db_column='artikel_gruppe_bontyp')
    is_revenue = models.BooleanField(db_column='artikel_gruppe_istUmsatz')
    show_on_receipt = models.BooleanField(
        db_column='artikel_gruppe_zeigeAufRechnung')
    print_recipe = models.BooleanField(
        db_column='artikel_gruppe_druckeRezeptur')
    no_cancellation = models.BooleanField(
        db_column='artikel_gruppe_keinStorno')
    period = models.ForeignKey(
        Period, on_delete=models.CASCADE, db_column='artikel_gruppe_periode')

    class Meta:
        db_table = 'artikel_gruppen'
        unique_together = [('source_id', 'period')]

    def __str__(self) -> str:
        return self.name


class Article(models.Model):
    """artikel_basis — imported from MSSQL (POS articles)."""
    source_id = models.IntegerField(db_column='artikel_id')
    name = models.CharField(max_length=50, db_column='artikel_bezeichnung')
    group = models.ForeignKey(
        ArticleGroup,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='articles',
        db_column='artikel_gruppe',
    )
    sales_price = models.DecimalField(
        max_digits=18, decimal_places=2, null=True, blank=True, db_column='artikel_ep'
    )
    sales_price_vat = models.IntegerField(
        null=True, blank=True, db_column='artikel_ep_mwst')
    price_popup = models.BooleanField(db_column='artikel_preis_popup')
    ep_price_popup = models.BooleanField(db_column='artikel_ep_preis_popup')
    note = models.TextField(null=True, blank=True,
                            db_column='artikel_bemerkung')
    name_2 = models.TextField(null=True, blank=True,
                              db_column='artikel_bezeichnung_2')
    rksv = models.BooleanField(db_column='artikel_rksv')
    external_receipt = models.BooleanField(db_column='artikel_externer_beleg')
    period = models.ForeignKey(
        Period, on_delete=models.CASCADE, db_column='artikel_periode')

    class Meta:
        db_table = 'artikel_basis'
        unique_together = [('source_id', 'period')]
        ordering = ['name']

    def __str__(self) -> str:
        return self.name


class ArticleMeta(models.Model):
    """Per-article metadata scoped to a period, keyed by (source_id, period)."""
    source_id = models.IntegerField()
    period = models.ForeignKey(
        Period,
        on_delete=models.CASCADE,
        related_name='article_metas',
    )
    is_hidden = models.BooleanField(default=False)
    # comma-separated, e.g. "lemon,orange"
    sub_articles = models.TextField(blank=True)
    package_size = models.DecimalField(
        max_digits=10, decimal_places=4, null=True, blank=True
    )
    extra = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = 'Article Meta'
        verbose_name_plural = 'Article Meta'
        unique_together = [('source_id', 'period')]

    def __str__(self) -> str:
        return f"ArticleMeta(source_id={self.source_id}, period={self.period_id})"


class Recipe(models.Model):
    """artikel_zutaten — recipe/ingredient relationships, imported from MSSQL."""
    source_master_article_id = models.IntegerField(
        db_column='zutate_master_artikel')
    master_article = models.ForeignKey(
        Article,
        on_delete=models.CASCADE,
        related_name='recipe_components',
        db_column='zutate_master_artikel_id',
    )
    source_ingredient_article_id = models.IntegerField(
        db_column='zutate_artikel')
    ingredient_article = models.ForeignKey(
        Article,
        on_delete=models.CASCADE,
        related_name='used_in_recipes',
        db_column='zutate_artikel_id',
    )
    quantity = models.DecimalField(
        max_digits=10, decimal_places=4, db_column='zutate_menge')
    is_fixed = models.BooleanField(db_column='zutate_istFixiert')
    is_ingredient = models.BooleanField(db_column='zutate_istZutat')
    is_recipe = models.BooleanField(db_column='zutate_istRezept')
    always_show = models.BooleanField(db_column='zutate_immerAnzeigen')
    is_mandatory = models.BooleanField(db_column='zutate_istZwangsAbfrage')
    use_price = models.BooleanField(db_column='zutate_preisVerwenden')
    period = models.ForeignKey(
        Period, on_delete=models.CASCADE, db_column='zutate_periode')

    class Meta:
        db_table = 'artikel_zutaten'

    def __str__(self) -> str:
        return f"{self.master_article_id} -> {self.ingredient_article_id}"


class WarehouseUnit(models.Model):
    """lager_einheiten — units of measure, imported from MSSQL."""
    source_id = models.IntegerField(db_column='lager_einheit_id')
    name = models.TextField(db_column='lager_einheit_name')
    multiplier = models.DecimalField(
        max_digits=10, decimal_places=4, db_column='lager_einheit_multiplizierer')
    base_unit = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='lager_einheit_basis',
    )
    period = models.ForeignKey(
        Period, on_delete=models.CASCADE, db_column='lager_einheit_periode')

    class Meta:
        db_table = 'lager_einheiten'
        unique_together = [('source_id', 'period')]

    def __str__(self) -> str:
        return str(self.name)


class WarehouseArticle(models.Model):
    """lager_artikel — warehouse-managed articles, imported from MSSQL."""
    source_id = models.IntegerField(db_column='lager_artikel_lagerartikel')
    supplier_source_id = models.IntegerField(
        db_column='lager_artikel_lieferant')
    supplier_article_number = models.CharField(
        max_length=20, null=True, blank=True, db_column='lager_artikel_lieferant_artikel'
    )
    article = models.ForeignKey(
        Article,
        on_delete=models.CASCADE,
        related_name='warehouse_entries',
        db_column='lager_artikel_artikel_id',
    )
    source_article_id = models.IntegerField(db_column='lager_artikel_artikel')

    priority = models.IntegerField(db_column='lager_artikel_prioritaet')
    unit = models.ForeignKey(
        WarehouseUnit,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='lager_artikel_einheit_id',
    )
    source_unit_id = models.IntegerField(db_column='lager_artikel_einheit')
    warehouse = models.IntegerField(
        null=True, blank=True, db_column='lager_artikel_lager')
    flags = models.IntegerField(db_column='lager_artikel_flags')
    max_stock = models.DecimalField(
        max_digits=10, decimal_places=3, db_column='lager_artikel_maxStand')
    min_stock = models.DecimalField(
        max_digits=10, decimal_places=3, db_column='lager_artikel_minStand')
    period = models.ForeignKey(Period, on_delete=models.CASCADE,
                               db_column='lager_artikel_periode')

    class Meta:
        db_table = 'lager_artikel'
        unique_together = [('source_id', 'period'), ('article', 'period')]
        ordering = ["article__name"]

    def __str__(self) -> str:
        return f"LA {self.source_id}"
