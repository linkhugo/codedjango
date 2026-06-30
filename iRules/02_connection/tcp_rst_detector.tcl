# =============================================================================
# tcp_rst_detector.tcl
#
# PURPOSE : Detecta conexiones TCP anormales y resets (RST) clasificandolos
#           por tipo segun en que etapa ocurren:
#
#           TIPO                  DESCRIPCION
#           ------------------    -----------------------------------------------
#           PRE_HTTP_CLOSE        CLIENT_CLOSED sin ningun HTTP_REQUEST previo.
#                                 El cliente cerro antes de enviar datos.
#                                 Causa: RST del cliente, timeout de red, scanner.
#
#           SERVER_ABORT          SERVER_CLOSED sin haber recibido HTTP_RESPONSE.
#                                 El backend cerro la conexion antes de responder.
#                                 Causa: backend crash, app error, timeout del pool.
#
#           INCOMPLETE_RESPONSE   HTTP_RESPONSE recibido pero CLIENT_CLOSED antes
#                                 de HTTP_RESPONSE_RELEASE. El cliente corto la
#                                 recepcion a mitad de la respuesta.
#                                 Causa: usuario cancelo, timeout del cliente, RST.
#
#           NORMAL                La conexion completo su ciclo correctamente.
#
# CASOS DE USO:
#   - Errores "connection reset by peer" en logs de aplicacion
#   - Backend que muere silenciosamente sin devolver respuesta
#   - Clientes que se desconectan durante la transferencia de archivos grandes
#   - Distinguir si el problema es el cliente, la red, o el backend
#
# LOG TAG : [rst_pre_http] / [rst_server_abort] / [rst_incomplete] / [rst_normal]
# GREP    : grep "\[rst_server_abort\]" /var/log/ltm
#           grep "\[rst_" /var/log/ltm | grep -v rst_normal
#
# EVENTS  : CLIENT_ACCEPTED, HTTP_REQUEST, LB_SELECTED, SERVER_CONNECTED,
#           HTTP_RESPONSE, HTTP_RESPONSE_RELEASE, SERVER_CLOSED, CLIENT_CLOSED
# =============================================================================

when CLIENT_ACCEPTED {
    set conn_id      "[IP::client_addr]:[TCP::client_port]:[clock clicks]"
    set conn_start   [clock clicks -milliseconds]
    set http_seen    0
    set lb_member    ""
    set resp_seen    0
    set resp_release 0
    set resp_status  ""
    set server_closed_early 0
}

when HTTP_REQUEST {
    set http_seen   1
    set req_method  [HTTP::method]
    set req_uri     [HTTP::uri]
    set req_src     [IP::client_addr]
}

when LB_SELECTED {
    set lb_member "[LB::server addr]:[LB::server port]"
    set lb_pool   [LB::server pool]
}

when SERVER_CONNECTED {
    set server_ip "[IP::server_addr]:[TCP::server_port]"
}

when HTTP_RESPONSE {
    set resp_seen   1
    set resp_status [HTTP::status]
}

when HTTP_RESPONSE_RELEASE {
    set resp_release 1
}

when SERVER_CLOSED {
    if { $resp_seen == 0 && $http_seen == 1 } {
        set server_closed_early 1
    }
}

when CLIENT_CLOSED {
    set duration [expr { [clock clicks -milliseconds] - $conn_start }]
    set src_ip   [IP::client_addr]
    set vs_name  [virtual name]

    if { $http_seen == 0 } {
        set msg "\[rst_pre_http\] ACTOR=CLIENTE ACCION=CIERRE_SIN_REQUEST_HTTP"
        set msg "${msg} VS=${vs_name} CLIENTE_IP=${src_ip} CORRELATION_ID=${conn_id}"
        set msg "${msg} DURATION_MS=${duration} TIPO=PRE_HTTP_CLOSE"
        set msg "${msg} DETALLE=El cliente cerro la conexion sin enviar ningun request HTTP."
        set msg "${msg} Puede ser un RST de red, timeout del cliente, o un escaner."
        log local0.warning $msg

    } elseif { $server_closed_early == 1 } {
        set msg "\[rst_server_abort\] ACTOR=SERVIDOR ACCION=SERVIDOR_CERRO_SIN_RESPONDER"
        set msg "${msg} VS=${vs_name} CLIENTE_IP=${src_ip} CORRELATION_ID=${conn_id}"
        set msg "${msg} DURATION_MS=${duration} TIPO=SERVER_ABORT"
        set msg "${msg} POOL=${lb_pool} SERVIDOR=${lb_member}"
        set msg "${msg} METHOD=${req_method} URI=${req_uri}"
        set msg "${msg} DETALLE=El servidor backend cerro la conexion sin enviar respuesta HTTP."
        set msg "${msg} Posible crash del backend, timeout del pool, o error de la aplicacion."
        log local0.err $msg

    } elseif { $resp_seen == 1 && $resp_release == 0 } {
        set msg "\[rst_incomplete\] ACTOR=CLIENTE ACCION=CLIENTE_CANCELO_RESPUESTA"
        set msg "${msg} VS=${vs_name} CLIENTE_IP=${src_ip} CORRELATION_ID=${conn_id}"
        set msg "${msg} DURATION_MS=${duration} TIPO=INCOMPLETE_RESPONSE"
        set msg "${msg} CODIGO_HTTP=${resp_status} SERVIDOR=${lb_member}"
        set msg "${msg} METHOD=${req_method} URI=${req_uri}"
        set msg "${msg} DETALLE=El cliente cerro la conexion mientras recibia la respuesta."
        set msg "${msg} El usuario cancelo la carga, el cliente tuvo timeout, o hubo RST de red."
        log local0.warning $msg

    } else {
        set msg "\[rst_normal\] ACTOR=CLIENTE ACCION=CONEXION_NORMAL"
        set msg "${msg} VS=${vs_name} CLIENTE_IP=${src_ip} CORRELATION_ID=${conn_id}"
        set msg "${msg} DURATION_MS=${duration} TIPO=NORMAL"
        log local0.debug $msg
    }
}
