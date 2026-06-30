# =============================================================================
# http_request_logger.tcl
#
# PURPOSE : Logs complete HTTP request details for troubleshooting.
#           Captures method, URI, Host, X-Forwarded-For, User-Agent,
#           Content-Type and a custom correlation header.
#
# USAGE   : Attach to a Virtual Server temporarily during an incident.
#           Remove after troubleshooting - alto volumen de logs.
#
# LOG TAG : [http_req_log]
# GREP    : grep "\[http_req_log\]" /var/log/ltm
#
# EVENTS  : HTTP_REQUEST
# =============================================================================

when HTTP_REQUEST {

    set src_ip        [IP::client_addr]
    set src_port      [TCP::client_port]
    set dst_ip        [IP::local_addr]
    set dst_port      [TCP::local_port]
    set method        [HTTP::method]
    set uri           [HTTP::uri]
    set host          [HTTP::host]
    set user_agent    [HTTP::header "User-Agent"]
    set xff           [HTTP::header "X-Forwarded-For"]
    set content_type  [HTTP::header "Content-Type"]
    set correlation   [HTTP::header "X-Correlation-ID"]

    set msg "\[http_req_log\] ACTOR=CLIENTE ACCION=REQUEST_RECIBIDO"
    set msg "${msg} CLIENTE_IP=${src_ip} PUERTO_CLIENTE=${src_port}"
    set msg "${msg} VS=[virtual name] DESTINO=${dst_ip}:${dst_port}"
    set msg "${msg} METHOD=${method} HOST=${host} URI=${uri}"
    set msg "${msg} NAVEGADOR=\"${user_agent}\" X_FORWARDED_FOR=${xff}"
    set msg "${msg} CONTENT_TYPE=${content_type} CORRELATION_ID=${correlation}"
    log local0.info $msg
}
