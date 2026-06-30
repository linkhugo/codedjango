# =============================================================================
# http_response_inspector.tcl
#
# PURPOSE : Correlaciona request <-> response mostrando:
#           - Status code del origin server
#           - Pool member que respondio
#           - Headers de respuesta: Server, Location, Content-Length
#           - Alerta explicita en 5xx
#
# USAGE   : Util para probar que los errores vienen del origin y no de BIG-IP,
#           y para verificar que member esta devolviendo cada status code.
#
# LOG TAG : [http_resp] y [http_5xx_alert]
# GREP    : grep "\[http_5xx_alert\]" /var/log/ltm
#
# EVENTS  : HTTP_REQUEST, HTTP_RESPONSE
# =============================================================================

when HTTP_REQUEST {
    set req_method [HTTP::method]
    set req_uri    [HTTP::uri]
    set req_src    [IP::client_addr]
    set req_host   [HTTP::host]
}

when HTTP_RESPONSE {
    set pool_name    [LB::server pool]
    set member_ip    [LB::server addr]
    set member_port  [LB::server port]
    set status       [HTTP::status]
    set content_len  [HTTP::header "Content-Length"]
    set content_type [HTTP::header "Content-Type"]
    set server_hdr   [HTTP::header "Server"]
    set location     [HTTP::header "Location"]

    set msg "\[http_resp\] ACTOR=SERVIDOR ACCION=RESPUESTA_RECIBIDA"
    set msg "${msg} CLIENTE_IP=${req_src} HOST=${req_host}"
    set msg "${msg} METHOD=${req_method} URI=${req_uri}"
    set msg "${msg} VS=[virtual name] POOL=${pool_name} SERVIDOR=${member_ip}:${member_port}"
    set msg "${msg} CODIGO_HTTP=${status} CONTENT_LENGTH=${content_len}"
    set msg "${msg} CONTENT_TYPE=\"${content_type}\""
    set msg "${msg} SERVIDOR_HEADER=\"${server_hdr}\" LOCATION=\"${location}\""
    log local0.info $msg

    if { [string range $status 0 0] eq "5" } {
        set alert "\[http_5xx_alert\] ACTOR=SERVIDOR ACCION=ERROR_5XX_DETECTADO"
        set alert "${alert} VS=[virtual name] SERVIDOR=${member_ip}:${member_port}"
        set alert "${alert} CODIGO_HTTP=${status} URI=${req_uri} CLIENTE_IP=${req_src}"
        set alert "${alert} DETALLE=El servidor respondio con error ${status}."
        set alert "${alert} Este error fue generado por el backend, no por BIG-IP."
        log local0.warning $alert
    }
}
