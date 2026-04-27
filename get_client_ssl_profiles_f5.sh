#!/usr/bin/env bash
# =============================================================================
# get_client_ssl_profiles_f5.sh
# Obtiene Client SSL Profiles de múltiples equipos F5 via iControl REST API
# Salida: /var/lb/client_ssl_profiles/<fqdn>.json
#         (compatible con insert_client_ssl_profiles_django.py)
# Uso   : ./get_client_ssl_profiles_f5.sh [archivo_hosts]   Default: ./hosts.txt
# =============================================================================

for cmd in curl jq; do
    command -v "$cmd" >/dev/null 2>&1 \
        || { echo "ERROR: '${cmd}' no encontrado."; exit 1; }
done

HOSTS_FILE="${1:-hosts.txt}"
[[ ! -f "$HOSTS_FILE" ]] && { echo "ERROR: Archivo no encontrado: ${HOSTS_FILE}"; exit 1; }
HOST_COUNT=$(grep -cE '^[^#[:space:]]' "$HOSTS_FILE" || true)
[[ "$HOST_COUNT" -eq 0 ]] && { echo "ERROR: No hay hosts válidos en ${HOSTS_FILE}"; exit 1; }

echo "============================================================"
echo "  F5 Client SSL Profiles — Extracción via iControl REST API"
echo "  Hosts: ${HOST_COUNT} equipos desde ${HOSTS_FILE}"
echo "============================================================"
read -rp  "Usuario  : " F5_USER
read -rsp "Password : " F5_PASS
echo

OUTPUT_DIR="/var/lb/client_ssl_profiles"
mkdir -p "$OUTPUT_DIR"

_get() {
    curl -sk --connect-timeout 15 --max-time 120 \
        -u "${F5_USER}:${F5_PASS}" \
        -H "Content-Type: application/json" "$1"
}

OK=0; FAIL=0

while IFS= read -r F5_HOST || [[ -n "$F5_HOST" ]]; do
    [[ -z "$F5_HOST" || "$F5_HOST" == \#* ]] && continue

    echo ""
    echo "------------------------------------------------------------"
    echo "  Host: ${F5_HOST}"
    echo "------------------------------------------------------------"

    OUTPUT_FILE="${OUTPUT_DIR}/${F5_HOST}.json"

    # ── Verificar que el equipo sea Standby ──────────────────────────────────
    echo "  → Verificando estado de failover..."
    FAILOVER_STATE=$(_get "https://${F5_HOST}/mgmt/tm/cm/failover-status" | \
        jq -r '.entries | to_entries[0].value.nestedStats.entries.status.description // "UNKNOWN"' 2>/dev/null || echo "UNKNOWN")

    if [[ "$FAILOVER_STATE" == "ACTIVE" ]]; then
        echo "  ⚠ Equipo ACTIVE — omitiendo (solo se extrae desde Standby)"
        continue
    elif [[ "$FAILOVER_STATE" == "STANDBY" ]]; then
        echo "  ✓ Equipo STANDBY — continuando"
    else
        echo "  ⚠ Estado desconocido (${FAILOVER_STATE}) — omitiendo"
        (( FAIL++ )) || true; continue
    fi

    echo "  → Obteniendo Client SSL Profiles..."
    PROFILES=$(_get "https://${F5_HOST}/mgmt/tm/ltm/profile/client-ssl?\$top=10000")

    if ! echo "$PROFILES" | jq -e '.items' >/dev/null 2>&1; then
        echo "  ERROR: No se pudo obtener perfiles. Verifica credenciales/conectividad."
        (( FAIL++ )) || true; continue
    fi

    echo "  → Generando JSON..."
    if ! jq -n \
        --arg     fqdn     "$F5_HOST" \
        --argjson profiles "$PROFILES" \
    '[$profiles.items[] | {
        name:                      .name,
        full_path:                 .fullPath,
        ltm_fqdn:                  $fqdn,
        description:               (.description // null),
        parent:                    (.defaultsFrom // null),
        certificate_file:          (.cert // null),
        chain_file:                (.chain // null),
        allow_non_ssl:             (.allowNonSsl // null),
        authenticate_depth:        (.authenticateDepth // null),
        authenticate_frequency:    (.authenticate // null),
        cache_size:                (.cacheSize // null),
        cache_timeout:             (.cacheTimeout // null),
        peer_certificate_mode:     (.peerCertMode // null),
        profile_mode_enabled:      (.mode // null),
        renegotiation:             (.renegotiation // null),
        retain_certificate:        (.retainCertificate // null),
        secure_renegotiation_mode: (.secureRenegotiation // null),
        session_ticket:            (.sessionTicket // null),
        sni_default:               (.sniDefault // null),
        strict_name:               (.sniRequire // null)
    }]' > "$OUTPUT_FILE"; then
        echo "  ERROR: Falló la transformación JSON para ${F5_HOST}."
        (( FAIL++ )) || true; continue
    fi

    SAVED=$(jq length "$OUTPUT_FILE")
    echo "  ✓ ${SAVED} perfiles guardados en: ${OUTPUT_FILE}"
    (( OK++ )) || true

done < "$HOSTS_FILE"

echo ""
echo "============================================================"
echo "  Resumen: ${OK} exitosos  |  ${FAIL} fallidos"
echo "============================================================"
[[ "$FAIL" -gt 0 ]] && exit 1 || exit 0
