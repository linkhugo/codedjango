# =============================================================================
# fastl4_payload_inspector.tcl
#
# PURPOSE : Captura e inspecciona los primeros bytes del payload TCP en un VS
#           con perfil FastL4. Permite identificar el protocolo de aplicacion
#           real que corre sobre la conexion TCP, detectar protocolos inesperados
#           y diagnosticar problemas de negociacion a nivel de aplicacion.
#
#           ADVERTENCIA IMPORTANTE - IMPACTO EN RENDIMIENTO:
#           El uso de TCP::collect en FastL4 DESACTIVA la aceleracion hardware
#           (PVA - Packet Velocity ASIC) para esa conexion. La conexion pasa a
#           ser procesada por software (TMM). Usar solo en troubleshooting,
#           nunca de forma permanente en produccion con alto trafico.
#
#           Deteccion de protocolos por primeros bytes (firmas):
#           +----------+------------------+-------------------------------+
#           | Protocolo| Firma (hex/ascii) | Ejemplo de uso               |
#           +----------+------------------+-------------------------------+
#           | HTTP/1.x | GET / POST / HTTP | VS FastL4 que recibe HTTP    |
#           | SSH       | SSH-             | Port 22 FastL4               |
#           | TLS/SSL   | 0x16 0x03        | TLS ClientHello en raw TCP   |
#           | MySQL     | 0x4a / handshake | Puerto 3306                  |
#           | FTP       | 220              | Puerto 21 control channel    |
#           | SMTP      | 220              | Puerto 25 banner             |
#           | RDP       | 0x03 0x00        | Puerto 3389                  |
#           | DNS       | query structure  | Puerto 53 TCP                |
#           | Unknown   | no firma         | Protocolo no identificado    |
#           +----------+------------------+-------------------------------+
#
# CASOS DE USO:
#   - Confirmar que el protocolo correcto llega al VS FastL4 esperado
#   - Detectar HTTP en un VS que deberia ser solo TCP puro (mal routing)
#   - Detectar TLS en un VS que deberia ser texto plano (o viceversa)
#   - Fingerprinting de aplicaciones en VSes generico TCP
#   - Diagnosticar handshakes de protocolo fallidos
#
# CONFIGURACION:
#   COLLECT_BYTES - Cantidad de bytes a capturar del primer segmento (default: 16)
#                  Suficiente para identificar el protocolo.
#                  Aumentar si se necesita mas contexto del handshake.
#
# LOG TAG : [l4_payload] / [l4_proto]
# GREP    : grep "\[l4_proto\]" /var/log/ltm
#
# PERFIL  : FastL4
# EVENTS  : CLIENT_ACCEPTED, CLIENT_DATA
# =============================================================================

when CLIENT_ACCEPTED {
    set COLLECT_BYTES 16

    set conn_id  "[IP::client_addr]:[TCP::client_port]:[clock clicks]"
    set src_ip   [IP::client_addr]
    set src_port [TCP::client_port]
    set dst_port [TCP::local_port]
    set vs_name  [virtual name]

    TCP::collect $COLLECT_BYTES
}

when CLIENT_DATA {

    set payload     [TCP::payload]
    set payload_len [string length $payload]
    set vs_name     [virtual name]

    set hex_dump ""
    set ascii_dump ""
    set i 0
    while { $i < $payload_len && $i < 16 } {
        binary scan [string index $payload $i] H2 hex_byte
        set hex_dump "${hex_dump}${hex_byte} "
        set dec_byte [scan [string index $payload $i] %c]
        if { $dec_byte >= 32 && $dec_byte <= 126 } {
            set ascii_dump "${ascii_dump}[string index $payload $i]"
        } else {
            set ascii_dump "${ascii_dump}."
        }
        incr i
    }

    set proto "DESCONOCIDO"

    if { [string match "GET *"    $payload] ||
         [string match "POST *"   $payload] ||
         [string match "HEAD *"   $payload] ||
         [string match "PUT *"    $payload] ||
         [string match "DELETE *" $payload] ||
         [string match "HTTP/*"   $payload] } {
        set proto "HTTP"

    } elseif { [string match "SSH-*" $payload] } {
        set proto "SSH"

    } elseif { [string match "220 *" $payload] || [string match "220-*" $payload] } {
        set proto "FTP_O_SMTP_BANNER"

    } elseif { $payload_len >= 2 } {
        binary scan [string range $payload 0 1] H2H2 byte0 byte1
        if { $byte0 eq "16" && ($byte1 eq "03" || $byte1 eq "02" || $byte1 eq "01") } {
            set proto "TLS_CLIENT_HELLO"
        } elseif { $byte0 eq "03" && $byte1 eq "00" } {
            set proto "RDP"
        } elseif { $byte0 eq "15" && $byte1 eq "03" } {
            set proto "TLS_ALERT"
        }
    }

    set msg "\[l4_proto\] ACTOR=CLIENTE ACCION=PROTOCOLO_IDENTIFICADO"
    set msg "${msg} CONN_ID=${conn_id} VS=${vs_name}"
    set msg "${msg} CLIENTE_IP=[IP::client_addr]:[TCP::client_port]"
    set msg "${msg} PUERTO_DESTINO=${dst_port}"
    set msg "${msg} PROTOCOLO_DETECTADO=${proto} TAMANO_PAYLOAD=${payload_len}"
    set msg "${msg} PRIMEROS_BYTES_HEX=\"${hex_dump}\" PRIMEROS_BYTES_ASCII=\"${ascii_dump}\""
    log local0.info $msg

    if { $proto eq "HTTP" } {
        set msg "\[l4_payload\] ACTOR=CLIENTE ACCION=HTTP_EN_VS_FASTL4"
        set msg "${msg} VS=${vs_name} CLIENTE_IP=[IP::client_addr]"
        set msg "${msg} DETALLE=Se detecto trafico HTTP en un VS FastL4."
        set msg "${msg} Considerar usar perfil Standard en lugar de FastL4 para este VS."
        log local0.warning $msg
    } elseif { $proto eq "TLS_CLIENT_HELLO" } {
        set msg "\[l4_payload\] ACTOR=CLIENTE ACCION=TLS_EN_VS_FASTL4"
        set msg "${msg} VS=${vs_name} CLIENTE_IP=[IP::client_addr] PUERTO_DESTINO=${dst_port}"
        set msg "${msg} DETALLE=Se detecto TLS en el VS FastL4."
        set msg "${msg} Verificar si se requiere perfil ClientSSL para terminacion TLS."
        log local0.info $msg
    }

    TCP::release
}
