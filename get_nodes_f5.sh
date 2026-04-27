#!/usr/bin/env bash
# =============================================================================
# get_nodes_f5.sh
# Obtiene LTM Nodes de múltiples equipos F5 via iControl REST API
# Salida: /var/lb/ltm_nodes/<fqdn>.json  (compatible con insert_ltm_nodes_django.py)
# Uso   : ./get_nodes_f5.sh [archivo_hosts]   Default: ./hosts.txt
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
echo "  F5 LTM Nodes — Extracción via iControl REST API"
echo "  Hosts: ${HOST_COUNT} equipos desde ${HOSTS_FILE}"
echo "============================================================"
read -rp  "Usuario  : " F5_USER
read -rsp "Password : " F5_PASS
echo

OUTPUT_DIR="/var/lb/ltm_nodes"
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

    echo "  → Obteniendo Nodes..."
    NODES=$(_get "https://${F5_HOST}/mgmt/tm/ltm/node?\$top=10000")

    if ! echo "$NODES" | jq -e '.items' >/dev/null 2>&1; then
        echo "  ERROR: No se pudo obtener Nodes. Verifica credenciales/conectividad."
        (( FAIL++ )) || true; continue
    fi

    echo "  → Obteniendo estadísticas..."
    NODE_STATS=$(_get "https://${F5_HOST}/mgmt/tm/ltm/node/stats")

    echo "  → Generando JSON..."
    if ! jq -n \
        --arg     fqdn  "$F5_HOST" \
        --argjson nodes "$NODES" \
        --argjson stats "$NODE_STATS" \
    '
    ($stats.entries // {} | to_entries | map({
        key: (.value.nestedStats.entries["tmName"].description // ""),
        value: {
            availability_status: (.value.nestedStats.entries["status.availabilityState"].description // null),
            enabled_status:      (.value.nestedStats.entries["status.enabledState"].description // null),
            monitor_status:      (.value.nestedStats.entries["monitorStatus"].description // null),
            monitor_rule:        (.value.nestedStats.entries["monitorRule"].description // null),
            session_status:      (.value.nestedStats.entries["sessionStatus"].description // null),
            status_reason:       (.value.nestedStats.entries["status.statusReason"].description // null)
        }
    }) | from_entries) as $sm |

    [$nodes.items[] |
        ($sm[.fullPath] // {}) as $st |
        {
            name:                .name,
            full_path:           .fullPath,
            ltm_fqdn:            $fqdn,
            address:             (.address | split("%")[0]),
            connection_limit:    (.connectionLimit // null),
            dynamic_ratio:       (.dynamicRatio // null),
            rate_limit:          ((.rateLimit // "disabled") | if . == "disabled" then null else tonumber? end),
            ratio:               (.ratio // null),
            availability_status: $st.availability_status,
            enabled_status:      $st.enabled_status,
            monitor_status:      $st.monitor_status,
            monitor_rule:        $st.monitor_rule,
            monitor_type:        (.monitor | if . then split(" ")[0] | ltrimstr("min ") else null end),
            session_status:      $st.session_status,
            status_reason:       $st.status_reason,
            monitors:            (if .monitor then [.monitor] else [] end)
        }
    ]' > "$OUTPUT_FILE"; then
        echo "  ERROR: Falló la transformación JSON para ${F5_HOST}."
        (( FAIL++ )) || true; continue
    fi

    SAVED=$(jq length "$OUTPUT_FILE")
    echo "  ✓ ${SAVED} Nodes guardados en: ${OUTPUT_FILE}"
    (( OK++ )) || true

done < "$HOSTS_FILE"

echo ""
echo "============================================================"
echo "  Resumen: ${OK} exitosos  |  ${FAIL} fallidos"
echo "============================================================"
[[ "$FAIL" -gt 0 ]] && exit 1 || exit 0
