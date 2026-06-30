# =============================================================================
# websocket_debugger.tcl
#
# PURPOSE : Diagnostica el proceso de upgrade a WebSocket:
#           - Detecta requests de upgrade y loguea los headers de handshake
#           - Verifica presencia de headers obligatorios (Sec-WebSocket-Key, Version)
#           - Loguea el resultado del handshake (101 Switching Protocols o error)
#           - Detecta upgrades rechazados por el servidor (no-101)
#           - Desactiva HTTP processing para conexiones WS establecidas
#           - Routea trafico WS a pool especifico (opcional)
#
# CASOS DE USO:
#   - WebSocket que no levanta (cliente recibe 400/403 en lugar de 101)
#   - Handshake parcial o con headers incorrectos
#   - Pool member que no soporta WS y rechaza el upgrade
#   - Validar que BIG-IP no esta interfiriendo con el protocolo WS
#
# CONFIGURACION:
#   WS_POOL - Pool destino para trafico WebSocket (dejar "" para no redirigir)
#
# LOG TAG : [ws_upgrade] / [ws_ok] / [ws_fail] / [ws_missing_header]
# GREP    : grep "\[ws_fail\]" /var/log/ltm
#
# EVENTS  : HTTP_REQUEST, HTTP_RESPONSE
# =============================================================================

when HTTP_REQUEST {

    set WS_POOL ""

    set upgrade_hdr    [string tolower [HTTP::header "Upgrade"]]
    set connection_hdr [string tolower [HTTP::header "Connection"]]
    set req_src        [IP::client_addr]
    set req_uri        [HTTP::uri]
    set req_host       [HTTP::host]
    set vs_name        [virtual name]

    set is_ws_upgrade 0
    if { [string match "*websocket*" $upgrade_hdr] && [string match "*upgrade*" $connection_hdr] } {
        set is_ws_upgrade 1
    }

    if { $is_ws_upgrade } {

        set ws_key      [HTTP::header "Sec-WebSocket-Key"]
        set ws_version  [HTTP::header "Sec-WebSocket-Version"]
        set ws_protocol [HTTP::header "Sec-WebSocket-Protocol"]
        set ws_ext      [HTTP::header "Sec-WebSocket-Extensions"]
        set ws_origin   [HTTP::header "Origin"]

        set msg "\[ws_upgrade\] ACTOR=CLIENTE ACCION=SOLICITUD_WEBSOCKET_RECIBIDA"
        set msg "${msg} VS=${vs_name} CLIENTE_IP=${req_src} HOST=${req_host} URI=${req_uri}"
        set msg "${msg} CLAVE_WS=${ws_key} VERSION_WS=${ws_version}"
        set msg "${msg} PROTOCOLO=\"${ws_protocol}\""
        set msg "${msg} ORIGEN=${ws_origin} EXTENSIONES=\"${ws_ext}\""
        log local0.info $msg

        if { $ws_key eq "" } {
            set msg "\[ws_missing_header\] ACTOR=CLIENTE ACCION=HEADER_OBLIGATORIO_FALTANTE"
            set msg "${msg} VS=${vs_name} CLIENTE_IP=${req_src} URI=${req_uri}"
            set msg "${msg} HEADER_FALTANTE=Sec-WebSocket-Key"
            set msg "${msg} DETALLE=El handshake WebSocket no puede completarse sin este header."
            log local0.warning $msg
        }
        if { $ws_version eq "" } {
            set msg "\[ws_missing_header\] ACTOR=CLIENTE ACCION=HEADER_OBLIGATORIO_FALTANTE"
            set msg "${msg} VS=${vs_name} CLIENTE_IP=${req_src} URI=${req_uri}"
            set msg "${msg} HEADER_FALTANTE=Sec-WebSocket-Version"
            set msg "${msg} DETALLE=El handshake WebSocket no puede completarse sin este header."
            log local0.warning $msg
        }

        if { $WS_POOL ne "" } {
            pool $WS_POOL
            set msg "\[ws_upgrade\] ACTOR=BIGIP ACCION=TRAFICO_WS_ENRUTADO_A_POOL"
            set msg "${msg} VS=${vs_name} CLIENTE_IP=${req_src} POOL_WEBSOCKET=${WS_POOL}"
            log local0.info $msg
        }
    }
}

when HTTP_RESPONSE {

    set status [HTTP::status]

    if { [HTTP::header exists "Upgrade"] || [HTTP::header exists "Sec-WebSocket-Accept"] } {

        if { $status eq "101" } {
            set msg "\[ws_ok\] ACTOR=SERVIDOR ACCION=WEBSOCKET_ESTABLECIDO"
            set msg "${msg} VS=[virtual name]"
            set msg "${msg} SERVIDOR=[LB::server addr]:[LB::server port]"
            set msg "${msg} CODIGO_HTTP=101"
            set msg "${msg} CLAVE_ACEPTADA=[HTTP::header Sec-WebSocket-Accept]"
            set msg "${msg} DETALLE=Handshake WebSocket completado con exito. Conexion establecida."
            log local0.info $msg
            HTTP::disable
        } else {
            set alert "\[ws_fail\] ACTOR=SERVIDOR ACCION=WEBSOCKET_RECHAZADO"
            set alert "${alert} VS=[virtual name]"
            set alert "${alert} SERVIDOR=[LB::server addr]:[LB::server port]"
            set alert "${alert} CODIGO_HTTP=${status}"
            set alert "${alert} DETALLE=El servidor rechazo el upgrade a WebSocket con codigo ${status}."
            set alert "${alert} Verificar que el backend soporte WebSocket y que no haya proxy intermedio bloqueando."
            log local0.warning $alert
        }
    }
}
