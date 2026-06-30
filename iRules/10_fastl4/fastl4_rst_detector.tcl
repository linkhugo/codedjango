# =============================================================================
# fastl4_rst_detector.tcl
#
# PURPOSE : Detecta conexiones TCP anomalas en Virtual Servers con perfil
#           FastL4, clasificandolas por el tipo de cierre anormal.
#
#           En FastL4 no hay eventos HTTP, por lo que la deteccion se basa
#           unicamente en el comportamiento TCP (duracion, bytes, orden de eventos).
#
#           TIPOS DE CIERRE ANOMALO EN FASTL4:
#
#           TIPO                  CONDICION DETECTADA
#           ------------------    -----------------------------------------------
#           NO_SERVER_CONNECT     CLIENT_CLOSED sin SERVER_CONNECTED previo.
#                                 El cliente cerro antes de que BIG-IP conectara
#                                 al backend (o LB_FAILED ocurrio).
#                                 Causa: LB fallo, cliente hizo RST rapido, scan.
#
#           ZERO_BYTES_CLIENT     Conexion cerrada con 0 bytes desde el cliente.
#                                 TCP SYN+ACK completado pero el cliente no envio
#                                 datos.
#                                 Causa: port scan (SYN scan), health probe externo,
#                                 aplicacion que no llego a enviar datos.
#
#           SERVER_FIRST_CLOSE    SERVER_CLOSED ocurrio antes de CLIENT_CLOSED
#                                 con muy pocos bytes intercambiados.
#                                 El backend cerro la conexion sin intercambio
#                                 sustancial de datos.
#                                 Causa: backend rechazo la conexion, reset del
#                                 servidor, timeout del backend, app crash.
#
#           SHORT_LIVED           Conexion que duro menos de SHORT_DURATION_MS ms
#                                 con pocos bytes. Indica conexion no funcional.
#
#           NORMAL                La conexion opero normalmente.
#
# CASOS DE USO:
#   - Diagnosticar por que conexiones a una base de datos fallan
#   - Detectar resets en servicios TCP como SMTP, FTP, SIP, RADIUS
#   - Identificar port scans en VSes FastL4
#   - Post-mortem de perdida de conectividad a backend no-HTTP
#
# CONFIGURACION:
#   SHORT_DURATION_MS  - Duracion minima para considerar conexion "normal"
#   MIN_BYTES          - Bytes minimos para considerar que hubo intercambio real
#
# LOG TAG : [l4_rst_no_server] / [l4_rst_zero_bytes] / [l4_rst_server_first]
#           [l4_rst_short] / [l4_rst_normal]
# GREP    : grep "\[l4_rst_" /var/log/ltm | grep -v l4_rst_normal
#
# PERFIL  : FastL4
# EVENTS  : CLIENT_ACCEPTED, SERVER_CONNECTED, SERVER_CLOSED, CLIENT_CLOSED
# =============================================================================

when CLIENT_ACCEPTED {
    set conn_id          "[IP::client_addr]:[TCP::client_port]:[clock clicks]"
    set conn_start       [clock clicks -milliseconds]
    set srv_connected    0
    set srv_closed_first 0
    set srv_member       ""
    set srv_pool         ""
}

when SERVER_CONNECTED {
    set srv_connected 1
    set srv_member    "[IP::server_addr]:[TCP::server_port]"
    set srv_pool      [LB::server pool]
}

when SERVER_CLOSED {
    set t_srv_close [expr { [clock clicks -milliseconds] - $conn_start }]

    set cli_bytes_at_srv_close [clientside { TCP::stat bytes_in }]
    if { $cli_bytes_at_srv_close < 128 } {
        set srv_closed_first 1
        set srv_close_time $t_srv_close
        set srv_close_bytes $cli_bytes_at_srv_close
    }
}

when CLIENT_CLOSED {

    set SHORT_DURATION_MS 200
    set MIN_BYTES         32

    set duration [expr { [clock clicks -milliseconds] - $conn_start }]
    set src_ip   [IP::client_addr]
    set src_port [TCP::client_port]
    set vs_name  [virtual name]

    set cli_bytes_in  [clientside { TCP::stat bytes_in }]
    set cli_bytes_out [clientside { TCP::stat bytes_out }]

    if { $srv_connected == 0 } {
        set msg "\[l4_rst_no_server\] ACTOR=CLIENTE ACCION=CIERRE_SIN_CONEXION_AL_SERVIDOR"
        set msg "${msg} VS=${vs_name} CLIENTE_IP=${src_ip}:${src_port}"
        set msg "${msg} CONN_ID=${conn_id} DURATION_MS=${duration}"
        set msg "${msg} BYTES_CLIENTE_ENTRADA=${cli_bytes_in} TIPO=NO_SERVER_CONNECT"
        set msg "${msg} DETALLE=El cliente cerro antes de que BIG-IP conectara al backend."
        set msg "${msg} Posible falla del LB, RST rapido del cliente, o escaneo de puertos."
        log local0.warning $msg

    } elseif { $cli_bytes_in == 0 } {
        set msg "\[l4_rst_zero_bytes\] ACTOR=CLIENTE ACCION=CONEXION_SIN_DATOS"
        set msg "${msg} VS=${vs_name} CLIENTE_IP=${src_ip}:${src_port}"
        set msg "${msg} CONN_ID=${conn_id} DURATION_MS=${duration}"
        set msg "${msg} SERVIDOR=${srv_member} TIPO=ZERO_BYTES_CLIENT"
        set msg "${msg} DETALLE=Conexion TCP establecida pero el cliente no envio ningun dato."
        set msg "${msg} Posible escaner de puertos (SYN scan) o health probe externo."
        log local0.warning $msg

    } elseif { $srv_closed_first == 1 } {
        set msg "\[l4_rst_server_first\] ACTOR=SERVIDOR ACCION=SERVIDOR_CERRO_CON_MINIMOS_DATOS"
        set msg "${msg} VS=${vs_name} CLIENTE_IP=${src_ip}:${src_port}"
        set msg "${msg} CONN_ID=${conn_id} DURATION_MS=${duration}"
        set msg "${msg} POOL=${srv_pool} SERVIDOR=${srv_member}"
        set msg "${msg} SERVIDOR_CERRO_EN_MS=${srv_close_time}"
        set msg "${msg} BYTES_AL_CIERRE_SERVIDOR=${srv_close_bytes}"
        set msg "${msg} TIPO=SERVER_FIRST_CLOSE"
        set msg "${msg} DETALLE=El backend cerro la conexion con minimo intercambio de datos."
        set msg "${msg} Posible rechazo del backend, RST del servidor, timeout, o crash de la app."
        log local0.err $msg

    } elseif { $duration < $SHORT_DURATION_MS && ($cli_bytes_in + $cli_bytes_out) < $MIN_BYTES } {
        set msg "\[l4_rst_short\] ACTOR=CLIENTE ACCION=CONEXION_MUY_CORTA"
        set msg "${msg} VS=${vs_name} CLIENTE_IP=${src_ip}:${src_port}"
        set msg "${msg} CONN_ID=${conn_id} DURATION_MS=${duration}"
        set msg "${msg} BYTES_CLIENTE_ENTRADA=${cli_bytes_in} BYTES_CLIENTE_SALIDA=${cli_bytes_out}"
        set msg "${msg} SERVIDOR=${srv_member} TIPO=SHORT_LIVED"
        set msg "${msg} DETALLE=Conexion muy corta (${duration}ms) con pocos datos. Indica conexion no funcional."
        log local0.warning $msg

    } else {
        set msg "\[l4_rst_normal\] ACTOR=CLIENTE ACCION=CONEXION_NORMAL"
        set msg "${msg} VS=${vs_name} CLIENTE_IP=${src_ip}:${src_port}"
        set msg "${msg} CONN_ID=${conn_id} DURATION_MS=${duration}"
        set msg "${msg} BYTES_ENTRADA=${cli_bytes_in} BYTES_SALIDA=${cli_bytes_out}"
        log local0.debug $msg
    }
}
