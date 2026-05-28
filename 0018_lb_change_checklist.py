"""
Migration 0018: Add LB Change Checklist models.

Creates:
  - lb_change_template
  - lb_change_template_item
  - lb_change_request
  - lb_change_item_response
"""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('lb_manager', '0017_credentialrotationevent'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='LBChangeTemplate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, verbose_name='Nombre')),
                ('change_type', models.CharField(
                    choices=[('upgrade', 'Software Upgrade'), ('migration', 'Migración'),
                             ('hardware', 'Reemplazo de Hardware'), ('other', 'Otro')],
                    default='upgrade', max_length=10, verbose_name='Tipo de cambio',
                )),
                ('description', models.TextField(blank=True, verbose_name='Descripción')),
                ('active', models.BooleanField(default=True, verbose_name='Activa')),
            ],
            options={
                'verbose_name': 'LB Change Template',
                'verbose_name_plural': 'LB Change Templates',
                'db_table': 'lb_change_template',
                'ordering': ['change_type', 'name'],
            },
        ),
        migrations.CreateModel(
            name='LBChangeTemplateItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name='ID')),
                ('phase', models.CharField(
                    choices=[('pre', 'Pre-Cambio'), ('post', 'Post-Cambio')],
                    max_length=4, verbose_name='Fase',
                )),
                ('order', models.PositiveIntegerField(default=0, verbose_name='Orden')),
                ('text', models.CharField(max_length=300, verbose_name='Verificación')),
                ('required', models.BooleanField(
                    default=True, verbose_name='Obligatorio',
                    help_text='Si está marcado, debe responderse "OK" para poder firmar la fase.',
                )),
                ('template', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='items',
                    to='lb_manager.lbchangetemplate',
                    verbose_name='Plantilla',
                )),
            ],
            options={
                'verbose_name': 'Template Item',
                'verbose_name_plural': 'Template Items',
                'db_table': 'lb_change_template_item',
                'ordering': ['phase', 'order'],
            },
        ),
        migrations.CreateModel(
            name='LBChangeRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=200, verbose_name='Título')),
                ('from_version', models.CharField(
                    blank=True, max_length=100, verbose_name='Versión actual',
                )),
                ('ticket_ref', models.CharField(
                    blank=True, max_length=100, verbose_name='Ticket',
                )),
                ('scheduled_at', models.DateTimeField(
                    blank=True, null=True, verbose_name='Fecha programada',
                )),
                ('status', models.CharField(
                    choices=[
                        ('draft', 'Borrador'),
                        ('pre_pending', 'Pre-cambio pendiente'),
                        ('in_progress', 'En ejecución'),
                        ('post_pending', 'Post-cambio pendiente'),
                        ('completed', 'Completado'),
                        ('cancelled', 'Cancelado'),
                    ],
                    db_index=True, default='pre_pending',
                    max_length=15, verbose_name='Estado',
                )),
                ('notes', models.TextField(blank=True, verbose_name='Notas')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('pre_signed_at', models.DateTimeField(
                    blank=True, null=True, verbose_name='Firma Pre (fecha)',
                )),
                ('post_signed_at', models.DateTimeField(
                    blank=True, null=True, verbose_name='Firma Post (fecha)',
                )),
                ('created_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='lb_changes_created',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Creado por',
                )),
                ('lb_guest', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='change_requests',
                    to='lb_manager.lbguest',
                    verbose_name='LB Guest',
                )),
                ('lb_physical', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='change_requests',
                    to='lb_manager.lbphysical',
                    verbose_name='LB Physical',
                )),
                ('post_signed_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='lb_changes_post_signed',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Firma Post (usuario)',
                )),
                ('pre_signed_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='lb_changes_pre_signed',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Firma Pre (usuario)',
                )),
                ('target_version', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='change_requests',
                    to='lb_manager.f5softwareversion',
                    verbose_name='Versión objetivo',
                )),
                ('template', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to='lb_manager.lbchangetemplate',
                    verbose_name='Plantilla',
                )),
            ],
            options={
                'verbose_name': 'LB Change Request',
                'verbose_name_plural': 'LB Change Requests',
                'db_table': 'lb_change_request',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='LBChangeItemResponse',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name='ID')),
                ('result', models.CharField(
                    choices=[('ok', 'OK'), ('na', 'N/A'), ('fail', 'Fallo')],
                    max_length=4, verbose_name='Resultado',
                )),
                ('comment', models.TextField(blank=True, verbose_name='Comentario')),
                ('at', models.DateTimeField(
                    auto_now=True, verbose_name='Última actualización',
                )),
                ('by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Respondido por',
                )),
                ('change', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='responses',
                    to='lb_manager.lbchangerequest',
                    verbose_name='Cambio',
                )),
                ('item', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    to='lb_manager.lbchangetemplateitem',
                    verbose_name='Ítem',
                )),
            ],
            options={
                'verbose_name': 'Item Response',
                'verbose_name_plural': 'Item Responses',
                'db_table': 'lb_change_item_response',
                'ordering': ['item__phase', 'item__order'],
            },
        ),
        migrations.AlterUniqueTogether(
            name='lbchangeitemresponse',
            unique_together={('change', 'item')},
        ),
    ]
