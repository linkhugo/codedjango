# =============================================================================
# suspicious_pattern_detector.tcl
#
# PURPOSE : Detecta y registra patrones HTTP sospechosos:
#           1. Metodos HTTP peligrosos (TRACE, CONNECT, DEBUG)
#           2. Path traversal (../../, %2e%2e/)
#           3. SQL injection en la URI
#           4. User-Agents de scanners conocidos (sqlmap, nikto, nuclei...)
#           5. URI oversized (>8192 bytes, posible buffer overflow probe)
#
# MODO    : Configurar ACTION_MODE:
#             "log"   - Solo registrar (modo observacion, seguro para produccion)
#             "block" - Responder 400 y bloquear (modo activo)
#           Empezar siempre en "log" para baselining antes de activar "block".
#
# LOG TAG : [security_detect]
# GREP    : grep "\[security_detect\]" /var/log/ltm | grep AMENAZA
#
# EVENTS  : HTTP_REQUEST
# =============================================================================

when HTTP_REQUEST {

    set ACTION_MODE "log"

    set client_ip  [IP::client_addr]
    set req_method [HTTP::method]
    set req_uri    [HTTP::uri]
    set req_host   [HTTP::host]
    set user_agent [HTTP::header "User-Agent"]
    set vs_name    [virtual name]

    set threat_detected 0
    set threat_type     ""

    # 1. Metodos peligrosos
    if { $req_method eq "TRACE" || $req_method eq "CONNECT" || $req_method eq "DEBUG" } {
        set threat_detected 1
        set threat_type "METODO_PELIGROSO:${req_method}"
    }

    # 2. Path traversal
    if { !$threat_detected } {
        set uri_lower [string tolower $req_uri]
        if { [string match "*../*" $uri_lower] || [string match "*%2e%2e%2f*" $uri_lower] || [string match "*%252e%252e*" $uri_lower] } {
            set threat_detected 1
            set threat_type "PATH_TRAVERSAL"
        }
    }

    # 3. SQL injection en URI
    if { !$threat_detected } {
        set uri_lower [string tolower $req_uri]
        if { [string match "*union select*" $uri_lower] || [string match "*drop table*" $uri_lower] || [string match "*1=1--*" $uri_lower] || [string match "*xp_cmdshell*" $uri_lower] || [string match "*information_schema*" $uri_lower] } {
            set threat_detected 1
            set threat_type "INYECCION_SQL"
        }
    }

    # 4. User-Agents de scanners conocidos
    if { !$threat_detected } {
        set ua_lower [string tolower $user_agent]
        foreach scanner { "sqlmap" "nikto" "nessus" "openvas" "nmap" "masscan" "zgrab" "dirbuster" "gobuster" "wfuzz" "nuclei" "acunetix" "burpsuite" } {
            if { [string match "*${scanner}*" $ua_lower] } {
                set threat_detected 1
                set threat_type "ESCANER_CONOCIDO:${scanner}"
                break
            }
        }
    }

    # 5. URI oversized
    if { !$threat_detected && [string length $req_uri] > 8192 } {
        set threat_detected 1
        set threat_type "URI_EXCESIVA:[string length $req_uri]bytes"
    }

    if { $threat_detected } {
        set alert "\[security_detect\] ACTOR=CLIENTE ACCION=AMENAZA_DETECTADA"
        set alert "${alert} VS=${vs_name} CLIENTE_IP=${client_ip} METHOD=${req_method}"
        set alert "${alert} HOST=${req_host} URI=${req_uri} NAVEGADOR=\"${user_agent}\""
        set alert "${alert} AMENAZA=${threat_type} MODO=${ACTION_MODE}"
        set alert "${alert} DETALLE=Se detecto un patron sospechoso en el request del cliente."
        log local0.warning $alert

        if { $ACTION_MODE eq "block" } {
            HTTP::respond 400 content "<html><body><h1>400 Bad Request</h1></body></html>" "Content-Type" "text/html"
        }
    }
}
