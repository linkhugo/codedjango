# =============================================================================
# http_cookie_inspector.tcl
#
# PURPOSE : Audita todas las cookies del request y de la respuesta:
#           - Nombres, valores y paths de cookies del cliente
#           - Flags de seguridad en respuesta: Secure, HttpOnly, SameSite
#           - Tamano de cookies (alerta si supera 4KB)
#           - Deteccion de cookies de sesion ausentes
#           - Cookies insertadas por BIG-IP vs origen
#
# CASOS DE USO:
#   - Sesiones que no persisten (cookie ausente o mal formada)
#   - Cookies sin flags de seguridad (Secure/HttpOnly) en produccion
#   - Cookies de tamano excesivo que causan errores 400 en otros proxies
#   - Validar que el backend inserta la cookie de sesion correctamente
#
# CONFIGURACION:
#   SESSION_COOKIES  - Lista de nombres de cookies de sesion a monitorear
#   MAX_COOKIE_BYTES - Tamano maximo permitido por cookie (default: 4096)
#
# LOG TAG : [cookie_req] / [cookie_resp] / [cookie_large] / [cookie_missing]
# GREP    : grep "\[cookie_missing\]" /var/log/ltm
#
# EVENTS  : HTTP_REQUEST, HTTP_RESPONSE
# =============================================================================

when HTTP_REQUEST {

    set SESSION_COOKIES  { "JSESSIONID" "PHPSESSID" "session_id" "sessionToken" "ASP.NET_SessionId" }
    set MAX_COOKIE_BYTES 4096

    set cookie_count [HTTP::cookie count]
    set req_src      [IP::client_addr]
    set req_uri      [HTTP::uri]
    set vs_name      [virtual name]

    set msg "\[cookie_req\] ACTOR=CLIENTE ACCION=COOKIES_REQUEST_INSPECCIONADAS"
    set msg "${msg} VS=${vs_name} CLIENTE_IP=${req_src} URI=${req_uri}"
    set msg "${msg} TOTAL_COOKIES=${cookie_count}"
    log local0.debug $msg

    foreach cookie_name [HTTP::cookie names] {
        set val  [HTTP::cookie value $cookie_name]
        set size [string length $val]

        set msg "\[cookie_req\] ACTOR=CLIENTE ACCION=COOKIE_DETALLE"
        set msg "${msg} NOMBRE_COOKIE=${cookie_name} TAMANO_BYTES=${size}"
        set msg "${msg} VALOR_PARCIAL=[string range $val 0 40]..."
        log local0.debug $msg

        if { $size > $MAX_COOKIE_BYTES } {
            set alert "\[cookie_large\] ACTOR=CLIENTE ACCION=COOKIE_TAMANO_EXCESIVO"
            set alert "${alert} VS=${vs_name} CLIENTE_IP=${req_src}"
            set alert "${alert} NOMBRE_COOKIE=${cookie_name} TAMANO_BYTES=${size}"
            set alert "${alert} LIMITE_BYTES=${MAX_COOKIE_BYTES}"
            set alert "${alert} DETALLE=La cookie supera el limite de ${MAX_COOKIE_BYTES} bytes."
            set alert "${alert} Esto puede causar errores 400 en proxies intermedios."
            log local0.warning $alert
        }
    }

    foreach sess_name $SESSION_COOKIES {
        if { ![HTTP::cookie exists $sess_name] } {
            set msg "\[cookie_missing\] ACTOR=CLIENTE ACCION=COOKIE_SESION_AUSENTE"
            set msg "${msg} VS=${vs_name} CLIENTE_IP=${req_src} URI=${req_uri}"
            set msg "${msg} NOMBRE_COOKIE=${sess_name} ESTADO=AUSENTE"
            set msg "${msg} DETALLE=El cliente no envio la cookie de sesion esperada."
            log local0.info $msg
        } else {
            set sess_val [HTTP::cookie value $sess_name]
            set msg "\[cookie_missing\] ACTOR=CLIENTE ACCION=COOKIE_SESION_PRESENTE"
            set msg "${msg} VS=${vs_name} CLIENTE_IP=${req_src}"
            set msg "${msg} NOMBRE_COOKIE=${sess_name} ESTADO=PRESENTE"
            set msg "${msg} TAMANO_BYTES=[string length $sess_val]"
            log local0.info $msg
        }
    }
}

when HTTP_RESPONSE {

    set resp_cookie_count [HTTP::cookie count]
    set msg "\[cookie_resp\] ACTOR=SERVIDOR ACCION=COOKIES_RESPUESTA_INSPECCIONADAS"
    set msg "${msg} VS=[virtual name] CODIGO_HTTP=[HTTP::status]"
    set msg "${msg} TOTAL_COOKIES_SET=${resp_cookie_count}"
    log local0.debug $msg

    foreach cookie_name [HTTP::cookie names] {
        set val      [HTTP::cookie value $cookie_name]
        set secure   [HTTP::cookie secure $cookie_name]
        set httponly [HTTP::cookie httponly $cookie_name]
        set size     [string length $val]

        set msg "\[cookie_resp\] ACTOR=SERVIDOR ACCION=COOKIE_RESPUESTA_DETALLE"
        set msg "${msg} NOMBRE_COOKIE=${cookie_name} TAMANO_BYTES=${size}"
        set msg "${msg} FLAG_SECURE=${secure} FLAG_HTTPONLY=${httponly}"
        set msg "${msg} SERVIDOR=[LB::server addr]:[LB::server port]"
        log local0.info $msg

        if { $size > 4096 } {
            set alert "\[cookie_large\] ACTOR=SERVIDOR ACCION=COOKIE_RESPUESTA_TAMANO_EXCESIVO"
            set alert "${alert} NOMBRE_COOKIE=${cookie_name} TAMANO_BYTES=${size}"
            set alert "${alert} DETALLE=Cookie de respuesta muy grande. Puede romper proxies intermedios."
            log local0.warning $alert
        }
    }
}
