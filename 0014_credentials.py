"""
Migration 0014: Add CredentialRotationPolicy and DeviceCredential models.

Creates:
  - credential_rotation_policy table
  - device_credential table (with CheckConstraint: exactly one of lb_physical or lb_guest)
"""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('lb_manager', '0013_f5_catalog_fix'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='CredentialRotationPolicy',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, verbose_name='Nombre')),
                ('days_interval', models.PositiveIntegerField(default=90, verbose_name='Intervalo (días)')),
                ('warn_days_before', models.PositiveIntegerField(default=15, verbose_name='Advertencia (días antes)')),
            ],
            options={
                'verbose_name': 'Credential Rotation Policy',
                'verbose_name_plural': 'Credential Rotation Policies',
                'db_table': 'credential_rotation_policy',
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='DeviceCredential',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('credential_type', models.CharField(
                    choices=[('admin', 'Admin'), ('monitor', 'Monitor User'), ('api', 'API User'), ('root', 'Root')],
                    default='admin',
                    max_length=20,
                    verbose_name='Tipo de credencial',
                )),
                ('last_rotated', models.DateTimeField(blank=True, null=True, verbose_name='Última rotación')),
                ('ticket_ref', models.CharField(blank=True, max_length=100, verbose_name='Ticket')),
                ('notes', models.TextField(blank=True, verbose_name='Notas')),
                ('lb_physical', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='credentials',
                    to='lb_manager.lbphysical',
                    verbose_name='LB Physical',
                )),
                ('lb_guest', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='credentials',
                    to='lb_manager.lbguest',
                    verbose_name='LB Guest',
                )),
                ('policy', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to='lb_manager.credentialrotationpolicy',
                    verbose_name='Política',
                )),
                ('rotated_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Rotado por',
                )),
            ],
            options={
                'verbose_name': 'Device Credential',
                'verbose_name_plural': 'Device Credentials',
                'db_table': 'device_credential',
                'ordering': ['lb_physical', 'lb_guest', 'credential_type'],
            },
        ),
        migrations.AddConstraint(
            model_name='devicecredential',
            constraint=models.CheckConstraint(
                check=(
                    models.Q(lb_physical__isnull=False, lb_guest__isnull=True) |
                    models.Q(lb_physical__isnull=True,  lb_guest__isnull=False)
                ),
                name='credential_exactly_one_device',
            ),
        ),
    ]
