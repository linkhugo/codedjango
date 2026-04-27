from django.conf import settings
from django.db import models


class DDIService(models.Model):
    """DNS/DHCP service record imported from Infoblox Grid."""

    ref = models.CharField(max_length=255, primary_key=True, db_column='_ref')
    service = models.CharField(max_length=32, blank=True, null=True)
    status = models.CharField(max_length=32, blank=True, null=True)
    description = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = 'ddi_services'
        verbose_name = 'DDI Service'
        verbose_name_plural = 'DDI Services'

    def __str__(self):
        return str(self.service or self.ref)


class DDILicense(models.Model):
    """Hardware license record for a DDI appliance."""

    hwid = models.CharField(max_length=64, primary_key=True)
    type = models.CharField(max_length=32, blank=True, null=True)
    kind = models.CharField(max_length=32, blank=True, null=True)
    expiry_date = models.DateTimeField(blank=True, null=True)
    expiration_status = models.CharField(max_length=64, blank=True, null=True)

    class Meta:
        db_table = 'ddi_licenses'
        verbose_name = 'DDI License'
        verbose_name_plural = 'DDI Licenses'

    def __str__(self):
        return str(self.hwid)


class DDIDevice(models.Model):
    """DDI appliance inventory: Infoblox, NTP, or other DNS device."""

    class Environment(models.TextChoices):
        DRP            = 'DRP',            'DRP'
        PRE_PRODUCTION = 'PRE-PRODUCTION', 'PRE-PRODUCTION'
        PRODUCTION     = 'PRODUCTION',     'PRODUCTION'

    class TipoChoices(models.TextChoices):
        INFOBLOX  = 'Infoblox',  'Infoblox'
        OTHER_DNS = 'Other DNS', 'Other DNS'
        NTP       = 'NTP',       'NTP'

    device           = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    service          = models.ForeignKey(DDIService, on_delete=models.SET_NULL, null=True, blank=True, db_column='_ref', to_field='ref', related_name='devices')
    platform         = models.CharField(max_length=32, blank=True, null=True)
    license          = models.ForeignKey(DDILicense, on_delete=models.SET_NULL, null=True, blank=True, db_column='hwid', to_field='hwid', related_name='devices')
    model            = models.CharField(max_length=32, blank=True, null=True)
    hwplatform       = models.CharField(max_length=32, blank=True, null=True)
    mgmt_ip          = models.CharField(max_length=32, blank=True, null=True)
    service_ip       = models.CharField(max_length=32, blank=True, null=True)
    sw_version       = models.CharField(max_length=32, blank=True, null=True)
    datacenter       = models.ForeignKey('lb_manager.Datacenter', on_delete=models.SET_NULL, null=True, blank=True, db_column='datacenter_id', related_name='ddi_devices')
    phy_location     = models.CharField(max_length=255, blank=True, null=True)
    company          = models.ForeignKey('lb_manager.Company', on_delete=models.SET_NULL, null=True, blank=True, db_column='company_id', related_name='ddi_devices')
    role             = models.CharField(max_length=255, blank=True, null=True)
    tipo             = models.CharField(max_length=32, choices=TipoChoices.choices, blank=True, null=True, verbose_name='Tipo')
    environment      = models.CharField(max_length=32, choices=Environment.choices, blank=True, null=True)
    net_zone         = models.CharField(max_length=32, blank=True, null=True)
    vendor_support   = models.CharField(max_length=255, blank=True, null=True)
    master_candidate = models.BooleanField(default=False)
    grid_master      = models.CharField(max_length=255, blank=True, null=True)
    monitoreo        = models.BooleanField(default=False)
    cyberark         = models.BooleanField(default=False)
    user_cyberark    = models.CharField(max_length=255, blank=True, null=True)
    url_cyberark     = models.CharField(max_length=2083, blank=True, null=True)
    last_modified    = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ddi_devices'
        verbose_name = 'DDI Device'
        verbose_name_plural = 'DDI Devices'

    def __str__(self):
        return str(self.device or self.pk)


class DDISnow(models.Model):
    """ServiceNow CMDB link for a DDI device."""

    device    = models.OneToOneField(DDIDevice, on_delete=models.CASCADE, primary_key=True, db_column='device_id', related_name='snow')
    cmdb_id   = models.CharField(max_length=12, blank=True, null=True)
    snow_link = models.CharField(max_length=2083, blank=True, null=True)

    class Meta:
        db_table = 'ddi_snow'
        verbose_name = 'DDI SNOW'

    def __str__(self):
        return f'SNOW for {self.device_id}'


class DDIDeviceChangeLog(models.Model):
    """Audit trail of field-level changes made to DDI devices."""

    device_id  = models.IntegerField(db_index=True)
    device     = models.CharField(max_length=255, db_index=True)
    user       = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='ddi_device_changes')
    timestamp  = models.DateTimeField(auto_now_add=True)
    field_name = models.CharField(max_length=100)
    old_value  = models.TextField(blank=True, null=True)
    new_value  = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'ddi_device_changelog'
        ordering = ['-timestamp']

    def __str__(self):
        return f'{self.device} · {self.field_name}'


class HealthCheckDDI(models.Model):
    """Snapshot diario de salud de un miembro del Grid DDI (Infoblox)."""

    fqdn               = models.CharField(max_length=255, db_index=True)
    fecha              = models.DateField(db_index=True)
    platform           = models.CharField(max_length=32, blank=True, null=True)
    grid_status        = models.CharField(max_length=64, blank=True, null=True)
    is_ha              = models.BooleanField(default=False)
    ha_state           = models.CharField(max_length=64, blank=True, null=True)
    pnode_role         = models.CharField(max_length=64, blank=True, null=True)
    master_candidate   = models.BooleanField(default=False)
    dns_service        = models.CharField(max_length=64, blank=True, null=True)
    dns_zones_count    = models.IntegerField(default=0)
    dns_zones_disabled = models.IntegerField(default=0)
    dhcp_service       = models.CharField(max_length=64, blank=True, null=True)
    dhcp_failover      = models.CharField(max_length=64, blank=True, null=True)
    leases_activos     = models.IntegerField(default=0)
    leases_abandonados = models.IntegerField(default=0)
    leases_declinados  = models.IntegerField(default=0)
    networks_total     = models.IntegerField(default=0)
    networks_en_riesgo = models.IntegerField(default=0)
    networks_criticas  = models.IntegerField(default=0)
    # backup_enabled / ntp_enabled: Ansible serializa booleanos Jinja2 como
    # string 'True'/'False'; CharField evita errores de conversión silenciosa.
    backup_enabled     = models.CharField(max_length=8, blank=True, null=True)
    backup_status      = models.CharField(max_length=64, blank=True, null=True)
    backup_tipo        = models.CharField(max_length=32, blank=True, null=True)
    ntp_enabled        = models.CharField(max_length=8, blank=True, null=True)
    ntp_servers_count  = models.IntegerField(default=0)
    cpu_pct            = models.IntegerField(null=True, blank=True)
    mem_pct            = models.IntegerField(null=True, blank=True)
    disk_pct           = models.IntegerField(null=True, blank=True)
    uptime_dias        = models.IntegerField(null=True, blank=True)

    class Meta:
        db_table = 'health_check_ddi'
        ordering = ['-fecha', 'fqdn']
        unique_together = [('fqdn', 'fecha')]
        verbose_name = 'DDI Health Check'
        verbose_name_plural = 'DDI Health Checks'

    def __str__(self) -> str:
        return f"{self.fqdn} — {self.fecha}"
