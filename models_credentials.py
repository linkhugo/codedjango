"""
Modelos de rotación de credenciales por grupo de equipos.

Incluye: CredentialRotationPolicy, CredentialRotation.

Separado de models.py para mantener cada archivo por debajo de 1000 líneas.
La app nunca almacena passwords — solo metadatos del evento de rotación.

Diseño: una fila por (device_type, credential_type).
Al rotar, se marca toda la familia de equipos (p.ej. "todos los F5").
"""
from datetime import date

from django.conf import settings
from django.db import models


class CredentialRotationPolicy(models.Model):
    """
    Política de rotación: define el intervalo en días y los días de advertencia.

    Args:
        name:             Nombre descriptivo (p.ej. "Producción 90 días").
        days_interval:    Días máximos entre rotaciones.
        warn_days_before: Días de antelación para mostrar advertencia.
    """

    name             = models.CharField(max_length=100, verbose_name='Nombre')
    days_interval    = models.PositiveIntegerField(default=90, verbose_name='Intervalo (días)')
    warn_days_before = models.PositiveIntegerField(default=15, verbose_name='Advertencia (días antes)')

    class Meta:
        db_table            = 'credential_rotation_policy'
        ordering            = ['name']
        verbose_name        = 'Credential Rotation Policy'
        verbose_name_plural = 'Credential Rotation Policies'

    def __str__(self) -> str:
        return f'{self.name} ({self.days_interval} días)'


class CredentialRotation(models.Model):
    """
    Registro de la última rotación de una credencial para un grupo de equipos.

    Una fila representa "el password de tipo X en todos los equipos de tipo Y".
    La combinación (device_type, credential_type) es única.

    Args:
        device_type:     Familia de equipos: F5, Infoblox u Otros.
        credential_type: Tipo de credencial: admin, root, monitor, api.
        policy:          Política de rotación aplicada (opcional).
        last_rotated:    Fecha/hora de la última rotación registrada.
        rotated_by:      Usuario que registró la rotación.
        ticket_ref:      Referencia al ticket de cambio (opcional).
        notes:           Notas adicionales (opcional).

    Returns:
        status: 'ok' | 'warning' | 'overdue' | 'unknown'
    """

    DEVICE_TYPE_CHOICES = [
        ('f5',       'F5'),
        ('infoblox', 'Infoblox'),
        ('other',    'Otros'),
    ]

    CRED_CHOICES = [
        ('admin',   'Admin'),
        ('root',    'Root'),
        ('monitor', 'Monitor User'),
        ('api',     'API User'),
    ]

    ENVIRONMENT_CHOICES = [
        ('PRODUCTION',     'Producción'),
        ('PRE-PRODUCTION', 'Pre-Producción'),
        ('DRP',            'DRP'),
        ('ALL',            'Todos los entornos'),
    ]

    device_type = models.CharField(
        max_length=20, choices=DEVICE_TYPE_CHOICES,
        verbose_name='Tipo de equipo',
    )
    credential_type = models.CharField(
        max_length=20, choices=CRED_CHOICES, default='admin',
        verbose_name='Tipo de credencial',
    )
    environment = models.CharField(
        max_length=20, choices=ENVIRONMENT_CHOICES, default='ALL',
        verbose_name='Entorno',
    )
    policy = models.ForeignKey(
        CredentialRotationPolicy, null=True, blank=True,
        on_delete=models.SET_NULL, verbose_name='Política',
    )
    last_rotated = models.DateTimeField(null=True, blank=True, verbose_name='Última rotación')
    rotated_by   = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, verbose_name='Rotado por',
    )
    ticket_ref = models.CharField(max_length=100, blank=True, verbose_name='Ticket')
    notes      = models.TextField(blank=True, verbose_name='Notas')

    class Meta:
        db_table            = 'credential_rotation'
        unique_together     = [('device_type', 'credential_type', 'environment')]
        ordering            = ['device_type', 'credential_type']
        verbose_name        = 'Credential Rotation'
        verbose_name_plural = 'Credential Rotations'

    # ── Propiedades calculadas ────────────────────────────────────────────────

    @property
    def days_since_rotation(self) -> int | None:
        """Días transcurridos desde la última rotación, o None si nunca se rotó."""
        if not self.last_rotated:
            return None
        return (date.today() - self.last_rotated.date()).days

    @property
    def days_remaining(self) -> int | None:
        """Días que faltan para que venza según la política, o None sin política/rotación."""
        if not self.policy or self.days_since_rotation is None:
            return None
        return self.policy.days_interval - self.days_since_rotation

    @property
    def status(self) -> str:
        """Estado: 'ok', 'warning', 'overdue' o 'unknown'."""
        remaining = self.days_remaining
        if remaining is None:
            return 'unknown'
        if remaining <= 0:
            return 'overdue'
        warn = self.policy.warn_days_before if self.policy else 15
        return 'warning' if remaining <= warn else 'ok'

    def __str__(self) -> str:
        return (
            f'{self.get_device_type_display()} — '
            f'{self.get_credential_type_display()} '
            f'[{self.get_environment_display()}]'
        )


class CredentialRotationEvent(models.Model):
    """
    Registro histórico de cada evento de rotación de credencial.

    Cada vez que se registra una rotación en CredentialRotation se crea
    una nueva fila aquí. Permite auditar quién rotó, cuándo y con qué ticket.

    Args:
        rotation:   Grupo de credencial al que pertenece este evento.
        rotated_at: Fecha/hora en que se registró la rotación.
        rotated_by: Usuario que registró el evento.
        ticket_ref: Ticket de cambio asociado (opcional).
        notes:      Notas del operador (opcional).
    """

    rotation   = models.ForeignKey(
        CredentialRotation, on_delete=models.CASCADE,
        related_name='events', verbose_name='Credencial',
    )
    rotated_at = models.DateTimeField(verbose_name='Fecha de rotación')
    rotated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, verbose_name='Rotado por',
    )
    ticket_ref = models.CharField(max_length=100, blank=True, verbose_name='Ticket')
    notes      = models.TextField(blank=True, verbose_name='Notas')

    class Meta:
        db_table            = 'credential_rotation_event'
        ordering            = ['-rotated_at']
        verbose_name        = 'Credential Rotation Event'
        verbose_name_plural = 'Credential Rotation Events'

    def __str__(self) -> str:
        return f'{self.rotation} — {self.rotated_at:%Y-%m-%d %H:%M}'
