from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.models import F


def backfill_unit_count(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    StockCountEntry = apps.get_model("stock_count", "StockCountEntry")
    # Set unit_count = quantity for all existing records (package_count stays 0)
    StockCountEntry.objects.update(unit_count=F("quantity"))


class Migration(migrations.Migration):
    dependencies = [
        ("stock_count", "0003_stockcountentry_package_count_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill_unit_count, migrations.RunPython.noop),
    ]
