"""
Migration: Correct F5 catalog field definitions.

F5SoftwareVersion:
  - Rename eoss_date → eosd_date (End of Software Development, not EoSS)

F5HardwareModel:
  - Add eol_tbd (BooleanField) for hardware whose EoL date has not been published by F5 yet
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('lb_manager', '0012_f5_catalog'),
    ]

    operations = [
        # Rename eoss_date to eosd_date on f5_software_version
        migrations.RenameField(
            model_name='f5softwareversion',
            old_name='eoss_date',
            new_name='eosd_date',
        ),
        migrations.AlterField(
            model_name='f5softwareversion',
            name='eosd_date',
            field=models.DateField(blank=True, null=True, verbose_name='EoSD date'),
        ),

        # Add eol_tbd to f5_hardware_model
        migrations.AddField(
            model_name='f5hardwaremodel',
            name='eol_tbd',
            field=models.BooleanField(default=False, verbose_name='Sin fecha (TBD)'),
        ),
    ]
