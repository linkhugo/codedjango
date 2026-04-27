#!/usr/bin/env bash
# =============================================================================
# get_ssl_certs_f5.sh
# Obtiene certificados SSL de múltiples equipos F5 via iControl REST API
# Salida: /var/lb/ssl_certs/<fqdn>.json  (compatible con insert_ssl_certs_django.py)
# Uso   : ./get_ssl_certs_f5.sh [archivo_hosts]   Default: ./hosts.txt
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
echo "  F5 SSL Certificates — Extracción via iControl REST API"
echo "  Hosts: ${HOST_COUNT} equipos desde ${HOSTS_FILE}"
echo "============================================================"
read -rp  "Usuario  : " F5_USER
read -rsp "Password : " F5_PASS
echo

OUTPUT_DIR="/var/lb/ssl_certs"
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

    echo "  → Obteniendo certificados SSL..."
    CERTS=$(_get "https://${F5_HOST}/mgmt/tm/sys/file/ssl-cert?\$top=10000")

    if ! echo "$CERTS" | jq -e '.items' >/dev/null 2>&1; then
        echo "  ERROR: No se pudo obtener certificados. Verifica credenciales/conectividad."
        (( FAIL++ )) || true; continue
    fi

    echo "  → Generando JSON..."
    if ! jq -n \
        --arg     fqdn  "$F5_HOST" \
        --argjson certs "$CERTS" \
    '[$certs.items[] | {
        name:                    .name,
        full_path:               .fullPath,
        ltm_fqdn:                $fqdn,
        create_time:             (.createTime // null),
        expiration_date:         (.expirationString // null),
        expiration_timestamp:    (.expirationDate // null),
        fingerprint:             (.fingerprint // null),
        issuer:                  (.issuer // null),
        is_bundle:               (if .isBundle then "true" else "false" end),
        key_size:                (.keySize // null),
        key_type:                (.keyType // null),
        last_update_time:        (.lastUpdateTime // null),
        sha1_checksum:           (.checksum // null),
        subject:                 (.subject // null),
        subject_alternative_name:(.subjectAlternativeName // null)
    }]' > "$OUTPUT_FILE"; then
        echo "  ERROR: Falló la transformación JSON para ${F5_HOST}."
        (( FAIL++ )) || true; continue
    fi

    SAVED=$(jq length "$OUTPUT_FILE")
    echo "  ✓ ${SAVED} certificados guardados en: ${OUTPUT_FILE}"
    (( OK++ )) || true

done < "$HOSTS_FILE"

echo ""
echo "============================================================"
echo "  Resumen: ${OK} exitosos  |  ${FAIL} fallidos"
echo "============================================================"
[[ "$FAIL" -gt 0 ]] && exit 1 || exit 0
