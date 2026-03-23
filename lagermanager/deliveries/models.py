from articles.models import Article
from core.models import Period
from django.db import models
from django.db.models import DecimalField, ExpressionWrapper, F, Sum


class Supplier(models.Model):
    """lieferanten"""
    name = models.CharField(max_length=255, db_column='lieferant_name')
    is_consumer = models.BooleanField(default=False, db_column='lft_ist_verbraucher')

    class Meta:
        db_table = 'lieferanten'
        ordering = ['name']

    def __str__(self):
        return self.name


class TaxRate(models.Model):
    """steuersaetze"""
    name = models.CharField(max_length=255, db_column='sts_bezeichnung')
    percent = models.DecimalField(max_digits=5, decimal_places=2, db_column='sts_prozent')

    class Meta:
        db_table = 'steuersaetze'
        ordering = ['percent']

    def __str__(self):
        return f"{self.name} ({self.percent}%)"


class DeliveryUnit(models.Model):
    """liefereinheiten — packaging units for deliveries (e.g. Kiste 20x)"""
    name = models.CharField(max_length=255, db_column='lei_bezeichnung')
    quantity = models.DecimalField(max_digits=10, decimal_places=3, db_column='lei_menge')

    class Meta:
        db_table = 'liefereinheiten'
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.quantity})"


class DocumentType(models.Model):
    """dokumenttypen"""
    name = models.CharField(max_length=255, db_column='dot_bezeichnung')

    class Meta:
        db_table = 'dokumenttypen'

    def __str__(self):
        return self.name


class Delivery(models.Model):
    """lieferungen — a delivery or consumption record."""
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name='deliveries',
        db_column='lieferant_id',
    )
    date = models.DateTimeField(db_column='datum')
    is_consumption = models.BooleanField(default=False, db_column='lie_ist_verbrauch')
    comment = models.TextField(null=True, blank=True, db_column='lie_kommentar')
    period = models.ForeignKey(
        Period,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='deliveries',
        db_column='lie_periode_id',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'lieferungen'
        ordering = ['-date']

    def __str__(self):
        return f"{'Verbrauch' if self.is_consumption else 'Lieferung'} {self.id} – {self.date:%Y-%m-%d}"

    @property
    def total_net(self):
        result = self.details.aggregate(
            total=Sum(
                ExpressionWrapper(
                    F('quantity') * F('unit_price'),
                    output_field=DecimalField(max_digits=18, decimal_places=4),
                )
            )
        )
        return result['total'] or 0

    @property
    def total_gross(self):
        result = self.details.aggregate(
            total=Sum(
                ExpressionWrapper(
                    F('quantity') * F('unit_price') * (1 + F('tax_rate__percent') / 100),
                    output_field=DecimalField(max_digits=18, decimal_places=4),
                )
            )
        )
        return result['total'] or 0


class DeliveryDetail(models.Model):
    """lieferungen_details"""
    delivery = models.ForeignKey(
        Delivery,
        on_delete=models.CASCADE,
        related_name='details',
        db_column='lieferung_id',
    )
    article = models.ForeignKey(
        Article,
        on_delete=models.PROTECT,
        db_column='artikel_id',
    )
    quantity = models.DecimalField(max_digits=10, decimal_places=3, db_column='anzahl')
    unit_price = models.DecimalField(max_digits=10, decimal_places=4, db_column='einkaufspreis')
    tax_rate = models.ForeignKey(
        TaxRate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='lde_stsid',
    )
    delivery_unit = models.ForeignKey(
        DeliveryUnit,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='lde_lei_id',
    )

    class Meta:
        db_table = 'lieferungen_details'

    def __str__(self):
        return f"{self.delivery_id} – {self.article_id}"

    @property
    def line_net(self):
        return self.quantity * self.unit_price

    @property
    def line_gross(self):
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
    delivery = models.ForeignKey(
        Delivery,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='documents',
        db_column='dok_lieferung_id',
    )

    class Meta:
        db_table = 'dokumente'

    def __str__(self):
        return self.name
