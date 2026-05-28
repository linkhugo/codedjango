"""
Migration 0017: Add CredentialRotationEvent for rotation history.

Each registration of a rotation creates a new event row, preserving
the full audit trail of who rotated what and when.
"""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('lb_manager', '0016_credentialrotation_environment'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='CredentialRotationEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name='ID')),
                ('rotated_at', models.DateTimeField(verbose_name='Fecha de rotación')),
                ('ticket_ref', models.CharField(blank=True, max_length=100,
                                                verbose_name='Ticket')),
                ('notes', models.TextField(blank=True, verbose_name='Notas')),
                ('rotation', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='events',
                    to='lb_manager.credentialrotation',
                    verbose_name='Credencial',
                )),
                ('rotated_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Rotado por',
                )),
            ],
            options={
                'verbose_name': 'Credential Rotation Event',
                'verbose_name_plural': 'Credential Rotation Events',
                'db_table': 'credential_rotation_event',
                'ordering': ['-rotated_at'],
            },
        ),
    ]
