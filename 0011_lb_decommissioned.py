import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('lb_manager', '0010_healthcheckdns_ntp_swap_total'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='LBDecommissioned',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('device', models.CharField(max_length=255)),
                ('device_type', models.CharField(choices=[('Physical', 'Physical LB'), ('Guest', 'Guest LB')], max_length=10)),
                ('ci_id', models.CharField(blank=True, max_length=255, null=True)),
                ('mgmt_ip', models.CharField(blank=True, max_length=45, null=True)),
                ('version', models.CharField(blank=True, max_length=255, null=True)),
                ('model', models.CharField(blank=True, max_length=255, null=True)),
                ('serial', models.CharField(blank=True, max_length=255, null=True)),
                ('environment', models.CharField(blank=True, max_length=255, null=True)),
                ('company', models.CharField(blank=True, max_length=100, null=True)),
                ('comments', models.TextField(blank=True, null=True)),
                ('decommissioned_at', models.DateTimeField(auto_now_add=True)),
                ('decommissioned_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='decomissions',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'db_table': 'lb_decommissioned',
                'ordering': ['-decommissioned_at'],
            },
        ),
    ]
