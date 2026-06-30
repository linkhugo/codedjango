# =============================================================================
# connection_tracker.tcl
#
# PURPOSE : Trackea el ciclo de vida completo de una conexion TCP:
#           CLIENT_ACCEPTED -> SERVER_CONNECTED -> SERVER_CLOSED -> CLIENT_CLOSED
#           Captura duracion total en ms y detecta fallas de LB.
#
# CASOS DE USO:
#   - TCP resets inesperados
#   - Idle timeouts mal configurados
#   - Asymmetric routing (SERVER_CLOSED sin CLIENT_CLOSED)
#   - Pool members rechazando conexiones (LB_FAILED)
#
# LOG TAG : [conn_track]
# GREP    : grep "\[conn_track\]" /var/log/ltm | grep ACCION=ERROR_SIN_SERVIDORES
#
# EVENTS  : CLIENT_ACCEPTED, SERVER_CONNECTED, LB_FAILED,
#           SERVER_CLOSED, CLIENT_CLOSED
# =============================================================================

when CLIENT_ACCEPTED {
    set conn_id    "[IP::client_addr]:[TCP::client_port]:[clock clicks]"
    set conn_start [clock clicks -milliseconds]

    set msg "\[conn_track\] ACTOR=CLIENTE ACCION=CONEXION_ACEPTADA"
    set msg "${msg} CORRELATION_ID=${conn_id} VS=[virtual name]"
    set msg "${msg} CLIENTE_IP=[IP::client_addr]:[TCP::client_port]"
    set msg "${msg} DESTINO=[IP::local_addr]:[TCP::local_port]"
    log local0.debug $msg
}

when SERVER_CONNECTED {
    set msg "\[conn_track\] ACTOR=BIGIP ACCION=CONEXION_AL_SERVIDOR_ESTABLECIDA"
    set msg "${msg} CORRELATION_ID=${conn_id} POOL=[LB::server pool]"
    set msg "${msg} SERVIDOR=[IP::server_addr]:[TCP::server_port]"
    set msg "${msg} CLIENTE_IP=[IP::client_addr]"
    log local0.debug $msg
}

when LB_FAILED {
    set msg "\[conn_track\] ACTOR=BIGIP ACCION=ERROR_SIN_SERVIDORES"
    set msg "${msg} CORRELATION_ID=${conn_id} VS=[virtual name]"
    set msg "${msg} CLIENTE_IP=[IP::client_addr]:[TCP::client_port]"
    set msg "${msg} DETALLE=No habia servidores disponibles en el pool."
    set msg "${msg} BIG-IP no pudo enrutar la conexion del cliente."
    log local0.warning $msg
}

when SERVER_CLOSED {
    set msg "\[conn_track\] ACTOR=SERVIDOR ACCION=CONEXION_SERVIDOR_CERRADA"
    set msg "${msg} CORRELATION_ID=${conn_id}"
    set msg "${msg} SERVIDOR=[IP::server_addr]:[TCP::server_port]"
    log local0.debug $msg
}

when CLIENT_CLOSED {
    set duration [expr { [clock clicks -milliseconds] - $conn_start }]

    set msg "\[conn_track\] ACTOR=CLIENTE ACCION=CONEXION_CERRADA"
    set msg "${msg} CORRELATION_ID=${conn_id} VS=[virtual name]"
    set msg "${msg} CLIENTE_IP=[IP::client_addr]:[TCP::client_port]"
    set msg "${msg} DURATION_MS=${duration}"
    log local0.info $msg
}
