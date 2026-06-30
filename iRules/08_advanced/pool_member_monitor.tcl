# =============================================================================
# pool_member_monitor.tcl
#
# PURPOSE : Registra cada transicion de estado de pool members:
#           POOL_MEMBER_UP   - El member paso a estado disponible
#           POOL_MEMBER_DOWN - El member paso a estado no disponible
#           Captura: pool name, member IP:port, causa del cambio.
#
# CASOS DE USO:
#   - Correlacionar caidas de pool members con errores de aplicacion
#   - Historial de disponibilidad de members para post-mortem
#   - Detectar members que oscilan (flapping up/down)
#   - Alertar inmediatamente cuando un member cae
#
# NOTA    : Este iRule debe asignarse al Virtual Server.
#           Los eventos POOL_MEMBER_UP/DOWN se disparan cuando el health
#           monitor detecta el cambio de estado, no cuando el admin lo cambia
#           manualmente (para eso se usaria POOL_MEMBER_FORCED_DOWN/UP).
#
# LOG TAG : [member_up] / [member_down]
# GREP    : grep "\[member_down\]" /var/log/ltm
#
# EVENTS  : POOL_MEMBER_UP, POOL_MEMBER_DOWN
# =============================================================================

when POOL_MEMBER_UP {

    set pool_name   [LB::server pool]
    set member_ip   [LB::server addr]
    set member_port [LB::server port]
    set event_time  [clock format [clock seconds] -format "%Y-%m-%d %H:%M:%S"]

    set msg "\[member_up\] ACTOR=BIGIP ACCION=SERVIDOR_DISPONIBLE"
    set msg "${msg} FECHA_HORA=${event_time} VS=[virtual name]"
    set msg "${msg} POOL=${pool_name} SERVIDOR=${member_ip}:${member_port} ESTADO=DISPONIBLE"
    set msg "${msg} DETALLE=El health monitor confirmo que el servidor volvio a estar disponible."
    log local0.info $msg
}

when POOL_MEMBER_DOWN {

    set pool_name   [LB::server pool]
    set member_ip   [LB::server addr]
    set member_port [LB::server port]
    set event_time  [clock format [clock seconds] -format "%Y-%m-%d %H:%M:%S"]

    set msg "\[member_down\] ACTOR=BIGIP ACCION=SERVIDOR_CAIDO"
    set msg "${msg} FECHA_HORA=${event_time} VS=[virtual name]"
    set msg "${msg} POOL=${pool_name} SERVIDOR=${member_ip}:${member_port} ESTADO=CAIDO"
    set msg "${msg} DETALLE=El health monitor detecto que el servidor no responde."
    log local0.warning $msg

    set flap_key "flap_${pool_name}_${member_ip}_${member_port}"
    set flap_count [table lookup -subtable "member_flap" $flap_key]
    if { $flap_count eq "" } {
        table set -subtable "member_flap" $flap_key 1 3600
        set flap_count 1
    } else {
        table incr -subtable "member_flap" $flap_key
        set flap_count [table lookup -subtable "member_flap" $flap_key]
    }

    if { $flap_count >= 3 } {
        set alert "\[member_down\] ACTOR=BIGIP ACCION=SERVIDOR_OSCILANDO_DETECTADO"
        set alert "${alert} POOL=${pool_name}"
        set alert "${alert} SERVIDOR=${member_ip}:${member_port}"
        set alert "${alert} VECES_CAIDO_EN_1H=${flap_count}"
        set alert "${alert} DETALLE=El servidor ha caido ${flap_count} veces en la ultima hora."
        set alert "${alert} Esto indica inestabilidad del backend. Revisar logs del servidor urgente."
        log local0.err $alert
    }
}
