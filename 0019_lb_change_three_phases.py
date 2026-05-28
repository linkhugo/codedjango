"""
Migration 0019: Extend LB Change Checklist to 3 phases.

Changes:
  - LBChangeTemplateItem.phase: add 'initial', expand max_length to 7
  - LBChangeTemplateItem: add comment_required_on, linked_item
  - LBChangeRequest.status: add 'initial_pending', remove 'post_pending/draft', max_length 16
  - LBChangeRequest: add initial_signed_by, initial_signed_at
  - LBChangeItemResponse.result: change to yes/no/na
"""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('lb_manager', '0018_lb_change_checklist'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ── LBChangeTemplateItem: phase max_length + new fields ───────────────
        migrations.AlterField(
            model_name='lbchangetemplateitem',
            name='phase',
            field=models.CharField(
                choices=[
                    ('initial', 'Validación Inicial'),
                    ('pre',     'Pre-Check'),
                    ('post',    'Post-Check'),
                ],
                max_length=7,
                verbose_name='Fase',
            ),
        ),
        migrations.AlterField(
            model_name='lbchangetemplateitem',
            name='text',
            field=models.CharField(max_length=400, verbose_name='Verificación'),
        ),
        migrations.AlterField(
            model_name='lbchangetemplateitem',
            name='required',
            field=models.BooleanField(
                default=True,
                verbose_name='Obligatorio',
                help_text='Fase initial: debe tener respuesta. Fase pre/post: debe responder Sí.',
            ),
        ),
        migrations.AddField(
            model_name='lbchangetemplateitem',
            name='comment_required_on',
            field=models.CharField(
                blank=True, default='',
                choices=[
                    ('yes', 'Comentario si respuesta es Sí'),
                    ('no',  'Comentario si respuesta es No'),
                ],
                max_length=3,
                verbose_name='Comentario obligatorio',
                help_text='Indica cuándo el operador debe escribir un comentario.',
            ),
        ),
        migrations.AddField(
            model_name='lbchangetemplateitem',
            name='linked_item',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='linked_by',
                to='lb_manager.lbchangetemplateitem',
                verbose_name='Ítem vinculado',
                help_text='Muestra la respuesta/comentario de ese ítem como contexto.',
            ),
        ),
        # ── LBChangeRequest: status + initial signature fields ────────────────
        migrations.AlterField(
            model_name='lbchangerequest',
            name='status',
            field=models.CharField(
                choices=[
                    ('initial_pending', 'Validación Inicial pendiente'),
                    ('pre_pending',     'Pre-Check pendiente'),
                    ('in_progress',     'En ejecución'),
                    ('completed',       'Completado'),
                    ('cancelled',       'Cancelado'),
                ],
                db_index=True,
                default='initial_pending',
                max_length=16,
                verbose_name='Estado',
            ),
        ),
        migrations.AddField(
            model_name='lbchangerequest',
            name='initial_signed_by',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='lb_changes_initial_signed',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Firma Inicial (usuario)',
            ),
        ),
        migrations.AddField(
            model_name='lbchangerequest',
            name='initial_signed_at',
            field=models.DateTimeField(
                blank=True, null=True,
                verbose_name='Firma Inicial (fecha)',
            ),
        ),
        # ── LBChangeItemResponse.result: yes/no/na ────────────────────────────
        migrations.AlterField(
            model_name='lbchangeitemresponse',
            name='result',
            field=models.CharField(
                choices=[('yes', 'Sí'), ('no', 'No'), ('na', 'N/A')],
                max_length=4,
                verbose_name='Resultado',
            ),
        ),
    ]
