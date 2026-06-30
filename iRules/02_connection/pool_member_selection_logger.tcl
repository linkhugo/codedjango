# =============================================================================
# pool_member_selection_logger.tcl
#
# PURPOSE : Registra exactamente que pool member fue seleccionado por request,
#           incluyendo el metodo de LB, si hay persistencia activa, y
#           el status code de la respuesta del member seleccionado.
#
# CASOS DE USO:
#   - Verificar distribucion de carga (ratio/weights/priority groups)
#   - Detectar que persistencia esta sobreescribiendo el LB
#   - Confirmar fallback de priority groups cuando members bajan
#   - Correlacionar que member devuelve que status codes
#
# LOG TAG : [lb_select] / [lb_resp]
# GREP    : grep "\[lb_select\]" /var/log/ltm | awk '{print $8}' | sort | uniq -c
#
# EVENTS  : HTTP_REQUEST, LB_SELECTED, LB_FAILED, HTTP_RESPONSE
# =============================================================================

when HTTP_REQUEST {
    set req_method [HTTP::method]
    set req_uri    [HTTP::uri]
    set req_src    [IP::client_addr]
    set req_host   [HTTP::host]

    if { [persist lookup uie] ne "" } {
        set persist_info "UIE=[persist lookup uie]"
    } elseif { [persist lookup cookie] ne "" } {
        set persist_info "COOKIE=[persist lookup cookie]"
    } elseif { [persist lookup source_addr] ne "" } {
        set persist_info "ORIGEN_IP=[persist lookup source_addr]"
    } else {
        set persist_info "SIN_PERSISTENCIA"
    }
}

when LB_SELECTED {
    set msg "\[lb_select\] ACTOR=BIGIP ACCION=SERVIDOR_SELECCIONADO"
    set msg "${msg} VS=[virtual name] CLIENTE_IP=${req_src} HOST=${req_host}"
    set msg "${msg} METHOD=${req_method} URI=${req_uri}"
    set msg "${msg} POOL=[LB::server pool] SERVIDOR=[LB::server addr]:[LB::server port]"
    set msg "${msg} PERSISTENCIA=${persist_info}"
    log local0.info $msg
}

when LB_FAILED {
    set msg "\[lb_select\] ACTOR=BIGIP ACCION=ERROR_SIN_SERVIDORES"
    set msg "${msg} VS=[virtual name] CLIENTE_IP=${req_src} URI=${req_uri}"
    set msg "${msg} DETALLE=Ningun servidor disponible en el pool."
    set msg "${msg} Verificar estado de los servidores con los health monitors."
    log local0.err $msg
}

when HTTP_RESPONSE {
    set msg "\[lb_resp\] ACTOR=SERVIDOR ACCION=RESPUESTA_SERVIDOR"
    set msg "${msg} VS=[virtual name] CLIENTE_IP=${req_src} URI=${req_uri}"
    set msg "${msg} SERVIDOR=[LB::server addr]:[LB::server port]"
    set msg "${msg} CODIGO_HTTP=[HTTP::status]"
    log local0.info $msg
}
