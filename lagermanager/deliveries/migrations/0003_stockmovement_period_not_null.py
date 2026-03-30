from django.db import migrations, models
import django.db.models.deletion


def fill_missing_periods(apps, schema_editor):
    StockMovement = apps.get_model('deliveries', 'StockMovement')
    Period = apps.get_model('core', 'Period')
    for movement in StockMovement.objects.filter(period__isnull=True):
        period = Period.objects.filter(start__lte=movement.date, end__gte=movement.date).first()
        if period:
            movement.period = period
            movement.save(update_fields=['period'])
        else:
            raise ValueError(
                f"StockMovement {movement.id} (date={movement.date}) has no matching period. "
                "Assign a period manually before running this migration."
            )


class Migration(migrations.Migration):

    dependencies = [
        ('deliveries', '0002_alter_stockmovement_date'),
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(fill_missing_periods, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='stockmovement',
            name='period',
            field=models.ForeignKey(
                db_column='lie_periode_id',
                on_delete=django.db.models.deletion.PROTECT,
                related_name='stock_movements',
                to='core.period',
            ),
        ),
    ]
