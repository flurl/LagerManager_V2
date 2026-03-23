from core.models import Period
from django.db import models


class ArticleGroup(models.Model):
    """artikel_gruppen — imported from MSSQL."""
    source_id = models.IntegerField(db_column='artikel_gruppe_id')
    parent_source_id = models.IntegerField(null=True, blank=True, db_column='artikel_gruppe_parent_id')
    name = models.CharField(max_length=50, db_column='artikel_gruppe_name')
    standard_course = models.IntegerField(db_column='artikel_gruppe_standard_gangfolge')
    bon_type = models.IntegerField(null=True, blank=True, db_column='artikel_gruppe_bontyp')
    is_revenue = models.BooleanField(db_column='artikel_gruppe_istUmsatz')
    show_on_receipt = models.BooleanField(db_column='artikel_gruppe_zeigeAufRechnung')
    print_recipe = models.BooleanField(db_column='artikel_gruppe_druckeRezeptur')
    no_cancellation = models.BooleanField(db_column='artikel_gruppe_keinStorno')
    period = models.ForeignKey(Period, on_delete=models.CASCADE, db_column='artikel_gruppe_periode')

    class Meta:
        db_table = 'artikel_gruppen'
        unique_together = [('source_id', 'period')]

    def __str__(self):
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
    sales_price_vat = models.IntegerField(null=True, blank=True, db_column='artikel_ep_mwst')
    price_popup = models.BooleanField(db_column='artikel_preis_popup')
    ep_price_popup = models.BooleanField(db_column='artikel_ep_preis_popup')
    note = models.TextField(null=True, blank=True, db_column='artikel_bemerkung')
    name_2 = models.TextField(null=True, blank=True, db_column='artikel_bezeichnung_2')
    rksv = models.BooleanField(db_column='artikel_rksv')
    external_receipt = models.BooleanField(db_column='artikel_externer_beleg')
    period = models.ForeignKey(Period, on_delete=models.CASCADE, null=True, blank=True, db_column='artikel_periode')

    class Meta:
        db_table = 'artikel_basis'
        unique_together = [('source_id', 'period')]

    def __str__(self):
        return self.name


class Recipe(models.Model):
    """artikel_zutaten — recipe/ingredient relationships, imported from MSSQL."""
    master_article = models.ForeignKey(
        Article,
        on_delete=models.CASCADE,
        related_name='recipe_components',
        db_column='zutate_master_artikel',
    )
    ingredient_article = models.ForeignKey(
        Article,
        on_delete=models.CASCADE,
        related_name='used_in_recipes',
        db_column='zutate_artikel',
    )
    quantity = models.DecimalField(max_digits=10, decimal_places=4, db_column='zutate_menge')
    is_fixed = models.BooleanField(db_column='zutate_istFixiert')
    is_ingredient = models.BooleanField(db_column='zutate_istZutat')
    is_recipe = models.BooleanField(db_column='zutate_istRezept')
    always_show = models.BooleanField(db_column='zutate_immerAnzeigen')
    is_mandatory = models.BooleanField(db_column='zutate_istZwangsAbfrage')
    use_price = models.BooleanField(db_column='zutate_preisVerwenden')
    period = models.ForeignKey(Period, on_delete=models.CASCADE, db_column='zutate_periode')

    class Meta:
        db_table = 'artikel_zutaten'

    def __str__(self):
        return f"{self.master_article_id} -> {self.ingredient_article_id}"


class WarehouseUnit(models.Model):
    """lager_einheiten — units of measure, imported from MSSQL."""
    source_id = models.IntegerField(db_column='lager_einheit_id')
    name = models.TextField(db_column='lager_einheit_name')
    multiplier = models.DecimalField(
        max_digits=10, decimal_places=4, db_column='lager_einheit_multiplizierer'
    )
    base_unit = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='lager_einheit_basis',
    )
    period = models.ForeignKey(Period, on_delete=models.CASCADE, db_column='lager_einheit_periode')

    class Meta:
        db_table = 'lager_einheiten'
        unique_together = [('source_id', 'period')]

    def __str__(self):
        return str(self.name)


class WarehouseArticle(models.Model):
    """lager_artikel — warehouse-managed articles, imported from MSSQL."""
    source_id = models.IntegerField(db_column='lager_artikel_lagerartikel')
    supplier_source_id = models.IntegerField(db_column='lager_artikel_lieferant')
    supplier_article_number = models.CharField(
        max_length=20, null=True, blank=True, db_column='lager_artikel_lieferant_artikel'
    )
    article = models.ForeignKey(
        Article,
        on_delete=models.CASCADE,
        related_name='warehouse_entries',
        db_column='lager_artikel_artikel',
    )
    priority = models.IntegerField(db_column='lager_artikel_prioritaet')
    unit = models.ForeignKey(
        WarehouseUnit,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='lager_artikel_einheit',
    )
    warehouse = models.IntegerField(null=True, blank=True, db_column='lager_artikel_lager')
    flags = models.IntegerField(db_column='lager_artikel_flags')
    max_stock = models.DecimalField(max_digits=10, decimal_places=3, db_column='lager_artikel_maxStand')
    min_stock = models.DecimalField(max_digits=10, decimal_places=3, db_column='lager_artikel_minStand')
    period = models.ForeignKey(Period, on_delete=models.CASCADE, null=True, blank=True, db_column='lager_artikel_periode')

    class Meta:
        db_table = 'lager_artikel'
        unique_together = [('source_id', 'period')]

    def __str__(self):
        return f"LA {self.source_id}"


class EkModifier(models.Model):
    """ek_modifikatoren — purchase price modifiers per article/period."""
    OPERATOR_CHOICES = [('+', '+'), ('-', '-'), ('*', '*'), ('/', '/')]

    article = models.ForeignKey(
        Article,
        on_delete=models.CASCADE,
        related_name='ek_modifiers',
        db_column='emo_artikel_id',
    )
    operator = models.CharField(max_length=1, choices=OPERATOR_CHOICES, db_column='emo_operator')
    modifier = models.DecimalField(max_digits=10, decimal_places=4, db_column='emo_modifikator')
    period = models.ForeignKey(Period, on_delete=models.CASCADE, db_column='emo_periode_id')

    class Meta:
        db_table = 'ek_modifikatoren'
        ordering = ['id']

    def __str__(self):
        return f"{self.article_id} {self.operator} {self.modifier}"
