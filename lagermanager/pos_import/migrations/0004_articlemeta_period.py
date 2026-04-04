"""
Redesign ArticleMeta: replace global unique source_id + periods text field
with a proper (source_id, period) unique_together. Table is empty so existing
rows are cleared before the schema changes.
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_rename_workplace_to_location'),
        ('pos_import', '0003_articlemeta'),
    ]

    operations = [
        migrations.RunSQL('DELETE FROM pos_import_articlemeta', migrations.RunSQL.noop),
        migrations.RemoveField(model_name='articlemeta', name='periods'),
        migrations.AlterField(
            model_name='articlemeta',
            name='source_id',
            field=models.IntegerField(),
        ),
        migrations.AddField(
            model_name='articlemeta',
            name='period',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='article_metas',
                to='core.period',
            ),
        ),
        migrations.AlterUniqueTogether(
            name='articlemeta',
            unique_together={('source_id', 'period')},
        ),
    ]
