# =============================================================================
# ssl_handshake_logger.tcl
#
# PURPOSE : Registra detalles del handshake SSL/TLS por conexion:
#           - Version TLS negociada (TLSv1.2, TLSv1.3, etc.)
#           - Cipher suite seleccionado y bits de seguridad
#           - SNI enviado en el ClientHello
#           - Certificado de cliente (si mTLS esta configurado)
#           - Detalles del handshake server-side (re-encripcion)
#           Alerta explicita en TLS 1.0 y TLS 1.1 (deprecated).
#
# REQUIERE: ClientSSL profile adjunto al VS.
#           ServerSSL profile para el evento SERVERSSL_HANDSHAKE.
#
# LOG TAG : [ssl_hello] / [ssl_hs_client] / [ssl_hs_server] / [ssl_deprecated]
# GREP    : grep "\[ssl_deprecated\]" /var/log/ltm
#
# EVENTS  : CLIENTSSL_CLIENTHELLO, CLIENTSSL_HANDSHAKE, SERVERSSL_HANDSHAKE
# =============================================================================

when CLIENTSSL_CLIENTHELLO {
    set sni_name [SSL::servername]
    set msg "\[ssl_hello\] ACTOR=CLIENTE ACCION=TLS_CLIENTHELLO_RECIBIDO"
    set msg "${msg} VS=[virtual name]"
    set msg "${msg} CLIENTE_IP=[IP::client_addr]:[TCP::client_port] SNI=\"${sni_name}\""
    log local0.debug $msg
}

when CLIENTSSL_HANDSHAKE {
    set tls_version   [SSL::cipher version]
    set tls_cipher    [SSL::cipher name]
    set tls_bits      [SSL::cipher bits]
    set sni_confirmed [SSL::servername]

    if { [SSL::cert count] > 0 } {
        set mtls_subject [X509::subject [SSL::cert 0]]
        set mtls_serial  [X509::serial [SSL::cert 0]]
        set mtls_exp     [X509::not_valid_after [SSL::cert 0]]
        set mtls_info    "SUJETO=\"${mtls_subject}\" SERIE=${mtls_serial} VENCE=${mtls_exp}"
    } else {
        set mtls_info "SIN_CERTIFICADO_CLIENTE"
    }

    set msg "\[ssl_hs_client\] ACTOR=CLIENTE ACCION=TLS_HANDSHAKE_COMPLETADO"
    set msg "${msg} VS=[virtual name]"
    set msg "${msg} CLIENTE_IP=[IP::client_addr]:[TCP::client_port]"
    set msg "${msg} SNI=\"${sni_confirmed}\" VERSION_TLS=${tls_version}"
    set msg "${msg} CIFRADO=${tls_cipher} BITS=${tls_bits}"
    set msg "${msg} CERT_CLIENTE=${mtls_info}"
    log local0.info $msg

    if { $tls_version eq "TLSv1" || $tls_version eq "TLSv1.1" || $tls_version eq "SSLv3" } {
        set alert "\[ssl_deprecated\] ACTOR=CLIENTE ACCION=VERSION_TLS_OBSOLETA_DETECTADA"
        set alert "${alert} VS=[virtual name] CLIENTE_IP=[IP::client_addr]"
        set alert "${alert} VERSION_TLS=${tls_version} CIFRADO=${tls_cipher}"
        set alert "${alert} DETALLE=El cliente nego una version TLS obsoleta y vulnerable."
        set alert "${alert} ${tls_version} ya no es segura. Requerir TLS 1.2 o superior."
        log local0.warning $alert
    }
}

when SERVERSSL_HANDSHAKE {
    set srv_version [SSL::cipher version]
    set srv_cipher  [SSL::cipher name]
    set srv_bits    [SSL::cipher bits]

    if { [SSL::cert count] > 0 } {
        set srv_subject [X509::subject [SSL::cert 0]]
        set srv_exp     [X509::not_valid_after [SSL::cert 0]]
        set srv_cert    "SUJETO=\"${srv_subject}\" VENCE=${srv_exp}"
    } else {
        set srv_cert "SIN_CERTIFICADO_SERVIDOR"
    }

    set msg "\[ssl_hs_server\] ACTOR=BIGIP ACCION=TLS_HANDSHAKE_CON_BACKEND"
    set msg "${msg} VS=[virtual name]"
    set msg "${msg} SERVIDOR=[IP::server_addr]:[TCP::server_port]"
    set msg "${msg} VERSION_TLS=${srv_version} CIFRADO=${srv_cipher} BITS=${srv_bits}"
    set msg "${msg} CERT_SERVIDOR=${srv_cert}"
    log local0.info $msg
}
