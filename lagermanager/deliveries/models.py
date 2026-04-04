from decimal import Decimal

from core.models import Period
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import DecimalField, ExpressionWrapper, F, Sum
from pos_import.models import Article


class Partner(models.Model):
    """partner — suppliers and consumers."""

    class Type(models.TextChoices):
        SUPPLIER = 'supplier', 'Lieferant'
        CONSUMER = 'consumer', 'Verbraucher'

    name = models.CharField(max_length=255, db_column='lieferant_name')
    partner_type = models.CharField(
        max_length=20,
        choices=Type.choices,
        default=Type.SUPPLIER,
    )

    class Meta:
        db_table = 'partner'
        ordering = ['name']

    def __str__(self) -> str:
        return self.name


class PartnerAiInstruction(models.Model):
    """Per-provider LLM instructions for a partner."""

    partner = models.ForeignKey(
        Partner,
        on_delete=models.CASCADE,
        related_name='ai_instructions',
    )
    provider = models.CharField(max_length=50)
    instructions = models.TextField(blank=True)

    class Meta:
        unique_together = [('partner', 'provider')]
        ordering = ['provider']

    def __str__(self) -> str:
        return f"{self.partner} – {self.provider}"


class TaxRate(models.Model):
    """steuersaetze"""
    name = models.CharField(max_length=255, db_column='sts_bezeichnung')
    percent = models.DecimalField(
        max_digits=5, decimal_places=2, db_column='sts_prozent')

    class Meta:
        db_table = 'steuersaetze'
        ordering = ['percent']

    def __str__(self) -> str:
        return f"{self.name} ({self.percent}%)"


class StockMovement(models.Model):
    """lagerbewegungen — a delivery or consumption record."""

    class Type(models.TextChoices):
        DELIVERY = 'delivery', 'Lieferung'
        CONSUMPTION = 'consumption', 'Verbrauch'

    partner = models.ForeignKey(
        Partner,
        on_delete=models.PROTECT,
        related_name='stock_movements',
        db_column='partner_id',
    )
    date = models.DateField(db_column='datum')
    movement_type = models.CharField(
        max_length=20,
        choices=Type.choices,
        default=Type.DELIVERY,
    )
    comment = models.TextField(
        null=True, blank=True, db_column='lie_kommentar')
    period = models.ForeignKey(
        Period,
        on_delete=models.PROTECT,
        related_name='stock_movements',
        db_column='lie_periode_id',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'lagerbewegungen'
        ordering = ['-date']

    def __str__(self) -> str:
        label = self.Type(
            self.movement_type).label if self.movement_type else 'Bewegung'
        return f"{label} {self.id} – {self.date:%Y-%m-%d}"

    def clean(self) -> None:
        if self.date and self.period_id:
            period = self.period
            if not (period.start.date() <= self.date <= period.end.date()):
                raise ValidationError(
                    {'date': f'Datum muss zwischen {period.start} und {period.end} liegen.'}
                )

    def apply_skonto(self, percent: float) -> None:
        """Apply a percentage discount to all detail line prices. Modifies unit_price in place."""
        factor = Decimal(str(1 - percent / 100))
        for detail in self.details.all():
            detail.unit_price = (detail.unit_price *
                                 factor).quantize(Decimal('0.0001'))
            detail.save(update_fields=['unit_price'])

    @property
    def total_net(self) -> Decimal:
        result = self.details.aggregate(
            total=Sum(
                ExpressionWrapper(
                    F('quantity') * F('unit_price'),
                    output_field=DecimalField(max_digits=18, decimal_places=4),
                )
            )
        )
        return result['total'] or Decimal(0)

    @property
    def total_gross(self) -> Decimal:
        result = self.details.aggregate(
            total=Sum(
                ExpressionWrapper(
                    F('quantity') * F('unit_price') *
                    (1 + F('tax_rate__percent') / 100),
                    output_field=DecimalField(max_digits=18, decimal_places=4),
                )
            )
        )
        return result['total'] or Decimal(0)


class StockMovementDetail(models.Model):
    """lagerbewegungen_details"""
    stock_movement = models.ForeignKey(
        StockMovement,
        on_delete=models.CASCADE,
        related_name='details',
        db_column='lagerbewegung_id',
    )
    article = models.ForeignKey(
        Article,
        on_delete=models.PROTECT,
        db_column='artikel_id',
    )
    quantity = models.DecimalField(
        max_digits=10, decimal_places=3, db_column='anzahl')
    unit_price = models.DecimalField(
        max_digits=10, decimal_places=4, db_column='einkaufspreis')
    tax_rate = models.ForeignKey(
        TaxRate,
        on_delete=models.PROTECT,
        db_column='lde_stsid',
    )

    class Meta:
        db_table = 'lagerbewegungen_details'

    def __str__(self) -> str:
        return f"{self.stock_movement_id} – {self.article_id}"

    @property
    def line_net(self) -> Decimal:
        return self.quantity * self.unit_price

    @property
    def line_gross(self) -> Decimal:
        return self.line_net * (1 + self.tax_rate.percent / 100)



def attachment_upload_path(instance: "Attachment", filename: str) -> str:
    folder = instance.stock_movement_id if instance.stock_movement_id is not None else "orphaned"
    return f"attachments/{folder}/{filename}"


class Attachment(models.Model):
    """Uploaded document images attached to a stock movement.

    PDFs are converted server-side to one Attachment per page (PNG).
    Images are stored as-is.
    Attachments may temporarily have no movement (stock_movement=None) while a new movement
    is being created; they are assigned once the movement is saved.
    """

    stock_movement = models.ForeignKey(
        StockMovement,
        on_delete=models.CASCADE,
        related_name='attachments',
        null=True,
        blank=True,
    )
    file = models.ImageField(upload_to=attachment_upload_path)
    original_filename = models.CharField(max_length=255)
    source_filename = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text='Original PDF filename when this image was extracted from a PDF.',
    )
    page_number = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text='Page number (1-based) if extracted from a PDF.',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['source_filename', 'page_number', 'created_at']

    def __str__(self) -> str:
        if self.source_filename and self.page_number:
            return f"{self.source_filename} S.{self.page_number}"
        return self.original_filename
