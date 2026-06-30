# =============================================================================
# snat_tracker.tcl
#
# PURPOSE : Trackea el uso de SNAT por conexion:
#           - Loguea la IP SNAT asignada por cada conexion hacia el servidor
#           - Detecta cuando una IP SNAT se acerca al limite de puertos (~64k)
#           - Cuenta conexiones activas por IP SNAT usando tabla
#           - Alerta de posible SNAT port exhaustion antes de que ocurra
#
# CASOS DE USO:
#   - Errores "connection refused" o timeouts hacia servidores backend
#     cuando en realidad el problema es agotamiento de puertos SNAT
#   - Verificar que el SNAT pool esta distribuyendo correctamente
#   - Detectar IP SNAT con carga desproporcionada
#   - Post-mortem de incidente de conectividad backend
#
# CONFIGURACION:
#   SNAT_WARN_THRESHOLD - Numero de conexiones simultaneas por IP SNAT
#                         que dispara un WARNING (default: 50000)
#
# LOG TAG : [snat_conn] / [snat_warn] / [snat_close]
# GREP    : grep "\[snat_warn\]" /var/log/ltm
#
# EVENTS  : SERVER_CONNECTED, CLIENT_CLOSED
# =============================================================================

when SERVER_CONNECTED {

    set SNAT_WARN_THRESHOLD 50000

    set client_ip   [IP::client_addr]
    set snat_ip     [IP::local_addr]
    set snat_port   [TCP::local_port]
    set server_ip   [IP::server_addr]
    set server_port [TCP::server_port]
    set pool_name   [LB::server pool]
    set vs_name     [virtual name]

    set snat_key "active_${snat_ip}"
    set active [table incr -subtable "snat_tracker" $snat_key]
    if { $active == 1 } {
        table timeout -subtable "snat_tracker" $snat_key 86400
    }

    set msg "\[snat_conn\] ACTOR=BIGIP ACCION=CONEXION_SNAT_REGISTRADA"
    set msg "${msg} VS=${vs_name} CLIENTE_IP=${client_ip}"
    set msg "${msg} IP_SNAT=${snat_ip}:${snat_port}"
    set msg "${msg} SERVIDOR=${server_ip}:${server_port}"
    set msg "${msg} POOL=${pool_name} CONEXIONES_ACTIVAS_EN_SNAT=${active}"
    log local0.debug $msg

    if { $active > $SNAT_WARN_THRESHOLD } {
        set alert "\[snat_warn\] ACTOR=BIGIP ACCION=RIESGO_AGOTAMIENTO_SNAT"
        set alert "${alert} VS=${vs_name} IP_SNAT=${snat_ip}"
        set alert "${alert} CONEXIONES_ACTIVAS=${active} UMBRAL=${SNAT_WARN_THRESHOLD}"
        set alert "${alert} DETALLE=La IP SNAT tiene ${active} conexiones activas."
        set alert "${alert} El limite de puertos disponibles es ~64000."
        set alert "${alert} Riesgo de agotamiento de puertos. Agregar mas IPs al SNAT pool."
        log local0.warning $alert
    }
}

when CLIENT_CLOSED {

    set snat_ip [IP::local_addr]
    set snat_key "active_${snat_ip}"

    set active [table lookup -subtable "snat_tracker" $snat_key]
    if { $active ne "" && $active > 0 } {
        table set -subtable "snat_tracker" $snat_key [expr { $active - 1 }] 86400
    }

    set msg "\[snat_close\] ACTOR=BIGIP ACCION=CONEXION_SNAT_CERRADA"
    set msg "${msg} IP_SNAT=${snat_ip} CLIENTE_IP=[IP::client_addr]"
    set msg "${msg} CONEXIONES_ACTIVAS_RESTANTES=[table lookup -subtable snat_tracker $snat_key]"
    log local0.debug $msg
}
