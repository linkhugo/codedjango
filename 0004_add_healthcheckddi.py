from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ddi_manager', '0003_ddidevice_tipo'),
    ]

    operations = [
        migrations.CreateModel(
            name='HealthCheckDDI',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('fqdn', models.CharField(db_index=True, max_length=255)),
                ('fecha', models.DateField(db_index=True)),
                ('platform', models.CharField(blank=True, max_length=32, null=True)),
                ('grid_status', models.CharField(blank=True, max_length=64, null=True)),
                ('is_ha', models.BooleanField(default=False)),
                ('ha_state', models.CharField(blank=True, max_length=64, null=True)),
                ('pnode_role', models.CharField(blank=True, max_length=64, null=True)),
                ('master_candidate', models.BooleanField(default=False)),
                ('dns_service', models.CharField(blank=True, max_length=64, null=True)),
                ('dns_zones_count', models.IntegerField(default=0)),
                ('dns_zones_disabled', models.IntegerField(default=0)),
                ('dhcp_service', models.CharField(blank=True, max_length=64, null=True)),
                ('dhcp_failover', models.CharField(blank=True, max_length=64, null=True)),
                ('leases_activos', models.IntegerField(default=0)),
                ('leases_abandonados', models.IntegerField(default=0)),
                ('leases_declinados', models.IntegerField(default=0)),
                ('networks_total', models.IntegerField(default=0)),
                ('networks_en_riesgo', models.IntegerField(default=0)),
                ('networks_criticas', models.IntegerField(default=0)),
                ('backup_enabled', models.CharField(blank=True, max_length=8, null=True)),
                ('backup_status', models.CharField(blank=True, max_length=64, null=True)),
                ('backup_tipo', models.CharField(blank=True, max_length=32, null=True)),
                ('ntp_enabled', models.CharField(blank=True, max_length=8, null=True)),
                ('ntp_servers_count', models.IntegerField(default=0)),
                ('cpu_pct', models.IntegerField(blank=True, null=True)),
                ('mem_pct', models.IntegerField(blank=True, null=True)),
                ('disk_pct', models.IntegerField(blank=True, null=True)),
                ('uptime_dias', models.IntegerField(blank=True, null=True)),
            ],
            options={
                'verbose_name': 'DDI Health Check',
                'verbose_name_plural': 'DDI Health Checks',
                'db_table': 'health_check_ddi',
                'ordering': ['-fecha', 'fqdn'],
            },
        ),
        migrations.AlterUniqueTogether(
            name='healthcheckddi',
            unique_together={('fqdn', 'fecha')},
        ),
    ]
