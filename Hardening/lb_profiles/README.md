# lb_profiles

Cargador de perfiles de checks de hardening para dispositivos **F5 BIG-IP**.

Carga el catálogo de checks definido en el perfil seleccionado y delega la ejecución al rol `lb_engine_core`.

## Requisitos

- Ansible 2.10+
- Variable `provider` con `user` y `password` definida (ver `inventory/group_vars/f5_devices.yml`)

## Variables

| Variable | Default | Descripción |
|----------|---------|-------------|
| `profile_name` | `hardening_v_1_5` | Nombre del archivo de vars a cargar desde `vars/` |
| `lb_user` | `{{ provider.user }}` | Usuario admin del F5 |
| `lb_pass` | `{{ provider.password }}` | Password del F5 |

## Perfiles disponibles

| Archivo | Descripción |
|---------|-------------|
| `vars/hardening_v_1_5.yml` | CIS Benchmark F5 BIG-IP — categorías 2.1 a 2.6 |

## Agregar un nuevo perfil

1. Crear `vars/nombre_perfil.yml` con la lista `checks`
2. Ejecutar el playbook con `-e profile_name=nombre_perfil`

## Schema del catálogo de checks

```yaml
checks:
  - categoria: "2.1"            # Agrupación de checks
    code: "2.1.1"               # Identificador único
    descripcion: "..."          # Descripción legible
    cmd: "list auth ..."        # Comando tmsh (referencia para validación manual)
    api_path: "/mgmt/tm/..."    # Endpoint iControlREST
    campo: "fieldName"          # Campo a extraer del JSON de respuesta
    valor_recomendado: "..."    # Valor esperado / comando de remediación
    policy:                     # Reglas de evaluación
      - type: allow_any
        values: ["enabled"]
```

## Tipos de reglas soportadas

```yaml
# Alguno de los valores debe estar presente en el output
- type: allow_any
  values: ["valor1", "valor2"]

# Ninguno de los valores debe estar presente (match exacto de token)
- type: deny
  values: ["0.0.0.0/0", "none"]

# Ningún token del output debe coincidir con el patrón regex
- type: deny_contains
  pattern: "sha1|md5|group1"

# El output no debe estar vacío
- type: not_empty

# El output debe estar vacío
- type: must_be_empty

# Todos los tokens del output deben estar en la lista de valores permitidos
- type: allow_only
  values: ["tcp:1028", "tcp:4353", "udp:1026", "none"]

# El valor numérico debe ser >= al umbral
- type: numeric_gte
  value: 15

# El valor numérico debe ser <= al umbral
- type: numeric_lte
  value: 600

# El valor numérico debe ser exactamente igual al umbral
- type: numeric_eq
  value: 15

# Debe haber al menos N entradas NTP
- type: min_entry_count
  value: 2

# valor_lista debe tener al menos N elementos
- type: min_list_count
  value: 2

# El valor_obtenido debe contener el inventory_hostname (para validar CN/SAN de certificados)
- type: must_contain_hostname

# El valor_obtenido (Unix timestamp de expiración) no debe superar N dias desde hoy
- type: cert_max_days_remaining
  value: 360
```

## Ejemplo de ejecución

```bash
# Perfil por defecto
ansible-playbook hardening.yml --ask-vault-pass

# Perfil alternativo
ansible-playbook hardening.yml -e profile_name=hardening_v_2_0 --ask-vault-pass

# Directorio de salida personalizado
ansible-playbook hardening.yml -e hardening_output_dir=/tmp/reportes --ask-vault-pass

# Con validación TLS (producción)
ansible-playbook hardening.yml -e f5_validate_certs=true --ask-vault-pass
```
