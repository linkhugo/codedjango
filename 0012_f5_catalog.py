"""
Migration: F5 software version and hardware model catalog tables.

Creates:
  - f5_software_version  (version, eoss_date, eots_date, notes)
  - f5_hardware_model    (name, eoss_date, eots_date, notes)

Adds nullable FK columns to lb_physical and lb_guest:
  - f5_version_id  → f5_software_version
  - f5_model_id    → f5_hardware_model
"""
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('lb_manager', '0011_lb_decommissioned'),
    ]

    operations = [
        # ── New catalog tables ─────────────────────────────────────────────────
        migrations.CreateModel(
            name='F5SoftwareVersion',
            fields=[
                ('id',        models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('version',   models.CharField(max_length=100, unique=True)),
                ('eoss_date', models.DateField(blank=True, null=True, verbose_name='EoSS date')),
                ('eots_date', models.DateField(blank=True, null=True, verbose_name='EoTS date')),
                ('notes',     models.TextField(blank=True, default='')),
            ],
            options={
                'verbose_name': 'F5 Software Version',
                'verbose_name_plural': 'F5 Software Versions',
                'db_table': 'f5_software_version',
                'ordering': ['version'],
            },
        ),
        migrations.CreateModel(
            name='F5HardwareModel',
            fields=[
                ('id',        models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name',      models.CharField(max_length=100, unique=True)),
                ('eoss_date', models.DateField(blank=True, null=True, verbose_name='EoSS date')),
                ('eots_date', models.DateField(blank=True, null=True, verbose_name='EoTS date')),
                ('notes',     models.TextField(blank=True, default='')),
            ],
            options={
                'verbose_name': 'F5 Hardware Model',
                'verbose_name_plural': 'F5 Hardware Models',
                'db_table': 'f5_hardware_model',
                'ordering': ['name'],
            },
        ),

        # ── FK columns on lb_physical ──────────────────────────────────────────
        migrations.AddField(
            model_name='lbphysical',
            name='f5_version',
            field=models.ForeignKey(
                blank=True, null=True,
                db_column='f5_version_id',
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='lb_physicals',
                to='lb_manager.f5softwareversion',
            ),
        ),
        migrations.AddField(
            model_name='lbphysical',
            name='f5_model',
            field=models.ForeignKey(
                blank=True, null=True,
                db_column='f5_model_id',
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='lb_physicals',
                to='lb_manager.f5hardwaremodel',
            ),
        ),

        # ── FK columns on lb_guest ─────────────────────────────────────────────
        migrations.AddField(
            model_name='lbguest',
            name='f5_version',
            field=models.ForeignKey(
                blank=True, null=True,
                db_column='f5_version_id',
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='lb_guests',
                to='lb_manager.f5softwareversion',
            ),
        ),
        migrations.AddField(
            model_name='lbguest',
            name='f5_model',
            field=models.ForeignKey(
                blank=True, null=True,
                db_column='f5_model_id',
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='lb_guests',
                to='lb_manager.f5hardwaremodel',
            ),
        ),
    ]
