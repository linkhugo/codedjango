# =============================================================================
# fastl4_flow_tracer.tcl
#
# PURPOSE : Traza el flujo completo de una conexion TCP en un VS con perfil
#           FastL4 mostrando cada evento con timestamp relativo y delta.
#           Equivalente al http_flow_tracer.tcl pero para capa 4.
#
#           ORDEN DE EVENTOS EN FASTL4:
#
#           SEQ  EVENTO            QUE OCURRE
#           ---  ---------------   ------------------------------------------
#            1   CLIENT_ACCEPTED   TCP SYN+ACK completado, cliente conectado
#            2   LB_SELECTED       BIG-IP selecciona el pool member
#            3   SERVER_CONNECTED  TCP hacia el backend establecido (3-way hs)
#            4   SERVER_CLOSED     Backend cierra la conexion TCP
#            5   CLIENT_CLOSED     Cliente cierra la conexion TCP
#
#           El DELTA_MS entre eventos muestra cuanto tardo cada etapa:
#             DELTA en SERVER_CONNECTED = latencia de red hacia el backend
#             DELTA en SERVER_CLOSED    = duracion de la sesion en el backend
#             DELTA en CLIENT_CLOSED    = tiempo total de vida de la conexion
#
#           DIFERENCIAS vs http_flow_tracer:
#             - No hay HTTP_REQUEST, HTTP_RESPONSE (capa 4, sin parse HTTP)
#             - No hay SSL eventos (FastL4 no termina TLS normalmente)
#             - No hay HTTP_REQUEST_SEND ni HTTP_RESPONSE_RELEASE
#             - Mucho menos eventos pero cubren todo el ciclo TCP
#
# CASOS DE USO:
#   - Ver exactamente cuanto tarda BIG-IP en conectar al backend (DELTA SEQ 3)
#   - Detectar si el backend cierra la conexion de inmediato (DELTA SEQ 4 pequeno)
#   - Confirmar que LB_SELECTED y SERVER_CONNECTED ocurren en el orden correcto
#   - Medir duracion total de sesiones TCP (database, MQTT, SIP, etc.)
#
# LOG TAG : [l4_flow]
# GREP    : grep "\[l4_flow\]" /var/log/ltm | grep "FLOW_ID=10.1.1.5:54321"
#
# PERFIL  : FastL4
# EVENTS  : CLIENT_ACCEPTED, LB_SELECTED, LB_FAILED,
#           SERVER_CONNECTED, SERVER_CLOSED, CLIENT_CLOSED
# =============================================================================

when CLIENT_ACCEPTED {
    set flow_id   "[IP::client_addr]:[TCP::client_port]:[clock clicks]"
    set t_start   [clock clicks -milliseconds]
    set t_prev    $t_start
    set flow_seq  1

    set msg "\[l4_flow\] ACTOR=CLIENTE FLOW_ID=${flow_id} SEQ=${flow_seq} EVENTO=CLIENT_ACCEPTED"
    set msg "${msg} T_MS=0 DELTA_MS=0 VS=[virtual name]"
    set msg "${msg} CLIENTE_IP=[IP::client_addr]:[TCP::client_port]"
    set msg "${msg} DESTINO=[IP::local_addr]:[TCP::local_port]"
    log local0.info $msg
}

when LB_SELECTED {
    set t_now   [clock clicks -milliseconds]
    set t_total [expr { $t_now - $t_start }]
    set t_delta [expr { $t_now - $t_prev }]
    set t_prev  $t_now
    incr flow_seq

    set msg "\[l4_flow\] ACTOR=BIGIP FLOW_ID=${flow_id} SEQ=${flow_seq} EVENTO=LB_SELECTED"
    set msg "${msg} T_MS=${t_total} DELTA_MS=${t_delta}"
    set msg "${msg} POOL=[LB::server pool] SERVIDOR=[LB::server addr]:[LB::server port]"
    log local0.info $msg
}

when LB_FAILED {
    set t_now   [clock clicks -milliseconds]
    set t_total [expr { $t_now - $t_start }]
    set t_delta [expr { $t_now - $t_prev }]

    set alert "\[l4_flow\] ACTOR=BIGIP FLOW_ID=${flow_id} SEQ=ERROR EVENTO=LB_FAILED"
    set alert "${alert} T_MS=${t_total} DELTA_MS=${t_delta}"
    set alert "${alert} CAUSA=SIN_SERVIDORES_DISPONIBLES"
    log local0.err $alert
}

when SERVER_CONNECTED {
    set t_now   [clock clicks -milliseconds]
    set t_total [expr { $t_now - $t_start }]
    set t_delta [expr { $t_now - $t_prev }]
    set t_prev  $t_now
    incr flow_seq

    set msg "\[l4_flow\] ACTOR=BIGIP FLOW_ID=${flow_id} SEQ=${flow_seq} EVENTO=SERVER_CONNECTED"
    set msg "${msg} T_MS=${t_total} DELTA_MS=${t_delta}"
    set msg "${msg} SERVIDOR=[IP::server_addr]:[TCP::server_port]"
    log local0.info $msg
}

when SERVER_CLOSED {
    set t_now   [clock clicks -milliseconds]
    set t_total [expr { $t_now - $t_start }]
    set t_delta [expr { $t_now - $t_prev }]
    set t_prev  $t_now
    incr flow_seq

    set msg "\[l4_flow\] ACTOR=SERVIDOR FLOW_ID=${flow_id} SEQ=${flow_seq} EVENTO=SERVER_CLOSED"
    set msg "${msg} T_MS=${t_total} DELTA_MS=${t_delta}"
    set msg "${msg} SERVIDOR=[IP::server_addr]:[TCP::server_port]"
    log local0.info $msg
}

when CLIENT_CLOSED {
    set t_now   [clock clicks -milliseconds]
    set t_total [expr { $t_now - $t_start }]
    set t_delta [expr { $t_now - $t_prev }]
    incr flow_seq

    set cli_bytes_in  [clientside { TCP::stat bytes_in }]
    set cli_bytes_out [clientside { TCP::stat bytes_out }]

    set msg "\[l4_flow\] ACTOR=CLIENTE FLOW_ID=${flow_id} SEQ=${flow_seq} EVENTO=CLIENT_CLOSED"
    set msg "${msg} T_MS=${t_total} DELTA_MS=${t_delta} DURACION_TOTAL_MS=${t_total}"
    set msg "${msg} BYTES_CLIENTE_ENTRADA=${cli_bytes_in} BYTES_CLIENTE_SALIDA=${cli_bytes_out}"
    set msg "${msg} VS=[virtual name] CLIENTE_IP=[IP::client_addr]:[TCP::client_port]"
    log local0.info $msg
}
