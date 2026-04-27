from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('lb_manager', '0008_add_docentry_directoryentry'),
    ]

    operations = [
        migrations.AddField(
            model_name='healthcheckdns',
            name='ntp',
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AddField(
            model_name='healthcheckdns',
            name='swap_total',
            field=models.IntegerField(blank=True, null=True),
        ),
    ]
