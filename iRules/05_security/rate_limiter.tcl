# =============================================================================
# rate_limiter.tcl
#
# PURPOSE : Rate limiting por IP de origen usando el comando table de BIG-IP.
#           Cuenta requests por IP dentro de una ventana deslizante.
#           Dos niveles de accion:
#             WARN  : Log de advertencia (primera deteccion)
#             BLOCK : Responde 429 Too Many Requests (sostenido)
#
# CONFIGURACION (editar estas variables para ajustar sin tocar la logica):
#   RATE_WINDOW_SECS  - Duracion de la ventana deslizante (default: 60s)
#   RATE_WARN_LIMIT   - Threshold de warning (default: 100 req/ventana)
#   RATE_BLOCK_LIMIT  - Threshold de bloqueo (default: 200 req/ventana)
#   RATE_BLOCK_PERIOD - Duracion del bloqueo en segundos (default: 300s)
#
# NOTA    : El comando table es TMM-local por blade. En chassis multi-blade,
#           los contadores no se sincronizan entre blades (comportamiento normal).
#
# LOG TAG : [rate_warn] / [rate_block]
# GREP    : grep "\[rate_block\]" /var/log/ltm
#
# EVENTS  : HTTP_REQUEST
# =============================================================================

when HTTP_REQUEST {

    set RATE_WINDOW_SECS  60
    set RATE_WARN_LIMIT   100
    set RATE_BLOCK_LIMIT  200
    set RATE_BLOCK_PERIOD 300

    set client_ip [IP::client_addr]
    set req_uri   [HTTP::uri]
    set vs_name   [virtual name]

    set block_key "block::${client_ip}"
    if { [table lookup -subtable "rate_limit" $block_key] ne "" } {
        set ttl [table lifetime -subtable "rate_limit" $block_key]
        set msg "\[rate_block\] ACTOR=BIGIP ACCION=IP_BLOQUEADA_429"
        set msg "${msg} VS=${vs_name} CLIENTE_IP=${client_ip} URI=${req_uri}"
        set msg "${msg} SEGUNDOS_RESTANTES_BLOQUEO=${ttl}"
        set msg "${msg} DETALLE=La IP esta bloqueada por exceder el limite de requests."
        log local0.warning $msg
        HTTP::respond 429 content "Too Many Requests" "Content-Type" "text/plain" "Retry-After" $RATE_BLOCK_PERIOD "X-RateLimit-Limit" $RATE_BLOCK_LIMIT
        return
    }

    set count_key     "count::${client_ip}"
    set current_count [table incr -subtable "rate_limit" $count_key]
    if { $current_count == 1 } {
        table timeout -subtable "rate_limit" $count_key $RATE_WINDOW_SECS
    }

    if { $current_count >= $RATE_BLOCK_LIMIT } {
        table set -subtable "rate_limit" $block_key "1" $RATE_BLOCK_PERIOD
        set alert "\[rate_block\] ACTOR=BIGIP ACCION=IP_BLOQUEADA_AHORA"
        set alert "${alert} VS=${vs_name} CLIENTE_IP=${client_ip}"
        set alert "${alert} REQUESTS_EN_VENTANA=${current_count}"
        set alert "${alert} VENTANA_SEGUNDOS=${RATE_WINDOW_SECS}"
        set alert "${alert} DURACION_BLOQUEO_S=${RATE_BLOCK_PERIOD}"
        set alert "${alert} DETALLE=La IP supero el limite de ${RATE_BLOCK_LIMIT} requests."
        set alert "${alert} BIG-IP aplicara bloqueo por ${RATE_BLOCK_PERIOD} segundos."
        log local0.err $alert
        HTTP::respond 429 content "Too Many Requests - IP Blocked" "Content-Type" "text/plain" "Retry-After" $RATE_BLOCK_PERIOD
        return
    } elseif { $current_count >= $RATE_WARN_LIMIT } {
        set warn "\[rate_warn\] ACTOR=CLIENTE ACCION=TASA_ALTA_DETECTADA"
        set warn "${warn} VS=${vs_name} CLIENTE_IP=${client_ip}"
        set warn "${warn} REQUESTS_EN_VENTANA=${current_count}"
        set warn "${warn} LIMITE_ADVERTENCIA=${RATE_WARN_LIMIT} LIMITE_BLOQUEO=${RATE_BLOCK_LIMIT}"
        set warn "${warn} URI=${req_uri}"
        set warn "${warn} DETALLE=La IP se acerca al limite de bloqueo."
        set warn "${warn} Si supera ${RATE_BLOCK_LIMIT} requests sera bloqueada automaticamente."
        log local0.warning $warn
    }

    HTTP::header insert "X-RateLimit-Limit"     $RATE_BLOCK_LIMIT
    HTTP::header insert "X-RateLimit-Remaining" [expr { $RATE_BLOCK_LIMIT - $current_count }]
    HTTP::header insert "X-RateLimit-Window"    "${RATE_WINDOW_SECS}s"
}
