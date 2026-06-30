# =============================================================================
# datagroup_lookup_debugger.tcl
#
# PURPOSE : Diagnostica problemas con DataGroups (class match / class lookup):
#           - Verifica en RULE_INIT que los DataGroups necesarios existen
#           - Loguea cada operacion de lookup con la clave buscada y el resultado
#           - Detecta no-match inesperados (la clave deberia estar pero no esta)
#           - Muestra si el problema es case-sensitivity
#           - Template para routing basado en DataGroup con trace completo
#
# CASOS DE USO:
#   - "class match" que nunca hace match aunque la clave esta en el DataGroup
#   - Routing a pool incorrecto por fallo silencioso de lookup
#   - Validar que un DataGroup se cargo correctamente despues de un cambio
#   - Debugging de DataGroups con valores tipo "host -> pool"
#
# CONFIGURACION:
#   DG_NAME     - Nombre del DataGroup a usar para routing (actualizar)
#   TRACE_MODE  - 1 = log de todos los lookups; 0 = solo no-matches
#
# LOG TAG : [dg_init] / [dg_match] / [dg_nomatch] / [dg_missing]
# GREP    : grep "\[dg_nomatch\]" /var/log/ltm
#
# EVENTS  : RULE_INIT, HTTP_REQUEST
# =============================================================================

when RULE_INIT {

    set static::DG_NAME    "mi_datagroup"
    set static::TRACE_MODE 1

    if { [class exists $static::DG_NAME] } {
        set msg "\[dg_init\] ACTOR=BIGIP ACCION=DATAGROUP_CARGADO_OK"
        set msg "${msg} DATAGROUP=\"${static::DG_NAME}\""
        set msg "${msg} DETALLE=El DataGroup existe y esta disponible para consultas."
        log local0.info $msg
    } else {
        set msg "\[dg_missing\] ACTOR=BIGIP ACCION=DATAGROUP_NO_ENCONTRADO"
        set msg "${msg} DATAGROUP=\"${static::DG_NAME}\""
        set msg "${msg} DETALLE=El DataGroup no existe en la configuracion del BIG-IP."
        set msg "${msg} Verificar nombre y que fue creado correctamente."
        log local0.err $msg
    }
}

when HTTP_REQUEST {

    set req_host   [HTTP::host]
    set req_uri    [HTTP::uri]
    set req_src    [IP::client_addr]
    set vs_name    [virtual name]

    set lookup_key [string tolower $req_host]

    if { $static::TRACE_MODE } {
        set msg "\[dg_match\] ACTOR=BIGIP ACCION=BUSCANDO_EN_DATAGROUP"
        set msg "${msg} VS=${vs_name} CLIENTE_IP=${req_src}"
        set msg "${msg} DATAGROUP=${static::DG_NAME} CLAVE_BUSCADA=\"${lookup_key}\""
        log local0.debug $msg
    }

    if { [class exists $static::DG_NAME] } {

        if { [class match $lookup_key equals $static::DG_NAME] } {
            set target_value [class lookup $lookup_key $static::DG_NAME]
            set msg "\[dg_match\] ACTOR=BIGIP ACCION=COINCIDENCIA_ENCONTRADA"
            set msg "${msg} VS=${vs_name} CLIENTE_IP=${req_src}"
            set msg "${msg} CLAVE=\"${lookup_key}\""
            set msg "${msg} DATAGROUP=${static::DG_NAME} VALOR_ENCONTRADO=\"${target_value}\""
            set msg "${msg} RESULTADO=COINCIDE"
            log local0.info $msg

        } elseif { [class match $req_host equals $static::DG_NAME] } {
            set target_value [class lookup $req_host $static::DG_NAME]
            set msg "\[dg_match\] ACTOR=BIGIP ACCION=COINCIDENCIA_SENSIBLE_A_MAYUSCULAS"
            set msg "${msg} VS=${vs_name} CLIENTE_IP=${req_src}"
            set msg "${msg} CLAVE_ORIGINAL=\"${req_host}\""
            set msg "${msg} DATAGROUP=${static::DG_NAME} VALOR_ENCONTRADO=\"${target_value}\""
            set msg "${msg} RESULTADO=COINCIDE_SOLO_CON_MAYUSCULAS"
            set msg "${msg} DETALLE=La clave coincide solo si se respetan mayusculas/minusculas."
            set msg "${msg} Verificar que el DataGroup y la clave usan el mismo formato de capitalización."
            log local0.warning $msg

        } else {
            set msg "\[dg_nomatch\] ACTOR=BIGIP ACCION=SIN_COINCIDENCIA_EN_DATAGROUP"
            set msg "${msg} VS=${vs_name} CLIENTE_IP=${req_src}"
            set msg "${msg} CLAVE=\"${lookup_key}\""
            set msg "${msg} DATAGROUP=${static::DG_NAME} URI=${req_uri}"
            set msg "${msg} RESULTADO=NO_COINCIDE"
            set msg "${msg} DETALLE=La clave no fue encontrada en el DataGroup."
            set msg "${msg} Verificar que la entrada existe con el mismo valor exacto."
            log local0.info $msg
        }

    } else {
        set msg "\[dg_missing\] ACTOR=BIGIP ACCION=DATAGROUP_NO_DISPONIBLE_EN_REQUEST"
        set msg "${msg} VS=${vs_name}"
        set msg "${msg} DATAGROUP=\"${static::DG_NAME}\""
        set msg "${msg} DETALLE=El DataGroup no fue encontrado al procesar el request."
        log local0.err $msg
    }
}
