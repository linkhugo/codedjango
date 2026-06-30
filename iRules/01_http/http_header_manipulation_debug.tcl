# =============================================================================
# http_header_manipulation_debug.tcl
#
# PURPOSE : Captura TODOS los headers del request y del response.
#           Util para comparar que headers llegan vs que headers salen,
#           depurar insercion/eliminacion de headers por HTTP profiles,
#           y validar X-Forwarded-For, X-Real-IP, y headers de app.
#
# SAMPLING: Para reducir volumen en VSes con mucho trafico, descomentar
#           el bloque de sampling (1 de cada 10 requests).
#
# LOG TAG : [hdr_debug_req] / [hdr_debug_resp]
# GREP    : grep "\[hdr_debug_req\]" /var/log/ltm
#
# EVENTS  : HTTP_REQUEST, HTTP_RESPONSE
# =============================================================================

when HTTP_REQUEST {

    # Sampling 1-in-10 para reducir volumen (descomentar para activar)
    # if { [expr { int(rand() * 10) }] != 0 } { return }

    set req_id  "[IP::client_addr]:[TCP::client_port]:[clock clicks]"
    set req_uri [HTTP::uri]
    set src_ip  [IP::client_addr]

    set req_header_list ""
    foreach header_name [HTTP::header names] {
        set req_header_list "${req_header_list}${header_name}=[HTTP::header value $header_name] | "
    }

    set msg "\[hdr_debug_req\] ACTOR=CLIENTE ACCION=HEADERS_REQUEST_CAPTURADOS"
    set msg "${msg} CORRELATION_ID=${req_id} CLIENTE_IP=${src_ip} URI=${req_uri}"
    set msg "${msg} HEADERS=\[${req_header_list}\]"
    log local0.info $msg

    set hdr_req_id $req_id
}

when HTTP_RESPONSE {

    set resp_header_list ""
    foreach header_name [HTTP::header names] {
        set resp_header_list "${resp_header_list}${header_name}=[HTTP::header value $header_name] | "
    }

    set msg "\[hdr_debug_resp\] ACTOR=SERVIDOR ACCION=HEADERS_RESPUESTA_CAPTURADOS"
    set msg "${msg} CORRELATION_ID=${hdr_req_id} CODIGO_HTTP=[HTTP::status]"
    set msg "${msg} SERVIDOR=[LB::server addr]:[LB::server port]"
    set msg "${msg} HEADERS=\[${resp_header_list}\]"
    log local0.info $msg
}
