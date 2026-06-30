# TaskLBCommons

Playbooks Ansible para tareas comunes en dispositivos F5 BIG-IP LTM.
Solo se aplican a equipos en estado **Failover Active**.

## Convención: módulos vs API REST

**Regla:** usar siempre módulos nativos de `f5networks.f5_modules` cuando existan.
Recurrir a `ansible.builtin.uri` (iControlREST) únicamente si no hay módulo nativo para el endpoint.

**Razón:** los módulos manejan idempotencia, validación de parámetros y errores de forma más robusta que llamadas REST directas.

## Patrón de playbook

Todos los playbooks siguen este flujo obligatorio:

```
vars_files:
  - vars/f5_common.yml      ← f5_provider (si usa módulos f5networks)
  - vars/<nombre>.yml       ← vars específicas del playbook
    ↓
f5_init_active.yml          ← token + failover + meta:end_host si standby
    ↓
GET antes → debug
    ↓
módulo f5networks (o uri si no hay módulo nativo)
    ↓
GET después → debug
    ↓
always: f5_revoke_token.yml
```

## Reglas de implementación

- `f5_provider` se define **inline** en cada playbook (referencia vars del inventario)
- Credenciales siempre en **vault**, nunca en texto plano
- `no_log: true` en cualquier tarea que use passwords o tokens
- El failover se evalúa con `failover | lower is match('active')` — el valor real incluye tiempo de uptime
- Los archivos de variables van en `vars/<playbook>.yml`
- Las tareas compartidas están en `tasks/` y no deben modificarse por playbook

## Estructura

```
TaskLBCommons/
├── ansible.cfg
├── requirements.yml              # f5networks.f5_modules >= 1.20.0
├── tasks/
│   ├── f5_init_active.yml        ← COMPARTIDO: token + failover + skip standby
│   ├── f5_get_token.yml
│   ├── f5_revoke_token.yml
│   └── f5_get_failover_status.yml
├── vars/
│   ├── f5_common.yml             ← COMPARTIDO: f5_provider dict
│   └── <tarea>.yml               # vars específicas por playbook
└── <tarea>.yml                   # un playbook por tarea
```

## Playbooks disponibles

| Playbook | Descripción |
|---|---|
| `sshd_ciphers.yml` | Actualiza algoritmos criptográficos del SSHD (KB K49586523) |
| `snmp_v3_user.yml` | Crea o modifica usuario SNMPv3 |
| `auth_fallback.yml` | Habilita/deshabilita fallback a auth local si AD no responde |
| `auth_source.yml` | Configura la fuente de autenticación (AD o LDAP) |
| `auth_servers.yml` | Modifica la lista de servidores AD/LDAP |
| `auth_remote_roles.yml` | Configura Remote Role Groups (grupo AD/LDAP → rol F5) |
| `snmp_v1v2c.yml` | Deshabilita SNMPv1 y SNMPv2c |
| `ntp_servers.yml` | Configura servidores NTP y timezone |
| `ha_sync.yml` | Fuerza sync de configuración del Active al device group HA |
| `ha_setup.yml` | Configura ConfigSync IP, Failover unicast y MAC masquerade del par HA |
