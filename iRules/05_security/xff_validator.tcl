# =============================================================================
# xff_validator.tcl
#
# PURPOSE : Valida y sanitiza el header X-Forwarded-For:
#           - Detecta spoofing: XFF enviado por cliente no confiable
#           - Extrae la IP real del cliente desde XFF cuando viene de proxy confiable
#           - Elimina XFF de clientes no confiables para evitar bypass de controles
#           - Logea la cadena completa de proxies
#           - Inserta XFF limpio con la IP real del cliente
#
# CASOS DE USO:
#   - Aplicaciones que confian en XFF para controles de acceso (bypass posible)
#   - Detectar clientes que inyectan XFF falso para evadir rate limiting
#   - Extraer IP real de cliente cuando BIG-IP esta detras de un proxy corporativo
#   - Auditar cadena de proxies en entornos multi-tier
#
# CONFIGURACION:
#   TRUSTED_PROXIES - DataGroup con IPs/CIDRs de proxies confiables
#                     Si no tienes DataGroup, usa la lista estatica TRUSTED_LIST
#
# LOG TAG : [xff_ok] / [xff_spoof] / [xff_clean]
# GREP    : grep "\[xff_spoof\]" /var/log/ltm
#
# EVENTS  : HTTP_REQUEST
# =============================================================================

when HTTP_REQUEST {

    set client_ip [IP::client_addr]
    set req_uri   [HTTP::uri]
    set vs_name   [virtual name]
    set xff       [HTTP::header "X-Forwarded-For"]

    if { $xff eq "" } {
        HTTP::header insert "X-Forwarded-For" $client_ip
        set msg "\[xff_ok\] ACTOR=BIGIP ACCION=XFF_INSERTADO_NUEVO"
        set msg "${msg} VS=${vs_name} CLIENTE_IP=${client_ip}"
        set msg "${msg} X_FORWARDED_FOR=${client_ip}"
        log local0.debug $msg
        return
    }

    set is_trusted 0

    if { [class exists "trusted_proxies"] } {
        if { [class match $client_ip equals "trusted_proxies"] } {
            set is_trusted 1
        }
    } else {
        foreach trusted_cidr { "10.0.0.0/8" "172.16.0.0/12" "192.168.0.0/16" "127.0.0.1/32" } {
            if { [IP::addr $client_ip mask $trusted_cidr] } {
                set is_trusted 1
                break
            }
        }
    }

    if { $is_trusted } {
        set real_client [string trim [lindex [split $xff ","] 0]]
        set msg "\[xff_ok\] ACTOR=BIGIP ACCION=XFF_PROXY_CONFIABLE_ACEPTADO"
        set msg "${msg} VS=${vs_name} PROXY_IP=${client_ip} IP_REAL_CLIENTE=${real_client}"
        set msg "${msg} CADENA_XFF=\"${xff}\" URI=${req_uri}"
        log local0.info $msg

        HTTP::header replace "X-Forwarded-For" "${xff}, ${client_ip}"
    } else {
        set alert "\[xff_spoof\] ACTOR=CLIENTE ACCION=XFF_FALSIFICADO_DETECTADO"
        set alert "${alert} VS=${vs_name} CLIENTE_IP=${client_ip}"
        set alert "${alert} X_FORWARDED_FOR_FALSO=\"${xff}\" URI=${req_uri}"
        set alert "${alert} DETALLE=Un cliente no confiable envio un header X-Forwarded-For."
        set alert "${alert} Este header fue eliminado para evitar bypass de controles de seguridad."
        log local0.warning $alert

        HTTP::header remove "X-Forwarded-For"
        HTTP::header insert "X-Forwarded-For" $client_ip
        set msg "\[xff_clean\] ACTOR=BIGIP ACCION=XFF_LIMPIADO_Y_REEMPLAZADO"
        set msg "${msg} VS=${vs_name} CLIENTE_IP=${client_ip}"
        set msg "${msg} NUEVO_X_FORWARDED_FOR=${client_ip}"
        log local0.info $msg
    }
}
