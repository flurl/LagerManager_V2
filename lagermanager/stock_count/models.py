from collections.abc import Iterable

from django.db import models
from django.db.models.base import ModelBase


class StockCountEntry(models.Model):
    """stock_count_entries — denormalized audit log of stock counts, no FKs."""
    count_date = models.DateTimeField()
    article_id = models.CharField(max_length=100)
    article_name = models.CharField(max_length=200)
    location_id = models.IntegerField()
    location_name = models.CharField(max_length=255)
    package_count = models.PositiveIntegerField(default=0)
    units_per_package = models.PositiveIntegerField(default=0)
    unit_count = models.PositiveIntegerField(default=0)
    quantity = models.PositiveIntegerField()

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'stock_count_entries'
        unique_together = [('article_id', 'location_id', 'count_date')]
        ordering = ['-count_date']

    def save(
        self,
        *,
        force_insert: bool | tuple[ModelBase, ...] = False,
        force_update: bool = False,
        using: str | None = None,
        update_fields: Iterable[str] | None = None,
    ) -> None:
        self.quantity = self.package_count * self.units_per_package + self.unit_count
        if update_fields is not None:
            update_fields = frozenset(update_fields) | {'quantity'}
        super().save(force_insert=force_insert, force_update=force_update, using=using, update_fields=update_fields)

    def __str__(self) -> str:
        return f"{self.article_name} @ {self.location_name} ({self.count_date:%Y-%m-%d}): {self.quantity}"
