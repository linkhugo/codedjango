# =============================================================================
# http_error_rate_monitor.tcl
#
# PURPOSE : Monitorea la tasa de errores HTTP (4xx y 5xx) por pool member
#           en una ventana deslizante. Alerta cuando la tasa supera el umbral.
#
#           Problema que resuelve:
#           Los health monitors de BIG-IP validan que el backend responde,
#           pero no miden la tasa de errores de la aplicacion. Un member puede
#           estar "UP" para el health monitor y al mismo tiempo devolviendo
#           80% de 500s. Este iRule lo detecta en tiempo real.
#
#           Contadores por member (usando tabla):
#             - Total de requests en la ventana
#             - Total de 5xx en la ventana
#             - Total de 4xx en la ventana
#           Alerta cuando: (5xx en ventana / total en ventana) > ERROR_RATE_PCT
#
# CASOS DE USO:
#   - Member degradado que pasa el health check pero falla en produccion
#   - Detectar inicio de un outage antes de que el monitor lo marque DOWN
#   - Identificar que endpoint especifico genera mas errores
#   - Baseline de tasa de errores para alertas de anomalia
#
# CONFIGURACION:
#   ERROR_WINDOW_SECS - Ventana de tiempo para contar errores (default: 60s)
#   ERROR_RATE_PCT    - Porcentaje de 5xx que dispara alerta (default: 20 = 20%)
#   MIN_REQUESTS      - Minimo de requests en la ventana para calcular tasa
#                       (evita alertas con muestra muy pequena, default: 10)
#
# LOG TAG : [err_rate_5xx] / [err_rate_4xx] / [err_rate_alert]
# GREP    : grep "\[err_rate_alert\]" /var/log/ltm
#
# EVENTS  : HTTP_REQUEST, HTTP_RESPONSE
# =============================================================================

when HTTP_REQUEST {
    set req_src    [IP::client_addr]
    set req_uri    [HTTP::uri]
    set req_method [HTTP::method]
}

when HTTP_RESPONSE {

    set ERROR_WINDOW_SECS 60
    set ERROR_RATE_PCT    20
    set MIN_REQUESTS      10

    set status      [HTTP::status]
    set member_ip   [LB::server addr]
    set member_port [LB::server port]
    set member_key  "${member_ip}:${member_port}"
    set vs_name     [virtual name]
    set status_class [string range $status 0 0]

    set total_key "total_${member_key}"
    set err5_key  "5xx_${member_key}"
    set err4_key  "4xx_${member_key}"

    set total [table incr -subtable "err_rate" $total_key]
    if { $total == 1 } { table timeout -subtable "err_rate" $total_key $ERROR_WINDOW_SECS }

    if { $status_class eq "5" } {
        set err5 [table incr -subtable "err_rate" $err5_key]
        if { $err5 == 1 } { table timeout -subtable "err_rate" $err5_key $ERROR_WINDOW_SECS }

        set msg "\[err_rate_5xx\] ACTOR=SERVIDOR ACCION=ERROR_5XX_REGISTRADO"
        set msg "${msg} VS=${vs_name} SERVIDOR=${member_key}"
        set msg "${msg} CODIGO_HTTP=${status} METHOD=${req_method} URI=${req_uri}"
        set msg "${msg} CLIENTE_IP=${req_src} TOTAL_5XX_EN_VENTANA=${err5}"
        log local0.warning $msg

    } elseif { $status_class eq "4" } {
        set err4 [table incr -subtable "err_rate" $err4_key]
        if { $err4 == 1 } { table timeout -subtable "err_rate" $err4_key $ERROR_WINDOW_SECS }

        set msg "\[err_rate_4xx\] ACTOR=SERVIDOR ACCION=ERROR_4XX_REGISTRADO"
        set msg "${msg} VS=${vs_name} SERVIDOR=${member_key}"
        set msg "${msg} CODIGO_HTTP=${status} URI=${req_uri} TOTAL_4XX_EN_VENTANA=${err4}"
        log local0.info $msg
    }

    set cur_total [table lookup -subtable "err_rate" $total_key]
    set cur_5xx   [table lookup -subtable "err_rate" $err5_key]
    if { $cur_5xx eq "" } { set cur_5xx 0 }

    if { $cur_total >= $MIN_REQUESTS && $cur_5xx > 0 } {
        set error_rate [expr { ($cur_5xx * 100) / $cur_total }]
        if { $error_rate >= $ERROR_RATE_PCT } {
            set alert "\[err_rate_alert\] ACTOR=SERVIDOR ACCION=TASA_ERRORES_CRITICA"
            set alert "${alert} VS=${vs_name} SERVIDOR=${member_key}"
            set alert "${alert} TASA_ERROR=${error_rate}% UMBRAL=${ERROR_RATE_PCT}%"
            set alert "${alert} TOTAL_5XX=${cur_5xx} TOTAL_REQUESTS=${cur_total}"
            set alert "${alert} VENTANA_SEGUNDOS=${ERROR_WINDOW_SECS}"
            set alert "${alert} DETALLE=El servidor esta fallando ${error_rate}% de los requests."
            set alert "${alert} Supera el umbral de ${ERROR_RATE_PCT}%. Verificar estado del backend."
            log local0.err $alert
        }
    }
}
