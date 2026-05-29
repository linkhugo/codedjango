"""
Management command: seed_lb_change_templates

Creates standard checklist templates for F5 upgrades and migrations.
Safe to run multiple times — uses get_or_create to avoid duplicates.

Usage:
    python manage.py seed_lb_change_templates
    python manage.py seed_lb_change_templates --force          # recreate ALL
    python manage.py seed_lb_change_templates --force --name "Upgrade Guest / Tenant"
"""
from django.core.management.base import BaseCommand

from lb_manager.models import LBChangeTemplate, LBChangeTemplateItem

# ---------------------------------------------------------------------------
# Item tuple format:
#   (phase, order, text, required, comment_required_on, key)
#
# phase              : 'initial' | 'pre' | 'post'
# required           : True = must answer; pre/post must answer 'yes' to sign
# comment_required_on: 'yes' | 'no' | '' = when comment is mandatory
# key                : string identifier used to resolve linked_item FKs, or None
# ---------------------------------------------------------------------------

TEMPLATES_DATA = [
    # ════════════════════════════════════════════════════════════════════════
    # 1. UPGRADE GUEST / TENANT
    # ════════════════════════════════════════════════════════════════════════
    {
        'name':        'Upgrade Guest / Tenant',
        'change_type': 'upgrade',
        'description': 'Checklist estándar de 3 fases para upgrade de software F5 Guest/Tenant.',
        'items': [
            # ── Validación Inicial ────────────────────────────────────────
            ('initial',  1, 'Tener la ISO de la Versión Cargada en los Equipos',              True,  '',    'iso_cargada'),
            ('initial',  2, 'Revisión de Service Check Date',                                 True,  '',    None),
            ('initial',  3, 'Revisión de Espacio para Instalación de ISO — indicar el HD',    True,  'yes', 'espacio_hd'),
            ('initial',  4, 'Se tiene MAC Masquerade configurada',                            True,  'no',  'mac_masq'),
            ('initial',  5, 'Se tiene configurada la VLAN de VIP como FailSafe',              True,  'no',  'vlan_failsafe'),
            ('initial',  6, 'Se tiene configurado NTP',                                       True,  'no',  'ntp'),
            ('initial',  7, 'Se tiene configurado DNS',                                       True,  'no',  'dns'),
            ('initial',  8, 'Se tiene configurado el Config Sync mediante la MGMT',           True,  'no',  'sync_mgmt'),
            ('initial',  9, 'Se tiene el Banner Correcto (Primary – Green / Secondary – Orange)',
                                                                                              True,  'no',  'banner'),
            ('initial', 10, 'Se tiene configurado Sync Failover Automatic with Incremental Sync',
                                                                                              True,  'no',  'sync_failover'),
            ('initial', 11, 'Se tiene Descripción Correcta en Banner',                        True,  'no',  'banner_desc'),
            ('initial', 12, 'Se tiene Configurado MGMT en Large',                             True,  'no',  'mgmt_large'),
            ('initial', 13, 'Se tiene Configurado LTM como Dedicado',                         True,  'no',  'ltm_dedicado'),
            ('initial', 14, 'Otros',                                                          False, 'no',  None),
            # ── Pre-Check ─────────────────────────────────────────────────
            ('pre',  1, 'ISO Cargada en el equipo',                                           True,  '',    'link_iso_cargada'),
            ('pre',  2, 'Instalación de ISO en: (ver comentario de Validación Inicial)',      True,  '',    'link_espacio_hd'),
            ('pre',  3, 'Obtener Backups (UCS)',                                              True,  '',    None),
            ('pre',  4, 'Sincronizar LB',                                                     True,  '',    None),
            ('pre',  5, 'Verificar Configuración',                                            True,  '',    None),
            ('pre',  6, 'Obtención de SelfIP / Route Domains / Routes',                      True,  '',    None),
            ('pre',  7, 'Obtener Status Summary',                                             True,  '',    None),
            ('pre',  8, 'Obtener Estadísticas',                                               True,  '',    None),
            # ── Post-Check ────────────────────────────────────────────────
            ('post',  1, 'Obtención de SelfIP / Route Domains / Routes y revisión vs Pre-Check',
                                                                                              True,  '',    None),
            ('post',  2, 'Parar Servicio Named',                                              True,  '',    None),
            ('post',  3, 'Obtener Status Summary y comparar vs Pre-Check',                   True,  '',    None),
            ('post',  4, 'Obtener Estadísticas y comparar vs Pre-Check',                     True,  '',    None),
            ('post',  5, 'Configurar MAC Masquerade (ver nota de Validación Inicial)',        True,  '',    'link_mac_masq'),
            ('post',  6, 'Configurar VLAN de VIP como FailSafe (ver nota de Validación Inicial)',
                                                                                              True,  '',    'link_vlan_failsafe'),
            ('post',  7, 'Configurar NTP',                                                    True,  '',    'link_ntp'),
            ('post',  8, 'Configurar DNS',                                                    True,  '',    'link_dns'),
            ('post',  9, 'Configurar Sync mediante MGMT',                                     True,  '',    'link_sync_mgmt'),
            ('post', 10, 'Configurar Banner (Primary – Green / Secondary – Orange)',          True,  '',    'link_banner'),
            ('post', 11, 'Configurar Sync Failover Automatic with Incremental Sync',          True,  '',    'link_sync_failover'),
            ('post', 12, 'Configurar Descripción Correcta en Banner',                         True,  '',    'link_banner_desc'),
            ('post', 13, 'Validación de CyberArk',                                            True,  '',    None),
            ('post', 14, 'Configurar MGMT en Large (ver nota de Validación Inicial)',         True,  '',    'link_mgmt_large'),
            ('post', 15, 'Configurar LTM como Dedicado (sea el caso)',                        True,  '',    'link_ltm_dedicado'),
            ('post', 16, 'Otros',                                                             False, '',    None),
        ],
        'link_map': {
            'link_iso_cargada':   'iso_cargada',
            'link_espacio_hd':    'espacio_hd',
            'link_mac_masq':      'mac_masq',
            'link_vlan_failsafe': 'vlan_failsafe',
            'link_ntp':           'ntp',
            'link_dns':           'dns',
            'link_sync_mgmt':     'sync_mgmt',
            'link_banner':        'banner',
            'link_sync_failover': 'sync_failover',
            'link_banner_desc':   'banner_desc',
            'link_mgmt_large':    'mgmt_large',
            'link_ltm_dedicado':  'ltm_dedicado',
        },
    },

    # ════════════════════════════════════════════════════════════════════════
    # 2. MIGRACIÓN GUEST / TENANT
    # ════════════════════════════════════════════════════════════════════════
    {
        'name':        'Migración Guest / Tenant',
        'change_type': 'migration',
        'description': 'Checklist estándar de 3 fases para migración de F5 Guest/Tenant a nuevo destino.',
        'items': [
            # ── Validación Inicial ────────────────────────────────────────
            ('initial',  1, 'Se crearon Tenant en el Destino',
                                                                                              True,  'yes', 'tenant_destino'),
            ('initial',  2, 'Validación de VLAN/IP en el Destino',
                                                                                              True,  'yes', 'vlan_ip_destino'),
            ('initial',  3, 'Verificación de VLAN no asociadas en el Tenant Destino, pero sí creadas en el Tenant',
                                                                                              True,  '',    None),
            ('initial',  4, 'Se tiene MAC Masquerade configurada',                            True,  'no',  'mac_masq'),
            ('initial',  5, 'Se tiene configurada la VLAN de VIP como FailSafe',              True,  'no',  'vlan_failsafe'),
            ('initial',  6, 'Se tiene configurado NTP',                                       True,  'no',  'ntp'),
            ('initial',  7, 'Se tiene configurado DNS',                                       True,  'no',  'dns'),
            ('initial',  8, 'Se tiene configurado el Config Sync mediante la MGMT',           True,  'no',  'sync_mgmt'),
            ('initial',  9, 'Se tiene el Banner Correcto (Primary – Green / Secondary – Orange)',
                                                                                              True,  'no',  'banner'),
            ('initial', 10, 'Se tiene configurado Sync Failover Automatic with Incremental Sync',
                                                                                              True,  'no',  'sync_failover'),
            ('initial', 11, 'Se tiene Descripción Correcta en Banner',                        True,  'no',  'banner_desc'),
            ('initial', 12, 'Se tiene Configurado MGMT en Large',                             True,  'no',  'mgmt_large'),
            ('initial', 13, 'Se tiene Configurado LTM como Dedicado',                         True,  'no',  'ltm_dedicado'),
            ('initial', 14, 'Otros',                                                          False, 'no',  None),
            # ── Pre-Check ─────────────────────────────────────────────────
            ('pre',  1, 'Sincronizar LB',                                                     True,  '',    None),
            ('pre',  2, 'Cambiar Usuario de N1 a Guest',                                      True,  '',    None),
            ('pre',  3, 'Obtener Backups',                                                    True,  '',    None),
            ('pre',  4, 'Edición de Backups con Nuevas IP MGMT (ver Tenant Destino)',         True,  '',    'link_tenant_destino'),
            ('pre',  5, 'Obtener Key Master y Montar en los Nuevos',                          True,  '',    None),
            ('pre',  6, 'Montar UCS a los Nuevos Tenant',                                     True,  '',    None),
            ('pre',  7, 'Hacer Upgrade sea el Caso',                                          True,  '',    None),
            ('pre',  8, 'Configurar MAC Masquerade (ver nota de Validación Inicial)',         True,  '',    'link_mac_masq'),
            ('pre',  9, 'Configurar VLAN de VIP como FailSafe (ver nota de Validación Inicial)',
                                                                                              True,  '',    'link_vlan_failsafe'),
            ('pre', 10, 'Configurar NTP',                                                     True,  '',    'link_ntp'),
            ('pre', 11, 'Configurar DNS',                                                     True,  '',    'link_dns'),
            ('pre', 12, 'Configurar Sync mediante MGMT',                                      True,  '',    'link_sync_mgmt'),
            ('pre', 13, 'Configurar Banner (Primary – Green / Secondary – Orange)',           True,  '',    'link_banner'),
            ('pre', 14, 'Configurar Sync Failover Automatic with Incremental Sync',           True,  '',    'link_sync_failover'),
            ('pre', 15, 'Configurar Descripción Correcta en Banner',                          True,  '',    'link_banner_desc'),
            ('pre', 16, 'Configurar MGMT en Large',                                           True,  '',    'link_mgmt_large'),
            ('pre', 17, 'Configurar LTM como Dedicado (sea el caso)',                         True,  '',    'link_ltm_dedicado'),
            ('pre', 18, 'Otros',                                                              False, '',    None),
            ('pre', 19, 'Obtención de SelfIP / Route Domains / Routes (Old Devices)',         True,  '',    None),
            ('pre', 20, 'Obtener Status Summary (Old Devices)',                               True,  '',    None),
            ('pre', 21, 'Obtener Estadísticas (Old Devices)',                                 True,  '',    None),
            # ── Post-Check ────────────────────────────────────────────────
            ('post',  1, 'Obtención de SelfIP / Route Domains / Routes y revisión vs Pre-Check',
                                                                                              True,  '',    None),
            ('post',  2, 'Parar Servicio Named',                                              True,  '',    None),
            ('post',  3, 'Obtener Status Summary vs Pre-Check',                               True,  '',    None),
            ('post',  4, 'Obtener Estadísticas vs Pre-Check',                                 True,  '',    None),
            ('post',  5, 'Eliminar User ServiceNow (SNMP)',                                   True,  '',    None),
            ('post',  6, 'Cambiar IP al DNS',                                                 True,  '',    None),
            ('post',  7, 'Crear Ticket de Monitoreo',                                         True,  'yes', None),
            ('post',  8, 'Crear Ticket de CMDB',                                              True,  'yes', None),
            ('post',  9, 'Regresar Permisos a N1',                                            True,  '',    None),
            ('post', 10, 'Validación de CyberArk N1/N2',                                      True,  '',    None),
        ],
        'link_map': {
            'link_tenant_destino': 'tenant_destino',
            'link_mac_masq':       'mac_masq',
            'link_vlan_failsafe':  'vlan_failsafe',
            'link_ntp':            'ntp',
            'link_dns':            'dns',
            'link_sync_mgmt':      'sync_mgmt',
            'link_banner':         'banner',
            'link_sync_failover':  'sync_failover',
            'link_banner_desc':    'banner_desc',
            'link_mgmt_large':     'mgmt_large',
            'link_ltm_dedicado':   'ltm_dedicado',
        },
    },
]


class Command(BaseCommand):
    """Seed standard LB change checklist templates."""

    help = 'Creates standard checklist templates for F5 upgrades and migrations.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Elimina y recrea los templates existentes.',
        )
        parser.add_argument(
            '--name',
            type=str,
            default='',
            help='Aplicar solo al template con este nombre (vacío = todos).',
        )

    def handle(self, *args, **options):
        if not __import__('django').conf.settings.DEBUG:
            raise SystemExit('Este comando solo puede ejecutarse con DEBUG=True.')

        force       = options['force']
        filter_name = options['name'].strip()
        created_n   = 0
        skipped_n   = 0

        for tpl_data in TEMPLATES_DATA:
            name = tpl_data['name']
            if filter_name and filter_name != name:
                continue

            if force:
                deleted, _ = LBChangeTemplate.objects.filter(name=name).delete()
                if deleted:
                    self.stdout.write(f'  [{name}] Eliminada (--force).')

            tpl, created = LBChangeTemplate.objects.get_or_create(
                name=name,
                defaults={
                    'change_type': tpl_data['change_type'],
                    'description': tpl_data['description'],
                    'active':      True,
                },
            )

            if not created:
                self.stdout.write(f'  [{name}] Ya existe (usa --force para recrear).')
                skipped_n += 1
                continue

            self.stdout.write(f'  [{name}] Creando...')
            item_by_key = {}

            for (phase, order, text, required, comment_on, key) in tpl_data['items']:
                item = LBChangeTemplateItem.objects.create(
                    template            = tpl,
                    phase               = phase,
                    order               = order,
                    text                = text,
                    required            = required,
                    comment_required_on = comment_on,
                )
                if key:
                    item_by_key[key] = item

            for item_key, target_key in tpl_data['link_map'].items():
                src = item_by_key.get(item_key)
                tgt = item_by_key.get(target_key)
                if src and tgt:
                    src.linked_item = tgt
                    src.save(update_fields=['linked_item'])

            n_items = LBChangeTemplateItem.objects.filter(template=tpl).count()
            n_links = LBChangeTemplateItem.objects.filter(template=tpl, linked_item__isnull=False).count()
            self.stdout.write(f'  [{name}] {n_items} ítems, {n_links} links.')
            created_n += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'\nListo: {created_n} plantilla(s) creada(s), {skipped_n} omitida(s).'
            )
        )
