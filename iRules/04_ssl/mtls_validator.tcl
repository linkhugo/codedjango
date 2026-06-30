# =============================================================================
# mtls_validator.tcl
#
# PURPOSE : Valida y registra el resultado del handshake mTLS (mutual TLS)
#           cuando el perfil ClientSSL tiene "Client Certificate: require".
#           Cubre los siguientes escenarios:
#
#           1. Cliente NO presenta certificado (requerido pero ausente)
#           2. Certificado presentado pero FALLO la verificacion del CA
#           3. Certificado presentado y VALIDO - log de detalles completos
#           4. Certificado valido pero PROXIMO A VENCER (warning anticipado)
#           5. Certificado EXPIRADO (detectado en iRule, no solo por SSL stack)
#           6. Validacion de atributos del Subject (CN, OU, O configurables)
#
# CASOS DE USO:
#   - Confirmar que el mTLS esta funcionando end-to-end en el VS
#   - Identificar que cliente especifico falla (por Subject/CN)
#   - Detectar certificados expirados antes de que causen incidentes
#   - Auditar que solo ciertos CAs o CNs estan siendo aceptados
#   - Post-mortem de rechazo de conexion mTLS
#
# REQUIERE:
#   - Perfil ClientSSL con "Client Certificate" configurado en "request" o "require"
#   - Para MTLS_REQUIRED_CN: el CN del cliente debe coincidir con el valor configurado
#     (dejar vacio "" para no validar CN especifico)
#
# CONFIGURACION:
#   MTLS_REQUIRED      - 1 = falla si no hay certificado; 0 = solo loguear si hay cert
#   EXPIRY_WARN_DAYS   - Dias antes del vencimiento para disparar WARNING (default: 30)
#   REQUIRED_CN        - CN requerido en el Subject (default: "" = no validar CN)
#   REQUIRED_OU        - OU requerida en el Subject (default: "" = no validar OU)
#
# LOG TAG : [mtls_ok] / [mtls_fail] / [mtls_expire] / [mtls_no_cert]
# GREP    : grep "\[mtls_fail\]" /var/log/ltm
#           grep "\[mtls_expire\]" /var/log/ltm
#
# EVENTS  : CLIENTSSL_HANDSHAKE
# =============================================================================

when CLIENTSSL_HANDSHAKE {

    set MTLS_REQUIRED    1
    set EXPIRY_WARN_DAYS 30
    set REQUIRED_CN      ""
    set REQUIRED_OU      ""

    set client_ip  [IP::client_addr]
    set client_port [TCP::client_port]
    set vs_name    [virtual name]
    set tls_ver    [SSL::cipher version]
    set tls_cipher [SSL::cipher name]

    # -------------------------------------------------------------------------
    # Caso 1: No se presento certificado de cliente
    # -------------------------------------------------------------------------
    if { [SSL::cert count] == 0 } {
        if { $MTLS_REQUIRED } {
            set alert "\[mtls_no_cert\] ACTOR=CLIENTE ACCION=CERTIFICADO_CLIENTE_AUSENTE"
            set alert "${alert} VS=${vs_name} CLIENTE_IP=${client_ip}:${client_port}"
            set alert "${alert} VERSION_TLS=${tls_ver} RESULTADO=FALLO"
            set alert "${alert} DETALLE=El cliente no presento certificado digital."
            set alert "${alert} El mTLS es obligatorio en este VS. La conexion sera rechazada."
            log local0.err $alert
            SSL::respond "alert"
        } else {
            set msg "\[mtls_no_cert\] ACTOR=CLIENTE ACCION=SIN_CERTIFICADO_OPCIONAL"
            set msg "${msg} VS=${vs_name} CLIENTE_IP=${client_ip}:${client_port}"
            set msg "${msg} RESULTADO=SIN_CERT_OPCIONAL"
            log local0.info $msg
        }
        return
    }

    # -------------------------------------------------------------------------
    # Caso 2: Certificado presente — extraer datos del Subject
    # -------------------------------------------------------------------------
    set cert         [SSL::cert 0]
    set subject      [X509::subject $cert]
    set issuer       [X509::issuer $cert]
    set serial       [X509::serial $cert]
    set not_before   [X509::not_valid_before $cert]
    set not_after    [X509::not_valid_after $cert]
    set verify_result [SSL::verify_result]

    # Extraer CN del subject (formato: "CN=valor, OU=..., O=..., C=...")
    set cert_cn ""
    set cert_ou ""
    set cert_o  ""
    foreach field [split $subject ","] {
        set field [string trim $field]
        if { [string match "CN=*" $field] } { set cert_cn [string range $field 3 end] }
        if { [string match "OU=*" $field] } { set cert_ou [string range $field 3 end] }
        if { [string match "O=*"  $field] } { set cert_o  [string range $field 2 end] }
    }

    # -------------------------------------------------------------------------
    # Caso 3: Verificar resultado del SSL stack (CA chain validation)
    # -------------------------------------------------------------------------
    if { $verify_result != 0 } {
        set verify_error [X509::verify_cert_error_string $verify_result]
        set alert "\[mtls_fail\] ACTOR=CLIENTE ACCION=VALIDACION_CERTIFICADO_FALLIDA"
        set alert "${alert} VS=${vs_name} CLIENTE_IP=${client_ip}:${client_port}"
        set alert "${alert} RESULTADO=FALLO CODIGO_ERROR=${verify_result}"
        set alert "${alert} RAZON_ERROR=\"${verify_error}\""
        set alert "${alert} CN_CLIENTE=\"${cert_cn}\" EMISOR=\"${issuer}\" SERIE=${serial}"
        set alert "${alert} DETALLE=El certificado del cliente no paso la validacion de la cadena CA."
        log local0.err $alert
        return
    }

    # -------------------------------------------------------------------------
    # Caso 4: Verificar expiracion del certificado
    # -------------------------------------------------------------------------
    set now_epoch    [clock seconds]
    set expiry_epoch [clock scan $not_after]
    set days_left    [expr { ($expiry_epoch - $now_epoch) / 86400 }]

    if { $days_left < 0 } {
        set alert "\[mtls_expire\] ACTOR=CLIENTE ACCION=CERTIFICADO_EXPIRADO"
        set alert "${alert} VS=${vs_name} CLIENTE_IP=${client_ip}:${client_port}"
        set alert "${alert} RESULTADO=FALLO CN_CLIENTE=\"${cert_cn}\""
        set alert "${alert} VENCIO_EL=\"${not_after}\" DIAS_VENCIDO=[expr { $days_left * -1 }]"
        set alert "${alert} DETALLE=El certificado del cliente esta vencido. Renovarlo urgente."
        log local0.err $alert
        return
    } elseif { $days_left <= $EXPIRY_WARN_DAYS } {
        set warn "\[mtls_expire\] ACTOR=CLIENTE ACCION=CERTIFICADO_PROXIMO_A_VENCER"
        set warn "${warn} VS=${vs_name} CLIENTE_IP=${client_ip}:${client_port}"
        set warn "${warn} RESULTADO=ADVERTENCIA CN_CLIENTE=\"${cert_cn}\""
        set warn "${warn} VENCE_EL=\"${not_after}\" DIAS_RESTANTES=${days_left}"
        set warn "${warn} DETALLE=El certificado del cliente vence en ${days_left} dias. Renovar pronto."
        log local0.warning $warn
    }

    # -------------------------------------------------------------------------
    # Caso 5: Validar CN requerido (si esta configurado)
    # -------------------------------------------------------------------------
    if { $REQUIRED_CN ne "" && $cert_cn ne $REQUIRED_CN } {
        set alert "\[mtls_fail\] ACTOR=CLIENTE ACCION=CN_NO_COINCIDE"
        set alert "${alert} VS=${vs_name} CLIENTE_IP=${client_ip}:${client_port}"
        set alert "${alert} RESULTADO=FALLO"
        set alert "${alert} CN_ESPERADO=\"${REQUIRED_CN}\" CN_PRESENTADO=\"${cert_cn}\""
        set alert "${alert} DETALLE=El CN del certificado no coincide con el requerido."
        log local0.err $alert
        return
    }

    # -------------------------------------------------------------------------
    # Caso 6: Validar OU requerida (si esta configurada)
    # -------------------------------------------------------------------------
    if { $REQUIRED_OU ne "" && $cert_ou ne $REQUIRED_OU } {
        set alert "\[mtls_fail\] ACTOR=CLIENTE ACCION=OU_NO_COINCIDE"
        set alert "${alert} VS=${vs_name} CLIENTE_IP=${client_ip}:${client_port}"
        set alert "${alert} RESULTADO=FALLO"
        set alert "${alert} OU_ESPERADA=\"${REQUIRED_OU}\" OU_PRESENTADA=\"${cert_ou}\""
        set alert "${alert} DETALLE=La OU del certificado no coincide con la requerida."
        log local0.err $alert
        return
    }

    # -------------------------------------------------------------------------
    # Exito: certificado valido, CA verificado, no expirado, atributos correctos
    # -------------------------------------------------------------------------
    set msg "\[mtls_ok\] ACTOR=CLIENTE ACCION=CERTIFICADO_VALIDO_ACEPTADO"
    set msg "${msg} VS=${vs_name} CLIENTE_IP=${client_ip}:${client_port} RESULTADO=OK"
    set msg "${msg} VERSION_TLS=${tls_ver} CIFRADO=${tls_cipher}"
    set msg "${msg} CN_CLIENTE=\"${cert_cn}\" OU=\"${cert_ou}\" ORGANIZACION=\"${cert_o}\""
    set msg "${msg} EMISOR=\"${issuer}\" SERIE=${serial}"
    set msg "${msg} VALIDO_DESDE=\"${not_before}\" VENCE_EL=\"${not_after}\" DIAS_RESTANTES=${days_left}"
    log local0.info $msg

    # Log de todos los certs de la cadena si hay mas de uno
    if { [SSL::cert count] > 1 } {
        set chain_count [SSL::cert count]
        set msg "\[mtls_ok\] ACTOR=CLIENTE ACCION=CADENA_CERTIFICADOS"
        set msg "${msg} TOTAL_CERTS_EN_CADENA=${chain_count}"
        set msg "${msg} CLIENTE_IP=${client_ip} VS=${vs_name}"
        log local0.debug $msg
        set i 1
        while { $i < $chain_count } {
            set chain_cert    [SSL::cert $i]
            set chain_subject [X509::subject $chain_cert]
            set chain_exp     [X509::not_valid_after $chain_cert]
            set msg "\[mtls_ok\] ACTOR=CLIENTE ACCION=CERT_CADENA_${i}"
            set msg "${msg} SUJETO=\"${chain_subject}\" VENCE=\"${chain_exp}\""
            log local0.debug $msg
            incr i
        }
    }
}
