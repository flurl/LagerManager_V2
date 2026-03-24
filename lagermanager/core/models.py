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
        db_table: str = 'perioden'
        ordering: list[str] = ['-start']

    def __str__(self) -> str:
        return self.name


class Workplace(models.Model):
    """Arbeitsplatz / Bar / Lager"""
    name = models.CharField(
        max_length=255, db_column='arp_bezeichnung')

    class Meta:
        db_table: str = 'arbeitsplaetze'
        ordering: list[str] = ['name']

    def __str__(self) -> str:
        return self.name
