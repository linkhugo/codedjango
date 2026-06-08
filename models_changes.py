"""
Modelos para gestión de cambios planificados en LB (upgrades y migraciones).

Incluye: LBChangeTemplate, LBChangeTemplateItem, LBChangeRequest, LBChangeItemResponse.

Separado de models.py para mantener cada archivo por debajo de 1000 líneas.
"""
from django.conf import settings
from django.db import models


class LBChangeTemplate(models.Model):
    """
    Plantilla de checklist para un tipo de operación sobre un LB.

    Define los ítems de verificación pre y post cambio que se aplicarán
    a cada instancia de cambio que use esta plantilla.

    Args:
        name:        Nombre descriptivo (ej. "F5 Software Upgrade").
        change_type: Categoría de la operación.
        description: Descripción del procedimiento (opcional).
        active:      Si False, no aparece al crear nuevos cambios.
    """

    CHANGE_TYPE = [
        ('upgrade',   'Software Upgrade'),
        ('migration', 'Migración'),
        ('hardware',  'Reemplazo de Hardware'),
        ('other',     'Otro'),
    ]

    name        = models.CharField(max_length=100, verbose_name='Nombre')
    change_type = models.CharField(
        max_length=10, choices=CHANGE_TYPE, default='upgrade',
        verbose_name='Tipo de cambio',
    )
    description = models.TextField(blank=True, verbose_name='Descripción')
    active      = models.BooleanField(default=True, verbose_name='Activa')

    class Meta:
        db_table            = 'lb_change_template'
        ordering            = ['change_type', 'name']
        verbose_name        = 'LB Change Template'
        verbose_name_plural = 'LB Change Templates'

    def __str__(self) -> str:
        return f'{self.name} ({self.get_change_type_display()})'


class LBChangeTemplateItem(models.Model):
    """
    Ítem de verificación dentro de una plantilla de cambio.

    Args:
        template:           Plantilla a la que pertenece.
        phase:              'initial' (validación), 'pre' (pre-check) o 'post' (post-check).
        order:              Posición en la lista (ascendente).
        text:               Texto de la pregunta / verificación.
        required:           Si True, debe responderse para poder firmar la fase.
        comment_required_on: Cuándo es obligatorio escribir un comentario: 'yes', 'no' o ''.
        linked_item:        Referencia a otro ítem cuya respuesta/comentario se mostrará aquí.
    """

    PHASE = [
        ('initial', 'Validación Inicial'),
        ('pre',     'Pre-Check'),
        ('post',    'Post-Check'),
    ]
    COMMENT_ON = [
        ('yes', 'Comentario si respuesta es Sí'),
        ('no',  'Comentario si respuesta es No'),
    ]

    template = models.ForeignKey(
        LBChangeTemplate, on_delete=models.CASCADE,
        related_name='items', verbose_name='Plantilla',
    )
    phase    = models.CharField(max_length=7, choices=PHASE, verbose_name='Fase')
    order    = models.PositiveIntegerField(default=0, verbose_name='Orden')
    text     = models.CharField(max_length=400, verbose_name='Verificación')
    required = models.BooleanField(
        default=True,
        verbose_name='Obligatorio',
        help_text='Fase initial: debe tener respuesta. Fase pre/post: debe responder Sí.',
    )
    comment_required_on = models.CharField(
        max_length=3, choices=COMMENT_ON, blank=True, default='',
        verbose_name='Comentario obligatorio',
        help_text='Indica cuándo el operador debe escribir un comentario.',
    )
    linked_item = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='linked_by', verbose_name='Ítem vinculado',
        help_text='Muestra la respuesta/comentario de ese ítem como contexto.',
    )

    class Meta:
        db_table            = 'lb_change_template_item'
        ordering            = ['phase', 'order']
        verbose_name        = 'Template Item'
        verbose_name_plural = 'Template Items'

    def __str__(self) -> str:
        text = str(self.text or '')
        return f'[{self.get_phase_display()}] {text[:60]}'


class LBChangeRequest(models.Model):
    """
    Instancia de un cambio planificado sobre un LB específico.

    Ciclo de vida:
        initial_pending → pre_pending → in_progress → completed
                                                     ↘ cancelled

    La firma pre valida que todos los ítems pre required = 'ok'.
    La firma post valida que todos los ítems post required = 'ok'.

    Args:
        title:          Descripción corta del cambio.
        template:       Plantilla de checklist utilizada.
        lb_physical:    LB físico intervenido (exclusivo con lb_guest).
        lb_guest:       LB virtual intervenido (exclusivo con lb_physical).
        from_version:   Versión actual antes del upgrade (texto libre).
        target_version: Versión objetivo (FK al catálogo F5SoftwareVersion).
        ticket_ref:     Número de ticket de cambio (CHG0012345).
        scheduled_at:   Fecha/hora programada del cambio.
        status:         Estado actual del ciclo de vida.
        notes:          Notas adicionales del operador.
        created_by:     Usuario que creó el cambio.
        pre_signed_by:  Usuario que firmó el pre-cambio.
        pre_signed_at:  Fecha/hora de la firma pre.
        post_signed_by: Usuario que firmó el post-cambio.
        post_signed_at: Fecha/hora de la firma post.
    """

    STATUS = [
        ('initial_pending', 'Validación Inicial pendiente'),
        ('pre_pending',     'Pre-Check pendiente'),
        ('in_progress',     'En ejecución'),
        ('completed',       'Completado'),
        ('cancelled',       'Cancelado'),
    ]

    title          = models.CharField(max_length=200, verbose_name='Título')
    template       = models.ForeignKey(
        LBChangeTemplate, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name='Plantilla',
    )
    lb_physical    = models.ForeignKey(
        'LBPhysical', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='change_requests', verbose_name='LB Physical',
    )
    lb_guest       = models.ForeignKey(
        'LBGuest', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='change_requests', verbose_name='LB Guest',
    )
    from_version   = models.CharField(
        max_length=100, blank=True, verbose_name='Versión actual',
    )
    target_version = models.ForeignKey(
        'F5SoftwareVersion', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='change_requests', verbose_name='Versión objetivo',
    )
    ticket_ref     = models.CharField(max_length=100, blank=True, verbose_name='Ticket')
    scheduled_at   = models.DateTimeField(null=True, blank=True, verbose_name='Fecha programada')
    status         = models.CharField(
        max_length=16, choices=STATUS, default='initial_pending',
        verbose_name='Estado', db_index=True,
    )
    initial_signed_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='lb_changes_initial_signed', verbose_name='Firma Inicial (usuario)',
    )
    initial_signed_at  = models.DateTimeField(
        null=True, blank=True, verbose_name='Firma Inicial (fecha)',
    )
    notes          = models.TextField(blank=True, verbose_name='Notas')
    created_by     = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='lb_changes_created', verbose_name='Creado por',
    )
    created_at     = models.DateTimeField(auto_now_add=True)
    pre_signed_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='lb_changes_pre_signed', verbose_name='Firma Pre (usuario)',
    )
    pre_signed_at  = models.DateTimeField(null=True, blank=True, verbose_name='Firma Pre (fecha)')
    post_signed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='lb_changes_post_signed', verbose_name='Firma Post (usuario)',
    )
    post_signed_at = models.DateTimeField(null=True, blank=True, verbose_name='Firma Post (fecha)')

    postmortem_had_issues = models.BooleanField(
        default=False,
        verbose_name='¿Hubo detalles?',
        help_text='Marcar si durante la ejecución del cambio surgió algún incidente o detalle a documentar.',
    )
    postmortem_notes      = models.TextField(
        blank=True, default='',
        verbose_name='Post-Validaciones / detalles',
        help_text='Descripción de lo ocurrido y qué tomar en cuenta para el próximo cambio sobre el mismo dispositivo.',
    )
    postmortem_filled_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='lb_changes_postmortem_filled',
        verbose_name='Post-Mortem llenado por',
    )
    postmortem_filled_at  = models.DateTimeField(
        null=True, blank=True,
        verbose_name='Post-Mortem llenado (fecha)',
    )

    class Meta:
        db_table            = 'lb_change_request'
        ordering            = ['-created_at']
        verbose_name        = 'LB Change Request'
        verbose_name_plural = 'LB Change Requests'

    @property
    def device_fqdn(self) -> str:
        """FQDN del dispositivo intervenido."""
        return self.lb_physical_id or self.lb_guest_id or '—'

    @property
    def device_company(self):
        """Empresa del dispositivo (para mostrar en tablas)."""
        if self.lb_physical_id:
            return self.lb_physical.company
        if self.lb_guest_id:
            return self.lb_guest.company
        return None

    def __str__(self) -> str:
        return f'{self.ticket_ref or self.pk} — {self.device_fqdn}'


class LBChangeItemResponse(models.Model):
    """
    Respuesta de un operador a un ítem del checklist.

    Una fila por (change_request, item). Se actualiza con update_or_create
    cada vez que el operador cambia su respuesta.

    Args:
        change:  ChangeRequest al que pertenece.
        item:    Ítem de la plantilla respondido.
        result:  'ok', 'na' (no aplica) o 'fail'.
        comment: Comentario opcional del operador.
        by:      Usuario que respondió.
        at:      Fecha/hora de la última respuesta (auto).
    """

    RESULT = [
        ('yes', 'Sí'),
        ('no',  'No'),
        ('na',  'N/A'),
    ]

    change  = models.ForeignKey(
        LBChangeRequest, on_delete=models.CASCADE,
        related_name='responses', verbose_name='Cambio',
    )
    item    = models.ForeignKey(
        LBChangeTemplateItem, on_delete=models.CASCADE,
        verbose_name='Ítem',
    )
    result  = models.CharField(max_length=4, choices=RESULT, verbose_name='Resultado')
    comment = models.TextField(blank=True, verbose_name='Comentario')
    by      = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name='Respondido por',
    )
    at      = models.DateTimeField(auto_now=True, verbose_name='Última actualización')

    # ── Snapshot inmutable del item al momento de crear la respuesta ──────
    # Permite que la edición del item de plantilla NO afecte el contexto
    # histórico de cambios ya iniciados. El workspace usa estos campos como
    # fuente de verdad cuando están llenos; si están vacíos (registros
    # pre-migración) cae al ``item`` vivo.
    item_phase_snapshot              = models.CharField(max_length=10, blank=True, default='')
    item_order_snapshot              = models.PositiveIntegerField(default=0)
    item_text_snapshot               = models.CharField(max_length=400, blank=True, default='')
    item_required_snapshot           = models.BooleanField(default=False)
    item_comment_required_on_snapshot = models.CharField(max_length=3, blank=True, default='')

    class Meta:
        db_table            = 'lb_change_item_response'
        unique_together     = [('change', 'item')]
        ordering            = ['item__phase', 'item__order']
        verbose_name        = 'Item Response'
        verbose_name_plural = 'Item Responses'

    def __str__(self) -> str:
        return f'{self.change} / {self.item} → {self.result}'
