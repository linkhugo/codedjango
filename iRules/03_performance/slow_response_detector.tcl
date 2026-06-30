# =============================================================================
# slow_response_detector.tcl
#
# PURPOSE : Detecta respuestas lentas y stalls usando tres puntos de tiempo:
#             T1 = HTTP_REQUEST          (request recibido del cliente)
#             T2 = HTTP_RESPONSE         (primer byte recibido del servidor)
#             T3 = HTTP_RESPONSE_RELEASE (ultimo byte entregado al cliente)
#
#           Metricas calculadas:
#             TTFB = T2 - T1  (tiempo de procesamiento en el servidor)
#             XFER = T3 - T2  (tiempo de transferencia/entrega al cliente)
#             TTLB = T3 - T1  (tiempo total end-to-end)
#
# CASOS DE USO:
#   - Distinguir lentitud del servidor (TTFB alto) vs red/cliente (XFER alto)
#   - Detectar stalls en responses chunked/streaming (XFER >> TTFB)
#   - Detectar hangs de aplicacion (TTFB >> threshold)
#
# LOG TAG : [resp_timing] / [slow_ttfb] / [slow_ttlb]
# GREP    : grep "\[slow_ttfb\]" /var/log/ltm
#
# EVENTS  : HTTP_REQUEST, HTTP_RESPONSE, HTTP_RESPONSE_RELEASE
# =============================================================================

when HTTP_REQUEST {
    set t1_request [clock clicks -milliseconds]
    set req_method [HTTP::method]
    set req_uri    [HTTP::uri]
    set req_src    [IP::client_addr]

    set TTFB_WARN_MS  2000
    set TTLB_WARN_MS  10000
}

when HTTP_RESPONSE {
    set t2_response [clock clicks -milliseconds]
    set ttfb        [expr { $t2_response - $t1_request }]
    set resp_status [HTTP::status]
    set resp_member "[LB::server addr]:[LB::server port]"

    if { $ttfb > $TTFB_WARN_MS } {
        set alert "\[slow_ttfb\] ACTOR=SERVIDOR ACCION=TTFB_LENTO_DETECTADO"
        set alert "${alert} VS=[virtual name] CLIENTE_IP=${req_src} URI=${req_uri}"
        set alert "${alert} SERVIDOR=${resp_member} CODIGO_HTTP=${resp_status}"
        set alert "${alert} TTFB_MS=${ttfb} UMBRAL_MS=${TTFB_WARN_MS}"
        set alert "${alert} DETALLE=El servidor tardo ${ttfb}ms en enviar el primer byte de respuesta."
        set alert "${alert} El umbral es ${TTFB_WARN_MS}ms. Indica lentitud en el backend o la aplicacion."
        log local0.warning $alert
    }
}

when HTTP_RESPONSE_RELEASE {
    set t3_release [clock clicks -milliseconds]
    set ttlb       [expr { $t3_release - $t1_request }]
    set xfer_time  [expr { $t3_release - $t2_response }]

    set msg "\[resp_timing\] ACTOR=SERVIDOR ACCION=TIEMPOS_COMPLETOS_REGISTRADOS"
    set msg "${msg} VS=[virtual name] CLIENTE_IP=${req_src} URI=${req_uri}"
    set msg "${msg} SERVIDOR=${resp_member} TTFB_MS=${ttfb}"
    set msg "${msg} XFER_MS=${xfer_time} TTLB_MS=${ttlb}"
    log local0.info $msg

    if { $ttlb > $TTLB_WARN_MS } {
        set alert "\[slow_ttlb\] ACTOR=SERVIDOR ACCION=TIEMPO_TOTAL_EXCESIVO"
        set alert "${alert} VS=[virtual name] CLIENTE_IP=${req_src} SERVIDOR=${resp_member}"
        set alert "${alert} TTLB_MS=${ttlb} XFER_MS=${xfer_time} UMBRAL_MS=${TTLB_WARN_MS}"
        set alert "${alert} DETALLE=El tiempo total de entrega al cliente fue ${ttlb}ms."
        set alert "${alert} El umbral es ${TTLB_WARN_MS}ms. Posible lentitud de red o stall en la transferencia."
        log local0.warning $alert
    }
}
