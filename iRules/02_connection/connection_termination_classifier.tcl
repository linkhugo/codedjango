# =============================================================================
# connection_termination_classifier.tcl
#
# PURPOSE : Clasifica la causa de terminacion de CUALQUIER conexion TCP,
#           funcionando en Virtual Servers con perfil Standard (HTTP) o FastL4.
#
#           Usa una maquina de estados: registra que eventos dispararon y cuales
#           NO dispararon, y al cierre (CLIENT_CLOSED) analiza el patron para
#           determinar por que se cerro la conexion.
#
#           CAUSAS DETECTADAS:
#
#           CAUSA                   QUIEN TERMINO   DESCRIPCION
#           ---------------------   -------------   ---------------------------
#           LB_FAILURE              BIG-IP          No habia pool members
#                                                   disponibles. BIG-IP envio
#                                                   RST al cliente.
#
#           IDLE_TIMEOUT_BIGIP      BIG-IP          La conexion estuvo inactiva
#                                                   durante el idle-timeout
#                                                   configurado y BIG-IP la
#                                                   termino (bytes = bajos).
#
#           IDLE_TIMEOUT_ACTIVE     BIG-IP          BIG-IP termino la conexion
#                                                   por timeout PERO habia bytes
#                                                   activos. El timeout esta
#                                                   demasiado corto.
#
#           SSL_HANDSHAKE_FAIL      BIG-IP/Client   ClientHello recibido pero
#                                                   el handshake no completo.
#                                                   Cipher incompatible, cert
#                                                   invalido, o cliente aborto.
#
#           SERVER_RST              Servidor        El backend cerro la conexion
#                                                   sin enviar respuesta HTTP.
#                                                   Backend crash, timeout del
#                                                   pool, app error.
#
#           CLIENT_RST_PRE_HTTP     Cliente         El cliente cerro antes de
#                                                   enviar cualquier request
#                                                   HTTP. Scanner, timeout de
#                                                   red, RST del cliente.
#
#           CLIENT_RST_MID_RESPONSE Cliente         El cliente aborto durante la
#                                                   recepcion de la respuesta.
#                                                   Usuario cancelo, timeout del
#                                                   cliente, red inestable.
#
#           FASTL4_NO_DATA          Cliente         Conexion FastL4 establecida
#                                                   pero el cliente no envio
#                                                   datos. Port scan o RST.
#
#           FASTL4_SERVER_RST       Servidor        En FastL4, el backend cerro
#                                                   la conexion con minimos
#                                                   bytes intercambiados.
#
#           NORMAL_COMPLETE         Cliente/Servidor Ciclo completo: request +
#                                                   response + release. Cierre
#                                                   normal.
#
#           FASTL4_NORMAL           Cliente/Servidor FastL4: bytes intercambiados,
#                                                   duracion normal. Cierre ok.
#
#           UNKNOWN                 Desconocido     Patron no identificado.
#                                                   Revisar logs.
#
# COMPATIBILIDAD:
#   - Perfil Standard (HTTP): usa todos los eventos disponibles
#   - Perfil FastL4: solo usa eventos TCP (HTTP_* no disparan)
#   El iRule detecta automaticamente en cual perfil esta corriendo usando
#   [info exists] para verificar si los eventos HTTP dispararon.
#
# CONFIGURACION:
#   IDLE_TIMEOUT_SECS   - Valor del idle-timeout configurado en el perfil.
#                         Verificar con: tmsh list ltm profile fastl4 <p> idle-timeout
#                         o:             tmsh list ltm profile tcp <p> idle-timeout
#   TIMEOUT_MARGIN_SECS - Margen para detectar cierre por timeout (+/- segundos)
#   ACTIVE_BYTES_MIN    - Bytes minimos para considerar conexion "activa"
#   SERVER_RST_BYTES    - Bytes maximos desde cliente para clasificar SERVER_RST
#
# LOG TAG : [conn_end]
# GREP    : grep "\[conn_end\]" /var/log/ltm
#           grep "\[conn_end\]" /var/log/ltm | grep "CAUSA=SERVER_RST"
#           grep "\[conn_end\]" /var/log/ltm | grep "CAUSA=IDLE_TIMEOUT_ACTIVE"
#           grep "\[conn_end\]" /var/log/ltm | grep "TERMINO=BIGIP"
#           grep "\[conn_end\]" /var/log/ltm | grep "VLAN=vlan_externa"
#           grep "\[conn_end\]" /var/log/ltm | grep "VLAN_ID=100"
#
# EVENTS  : CLIENT_ACCEPTED, CLIENTSSL_CLIENTHELLO, CLIENTSSL_HANDSHAKE,
#           HTTP_REQUEST, LB_SELECTED, LB_FAILED, SERVER_CONNECTED,
#           HTTP_RESPONSE, HTTP_RESPONSE_RELEASE, SERVER_CLOSED, CLIENT_CLOSED
# =============================================================================

when CLIENT_ACCEPTED {

    set IDLE_TIMEOUT_SECS   360
    set TIMEOUT_MARGIN_SECS 10
    set ACTIVE_BYTES_MIN    512
    set SERVER_RST_BYTES    128

    set conn_id    "[IP::client_addr]:[TCP::client_port]:[clock clicks]"
    set conn_start [clock clicks -milliseconds]

    # Maquina de estados — todos a 0 por defecto
    set state_lb_failed       0
    set state_srv_connected   0
    set state_ssl_hello       0
    set state_ssl_done        0
    set state_http_req        0
    set state_http_resp       0
    set state_http_released   0
    set state_srv_early_close 0

    set req_method  ""
    set req_uri     ""
    set resp_status ""
    set lb_member   ""
    set lb_pool     ""

    # VLAN de origen de la conexion
    set vlan_name [VLAN::name]
    set vlan_id   [VLAN::id]
}

when CLIENTSSL_CLIENTHELLO {
    set state_ssl_hello 1
}

when CLIENTSSL_HANDSHAKE {
    set state_ssl_done 1
}

when HTTP_REQUEST {
    set state_http_req 1
    set req_method     [HTTP::method]
    set req_uri        [HTTP::uri]
}

when LB_SELECTED {
    set lb_member "[LB::server addr]:[LB::server port]"
    set lb_pool   [LB::server pool]
}

when LB_FAILED {
    set state_lb_failed 1
}

when SERVER_CONNECTED {
    set state_srv_connected 1
    if { $lb_member eq "" } {
        set lb_member "[IP::server_addr]:[TCP::server_port]"
    }
}

when HTTP_RESPONSE {
    set state_http_resp 1
    set resp_status [HTTP::status]
}

when HTTP_RESPONSE_RELEASE {
    set state_http_released 1
}

when SERVER_CLOSED {
    if { $state_http_resp == 0 && $state_http_req == 1 } {
        set state_srv_early_close 1
    }
    if { $state_srv_connected == 1 && $state_http_req == 0 } {
        set cli_bytes_at_srv_close [clientside { TCP::stat bytes_in }]
        if { $cli_bytes_at_srv_close < $SERVER_RST_BYTES } {
            set state_srv_early_close 1
        }
    }
}

when CLIENT_CLOSED {

    set duration_ms  [expr { [clock clicks -milliseconds] - $conn_start }]
    set duration_s   [expr { $duration_ms / 1000 }]
    set vs_name      [virtual name]
    set src_ip       [IP::client_addr]
    set src_port     [TCP::client_port]

    set cli_bytes_in  [clientside { TCP::stat bytes_in }]
    set cli_bytes_out [clientside { TCP::stat bytes_out }]
    set total_bytes   [expr { $cli_bytes_in + $cli_bytes_out }]

    set timeout_low  [expr { $IDLE_TIMEOUT_SECS - $TIMEOUT_MARGIN_SECS }]
    set timeout_high [expr { $IDLE_TIMEOUT_SECS + $TIMEOUT_MARGIN_SECS }]
    set near_timeout [expr { $duration_s >= $timeout_low && $duration_s <= $timeout_high }]

    # ------------------------------------------------------------------
    # Determinar CAUSA de terminacion (orden de prioridad)
    # ------------------------------------------------------------------
    set cause        "DESCONOCIDO"
    set terminated_by "DESCONOCIDO"
    set detail        ""

    if { $state_lb_failed } {
        set cause         "LB_FAILURE"
        set terminated_by "BIGIP"
        set detail        "No habia servidores disponibles en el pool. BIG-IP envio RST al cliente."

    } elseif { $state_ssl_hello && !$state_ssl_done } {
        set cause         "SSL_HANDSHAKE_FAIL"
        set terminated_by "BIGIP_O_CLIENTE"
        set detail        "Se recibio el ClientHello TLS pero el handshake no se completo."
        set detail        "${detail} Posible causa: cifrado incompatible, certificado invalido, o cliente aborto."

    } elseif { $near_timeout && $total_bytes >= $ACTIVE_BYTES_MIN } {
        set cause         "IDLE_TIMEOUT_ACTIVE"
        set terminated_by "BIGIP"
        set detail        "BIG-IP termino una conexion ACTIVA por idle-timeout."
        set detail        "${detail} El timeout de ${IDLE_TIMEOUT_SECS}s es demasiado corto. Considerar aumentarlo."

    } elseif { $near_timeout && $total_bytes < $ACTIVE_BYTES_MIN } {
        set cause         "IDLE_TIMEOUT_BIGIP"
        set terminated_by "BIGIP"
        set detail        "BIG-IP cerro una conexion verdaderamente inactiva por idle-timeout."
        set detail        "${detail} El timeout de ${IDLE_TIMEOUT_SECS}s es apropiado para este caso."

    } elseif { $state_http_req && $state_srv_early_close } {
        set cause         "SERVER_RST"
        set terminated_by "SERVIDOR"
        set detail        "El backend cerro la conexion sin enviar respuesta HTTP."

    } elseif { $state_http_req && !$state_http_resp && $state_srv_connected } {
        set cause         "SERVER_NO_RESPONSE"
        set terminated_by "SERVIDOR"
        set detail        "Se envio el request HTTP al backend pero no se recibio respuesta."
        set detail        "${detail} Posible timeout o crash del backend."

    } elseif { $state_http_resp && !$state_http_released } {
        set cause         "CLIENT_RST_MID_RESPONSE"
        set terminated_by "CLIENTE"
        set detail        "El cliente cerro la conexion mientras recibia la respuesta."
        set detail        "${detail} El usuario cancelo, el cliente tuvo timeout, o la red es inestable."

    } elseif { $state_srv_connected && !$state_http_req && $state_ssl_done } {
        set cause         "CLIENT_RST_POST_SSL"
        set terminated_by "CLIENTE"
        set detail        "El handshake TLS se completo pero el cliente no envio ningun request HTTP."

    } elseif { $state_srv_connected && !$state_http_req && !$state_ssl_hello } {
        if { $cli_bytes_in == 0 } {
            set cause         "FASTL4_NO_DATA"
            set terminated_by "CLIENTE"
            set detail        "FastL4: conexion establecida pero el cliente no envio datos. Port scan o RST."
        } elseif { $state_srv_early_close } {
            set cause         "FASTL4_SERVER_RST"
            set terminated_by "SERVIDOR"
            set detail        "FastL4: el backend cerro la conexion con minimo intercambio de datos."
        } else {
            set cause         "FASTL4_NORMAL"
            set terminated_by "CLIENTE_O_SERVIDOR"
            set detail        "FastL4: cierre normal despues de intercambio de datos."
        }

    } elseif { !$state_srv_connected && !$state_lb_failed } {
        set cause         "CLIENT_RST_PRE_LB"
        set terminated_by "CLIENTE"
        set detail        "El cliente cerro antes de que BIG-IP pudiera conectar al backend."
        set detail        "${detail} Posible RST de red, timeout del cliente, o escaner."

    } elseif { $state_http_released } {
        set cause         "NORMAL_COMPLETE"
        set terminated_by "CLIENTE_O_SERVIDOR"
        set detail        "Ciclo HTTP completo con exito: request, respuesta y entrega al cliente."

    } elseif { $state_http_req && $state_http_resp } {
        set cause         "NORMAL_AFTER_RESPONSE"
        set terminated_by "CLIENTE_O_SERVIDOR"
        set detail        "Respuesta HTTP recibida y conexion cerrada antes de HTTP_RESPONSE_RELEASE."
    }

    # ------------------------------------------------------------------
    # Log con toda la informacion relevante
    # ------------------------------------------------------------------
    set msg "\[conn_end\] ACTOR=${terminated_by} CAUSA=${cause}"
    set msg "${msg} VS=${vs_name} CLIENTE_IP=${src_ip}:${src_port} CORRELATION_ID=${conn_id}"
    set msg "${msg} VLAN=${vlan_name} VLAN_ID=${vlan_id}"
    set msg "${msg} TERMINO=${terminated_by}"
    set msg "${msg} DURACION_S=${duration_s} DURATION_MS=${duration_ms}"
    set msg "${msg} BYTES_CLIENTE_ENTRADA=${cli_bytes_in} BYTES_CLIENTE_SALIDA=${cli_bytes_out}"
    set msg "${msg} POOL=${lb_pool} SERVIDOR=${lb_member}"

    if { $req_method ne "" } {
        set msg "${msg} METHOD=${req_method} URI=${req_uri} CODIGO_HTTP=${resp_status}"
    }

    set msg "${msg} ESTADOS=lb_fail:${state_lb_failed}|srv_conn:${state_srv_connected}|ssl:${state_ssl_done}|http_req:${state_http_req}|http_resp:${state_http_resp}|released:${state_http_released}|srv_early:${state_srv_early_close}"
    set msg "${msg} DETALLE=\"${detail}\""

    # Severidad segun quien termino y la causa
    if { $terminated_by eq "BIGIP" && $cause ne "IDLE_TIMEOUT_BIGIP" && $cause ne "NORMAL_COMPLETE" } {
        log local0.warning $msg
    } elseif { $terminated_by eq "SERVIDOR" } {
        log local0.err $msg
    } elseif { $cause eq "LB_FAILURE" || $cause eq "SSL_HANDSHAKE_FAIL" } {
        log local0.err $msg
    } elseif { $cause eq "NORMAL_COMPLETE" || $cause eq "FASTL4_NORMAL" || $cause eq "IDLE_TIMEOUT_BIGIP" } {
        log local0.debug $msg
    } else {
        log local0.info $msg
    }
}
