# =============================================================================
# geo_ip_logger.tcl
#
# PURPOSE : Loguea informacion geografica de cada cliente usando el comando
#           F5 `whereis`. Permite identificar trafico de paises inesperados
#           y bloquear regiones configurables.
#
#           Datos capturados por conexion:
#           - Continente, pais, region, ciudad
#           - ISP / organizacion
#           - Coordenadas (latitud/longitud)
#
# CASOS DE USO:
#   - Detectar trafico de paises no esperados (baseline geografico)
#   - Alertar o bloquear acceso desde paises en lista de restriccion
#   - Correlacionar incidentes de seguridad con origen geografico
#   - Validar que el Geo-IP database de BIG-IP esta actualizado
#
# CONFIGURACION:
#   BLOCKED_COUNTRIES - Lista de codigos ISO 3166-1 alpha-2 de paises bloqueados
#   ACTION_MODE       - "log" (solo registrar) o "block" (rechazar conexion)
#
# REQUIERE: BIG-IP con Geo-IP database cargada (IP Intelligence o IP Geolocation)
#
# LOG TAG : [geo_info] / [geo_block]
# GREP    : grep "\[geo_block\]" /var/log/ltm
#
# EVENTS  : CLIENT_ACCEPTED
# =============================================================================

when CLIENT_ACCEPTED {

    set BLOCKED_COUNTRIES { "XX" "YY" }
    set ACTION_MODE       "log"

    set client_ip [IP::client_addr]
    set vs_name   [virtual name]

    set continent [whereis $client_ip continent]
    set country   [whereis $client_ip country]
    set region    [whereis $client_ip region]
    set city      [whereis $client_ip city]
    set isp       [whereis $client_ip isp]

    set msg "\[geo_info\] ACTOR=CLIENTE ACCION=ORIGEN_GEOGRAFICO_REGISTRADO"
    set msg "${msg} VS=${vs_name} CLIENTE_IP=${client_ip}"
    set msg "${msg} CONTINENTE=${continent} PAIS=${country}"
    set msg "${msg} REGION=${region} CIUDAD=${city} ISP=\"${isp}\""
    log local0.info $msg

    if { [lsearch -exact $BLOCKED_COUNTRIES $country] >= 0 } {
        set alert "\[geo_block\] ACTOR=BIGIP ACCION=PAIS_BLOQUEADO_DETECTADO"
        set alert "${alert} VS=${vs_name} CLIENTE_IP=${client_ip}"
        set alert "${alert} PAIS=${country} CIUDAD=${city} MODO=${ACTION_MODE}"
        set alert "${alert} DETALLE=La conexion proviene de un pais en la lista de bloqueo (${country})."
        log local0.warning $alert

        if { $ACTION_MODE eq "block" } {
            drop
            return
        }
    }
}
