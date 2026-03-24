from django.db import models


class Period(models.Model):
    """Abrechnungsperiode (Geschäftsjahr)"""
    name = models.CharField(max_length=255, db_column='periode_bezeichnung')
    checkpoint_year = models.IntegerField(null=True, blank=True, db_column='periode_checkpoint_jahr')
    start = models.DateTimeField(db_column='periode_start')
    end = models.DateTimeField(db_column='periode_ende')

    class Meta:
        db_table = 'perioden'
        ordering = ['-start']

    def __str__(self) -> str:
        return self.name


class Workplace(models.Model):
    """Arbeitsplatz / Bar / Lager"""
    name = models.CharField(max_length=255, db_column='arp_bezeichnung')
    default_shift_duration = models.FloatField(db_column='arp_std_dienst_dauer')

    class Meta:
        db_table = 'arbeitsplaetze'
        ordering = ['name']

    def __str__(self) -> str:
        return self.name


class Config(models.Model):
    """Globale Konfigurationseinstellungen"""
    key = models.CharField(max_length=255, db_column='cfg_key')
    value_int = models.IntegerField(null=True, blank=True, db_column='cfg_valueI')
    value_float = models.FloatField(null=True, blank=True, db_column='cfg_valueF')
    value_str = models.TextField(null=True, blank=True, db_column='cfg_valueS')
    valid_till = models.DateTimeField(db_column='cfg_validTill')

    class Meta:
        db_table = 'config'
        unique_together = [('key', 'valid_till')]

    def __str__(self) -> str:
        return self.key
