"""
Database models for the Load Balancer Management System.
Infrastructure:    Company · Datacenter · LBPhysical · LBGuest
F5 LTM objects:    Servicio · VIP · Pool · LTMNode · SelfIP · SNATTranslation
                   ClientSSLProfile · SSLCert
Health monitoring: HealthCheckF5 · HealthCheckDHCP · HealthCheckDNS
                   HealthRule · BitacoraHealth · BitacoraEvent · HealthCheckCertificate
Historical data:   LBVIPHistorical
Access control:    LDAPGroupMap · GroupProfile · LDAPConfig · LoginAuditLog · LBDeviceChangeLog
Hardening:         LBHardening · BitacoraHardening
Config models:     SiteSettings · CMDBFieldConfig · CSVImportConfig · CSVColumnMapping
                   CSVTableUploadConfig · CSVTableColumnMapping · ScriptRunConfig
                   AnsibleGroupVar · AnsibleInventoryFile
Catalog:           DocEntry · DirectoryEntry
"""
from datetime import date
from django.conf import settings
from django.contrib.auth.models import Group
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver

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

class LBPhysical(models.Model):
    """Appliance F5 BIG-IP físico (rack-mounted). `device` es la PK (hostname en F5)."""
    device = models.CharField(max_length=255, primary_key=True)
    ci_id = models.CharField(max_length=255, blank=True, null=True)
    mgmt_ip = models.CharField(max_length=45, default='')
    version = models.CharField(max_length=255, default='')
    distro = models.CharField(max_length=255, default='')
    model = models.CharField(max_length=255, default='')
    serial = models.CharField(max_length=255, default='')
    snow_link = models.CharField(max_length=2083, blank=True, null=True)
    environment = models.CharField(max_length=255, default='')
    service = models.DateField(null=True)
    vendor_support = models.CharField(max_length=255, blank=True, null=True)
    location = models.CharField(max_length=255, blank=True, null=True)
    last_modified = models.DateTimeField(auto_now=True)
    ansible_group = models.TextField(blank=True, null=True)
    company = models.ForeignKey(Company, on_delete=models.PROTECT, null=True, db_column='company_id', related_name='lb_physicals')
    datacenter = models.ForeignKey(Datacenter, on_delete=models.SET_NULL, null=True, blank=True, db_column='datacenter_id', related_name='lb_physicals')
    purpose = models.CharField(max_length=255, default='')
    ha_pair = models.CharField(max_length=255, blank=True, null=True)
    monitoreo = models.BooleanField(default=False)
    cyberark = models.BooleanField(default=False)
    user_cyberark = models.CharField(max_length=255, blank=True, null=True)
    url_cyberark = models.CharField(max_length=2083, blank=True, null=True)
    cmdb_snmp = models.BooleanField(default=False)

    class Meta:
        db_table = 'lb_physical'
        verbose_name = 'LB Physical'
        verbose_name_plural = 'LB Physicals'

    def __str__(self):
        return str(self.device)

class LBGuest(models.Model):
    """Instancia virtual F5 BIG-IP (vCMP/guest). `serial` apunta al LBPhysical host."""
    device = models.CharField(max_length=255, primary_key=True)
    ci_id = models.CharField(max_length=255, blank=True, null=True)
    mgmt_ip = models.CharField(max_length=45, blank=True, null=True)
    version = models.CharField(max_length=255, blank=True, null=True)
    distro = models.CharField(max_length=255, blank=True, null=True)
    model = models.CharField(max_length=255, blank=True, null=True)
    serial = models.CharField(max_length=255, blank=True, null=True)
    snow_link = models.CharField(max_length=2083, blank=True, null=True)
    environment = models.CharField(max_length=255, blank=True, null=True)
    ha_pair = models.CharField(max_length=255, blank=True, null=True)
    last_modified = models.DateTimeField(auto_now=True)
    ansible_group = models.TextField(blank=True, null=True)
    company = models.ForeignKey(Company, on_delete=models.SET_NULL, null=True, blank=True, db_column='company_id', related_name='lb_guests')
    monitoreo = models.BooleanField(default=False)
    cyberark = models.BooleanField(default=False)
    user_cyberark = models.CharField(max_length=255, blank=True, null=True)
    url_cyberark = models.CharField(max_length=2083, blank=True, null=True)
    cmdb_snmp = models.BooleanField(default=False)

    class Meta:
        db_table = 'lb_guest'
        verbose_name = 'LB Guest'
        verbose_name_plural = 'LB Guests'

    def __str__(self):
        return str(self.device)

class Servicio(models.Model):
    """Servicio lógico de aplicación definido en un dispositivo F5."""
    name = models.CharField(max_length=100, blank=True, null=True)
    enabled = models.CharField(max_length=20, blank=True, null=True)
    servicio = models.CharField(max_length=100, blank=True, null=True)
    ltm_fqn = models.CharField(max_length=100, blank=True, null=True)
    ultima_modificacion = models.DateTimeField(blank=True, null=True)
    comentarios = models.CharField(max_length=200, blank=True, null=True)
    description = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'servicio'
        verbose_name = 'Servicio'
        verbose_name_plural = 'Servicios'

    def __str__(self):
        return str(self.name or self.id)

class ClientSSLProfile(models.Model):
    """Perfil SSL/TLS cliente configurado en un dispositivo F5."""
    allow_non_ssl = models.CharField(max_length=10, blank=True, null=True)
    authenticate_depth = models.IntegerField(blank=True, null=True)
    authenticate_frequency = models.CharField(max_length=50, blank=True, null=True)
    cache_size = models.IntegerField(blank=True, null=True)
    cache_timeout = models.IntegerField(blank=True, null=True)
    certificate_file = models.CharField(max_length=255, blank=True, null=True)
    chain_file = models.CharField(max_length=255, blank=True, null=True)
    description = models.CharField(max_length=255, blank=True, null=True)
    full_path = models.CharField(max_length=255, blank=True, null=True)
    name = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    parent = models.CharField(max_length=255, blank=True, null=True)
    peer_certificate_mode = models.CharField(max_length=50, blank=True, null=True)
    profile_mode_enabled = models.CharField(max_length=10, blank=True, null=True)
    renegotiation = models.CharField(max_length=10, blank=True, null=True)
    retain_certificate = models.CharField(max_length=10, blank=True, null=True)
    secure_renegotiation_mode = models.CharField(max_length=50, blank=True, null=True)
    session_ticket = models.CharField(max_length=10, blank=True, null=True)
    sni_default = models.CharField(max_length=10, blank=True, null=True)
    strict_name = models.CharField(max_length=10, blank=True, null=True)
    ltm_fqdn = models.CharField(max_length=100, blank=True, null=True, db_index=True)

    class Meta:
        db_table = 'client_ssl_profiles'
        verbose_name = 'Client SSL Profile'
        verbose_name_plural = 'Client SSL Profiles'
        constraints = [
            models.UniqueConstraint(fields=['full_path', 'ltm_fqdn'], name='clientssl_full_path_ltm_fqdn_uniq'),
        ]

    def __str__(self):
        return str(self.name or self.id)

class HealthCheckDHCP(models.Model):
    """Snapshot diario de salud de un servidor DHCP."""
    fqdn = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    uptime = models.FloatField(blank=True, null=True)
    nproc = models.IntegerField(blank=True, null=True)
    user_nice_iowait_steal_idle = models.CharField(max_length=100, blank=True, null=True)
    memory_total = models.IntegerField(blank=True, null=True)
    memory_free = models.IntegerField(blank=True, null=True)
    swap_free = models.IntegerField(blank=True, null=True)
    dhcpd = models.CharField(max_length=100, blank=True, null=True)
    ntp = models.CharField(max_length=100, blank=True, null=True)
    filesystems = models.CharField(max_length=100, blank=True, null=True)
    dhcpd_conf = models.IntegerField(blank=True, null=True)
    fecha = models.DateField(blank=True, null=True, db_index=True)
    company = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        db_table = 'health_check_dhcp'
        verbose_name = 'Health Check DHCP'
        verbose_name_plural = 'Health Checks DHCP'
        unique_together = [('fqdn', 'fecha')]

    def __str__(self):
        return f"{self.fqdn} - {self.fecha}"

class HealthCheckDNS(models.Model):
    """Snapshot diario de salud de un servidor DNS."""
    fqdn = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    uptime = models.FloatField(blank=True, null=True)
    nproc = models.IntegerField(blank=True, null=True)
    max_recursive_clients = models.CharField(max_length=100, blank=True, null=True)
    user_nice_iowait_steal_idle = models.CharField(max_length=100, blank=True, null=True)
    memory_total = models.IntegerField(blank=True, null=True)
    memory_free = models.IntegerField(blank=True, null=True)
    swap_total = models.IntegerField(blank=True, null=True)
    swap_free  = models.IntegerField(blank=True, null=True)
    named = models.CharField(max_length=100, blank=True, null=True)
    filesystems = models.CharField(max_length=100, blank=True, null=True)
    backup = models.CharField(max_length=15, blank=True, null=True)
    ntp    = models.CharField(max_length=100, blank=True, null=True)
    fecha = models.DateField(blank=True, null=True, db_index=True)
    company = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        db_table = 'health_check_dns'
        verbose_name = 'Health Check DNS'
        verbose_name_plural = 'Health Checks DNS'
        unique_together = [('fqdn', 'fecha')]

    def __str__(self):
        return f"{self.fqdn} - {self.fecha}"

class HealthCheckF5(models.Model):
    """ Snapshot diario de salud de un appliance F5 BIG-IP. Unique constraint en (fqdn, fecha). Campos clave: failover, sync, cpu_usage, file_backup. """
    fqdn = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    uptime = models.FloatField(blank=True, null=True)
    failover = models.CharField(max_length=100, blank=True, null=True)
    failsafe = models.CharField(max_length=100, blank=True, null=True)
    sync = models.CharField(max_length=100, blank=True, null=True)
    ltm_logs = models.IntegerField(blank=True, null=True)
    cpu_usage = models.IntegerField(blank=True, null=True)
    cpu_plane_use = models.IntegerField(blank=True, null=True)
    cpu_analysis_use = models.IntegerField(blank=True, null=True)
    top_connections = models.CharField(max_length=100, blank=True, null=True)
    tmm_memory = models.CharField(max_length=100, blank=True, null=True)
    tmm_memory_used = models.CharField(max_length=100, blank=True, null=True)
    nodes = models.IntegerField(blank=True, null=True)
    nodes_up = models.IntegerField(blank=True, null=True)
    nodes_down = models.IntegerField(blank=True, null=True)
    nodes_user_down = models.IntegerField(blank=True, null=True)
    vips = models.IntegerField(blank=True, null=True)
    vips_up = models.IntegerField(blank=True, null=True)
    vips_offline = models.IntegerField(blank=True, null=True)
    vips_unknown = models.IntegerField(blank=True, null=True)
    fecha = models.DateField(blank=True, null=True, db_index=True)
    company = models.CharField(max_length=100, blank=True, null=True)
    last_folder = models.CharField(max_length=100, blank=True, null=True)
    file_backup = models.CharField(max_length=15, blank=True, null=True)
    backup_path = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = 'health_check_f5'
        verbose_name = 'Health Check F5'
        verbose_name_plural = 'Health Checks F5'
        unique_together = [('fqdn', 'fecha')]

    def __str__(self):
        return f"{self.fqdn} - {self.fecha}"

class HealthCheckCertificate(models.Model):
    """Snapshot diario de certificados SSL/TLS recolectados desde dispositivos de red."""
    device           = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    expiration_date  = models.CharField(max_length=100, blank=True, null=True)
    days_remaining   = models.IntegerField(blank=True, null=True, db_index=True)
    certificate_type = models.CharField(max_length=100, blank=True, null=True)
    comments         = models.TextField(blank=True, null=True)
    alternames       = models.TextField(blank=True, null=True)
    fecha            = models.DateField(blank=True, null=True, db_index=True)
    company          = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        db_table            = 'health_check_certificate'
        verbose_name        = 'Health Check Certificate'
        verbose_name_plural = 'Health Checks Certificate'
        ordering            = ['-fecha', 'days_remaining']

    def __str__(self):
        return f"{self.device} - {self.expiration_date} ({self.fecha})"

class LTMNode(models.Model):
    """Servidor real registrado en un dispositivo F5 LTM."""
    address = models.CharField(max_length=32, blank=True, null=True, db_index=True)
    availability_status = models.CharField(max_length=255, blank=True, null=True)
    connection_limit = models.IntegerField(blank=True, null=True)
    dynamic_ratio = models.IntegerField(blank=True, null=True)
    enabled_status = models.CharField(max_length=255, blank=True, null=True)
    full_path = models.CharField(max_length=255, blank=True, null=True)
    monitor_rule = models.CharField(max_length=255, blank=True, null=True)
    monitor_status = models.CharField(max_length=255, blank=True, null=True)
    monitor_type = models.CharField(max_length=255, blank=True, null=True)
    monitors = models.JSONField(blank=True, null=True)
    name = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    rate_limit = models.IntegerField(blank=True, null=True)
    ratio = models.IntegerField(blank=True, null=True)
    session_status = models.CharField(max_length=255, blank=True, null=True)
    status_reason = models.CharField(max_length=255, blank=True, null=True)
    ltm_fqdn = models.CharField(max_length=100, blank=True, null=True, db_index=True)

    class Meta:
        db_table = 'ltm_nodes'
        verbose_name = 'LTM Node'
        verbose_name_plural = 'LTM Nodes'
        constraints = [
            models.UniqueConstraint(fields=['full_path', 'ltm_fqdn'], name='ltmnode_full_path_ltm_fqdn_uniq'),
        ]

    def __str__(self):
        return str(self.name or self.id)

class Pool(models.Model):
    """Grupo de servidores reales detrás de un VIP. Distribución según `lb_method`."""
    active_member_count = models.IntegerField(blank=True, null=True)
    allow_nat = models.CharField(max_length=10, blank=True, null=True)
    allow_snat = models.CharField(max_length=10, blank=True, null=True)
    availability_status = models.CharField(max_length=255, blank=True, null=True)
    available_member_count = models.IntegerField(blank=True, null=True)
    client_ip_tos = models.CharField(max_length=50, blank=True, null=True)
    client_link_qos = models.CharField(max_length=50, blank=True, null=True)
    enabled_status = models.CharField(max_length=50, blank=True, null=True)
    full_path = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    lb_method = models.CharField(max_length=50, blank=True, null=True)
    member_count = models.IntegerField(blank=True, null=True)
    members = models.JSONField(default=list, blank=True, null=True)
    monitors = models.JSONField(default=list, blank=True, null=True)
    name = models.CharField(max_length=100, blank=True, null=True)
    service_down_action = models.CharField(max_length=50, blank=True, null=True)
    status_reason = models.CharField(max_length=255, blank=True, null=True)
    ltm_fqdn = models.CharField(max_length=100, blank=True, null=True, db_index=True)

    class Meta:
        db_table = 'pools'
        verbose_name = 'Pool'
        verbose_name_plural = 'Pools'
        constraints = [
            models.UniqueConstraint(fields=['full_path', 'ltm_fqdn'], name='pool_full_path_ltm_fqdn_uniq'),
        ]

    def __str__(self):
        return str(self.name or self.id)

class SelfIP(models.Model):
    """Dirección IP propia del LB en una VLAN. `floating` indica si migra en failover."""
    address = models.CharField(max_length=32, blank=True, null=True)
    allow_access_list = models.CharField(max_length=100, blank=True, null=True)
    floating = models.CharField(max_length=100, blank=True, null=True)
    full_path = models.CharField(max_length=100, blank=True, null=True)
    name = models.CharField(max_length=100, blank=True, null=True)
    netmask = models.CharField(max_length=100, blank=True, null=True)
    netmask_cidr = models.IntegerField(blank=True, null=True)
    vlan = models.CharField(max_length=100, blank=True, null=True)
    ltm_fqdn = models.CharField(max_length=100, blank=True, null=True, db_index=True)

    class Meta:
        db_table = 'self_ips'
        verbose_name = 'Self IP'
        verbose_name_plural = 'Self IPs'
        constraints = [
            models.UniqueConstraint(fields=['full_path', 'ltm_fqdn'], name='selfip_full_path_ltm_fqdn_uniq'),
        ]

    def __str__(self):
        return str(self.name or self.id)

class SNATTranslation(models.Model):
    """Entrada SNAT que reemplaza la IP origen del cliente antes de enviar al backend."""
    snat = models.CharField(max_length=100, blank=True, null=True)
    ltm_fqdn = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    name = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        db_table = 'snats_translations'
        verbose_name = 'SNAT Translation'
        verbose_name_plural = 'SNAT Translations'
        constraints = [
            models.UniqueConstraint(fields=['name', 'ltm_fqdn'], name='snat_name_ltm_fqdn_uniq'),
        ]

    def __str__(self):
        return str(self.name or self.id)

class VIP(models.Model):
    """VIP (Virtual Server) en F5 LTM. Escucha en destination_address:port y reenvía al default_pool."""
    # Core identity
    name = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    full_path = models.CharField(max_length=100, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    ltm_fqdn = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    # Destination / traffic matching
    destination = models.CharField(max_length=100, blank=True, null=True)
    destination_address = models.CharField(max_length=50, blank=True, null=True)
    destination_port = models.IntegerField(blank=True, null=True)
    protocol = models.CharField(max_length=10, blank=True, null=True)
    type = models.CharField(max_length=30, blank=True, null=True)
    source_address = models.CharField(max_length=50, blank=True, null=True)
    source_port_behavior = models.CharField(max_length=50, blank=True, null=True)
    # State
    enabled = models.CharField(max_length=20, blank=True, null=True)
    availability_status = models.CharField(max_length=50, blank=True, null=True)
    status_reason = models.TextField(blank=True, null=True)
    # Pool & traffic forwarding
    default_pool = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    snat_type = models.CharField(max_length=50, blank=True, null=True)
    snat_pool = models.CharField(max_length=100, blank=True, null=True)
    persistence_profile = models.CharField(max_length=100, blank=True, null=True)
    profiles = models.JSONField(blank=True, null=True)
    policies = models.CharField(max_length=100, blank=True, null=True)
    # Address translation
    translate_address = models.CharField(max_length=10, blank=True, null=True)
    translate_port = models.CharField(max_length=10, blank=True, null=True)
    nat64_enabled = models.CharField(max_length=10, blank=True, null=True)
    # Performance / limits
    connection_limit = models.IntegerField(blank=True, null=True)
    connection_mirror_enabled = models.CharField(max_length=10, blank=True, null=True)
    rate_limit = models.IntegerField(blank=True, null=True)
    rate_limit_mode = models.CharField(max_length=50, blank=True, null=True)
    rate_limit_destination_mask = models.IntegerField(blank=True, null=True)
    # CMP / hardware acceleration
    cmp_enabled = models.CharField(max_length=10, blank=True, null=True)
    cmp_mode = models.CharField(max_length=50, blank=True, null=True)
    hardware_syn_cookie_instances = models.IntegerField(blank=True, null=True)
    syn_cookies_status = models.CharField(max_length=50, blank=True, null=True)
    # Miscellaneous F5 attributes
    auto_lasthop = models.CharField(max_length=50, blank=True, null=True)
    gtm_score = models.IntegerField(blank=True, null=True)

    class Meta:
        db_table = 'vips'
        verbose_name = 'VIP'
        verbose_name_plural = 'VIPs'
        constraints = [
            models.UniqueConstraint(fields=['full_path', 'ltm_fqdn'], name='vip_full_path_ltm_fqdn_uniq'),
        ]

    def __str__(self):
        return str(self.name or self.id)

class BitacoraHealth(models.Model):
    """Ticket de incidente de salud por dispositivo/día. Severity: LOW/MEDIUM/HIGH. Status: OPEN/IN_PROGRESS/CLOSED."""
    class Severity(models.TextChoices):
        LOW    = 'LOW',    'Low'
        MEDIUM = 'MEDIUM', 'Medium'
        HIGH   = 'HIGH',   'High'

    class Status(models.TextChoices):
        OPEN        = 'OPEN',        'Open'
        IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
        CLOSED      = 'CLOSED',      'Closed'

    ticket_id = models.CharField(max_length=20, unique=True, blank=True, null=True)
    fqdn = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    fecha = models.DateField(blank=True, null=True, db_index=True)
    severity = models.CharField(max_length=10, choices=Severity.choices, blank=True, null=True)
    status = models.CharField(max_length=20, choices=Status.choices, blank=True, null=True, db_index=True)
    assigned_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='bitacora_assignments')
    comments = models.TextField(blank=True, null=True)
    closed_user = models.CharField(max_length=100, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(blank=True, null=True)
    creation_reason = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'bitacora_health'
        verbose_name = 'Bitacora Health'
        verbose_name_plural = 'Bitacora Health'
        permissions = [
            ('manage_bitacora', 'Can manage Bitacora Health tickets'),
        ]

    def save(self, *args, **kwargs):
        """Auto-generate ticket_id (NSINC0000001 format) on first save if not set."""
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new and not self.ticket_id:
            self.ticket_id = f'NSINC{self.pk:07d}'
            BitacoraHealth.objects.filter(pk=self.pk).update(ticket_id=self.ticket_id)

    def __str__(self):
        return f"{self.ticket_id or self.pk} - {self.fqdn} ({self.severity})"

class BitacoraEvent(models.Model):
    """Entrada de auditoría adjunta a un ticket BitacoraHealth."""
    bitacora = models.ForeignKey(BitacoraHealth, on_delete=models.CASCADE, related_name='events', db_column='bitacora_id')
    message = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'bitacora_events'
        verbose_name = 'Bitacora Event'
        verbose_name_plural = 'Bitacora Events'

    def __str__(self):
        return f"Event for {self.bitacora_id} at {self.created_at}"

class SSLCert(models.Model):
    """Certificado TLS/SSL instalado en un dispositivo F5. `expiration_date` es el campo crítico."""
    create_time = models.CharField(max_length=100, blank=True, null=True)
    expiration_date = models.CharField(max_length=100, blank=True, null=True)
    expiration_timestamp = models.BigIntegerField(blank=True, null=True, db_index=True)
    fingerprint = models.CharField(max_length=128, blank=True, null=True)
    full_path = models.CharField(max_length=255, blank=True, null=True)
    is_bundle = models.CharField(max_length=10, blank=True, null=True)
    issuer = models.CharField(max_length=500, blank=True, null=True)
    key_size = models.PositiveSmallIntegerField(blank=True, null=True)
    key_type = models.CharField(max_length=50, blank=True, null=True)
    last_update_time = models.CharField(max_length=100, blank=True, null=True)
    name = models.CharField(max_length=255, blank=True, null=True)
    sha1_checksum = models.CharField(max_length=128, blank=True, null=True)
    subject = models.CharField(max_length=500, blank=True, null=True)
    ltm_fqdn = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    subject_alternative_name = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'ssl_certs'
        verbose_name = 'SSL Certificate'
        verbose_name_plural = 'SSL Certificates'
        constraints = [
            models.UniqueConstraint(fields=['full_path', 'ltm_fqdn'], name='sslcert_full_path_ltm_fqdn_uniq'),
        ]

    def __str__(self):
        return str(self.name or self.id)

class LBVIPHistorical(models.Model):
    """Snapshot histórico de la configuración de un VIP en un momento dado."""
    # Core identity
    name = models.CharField(max_length=100, blank=True, null=True)
    full_path = models.CharField(max_length=100, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    ltm_fqdn = models.CharField(max_length=100, blank=True, null=True)
    # Destination / traffic matching
    destination = models.CharField(max_length=100, blank=True, null=True)
    destination_address = models.CharField(max_length=50, blank=True, null=True)
    destination_port = models.IntegerField(blank=True, null=True)
    protocol = models.CharField(max_length=10, blank=True, null=True)
    type = models.CharField(max_length=30, blank=True, null=True)
    source_address = models.CharField(max_length=50, blank=True, null=True)
    source_port_behavior = models.CharField(max_length=50, blank=True, null=True)
    # State
    enabled = models.CharField(max_length=20, blank=True, null=True)
    availability_status = models.CharField(max_length=50, blank=True, null=True)
    status_reason = models.TextField(blank=True, null=True)
    # Pool & traffic forwarding
    default_pool = models.CharField(max_length=100, blank=True, null=True)
    snat_type = models.CharField(max_length=50, blank=True, null=True)
    snat_pool = models.CharField(max_length=100, blank=True, null=True)
    persistence_profile = models.CharField(max_length=100, blank=True, null=True)
    profiles = models.TextField(blank=True, null=True)
    policies = models.CharField(max_length=100, blank=True, null=True)
    # Address translation
    translate_address = models.CharField(max_length=10, blank=True, null=True)
    translate_port = models.CharField(max_length=10, blank=True, null=True)
    nat64_enabled = models.CharField(max_length=10, blank=True, null=True)
    # Performance / limits
    connection_limit = models.IntegerField(blank=True, null=True)
    connection_mirror_enabled = models.CharField(max_length=10, blank=True, null=True)
    rate_limit = models.IntegerField(blank=True, null=True)
    rate_limit_mode = models.CharField(max_length=50, blank=True, null=True)
    rate_limit_destination_mask = models.IntegerField(blank=True, null=True)
    # CMP / hardware acceleration
    cmp_enabled = models.CharField(max_length=10, blank=True, null=True)
    cmp_mode = models.CharField(max_length=50, blank=True, null=True)
    hardware_syn_cookie_instances = models.IntegerField(blank=True, null=True)
    syn_cookies_status = models.CharField(max_length=50, blank=True, null=True)
    # Miscellaneous F5 attributes
    auto_lasthop = models.CharField(max_length=50, blank=True, null=True)
    gtm_score = models.IntegerField(blank=True, null=True)
    # Snapshot timestamp
    date = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'lb_vips_historical'
        verbose_name = 'LB VIP Historical'
        verbose_name_plural = 'LB VIPs Historical'

    def __str__(self):
        return f"{self.name} - {self.date}"

class HealthRule(models.Model):
    """Regla de umbral que dispara alertas de salud. Ejemplo: cpu_usage > 90 → HIGH."""
    class Severity(models.TextChoices):
        LOW    = 'LOW',    'Low'
        MEDIUM = 'MEDIUM', 'Medium'
        HIGH   = 'HIGH',   'High'

    field_name = models.CharField(max_length=50, blank=True, null=True)
    operator = models.CharField(max_length=10, blank=True, null=True)
    threshold = models.CharField(max_length=50, blank=True, null=True)
    message = models.TextField(blank=True, null=True)
    severity = models.CharField(max_length=10, choices=Severity.choices, blank=True, null=True)

    class Meta:
        db_table = 'health_rules'
        verbose_name = 'Health Rule'
        verbose_name_plural = 'Health Rules'

    def __str__(self):
        return f"{self.field_name} {self.operator} {self.threshold}"

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

class LBHardening(models.Model):
    """Resultado de un check de hardening/vulnerabilidad para un dispositivo LB."""
    class Resultado(models.TextChoices):
        PASSED  = 'passed',  'Passed'
        FAILED  = 'failed',  'Failed'
        WARNING = 'warning', 'Warning'
        NA      = 'n/a',     'N/A'

    device               = models.CharField(max_length=255, db_index=True)
    code                 = models.CharField(max_length=32, db_index=True)
    descripcion          = models.TextField(blank=True, null=True)
    valor_obtenido       = models.TextField(blank=True, null=True)
    valor_recomendado    = models.TextField(blank=True, null=True)
    resultado            = models.CharField(max_length=32, choices=Resultado.choices, db_index=True)
    comando_para_validar = models.TextField(blank=True, null=True)
    fecha                = models.DateField(db_index=True)

    class Meta:
        db_table = 'lb_hardening'
        ordering = ['device', 'code']
        verbose_name = 'LB Hardening Check'
        verbose_name_plural = 'LB Hardening Checks'
        unique_together = [('device', 'code', 'fecha')]

    def __str__(self):
        return f'{self.device} · {self.code} · {self.resultado}'

class BitacoraHardening(models.Model):
    """Ticket de incidente para un check de hardening fallido. Creado automáticamente por señal."""
    class Status(models.TextChoices):
        OPEN        = 'OPEN',        'Open'
        IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
        CLOSED      = 'CLOSED',      'Closed'

    ticket_id         = models.CharField(max_length=20, unique=True, blank=True, null=True)
    hardening         = models.ForeignKey(LBHardening, on_delete=models.SET_NULL, null=True, blank=True, related_name='bitacora_tickets', db_column='hardening_id')
    device            = models.CharField(max_length=255, db_index=True)
    code              = models.CharField(max_length=32, db_index=True)
    descripcion       = models.TextField(blank=True, null=True)
    valor_obtenido    = models.TextField(blank=True, null=True)
    valor_recomendado = models.TextField(blank=True, null=True)
    fecha             = models.DateField(db_index=True)
    status            = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN, db_index=True)
    assigned_user     = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='hardening_assignments')
    comments          = models.TextField(blank=True, null=True)
    closed_at         = models.DateTimeField(blank=True, null=True)
    closed_user       = models.CharField(max_length=100, blank=True, null=True)
    created_at        = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'bitacora_hardening'
        ordering = ['-created_at']
        verbose_name = 'Bitacora Hardening'
        verbose_name_plural = 'Bitacora Hardening'
        permissions = [
            ('manage_bitacora_hardening', 'Can manage Bitacora Hardening tickets'),
        ]

    def save(self, *args, **kwargs):
        """Auto-generate ticket_id (NSHRD0000001 format) on first save if not set."""
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new and not self.ticket_id:
            self.ticket_id = f'NSHRD{self.pk:07d}'
            BitacoraHardening.objects.filter(pk=self.pk).update(ticket_id=self.ticket_id)

    def __str__(self):
        return f"{self.ticket_id or self.pk} - {self.device} · {self.code}"

class CMDBFieldConfig(models.Model):
    """Valores aceptados para campos CMDB (assignment_group, support_group). Múltiples filas = OR."""

    class Field(models.TextChoices):
        ASSIGNMENT_GROUP = 'assignment_group', 'Assignment Group'
        SUPPORT_GROUP    = 'support_group',    'Support Group'
    field_name     = models.CharField(max_length=50, choices=Field.choices, verbose_name='CMDB Field')
    expected_value = models.CharField(max_length=255, verbose_name='Accepted Value')
    active         = models.BooleanField(default=True)

    class Meta:
        db_table = 'cmdb_field_config'
        verbose_name = 'CMDB Field Config'
        verbose_name_plural = 'CMDB Field Configs'
        ordering = ['field_name', 'expected_value']

    def __str__(self):
        return f'{self.get_field_name_display()} = "{self.expected_value}"'

class CSVImportConfig(models.Model):
    """Job programado de importación CSV. `file_path_template` soporta {date} como placeholder."""
    class RunStatus(models.TextChoices):
        NEVER = 'never', 'Never run'
        OK    = 'ok',    'OK'
        ERROR = 'error', 'Error'
    name               = models.CharField(max_length=100)
    table_config       = models.ForeignKey('CSVTableUploadConfig', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Type', related_name='import_configs', limit_choices_to={'active': True})
    file_path_template = models.CharField(max_length=500, verbose_name='File path template')
    date_format        = models.CharField(max_length=30, default='%Y-%m-%d')
    cron_schedule      = models.CharField(max_length=50)
    active             = models.BooleanField(default=True)
    last_run_at        = models.DateTimeField(null=True, blank=True, editable=False)
    last_run_status    = models.CharField(max_length=10, choices=RunStatus.choices, default=RunStatus.NEVER, editable=False)
    last_run_message   = models.TextField(blank=True, default='', editable=False)

    class Meta:
        db_table = 'csv_import_config'
        verbose_name = 'CSV Import Config'
        verbose_name_plural = 'CSV Import Configs'
        ordering = ['name']

    def __str__(self) -> str:
        return str(self.name)

class CSVColumnMapping(models.Model):
    """Mapea una columna CSV a un campo del modelo para un CSVImportConfig."""
    config      = models.ForeignKey(CSVImportConfig, on_delete=models.CASCADE, related_name='column_mappings')
    csv_column  = models.CharField(max_length=100)
    model_field = models.CharField(max_length=100)

    class Meta:
        db_table = 'csv_column_mapping'
        verbose_name = 'Column Mapping'
        verbose_name_plural = 'Column Mappings'
        unique_together = [('config', 'csv_column')]
        ordering = ['csv_column']

    def __str__(self):
        return f'{self.csv_column} → {self.model_field}'

# ── CSV Table Upload Config ───────────────────────────────────────────────────
class CSVTableUploadConfig(models.Model):
    """Declara una tabla Django como elegible para carga manual de CSV desde la UI."""
    label         = models.CharField(max_length=100, verbose_name='Label')
    model_path    = models.CharField(max_length=200, default='', verbose_name='Model')
    unique_fields = models.CharField(max_length=500, blank=True, default='', verbose_name='Unique Fields')
    active        = models.BooleanField(default=True)
    description   = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'csv_table_upload_config'
        verbose_name = 'CSV Table Upload Config'
        verbose_name_plural = 'CSV Table Upload Configs'
        ordering = ['label']
        unique_together = [('model_path',)]

    def __str__(self) -> str:
        return str(self.label)

    def get_model_class(self):
        """Return the Django model class for this config."""
        from django.apps import apps  # pylint: disable=import-outside-toplevel
        app_label, model_name = self.model_path.split('.')
        return apps.get_model(app_label, model_name)

    def get_unique_fields_list(self):
        """Return unique_fields as a clean list."""
        return [f.strip() for f in self.unique_fields.split(',') if f.strip()]

class CSVTableColumnMapping(models.Model):
    """Mapea una columna CSV a un campo del modelo para un CSVTableUploadConfig."""
    config      = models.ForeignKey(CSVTableUploadConfig, on_delete=models.CASCADE, related_name='column_mappings')
    csv_column  = models.CharField(max_length=200)
    model_field = models.CharField(max_length=100)

    class Meta:
        db_table = 'csv_table_column_mapping'
        verbose_name = 'Column Mapping'
        verbose_name_plural = 'Column Mappings'
        unique_together = [('config', 'csv_column')]
        ordering = ['csv_column']

    def __str__(self):
        return f'{self.csv_column} → {self.model_field}'

# ── Script Run Config ─────────────────────────────────────────────────────────
class ScriptRunConfig(models.Model):
    """Script Python ejecutado on-demand o en schedule. `run_date` se pasa como primer argumento."""
    class RunStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        OK      = 'ok',      'OK'
        ERROR   = 'error',   'Error'
    name             = models.CharField(max_length=120, unique=True)
    description      = models.TextField(blank=True)
    script_path      = models.CharField(max_length=500)
    run_date         = models.DateField(default=date.today)
    date_format      = models.CharField(max_length=30, default='%Y-%m-%d')
    cron_schedule    = models.CharField(max_length=100, blank=True)
    active           = models.BooleanField(default=True)
    last_run_at      = models.DateTimeField(null=True, blank=True, editable=False)
    last_run_status  = models.CharField(max_length=20, choices=RunStatus.choices, default=RunStatus.PENDING, editable=False)
    last_run_message = models.TextField(blank=True, editable=False)

    class Meta:
        db_table = 'script_run_config'
        verbose_name = 'Script Run Config'
        verbose_name_plural = 'Script Run Configs'
        ordering = ['name']

    def __str__(self) -> str:
        return str(self.name)

# ── Ansible Group Vars ────────────────────────────────────────────────────────
class AnsibleGroupVar(models.Model):
    """Variable clave-valor para un grupo de inventario Ansible."""
    group_name   = models.CharField(max_length=100)
    key          = models.CharField(max_length=100)
    value        = models.CharField(max_length=1000, blank=True)
    is_sensitive = models.BooleanField(default=False)
    notes        = models.CharField(max_length=200, blank=True)

    class Meta:
        db_table = 'ansible_group_var'
        verbose_name = 'Ansible Group Var'
        verbose_name_plural = 'Ansible Group Vars'
        unique_together = [('group_name', 'key')]
        ordering = ['group_name', 'key']

    def __str__(self):
        return f'{self.group_name} / {self.key}'

class AnsibleInventoryFile(models.Model):
    """Archivo de inventario INI de Ansible en el filesystem del servidor."""
    ENV_PRODUCTION = 'PRODUCTION'
    ENV_PRE        = 'PRE-PRODUCTION'
    ENV_DRP        = 'DRP'
    ENV_CHOICES = [
        (ENV_PRODUCTION, 'Production'),
        (ENV_PRE,        'Pre-Production'),
        (ENV_DRP,        'DRP'),
    ]
    name        = models.CharField(max_length=100)
    file_path   = models.CharField(max_length=500)
    environment = models.CharField(max_length=20, choices=ENV_CHOICES)
    description = models.CharField(max_length=300, blank=True)

    class Meta:
        db_table = 'ansible_inventory_file'
        verbose_name = 'Ansible Inventory File'
        verbose_name_plural = 'Ansible Inventory Files'
        ordering = ['environment', 'name']

    def __str__(self):
        return f'{self.name} ({self.get_environment_display()})'

class DocEntry(models.Model):
    """Catálogo de documentos con enlace a recursos externos."""
    name        = models.CharField(max_length=200, verbose_name='Nombre')
    description = models.TextField(blank=True, verbose_name='Descripción')
    url         = models.URLField(max_length=500, verbose_name='URL')
    category    = models.CharField(max_length=100, blank=True, verbose_name='Categoría')
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table            = 'doc_entry'
        ordering            = ['category', 'name']
        verbose_name        = 'Doc Entry'
        verbose_name_plural = 'Doc Entries'

    def __str__(self) -> str:
        return self.name

class DirectoryEntry(models.Model):
    """Directorio de números importantes (proveedores, soporte, emergencias)."""
    name        = models.CharField(max_length=200, verbose_name='Nombre / Proveedor')
    number      = models.CharField(max_length=100, verbose_name='Número')
    description = models.TextField(blank=True, verbose_name='Descripción')
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table            = 'directory_entry'
        ordering            = ['name']
        verbose_name        = 'Directory Entry'
        verbose_name_plural = 'Directory Entries'

    def __str__(self) -> str:
        return f"{self.name} — {self.number}"

# ── Signal: auto-create BitacoraHardening when a 'failed' check is saved ──────
@receiver(post_save, sender=LBHardening)
def _create_hardening_ticket(sender, instance, **kwargs):
    """When a LBHardening row with resultado='failed' is saved, open (or reuse)  a BitacoraHardening ticket for that (device, code, fecha) combination."""
    if instance.resultado != 'failed':
        return
    existing = BitacoraHardening.objects.filter(
        device=instance.device,
        code=instance.code,
        fecha=instance.fecha,
        status__in=[BitacoraHardening.Status.OPEN, BitacoraHardening.Status.IN_PROGRESS],
    ).first()
    if not existing:
        BitacoraHardening.objects.create(
            hardening=instance,
            device=instance.device,
            code=instance.code,
            descripcion=instance.descripcion,
            valor_obtenido=instance.valor_obtenido,
            valor_recomendado=instance.valor_recomendado,
            fecha=instance.fecha,
            status=BitacoraHardening.Status.OPEN,
        )
