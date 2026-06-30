# =============================================================================
# http_compression_debug.tcl
#
# PURPOSE : Diagnostica problemas de compresion y encoding en HTTP:
#           - Compara Accept-Encoding del cliente vs Content-Encoding del server
#           - Detecta conflicto gzip + chunked (causa errores en algunos clientes)
#           - Detecta respuestas comprimidas doble (gzip sobre gzip)
#           - Alerta cuando el servidor envia gzip pero el cliente no lo acepto
#           - Registra Content-Length antes y despues de compresion
#
# CASOS DE USO:
#   - Clientes recibiendo datos corruptos o ilegibles (doble gzip)
#   - APIs que retornan errores 400/500 por encoding incorrecto
#   - Conflicto entre Transfer-Encoding: chunked y Content-Encoding: gzip
#   - Validar que el perfil de compresion de BIG-IP esta funcionando
#
# LOG TAG : [compress_req] / [compress_resp] / [compress_conflict]
# GREP    : grep "\[compress_conflict\]" /var/log/ltm
#
# EVENTS  : HTTP_REQUEST, HTTP_RESPONSE
# =============================================================================

when HTTP_REQUEST {

    set req_src        [IP::client_addr]
    set req_uri        [HTTP::uri]
    set vs_name        [virtual name]
    set accept_enc     [HTTP::header "Accept-Encoding"]
    set req_content_enc [HTTP::header "Content-Encoding"]

    set msg "\[compress_req\] ACTOR=CLIENTE ACCION=ENCODING_REQUEST_REGISTRADO"
    set msg "${msg} VS=${vs_name} CLIENTE_IP=${req_src} URI=${req_uri}"
    set msg "${msg} ACCEPT_ENCODING=\"${accept_enc}\""
    log local0.debug $msg

    if { $req_content_enc ne "" } {
        set msg "\[compress_req\] ACTOR=CLIENTE ACCION=REQUEST_CON_ENCODING"
        set msg "${msg} ENCODING_USADO=${req_content_enc} CLIENTE_IP=${req_src} URI=${req_uri}"
        set msg "${msg} DETALLE=El cliente envio el request con compresion activada."
        log local0.info $msg
    }
}

when HTTP_RESPONSE {

    set content_enc    [HTTP::header "Content-Encoding"]
    set transfer_enc   [HTTP::header "Transfer-Encoding"]
    set content_type   [HTTP::header "Content-Type"]
    set content_length [HTTP::header "Content-Length"]
    set status         [HTTP::status]
    set member         "[LB::server addr]:[LB::server port]"

    set msg "\[compress_resp\] ACTOR=SERVIDOR ACCION=ENCODING_RESPUESTA_REGISTRADO"
    set msg "${msg} VS=[virtual name] CODIGO_HTTP=${status} SERVIDOR=${member}"
    set msg "${msg} CONTENT_ENCODING=\"${content_enc}\" TRANSFER_ENCODING=\"${transfer_enc}\""
    set msg "${msg} CONTENT_TYPE=\"${content_type}\" CONTENT_LENGTH=${content_length}"
    log local0.info $msg

    if { ($content_enc eq "gzip" || $content_enc eq "deflate") && [string tolower $transfer_enc] eq "chunked" } {
        set alert "\[compress_conflict\] ACTOR=SERVIDOR ACCION=CONFLICTO_ENCODING_DETECTADO"
        set alert "${alert} VS=[virtual name] SERVIDOR=${member} URI=${req_uri}"
        set alert "${alert} CONFLICT=gzip+chunked"
        set alert "${alert} DETALLE=El servidor usa gzip Y chunked al mismo tiempo."
        set alert "${alert} Algunos clientes no pueden decodificar esta combinacion y mostraran errores."
        log local0.warning $alert
    }

    if { [string match "*gzip*" $content_enc] && [string match "*gzip*" $content_enc] } {
        set ce_lower [string tolower $content_enc]
        set gzip_count [llength [lsearch -all [split $ce_lower ","] "*gzip*"]]
        if { $gzip_count > 1 } {
            set alert "\[compress_conflict\] ACTOR=SERVIDOR ACCION=DOBLE_GZIP_DETECTADO"
            set alert "${alert} SERVIDOR=${member} URI=${req_uri}"
            set alert "${alert} DETALLE=La respuesta esta comprimida dos veces con gzip."
            set alert "${alert} El cliente recibira datos ilegibles."
            log local0.warning $alert
        }
    }

    if { $content_enc eq "gzip" && ![string match "*gzip*" $accept_enc] && ![string match "*\**" $accept_enc] } {
        set alert "\[compress_conflict\] ACTOR=SERVIDOR ACCION=GZIP_NO_ACEPTADO_POR_CLIENTE"
        set alert "${alert} VS=[virtual name] SERVIDOR=${member}"
        set alert "${alert} ACCEPT_ENCODING_CLIENTE=\"${accept_enc}\""
        set alert "${alert} DETALLE=El servidor envio gzip pero el cliente no declaro aceptar gzip."
        set alert "${alert} El cliente puede recibir datos corruptos o ilegibles."
        log local0.warning $alert
    }
}
