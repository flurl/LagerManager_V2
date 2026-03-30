from django.db import migrations, models
import django.db.models.deletion


def backfill_tax_rate(apps, schema_editor):
    StockMovementDetail = apps.get_model('deliveries', 'StockMovementDetail')
    TaxRate = apps.get_model('deliveries', 'TaxRate')

    null_details = StockMovementDetail.objects.filter(tax_rate__isnull=True)
    if not null_details.exists():
        return

    # Try to use the constance DEFAULT_TAX_RATE_ID, fall back to first TaxRate
    default_tax_rate = None
    try:
        from constance import config as constance_cfg
        default_id = constance_cfg.DEFAULT_TAX_RATE_ID
        if default_id:
            default_tax_rate = TaxRate.objects.filter(pk=default_id).first()
    except Exception:
        pass

    if default_tax_rate is None:
        default_tax_rate = TaxRate.objects.first()

    if default_tax_rate is None:
        raise RuntimeError(
            'Cannot make tax_rate non-nullable: no TaxRate exists and no rows to backfill with.'
        )

    null_details.update(tax_rate=default_tax_rate)


class Migration(migrations.Migration):

    dependencies = [
        ('deliveries', '0003_stockmovement_period_not_null'),
    ]

    operations = [
        migrations.RunPython(backfill_tax_rate, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='stockmovementdetail',
            name='tax_rate',
            field=models.ForeignKey(
                db_column='lde_stsid',
                on_delete=django.db.models.deletion.PROTECT,
                to='deliveries.taxrate',
            ),
        ),
    ]
