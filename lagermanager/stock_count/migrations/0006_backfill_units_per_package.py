from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor


def backfill_units_per_package(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    StockCountEntry = apps.get_model("stock_count", "StockCountEntry")
    for entry in StockCountEntry.objects.filter(package_count__gt=0):
        entry.units_per_package = round((float(entry.quantity) - entry.unit_count) / entry.package_count)
        entry.save(update_fields=["units_per_package"])


class Migration(migrations.Migration):
    dependencies = [
        ("stock_count", "0005_stockcountentry_units_per_package_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill_units_per_package, migrations.RunPython.noop),
    ]
