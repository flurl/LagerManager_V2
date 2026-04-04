from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_rename_workplace_to_location'),
        ('inventory', '0002_alter_periodstartstocklevel_period_and_more'),
    ]

    operations = [
        migrations.RenameField('initialinventory', 'workplace', 'location'),
    ]
