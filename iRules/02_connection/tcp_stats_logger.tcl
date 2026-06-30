# =============================================================================
# tcp_stats_logger.tcl
#
# PURPOSE : Captura estadisticas TCP a nivel de conexion al momento del cierre.
#           Permite distinguir problemas de red de problemas de aplicacion.
#
#           Estadisticas capturadas al cierre:
#             - Bytes recibidos del cliente (clientside bytes_in)
#             - Bytes enviados al cliente (clientside bytes_out)
#             - Bytes enviados al servidor (serverside bytes_out)
#             - Bytes recibidos del servidor (serverside bytes_in)
#             - Duracion total de la conexion
#             - Ratio de datos (request size vs response size)
#
#           Alertas:
#             - Conexion con CERO bytes desde el cliente (posible RST/scanner)
#             - Respuesta enviada sin bytes del servidor (posible servicio de BIG-IP)
#             - Conexion con transferencia muy grande (posible exfiltracion o carga lenta)
#
# CASOS DE USO:
#   - Verificar que el trafico realmente fluyó en ambas direcciones
#   - Detectar conexiones "fantasma" (TCP abierto pero sin datos)
#   - Medir tamano real de payloads (no solo Content-Length declarado)
#   - Detectar uploads o downloads anormalmente grandes
#   - Correlacionar bytes con lentitud de transferencia (bytes / ms = throughput)
#
# CONFIGURACION:
#   LARGE_XFER_BYTES - Umbral para alertar transferencias grandes (default: 10MB)
#   LOG_NORMAL       - 1 = loguear todas las conexiones; 0 = solo anomalias
#
# LOG TAG : [tcp_stats] / [tcp_zero_bytes] / [tcp_large_xfer]
# GREP    : grep "\[tcp_zero_bytes\]" /var/log/ltm
#           grep "\[tcp_large_xfer\]" /var/log/ltm
#
# EVENTS  : CLIENT_ACCEPTED, HTTP_REQUEST, LB_SELECTED, HTTP_RESPONSE,
#           CLIENT_CLOSED
# =============================================================================

when CLIENT_ACCEPTED {
    set conn_id    "[IP::client_addr]:[TCP::client_port]:[clock clicks]"
    set conn_start [clock clicks -milliseconds]
    set req_uri    ""
    set req_method ""
    set resp_status ""
    set lb_member  ""
}

when HTTP_REQUEST {
    set req_method [HTTP::method]
    set req_uri    [HTTP::uri]
}

when LB_SELECTED {
    set lb_member "[LB::server addr]:[LB::server port]"
    set lb_pool   [LB::server pool]
}

when HTTP_RESPONSE {
    set resp_status [HTTP::status]
}

when CLIENT_CLOSED {

    set LARGE_XFER_BYTES 10485760
    set LOG_NORMAL       0

    set duration    [expr { [clock clicks -milliseconds] - $conn_start }]
    set vs_name     [virtual name]
    set src_ip      [IP::client_addr]

    set cli_bytes_in  [clientside { TCP::stat bytes_in }]
    set cli_bytes_out [clientside { TCP::stat bytes_out }]

    if { [catch { set srv_bytes_in  [serverside { TCP::stat bytes_in }]  }] } { set srv_bytes_in  0 }
    if { [catch { set srv_bytes_out [serverside { TCP::stat bytes_out }] }] } { set srv_bytes_out 0 }

    set total_bytes [expr { $cli_bytes_in + $cli_bytes_out }]

    if { $cli_bytes_in == 0 } {
        set alert "\[tcp_zero_bytes\] ACTOR=CLIENTE ACCION=CONEXION_SIN_DATOS"
        set alert "${alert} VS=${vs_name} CLIENTE_IP=${src_ip} CORRELATION_ID=${conn_id}"
        set alert "${alert} DURATION_MS=${duration} BYTES_DEL_CLIENTE=0"
        set alert "${alert} DETALLE=El cliente conecto pero no envio ningun dato."
        set alert "${alert} Puede ser un escaner de puertos, health probe externo, o RST de red."
        log local0.warning $alert

    } elseif { $total_bytes > $LARGE_XFER_BYTES } {
        set total_mb [expr { $total_bytes / 1048576 }]
        set alert "\[tcp_large_xfer\] ACTOR=CLIENTE ACCION=TRANSFERENCIA_GRANDE_DETECTADA"
        set alert "${alert} VS=${vs_name} CLIENTE_IP=${src_ip} CORRELATION_ID=${conn_id}"
        set alert "${alert} TOTAL_MB=${total_mb} BYTES_CLIENTE_ENTRADA=${cli_bytes_in}"
        set alert "${alert} BYTES_CLIENTE_SALIDA=${cli_bytes_out}"
        set alert "${alert} BYTES_SERVIDOR_ENTRADA=${srv_bytes_in} BYTES_SERVIDOR_SALIDA=${srv_bytes_out}"
        set alert "${alert} DURATION_MS=${duration} SERVIDOR=${lb_member} URI=${req_uri}"
        set alert "${alert} DETALLE=Transferencia de ${total_mb} MB detectada. Revisar si es esperada."
        log local0.warning $alert

    } elseif { $LOG_NORMAL } {
        set msg "\[tcp_stats\] ACTOR=CLIENTE ACCION=ESTADISTICAS_CONEXION"
        set msg "${msg} VS=${vs_name} CLIENTE_IP=${src_ip} CORRELATION_ID=${conn_id}"
        set msg "${msg} BYTES_CLIENTE_ENTRADA=${cli_bytes_in} BYTES_CLIENTE_SALIDA=${cli_bytes_out}"
        set msg "${msg} BYTES_SERVIDOR_ENTRADA=${srv_bytes_in} BYTES_SERVIDOR_SALIDA=${srv_bytes_out}"
        set msg "${msg} DURATION_MS=${duration} CODIGO_HTTP=${resp_status} SERVIDOR=${lb_member}"
        log local0.info $msg
    }
}
