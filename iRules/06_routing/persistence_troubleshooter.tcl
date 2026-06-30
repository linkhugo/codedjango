# =============================================================================
# persistence_troubleshooter.tcl
#
# PURPOSE : Trace completo de la decision de persistencia:
#           - Cookie BIG-IP (BIGipServer<pool>) presente/ausente y su valor
#           - Source-IP persistence record lookup
#           - UIE persistence key
#           - App cookies (JSESSIONID, PHPSESSID, sessionToken)
#           - Member al que finalmente resolvio LB_SELECTED
#           - Si BIG-IP inserto una nueva cookie de persistencia en la respuesta
#           Inyecta X-BIG-IP-Member y X-BIG-IP-Pool como headers de respuesta
#           para confirmar routing desde el cliente (REMOVER EN PRODUCCION).
#
# CASOS DE USO:
#   - Sesiones no sticky o siempre al mismo member aunque este down
#   - Validar que la cookie de persistencia se esta insertando correctamente
#   - Confirmar fallback behavior cuando el member persisted esta down
#
# LOG TAG : [persist_debug] / [persist_result]
# GREP    : grep "\[persist_debug\]" /var/log/ltm | grep COOKIE_PRESENTE
#
# EVENTS  : HTTP_REQUEST, LB_SELECTED, HTTP_RESPONSE
# =============================================================================

when HTTP_REQUEST {

    set client_ip [IP::client_addr]
    set req_uri   [HTTP::uri]
    set req_host  [HTTP::host]
    set vs_name   [virtual name]

    set persist_cookie_name "BIGipServer[LB::server pool]"
    set persist_cookie_val  [HTTP::cookie value $persist_cookie_name]

    if { $persist_cookie_val ne "" } {
        set msg "\[persist_debug\] ACTOR=CLIENTE ACCION=COOKIE_PERSISTENCIA_PRESENTE"
        set msg "${msg} TIPO=COOKIE VS=${vs_name} CLIENTE_IP=${client_ip} URI=${req_uri}"
        set msg "${msg} NOMBRE_COOKIE=${persist_cookie_name} VALOR=${persist_cookie_val}"
        log local0.info $msg
    } else {
        set msg "\[persist_debug\] ACTOR=CLIENTE ACCION=SIN_COOKIE_PERSISTENCIA"
        set msg "${msg} TIPO=COOKIE VS=${vs_name} CLIENTE_IP=${client_ip}"
        set msg "${msg} DETALLE=El cliente no envio cookie de persistencia de BIG-IP."
        log local0.debug $msg
    }

    set src_persist [persist lookup source_addr]
    if { $src_persist ne "" } {
        set msg "\[persist_debug\] ACTOR=BIGIP ACCION=PERSISTENCIA_IP_ORIGEN_ACTIVA"
        set msg "${msg} TIPO=IP_ORIGEN VS=${vs_name} CLIENTE_IP=${client_ip}"
        set msg "${msg} SERVIDOR_PERSISTIDO=${src_persist}"
        log local0.info $msg
    }

    set uie_persist [persist lookup uie]
    if { $uie_persist ne "" } {
        set msg "\[persist_debug\] ACTOR=BIGIP ACCION=PERSISTENCIA_UIE_ACTIVA"
        set msg "${msg} TIPO=UIE VS=${vs_name} CLIENTE_IP=${client_ip}"
        set msg "${msg} CLAVE_UIE=${uie_persist}"
        log local0.info $msg
    }

    foreach app_cookie { "JSESSIONID" "PHPSESSID" "session_id" "sessionToken" } {
        set val [HTTP::cookie value $app_cookie]
        if { $val ne "" } {
            set msg "\[persist_debug\] ACTOR=CLIENTE ACCION=COOKIE_APP_PRESENTE"
            set msg "${msg} NOMBRE_COOKIE=${app_cookie} CLIENTE_IP=${client_ip}"
            set msg "${msg} VALOR_PARCIAL=[string range $val 0 20]..."
            log local0.debug $msg
        }
    }
}

when LB_SELECTED {
    set msg "\[persist_debug\] ACTOR=BIGIP ACCION=SERVIDOR_SELECCIONADO_POR_LB"
    set msg "${msg} VS=[virtual name] CLIENTE_IP=${client_ip} URI=${req_uri}"
    set msg "${msg} POOL=[LB::server pool]"
    set msg "${msg} SERVIDOR_FINAL=[LB::server addr]:[LB::server port]"
    log local0.info $msg
}

when HTTP_RESPONSE {
    set member_ip   [LB::server addr]
    set member_port [LB::server port]
    set pool_name   [LB::server pool]
    set status      [HTTP::status]

    set new_cookie [HTTP::cookie value $persist_cookie_name]
    if { $new_cookie ne "" } {
        set msg "\[persist_debug\] ACTOR=BIGIP ACCION=COOKIE_PERSISTENCIA_INSERTADA_EN_RESPUESTA"
        set msg "${msg} VS=[virtual name] CLIENTE_IP=${client_ip}"
        set msg "${msg} NOMBRE_COOKIE=${persist_cookie_name}"
        set msg "${msg} SERVIDOR=${member_ip}:${member_port}"
        log local0.info $msg
    }

    HTTP::header insert "X-BIG-IP-Member" "${member_ip}:${member_port}"
    HTTP::header insert "X-BIG-IP-Pool"   $pool_name

    set msg "\[persist_result\] ACTOR=BIGIP ACCION=RESULTADO_PERSISTENCIA"
    set msg "${msg} VS=[virtual name] CLIENTE_IP=${client_ip} URI=${req_uri}"
    set msg "${msg} CODIGO_HTTP=${status} SERVIDOR=${member_ip}:${member_port}"
    log local0.info $msg
}
