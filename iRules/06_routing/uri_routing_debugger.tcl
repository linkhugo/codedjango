# =============================================================================
# uri_routing_debugger.tcl
#
# PURPOSE : Content switching basado en URI con trace log completo de cada
#           condicion evaluada. Sirve como template de referencia y como
#           herramienta de debug para entender que regla se ejecuto y por que.
#
# POOLS REFERENCIADOS (actualizar con los nombres reales del BIG-IP):
#   pool_health   - Endpoints de health check
#   pool_api_v2   - API v2
#   pool_api      - API v1 / generica
#   pool_static   - Assets estaticos / CDN origin
#   pool_legacy   - Paths legacy
#   pool_default  - Pool principal de la aplicacion
#
# TRACE_MODE:
#   1 - Loguea cada condicion evaluada (maximo detalle para debug)
#   0 - Solo loguea la regla que coincidio
#
# LOG TAG : [uri_route_trace] / [uri_route]
# GREP    : grep "\[uri_route\]" /var/log/ltm | awk '{print $8}' | sort | uniq -c
#
# NOTA    : La linea "pool $target_pool" esta comentada.
#           Descomentarla cuando el iRule este listo para enrutar de verdad.
#
# EVENTS  : HTTP_REQUEST
# =============================================================================

when HTTP_REQUEST {

    set TRACE_MODE 1

    set client_ip  [IP::client_addr]
    set req_uri    [HTTP::uri]
    set req_host   [HTTP::host]
    set req_method [HTTP::method]
    set vs_name    [virtual name]
    set uri_path   [getfield $req_uri "?" 1]

    if { $TRACE_MODE } {
        set msg "\[uri_route_trace\] ACTOR=BIGIP ACCION=EVALUANDO_REGLAS_DE_RUTA"
        set msg "${msg} VS=${vs_name} CLIENTE_IP=${client_ip}"
        set msg "${msg} METHOD=${req_method} HOST=${req_host} PATH=${uri_path}"
        log local0.debug $msg
    }

    if { [string match "/health*" $uri_path] || $uri_path eq "/ping" } {
        set matched_rule "R1_HEALTH"
        set target_pool  "pool_health"
        if { $TRACE_MODE } {
            log local0.debug "\[uri_route_trace\] ACTOR=BIGIP ACCION=REGLA_R1_COINCIDIO REGLA=health_endpoint PATH=${uri_path}"
        }

    } elseif { [string match "/api/v2/*" $uri_path] } {
        set matched_rule "R2_API_V2"
        set target_pool  "pool_api_v2"
        if { $TRACE_MODE } {
            log local0.debug "\[uri_route_trace\] ACTOR=BIGIP ACCION=REGLA_R2_COINCIDIO REGLA=api_v2_prefix PATH=${uri_path}"
        }

    } elseif { [string match "/api/*" $uri_path] } {
        set matched_rule "R3_API_V1"
        set target_pool  "pool_api"
        if { $TRACE_MODE } {
            log local0.debug "\[uri_route_trace\] ACTOR=BIGIP ACCION=REGLA_R3_COINCIDIO REGLA=api_generica PATH=${uri_path}"
        }

    } elseif { [string match "*.css" $uri_path] || [string match "*.js" $uri_path] || [string match "*.png" $uri_path] || [string match "*.jpg" $uri_path] || [string match "*.woff*" $uri_path] || [string match "/static/*" $uri_path] } {
        set matched_rule "R4_STATIC"
        set target_pool  "pool_static"
        if { $TRACE_MODE } {
            log local0.debug "\[uri_route_trace\] ACTOR=BIGIP ACCION=REGLA_R4_COINCIDIO REGLA=recurso_estatico PATH=${uri_path}"
        }

    } elseif { [string match "/legacy/*" $uri_path] || [string match "/old/*" $uri_path] } {
        set matched_rule "R5_LEGACY"
        set target_pool  "pool_legacy"
        if { $TRACE_MODE } {
            log local0.debug "\[uri_route_trace\] ACTOR=BIGIP ACCION=REGLA_R5_COINCIDIO REGLA=path_legacy PATH=${uri_path}"
        }

    } else {
        set matched_rule "DEFECTO"
        set target_pool  "pool_default"
        if { $TRACE_MODE } {
            log local0.debug "\[uri_route_trace\] ACTOR=BIGIP ACCION=NINGUNA_REGLA_COINCIDIO RUTA=pool_defecto PATH=${uri_path}"
        }
    }

    set msg "\[uri_route\] ACTOR=BIGIP ACCION=RUTA_SELECCIONADA"
    set msg "${msg} VS=${vs_name} CLIENTE_IP=${client_ip} HOST=${req_host} URI=${req_uri}"
    set msg "${msg} REGLA_APLICADA=${matched_rule} POOL_DESTINO=${target_pool}"
    log local0.info $msg

    # Descomenter para activar el routing real:
    # pool $target_pool
}
