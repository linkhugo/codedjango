# Documentación Técnica — Sistema de Gestión de Balanceadores de Carga

> **Audiencia:** Desarrolladores y administradores del sistema.
> Versión Django: 5.2 · Base de datos: PostgreSQL · Python: 3.14

---

## Tabla de contenidos

1. [Estructura del proyecto](#1-estructura-del-proyecto)
2. [Modelos y tablas de base de datos](#2-modelos-y-tablas-de-base-de-datos)
3. [Mapa de URLs](#3-mapa-de-urls)
4. [Arquitectura de vistas](#4-arquitectura-de-vistas)
5. [Sistema de autenticación LDAP](#5-sistema-de-autenticación-ldap)
6. [Control de acceso y permisos](#6-control-de-acceso-y-permisos)
7. [DataTables — patrón servidor/cliente](#7-datatables--patrón-servidorcliente)
8. [Cadena SSL (VIP → Perfil → Certificado)](#8-cadena-ssl-vip--perfil--certificado)
9. [Sistema de ayuda contextual](#9-sistema-de-ayuda-contextual)
10. [Comandos de gestión](#10-comandos-de-gestión)
11. [Panel de administración](#11-panel-de-administración)
12. [Configuración de entorno](#12-configuración-de-entorno)
13. [Recetas — cómo agregar cosas nuevas](#13-recetas--cómo-agregar-cosas-nuevas)

---

## 1. Estructura del proyecto

```
Django_DEV/
├── network_services/          # Configuración del proyecto Django
│   ├── settings.py            # BD, LDAP, tiempo de sesión, apps instaladas
│   └── urls.py                # Rutas raíz + GroupAwareLoginView
│
├── lb_manager/                # Aplicación principal
│   ├── models.py              # 29 modelos (tablas de BD)
│   ├── views.py               # ~86 funciones/clases de vista
│   ├── urls.py                # ~70 rutas de la app
│   ├── admin.py               # Configuración del panel /ns-mgmt/
│   ├── forms.py               # Formularios de creación/edición
│   ├── ldap_backend.py        # Backend de autenticación LDAP
│   └── management/commands/
│       ├── seed_dummy.py      # Poblar BD con datos de prueba genéricos
│       ├── seed_chain.py      # Poblar cadena SSL completa (test)
│       ├── evaluate_health_rules.py  # Evaluar reglas de salud
│       ├── sync_vips_to_servicio.py  # Sincronizar VIPs ↔ Servicio
│       └── test_ldap.py       # Probar conexión LDAP
│
├── ddi_manager/               # Aplicación secundaria (DHCP/DNS/DDI)
│
├── templates/
│   ├── base.html              # Layout principal (sidebar, header, ayuda, sesión)
│   ├── login.html             # Pantalla de inicio de sesión
│   ├── dashboard.html         # Panel principal
│   └── lb_manager/            # Templates de cada vista
│
├── static/
│   ├── css/custom.css         # Estilos propios (stat-cards, badges, etc.)
│   ├── js/custom.js           # JS global (sidebar, búsqueda, etc.)
│   └── vendor/                # jQuery, Bootstrap, DataTables, Chart.js
│
└── lb_manager/migrations/     # 34 migraciones (última: 0034_add_group_profile)
```

---

## 2. Modelos y tablas de base de datos

### Referencia rápida

| Modelo | Tabla | Descripción |
|--------|-------|-------------|
| `Company` | `company` | Empresas/clientes |
| `Datacenter` | `datacenter` | Centros de datos |
| `LBPhysical` | `lb_physical` | Equipos F5 físicos |
| `LBGuest` | `lb_guest` | Instancias F5 virtuales |
| `Servicio` | `servicio` | Servicios configurados por LTM |
| `LTMNode` | `ltm_nodes` | Nodos individuales (por IP) |
| `Pool` | `pools` | Grupos de servidores; `members` es JSON |
| `SelfIP` | `self_ips` | IPs propias del balanceador |
| `SNATTranslation` | `snats_translations` | Reglas de traducción SNAT |
| `VIP` | `vips` | Direcciones virtuales; `profiles` es JSON |
| `SSLCert` | `ssl_certs` | Certificados SSL instalados en F5 |
| `ClientSSLProfile` | `client_ssl_profiles` | Perfiles SSL cliente |
| `BitacoraHealth` | `bitacora_health` | Tickets de incidencia de salud |
| `BitacoraEvent` | `bitacora_events` | Comentarios/eventos de un ticket |
| `HealthCheckF5` | `health_check_f5` | Snapshot diario de salud F5 |
| `HealthCheckDHCP` | `health_check_dhcp` | Snapshot diario de salud DHCP |
| `HealthCheckDNS` | `health_check_dns` | Snapshot diario de salud DNS |
| `HealthCheckCertificate` | `health_check_certificate` | Snapshot diario de salud de certificados SSL/TLS |
| `HealthRule` | `health_rules` | Reglas que activan alertas automáticas |
| `LBVIPHistorical` | `lb_vips_historical` | Snapshot histórico de VIPs |
| `LBDeviceChangeLog` | `lb_device_changelog` | Historial de cambios por dispositivo |
| `LBHardening` | `lb_hardening` | Resultados de hardening por dispositivo |
| `BitacoraHardening` | `bitacora_hardening` | Tickets de incidencias de hardening |
| `LDAPGroupMap` | `ldap_group_map` | Mapeo OU de AD → Group de Django |
| `GroupProfile` | `group_profile` | Extensión de Group (login redirect URL) |
| `SiteSettings` | `site_settings` | Configuración global (singleton); incluye campos de backup |
| `LDAPConfig` | `ldap_config` | Conexión LDAP (singleton) |
| `LoginAuditLog` | `login_audit_log` | Registro de intentos de inicio de sesión |
| `CSVTableUploadConfig` | `csv_table_upload_config` | Registro de tablas elegibles para importación CSV |
| `CSVTableColumnMapping` | `csv_table_column_mapping` | Mapeo de columnas para carga manual (auto-match si vacío) |
| `CSVImportConfig` | `csv_import_config` | Jobs de importación CSV programados (schedule + file path) |
| `CSVColumnMapping` | `csv_column_mapping` | Mapeo de columnas para jobs programados (dinámico por modelo) |
| `DocEntry` | `doc_entry` | Catálogo de documentos con enlace a recursos externos (Nombre, Descripción, URL, Categoría) |
| `DirectoryEntry` | `directory_entry` | Directorio de números importantes: proveedores, soporte y emergencias (Nombre, Número, Descripción) |

### Campos JSON importantes

**`Pool.members`** — lista de objetos con estructura F5 real:
```python
[{
    "name":       "hostname.corp.local",      # nombre del nodo
    "address":    "10.10.1.5",               # IP del servidor
    "full_path":  "/Common/hostname.corp.local:443",  # contiene el puerto
    "partition":  "Common",
    "connection_limit": 0,
    "dynamic_ratio": 1,
    "real_state": "up",
    "state":      "present",
    # ... otros campos F5
}]
```

**`VIP.profiles`** — lista de perfiles asignados al VIP:
```python
[
    {"context": "all",         "full_path": "/Common/http",      "name": "http"},
    {"context": "client-side", "full_path": "/Common/mi-perfil", "name": "mi-perfil"},
    {"context": "server-side", "full_path": "/Common/serverssl", "name": "serverssl"},
]
```
> El valor de `context` es `"client-side"` (con guión), no `"clientside"`.

---

## 3. Mapa de URLs

### `network_services/urls.py` (raíz)

| URL | Vista | Descripción |
|-----|-------|-------------|
| `/ns-mgmt/` | Django admin | Solo staff/superuser |
| `/login/` | `GroupAwareLoginView` | Login con redirect por grupo |
| `/logout/` | `LogoutView` | Cierra sesión |
| `/health/` | `health_check` | Liveness probe (Docker) |
| `/*` | `lb_manager.urls` | Delegado a la app |

### `lb_manager/urls.py` — rutas principales

| Patrón | Nombre | Tipo |
|--------|--------|------|
| `/` | `dashboard` | Página (solo staff/superuser) |
| `/contact-admin/` | `contact_admin` | Página de acceso no configurado |
| `/search/` | `global_search` | Búsqueda global por IP exacta (iexact; Self IPs admiten CIDR con istartswith) |
| `/ssl/certs/` | `ssl_cert_list` | Lista + DataTable |
| `/ssl/certs/data/` | `ssl_cert_data` | JSON para DataTable |
| `/ssl/profiles/` | `ssl_profile_list` | Lista + DataTable |
| `/ssl/profiles/data/` | `ssl_profile_data` | JSON para DataTable |
| `/ssl/dashboard/` | `ssl_dashboard` | Dashboard consolidado — solo certs vinculados a VIPs |
| `/ssl/vips-expired/` | `vip_expired_ssl` | VIPs con cert vencido/por vencer (incluye subject del cert) |
| `/vips/` | `vip_list` | Lista + DataTable |
| `/vips/data/` | `vip_data` | JSON para DataTable |
| `/vips/lookup/` | `vip_lookup` | Búsqueda por nombre/IP/pool |
| `/vips/dormant/` | `vip_dormant_list` | VIPs sin tráfico reciente |
| `/pools/` | `pool_list` | Lista + DataTable |
| `/pools/lookup/` | `pool_lookup` | Búsqueda por nombre/IP |
| `/ip-balance-check/` | `ip_balance_check` | IP → Pool → VIPs |
| `/ip-vip-tls/` | `ip_vip_tls_check` | IP → VIP → TLS chain |
| `/nodes/` | `node_list` | Lista + DataTable |
| `/health/f5/` | `health_f5_list` | Health checks F5 (historial filtrable) |
| `/health/f5/backups/` | `health_f5_backups` | Estado de backups F5 — última fecha disponible |
| `/health/certificates/` | `health_certificate_list` | Health checks de certificados SSL/TLS |
| `/health/bitacora/` | `bitacora_list` | Tickets de incidencia |
| `/infrastructure/lb-physical/` | `lb_physical_list` | CRUD equipos físicos |
| `/hardening/` | `lb_hardening_list` | Resultados de hardening |
| `/csv-upload/` | `csv_upload_list` | Lista de tablas disponibles para carga manual |
| `/csv-upload/<pk>/` | `csv_upload_form` | Formulario de carga CSV para una tabla específica |
| `/csv-upload/model-fields/` | `csv_model_fields` | AJAX — campos de un modelo (`?model_path=` o `?config_id=`) |
| **Recursos** | | |
| `/docs/` | `doc_entry_list` | Lista de documentación (DataTable client-side) |
| `/docs/add/` | `doc_entry_add` | Crear entrada de documentación |
| `/docs/<pk>/edit/` | `doc_entry_edit` | Editar entrada de documentación |
| `/docs/<pk>/delete/` | `doc_entry_delete` | Eliminar entrada de documentación |
| `/directorio/` | `directory_entry_list` | Directorio de números importantes (DataTable client-side) |
| `/directorio/add/` | `directory_entry_add` | Crear entrada de directorio |
| `/directorio/<pk>/edit/` | `directory_entry_edit` | Editar entrada de directorio |
| `/directorio/<pk>/delete/` | `directory_entry_delete` | Eliminar entrada de directorio |
| `/db-backups/` | `backup_list` | Lista de backups de BD con descarga/eliminación |
| `/db-backups/create/` | `backup_create` | Crear backup manual (`pg_dump`) |
| `/db-backups/download/<filename>/` | `backup_download` | Descargar archivo `.dump` |
| `/db-backups/delete/<filename>/` | `backup_delete` | Eliminar archivo `.dump` |

---

## 4. Arquitectura de vistas

### Patrón DataTable (server-side)

La mayoría de las listas siguen este patrón de dos vistas:

```python
# 1. Vista HTML — renderiza la página vacía con la tabla
class VIPListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = VIP
    template_name = 'lb_manager/vip_list.html'
    permission_required = 'lb_manager.view_vip'

    def get_queryset(self):
        return VIP.objects.none()   # DataTable carga los datos por AJAX


# 2. Endpoint JSON — devuelve datos paginados/filtrados para DataTable
@login_required
@permission_required('lb_manager.view_vip', raise_exception=True)
def vip_data(request):
    cfg = SiteSettings.objects.first()
    max_rows = cfg.datatable_max_rows if cfg else 5000

    qs = VIP.objects.values('id', 'name', 'destination', ...)
    # filtro de búsqueda
    search = request.GET.get('search[value]', '')
    if search:
        qs = qs.filter(Q(name__icontains=search) | Q(destination__icontains=search))
    # paginación
    start  = int(request.GET.get('start', 0))
    length = int(request.GET.get('length', 25))
    total  = qs.count()
    data   = list(qs[start:start + length])
    return JsonResponse({'draw': ..., 'recordsTotal': total, 'recordsFiltered': total, 'data': data})
```

### Patrón herramienta de búsqueda (POST)

Para herramientas interactivas como `ip_balance_check` o `ip_vip_tls_check`:

```python
@login_required
def ip_balance_check(request):
    results, searched, ips_raw = [], False, ''
    if request.method == 'POST':
        searched = True
        ips_raw  = request.POST.get('ips', '')
        ips      = [ip.strip() for ip in ips_raw.splitlines() if ip.strip()]
        for ip in ips:
            # lógica de consulta...
            results.append({...})
    return render(request, 'lb_manager/ip_balance_check.html', {
        'results': results, 'searched': searched, 'ips_raw': ips_raw,
    })
```

### Vista simple (solo staff)

```python
@login_required
def dashboard(request):
    if not (request.user.is_staff or request.user.is_superuser):
        return redirect('contact_admin')
    # lógica del dashboard...
    return render(request, 'dashboard.html', context)
```

---

## 5. Sistema de autenticación LDAP

**Archivo:** `lb_manager/ldap_backend.py` — clase `LDAPTemplateBackend`

### Flujo de autenticación

```
Usuario envía user/password
    ↓
LDAPTemplateBackend.authenticate()
    ↓ Lee LDAPGroupMap (ordenado por `order`)
    ↓ Construye DN usando dn_template % {'user': username}
    ↓ Intenta bind en el servidor LDAP
    ↓ Si bind OK:
        ├── get_or_create(username=username)
        ├── Asigna django_group del LDAPGroupMap
        ├── Si grants_superuser=True → is_staff=True, is_superuser=True
        └── set_unusable_password()  ← siempre, en cada login
```

### Puntos clave

- Los usuarios LDAP **siempre** tienen `has_usable_password() == False` después del primer login. Esto es lo que los diferencia de usuarios locales.
- El admin usa `CustomUserAdmin` que bloquea `/ns-mgmt/auth/user/<id>/password/` para estos usuarios y muestra mensaje informativo en lugar del hash de contraseña.
- La configuración del servidor LDAP vive en la tabla `ldap_config` (singleton, editable desde `/ns-mgmt/`).
- Los mapeos OU → Group están en `ldap_group_map` (sin tocar código).

---

## 6. Control de acceso y permisos

### Redirect post-login

`network_services/urls.py` — `GroupAwareLoginView.get_success_url()`:

```
1. ¿El grupo del usuario tiene login_redirect_url en GroupProfile?  → ir ahí
2. ¿Es staff o superuser?                                           → dashboard (/)
3. Ninguna de las anteriores                                        → /contact-admin/
```

Para configurar el redirect de un grupo: **Admin → Groups → [grupo] → Profile → Login Redirect URL**.

### Permisos de menú (sidebar en `base.html`)

| Permiso | Controla |
|---------|---------|
| `lb_manager.view_vip` | Menú VIPs |
| `lb_manager.view_pool` | Menú Pools |
| `lb_manager.view_ltmnode` | Menú Nodes |
| `lb_manager.view_sslcert` | Submenú SSL |
| `lb_manager.view_clientsslprofile` | Submenú SSL |
| `lb_manager.view_lbphysical` | Menú Infraestructura |
| `lb_manager.view_wiki` | Menú Wiki (permiso custom) |
| `lb_manager.view_charts` | Menú Charts (permiso custom) |
| `user.is_staff` | Menú Health, Bitácora, Admin |

Los permisos custom (`view_wiki`, `view_charts`) están declarados en `LDAPGroupMap.Meta.permissions`.

### Permisos en vistas (enforcement server-side)

Todas las vistas que acceden a datos tienen **doble protección**:

1. `LoginRequiredMiddleware` (global) — requiere sesión activa.
2. `PermissionRequiredMixin` (CBVs) o `@permission_required` (FBVs) — requiere permiso específico.

Si el usuario no tiene el permiso, la vista devuelve **HTTP 403** (`raise_exception=True`).

| Vista (CBV) | Permiso requerido |
|---|---|
| `CompanyListView` | `lb_manager.view_company` |
| `DatacenterListView` | `lb_manager.view_datacenter` |
| `VIPListView`, `VIPDormantListView` | `lb_manager.view_vip` |
| `ServicioListView` | `lb_manager.view_servicio` |
| `PoolListView`, `UnassignedPoolListView` | `lb_manager.view_pool` |
| `NodeListView`, `UnassignedNodeListView` | `lb_manager.view_ltmnode` |
| `SelfIPListView` | `lb_manager.view_selfip` |
| `SNATListView` | `lb_manager.view_snattranslation` |
| `LBVIPHistoricalListView` | `lb_manager.view_lbviphistorical` |
| `SSLCertListView` | `lb_manager.view_sslcert` |
| `SSLProfileListView` | `lb_manager.view_clientsslprofile` |
| `HealthF5ListView` | `lb_manager.view_healthcheckf5` |
| `HealthDHCPListView` | `lb_manager.view_healthcheckdhcp` |
| `HealthDNSListView` | `lb_manager.view_healthcheckdns` |
| `HealthCertificateListView` | `lb_manager.view_healthcheckcertificate` |
| `BitacoraListView` | `lb_manager.view_bitacorahealth` |
| `HealthRuleListView` | `lb_manager.view_healthrule` |
| `LBHardeningListView` | `lb_manager.view_lbhardening` |
| `BitacoraHardeningListView` | `lb_manager.view_bitacorahardening` |

Los endpoints AJAX (`*_data`) usan el mismo permiso `view_*` que su vista correspondiente. Los endpoints de escritura (`servicio_sync`, `servicio_edit`, `bitacora_edit`, `bitacora_bulk_action`, `bitacora_hardening_edit`) usan `change_*`.

---

## 7. DataTables — patrón servidor/cliente

### Server-side (mayoría de listas)

El template inicializa la tabla con `serverSide: true` y apunta al endpoint `data/`:

```javascript
$('#myTable').DataTable({
    serverSide: true,
    processing: true,
    ajax: { url: "{% url 'vip_data' %}", type: 'GET' },
    columns: [
        { data: 'name' },
        { data: 'destination' },
        // ...
    ],
    pageLength: cfg_page_length,   // de SiteSettings
});
```

El endpoint devuelve:
```json
{
  "draw": 1,
  "recordsTotal": 5000,
  "recordsFiltered": 42,
  "data": [{"id": 1, "name": "...", ...}, ...]
}
```

### Client-side (herramientas POST)

Para páginas que renderizan todos los datos en el HTML (como `ip_vip_tls_check`), se usa DataTable sin AJAX:

```javascript
$('#resultsTable').DataTable({
    pageLength: 25,
    order: [[0, 'asc']],
    language: { search: 'Filtrar:' },
});
```

> **Importante:** si hay filas con colspan en tablas client-side, DataTables lanza error de columnas. Siempre usar el número exacto de `<td>` aunque el contenido sea `-`.

---

## 8. Cadena SSL (VIP → Perfil → Certificado)

La cadena completa se resuelve así:

```
VIP.profiles (JSON)
    └── filter context == "client-side"   ← OJO: con guión, no "clientside"
        └── profile["name"]
            └── ClientSSLProfile WHERE name = profile["name"]
                                  AND ltm_fqdn = VIP.ltm_fqdn
                └── ClientSSLProfile.certificate_file  ← full_path del cert (/Common/cert-XXXXXX)
                    └── SSLCert WHERE full_path = certificate_file
                                  AND ltm_fqdn = VIP.ltm_fqdn
                        └── SSLCert.expiration_timestamp  (BigInteger, epoch UTC)
                        └── SSLCert.subject               (CN= del certificado)
```

> **Importante:** `ClientSSLProfile.certificate_file` debe almacenar el `full_path`
> del certificado (ej. `/Common/cert-000001`), **no** el nombre corto (`cert-000001`).
> Si no coincide con `SSLCert.full_path`, la cadena no se puede resolver y el
> Dashboard SSL mostrará 0 certificados.

### Vistas que usan esta cadena

| Vista | URL | Filtro aplicado |
|---|---|---|
| `ssl_dashboard` | `/ssl/dashboard/` | Solo certs que llegan a través de un ClientSSLProfile vinculado a una VIP |
| `vip_expired_ssl` | `/ssl/vips-expired/` | VIPs cuyo cert está vencido o vence en ≤30 días; muestra `subject` del cert |

### Ejemplo de consulta SQL equivalente

```sql
SELECT
    v.name         AS vip_name,
    p.name         AS profile_name,
    c.name         AS cert_name,
    c.expiration_date
FROM vips v
JOIN client_ssl_profiles p
    ON p.ltm_fqdn = v.ltm_fqdn
   AND p.name IN (
       SELECT elem->>'name'
       FROM jsonb_array_elements(v.profiles::jsonb) AS elem
       WHERE elem->>'context' = 'client-side'
   )
JOIN ssl_certs c
    ON c.full_path  = p.certificate_file
   AND c.ltm_fqdn  = p.ltm_fqdn
WHERE v.enabled = 'yes';
```

### Helper en `views.py`

```python
def _vip_ssl_cert_counts():
    """Retorna (n_vips_cert_expired, n_vips_cert_soon_to_expire)."""
    today_dt = datetime.now(dt_timezone.utc)
    now_ts   = int(today_dt.timestamp())
    soon_ts  = int((today_dt + timedelta(days=30)).timestamp())
    # ... ver implementación completa en views.py
```

---

## 9. Sistema de ayuda contextual

Cada template puede mostrar un botón flotante `?` con ayuda en lenguaje sencillo.

### Cómo funciona

`base.html` contiene:
1. Un `<div id="pageHelpContent">{% block page_help %}{% endblock %}</div>` oculto.
2. Un `<button id="helpFloatBtn">` oculto por defecto.
3. Un script que, si el div tiene contenido, muestra el botón.
4. Un modal Bootstrap (`#pageHelpModal`) que carga el contenido del div.

### Cómo agregar ayuda a un template

```django
{# Antes de {% block content %} #}
{% block page_help %}
<p class="text-muted small mb-3">
    <i class="fa-solid fa-[icono] text-primary me-1"></i>
    <strong>Nombre de la página</strong> — Qué hace en una oración simple.
</p>
<hr class="my-3">
<p class="fw-semibold mb-2">
    <i class="fa-solid fa-list-check text-primary me-1"></i>¿Cómo usarlo?
</p>
<ol class="small text-muted ps-3">
    <li class="mb-2">Paso uno...</li>
    <li class="mb-2">Paso dos...</li>
</ol>
<div class="alert alert-info py-2 px-3 small mb-0 mt-3">
    <i class="fa-solid fa-lightbulb me-1"></i>
    <strong>Consejo:</strong> texto del tip.
</div>
{% endblock %}

{% block content %}
...
{% endblock %}
```

Si el bloque está vacío (o no se define), el botón `?` no aparece.

---

## 10. Comandos de gestión

```bash
# Poblar datos de prueba (genéricos, varios LTMs)
python manage.py seed_dummy

# Poblar cadena SSL completa (3 LTMs sintéticos, 100 certs, 200 VIPs)
python manage.py seed_chain
python manage.py seed_chain --flush   # borra primero los registros chain-*

# Evaluar reglas de salud y crear alertas automáticas
python manage.py evaluate_health_rules

# Sincronizar VIPs detectados con la tabla servicio
python manage.py sync_vips_to_servicio

# Probar conexión LDAP
python manage.py test_ldap --username juan.perez
```

### Crear un nuevo comando de gestión

```python
# lb_manager/management/commands/mi_comando.py
from django.core.management.base import BaseCommand

class Command(BaseCommand):
    help = 'Descripción del comando'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        self.stdout.write('Ejecutando...')
        # lógica aquí
        self.stdout.write(self.style.SUCCESS('Completado.'))
```

---

## 11. Panel de administración

**Ruta:** `/ns-mgmt/` — solo `is_staff=True`.

### Modelos administrables clave

| Modelo admin | Uso principal |
|---|---|
| `LDAPGroupMap` | Mapear OUs de AD a grupos Django. Controla permisos de toda la app. |
| `GroupProfile` | Inline en Groups — configura `Login Redirect URL` por grupo. |
| `SiteSettings` | Singleton. Controla límites de DataTables, historial, backups, decommission, etc. |
| `LDAPConfig` | Singleton. URI y TLS del servidor LDAP. |
| `HealthRule` | Reglas de alerta automática (campo, operador, umbral, severidad). |
| `LoginAuditLog` | Solo lectura. Registro de todos los intentos de login. |
| `CSVTableUploadConfig` | Registrar tablas elegibles para CSV. Step 1 del flujo de importación. `unique_fields` es opcional: si se deja vacío cada fila del CSV se inserta directamente (sin verificar duplicados); si se indica, se usa `update_or_create`. |
| `CSVImportConfig` | Jobs programados de importación. Type = FK a CSVTableUploadConfig activo. Incluye schedule cron, file path y column mappings inline con selector dinámico. |

### `SiteSettings` — campos importantes

| Campo | Default | Descripción |
|---|---|---|
| `axes_failure_limit` | 5 | Intentos fallidos antes de bloqueo |
| `axes_cooldown_minutes` | 15 | Minutos de bloqueo |
| `datatable_max_rows` | 5000 | Máximo de filas en respuestas JSON |
| `datatable_default_page_length` | 25 | Filas por página en DataTables |
| `decommission_lookback_months` | 3 | Meses sin tráfico para marcar VIP dormido |
| `dashboard_history_days` | 7 | Días de historia en dashboard |
| `backup_path` | `/backups` | Directorio de archivos `.dump` |
| `backup_pg_dump_path` | `` | Ruta a `pg_dump` si no está en PATH |
| `backup_retention_days` | 30 | Días de retención de backups |
| `backup_schedule` | `0 2 * * *` | Cron del backup automático nocturno |

---

## 12. Configuración de entorno

**Archivo:** `network_services/settings.py`

```python
# Base de datos
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ['DB_NAME'],
        ...
    }
}

# LDAP
AUTHENTICATION_BACKENDS = ['lb_manager.ldap_backend.LDAPTemplateBackend', ...]

# Post-login
LOGIN_REDIRECT_URL = '/'          # Para staff/superuser (overrideado por GroupAwareLoginView)
LOGIN_URL          = '/login/'

# Timezone
TIME_ZONE = 'America/Mexico_City'
USE_TZ    = True
```

---

## 13. Recetas — cómo agregar cosas nuevas

### A. Agregar una nueva página de lista con DataTable

**1. Modelo** (`models.py`):
```python
class MiRecurso(models.Model):
    nombre = models.CharField(max_length=200)
    ltm_fqdn = models.CharField(max_length=200)

    class Meta:
        db_table = 'mi_recurso'
```

**2. Migración:**
```bash
python manage.py makemigrations lb_manager --name add_mi_recurso
python manage.py migrate
```

**3. Vista HTML + endpoint JSON** (`views.py`):
```python
class MiRecursoListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = MiRecurso
    template_name = 'lb_manager/mi_recurso_list.html'
    permission_required = 'lb_manager.view_mirecurso'

    def get_queryset(self):
        return MiRecurso.objects.none()


@login_required
@permission_required('lb_manager.view_mirecurso', raise_exception=True)
def mi_recurso_data(request):
    qs = MiRecurso.objects.values('id', 'nombre', 'ltm_fqdn')
    search = request.GET.get('search[value]', '')
    if search:
        qs = qs.filter(nombre__icontains=search)
    start  = int(request.GET.get('start', 0))
    length = int(request.GET.get('length', 25))
    total  = qs.count()
    return JsonResponse({
        'draw': int(request.GET.get('draw', 1)),
        'recordsTotal': total, 'recordsFiltered': total,
        'data': list(qs[start:start + length]),
    })
```

**4. URL** (`urls.py`):
```python
path('mi-recurso/', views.MiRecursoListView.as_view(), name='mi_recurso_list'),
path('mi-recurso/data/', views.mi_recurso_data, name='mi_recurso_data'),
```

**5. Template** (`templates/lb_manager/mi_recurso_list.html`):
```django
{% extends 'base.html' %}

{% block page_help %}
<p class="text-muted small mb-3">Descripción simple para el usuario.</p>
{% endblock %}

{% block content %}
<div class="page-header">
    <h1 class="page-title"><i class="fa-solid fa-box text-primary me-2"></i>Mi Recurso</h1>
</div>
<div class="card card-modern">
    <div class="card-body p-0">
        <table id="miRecursoTable" class="table table-hover mb-0">
            <thead><tr><th>Nombre</th><th>LTM</th></tr></thead>
        </table>
    </div>
</div>
{% endblock %}

{% block extra_js %}
<script>
$('#miRecursoTable').DataTable({
    serverSide: true, processing: true,
    ajax: { url: "{% url 'mi_recurso_data' %}", type: 'GET' },
    columns: [{ data: 'nombre' }, { data: 'ltm_fqdn' }],
});
</script>
{% endblock %}
```

**6. Admin** (`admin.py`):
```python
@admin.register(MiRecurso)
class MiRecursoAdmin(admin.ModelAdmin):
    list_display = ('id', 'nombre', 'ltm_fqdn')
    search_fields = ('nombre', 'ltm_fqdn')
```

**7. Sidebar** (`templates/base.html`) — buscar la sección correspondiente y agregar:
```django
{% if perms.lb_manager.view_mirecurso %}
<li class="nav-item">
    <a class="nav-link {% if request.resolver_match.url_name == 'mi_recurso_list' %}active{% endif %}"
       href="{% url 'mi_recurso_list' %}">
        <i class="fa-solid fa-box me-2"></i>Mi Recurso
    </a>
</li>
{% endif %}
```

---

### B. Agregar una stat-card al dashboard

En `views.py` → función `dashboard`, agregar al `context`:
```python
context['mi_contador'] = MiRecurso.objects.filter(activo=True).count()
```

En `templates/dashboard.html`, agregar la tarjeta en el row correspondiente:
```django
<div class="col-md-3">
    <div class="stat-card stat-card-primary">  {# primary=azul, warning=amarillo, success=verde #}
        <div class="stat-card-icon"><i class="fa-solid fa-box"></i></div>
        <div class="stat-card-value">{{ mi_contador }}</div>
        <div class="stat-card-label">Mi Recurso</div>
    </div>
</div>
```

Clases disponibles: `stat-card-primary` (azul), `stat-card-success` (verde), `stat-card-warning` (amarillo), `stat-card-info` (cyan).

---

### C. Agregar un redirect post-login a un grupo

1. Ir a `/ns-mgmt/auth/group/` → seleccionar el grupo.
2. En la sección **Profile**, escribir la URL en **Login Redirect URL** (ej. `/ssl/certs/`).
3. Guardar. Sin tocar código.

---

### D. Agregar un nuevo grupo LDAP

1. Ir a `/ns-mgmt/` → **Groups** → crear el grupo y asignarle permisos.
2. Ir a **LDAP Group Mappings** → agregar una fila:
   - `container_dn`: OU completo en AD (ej. `cn=soporte,dc=corp,dc=local`)
   - `dn_template`: plantilla de DN (ej. `cn=%(user)s,cn=soporte,dc=corp,dc=local`)
   - `django_group`: el grupo recién creado
   - `order`: número de prioridad (menor = primero)
3. Sin tocar código ni reiniciar el servidor.

---

### E. Agregar una nueva regla de alerta automática

1. Ir a `/ns-mgmt/` → **Health Rules** → agregar:
   - `field_name`: nombre del campo en `HealthCheckF5` (ej. `cpu_usage`)
   - `operator`: `>`, `<`, `==`, `contains`
   - `threshold`: valor umbral (ej. `90`)
   - `severity`: LOW / MEDIUM / HIGH
   - `message`: texto de la alerta
2. Ejecutar `python manage.py evaluate_health_rules` (o configurarlo como cron).

---

### F. Agregar ayuda contextual a un template existente

Insertar antes de `{% block content %}`:
```django
{% block page_help %}
<p class="text-muted small mb-3">
    <i class="fa-solid fa-[icono] text-primary me-1"></i>
    <strong>Nombre visible</strong> — qué hace esta página.
</p>
<hr class="my-3">
<p class="fw-semibold mb-2">¿Cómo usarlo?</p>
<ol class="small text-muted ps-3">
    <li class="mb-2">Paso 1...</li>
</ol>
{% endblock %}
```

Si el bloque queda vacío o no se define, el botón `?` no aparece.

---

## 14. Seguridad y calidad de código

### SAST — Reglas aplicadas

| Riesgo | Mitigación activa |
|---|---|
| SQL injection | Queries con `%s` parametrizados; `sort_col` validado con whitelist `_INV_SORT_COLS`; `LIMIT/OFFSET` parametrizados |
| XSS | Templates Django escapan por defecto; sin uso de `\| safe` en variables de usuario |
| CSRF | `{% csrf_token %}` en todos los formularios; `@csrf_protect` en endpoints AJAX mutables |
| Path traversal | Rutas de archivo construidas con `Path` y verificadas dentro del directorio base |
| Secretos | Passwords, tokens y API keys en `settings.py` + variables de entorno; sin hardcode en código fuente |
| Permisos | `LoginRequiredMiddleware` global (Django 5.1+) + `@permission_required` por vista. Únicas excepciones: `/login/`, `/logout/`, `/health/` marcadas con `@login_not_required` |

### CSP — Reglas de estilo

- Sin bloques `<style>` inline en templates.
- Sin atributos `style="..."` fijos en HTML — todo en `static/css/custom.css`.
- Los 5 `style="..."` restantes están dentro de funciones JS con ancho dinámico (`${w || 180}px`) y no pueden ser reemplazados por clases estáticas.

### Deuda técnica conocida — Inline scripts

47 templates tienen bloques `<script>` inline. 6 de ellos inyectan variables de Django (`{{ csrf_token }}`, `{{ request.user.pk }}`), lo que requiere el patrón data-attributes para migrarse a archivos estáticos. Impacto: CSP `script-src 'self'` sin `'unsafe-inline'` no puede aplicarse hasta resolver esto.

**Patrón recomendado para migración futura:**
```html
<!-- En el template: exponer vars Django como data attrs -->
<div id="pageConfig"
     data-csrf="{{ csrf_token }}"
     data-user-id="{{ request.user.pk }}">
</div>
```
```javascript
// En static/js/my_view.js
const cfg = document.getElementById('pageConfig').dataset;
const csrf = cfg.csrf;
```

### Calidad Python

- Convertidores de tipo en `csv_importers.py` tienen anotaciones y docstrings.
- `_fmt()` en `infrastructure.py` y `_orphan_reason()` usan list comprehensions en lugar de `append` loops.
- Sin uso de `eval()`, `exec()`, `pickle`, ni `yaml.load` sin `SafeLoader`.

---

## Rendimiento y configuración de producción

### Conexiones persistentes a PostgreSQL (`CONN_MAX_AGE`)

`settings.py` define `CONN_MAX_AGE=60` (configurable via `.env` con `DB_CONN_MAX_AGE`).
Cada worker Gunicorn mantiene la conexión TCP abierta hasta 60 s en lugar de abrir y cerrar
en cada request. Usar `DB_CONN_MAX_AGE=0` si se usa PgBouncer en modo *transaction*.

### Caché compartido entre workers (`DatabaseCache`)

Backend: `django.core.cache.backends.db.DatabaseCache`, tabla `django_cache` en PostgreSQL.

Objetos cacheados:

| Clave | TTL | Contenido |
|---|---|---|
| `site_settings` | 300 s | Instancia de `SiteSettings` |
| `vip_ssl_cert_counts` | 900 s | Tupla `(expired, soon)` de VIPs con SSL próximo a vencer |

Para invalidar manualmente desde el shell de Django:
```python
from django.core.cache import cache
cache.delete('site_settings')        # fuerza recarga de SiteSettings
cache.delete('vip_ssl_cert_counts')  # fuerza recálculo de SSL dashboard
```

**Nota:** Al guardar cambios en `SiteSettings` desde el admin, la nueva configuración se
reflejará en un máximo de 5 minutos sin intervención. Si se necesita efecto inmediato,
ejecutar el comando anterior desde Django shell o agregar una señal `post_save`.

### Helper `get_site_settings()`

`lb_manager/views/utils.py` expone `get_site_settings()` que sustituye a todas las llamadas
directas a `SiteSettings.objects.first()`. Usar siempre este helper en vistas nuevas.

### Optimizaciones de queries en el dashboard

- **20 COUNTs individuales → 4 `aggregate()`**: el dashboard agrupa conteos de VIP, Node,
  SSLCert y Bitácora en una sola query por modelo con `Count(..., filter=Q(...))`.
- **N+1 eliminado en `wiki()`**: el mapa de failover se construye con un `Subquery` correlacionado
  en lugar de 1 query por dispositivo.
- **Alertas del dashboard**: 3 filtros de `HealthCheckF5` de hoy se resuelven en 1 `aggregate()`.

### Índices de rendimiento (migración `0012_add_performance_indexes`)

Campos indexados:

| Modelo | Campo |
|---|---|
| `LTMNode` | `ltm_fqdn` |
| `SSLCert` | `ltm_fqdn`, `full_path`, `expiration_timestamp` |
| `ClientSSLProfile` | `ltm_fqdn`, `certificate_file`, `name` |
| `HealthCheckF5` | `fecha`, `company`, `failover`, `sync`, `cpu_usage`, `cpu_plane_use`, `cpu_analysis_use`, `backup_path` |

### Gunicorn

Archivo de configuración: `gunicorn.conf.py` en la raíz del proyecto.

```bash
# Iniciar con configuración optimizada
gunicorn network_services.wsgi:application --config gunicorn.conf.py
```

Parámetros clave:
- `workers = cpu_count * 2 + 1` (2 vCPU → 5 workers; 4 vCPU → 9 workers)
- `preload_app = True` (carga la app una vez, workers hacen fork)
- `max_requests = 1000` (recicla workers para evitar memory leaks)
- `timeout = 120 s`

### Archivos estáticos (WhiteNoise)

WhiteNoise sirve los estáticos directamente desde Gunicorn con:
- Compresión gzip automática
- `Cache-Control: max-age=31536000` para assets con hash de contenido
- `STORAGES['staticfiles'] = 'whitenoise.storage.CompressedManifestStaticFilesStorage'`

Después de cambios en estáticos:
```bash
python manage.py collectstatic --noinput
```

### Requerimientos de hardware para 10 usuarios simultáneos

| Componente | Mínimo | Recomendado |
|---|---|---|
| Django + Gunicorn (3-5 workers) | 450 MB RAM | 750 MB RAM |
| PostgreSQL | 512 MB RAM | 1 GB RAM |
| OS + Docker overhead | 512 MB RAM | 512 MB RAM |
| **Total RAM** | **2 GB** | **4 GB** |
| **CPU** | **2 vCores** | **4 vCores** |

PostgreSQL recomendado: `max_connections=50`, `shared_buffers=512MB`, `work_mem=4MB`.

---

**Nota producción — DB user:** El `DB_USER` en `.env` no debe ser `postgres` (superuser). Crear un rol PostgreSQL con solo `SELECT/INSERT/UPDATE/DELETE` sobre las tablas de la app. Ejemplo: `CREATE ROLE app_user LOGIN PASSWORD '...'; GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO app_user;`

---

## DDIDevice — campo `tipo`

**Migración:** `ddi_manager/migrations/0003_ddidevice_tipo.py`

El modelo `DDIDevice` tiene un campo `tipo` con las opciones:

| Valor | Descripción |
|---|---|
| `Infoblox` | Dispositivos Infoblox Grid |
| `Other DNS` | Otros servidores DNS |
| `NTP` | Servidores NTP |

### Lógica de visibilidad en la Wiki

La wiki (`/wiki/`) aplica el siguiente filtro para la sección DDI:

```python
Q(tipo='Infoblox', role__iexact='GRID MASTER') |
Q(tipo='Other DNS') |
Q(tipo='NTP')
```

- `tipo = Infoblox` → solo aparecen dispositivos con `role = GRID MASTER`
- `tipo = Other DNS` → aparecen todos
- `tipo = NTP` → aparecen todos
- Dispositivos sin `tipo` asignado → no aparecen en la wiki

La tabla DDI en la wiki muestra columnas: **Device · Tipo · Platform · Role**

---

## django-jazzmin — Admin UI

**Versión:** 3.0.x · **Paquete:** `django-jazzmin>=3.0,<4.0`

Reemplaza la interfaz default de Django admin con un tema moderno basado en AdminLTE + Bootstrap.

**Configuración en `settings.py`:**
- `'jazzmin'` debe estar en `INSTALLED_APPS` **antes** de `'django.contrib.admin'`
- `JAZZMIN_SETTINGS` — branding, top menu links, íconos por modelo, búsqueda
- `JAZZMIN_UI_TWEAKS` — tema, colores de navbar y sidebar

**Top menu links configurados:** Dashboard `/`, Wiki `/wiki/`, DDI Devices `/ddi/devices/`, Admin Guide `/ns-mgmt/guide/`

**Íconos:** Configurados para todos los modelos de `lb_manager`, `ddi_manager` y `auth` usando FontAwesome 6 Solid (ya presente en el proyecto).

**Nota:** La agrupación personalizada del sidebar (secciones Automatización, Configuración) sigue siendo controlada por `CustomAdminSite.get_app_list()` en `network_services/admin_site.py`. Jazzmin solo sobreescribe los templates, no la lógica de agrupación.

*Última actualización: 2026-04-04 (Nuevos modelos DocEntry y DirectoryEntry; páginas CRUD /docs/ y /directorio/ con sección "Recursos" en el sidebar)*
