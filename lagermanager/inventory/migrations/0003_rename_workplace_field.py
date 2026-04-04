import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_rename_workplace_to_location'),
        ('inventory', '0002_alter_periodstartstocklevel_period_and_more'),
    ]

    operations = [
        migrations.RenameField('initialinventory', 'workplace', 'location'),
        migrations.AlterField(
            model_name='initialinventory',
            name='location',
            field=models.ForeignKey(
                db_column='ist_arp_id',
                on_delete=django.db.models.deletion.CASCADE,
                to='core.location',
            ),
        ),
    ]
