# =============================================================================
# fastl4_idle_timeout_detector.tcl
#
# PURPOSE : Detecta conexiones que estan siendo terminadas por el idle-timeout
#           del perfil FastL4 y determina si el timeout configurado es adecuado
#           o necesita aumentarse.
#
#           LOGICA DE DETECCION:
#           Cuando BIG-IP mata una conexion por idle-timeout, la conexion dura
#           exactamente el valor configurado en "idle-timeout" del perfil FastL4.
#           Este iRule compara la duracion real de cada conexion contra el timeout
#           configurado (con un margen). Si coincide Y habia bytes activos,
#           el timeout esta matando conexiones que deberian seguir vivas.
#
#           CLASIFICACION DEL CIERRE:
#
#           TIPO                   CONDICION                SIGNIFICADO
#           -------------------    --------------------     -----------------------
#           IDLE_TIMEOUT_ACTIVE    duracion ~= timeout      El timeout mato una
#                                  Y bytes > 0              conexion con actividad
#                                                           reciente. Timeout CORTO.
#                                                           ACCION: aumentar timeout.
#
#           IDLE_TIMEOUT_IDLE      duracion ~= timeout      El timeout mato una
#                                  Y bytes == 0 o muy bajos conexion verdaderamente
#                                                           inactiva. Timeout OK.
#
#           NORMAL_CLOSE           duracion != timeout      Cierre normal, el cliente
#                                                           o servidor termino la
#                                                           sesion antes del timeout.
#
#           LONG_LIVED             duracion > timeout        Conexion larga que no fue
#                                                           killed (posible si el
#                                                           perfil tiene timeout 0).
#
#           COMO CAMBIAR EL IDLE-TIMEOUT EN EL PERFIL FastL4:
#           -------------------------------------------------------
#           Ver el timeout actual:
#             tmsh list ltm profile fastl4 <profile_name> idle-timeout
#
#           Cambiar a 600 segundos (perfil especifico):
#             tmsh modify ltm profile fastl4 <profile_name> idle-timeout 600
#
#           Cambiar el perfil fastL4 por defecto del sistema:
#             tmsh modify ltm profile fastl4 fastL4 idle-timeout 600
#
#           Deshabilitar idle-timeout (conexion permanente, con precaucion):
#             tmsh modify ltm profile fastl4 <profile_name> idle-timeout 0
#
#           Guardar cambios:
#             tmsh save sys config
#
# CONFIGURACION:
#   CURRENT_TIMEOUT_SECS - Valor actual del idle-timeout en el perfil FastL4.
#                          DEBE coincidir con el valor real configurado.
#                          Verifica con: tmsh list ltm profile fastl4 <nombre> idle-timeout
#
#   TIMEOUT_MARGIN_SECS  - Margen de tolerancia para detectar timeout kill.
#                          Una conexion cerrada en CURRENT_TIMEOUT_SECS +/- MARGIN
#                          se considera terminada por timeout.
#
#   ACTIVE_BYTES_MIN     - Bytes minimos para considerar que la conexion tenia
#                          actividad real (no era verdaderamente idle).
#
# LOG TAG : [idle_timeout_active] / [idle_timeout_idle] / [idle_normal] / [idle_long]
# GREP    : grep "\[idle_timeout_active\]" /var/log/ltm
#           Para ver distribucion de duraciones de sesion:
#             grep "\[idle_normal\]\|\[idle_timeout" /var/log/ltm | awk '{print $6}' | sort -t= -k2 -n
#
# PERFIL  : FastL4
# EVENTS  : CLIENT_ACCEPTED, SERVER_CONNECTED, CLIENT_CLOSED
# =============================================================================

when CLIENT_ACCEPTED {

    set CURRENT_TIMEOUT_SECS 360
    set TIMEOUT_MARGIN_SECS  10
    set ACTIVE_BYTES_MIN     512

    set conn_id   "[IP::client_addr]:[TCP::client_port]:[clock clicks]"
    set conn_start [clock clicks -milliseconds]
    set srv_member ""
    set srv_pool   ""
}

when SERVER_CONNECTED {
    set srv_member "[IP::server_addr]:[TCP::server_port]"
    set srv_pool   [LB::server pool]
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

    set timeout_low  [expr { $CURRENT_TIMEOUT_SECS - $TIMEOUT_MARGIN_SECS }]
    set timeout_high [expr { $CURRENT_TIMEOUT_SECS + $TIMEOUT_MARGIN_SECS }]

    # ------------------------------------------------------------------
    # Determinar tipo de cierre
    # ------------------------------------------------------------------
    if { $duration_s >= $timeout_low && $duration_s <= $timeout_high } {

        if { $total_bytes >= $ACTIVE_BYTES_MIN } {
            # Timeout mato una conexion con actividad real -> timeout demasiado corto
            set alert "\[idle_timeout_active\] ACTOR=BIGIP ACCION=TIMEOUT_MATO_CONEXION_ACTIVA"
            set alert "${alert} VS=${vs_name} CLIENTE_IP=${src_ip}:${src_port}"
            set alert "${alert} CONN_ID=${conn_id} POOL=${srv_pool} SERVIDOR=${srv_member}"
            set alert "${alert} DURACION_S=${duration_s} TIMEOUT_CONFIGURADO=${CURRENT_TIMEOUT_SECS}s"
            set alert "${alert} BYTES_CLIENTE_ENTRADA=${cli_bytes_in}"
            set alert "${alert} BYTES_CLIENTE_SALIDA=${cli_bytes_out}"
            set alert "${alert} VEREDICTO=TIMEOUT_DEMASIADO_CORTO"
            set alert "${alert} DETALLE=El timeout de ${CURRENT_TIMEOUT_SECS}s elimino una conexion que aun tenia actividad."
            set alert "${alert} Considerar aumentar el idle-timeout."
            set alert "${alert} COMANDO_SUGERIDO=\"tmsh modify ltm profile fastl4 <perfil> idle-timeout 600\""
            log local0.warning $alert

        } else {
            # Timeout mato una conexion verdaderamente inactiva -> timeout funciona bien
            set msg "\[idle_timeout_idle\] ACTOR=BIGIP ACCION=TIMEOUT_CERRO_CONEXION_INACTIVA"
            set msg "${msg} VS=${vs_name} CLIENTE_IP=${src_ip}:${src_port}"
            set msg "${msg} CONN_ID=${conn_id} POOL=${srv_pool} SERVIDOR=${srv_member}"
            set msg "${msg} DURACION_S=${duration_s} TIMEOUT_CONFIGURADO=${CURRENT_TIMEOUT_SECS}s"
            set msg "${msg} BYTES_CLIENTE_ENTRADA=${cli_bytes_in}"
            set msg "${msg} BYTES_CLIENTE_SALIDA=${cli_bytes_out}"
            set msg "${msg} VEREDICTO=CONEXION_INACTIVA_CERRADA_CORRECTAMENTE"
            set msg "${msg} DETALLE=La conexion estaba verdaderamente inactiva. El timeout es apropiado."
            log local0.info $msg
        }

    } elseif { $duration_s > $timeout_high } {
        # Conexion larga que supero el timeout (posible timeout=0 o keepalive activo)
        set msg "\[idle_long\] ACTOR=CLIENTE ACCION=CONEXION_DE_LARGA_DURACION"
        set msg "${msg} VS=${vs_name} CLIENTE_IP=${src_ip}:${src_port}"
        set msg "${msg} CONN_ID=${conn_id} POOL=${srv_pool} SERVIDOR=${srv_member}"
        set msg "${msg} DURACION_S=${duration_s} TIMEOUT_CONFIGURADO=${CURRENT_TIMEOUT_SECS}s"
        set msg "${msg} BYTES_CLIENTE_ENTRADA=${cli_bytes_in}"
        set msg "${msg} BYTES_CLIENTE_SALIDA=${cli_bytes_out}"
        set msg "${msg} VEREDICTO=CONEXION_LARGA_ACTIVA"
        log local0.info $msg

    } else {
        # Cierre normal antes del timeout
        set msg "\[idle_normal\] ACTOR=CLIENTE ACCION=CIERRE_NORMAL_ANTES_DEL_TIMEOUT"
        set msg "${msg} VS=${vs_name} CLIENTE_IP=${src_ip}:${src_port}"
        set msg "${msg} CONN_ID=${conn_id} DURACION_S=${duration_s}"
        set msg "${msg} BYTES_ENTRADA=${cli_bytes_in} BYTES_SALIDA=${cli_bytes_out}"
        set msg "${msg} VEREDICTO=CIERRE_NORMAL"
        log local0.debug $msg
    }
}
