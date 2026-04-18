from django.db import models


class StaffConsumptionEntry(models.Model):
    """staff_consumption_entries — denormalized log of staff consumption, no FKs."""

    consumption_date = models.DateTimeField()
    department_name = models.CharField(max_length=255)
    article_id = models.CharField(
        max_length=100
    )  # warehouse source_id or "free-text-<name>"
    article_name = models.CharField(max_length=200)
    count = models.PositiveIntegerField()
    year_month = models.CharField(max_length=7)  # e.g. "2026-4"
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "staff_consumption_entries"
        unique_together = [("consumption_date", "department_name", "article_id")]
        ordering = ["-consumption_date"]

    def __str__(self) -> str:
        return f"{self.article_name} @ {self.department_name} ({self.consumption_date:%Y-%m-%d}): {self.count}"
