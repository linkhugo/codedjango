"""
URL routing for the lb_manager application.

Each path() entry maps a URL pattern to a view. The convention used here:
  - List pages   : /resource/           → ResourceListView (HTML page)
  - AJAX data    : /resource/data/      → resource_data()  (JSON for DataTables)
  - Create       : /resource/add/       → ResourceCreateView
  - Edit         : /resource/<pk>/edit/ → ResourceUpdateView
  - Delete       : /resource/<pk>/delete/ → ResourceDeleteView

The 'name' argument on each path() gives it an alias so templates and
redirects can reference it by name instead of hard-coding the URL string
(e.g. {% url 'vip_list' %} instead of '/vips/').

All views require the user to be logged in. CRUD views additionally require
the corresponding Django permission (add_*, change_*, delete_*).
"""

from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('contact-admin/', views.contact_admin, name='contact_admin'),
    path('search/', views.global_search, name='global_search'),
    path('wiki/', views.wiki, name='wiki'),
    path('charts/', views.charts, name='charts'),

    # Services
    path('services/', views.ServicioListView.as_view(), name='servicio_list'),
    path('services/data/', views.servicio_data, name='servicio_data'),
    path('services/sync/', views.servicio_sync, name='servicio_sync'),
    path('services/<int:pk>/edit/', views.servicio_edit, name='servicio_edit'),
    path('ssl/dashboard/', views.ssl_dashboard, name='ssl_dashboard'),
    path('ssl/certs/', views.SSLCertListView.as_view(), name='ssl_cert_list'),
    path('ssl/certs/data/', views.ssl_cert_data, name='ssl_cert_data'),
    path('ssl/profiles/', views.SSLProfileListView.as_view(), name='ssl_profile_list'),
    path('ssl/profiles/data/', views.ssl_profile_data, name='ssl_profile_data'),
    path('ssl/vips-expired/', views.vip_expired_ssl, name='vip_expired_ssl'),
    path('ssl/hostname-search/', views.ssl_hostname_search, name='ssl_hostname_search'),

    # Load Balancer
    path('vips/', views.VIPListView.as_view(), name='vip_list'),
    path('vips/data/', views.vip_data, name='vip_data'),
    path('vips/lookup/', views.vip_lookup, name='vip_lookup'),
    path('vips/<int:pk>/edit/', views.VIPUpdateView.as_view(), name='vip_edit'),
    path('vips/dormant/', views.VIPDormantListView.as_view(), name='vip_dormant_list'),
    path('vips/dormant/data/', views.vip_dormant_data, name='vip_dormant_data'),
    path('pools/', views.PoolListView.as_view(), name='pool_list'),
    path('pools/data/', views.pool_data, name='pool_data'),
    path('pools/lookup/', views.pool_lookup, name='pool_lookup'),
    path('ip-balance-check/', views.ip_balance_check, name='ip_balance_check'),
    path('ip-vip-tls/', views.ip_vip_tls_check, name='ip_vip_tls_check'),
    path('pools/unassigned/', views.UnassignedPoolListView.as_view(), name='unassigned_pool_list'),
    path('pools/unassigned/data/', views.unassigned_pool_data, name='unassigned_pool_data'),
    path('nodes/', views.NodeListView.as_view(), name='node_list'),
    path('nodes/data/', views.node_data, name='node_data'),
    path('nodes/unassigned/', views.UnassignedNodeListView.as_view(), name='unassigned_node_list'),
    path('nodes/unassigned/data/', views.unassigned_node_data, name='unassigned_node_data'),
    path('self-ips/', views.SelfIPListView.as_view(), name='self_ip_list'),
    path('self-ips/data/', views.self_ip_data, name='self_ip_data'),
    path('snats/', views.SNATListView.as_view(), name='snat_list'),
    path('snats/data/', views.snat_data, name='snat_data'),

    # Health Monitoring
    path('health/f5/backups/', views.HealthF5BackupsView.as_view(), name='health_f5_backups'),
    path('health/f5/', views.HealthF5ListView.as_view(), name='health_f5_list'),
    path('health/dhcp/', views.HealthDHCPListView.as_view(), name='health_dhcp_list'),
    path('health/dns/', views.HealthDNSListView.as_view(), name='health_dns_list'),
    path('health/certificates/', views.HealthCertificateListView.as_view(), name='health_certificate_list'),
    path('health/bitacora/', views.BitacoraListView.as_view(), name='bitacora_list'),
    path('health/bitacora/data/', views.bitacora_data, name='bitacora_data'),
    path('health/bitacora/<int:pk>/edit/', views.bitacora_edit, name='bitacora_edit'),
    path('health/bitacora/export/', views.bitacora_export, name='bitacora_export'),
    path('health/bitacora/bulk/', views.bitacora_bulk_action, name='bitacora_bulk_action'),
    path('health/bitacora/ticket/<str:ticket_ref>/', views.bitacora_ticket_redirect, name='bitacora_ticket_redirect'),
    path('health/rules/', views.HealthRuleListView.as_view(), name='health_rule_list'),
    path('health/rules/add/', views.HealthRuleCreateView.as_view(), name='health_rule_add'),
    path('health/rules/<int:pk>/edit/', views.HealthRuleUpdateView.as_view(), name='health_rule_edit'),
    path('health/rules/<int:pk>/delete/', views.HealthRuleDeleteView.as_view(), name='health_rule_delete'),

    # Ansible Inventory Editor
    path('infrastructure/ansible-inventory/', views.ansible_inventory, name='ansible_inventory'),

    # Infrastructure - LB Physical
    path('infrastructure/lb-physical/', views.LBPhysicalListView.as_view(), name='lb_physical_list'),
    path('infrastructure/lb-physical/add/', views.LBPhysicalCreateView.as_view(), name='lb_physical_add'),
    path('infrastructure/lb-physical/<str:pk>/edit/', views.LBPhysicalUpdateView.as_view(), name='lb_physical_edit'),
    path('infrastructure/lb-physical/<str:pk>/delete/', views.LBPhysicalDeleteView.as_view(), name='lb_physical_delete'),

    # Infrastructure - LB Guest
    path('infrastructure/lb-guest/', views.LBGuestListView.as_view(), name='lb_guest_list'),
    path('infrastructure/lb-guest/add/', views.LBGuestCreateView.as_view(), name='lb_guest_add'),
    path('infrastructure/lb-guest/<str:pk>/edit/', views.LBGuestUpdateView.as_view(), name='lb_guest_edit'),
    path('infrastructure/lb-guest/<str:pk>/delete/', views.LBGuestDeleteView.as_view(), name='lb_guest_delete'),

    # Infrastructure - Companies
    path('infrastructure/companies/', views.CompanyListView.as_view(), name='company_list'),
    path('infrastructure/companies/add/', views.CompanyCreateView.as_view(), name='company_add'),
    path('infrastructure/companies/<int:pk>/edit/', views.CompanyUpdateView.as_view(), name='company_edit'),
    path('infrastructure/companies/<int:pk>/delete/', views.CompanyDeleteView.as_view(), name='company_delete'),

    # Infrastructure - Datacenters
    path('infrastructure/datacenters/', views.DatacenterListView.as_view(), name='datacenter_list'),
    path('infrastructure/datacenters/add/', views.DatacenterCreateView.as_view(), name='datacenter_add'),
    path('infrastructure/datacenters/<int:pk>/edit/', views.DatacenterUpdateView.as_view(), name='datacenter_edit'),
    path('infrastructure/datacenters/<int:pk>/delete/', views.DatacenterDeleteView.as_view(), name='datacenter_delete'),

    # Historical
    path('historical/vips/', views.LBVIPHistoricalListView.as_view(), name='lb_vip_historical_list'),
    path('historical/vips/data/', views.lb_vip_historical_data, name='lb_vip_historical_data'),
    path('historical/vips/diff/', views.vip_config_diff, name='vip_config_diff'),

    # Unified LB Inventory (LBGuest UNION LBPhysical)
    path('infrastructure/inventory/', views.LBInventoryListView.as_view(), name='lb_inventory_list'),
    path('infrastructure/inventory/data/', views.lb_inventory_data, name='lb_inventory_data'),
    path('infrastructure/inventory/device-history/<str:device>/', views.lb_device_history, name='lb_device_history'),

    # CMDB Validation
    path('infrastructure/cmdb-validation/', views.cmdb_vs_lb_inventory, name='cmdb_validation'),

    # Autocomplete
    path('autocomplete/', views.autocomplete_data, name='autocomplete_data'),

    # Hardening / Vulnerabilities
    path('hardening/', views.LBHardeningListView.as_view(), name='lb_hardening_list'),
    path('hardening/data/', views.lb_hardening_data, name='lb_hardening_data'),

    # Bitácora Hardening
    path('hardening/bitacora/', views.BitacoraHardeningListView.as_view(), name='bitacora_hardening_list'),
    path('hardening/bitacora/data/', views.bitacora_hardening_data, name='bitacora_hardening_data'),
    path('hardening/bitacora/<int:pk>/edit/', views.bitacora_hardening_edit, name='bitacora_hardening_edit'),

    # Hardening Chart
    path('hardening/chart/', views.hardening_chart, name='hardening_chart'),
    path('hardening/chart/data/', views.hardening_chart_data, name='hardening_chart_data'),

    # HealthCheck LB Chart
    path('healthcheck/chart/', views.healthcheck_lb_chart, name='healthcheck_lb_chart'),
    path('healthcheck/chart/data/', views.healthcheck_lb_chart_data, name='healthcheck_lb_chart_data'),

    # CPU Usage Chart
    path('healthcheck/cpu/', views.cpu_chart, name='cpu_chart'),
    path('healthcheck/cpu/data/', views.cpu_chart_data, name='cpu_chart_data'),

    # CSV Table Upload
    path('csv-upload/', views.csv_upload_list, name='csv_upload_list'),
    path('csv-upload/<int:pk>/', views.csv_upload_form, name='csv_upload_form'),
    path('csv-upload/model-fields/', views.csv_model_fields, name='csv_model_fields'),

    # Documentación
    path('docs/',                        views.DocEntryListView.as_view(),          name='doc_entry_list'),
    path('docs/add/',                    views.DocEntryCreateView.as_view(),        name='doc_entry_add'),
    path('docs/<int:pk>/edit/',          views.DocEntryUpdateView.as_view(),        name='doc_entry_edit'),
    path('docs/<int:pk>/delete/',        views.DocEntryDeleteView.as_view(),        name='doc_entry_delete'),

    # Directorio de Números
    path('directorio/',                  views.DirectoryEntryListView.as_view(),    name='directory_entry_list'),
    path('directorio/add/',              views.DirectoryEntryCreateView.as_view(),  name='directory_entry_add'),
    path('directorio/<int:pk>/edit/',    views.DirectoryEntryUpdateView.as_view(),  name='directory_entry_edit'),
    path('directorio/<int:pk>/delete/',  views.DirectoryEntryDeleteView.as_view(),  name='directory_entry_delete'),

    # Database Backups (staff only)
    path('db-backups/', views.backup_list, name='backup_list'),
    path('db-backups/create/', views.backup_create, name='backup_create'),
    path('db-backups/download/<str:filename>/', views.backup_download, name='backup_download'),
    path('db-backups/delete/<str:filename>/', views.backup_delete, name='backup_delete'),
]
