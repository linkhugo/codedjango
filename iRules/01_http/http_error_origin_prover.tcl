# =============================================================================
# http_error_origin_prover.tcl
#
# PURPOSE : Demuestra con evidencia irrefutable si un error HTTP (como 500)
#           fue generado por el SERVIDOR BACKEND o por el propio BIG-IP.
#
#           COMO FUNCIONA LA DISTINCION TECNICA:
#
#           Si el ERROR LO GENERO EL SERVIDOR:
#             El evento HTTP_RESPONSE dispara con datos reales del backend.
#             LB::server addr devuelve la IP del servidor que respondio.
#             El codigo HTTP viajo desde el servidor hasta BIG-IP y fue
#             reenviado al cliente sin modificacion.
#
#           Si el ERROR LO GENERO BIG-IP:
#             LB_FAILED dispara (no habia servidores disponibles en el pool).
#             O el handshake SSL fallo antes de conectar al backend.
#             En estos casos HTTP_RESPONSE NUNCA dispara con datos del backend.
#
#           TRAZA COMPLETA DE PASOS:
#
#           PASO  ACTOR    ACCION
#           ----  -------  ----------------------------------------
#           1     CLIENTE  Abre conexion TCP al VirtualServer
#           2     CLIENTE  Envia el HTTP Request
#           3a    BIGIP    Selecciona servidor del pool (LB_SELECTED)
#           3b    BIGIP    ERROR: no habia servidores (LB_FAILED)
#           4     BIGIP    Abre conexion TCP al servidor backend
#           5     BIGIP    Reenvio del request al backend
#           6     SERVIDOR Responde con HTTP status (aqui se detecta el 500)
#           7     BIGIP    Entrega la respuesta al cliente
#           FIN   ---      VEREDICTO: quien genero el error y por que
#
# CONFIGURACION:
#   TRACE_MODE  - 1: loguea TODOS los pasos (para investigacion activa)
#                 0: solo loguea errores y el VEREDICTO final (modo silencioso)
#
# LOG TAGS:
#   [origin_paso]      Cada paso del flujo normal (debug)
#   [origin_error]     Cuando se detecta un error (err / warning)
#   [origin_veredicto] Resumen final con QUIEN genero el error
#
# GREP RAPIDO:
#   Ver solo los veredictos de errores:
#     grep "\[origin_veredicto\]" /var/log/ltm | grep -v "RESULTADO=NORMAL"
#
#   Ver evidencia del error de un IP especifico:
#     grep "\[origin_" /var/log/ltm | grep "SRC=10.1.1.5"
#
#   Ver solo casos donde el SERVIDOR genero el error:
#     grep "\[origin_veredicto\]" /var/log/ltm | grep "ORIGEN_DEL_ERROR=SERVIDOR_BACKEND"
#
#   Ver casos donde BIG-IP genero el error (sin backend disponible):
#     grep "\[origin_veredicto\]" /var/log/ltm | grep "ORIGEN_DEL_ERROR=BIGIP"
#
#   Traza completa de una conexion especifica (correlacionar por CONN_ID):
#     grep "CONN=10.1.1.5:54321" /var/log/ltm
#
# APLICAR AL VS:
#   tmsh modify ltm virtual <VS_NAME> rules add { http_error_origin_prover }
#
# EVENTS  : CLIENT_ACCEPTED, CLIENTSSL_CLIENTHELLO, CLIENTSSL_HANDSHAKE,
#           HTTP_REQUEST, LB_SELECTED, LB_FAILED, SERVER_CONNECTED,
#           HTTP_REQUEST_SEND, HTTP_RESPONSE, HTTP_RESPONSE_RELEASE,
#           CLIENT_CLOSED
# =============================================================================

when CLIENT_ACCEPTED {

    set TRACE_MODE 1

    set CONN_ID  "[IP::client_addr]:[TCP::client_port]:[clock clicks]"
    set T_START  [clock clicks -milliseconds]
    set SRC_IP   [IP::client_addr]
    set SRC_PORT [TCP::client_port]
    set VS_NAME  [virtual name]

    set t_req_sent  0
    set t_response  0

    set lb_member   ""
    set lb_pool     ""
    set req_method  ""
    set req_uri     ""
    set req_host    ""
    set resp_status ""

    set state_lb_failed     0
    set state_srv_connected 0
    set state_ssl_hello     0
    set state_ssl_done      0
    set state_http_req      0
    set state_http_resp     0
    set state_http_released 0

    if { $TRACE_MODE } {
        set t_ms [expr { [clock clicks -milliseconds] - $T_START }]
        set msg "\[origin_paso\] CONN=${CONN_ID} PASO=1 ACTOR=CLIENTE"
        set msg "${msg} ACCION=CONEXION_ACEPTADA"
        set msg "${msg} SRC=${SRC_IP}:${SRC_PORT} VS=${VS_NAME} T_MS=${t_ms}"
        log local0.debug $msg
    }
}

when CLIENTSSL_CLIENTHELLO {
    set state_ssl_hello 1

    if { $TRACE_MODE } {
        set t_ms [expr { [clock clicks -milliseconds] - $T_START }]
        log local0.debug "\[origin_paso\] CONN=${CONN_ID} PASO=1b ACTOR=CLIENTE ACCION=TLS_CLIENTHELLO T_MS=${t_ms}"
    }
}

when CLIENTSSL_HANDSHAKE {
    set state_ssl_done 1

    if { $TRACE_MODE } {
        set cipher [SSL::cipher name]
        set t_ms [expr { [clock clicks -milliseconds] - $T_START }]
        set msg "\[origin_paso\] CONN=${CONN_ID} PASO=1c ACTOR=BIGIP"
        set msg "${msg} ACCION=TLS_HANDSHAKE_COMPLETADO CIPHER=${cipher} T_MS=${t_ms}"
        log local0.debug $msg
    }
}

when HTTP_REQUEST {
    set state_http_req 1
    set req_method [HTTP::method]
    set req_uri    [HTTP::uri]
    set req_host   [HTTP::host]

    if { $TRACE_MODE } {
        set t_ms [expr { [clock clicks -milliseconds] - $T_START }]
        set msg "\[origin_paso\] CONN=${CONN_ID} PASO=2 ACTOR=CLIENTE"
        set msg "${msg} ACCION=REQUEST_RECIBIDO METHOD=${req_method}"
        set msg "${msg} HOST=${req_host} URI=${req_uri} T_MS=${t_ms}"
        log local0.debug $msg
    }
}

when LB_SELECTED {
    set lb_member "[LB::server addr]:[LB::server port]"
    set lb_pool   [LB::server pool]

    if { $TRACE_MODE } {
        set t_ms [expr { [clock clicks -milliseconds] - $T_START }]
        set msg "\[origin_paso\] CONN=${CONN_ID} PASO=3 ACTOR=BIGIP"
        set msg "${msg} ACCION=SERVIDOR_SELECCIONADO"
        set msg "${msg} POOL=${lb_pool} SERVIDOR=${lb_member} T_MS=${t_ms}"
        log local0.debug $msg
    }
}

when LB_FAILED {
    set state_lb_failed 1

    set t_ms [expr { [clock clicks -milliseconds] - $T_START }]
    set msg "\[origin_error\] CONN=${CONN_ID} VS=${VS_NAME} SRC=${SRC_IP}"
    set msg "${msg} PASO=3 ACTOR=BIGIP ACCION=ERROR_SIN_SERVIDORES"
    set msg "${msg} POOL=${lb_pool} T_MS=${t_ms}"
    set msg "${msg} DETALLE=BIG-IP no encontro ningun servidor disponible en el pool"
    log local0.err $msg
}

when SERVER_CONNECTED {
    set state_srv_connected 1
    if { $lb_member eq "" } {
        set lb_member "[IP::server_addr]:[TCP::server_port]"
        set lb_pool   [LB::server pool]
    }

    if { $TRACE_MODE } {
        set t_ms [expr { [clock clicks -milliseconds] - $T_START }]
        set msg "\[origin_paso\] CONN=${CONN_ID} PASO=4 ACTOR=BIGIP"
        set msg "${msg} ACCION=CONEXION_TCP_AL_SERVIDOR"
        set msg "${msg} SERVIDOR=${lb_member} POOL=${lb_pool} T_MS=${t_ms}"
        log local0.debug $msg
    }
}

when HTTP_REQUEST_SEND {
    set t_req_sent [clock clicks -milliseconds]

    if { $TRACE_MODE } {
        set t_ms [expr { $t_req_sent - $T_START }]
        set msg "\[origin_paso\] CONN=${CONN_ID} PASO=5 ACTOR=BIGIP"
        set msg "${msg} ACCION=REQUEST_REENVIADO_AL_SERVIDOR"
        set msg "${msg} SERVIDOR=${lb_member} METHOD=${req_method} URI=${req_uri} T_MS=${t_ms}"
        log local0.debug $msg
    }
}

when HTTP_RESPONSE {
    set state_http_resp 1
    set resp_status [HTTP::status]
    set t_response  [clock clicks -milliseconds]

    set t_ms    [expr { $t_response - $T_START }]
    set ttfb_ms [expr { $t_req_sent > 0 ? $t_response - $t_req_sent : -1 }]

    set status_class [string range $resp_status 0 0]

    if { $status_class eq "5" } {
        set msg "\[origin_error\] CONN=${CONN_ID} VS=${VS_NAME} SRC=${SRC_IP}"
        set msg "${msg} PASO=6 ACTOR=SERVIDOR ACCION=SERVIDOR_RESPONDIO_CON_ERROR"
        set msg "${msg} CODIGO_HTTP=${resp_status} ORIGEN_ERROR=SERVIDOR_BACKEND"
        set msg "${msg} SERVIDOR=${lb_member} POOL=${lb_pool}"
        set msg "${msg} TTFB_MS=${ttfb_ms} T_MS=${t_ms}"
        set msg "${msg} EVIDENCIA=HTTP_RESPONSE_disparo_con_IP_del_backend"
        log local0.err $msg

    } elseif { $status_class eq "4" } {
        set msg "\[origin_error\] CONN=${CONN_ID} VS=${VS_NAME} SRC=${SRC_IP}"
        set msg "${msg} PASO=6 ACTOR=SERVIDOR ACCION=SERVIDOR_RESPONDIO_CON_ERROR"
        set msg "${msg} CODIGO_HTTP=${resp_status} ORIGEN_ERROR=SERVIDOR_BACKEND"
        set msg "${msg} SERVIDOR=${lb_member} POOL=${lb_pool}"
        set msg "${msg} TTFB_MS=${ttfb_ms} T_MS=${t_ms}"
        log local0.warning $msg

    } elseif { $TRACE_MODE } {
        set msg "\[origin_paso\] CONN=${CONN_ID} PASO=6 ACTOR=SERVIDOR"
        set msg "${msg} ACCION=SERVIDOR_RESPONDIO STATUS=${resp_status}"
        set msg "${msg} SERVIDOR=${lb_member} TTFB_MS=${ttfb_ms} T_MS=${t_ms}"
        log local0.debug $msg
    }
}

when HTTP_RESPONSE_RELEASE {
    set state_http_released 1

    if { $TRACE_MODE } {
        set t_ms [expr { [clock clicks -milliseconds] - $T_START }]
        set msg "\[origin_paso\] CONN=${CONN_ID} PASO=7 ACTOR=BIGIP"
        set msg "${msg} ACCION=RESPUESTA_ENTREGADA_AL_CLIENTE"
        set msg "${msg} STATUS=${resp_status} T_MS=${t_ms}"
        log local0.debug $msg
    }
}

when CLIENT_CLOSED {

    set t_total_ms [expr { [clock clicks -milliseconds] - $T_START }]
    set ttfb_ms    [expr { $t_req_sent > 0 && $t_response > 0 ? $t_response - $t_req_sent : -1 }]
    set status_class [expr { $resp_status ne "" ? [string range $resp_status 0 0] : "" }]

    # ------------------------------------------------------------------
    # VEREDICTO - determinar quien genero el error
    # ------------------------------------------------------------------

    if { $state_lb_failed } {
        # BIG-IP no pudo conectar al backend - el error ES de BIG-IP
        set msg "\[origin_veredicto\] CONN=${CONN_ID} VS=${VS_NAME} SRC=${SRC_IP}"
        set msg "${msg} RESULTADO=ERROR_BIGIP_SIN_BACKEND ORIGEN_DEL_ERROR=BIGIP"
        set msg "${msg} POOL=${lb_pool} TOTAL_MS=${t_total_ms}"
        set msg "${msg} CONCLUSION=BIG-IP no tenia servidores disponibles."
        set msg "${msg} El servidor backend NO fue contactado y NO genero este error."
        set msg "${msg} ACCION=Verificar estado del pool con: tmsh show ltm pool ${lb_pool}"
        log local0.err $msg

    } elseif { $state_ssl_hello && !$state_ssl_done } {
        # TLS handshake fallo antes de llegar al backend
        set msg "\[origin_veredicto\] CONN=${CONN_ID} VS=${VS_NAME} SRC=${SRC_IP}"
        set msg "${msg} RESULTADO=ERROR_TLS_HANDSHAKE ORIGEN_DEL_ERROR=BIGIP_O_CLIENTE"
        set msg "${msg} TOTAL_MS=${t_total_ms}"
        set msg "${msg} CONCLUSION=El handshake TLS no se completo."
        set msg "${msg} El servidor backend NO fue contactado. No es un error del servidor."
        log local0.err $msg

    } elseif { $state_http_resp && $status_class eq "5" } {
        # El SERVIDOR respondio con 5xx - el servidor es el culpable
        set msg "\[origin_veredicto\] CONN=${CONN_ID} VS=${VS_NAME} SRC=${SRC_IP}"
        set msg "${msg} RESULTADO=ERROR_GENERADO_POR_SERVIDOR ORIGEN_DEL_ERROR=SERVIDOR_BACKEND"
        set msg "${msg} CODIGO_HTTP=${resp_status} SERVIDOR_CULPABLE=${lb_member}"
        set msg "${msg} POOL=${lb_pool} TIEMPO_SERVIDOR_MS=${ttfb_ms} TOTAL_MS=${t_total_ms}"
        set msg "${msg} CONCLUSION=BIG-IP recibio HTTP ${resp_status} directamente del servidor."
        set msg "${msg} BIG-IP solo lo reenvio. BIG-IP NO genero este error."
        log local0.err $msg

    } elseif { $state_http_resp && $status_class eq "4" } {
        # El SERVIDOR respondio con 4xx
        set msg "\[origin_veredicto\] CONN=${CONN_ID} VS=${VS_NAME} SRC=${SRC_IP}"
        set msg "${msg} RESULTADO=ERROR_4XX_SERVIDOR ORIGEN_DEL_ERROR=SERVIDOR_BACKEND"
        set msg "${msg} CODIGO_HTTP=${resp_status} SERVIDOR=${lb_member} POOL=${lb_pool}"
        set msg "${msg} TIEMPO_SERVIDOR_MS=${ttfb_ms} TOTAL_MS=${t_total_ms}"
        log local0.warning $msg

    } elseif { $state_http_req && $state_srv_connected && !$state_http_resp } {
        # Request enviado al servidor pero no respondio
        set msg "\[origin_veredicto\] CONN=${CONN_ID} VS=${VS_NAME} SRC=${SRC_IP}"
        set msg "${msg} RESULTADO=SERVIDOR_NO_RESPONDIO ORIGEN_DEL_ERROR=SERVIDOR_BACKEND"
        set msg "${msg} SERVIDOR=${lb_member} POOL=${lb_pool} TOTAL_MS=${t_total_ms}"
        set msg "${msg} CONCLUSION=BIG-IP envio el request pero el servidor no respondio."
        set msg "${msg} Posible crash del backend, timeout de aplicacion o RST del servidor."
        log local0.err $msg

    } elseif { $state_http_resp } {
        # Conexion normal sin errores
        if { $TRACE_MODE } {
            set msg "\[origin_veredicto\] CONN=${CONN_ID} VS=${VS_NAME} SRC=${SRC_IP}"
            set msg "${msg} RESULTADO=NORMAL STATUS=${resp_status}"
            set msg "${msg} SERVIDOR=${lb_member} POOL=${lb_pool}"
            set msg "${msg} TTFB_MS=${ttfb_ms} TOTAL_MS=${t_total_ms}"
            log local0.debug $msg
        }

    } else {
        # Conexion cerrada sin completar el ciclo HTTP
        set msg "\[origin_veredicto\] CONN=${CONN_ID} VS=${VS_NAME} SRC=${SRC_IP}"
        set msg "${msg} RESULTADO=CONEXION_INCOMPLETA ORIGEN_DEL_ERROR=DESCONOCIDO"
        set msg "${msg} TOTAL_MS=${t_total_ms}"
        set msg "${msg} ESTADOS=ssl_hello:${state_ssl_hello}|ssl_done:${state_ssl_done}"
        set msg "${msg}|http_req:${state_http_req}|srv_conn:${state_srv_connected}"
        log local0.warning $msg
    }
}
