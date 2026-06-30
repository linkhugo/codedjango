# =============================================================================
# ssl_cipher_inspector.tcl
#
# PURPOSE : Audita que ciphers SSL/TLS se estan negociando en produccion.
#           Detecta y alerta ciphers debiles o deprecated:
#             - CBC mode (vulnerable a BEAST/POODLE)
#             - RC4 / ARCFOUR (broken)
#             - 3DES / DES (SWEET32)
#             - NULL ciphers
#             - EXPORT-grade
#             - Anonymous (no auth)
#             - Claves < 128 bits
#           Tambien alerta versiones TLS deprecated (1.0, 1.1).
#
# CASOS DE USO:
#   - Validacion post-hardening de cipher strings
#   - Auditoria de compliance (PCI-DSS, FIPS)
#   - Detectar clientes que no soportan TLS 1.2+
#
# LOG TAG : [cipher_audit] / [cipher_weak] / [tls_deprecated]
# GREP    : grep "\[cipher_weak\]" /var/log/ltm
#
# EVENTS  : CLIENTSSL_HANDSHAKE
# =============================================================================

when CLIENTSSL_HANDSHAKE {

    set cipher_name    [SSL::cipher name]
    set cipher_version [SSL::cipher version]
    set cipher_bits    [SSL::cipher bits]
    set client_ip      [IP::client_addr]
    set sni_name       [SSL::servername]

    set msg "\[cipher_audit\] ACTOR=CLIENTE ACCION=CIFRADO_TLS_REGISTRADO"
    set msg "${msg} VS=[virtual name] CLIENTE_IP=${client_ip} SNI=\"${sni_name}\""
    set msg "${msg} CIFRADO=${cipher_name} VERSION_TLS=${cipher_version} BITS=${cipher_bits}"
    log local0.debug $msg

    set cipher_lower [string tolower $cipher_name]
    set is_weak      0
    set weak_reason  ""

    if { [string match "*_cbc*" $cipher_lower] || [string match "*-cbc*" $cipher_lower] } {
        set is_weak 1
        set weak_reason "CBC_MODE"
    } elseif { [string match "*rc4*" $cipher_lower] || [string match "*arcfour*" $cipher_lower] } {
        set is_weak 1
        set weak_reason "RC4"
    } elseif { [string match "*3des*" $cipher_lower] || [string match "*des*" $cipher_lower] } {
        set is_weak 1
        set weak_reason "3DES"
    } elseif { [string match "*null*" $cipher_lower] } {
        set is_weak 1
        set weak_reason "NULL_CIPHER"
    } elseif { [string match "*export*" $cipher_lower] } {
        set is_weak 1
        set weak_reason "EXPORT_GRADE"
    } elseif { [string match "*anon*" $cipher_lower] } {
        set is_weak 1
        set weak_reason "ANONIMO"
    } elseif { $cipher_bits < 128 } {
        set is_weak 1
        set weak_reason "CLAVE_DEBIL_${cipher_bits}bits"
    }

    if { $is_weak } {
        set alert "\[cipher_weak\] ACTOR=CLIENTE ACCION=CIFRADO_DEBIL_DETECTADO"
        set alert "${alert} VS=[virtual name] CLIENTE_IP=${client_ip} SNI=\"${sni_name}\""
        set alert "${alert} CIFRADO=${cipher_name} VERSION_TLS=${cipher_version} BITS=${cipher_bits}"
        set alert "${alert} RAZON_DEBILIDAD=${weak_reason}"
        set alert "${alert} DETALLE=El cliente nego un cifrado inseguro (${weak_reason})."
        set alert "${alert} Revisar configuracion del ClientSSL profile para bloquear ciphers debiles."
        log local0.err $alert
    }

    if { $cipher_version eq "TLSv1" || $cipher_version eq "TLSv1.1" } {
        set alert "\[tls_deprecated\] ACTOR=CLIENTE ACCION=VERSION_TLS_OBSOLETA"
        set alert "${alert} VS=[virtual name] CLIENTE_IP=${client_ip}"
        set alert "${alert} VERSION_TLS=${cipher_version} CIFRADO=${cipher_name}"
        set alert "${alert} DETALLE=El cliente uso ${cipher_version} que es una version obsoleta y vulnerable."
        set alert "${alert} Requerir TLS 1.2 o superior para cumplir con PCI-DSS y mejores practicas."
        log local0.warning $alert
    }
}
