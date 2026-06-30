# lb_engine_core

Motor de ejecución para auditoría de hardening en dispositivos **F5 BIG-IP** via iControlREST API.

Recibe un catálogo de checks (cargado por `lb_profiles`), obtiene un token de sesión, ejecuta cada check contra la API REST del dispositivo, evalúa las reglas de policy y genera un reporte CSV en el controller.

**Flujo:** Ansible controller → HTTPS → F5 iControlREST API → JSON → policy engine → CSV

No se requiere SSH al dispositivo F5.

## Requisitos

- Ansible 2.10+
- Credenciales de admin F5 (`lb_user` / `lb_pass`)
- Permisos de escritura en `hardening_output_dir` en el Ansible controller

## Variables

| Variable | Default | Descripción |
|----------|---------|-------------|
| `hardening_output_dir` | `/pruebas` | Directorio en el controller donde se escriben los CSV |
| `f5_api_port` | `443` | Puerto HTTPS del iControlREST |
| `f5_validate_certs` | `false` | Validación de cert TLS (`true` en producción) |
| `f5_token_timeout` | `3600` | Duración del token tras extensión (segundos, max 36000) |
| `checks` | (requerido) | Lista de checks cargada por `lb_profiles` |

## Tipos de reglas de policy

| Tipo | Descripción |
|------|-------------|
| `allow_any` | Falla si ningún valor de la lista aparece en el output |
| `deny` | Falla si algún valor de la lista aparece en el output (match exacto de token) |
| `deny_contains` | Falla si algún token del output coincide con el patrón regex |
| `not_empty` | Falla si el output está vacío |
| `must_be_empty` | Falla si el output tiene algún elemento |
| `allow_only` | Falla si algún token del output NO está en la lista de valores permitidos |
| `numeric_gte` | Falla si el valor numérico es menor al umbral |
| `numeric_lte` | Falla si el valor numérico es mayor al umbral |
| `numeric_eq` | Falla si el valor numérico no es exactamente igual al umbral |
| `min_entry_count` | Falla si hay menos entradas NTP que el umbral |
| `min_list_count` | Falla si `valor_lista` tiene menos elementos que el umbral |

## Formato del CSV de salida

```
Device,Code,Descripcion,Valor_Obtenido,Valor_Recomendado,Resultado,Comando_Para_Validar,fecha
```

- `Resultado`: `passed` o `failed`
- `Valor_Obtenido`: valor extraído de la API, o `ERROR` si la llamada falló

## Manejo de errores

Si una llamada a la API falla (dispositivo inaccesible, permiso denegado, endpoint no soportado), el check se registra con `Valor_Obtenido: ERROR` y `Resultado: failed` en lugar de abortar toda la ejecución.

El token iControlREST siempre se revoca al finalizar (bloque `always:`), incluso si la auditoría falla a mitad.
