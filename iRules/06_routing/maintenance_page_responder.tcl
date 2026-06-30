# =============================================================================
# maintenance_page_responder.tcl
#
# PURPOSE : Responde con una pagina HTTP de mantenimiento cuando ningun pool
#           member esta disponible (LB_FAILED), en lugar de dejar que el cliente
#           reciba un error TCP de conexion rechazada.
#
#           Sin este iRule: cliente ve "ERR_CONNECTION_REFUSED" o similar.
#           Con este iRule: cliente recibe HTTP 503 con pagina personalizable.
#
#           Tambien maneja el caso donde se quiere poner el VS en mantenimiento
#           manual activando la variable MAINTENANCE_MODE al inicio del iRule.
#
#           COMPORTAMIENTO:
#           - LB_FAILED (todos los members DOWN): responde 503 automaticamente
#           - MAINTENANCE_MODE = 1: responde 503 a TODOS los requests (override)
#           - BYPASS_NETWORKS: lista de IPs/CIDRs que pueden pasar aunque el
#             modo mantenimiento este activo (para que el equipo de ops valide)
#
# CASOS DE USO:
#   - Todos los backends caen en produccion: cliente ve pagina amigable
#   - Despliegue planificado: activar MAINTENANCE_MODE antes del deploy
#   - Validar el nuevo backend desde IP de ops antes de abrir al publico
#
# CONFIGURACION:
#   MAINTENANCE_MODE  - 0 = normal; 1 = mantenimiento forzado para todos
#   BYPASS_NETWORKS   - Lista de CIDRs que bypasean el modo mantenimiento
#   PAGE_TITLE        - Titulo de la pagina de mantenimiento
#   RETRY_AFTER_SECS  - Segundos que el cliente debe esperar antes de reintentar
#                       (header Retry-After en la respuesta 503)
#
# LOG TAG : [maint_503] / [maint_bypass] / [maint_lb_fail]
# GREP    : grep "\[maint_503\]" /var/log/ltm
#
# EVENTS  : HTTP_REQUEST, LB_FAILED
# =============================================================================

when HTTP_REQUEST {

    set MAINTENANCE_MODE  0
    set BYPASS_NETWORKS   { "10.0.0.0/8" "192.168.0.0/16" }
    set PAGE_TITLE        "Servicio en Mantenimiento"
    set RETRY_AFTER_SECS  120

    set client_ip [IP::client_addr]
    set req_uri   [HTTP::uri]
    set vs_name   [virtual name]

    if { $MAINTENANCE_MODE } {

        set is_bypass 0
        foreach net $BYPASS_NETWORKS {
            if { [IP::addr $client_ip mask $net] } {
                set is_bypass 1
                break
            }
        }

        if { $is_bypass } {
            set msg "\[maint_bypass\] ACTOR=BIGIP ACCION=MANTENIMIENTO_BYPASS_PERMITIDO"
            set msg "${msg} VS=${vs_name} CLIENTE_IP=${client_ip} URI=${req_uri}"
            set msg "${msg} MODO_MANTENIMIENTO=ACTIVO"
            set msg "${msg} DETALLE=La IP del cliente pertenece a una red de bypass permitida."
            set msg "${msg} Se permite el acceso durante el mantenimiento."
            log local0.info $msg
            return
        }

        set body "<html><head><title>${PAGE_TITLE}</title>"
        set body "${body}<style>body{font-family:Arial,sans-serif;text-align:center;padding:80px;background:#f5f5f5}"
        set body "${body}h1{color:#333}p{color:#666}code{background:#eee;padding:4px 8px;border-radius:4px}</style></head>"
        set body "${body}<body><h1>${PAGE_TITLE}</h1>"
        set body "${body}<p>Estamos realizando tareas de mantenimiento programado.</p>"
        set body "${body}<p>Por favor, intente nuevamente en <strong>${RETRY_AFTER_SECS} segundos</strong>.</p>"
        set body "${body}<p><code>VS: ${vs_name}</code></p>"
        set body "${body}</body></html>"

        set msg "\[maint_503\] ACTOR=BIGIP ACCION=PAGINA_503_MANTENIMIENTO_MANUAL"
        set msg "${msg} VS=${vs_name} CLIENTE_IP=${client_ip} URI=${req_uri}"
        set msg "${msg} CAUSA=MODO_MANTENIMIENTO_FORZADO"
        set msg "${msg} DETALLE=El administrador activo el modo mantenimiento."
        set msg "${msg} Todos los clientes reciben HTTP 503 hasta que se desactive."
        log local0.warning $msg
        HTTP::respond 503 content $body "Content-Type" "text/html; charset=utf-8" "Retry-After" $RETRY_AFTER_SECS
    }
}

when LB_FAILED {

    set client_ip [IP::client_addr]
    set req_uri   [HTTP::uri]
    set vs_name   [virtual name]

    set alert "\[maint_lb_fail\] ACTOR=BIGIP ACCION=PAGINA_503_SIN_SERVIDORES"
    set alert "${alert} VS=${vs_name} CLIENTE_IP=${client_ip} URI=${req_uri}"
    set alert "${alert} CAUSA=TODOS_LOS_SERVIDORES_CAIDOS"
    set alert "${alert} DETALLE=No hay servidores disponibles en el pool."
    set alert "${alert} BIG-IP responde con HTTP 503 al cliente en lugar de RST."
    log local0.err $alert

    set body "<html><head><title>Servicio No Disponible</title>"
    set body "${body}<style>body{font-family:Arial,sans-serif;text-align:center;padding:80px;background:#f5f5f5}"
    set body "${body}h1{color:#c0392b}p{color:#666}code{background:#eee;padding:4px 8px;border-radius:4px}</style></head>"
    set body "${body}<body><h1>Servicio Temporalmente No Disponible</h1>"
    set body "${body}<p>El servicio no esta disponible en este momento.</p>"
    set body "${body}<p>Nuestro equipo ya fue notificado. Por favor intente nuevamente en unos minutos.</p>"
    set body "${body}<p><code>VS: ${vs_name}</code></p>"
    set body "${body}</body></html>"

    HTTP::respond 503 content $body "Content-Type" "text/html; charset=utf-8" "Retry-After" 60
}
