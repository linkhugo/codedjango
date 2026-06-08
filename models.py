"""
Modelos centrales y fachada de re-exports del paquete `lb_manager`.

Este archivo contiene los modelos **transversales** (Company, Datacenter,
catálogo F5, autenticación LDAP, settings globales y audit log). El resto
de los modelos vive en archivos hermanos por dominio:

  - models_infrastructure.py  → LBPhysical, LBGuest, LBDecommissioned
  - models_ltm.py             → Servicio, LTMNode, Pool, SelfIP,
                                SNATTranslation, VIP, LBVIPHistorical
  - models_ssl.py             → ClientSSLProfile, SSLCert
  - models_health.py          → HealthCheck* (DHCP/DNS/F5/Certificate),
                                HealthRule, BitacoraHealth, BitacoraEvent
  - models_hardening.py       → LBHardening, BitacoraHardening + signal
  - models_credentials.py     → CredentialRotationPolicy / Rotation / Event
  - models_changes.py         → LBChangeTemplate / TemplateItem / Request /
                                ItemResponse
  - models_meetings.py        → F5Meeting / F5Agreement
  - models_config.py          → SiteSettings auxiliares (CMDB, CSVImport,
                                CSVTableUpload, ScriptRunConfig, Ansible*,
                                DocEntry, DirectoryEntry)

Importar desde el código sigue funcionando como antes:

    from lb_manager.models import LBPhysical, Pool, VIP, BitacoraHealth

porque los re-exports al final de este archivo exponen todos los nombres
en el namespace `lb_manager.models`.
"""
from django.conf import settings
from django.contrib.auth.models import Group
from django.db import models


class Company(models.Model):
    """Cliente o empresa a la que pertenecen los equipos de infraestructura."""
    client_code = models.CharField(max_length=50, blank=True, null=True)
    name = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        db_table = 'company'
        verbose_name = 'Company'
        verbose_name_plural = 'Companies'

    def __str__(self):
        return str(self.name or self.id)


class Datacenter(models.Model):
    """Ubicación física donde se aloja el equipamiento."""
    datacenter = models.CharField(max_length=50, blank=True, null=True)
    location = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        db_table = 'datacenter'
        verbose_name = 'Datacenter'

    def __str__(self):
        return str(self.datacenter or self.id)


class F5SoftwareVersion(models.Model):
    """
    Versión de software F5 BIG-IP.

    Campos de ciclo de vida para software:
      - eosd_date: End of Software Development — F5 deja de publicar parches
      - eots_date: End of Technical Support    — F5 deja de ofrecer soporte técnico
    """

    version    = models.CharField(max_length=100, unique=True)
    eosd_date  = models.DateField(null=True, blank=True, verbose_name='EoSD date')
    eots_date  = models.DateField(null=True, blank=True, verbose_name='EoTS date')
    notes      = models.TextField(blank=True, default='')

    class Meta:
        db_table        = 'f5_software_version'
        ordering        = ['version']
        verbose_name    = 'F5 Software Version'
        verbose_name_plural = 'F5 Software Versions'

    def __str__(self) -> str:
        return str(self.version or '')


class F5HardwareModel(models.Model):
    """
    Modelo de hardware F5 BIG-IP.

    Campos de ciclo de vida para hardware:
      - eoss_date: End of Software Support    — F5 deja de publicar software para este hardware
      - eots_date: End of Technical Support   — F5 deja de ofrecer soporte técnico
      - eol_tbd:   True cuando el vendor aún no ha publicado la fecha de fin de vida
    """

    name       = models.CharField(max_length=100, unique=True)
    eoss_date  = models.DateField(null=True, blank=True, verbose_name='EoSS date')
    eots_date  = models.DateField(null=True, blank=True, verbose_name='EoTS date')
    eol_tbd    = models.BooleanField(default=False, verbose_name='Sin fecha (TBD)')
    notes      = models.TextField(blank=True, default='')

    class Meta:
        db_table        = 'f5_hardware_model'
        ordering        = ['name']
        verbose_name    = 'F5 Hardware Model'
        verbose_name_plural = 'F5 Hardware Models'

    def __str__(self) -> str:
        return str(self.name or '')


class LDAPGroupMap(models.Model):
    """ Mapea un DN contenedor de LDAP a un Group de Django. El backend LDAP lee esta tabla en cada login para construir templates de DN, asignar el grupo y otorgar is_staff/is_superuser. """
    container_dn = models.CharField(
        max_length=500, unique=True,
        verbose_name='LDAP Container DN',
        help_text='Parent container of users in this group. e.g. cn=web_team,dc=corp,dc=local',
    )
    dn_template = models.CharField(
        max_length=500,
        verbose_name='DN Template',
        help_text='Full DN template for users in this container. Use %(user)s as placeholder. e.g. cn=%(user)s,cn=web_team,dc=corp,dc=local',
    )
    django_group = models.ForeignKey(
        Group, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name='Django Group',
        help_text='Django Group to assign to authenticated users from this container. Controls which menus and permissions they have.',
    )
    grants_superuser = models.BooleanField(
        default=False,
        verbose_name='Grants Superuser',
        help_text='If checked, users in this container become Django superusers (full admin access). Takes precedence over Django Group permissions.',
    )
    order = models.PositiveSmallIntegerField(
        default=0,
        verbose_name='Try Order',
        help_text='Templates are tried in ascending order during login. Lower number = tried first.',
    )
    active = models.BooleanField(
        default=True,
        verbose_name='Active',
        help_text='Uncheck to disable this mapping without deleting it.',
    )

    class Meta:
        db_table = 'ldap_group_map'
        verbose_name = 'LDAP Group Mapping'
        verbose_name_plural = 'LDAP Group Mappings'
        ordering = ['order', 'container_dn']
        permissions = [
            ('view_wiki',   'Can view Wiki'),
            ('view_charts', 'Can view Charts'),
        ]

    def __str__(self):
        group_name = self.django_group.name if self.django_group else '(no group)'
        return f'{self.container_dn} → {group_name}'


class GroupProfile(models.Model):
    """Extiende el Group de Django con configuración específica de la aplicación."""
    group = models.OneToOneField(Group, on_delete=models.CASCADE, related_name='profile', verbose_name='Group')
    login_redirect_url = models.CharField(
        max_length=200, blank=True, default='',
        verbose_name='Login Redirect URL',
        help_text='URL to redirect after login. Leave blank for default (Dashboard). Example: /ssl/certs/',
    )

    class Meta:
        db_table = 'group_profile'
        verbose_name = 'Group Profile'
        verbose_name_plural = 'Group Profiles'

    def __str__(self):
        return self.group.name


class SiteSettings(models.Model):
    """Configuración global de la aplicación gestionada desde Admin. Solo se usa el primer registro."""
    axes_failure_limit = models.PositiveSmallIntegerField(default=5, verbose_name='Max Login Attempts')
    axes_cooldown_minutes = models.PositiveSmallIntegerField(default=15, verbose_name='Lockout Duration (minutes)')
    decommission_lookback_months = models.PositiveSmallIntegerField(default=3, verbose_name='Decommission Lookback (months)')
    datatable_max_rows = models.PositiveIntegerField(default=5000, verbose_name='DataTable Max Rows')
    dashboard_history_days = models.PositiveSmallIntegerField(default=7, verbose_name='Dashboard History (days)')
    dashboard_recent_alerts = models.PositiveSmallIntegerField(default=10, verbose_name='Recent Alerts Shown')
    dashboard_recent_health = models.PositiveSmallIntegerField(default=5, verbose_name='Recent Health Checks Shown')
    dashboard_recent_wiki_actions = models.PositiveSmallIntegerField(default=20, verbose_name='Recent Wiki Actions Shown')
    global_search_results_per_type = models.PositiveSmallIntegerField(default=100, verbose_name='Global Search Results per Type')
    bitacora_max_comment_length = models.PositiveIntegerField(default=2000, verbose_name='Bitácora Max Comment Length')
    ddi_device_history_limit = models.PositiveSmallIntegerField(default=200, verbose_name='DDI Device History Limit')
    lb_device_history_limit = models.PositiveSmallIntegerField(default=200, verbose_name='LB Device History Limit')
    inventory_recent_changes_limit = models.PositiveSmallIntegerField(default=50, verbose_name='Inventory Recent Changes Limit')
    health_check_dates_limit = models.PositiveSmallIntegerField(default=60, verbose_name='Health Check Dates Limit')
    bulk_close_limit = models.PositiveSmallIntegerField(default=500, verbose_name='Bulk Close Limit')
    csv_export_limit = models.PositiveIntegerField(default=1000, verbose_name='CSV Export Limit')
    datatable_default_page_length = models.PositiveSmallIntegerField(default=25, verbose_name='DataTable Default Page Length')
    backup_path = models.CharField(max_length=512, default='/backups', verbose_name='Backup Path')
    backup_pg_dump_path = models.CharField(max_length=512, blank=True, default='', verbose_name='pg_dump Binary Path')
    backup_retention_days = models.PositiveSmallIntegerField(default=30, verbose_name='Backup Retention (days)')
    backup_schedule = models.CharField(max_length=100, default='0 2 * * *', verbose_name='Backup Schedule (cron)')

    class Meta:
        db_table = 'site_settings'
        verbose_name = 'Site Settings'
        verbose_name_plural = 'Site Settings'

    def __str__(self):
        return f'Site Settings (limit={self.axes_failure_limit}, cooldown={self.axes_cooldown_minutes}m)'


class LDAPConfig(models.Model):
    """Configuración de conexión al servidor LDAP, gestionada desde Admin. El backend lee el primer registro activo en cada login."""
    server_uri = models.CharField(
        max_length=255,
        verbose_name='LDAP Server URI',
        help_text='e.g. ldap://ldap.corp.local  or  ldaps://ldap.corp.local:636',
    )
    use_tls = models.BooleanField(
        default=False,
        verbose_name='Use STARTTLS',
        help_text='Enable STARTTLS upgrade on the connection (only valid with ldap://).',
    )
    active = models.BooleanField(
        default=True,
        verbose_name='Active',
        help_text='Only the first active record is used. Uncheck to disable without deleting.',
    )
    network_timeout = models.PositiveSmallIntegerField(
        default=10,
        verbose_name='Network Timeout (seconds)',
        help_text='Seconds to wait for a response from the LDAP server before giving up.',
    )

    class Meta:
        db_table = 'ldap_config'
        verbose_name = 'LDAP Configuration'
        verbose_name_plural = 'LDAP Configuration'

    def __str__(self):
        state = 'active' if self.active else 'inactive'
        return f'{self.server_uri} ({state})'


class LoginAuditLog(models.Model):
    """Registra cada intento de login (éxito o fallo) con IP y timestamp."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='login_audit_logs')
    username_attempted = models.CharField(max_length=150)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    success = models.BooleanField(default=False)

    class Meta:
        db_table = 'login_audit_log'
        ordering = ['-timestamp']

    def __str__(self):
        status = 'OK' if self.success else 'FAIL'
        return f'[{status}] {self.username_attempted} @ {self.timestamp}'


class LBDeviceChangeLog(models.Model):
    """Cambios a nivel de campo en dispositivos LBPhysical y LBGuest."""
    DEVICE_TYPE_CHOICES = [('guest', 'Guest LB'), ('physical', 'Physical LB')]
    device = models.CharField(max_length=255, db_index=True)
    device_type = models.CharField(max_length=20, choices=DEVICE_TYPE_CHOICES)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='lb_device_changes')
    timestamp = models.DateTimeField(auto_now_add=True)
    field_name = models.CharField(max_length=100)
    old_value = models.TextField(blank=True, null=True)
    new_value = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'lb_device_changelog'
        ordering = ['-timestamp']

    def __str__(self):
        return f'{self.device} · {self.field_name} @ {self.timestamp}'


# ── Re-exports de los archivos hermanos por dominio ──────────────────────────
# Estos imports al final permiten escribir `from lb_manager.models import X`
# sin importar en cuál archivo viva X. Django también necesita verlos para
# registrarlos en el app `lb_manager` antes de hacer migrations.
# pylint: disable=wrong-import-position,unused-import
# noqa: E402  (imports al final, justificados por orden de registro de modelos)

from .models_infrastructure import (  # noqa: E402,F401
    LBPhysical, LBGuest, LBDecommissioned,
)
from .models_ltm import (  # noqa: E402,F401
    Servicio, LTMNode, Pool, SelfIP, SNATTranslation, VIP, LBVIPHistorical,
)
from .models_ssl import (  # noqa: E402,F401
    ClientSSLProfile, SSLCert,
)
from .models_health import (  # noqa: E402,F401
    HealthCheckDHCP, HealthCheckDNS, HealthCheckF5, HealthCheckCertificate,
    HealthRule, BitacoraHealth, BitacoraEvent,
)
from .models_hardening import (  # noqa: E402,F401
    LBHardening, BitacoraHardening,
)
from .models_credentials import (  # noqa: E402,F401
    CredentialRotationPolicy, CredentialRotation, CredentialRotationEvent,
)
from .models_changes import (  # noqa: E402,F401
    LBChangeTemplate, LBChangeTemplateItem, LBChangeRequest, LBChangeItemResponse,
)
from .models_meetings import (  # noqa: E402,F401
    F5Meeting, F5Agreement,
)
from .models_config import (  # noqa: E402,F401
    CMDBFieldConfig, CSVImportConfig, CSVColumnMapping,
    CSVTableUploadConfig, CSVTableColumnMapping,
    ScriptRunConfig, AnsibleGroupVar, AnsibleInventoryFile,
    DocEntry, DirectoryEntry,
)

# Re-exports declarados para silenciar pylint "unused-import" — todos los
# símbolos importados arriba son parte de la API pública del módulo.
__all__ = [
    # locales
    'Company', 'Datacenter', 'F5SoftwareVersion', 'F5HardwareModel',
    'LDAPGroupMap', 'GroupProfile', 'SiteSettings', 'LDAPConfig',
    'LoginAuditLog', 'LBDeviceChangeLog',
    # infrastructure
    'LBPhysical', 'LBGuest', 'LBDecommissioned',
    # ltm
    'Servicio', 'LTMNode', 'Pool', 'SelfIP', 'SNATTranslation', 'VIP',
    'LBVIPHistorical',
    # ssl
    'ClientSSLProfile', 'SSLCert',
    # health
    'HealthCheckDHCP', 'HealthCheckDNS', 'HealthCheckF5',
    'HealthCheckCertificate', 'HealthRule', 'BitacoraHealth', 'BitacoraEvent',
    # hardening
    'LBHardening', 'BitacoraHardening',
    # credentials
    'CredentialRotationPolicy', 'CredentialRotation', 'CredentialRotationEvent',
    # changes
    'LBChangeTemplate', 'LBChangeTemplateItem', 'LBChangeRequest',
    'LBChangeItemResponse',
    # meetings
    'F5Meeting', 'F5Agreement',
    # config
    'CMDBFieldConfig', 'CSVImportConfig', 'CSVColumnMapping',
    'CSVTableUploadConfig', 'CSVTableColumnMapping',
    'ScriptRunConfig', 'AnsibleGroupVar', 'AnsibleInventoryFile',
    'DocEntry', 'DirectoryEntry',
]
