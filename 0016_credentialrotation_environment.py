"""
Migration 0016: Add environment field to CredentialRotation.

Changes unique_together from (device_type, credential_type)
to (device_type, credential_type, environment) so the same
credential type can have different policies per environment.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('lb_manager', '0015_credential_rotation'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='credentialrotation',
            unique_together=set(),
        ),
        migrations.AddField(
            model_name='credentialrotation',
            name='environment',
            field=models.CharField(
                choices=[
                    ('PRODUCTION',     'Producción'),
                    ('PRE-PRODUCTION', 'Pre-Producción'),
                    ('DRP',            'DRP'),
                    ('ALL',            'Todos los entornos'),
                ],
                default='ALL',
                max_length=20,
                verbose_name='Entorno',
            ),
        ),
        migrations.AlterUniqueTogether(
            name='credentialrotation',
            unique_together={('device_type', 'credential_type', 'environment')},
        ),
    ]
