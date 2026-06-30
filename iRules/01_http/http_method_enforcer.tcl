# =============================================================================
# http_method_enforcer.tcl
#
# PURPOSE : Controla que metodos HTTP pueden pasar al backend:
#           - Lista configurable de metodos permitidos
#           - Bloqueo de metodos peligrosos (TRACE, CONNECT, DEBUG)
#           - Log de distribucion de metodos (contador por tipo)
#           - Alerta cuando se detecta un metodo no estandar
#           - Modo "log" para observacion o "block" para enforcement activo
#
# CASOS DE USO:
#   - APIs que solo deben aceptar GET/POST pero reciben PUT/DELETE
#   - Detectar herramientas de escaneo que usan TRACE/OPTIONS
#   - Compliance (algunos frameworks requieren deshabilitar TRACE)
#   - Baseline de distribucion de metodos antes de un cambio
#
# CONFIGURACION:
#   ALLOWED_METHODS - Lista de metodos permitidos
#   ACTION_MODE     - "log" (observar) o "block" (rechazar con 405)
#
# LOG TAG : [method_allow] / [method_block] / [method_dist]
# GREP    : grep "\[method_block\]" /var/log/ltm
#
# EVENTS  : HTTP_REQUEST
# =============================================================================

when HTTP_REQUEST {

    set ALLOWED_METHODS { "GET" "POST" "HEAD" "OPTIONS" "PUT" "DELETE" "PATCH" }
    set ACTION_MODE     "log"

    set method  [HTTP::method]
    set req_uri [HTTP::uri]
    set req_src [IP::client_addr]
    set vs_name [virtual name]

    if { [lsearch -exact $ALLOWED_METHODS $method] >= 0 } {
        set msg "\[method_allow\] ACTOR=CLIENTE ACCION=METODO_PERMITIDO"
        set msg "${msg} VS=${vs_name} CLIENTE_IP=${req_src} METHOD=${method} URI=${req_uri}"
        log local0.debug $msg
    } else {
        set alert "\[method_block\] ACTOR=CLIENTE ACCION=METODO_NO_PERMITIDO"
        set alert "${alert} VS=${vs_name} CLIENTE_IP=${req_src} METHOD=${method} URI=${req_uri}"
        set alert "${alert} MODO=${ACTION_MODE}"
        set alert "${alert} DETALLE=El cliente uso el metodo HTTP ${method} que no esta en la lista permitida."
        log local0.warning $alert

        if { $ACTION_MODE eq "block" } {
            HTTP::respond 405 content "Method Not Allowed" "Content-Type" "text/plain" "Allow" [join $ALLOWED_METHODS ", "]
            return
        }
    }

    set count_key "method_count_${method}"
    set current [table lookup -subtable "http_methods" $count_key]
    if { $current eq "" } {
        table set -subtable "http_methods" $count_key 1 3600
    } else {
        table incr -subtable "http_methods" $count_key
    }

    set total [table lookup -subtable "http_methods" $count_key]
    if { [expr { $total % 500 }] == 0 } {
        set msg "\[method_dist\] ACTOR=BIGIP ACCION=ESTADISTICA_METODO"
        set msg "${msg} VS=${vs_name} METHOD=${method} TOTAL_ULTIMAS_1H=${total}"
        log local0.info $msg
    }
}
