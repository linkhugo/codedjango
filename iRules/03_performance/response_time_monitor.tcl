# =============================================================================
# response_time_monitor.tcl
#
# PURPOSE : Mide el tiempo de respuesta del servidor (TTFB) por cada request.
#           Tiempo medido desde HTTP_REQUEST hasta HTTP_RESPONSE.
#           Requests que superen SLOW_THRESHOLD_MS se loguean en WARNING.
#
# CASOS DE USO:
#   - Aislar si la lentitud esta en BIG-IP, red, o aplicacion
#   - Identificar URIs lentas: grep + sort por TTFB_MS
#   - Identificar servidores lentos: grep por SERVIDOR
#   - Baselining previo a un cambio de aplicacion
#
# TUNING  : Ajustar SLOW_THRESHOLD_MS al SLA de la aplicacion.
#
# LOG TAG : [resp_time] / [slow_response]
# GREP    : grep "\[slow_response\]" /var/log/ltm
#
# EVENTS  : HTTP_REQUEST, HTTP_RESPONSE
# =============================================================================

when HTTP_REQUEST {
    set req_start_time    [clock clicks -milliseconds]
    set req_method        [HTTP::method]
    set req_uri           [HTTP::uri]
    set req_src           [IP::client_addr]
    set req_host          [HTTP::host]

    set SLOW_THRESHOLD_MS 3000
}

when HTTP_RESPONSE {
    set response_ms [expr { [clock clicks -milliseconds] - $req_start_time }]
    set member_ip   [LB::server addr]
    set member_port [LB::server port]
    set status      [HTTP::status]

    set msg "\[resp_time\] ACTOR=SERVIDOR ACCION=TIEMPO_RESPUESTA_REGISTRADO"
    set msg "${msg} VS=[virtual name] CLIENTE_IP=${req_src} HOST=${req_host}"
    set msg "${msg} METHOD=${req_method} URI=${req_uri}"
    set msg "${msg} POOL=[LB::server pool] SERVIDOR=${member_ip}:${member_port}"
    set msg "${msg} CODIGO_HTTP=${status} TTFB_MS=${response_ms}"
    log local0.info $msg

    if { $response_ms > $SLOW_THRESHOLD_MS } {
        set alert "\[slow_response\] ACTOR=SERVIDOR ACCION=RESPUESTA_LENTA_DETECTADA"
        set alert "${alert} VS=[virtual name] SERVIDOR=${member_ip}:${member_port}"
        set alert "${alert} URI=${req_uri} CLIENTE_IP=${req_src}"
        set alert "${alert} TTFB_MS=${response_ms} UMBRAL_MS=${SLOW_THRESHOLD_MS}"
        set alert "${alert} DETALLE=El servidor tardo ${response_ms}ms en responder."
        set alert "${alert} El limite es ${SLOW_THRESHOLD_MS}ms. Revisar rendimiento del backend."
        log local0.warning $alert
    }
}
