"""
Django Admin configuration for the lb_manager application.

Every model listed here becomes visible and manageable through the
/admin/ interface. The ModelAdmin subclasses control which columns
are shown in the list view, which fields can be searched via the
search box, and which sidebar filters appear on the right.

Access to /admin/ requires is_staff=True on the user account.
Superusers (is_superuser=True) can see and modify every record;
staff users see only what their group permissions allow.
"""

from django import forms
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin, GroupAdmin
from django.contrib.auth.models import Group
from django.contrib import messages
from django.shortcuts import redirect
from unfold.admin import ModelAdmin as UnfoldModelAdmin
from unfold.decorators import display as unfold_display
from .models import (
    Company, Datacenter, LBPhysical, LBGuest, Servicio,
    ClientSSLProfile, HealthCheckCertificate, HealthCheckDHCP, HealthCheckDNS, HealthCheckF5,
    LTMNode, Pool, SelfIP, SNATTranslation, VIP, BitacoraHealth,
    BitacoraEvent, SSLCert, LBVIPHistorical, HealthRule, LDAPGroupMap,
    SiteSettings, LDAPConfig, LoginAuditLog, GroupProfile, CMDBFieldConfig,
    CSVImportConfig, CSVColumnMapping, ScriptRunConfig,
    AnsibleInventoryFile, CSVTableUploadConfig,
    DocEntry, DirectoryEntry,
)


@admin.register(Company)
class CompanyAdmin(UnfoldModelAdmin):
    icon = 'business'
    list_display = ('id', 'name', 'client_code')
    search_fields = ('name', 'client_code')


@admin.register(Datacenter)
class DatacenterAdmin(UnfoldModelAdmin):
    icon = 'location_on'
    list_display = ('id', 'datacenter', 'location')
    search_fields = ('datacenter', 'location')


@admin.register(LBPhysical)
class LBPhysicalAdmin(UnfoldModelAdmin):
    icon = 'router'
    list_display = ('device', 'mgmt_ip', 'model', 'version', 'environment', 'company', 'datacenter')
    list_select_related = ['company', 'datacenter']
    search_fields = ('device', 'mgmt_ip', 'model', 'serial')
    list_filter = ('environment', 'company', 'datacenter')


@admin.register(LBGuest)
class LBGuestAdmin(UnfoldModelAdmin):
    icon = 'computer'
    list_display = ('device', 'mgmt_ip', 'model', 'version', 'environment', 'company')
    list_select_related = ['company']
    search_fields = ('device', 'mgmt_ip', 'model')
    list_filter = ('environment', 'company')


@admin.register(Servicio)
class ServicioAdmin(UnfoldModelAdmin):
    icon = 'miscellaneous_services'
    list_display = ('id', 'name', 'enabled', 'servicio', 'ltm_fqn', 'ultima_modificacion')
    search_fields = ('name', 'servicio', 'ltm_fqn')
    list_filter = ('enabled',)


@admin.register(ClientSSLProfile)
class ClientSSLProfileAdmin(UnfoldModelAdmin):
    icon = 'shield'
    list_display = ('id', 'name', 'certificate_file', 'ltm_fqdn', 'full_path')
    search_fields = ('name', 'ltm_fqdn', 'certificate_file')


@admin.register(HealthCheckDHCP)
class HealthCheckDHCPAdmin(UnfoldModelAdmin):
    icon = 'wifi'
    list_display = ('id', 'fqdn', 'fecha', 'uptime', 'dhcpd', 'ntp', 'company')
    search_fields = ('fqdn', 'company')
    list_filter = ('fecha', 'dhcpd', 'ntp')


@admin.register(HealthCheckDNS)
class HealthCheckDNSAdmin(UnfoldModelAdmin):
    icon = 'dns'
    list_display = ('id', 'fqdn', 'fecha', 'uptime', 'named', 'backup', 'company')
    search_fields = ('fqdn', 'company')
    list_filter = ('fecha', 'named')


@admin.register(HealthCheckF5)
class HealthCheckF5Admin(UnfoldModelAdmin):
    icon = 'monitor_heart'
    list_display = ('id', 'fqdn', 'fecha', 'cpu_usage', 'nodes_up', 'nodes_down', 'vips_up', 'vips_offline', 'company')
    search_fields = ('fqdn', 'company')
    list_filter = ('fecha', 'company', 'failover')


@admin.register(HealthCheckCertificate)
class HealthCheckCertificateAdmin(UnfoldModelAdmin):
    icon = 'verified'
    list_display  = ('id', 'device', 'expiration_date', 'days_remaining', 'certificate_type', 'fecha', 'company')
    search_fields = ('device', 'certificate_type', 'alternames')
    list_filter   = ('fecha', 'certificate_type')


@admin.register(LTMNode)
class LTMNodeAdmin(UnfoldModelAdmin):
    icon = 'lan'
    list_display = ('id', 'name', 'address', 'availability_status', 'enabled_status', 'ltm_fqdn')
    search_fields = ('name', 'address', 'ltm_fqdn')
    list_filter = ('availability_status', 'enabled_status')


@admin.register(Pool)
class PoolAdmin(UnfoldModelAdmin):
    icon = 'hub'
    list_display = ('id', 'name', 'availability_status', 'member_count', 'lb_method', 'ltm_fqdn')
    search_fields = ('name', 'ltm_fqdn', 'full_path')
    list_filter = ('availability_status', 'enabled_status', 'lb_method')


@admin.register(SelfIP)
class SelfIPAdmin(UnfoldModelAdmin):
    icon = 'settings_ethernet'
    list_display = ('id', 'name', 'address', 'netmask_cidr', 'vlan', 'floating', 'ltm_fqdn')
    search_fields = ('name', 'address', 'ltm_fqdn')


@admin.register(SNATTranslation)
class SNATTranslationAdmin(UnfoldModelAdmin):
    icon = 'alt_route'
    list_display = ('id', 'name', 'snat', 'ltm_fqdn')
    search_fields = ('name', 'snat', 'ltm_fqdn')


@admin.register(VIP)
class VIPAdmin(UnfoldModelAdmin):
    icon = 'swap_horiz'
    list_display = ('id', 'name', 'destination', 'protocol', 'enabled', 'default_pool', 'ltm_fqdn')
    search_fields = ('name', 'destination', 'ltm_fqdn', 'default_pool')
    list_filter = ('enabled', 'protocol', 'snat_type', 'type')


@admin.register(BitacoraHealth)
class BitacoraHealthAdmin(UnfoldModelAdmin):
    icon = 'event_note'
    list_display = ('id', 'fqdn', 'fecha', 'severity_badge', 'status', 'assigned_user', 'created_at')
    list_select_related = ['assigned_user']
    search_fields = ('fqdn', 'assigned_user', 'creation_reason')
    list_filter = ('severity', 'status', 'fecha')

    @unfold_display(description='Severidad', label={
        'LOW': 'success', 'MEDIUM': 'warning', 'HIGH': 'danger',
    })
    def severity_badge(self, obj):
        return obj.severity or ''


@admin.register(BitacoraEvent)
class BitacoraEventAdmin(UnfoldModelAdmin):
    icon = 'timeline'
    list_display = ('id', 'bitacora', 'created_at')
    search_fields = ('message',)


@admin.register(SSLCert)
class SSLCertAdmin(UnfoldModelAdmin):
    icon = 'lock'
    list_display = ('id', 'name', 'expiration_date', 'subject', 'ltm_fqdn')
    search_fields = ('name', 'subject', 'ltm_fqdn')


@admin.register(LBVIPHistorical)
class LBVIPHistoricalAdmin(UnfoldModelAdmin):
    icon = 'history'
    list_display = ('id', 'name', 'destination', 'protocol', 'date', 'ltm_fqdn')
    search_fields = ('name', 'destination', 'ltm_fqdn')
    list_filter = ('protocol', 'enabled')


@admin.register(HealthRule)
class HealthRuleAdmin(UnfoldModelAdmin):
    icon = 'rule'
    list_display = ('id', 'field_name', 'operator', 'threshold', 'severity')
    search_fields = ('field_name', 'message')
    list_filter = ('severity', 'operator')


@admin.register(LDAPGroupMap)
class LDAPGroupMapAdmin(UnfoldModelAdmin):
    """
    The most important admin page for access control.

    Each row maps an Active Directory organisational unit (container_dn) to a
    Django permission group. On every login the LDAP backend reads this table
    to decide which group the user belongs to and whether they get superuser
    rights. Changes here take effect immediately — no server restart needed.

    Key fields:
      order          – Lower number = tried first when building the DN template
      container_dn   – The AD OU path (e.g. cn=network_services,dc=corp)
      dn_template    – Pattern used to construct the user's full DN for binding
      django_group   – The Django Group assigned to users in this OU
      grants_superuser – If checked, users in this OU become admins
      active         – Uncheck to disable this mapping without deleting it
    """
    icon = 'groups'
    list_display = ('order', 'container_dn', 'dn_template', 'django_group', 'grants_superuser', 'active')
    list_select_related = ['django_group']
    list_display_links = ('container_dn',)
    list_filter = ('grants_superuser', 'active')
    search_fields = ('container_dn', 'dn_template')
    ordering = ('order', 'container_dn')


@admin.register(SiteSettings)
class SiteSettingsAdmin(UnfoldModelAdmin):
    """
    Global application settings. Only one record is active at a time.
    Changes take effect immediately on the next request.
    """
    icon = 'settings'
    warn_unsaved_changes = True
    fieldsets = (
        ('Brute-force Protection', {
            'classes': ('tab',),
            'fields': ('axes_failure_limit', 'axes_cooldown_minutes'),
            'description': (
                'Controls how many failed logins are allowed before locking out '
                'an IP/account, and for how long.'
            ),
        }),
        ('VIP Management', {
            'classes': ('tab',),
            'fields': ('decommission_lookback_months',),
            'description': (
                'VIPs that have been inactive for this many consecutive months '
                'are flagged as decommission candidates.'
            ),
        }),
        ('Dashboard', {
            'classes': ('tab',),
            'fields': (
                'dashboard_history_days',
                'dashboard_recent_alerts',
                'dashboard_recent_health',
                'dashboard_recent_wiki_actions',
            ),
            'description': 'Controls what is shown on the main dashboard.',
        }),
        ('Search & Limits', {
            'classes': ('tab',),
            'fields': (
                'global_search_results_per_type',
                'bitacora_max_comment_length',
                'bulk_close_limit',
                'csv_export_limit',
            ),
            'description': 'Caps on search results and user-submitted content.',
        }),
        ('History & Changelog', {
            'classes': ('tab',),
            'fields': (
                'ddi_device_history_limit',
                'lb_device_history_limit',
                'inventory_recent_changes_limit',
                'health_check_dates_limit',
            ),
            'description': 'Controls how many historical records are loaded per device or panel.',
        }),
        ('Performance', {
            'classes': ('tab',),
            'fields': ('datatable_max_rows', 'datatable_default_page_length'),
            'description': (
                'Maximum rows returned in server-side DataTable responses and default page size. '
                'Raise max rows with caution — very large values can exhaust server memory.'
            ),
        }),
        ('Database Backups', {
            'classes': ('tab',),
            'fields': ('backup_path', 'backup_pg_dump_path', 'backup_retention_days', 'backup_schedule'),
            'description': (
                'Configure where pg_dump backups are stored and how long they are kept. '
                'The schedule field is informational — configure your system crontab '
                'or Docker cron service to run: python manage.py backup_db'
            ),
        }),
    )

    def has_add_permission(self, request):
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(LDAPConfig)
class LDAPConfigAdmin(UnfoldModelAdmin):
    """
    Manage the LDAP server connection from the admin panel.

    Only the first active row is used by the authentication backend.
    Changes take effect immediately on the next login attempt.
    """
    icon = 'manage_accounts'
    warn_unsaved_changes = True
    list_display = ('server_uri', 'use_tls', 'network_timeout', 'active')
    fieldsets = (
        ('Connection', {
            'fields': ('server_uri', 'use_tls', 'network_timeout', 'active'),
        }),
    )

    def has_add_permission(self, request):
        return not LDAPConfig.objects.exists()


@admin.register(LoginAuditLog)
class LoginAuditLogAdmin(UnfoldModelAdmin):
    icon = 'security'
    list_display = ('timestamp', 'username_attempted', 'ip_address', 'result_badge', 'user')
    list_select_related = ['user']
    list_filter = ('success',)
    search_fields = ('username_attempted', 'ip_address')
    readonly_fields = ('user', 'username_attempted', 'ip_address', 'timestamp', 'success')
    ordering = ('-timestamp',)

    @unfold_display(description='Resultado', label={
        'Exitoso': 'success', 'Fallido': 'danger',
    })
    def result_badge(self, obj):
        return 'Exitoso' if obj.success else 'Fallido'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


# ── GroupProfile inline on the built-in Group admin ──────────────────────────

class GroupProfileInline(admin.StackedInline):
    model = GroupProfile
    can_delete = False
    verbose_name = 'Profile'
    verbose_name_plural = 'Profile'
    fields = ('login_redirect_url',)


class CustomGroupAdmin(GroupAdmin):
    inlines = [GroupProfileInline]


admin.site.unregister(Group)
admin.site.register(Group, CustomGroupAdmin)


# ── Custom UserAdmin — hide password change for LDAP users ────────────────────

class CustomUserAdmin(UserAdmin):
    """
    Extends the built-in UserAdmin to prevent password changes for LDAP users.
    LDAP users always have an unusable password (set by LDAPTemplateBackend on
    every login), so exposing the "Set Password" link is misleading and unsafe.
    """

    def user_change_password(self, request, id, form_url=''):  # pylint: disable=redefined-builtin
        user = self.get_object(request, id)
        if user and not user.has_usable_password():
            messages.error(
                request,
                'Este usuario se autentica vía LDAP. La contraseña no puede '
                'cambiarse desde el panel de administración.',
            )
            return redirect(f'../{id}/change/')
        return super().user_change_password(request, id, form_url)

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if obj and not obj.has_usable_password() and 'password' in form.base_fields:
            # Keep the field so the template can render it, but strip the
            # "change password" anchor from the help text.
            form.base_fields['password'].help_text = (
                'Este usuario se autentica vía LDAP. '
                'La contraseña es gestionada externamente y no puede cambiarse aquí.'
            )
        return form


_User = get_user_model()
admin.site.unregister(_User)
admin.site.register(_User, CustomUserAdmin)


# ── CMDB Validation Config ─────────────────────────────────────────────────────

@admin.register(CMDBFieldConfig)
class CMDBFieldConfigAdmin(UnfoldModelAdmin):
    """
    Configure accepted values for CMDB fields that have no direct column in
    LBPhysical/LBGuest (assignment_group, support_group).

    Add one row per acceptable value. Multiple rows for the same field are
    treated as OR — any match is considered correct.
    Example:
        assignment_group = "Network Services"
        assignment_group = "Infrastructure Team"   ← both are OK
        support_group    = "NOC Level 2"
    """
    icon = 'table_chart'
    list_display  = ('field_name', 'expected_value', 'active')
    list_filter   = ('field_name', 'active')
    search_fields = ('expected_value',)
    ordering      = ('field_name', 'expected_value')


# ── CSV Import Config ──────────────────────────────────────────────────────────

class CSVColumnMappingInline(admin.TabularInline):
    model = CSVColumnMapping
    extra = 3
    fields = ('csv_column', 'model_field')
    verbose_name = 'Column mapping'
    verbose_name_plural = (
        'Column mappings  '
        '(leave empty to auto-match CSV headers to model field names)'
    )


def _sync_csv_schedule(config):
    """Create or update the django-q2 Schedule for a CSVImportConfig row."""
    try:
        from django_q.models import Schedule  # pylint: disable=import-outside-toplevel
    except ImportError:
        return

    schedule_name = f'CSV Import: {config.name}'
    if not config.active:
        Schedule.objects.filter(name=schedule_name).delete()
        return

    Schedule.objects.update_or_create(
        name=schedule_name,
        defaults={
            'func':          'lb_manager.tasks.run_csv_import_task',
            'args':          str(config.pk),
            'schedule_type': Schedule.CRON,
            'cron':          config.cron_schedule,
            'repeats':       -1,
        },
    )


@admin.register(CSVImportConfig)
class CSVImportConfigAdmin(UnfoldModelAdmin):
    """
    Configure and manage scheduled CSV import jobs.

    Each row defines one import job.  On save, a django-q2 Schedule is
    automatically created or updated.  Use the "Run now" action to trigger
    an immediate import without waiting for the next scheduled run.

    Path template examples
    ----------------------
    /data/f5/health_check_{date}.csv
    /mnt/shared/dns/dns_health_{date}.csv
    /var/exports/dhcp/dhcp_daily_{date}.csv
    """
    icon = 'upload_file'

    list_display  = (
        'name', 'table_config', 'file_path_template',
        'cron_schedule', 'active',
        'run_status_badge', 'last_run_at',
    )
    list_filter   = ('active', 'last_run_status')
    search_fields = ('name', 'file_path_template')
    ordering      = ('name',)
    actions       = ['run_now']

    @unfold_display(description='Último estado', label={
        'never': 'info', 'ok': 'success', 'error': 'danger',
    })
    def run_status_badge(self, obj):
        return obj.last_run_status or 'never'

    fieldsets = (
        ('Job', {
            'fields': ('name', 'table_config', 'active'),
        }),
        ('File', {
            'fields': ('file_path_template', 'date_format'),
            'description': (
                'Use <code>{date}</code> in the path; it is replaced with '
                'today\'s date using the format below.'
            ),
        }),
        ('Schedule', {
            'fields': ('cron_schedule',),
            'description': (
                'Cron expression (min hour day month weekday). '
                'Examples: <code>0 6 * * *</code> = daily at 06:00, '
                '<code>30 5 * * 1-5</code> = Mon–Fri at 05:30.'
            ),
        }),
        ('Last run (read-only)', {
            'fields': ('last_run_at', 'last_run_status', 'last_run_message'),
            'classes': ('collapse',),
        }),
    )
    readonly_fields = ('last_run_at', 'last_run_status', 'last_run_message')
    inlines = [CSVColumnMappingInline]

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        _sync_csv_schedule(obj)

    def delete_model(self, request, obj):
        # Remove the associated Q schedule before deleting the config
        try:
            from django_q.models import Schedule  # pylint: disable=import-outside-toplevel
            Schedule.objects.filter(name=f'CSV Import: {obj.name}').delete()
        except ImportError:
            pass
        super().delete_model(request, obj)

    @admin.action(description='▶ Run now (enqueue immediately)')
    def run_now(self, request, queryset):
        try:
            from django_q.tasks import async_task  # pylint: disable=import-outside-toplevel
        except ImportError:
            self.message_user(request, 'django-q2 is not installed.', level=messages.ERROR)
            return

        queued = 0
        for config in queryset:
            async_task('lb_manager.tasks.run_csv_import_task', config.pk)
            queued += 1

        self.message_user(
            request,
            f'{queued} import job(s) queued. Results will appear in '
            '"Last run" once the qcluster worker processes them.',
            level=messages.SUCCESS,
        )

    class Media:
        js = ('lb_manager/admin/csv_column_mapping.js',)


# ── Script Run Config ─────────────────────────────────────────────────────────

def _sync_script_schedule(config):
    """Create, update, or delete the django-q2 Schedule for a ScriptRunConfig row."""
    try:
        from django_q.models import Schedule  # pylint: disable=import-outside-toplevel
    except ImportError:
        return

    schedule_name = f'Script Run: {config.name}'
    if not config.active or not config.cron_schedule:
        Schedule.objects.filter(name=schedule_name).delete()
        return

    Schedule.objects.update_or_create(
        name=schedule_name,
        defaults={
            'func':          'lb_manager.tasks.run_script_task',
            'args':          str(config.pk),
            'schedule_type': Schedule.CRON,
            'cron':          config.cron_schedule,
            'repeats':       -1,
        },
    )


@admin.register(ScriptRunConfig)
class ScriptRunConfigAdmin(UnfoldModelAdmin):
    """
    Configure and run external Python scripts from the Admin panel.

    Each row defines one script.  Set run_date to the date you want to pass,
    then use the "Run now" action to execute immediately, or set a cron_schedule
    for automatic daily/weekly execution.

    The script receives run_date (formatted with date_format) as its first
    positional argument:
        python /path/to/script.py 2026-03-13

    stdout + stderr (up to 4 000 chars) are saved in "Last run message" so
    you can verify the result without checking server logs.
    """
    icon = 'terminal'

    list_display  = (
        'name', 'script_path', 'run_date',
        'cron_schedule', 'active',
        'run_status_badge', 'last_run_at',
    )
    list_filter   = ('active', 'last_run_status')
    search_fields = ('name', 'script_path', 'description')
    ordering      = ('name',)
    actions       = ['run_now']

    @unfold_display(description='Último estado', label={
        'pending': 'info', 'ok': 'success', 'error': 'danger',
    })
    def run_status_badge(self, obj):
        return obj.last_run_status or 'pending'

    fieldsets = (
        ('Job', {
            'fields': ('name', 'description', 'active'),
        }),
        ('Script', {
            'fields': ('script_path', 'run_date', 'date_format'),
            'description': (
                'The script is called as: '
                '<code>python &lt;script_path&gt; &lt;run_date&gt;</code> '
                'where <em>run_date</em> is formatted using the format below.'
            ),
        }),
        ('Schedule', {
            'fields': ('cron_schedule',),
            'description': (
                'Cron expression (min hour day month weekday). '
                'Leave blank to disable automatic scheduling. '
                'Examples: <code>0 6 * * *</code> = daily at 06:00, '
                '<code>30 5 * * 1-5</code> = Mon–Fri at 05:30.'
            ),
        }),
        ('Last run (read-only)', {
            'fields': ('last_run_at', 'last_run_status', 'last_run_message'),
            'classes': ('collapse',),
        }),
    )
    readonly_fields = ('last_run_at', 'last_run_status', 'last_run_message')

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        _sync_script_schedule(obj)

    def delete_model(self, request, obj):
        try:
            from django_q.models import Schedule  # pylint: disable=import-outside-toplevel
            Schedule.objects.filter(name=f'Script Run: {obj.name}').delete()
        except ImportError:
            pass
        super().delete_model(request, obj)

    @admin.action(description='▶ Run now (enqueue immediately)')
    def run_now(self, request, queryset):
        try:
            from django_q.tasks import async_task  # pylint: disable=import-outside-toplevel
        except ImportError:
            self.message_user(request, 'django-q2 is not installed.', level=messages.ERROR)
            return

        queued = 0
        for config in queryset:
            async_task('lb_manager.tasks.run_script_task', config.pk)
            queued += 1

        self.message_user(
            request,
            f'{queued} script(s) queued. Results will appear in '
            '"Last run" once the qcluster worker processes them.',
            level=messages.SUCCESS,
        )


# ── Ansible Inventory ─────────────────────────────────────────────────────────

@admin.register(AnsibleInventoryFile)
class AnsibleInventoryFileAdmin(UnfoldModelAdmin):
    """
    Register the Ansible INI inventory files that the Inventory Editor can
    read and write.  Each row links an environment (Production / Pre / DRP)
    to the absolute path of the file on the server.
    """
    icon = 'inventory_2'
    list_display  = ('name', 'environment', 'file_path', 'description')
    list_filter   = ('environment',)
    search_fields = ('name', 'file_path')
    ordering      = ('environment', 'name')


# ── CSV Table Upload ──────────────────────────────────────────────────────────

def _model_path_choices():
    """Return (value, label) choices for all concrete models in project apps.

    Excludes Django built-ins and third-party apps so any new project app
    appears automatically without touching this function.
    """
    from django.apps import apps as django_apps  # pylint: disable=import-outside-toplevel
    EXCLUDE_APPS = {
        'admin', 'auth', 'contenttypes', 'sessions',
        'messages', 'staticfiles', 'axes', 'django_q',
    }
    choices = []
    for model in sorted(django_apps.get_models(), key=lambda m: (m._meta.app_label, m._meta.model_name)):  # pylint: disable=protected-access
        if model._meta.app_label not in EXCLUDE_APPS and not model._meta.abstract:  # pylint: disable=protected-access
            path = f'{model._meta.app_label}.{model.__name__}'  # pylint: disable=protected-access
            label = f'{model._meta.app_label} › {model._meta.verbose_name}'  # pylint: disable=protected-access
            choices.append((path, label))
    return choices


class CSVTableUploadConfigForm(forms.ModelForm):
    """Custom form that shows a select dropdown for model_path."""

    model_path = forms.ChoiceField(
        label='Model (tabla destino)',
        help_text='Selecciona el modelo Django cuya tabla recibirá los datos del CSV.',
    )

    class Meta:
        model = CSVTableUploadConfig
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['model_path'].choices = [('', '---------')] + _model_path_choices()


@admin.register(CSVTableUploadConfig)
class CSVTableUploadConfigAdmin(UnfoldModelAdmin):
    """
    Register a Django model table as eligible for CSV imports.

    1. Set a display label and optional description.
    2. Select the target model from the dropdown.
    3. Set unique_fields: comma-separated field names used as the dedup key.
    4. Mark as active to make this table available in CSV Import Configs.
    """
    icon = 'table'
    form          = CSVTableUploadConfigForm
    list_display  = ('label', 'model_path', 'unique_fields')
    list_filter   = ('active',)
    search_fields = ('label', 'model_path')
    ordering      = ('label',)
    fieldsets = (
        (None, {
            'fields': ('label', 'active', 'description'),
        }),
        ('Tabla destino', {
            'fields': ('model_path', 'unique_fields'),
            'description': (
                'Selecciona el modelo y los campos que identifican un registro único '
                '(separados por coma). Ejemplo: "device,fecha"'
            ),
        }),
    )


@admin.register(DocEntry)
class DocEntryAdmin(UnfoldModelAdmin):
    """Admin for documentation catalog entries."""

    icon          = 'description'
    list_display  = ('id', 'name', 'category', 'url', 'created_at')
    search_fields = ('name', 'category', 'description')
    list_filter   = ('category',)
    ordering      = ('category', 'name')


@admin.register(DirectoryEntry)
class DirectoryEntryAdmin(UnfoldModelAdmin):
    """Admin for important-numbers directory entries."""

    icon          = 'phone'
    list_display  = ('id', 'name', 'number', 'description', 'created_at')
    search_fields = ('name', 'number', 'description')
    ordering      = ('name',)
