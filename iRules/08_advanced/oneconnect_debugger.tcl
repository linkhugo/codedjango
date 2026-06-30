# =============================================================================
# oneconnect_debugger.tcl
#
# PURPOSE : Diagnostica el comportamiento del perfil OneConnect en BIG-IP.
#
#           QUE ES ONECONNECT:
#           OneConnect es un perfil de F5 que multiplexa multiples conexiones
#           HTTP de clientes sobre un numero menor de conexiones TCP hacia el
#           backend. En lugar de abrir una conexion TCP por cada request HTTP,
#           BIG-IP reutiliza conexiones TCP existentes hacia el servidor.
#
#           SIN ONECONNECT:              CON ONECONNECT:
#           Cliente1 -> TCP1 -> Server   Cliente1 ---|
#           Cliente2 -> TCP2 -> Server   Cliente2 ---+--> TCP1 (reusado) -> Server
#           Cliente3 -> TCP3 -> Server   Cliente3 ---|
#
#           IMPACTO EN IRULES - TRAMPA COMUN:
#           Cuando OneConnect esta activo:
#
#           1. SERVER_CONNECTED NO dispara para cada HTTP request.
#              Solo dispara cuando se abre una conexion TCP nueva al backend.
#              Si el request reutiliza una conexion TCP existente, SERVER_CONNECTED
#              NO ocurre. iRules que dependan de SERVER_CONNECTED para inicializar
#              variables fallaran silenciosamente.
#
#           2. Variables de conexion persisten entre requests del MISMO cliente.
#              Una variable set en HTTP_REQUEST del request #1 sigue existiendo
#              en HTTP_REQUEST del request #2 si vienen por la misma conexion TCP
#              del cliente. Esto puede causar que datos de un request "contaminen"
#              el siguiente.
#
#           3. LB_SELECTED puede no elegir un nuevo member.
#              BIG-IP puede reutilizar la conexion TCP existente sin pasar por
#              la logica de LB de nuevo, dependiendo de la configuracion.
#
#           LO QUE ESTE IRULE DETECTA:
#
#           CAMPO                  DESCRIPCION
#           ----------------       -------------------------------------------------
#           NUM_REQUEST_CLIENTE    Numero de request HTTP en esta conexion TCP cliente.
#                                  Si es > 1, el cliente esta usando keepalive.
#
#           VECES_SERVIDOR_CONECTADO Cuantas veces SERVER_CONNECTED disparo para esta
#                                  conexion cliente. Si NUM_REQUEST_CLIENTE >
#                                  VECES_SERVIDOR_CONECTADO, OneConnect esta
#                                  reutilizando conexiones al backend.
#
#           ONECONNECT_REUSO       SI si este request va por una conexion TCP al
#                                  backend ya existente (SERVER_CONNECTED no disparo).
#                                  NO si se abrio una conexion TCP nueva al backend.
#
#           ID_CONEXION_SERVIDOR   IP:puerto de la conexion backend siendo usada.
#                                  Si el mismo ID aparece en varios requests
#                                  de diferentes clientes, OneConnect multiplexando.
#
#           CONTAMINACION_VARIABLE Detectado cuando una variable de request anterior
#                                  NO fue reinicializada y tiene un valor residual.
#
# CASOS DE USO:
#   - Confirmar si OneConnect esta activo en un VS
#   - Diagnosticar iRules que se comportan diferente con/sin OneConnect
#   - Detectar variables contaminadas entre requests
#   - Ver el ratio de reutilizacion de conexiones backend
#   - Entender por que SERVER_CONNECTED no dispara en algunos requests
#
# LOG TAG : [oc_request] / [oc_server] / [oc_warn]
# GREP    : grep "\[oc_request\]" /var/log/ltm | grep "ONECONNECT_REUSO=SI"
#           grep "\[oc_warn\]" /var/log/ltm
#
# EVENTS  : CLIENT_ACCEPTED, SERVER_CONNECTED, HTTP_REQUEST, HTTP_RESPONSE
# =============================================================================

when CLIENT_ACCEPTED {
    set client_conn_id  "[IP::client_addr]:[TCP::client_port]:[clock clicks]"
    set client_req_num  0
    set srv_conn_count  0
    set srv_conn_id     ""
    set last_req_method ""
    set last_req_uri    ""
}

when SERVER_CONNECTED {
    incr srv_conn_count
    set srv_conn_id "[IP::server_addr]:[TCP::server_port]"

    set msg "\[oc_server\] ACTOR=BIGIP ACCION=NUEVA_CONEXION_AL_SERVIDOR"
    set msg "${msg} CONEXION_CLIENTE=${client_conn_id} VS=[virtual name]"
    set msg "${msg} VECES_SERVIDOR_CONECTADO=${srv_conn_count}"
    set msg "${msg} ID_CONEXION_SERVIDOR=${srv_conn_id} POOL=[LB::server pool]"
    log local0.debug $msg
}

when HTTP_REQUEST {
    incr client_req_num

    set req_method [HTTP::method]
    set req_uri    [HTTP::uri]
    set req_host   [HTTP::host]
    set vs_name    [virtual name]
    set src_ip     [IP::client_addr]

    # Si el numero de requests supera el numero de veces que SERVER_CONNECTED
    # disparo, OneConnect esta reutilizando la conexion TCP al backend.
    if { $client_req_num > $srv_conn_count } {
        set oc_reuse "SI"
    } else {
        set oc_reuse "NO"
    }

    # Detectar posible contaminacion de variables del request anterior.
    # Si last_req_uri no esta vacio en el request #2+, significa que la variable
    # persistio desde el request anterior (comportamiento normal en keepalive/OC,
    # pero puede causar bugs si el desarrollador no lo sabe).
    set contamination_warn ""
    if { $client_req_num > 1 && $last_req_uri ne "" } {
        set contamination_warn "URI_ANTERIOR=\"${last_req_uri}\" METHOD_ANTERIOR=${last_req_method}"
    }

    set msg "\[oc_request\] ACTOR=CLIENTE ACCION=REQUEST_HTTP_REGISTRADO"
    set msg "${msg} VS=${vs_name} CLIENTE_IP=${src_ip} CONEXION_CLIENTE=${client_conn_id}"
    set msg "${msg} NUM_REQUEST_CLIENTE=${client_req_num}"
    set msg "${msg} VECES_SERVIDOR_CONECTADO=${srv_conn_count}"
    set msg "${msg} ONECONNECT_REUSO=${oc_reuse} ID_CONEXION_SERVIDOR=${srv_conn_id}"
    set msg "${msg} METHOD=${req_method} HOST=${req_host} URI=${req_uri}"
    log local0.info $msg

    if { $oc_reuse eq "SI" && $client_req_num == 2 } {
        set warn "\[oc_warn\] ACTOR=BIGIP ACCION=ONECONNECT_ACTIVO_CONFIRMADO"
        set warn "${warn} VS=${vs_name} CLIENTE_IP=${src_ip} CONEXION_CLIENTE=${client_conn_id}"
        set warn "${warn} ID_CONEXION_SERVIDOR=${srv_conn_id}"
        set warn "${warn} DETALLE=SERVER_CONNECTED no disparo para este request."
        set warn "${warn} OneConnect esta reutilizando la conexion TCP al servidor."
        set warn "${warn} Tener cuidado con iRules que usen SERVER_CONNECTED para inicializar variables."
        log local0.warning $warn
    }

    if { $contamination_warn ne "" } {
        set warn "\[oc_warn\] ACTOR=BIGIP ACCION=POSIBLE_CONTAMINACION_VARIABLES"
        set warn "${warn} VS=${vs_name} CLIENTE_IP=${src_ip} CONEXION_CLIENTE=${client_conn_id}"
        set warn "${warn} TIPO=VARIABLES_DEL_REQUEST_ANTERIOR NUM_REQUEST=${client_req_num}"
        set warn "${warn} ${contamination_warn}"
        set warn "${warn} DETALLE=Variables del request anterior siguen disponibles en este request."
        set warn "${warn} Reinicializar variables en HTTP_REQUEST si esto causa problemas."
        log local0.warning $warn
    }

    # Actualizar variables del request actual para el proximo ciclo
    set last_req_method $req_method
    set last_req_uri    $req_uri
}

when HTTP_RESPONSE {
    set status  [HTTP::status]
    set member  "[LB::server addr]:[LB::server port]"

    set msg "\[oc_request\] ACTOR=SERVIDOR ACCION=RESPUESTA_HTTP_EN_CONEXION_ONECONNECT"
    set msg "${msg} CONEXION_CLIENTE=${client_conn_id} NUM_REQUEST=${client_req_num}"
    set msg "${msg} CODIGO_HTTP=${status} SERVIDOR=${member}"
    set msg "${msg} ID_CONEXION_SERVIDOR=${srv_conn_id}"
    log local0.debug $msg
}
