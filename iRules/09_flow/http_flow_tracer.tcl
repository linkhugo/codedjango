# =============================================================================
# http_flow_tracer.tcl
#
# PURPOSE : Registra el flujo COMPLETO de una conexion HTTP en todas sus etapas,
#           con tiempo absoluto (ms desde CLIENT_ACCEPTED) y delta entre etapas.
#
#           ORDEN DE EVENTOS en BIG-IP LTM para HTTP estandar:
#
#           SEQ  EVENTO                  QUE OCURRE
#           ---  ---------------------   ------------------------------------------
#            1   CLIENT_ACCEPTED         TCP SYN del cliente aceptado por BIG-IP
#           (2)  CLIENTSSL_CLIENTHELLO   Si hay ClientSSL profile: ClientHello recibido
#           (3)  CLIENTSSL_HANDSHAKE     Si hay ClientSSL profile: TLS negociado
#            4   HTTP_REQUEST            Headers HTTP del cliente parseados
#            5   LB_SELECTED             Pool member seleccionado por BIG-IP
#            6   SERVER_CONNECTED        TCP hacia el backend establecido
#           (7)  SERVERSSL_HANDSHAKE     Si hay ServerSSL profile: TLS con backend
#            8   HTTP_REQUEST_SEND       Request a punto de ser enviado al backend
#            9   HTTP_RESPONSE           Primer byte de respuesta recibido del backend
#           10   HTTP_RESPONSE_RELEASE   Ultimo byte entregado al cliente
#           11   SERVER_CLOSED           Conexion TCP hacia backend cerrada
#           12   CLIENT_CLOSED           Conexion TCP con cliente cerrada
#
#           Los eventos entre parentesis solo aplican si el VS tiene perfil SSL.
#           LB_FAILED reemplaza a LB_SELECTED si no hay member disponible.
#
# CASOS DE USO:
#   - Entender exactamente en que etapa esta tardando una transaccion
#   - Confirmar el orden de ejecucion de eventos al desarrollar iRules
#   - Diagnosticar si BIG-IP tarda en conectar al backend (DELTA en SERVER_CONNECTED)
#   - Medir tiempo de procesamiento del backend (DELTA entre HTTP_REQUEST_SEND y HTTP_RESPONSE)
#   - Detectar si el cliente tarda en cerrar la conexion (DELTA en CLIENT_CLOSED)
#
# IMPORTANTE:
#   - Usar TEMPORALMENTE en produccion: genera un log por evento por conexion.
#   - Activar SAMPLING si el trafico es alto (ver bloque en CLIENT_ACCEPTED).
#   - Cada linea de log comparte el mismo FLOW_ID para correlacionar con grep.
#
# LOG TAG : [flow]
# GREP    : grep "\[flow\]" /var/log/ltm | grep "FLOW_ID=<ip>:<port>:<clicks>"
#           grep "\[flow\]" /var/log/ltm | grep "EVENTO=HTTP_RESPONSE"
#
# EVENTS  : CLIENT_ACCEPTED, CLIENTSSL_CLIENTHELLO, CLIENTSSL_HANDSHAKE,
#           HTTP_REQUEST, LB_SELECTED, LB_FAILED, SERVER_CONNECTED,
#           SERVERSSL_HANDSHAKE, HTTP_REQUEST_SEND, HTTP_RESPONSE,
#           HTTP_RESPONSE_RELEASE, SERVER_CLOSED, CLIENT_CLOSED
# =============================================================================

when CLIENT_ACCEPTED {

    # -- Sampling: descomentar para capturar solo 1 de cada 10 conexiones ----
    # if { [expr { int(rand() * 10) }] != 0 } { set flow_skip 1; return }
    # set flow_skip 0

    set flow_id   "[IP::client_addr]:[TCP::client_port]:[clock clicks]"
    set t_start   [clock clicks -milliseconds]
    set t_prev    $t_start
    set flow_seq  1

    set msg "\[flow\] ACTOR=CLIENTE FLOW_ID=${flow_id} SEQ=${flow_seq} EVENTO=CLIENT_ACCEPTED"
    set msg "${msg} T_MS=0 DELTA_MS=0 VS=[virtual name]"
    set msg "${msg} CLIENTE_IP=[IP::client_addr]:[TCP::client_port]"
    set msg "${msg} DESTINO=[IP::local_addr]:[TCP::local_port]"
    log local0.info $msg
}

when CLIENTSSL_CLIENTHELLO {
    if { ![info exists flow_id] } { return }

    set t_now   [clock clicks -milliseconds]
    set t_total [expr { $t_now - $t_start }]
    set t_delta [expr { $t_now - $t_prev }]
    set t_prev  $t_now
    incr flow_seq

    set msg "\[flow\] ACTOR=CLIENTE FLOW_ID=${flow_id} SEQ=${flow_seq} EVENTO=CLIENTSSL_CLIENTHELLO"
    set msg "${msg} T_MS=${t_total} DELTA_MS=${t_delta} SNI=\"[SSL::servername]\""
    log local0.info $msg
}

when CLIENTSSL_HANDSHAKE {
    if { ![info exists flow_id] } { return }

    set t_now   [clock clicks -milliseconds]
    set t_total [expr { $t_now - $t_start }]
    set t_delta [expr { $t_now - $t_prev }]
    set t_prev  $t_now
    incr flow_seq

    set msg "\[flow\] ACTOR=BIGIP FLOW_ID=${flow_id} SEQ=${flow_seq} EVENTO=CLIENTSSL_HANDSHAKE"
    set msg "${msg} T_MS=${t_total} DELTA_MS=${t_delta}"
    set msg "${msg} VERSION_TLS=[SSL::cipher version] CIFRADO=[SSL::cipher name] BITS=[SSL::cipher bits]"
    if { [SSL::cert count] > 0 } {
        set msg "${msg} CN_CERT_CLIENTE=\"[X509::subject [SSL::cert 0]]\""
    } else {
        set msg "${msg} CERT_CLIENTE=NINGUNO"
    }
    log local0.info $msg
}

when HTTP_REQUEST {
    if { ![info exists flow_id] } { return }

    set t_now   [clock clicks -milliseconds]
    set t_total [expr { $t_now - $t_start }]
    set t_delta [expr { $t_now - $t_prev }]
    set t_prev  $t_now
    incr flow_seq

    set req_method [HTTP::method]
    set req_uri    [HTTP::uri]
    set req_host   [HTTP::host]
    set req_cl     [HTTP::header "Content-Length"]

    set msg "\[flow\] ACTOR=CLIENTE FLOW_ID=${flow_id} SEQ=${flow_seq} EVENTO=HTTP_REQUEST"
    set msg "${msg} T_MS=${t_total} DELTA_MS=${t_delta}"
    set msg "${msg} METHOD=${req_method} HOST=${req_host} URI=${req_uri}"
    set msg "${msg} CONTENT_LENGTH=${req_cl}"
    log local0.info $msg
}

when LB_SELECTED {
    if { ![info exists flow_id] } { return }

    set t_now   [clock clicks -milliseconds]
    set t_total [expr { $t_now - $t_start }]
    set t_delta [expr { $t_now - $t_prev }]
    set t_prev  $t_now
    incr flow_seq

    set msg "\[flow\] ACTOR=BIGIP FLOW_ID=${flow_id} SEQ=${flow_seq} EVENTO=LB_SELECTED"
    set msg "${msg} T_MS=${t_total} DELTA_MS=${t_delta}"
    set msg "${msg} POOL=[LB::server pool] SERVIDOR=[LB::server addr]:[LB::server port]"
    log local0.info $msg
}

when LB_FAILED {
    if { ![info exists flow_id] } { return }

    set t_now   [clock clicks -milliseconds]
    set t_total [expr { $t_now - $t_start }]
    set t_delta [expr { $t_now - $t_prev }]

    set msg "\[flow\] ACTOR=BIGIP FLOW_ID=${flow_id} SEQ=ERROR EVENTO=LB_FAILED"
    set msg "${msg} T_MS=${t_total} DELTA_MS=${t_delta}"
    set msg "${msg} CAUSA=SIN_SERVIDORES_DISPONIBLES"
    log local0.err $msg
}

when SERVER_CONNECTED {
    if { ![info exists flow_id] } { return }

    set t_now   [clock clicks -milliseconds]
    set t_total [expr { $t_now - $t_start }]
    set t_delta [expr { $t_now - $t_prev }]
    set t_prev  $t_now
    incr flow_seq

    set msg "\[flow\] ACTOR=BIGIP FLOW_ID=${flow_id} SEQ=${flow_seq} EVENTO=SERVER_CONNECTED"
    set msg "${msg} T_MS=${t_total} DELTA_MS=${t_delta}"
    set msg "${msg} SERVIDOR=[IP::server_addr]:[TCP::server_port]"
    log local0.info $msg
}

when SERVERSSL_HANDSHAKE {
    if { ![info exists flow_id] } { return }

    set t_now   [clock clicks -milliseconds]
    set t_total [expr { $t_now - $t_start }]
    set t_delta [expr { $t_now - $t_prev }]
    set t_prev  $t_now
    incr flow_seq

    set msg "\[flow\] ACTOR=BIGIP FLOW_ID=${flow_id} SEQ=${flow_seq} EVENTO=SERVERSSL_HANDSHAKE"
    set msg "${msg} T_MS=${t_total} DELTA_MS=${t_delta}"
    set msg "${msg} VERSION_TLS=[SSL::cipher version] CIFRADO=[SSL::cipher name]"
    log local0.info $msg
}

when HTTP_REQUEST_SEND {
    if { ![info exists flow_id] } { return }

    set t_now   [clock clicks -milliseconds]
    set t_total [expr { $t_now - $t_start }]
    set t_delta [expr { $t_now - $t_prev }]
    set t_prev  $t_now
    incr flow_seq

    set msg "\[flow\] ACTOR=BIGIP FLOW_ID=${flow_id} SEQ=${flow_seq} EVENTO=HTTP_REQUEST_SEND"
    set msg "${msg} T_MS=${t_total} DELTA_MS=${t_delta}"
    set msg "${msg} SERVIDOR=[LB::server addr]:[LB::server port]"
    log local0.info $msg
}

when HTTP_RESPONSE {
    if { ![info exists flow_id] } { return }

    set t_now   [clock clicks -milliseconds]
    set t_total [expr { $t_now - $t_start }]
    set t_delta [expr { $t_now - $t_prev }]
    set t_prev  $t_now
    incr flow_seq

    set resp_status [HTTP::status]
    set resp_cl     [HTTP::header "Content-Length"]
    set resp_ct     [HTTP::header "Content-Type"]

    set msg "\[flow\] ACTOR=SERVIDOR FLOW_ID=${flow_id} SEQ=${flow_seq} EVENTO=HTTP_RESPONSE"
    set msg "${msg} T_MS=${t_total} DELTA_MS=${t_delta}"
    set msg "${msg} CODIGO_HTTP=${resp_status} CONTENT_LENGTH=${resp_cl}"
    set msg "${msg} CONTENT_TYPE=\"${resp_ct}\""
    set msg "${msg} SERVIDOR=[LB::server addr]:[LB::server port]"
    log local0.info $msg
}

when HTTP_RESPONSE_RELEASE {
    if { ![info exists flow_id] } { return }

    set t_now   [clock clicks -milliseconds]
    set t_total [expr { $t_now - $t_start }]
    set t_delta [expr { $t_now - $t_prev }]
    set t_prev  $t_now
    incr flow_seq

    set msg "\[flow\] ACTOR=BIGIP FLOW_ID=${flow_id} SEQ=${flow_seq} EVENTO=HTTP_RESPONSE_RELEASE"
    set msg "${msg} T_MS=${t_total} DELTA_MS=${t_delta} CODIGO_HTTP=${resp_status}"
    log local0.info $msg
}

when SERVER_CLOSED {
    if { ![info exists flow_id] } { return }

    set t_now   [clock clicks -milliseconds]
    set t_total [expr { $t_now - $t_start }]
    set t_delta [expr { $t_now - $t_prev }]
    set t_prev  $t_now
    incr flow_seq

    set msg "\[flow\] ACTOR=SERVIDOR FLOW_ID=${flow_id} SEQ=${flow_seq} EVENTO=SERVER_CLOSED"
    set msg "${msg} T_MS=${t_total} DELTA_MS=${t_delta}"
    set msg "${msg} SERVIDOR=[IP::server_addr]:[TCP::server_port]"
    log local0.info $msg
}

when CLIENT_CLOSED {
    if { ![info exists flow_id] } { return }

    set t_now      [clock clicks -milliseconds]
    set t_total    [expr { $t_now - $t_start }]
    set t_delta    [expr { $t_now - $t_prev }]
    incr flow_seq

    set msg "\[flow\] ACTOR=CLIENTE FLOW_ID=${flow_id} SEQ=${flow_seq} EVENTO=CLIENT_CLOSED"
    set msg "${msg} T_MS=${t_total} DELTA_MS=${t_delta} DURACION_TOTAL_MS=${t_total}"
    set msg "${msg} VS=[virtual name] CLIENTE_IP=[IP::client_addr]:[TCP::client_port]"
    log local0.info $msg
}
