from django.db import models


class StockCountEntry(models.Model):
    """stock_count_entries — denormalized audit log of stock counts, no FKs."""
    count_date = models.DateTimeField()
    article_id = models.CharField(max_length=100)
    article_name = models.CharField(max_length=200)
    location_id = models.IntegerField()
    location_name = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=10, decimal_places=3)
    period_id_value = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'stock_count_entries'
        unique_together = [('article_id', 'location_id', 'count_date', 'period_id_value')]

    def __str__(self) -> str:
        return f"{self.article_name} @ {self.location_name} ({self.count_date:%Y-%m-%d}): {self.quantity}"
