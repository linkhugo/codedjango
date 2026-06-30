# iRules Project — F5 BIG-IP LTM

## Plataforma

| Campo              | Valor                              |
|--------------------|------------------------------------|
| Producto           | F5 BIG-IP LTM                      |
| Versión BIG-IP     | 17.x                               |
| Versión Tcl iRules | **8.4.6** (base para iRules en todas las versiones 12.x – 17.x) |
| Versión Tcl EAV    | 8.5.x (solo para Extended Application Verification monitors, NO para iRules) |

> **Nota importante:** La versión 8.4.6 es el motor base de iRules. F5 extiende esta implementación
> con comandos propios (`HTTP::`, `IP::`, `LB::`, `SSL::`, etc.) que no existen en Tcl estándar.
> `clock clicks` en F5 iRules retorna milisegundos (comportamiento modificado por F5, difiere
> del Tcl estándar donde retorna CPU ticks).

---

## Comandos Tcl DESHABILITADOS en iRules (12.x – 17.x)

Los siguientes comandos estándar de Tcl 8.4 están bloqueados y NO se pueden usar en iRules.
Referencia: K36322151 — F5 Support Article.

```
auto_execok       auto_import       auto_load         auto_mkindex
auto_mkindex_old  auto_qualify      auto_reset        bgerror
cd                eof               exec              exit
fblocked          fconfigure        fcopy             file
fileevent         filename          flush             gets
glob              http              interp            load
memory            namespace         open              package
pid               pkg::create       pkg_mkindex       pwd
rename            seek              socket            source
tcl_findLibrary   tell              time              unknown
update            vwait
```

### Impacto práctico de los comandos deshabilitados

| Comando deshabilitado | Qué NO se puede hacer                                              |
|-----------------------|--------------------------------------------------------------------|
| `exec`                | Ejecutar comandos del sistema operativo / shell                   |
| `file`                | Leer o escribir archivos del filesystem                           |
| `open`                | Abrir file handles o pipes                                        |
| `socket`              | Abrir conexiones TCP/UDP directas desde un iRule                  |
| `namespace`           | Crear namespaces Tcl                                              |
| `package`             | Cargar paquetes Tcl externos (Tcllib, etc.)                       |
| `http`                | Módulo HTTP nativo de Tcl (usar comandos F5 `HTTP::` en su lugar) |
| `interp`              | Crear sub-intérpretes Tcl                                         |
| `source`              | Cargar scripts Tcl externos                                       |
| `load`                | Cargar extensiones binarias (.so / .dll)                          |
| `cd` / `pwd` / `glob` | Operaciones de filesystem                                         |
| `time`                | Benchmark de comandos Tcl (usar `clock clicks -milliseconds`)     |
| `exit`                | Terminar el intérprete                                            |
| `rename`              | Renombrar o eliminar comandos Tcl                                 |
| `update` / `vwait`    | Event loop de Tcl (no aplica en el modelo de eventos de iRules)   |

---

## Convenciones del proyecto

### Estilo de código
- **Sin `\` para continuar líneas** — el editor del BIG-IP GUI puede tener problemas con backslash
  en strings multi-línea. Usar el patrón `set msg / set msg "${msg} ..."` para construir logs.
- **Sin acentos ni caracteres especiales** en el código ejecutable (solo en comentarios con cuidado).
- **Líneas máximo 120 caracteres.**

### Logs
- Cada `log` usa un tag entre corchetes al inicio: `\[nombre_tag\]`
- Permite filtrar en `/var/log/ltm` con: `grep "\[tag\]" /var/log/ltm`
- Severidades usadas: `local0.debug`, `local0.info`, `local0.warning`, `local0.err`

### Timing y rendimiento
- Usar `[clock clicks -milliseconds]` para medir tiempo en ms.
  F5 extiende Tcl 8.4.6 con soporte para `-milliseconds` en su implementación.
- Alternativa compatible estricta con 8.4.6: `[clock clicks]`
  (en F5 iRules retorna ms por defecto, a diferencia del Tcl estándar).

### Rate limiting
- Usar el comando `table` (no `session`) para contadores por IP con TTL.
- Contadores son TMM-local por blade (no se sincronizan en chassis multi-blade).

### Seguridad
- Los iRules de `05_security/` tienen un `ACTION_MODE` configurable.
  Siempre iniciar en `"log"` antes de cambiar a `"block"` en producción.
- Los iRules que inyectan headers de debug (`X-BIG-IP-Member`, `X-BIG-IP-Pool`)
  deben removerse antes de pasar a producción.

---

## Estructura del proyecto

```
iRules/
├── 01_http/           HTTP troubleshooting (request, response, headers)
├── 02_connection/     TCP lifecycle y pool member selection
├── 03_performance/    TTFB, TTLB, slow response detection
├── 04_ssl/            TLS handshake, cipher audit
├── 05_security/       Rate limiting, detección de patrones maliciosos
└── 06_routing/        URI routing debug, persistence troubleshooting
```

## Aplicar un iRule (TMSH)

```bash
tmsh modify ltm virtual <VS_NAME> rules add { <IRULE_NAME> }
```

## Verificar logs en tiempo real

```bash
tail -f /var/log/ltm
grep "\[slow_response\]" /var/log/ltm
grep "\[ssl_deprecated\]" /var/log/ltm
grep "\[rate_block\]" /var/log/ltm
```
