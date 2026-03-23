from articles.models import Article
from core.models import Period, Workplace
from django.db import models


class StockLevel(models.Model):
    """lagerstand — initial stock level per article per period."""
    article = models.ForeignKey(
        Article,
        on_delete=models.CASCADE,
        related_name='stock_levels',
        db_column='artikel_id',
    )
    quantity = models.DecimalField(max_digits=10, decimal_places=3, db_column='anzahl')
    period = models.ForeignKey(
        Period,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='stock_levels',
        db_column='periode_id',
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'lagerstand'
        unique_together = [('article', 'period')]

    def __str__(self):
        return f"{self.article_id} @ {self.period_id}: {self.quantity}"


class InitialInventory(models.Model):
    """initialer_stand — initial stock per article/workplace/period."""
    article = models.ForeignKey(
        Article,
        on_delete=models.CASCADE,
        related_name='initial_inventories',
        db_column='ist_artikel_id',
    )
    quantity = models.DecimalField(max_digits=10, decimal_places=3, db_column='ist_anzahl')
    workplace = models.ForeignKey(
        Workplace,
        on_delete=models.CASCADE,
        db_column='ist_arp_id',
    )
    period = models.ForeignKey(
        Period,
        on_delete=models.CASCADE,
        related_name='initial_inventories',
        db_column='ist_periode_id',
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'initialer_stand'
        unique_together = [('article', 'workplace', 'period')]

    def __str__(self):
        return f"IS {self.article_id}/{self.workplace_id}/{self.period_id}"


class PhysicalCount(models.Model):
    """gezaehlter_stand — physical stock counts."""
    date = models.DateTimeField(db_column='gst_datum')
    article = models.ForeignKey(
        Article,
        on_delete=models.CASCADE,
        related_name='physical_counts',
        db_column='gst_artikel_id',
    )
    quantity = models.DecimalField(max_digits=10, decimal_places=3, db_column='gst_anzahl')
    period = models.ForeignKey(
        Period,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='physical_counts',
        db_column='gst_periode_id',
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'gezaehlter_stand'
        indexes = [models.Index(fields=['date'], name='gezaehlter_stand_datum_idx')]

    def __str__(self):
        return f"PC {self.article_id} @ {self.date:%Y-%m-%d}: {self.quantity}"
