# =============================================================================
# fastl4_connection_tracker.tcl
#
# PURPOSE : Trackea el ciclo de vida completo de conexiones TCP en un Virtual
#           Server con perfil FastL4. A diferencia de un VS con perfil HTTP,
#           en FastL4 no existen eventos HTTP_REQUEST ni HTTP_RESPONSE.
#           Solo se disparan eventos TCP.
#
#           EVENTOS DISPONIBLES EN FASTL4:
#           +-----------------------+----------------------------------------+
#           | Evento                | Cuando ocurre                          |
#           +-----------------------+----------------------------------------+
#           | CLIENT_ACCEPTED       | BIG-IP acepta el SYN del cliente       |
#           | SERVER_CONNECTED      | TCP hacia el backend establecido       |
#           | LB_FAILED             | Ningun member disponible               |
#           | SERVER_CLOSED         | Conexion TCP hacia backend cerrada     |
#           | CLIENT_CLOSED         | Conexion TCP con cliente cerrada       |
#           +-----------------------+----------------------------------------+
#
#           DIFERENCIAS CLAVE vs perfil HTTP/Standard:
#           - NO hay HTTP_REQUEST, HTTP_RESPONSE, HTTP_RESPONSE_RELEASE
#           - NO hay SSL::* commands
#           - NO hay HTTP::* commands
#           - NO hay persist lookup
#           - SI hay TCP::stat bytes_in / bytes_out
#           - SI hay TCP::collect / TCP::payload (pero desactiva aceleracion PVA)
#
#           Estadisticas al cierre:
#             - Bytes cliente -> BIG-IP (bytes_cliente_entrada)
#             - Bytes BIG-IP -> cliente (bytes_cliente_salida)
#             - Duracion total de la conexion en ms
#
# CASOS DE USO:
#   - Verificar que conexiones TCP llegan y se establecen correctamente
#   - Medir duracion de sesiones en servicios no-HTTP (bases de datos, MQTT,
#     FTP control, SIP, RADIUS, DNS TCP, etc.)
#   - Detectar conexiones muy cortas (posible RST o port scan)
#   - Confirmar que BIG-IP esta conectando al backend correcto
#
# LOG TAG : [l4_accept] / [l4_server] / [l4_close] / [l4_lb_fail]
# GREP    : grep "\[l4_close\]" /var/log/ltm
#           grep "\[l4_lb_fail\]" /var/log/ltm
#
# PERFIL  : FastL4
# EVENTS  : CLIENT_ACCEPTED, SERVER_CONNECTED, LB_FAILED,
#           SERVER_CLOSED, CLIENT_CLOSED
# =============================================================================

when CLIENT_ACCEPTED {
    set conn_id      "[IP::client_addr]:[TCP::client_port]:[clock clicks]"
    set conn_start   [clock clicks -milliseconds]
    set srv_connected 0
    set srv_member    ""
    set srv_pool      ""

    set msg "\[l4_accept\] ACTOR=CLIENTE ACCION=CONEXION_TCP_ACEPTADA"
    set msg "${msg} CONN_ID=${conn_id} VS=[virtual name]"
    set msg "${msg} CLIENTE_IP=[IP::client_addr]:[TCP::client_port]"
    set msg "${msg} DESTINO=[IP::local_addr]:[TCP::local_port]"
    log local0.info $msg
}

when SERVER_CONNECTED {
    set srv_connected 1
    set srv_member    "[IP::server_addr]:[TCP::server_port]"
    set srv_pool      [LB::server pool]
    set t_to_server   [expr { [clock clicks -milliseconds] - $conn_start }]

    set msg "\[l4_server\] ACTOR=BIGIP ACCION=CONEXION_TCP_AL_SERVIDOR_ESTABLECIDA"
    set msg "${msg} CONN_ID=${conn_id} POOL=${srv_pool}"
    set msg "${msg} SERVIDOR=${srv_member} T_PARA_CONECTAR_MS=${t_to_server}"
    log local0.info $msg
}

when LB_FAILED {
    set t_fail [expr { [clock clicks -milliseconds] - $conn_start }]
    set alert  "\[l4_lb_fail\] ACTOR=BIGIP ACCION=ERROR_SIN_SERVIDORES"
    set alert  "${alert} CONN_ID=${conn_id} VS=[virtual name]"
    set alert  "${alert} CLIENTE_IP=[IP::client_addr]:[TCP::client_port] T_MS=${t_fail}"
    set alert  "${alert} DETALLE=No hay servidores disponibles en el pool."
    set alert  "${alert} La conexion del cliente no puede ser enrutada al backend."
    log local0.err $alert
}

when SERVER_CLOSED {
    set t_srv_close [expr { [clock clicks -milliseconds] - $conn_start }]
    set msg "\[l4_server\] ACTOR=SERVIDOR ACCION=CONEXION_TCP_SERVIDOR_CERRADA"
    set msg "${msg} CONN_ID=${conn_id} SERVIDOR=${srv_member} T_MS=${t_srv_close}"
    log local0.debug $msg
}

when CLIENT_CLOSED {
    set duration [expr { [clock clicks -milliseconds] - $conn_start }]

    set cli_bytes_in  [clientside { TCP::stat bytes_in }]
    set cli_bytes_out [clientside { TCP::stat bytes_out }]

    set msg "\[l4_close\] ACTOR=CLIENTE ACCION=CONEXION_CERRADA_RESUMEN"
    set msg "${msg} CONN_ID=${conn_id} VS=[virtual name]"
    set msg "${msg} CLIENTE_IP=[IP::client_addr]:[TCP::client_port]"
    set msg "${msg} POOL=${srv_pool} SERVIDOR=${srv_member}"
    set msg "${msg} DURATION_MS=${duration}"
    set msg "${msg} BYTES_CLIENTE_ENTRADA=${cli_bytes_in}"
    set msg "${msg} BYTES_CLIENTE_SALIDA=${cli_bytes_out}"
    set msg "${msg} SERVIDOR_CONECTO=${srv_connected}"
    log local0.info $msg
}
