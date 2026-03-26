from decimal import Decimal

from core.models import Period
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


class DocumentType(models.Model):
    """dokumenttypen"""
    name = models.CharField(max_length=255, db_column='dot_bezeichnung')

    class Meta:
        db_table = 'dokumenttypen'

    def __str__(self) -> str:
        return self.name


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
        null=True,
        blank=True,
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
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
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
        if self.tax_rate:
            return self.line_net * (1 + self.tax_rate.percent / 100)
        return self.line_net


class Document(models.Model):
    """dokumente — delivery document attachments."""
    doc_type = models.ForeignKey(
        DocumentType,
        on_delete=models.PROTECT,
        db_column='dok_dotid',
    )
    name = models.CharField(max_length=255, db_column='dok_bezeichnung')
    ocr_text = models.TextField(null=True, blank=True, db_column='dok_ocr')
    data = models.BinaryField(db_column='dok_data')
    date = models.DateTimeField(db_column='dok_datum')
    stock_movement = models.ForeignKey(
        StockMovement,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='documents',
        db_column='dok_lagerbewegung_id',
    )

    class Meta:
        db_table = 'dokumente'

    def __str__(self) -> str:
        return self.name


class EkModifier(models.Model):
    """ek_modifikatoren — purchase price modifiers per article/period."""
    OPERATOR_CHOICES = [('+', '+'), ('-', '-'), ('*', '*'), ('/', '/')]

    article = models.ForeignKey(
        Article,
        on_delete=models.CASCADE,
        related_name='ek_modifiers',
        db_column='emo_artikel_id',
    )
    operator = models.CharField(
        max_length=1, choices=OPERATOR_CHOICES, db_column='emo_operator')
    modifier = models.DecimalField(
        max_digits=10, decimal_places=4, db_column='emo_modifikator')
    period = models.ForeignKey(
        Period, on_delete=models.CASCADE, db_column='emo_periode_id')

    class Meta:
        db_table = 'ek_modifikatoren'
        ordering = ['id']

    def __str__(self) -> str:
        return f"{self.article_id} {self.operator} {self.modifier}"
