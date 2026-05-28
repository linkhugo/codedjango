"""
Migration 0015: Replace per-device DeviceCredential with group-level CredentialRotation.

Drops:
  - device_credential table (DeviceCredential model)

Creates:
  - credential_rotation table (CredentialRotation model)
    unique_together: (device_type, credential_type) — one row per group.
"""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('lb_manager', '0014_credentials'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.DeleteModel(name='DeviceCredential'),
        migrations.CreateModel(
            name='CredentialRotation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name='ID')),
                ('device_type', models.CharField(
                    choices=[('f5', 'F5'), ('infoblox', 'Infoblox'), ('other', 'Otros')],
                    max_length=20, verbose_name='Tipo de equipo',
                )),
                ('credential_type', models.CharField(
                    choices=[('admin', 'Admin'), ('root', 'Root'),
                             ('monitor', 'Monitor User'), ('api', 'API User')],
                    default='admin', max_length=20, verbose_name='Tipo de credencial',
                )),
                ('last_rotated', models.DateTimeField(blank=True, null=True,
                                                      verbose_name='Última rotación')),
                ('ticket_ref', models.CharField(blank=True, max_length=100,
                                                verbose_name='Ticket')),
                ('notes', models.TextField(blank=True, verbose_name='Notas')),
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
                'verbose_name': 'Credential Rotation',
                'verbose_name_plural': 'Credential Rotations',
                'db_table': 'credential_rotation',
                'ordering': ['device_type', 'credential_type'],
            },
        ),
        migrations.AlterUniqueTogether(
            name='credentialrotation',
            unique_together={('device_type', 'credential_type')},
        ),
    ]
