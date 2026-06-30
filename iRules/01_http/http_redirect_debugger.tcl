# =============================================================================
# http_redirect_debugger.tcl
#
# PURPOSE : Diagnostica redirecciones HTTP (301, 302, 303, 307, 308) logging
#           la cadena completa de redirects y detectando loops y anomalias.
#
#           PROBLEMAS QUE DETECTA:
#
#           REDIRECT_LOOP         El header Location apunta al mismo host+URI
#                                 que el request actual. El cliente entraria en
#                                 un loop infinito.
#                                 Causa tipica: VS que redirige HTTP->HTTPS pero
#                                 el perfil ClientSSL no esta bien configurado.
#
#           REDIRECT_WRONG_SCHEME El backend redirige a HTTP cuando el request
#                                 original llego por HTTPS (downgrade inseguro).
#
#           REDIRECT_EXTERNAL     Location apunta a un host diferente al del
#                                 request. Puede ser intencional o un error de
#                                 configuracion del backend.
#
#           REDIRECT_POST_TO_GET  302/303 en respuesta a un POST: el browser
#                                 convierte el POST en GET en el redirect.
#                                 Si se quiere preservar el metodo usar 307/308.
#
#           REDIRECT_CHAIN        Contador de redirects en la misma conexion
#                                 TCP. Mas de MAX_REDIRECTS indica posible loop
#                                 o configuracion incorrecta.
#
# CASOS DE USO:
#   - "Too many redirects" en el browser (loop HTTP<->HTTPS)
#   - Redirect a hostname incorrecto (app que hardcodea la URL de redirect)
#   - POST que llega como GET al destino final
#   - Validar que los redirects HTTP->HTTPS usan 301 y no 302
#
# CONFIGURACION:
#   MAX_REDIRECTS - Numero de redirects en la misma conexion antes de alertar
#
# LOG TAG : [redirect] / [redirect_loop] / [redirect_warn]
# GREP    : grep "\[redirect_loop\]" /var/log/ltm
#           grep "\[redirect_warn\]" /var/log/ltm
#
# EVENTS  : HTTP_REQUEST, HTTP_RESPONSE
# =============================================================================

when HTTP_REQUEST {

    set MAX_REDIRECTS 3

    set req_method  [HTTP::method]
    set req_uri     [HTTP::uri]
    set req_host    [HTTP::host]
    set req_src     [IP::client_addr]
    set vs_name     [virtual name]

    set req_scheme "http"
    if { [PROFILE::exists clientssl] } {
        set req_scheme "https"
    }

    if { ![info exists redirect_count] } {
        set redirect_count 0
    }
}

when HTTP_RESPONSE {

    set status [HTTP::status]
    set status_class [string range $status 0 0]

    if { $status_class ne "3" || $status eq "304" } {
        return
    }

    set location [HTTP::header "Location"]
    set member   "[LB::server addr]:[LB::server port]"

    incr redirect_count

    set msg "\[redirect\] ACTOR=SERVIDOR ACCION=REDIRECCION_DETECTADA"
    set msg "${msg} VS=${vs_name} CLIENTE_IP=${req_src} SERVIDOR=${member}"
    set msg "${msg} CODIGO_HTTP=${status} METHOD=${req_method}"
    set msg "${msg} URL_ORIGEN=\"${req_scheme}://${req_host}${req_uri}\""
    set msg "${msg} URL_DESTINO=\"${location}\" NUMERO_REDIRECT=${redirect_count}"
    log local0.info $msg

    # -- Detectar loop: Location apunta al mismo host+URI ----------------
    set loc_lower [string tolower $location]
    set req_lower [string tolower "${req_host}${req_uri}"]

    if { [string match "*${req_lower}*" $loc_lower] } {
        set alert "\[redirect_loop\] ACTOR=SERVIDOR ACCION=LOOP_DE_REDIRECCION_DETECTADO"
        set alert "${alert} VS=${vs_name} CLIENTE_IP=${req_src} CODIGO_HTTP=${status}"
        set alert "${alert} URL_ACTUAL=\"${req_scheme}://${req_host}${req_uri}\""
        set alert "${alert} URL_DESTINO=\"${location}\""
        set alert "${alert} DETALLE=El servidor redirige a la misma URL del request."
        set alert "${alert} El cliente entrara en loop infinito. Revisar configuracion del servidor o del VS."
        log local0.err $alert
    }

    # -- Detectar downgrade HTTPS -> HTTP --------------------------------
    if { $req_scheme eq "https" && [string match "http://*" $loc_lower] && ![string match "https://*" $loc_lower] } {
        set warn "\[redirect_warn\] ACTOR=SERVIDOR ACCION=DOWNGRADE_HTTPS_A_HTTP"
        set warn "${warn} VS=${vs_name} CLIENTE_IP=${req_src}"
        set warn "${warn} URL_ORIGEN=\"https://${req_host}${req_uri}\" URL_DESTINO=\"${location}\""
        set warn "${warn} DETALLE=El servidor redirige de HTTPS a HTTP inseguro."
        set warn "${warn} Los datos del cliente viajaran sin cifrado en el proximo request."
        log local0.warning $warn
    }

    # -- Detectar redirect a host externo --------------------------------
    if { $location ne "" && ![string match "*${req_host}*" $location] && [string match "http*" $location] } {
        set warn "\[redirect_warn\] ACTOR=SERVIDOR ACCION=REDIRECCION_A_HOST_EXTERNO"
        set warn "${warn} VS=${vs_name} CLIENTE_IP=${req_src}"
        set warn "${warn} HOST_ORIGINAL=${req_host} URL_DESTINO=\"${location}\""
        set warn "${warn} DETALLE=El servidor redirige a un host diferente al original."
        log local0.warning $warn
    }

    # -- Detectar POST -> GET en 302/303 ---------------------------------
    if { ($status eq "302" || $status eq "303") && $req_method eq "POST" } {
        set warn "\[redirect_warn\] ACTOR=SERVIDOR ACCION=POST_CONVERTIDO_A_GET"
        set warn "${warn} VS=${vs_name} CLIENTE_IP=${req_src}"
        set warn "${warn} CODIGO_HTTP=${status} URL_DESTINO=\"${location}\""
        set warn "${warn} DETALLE=Con ${status}, el browser convierte el POST en GET al redirigir."
        set warn "${warn} Si se necesita preservar el POST usar 307 o 308 en lugar de ${status}."
        log local0.warning $warn
    }

    # -- Alertar si se superan los redirects maximos en la misma conexion
    if { $redirect_count >= $MAX_REDIRECTS } {
        set alert "\[redirect_warn\] ACTOR=SERVIDOR ACCION=CADENA_DE_REDIRECTS_EXCESIVA"
        set alert "${alert} VS=${vs_name} CLIENTE_IP=${req_src}"
        set alert "${alert} TOTAL_REDIRECTS=${redirect_count} MAXIMO_CONFIGURADO=${MAX_REDIRECTS}"
        set alert "${alert} ULTIMA_URL=\"${location}\""
        set alert "${alert} DETALLE=Se detectaron ${redirect_count} redirects en la misma conexion."
        set alert "${alert} Posible loop de redireccion o configuracion incorrecta del servidor."
        log local0.err $alert
    }
}
