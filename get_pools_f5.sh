#!/usr/bin/env bash
# =============================================================================
# get_pools_f5.sh
# Obtiene Pools de múltiples equipos F5 via iControl REST API
# Salida: /var/lb/pools/<fqdn>.json  (compatible con insert_pools_django.py)
# Uso   : ./get_pools_f5.sh [archivo_hosts]   Default: ./hosts.txt
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
echo "  F5 Pools — Extracción via iControl REST API"
echo "  Hosts: ${HOST_COUNT} equipos desde ${HOSTS_FILE}"
echo "============================================================"
read -rp  "Usuario  : " F5_USER
read -rsp "Password : " F5_PASS
echo

OUTPUT_DIR="/var/lb/pools"
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

    echo "  → Obteniendo Pools..."
    POOLS=$(_get "https://${F5_HOST}/mgmt/tm/ltm/pool?\$top=10000&expandSubcollections=true")

    if ! echo "$POOLS" | jq -e '.items' >/dev/null 2>&1; then
        echo "  ERROR: No se pudo obtener Pools. Verifica credenciales/conectividad."
        (( FAIL++ )) || true; continue
    fi

    echo "  → Obteniendo estadísticas..."
    POOL_STATS=$(_get "https://${F5_HOST}/mgmt/tm/ltm/pool/stats")

    echo "  → Generando JSON..."
    if ! jq -n \
        --arg     fqdn  "$F5_HOST" \
        --argjson pools "$POOLS" \
        --argjson stats "$POOL_STATS" \
    '
    ($stats.entries // {} | to_entries | map({
        key: (.value.nestedStats.entries["tmName"].description // ""),
        value: {
            availability_status:    (.value.nestedStats.entries["status.availabilityState"].description // null),
            enabled_status:         (.value.nestedStats.entries["status.enabledState"].description // null),
            status_reason:          (.value.nestedStats.entries["status.statusReason"].description // null),
            active_member_count:    (.value.nestedStats.entries["activeMemberCnt"].value // null),
            available_member_count: (.value.nestedStats.entries["availableMemberCnt"].value // null),
            member_count:           (.value.nestedStats.entries["memberCnt"].value // null)
        }
    }) | from_entries) as $sm |

    [$pools.items[] |
        ($sm[.fullPath] // {}) as $st |
        {
            name:                    .name,
            full_path:               .fullPath,
            ltm_fqdn:                $fqdn,
            allow_nat:               (.allowNat // null),
            allow_snat:              (.allowSnat // null),
            client_ip_tos:           (.clientIpTos // null),
            client_link_qos:         (.clientLinkQos // null),
            lb_method:               (.loadBalancingMode // null),
            service_down_action:     (.serviceDownAction // null),
            availability_status:     $st.availability_status,
            enabled_status:          $st.enabled_status,
            status_reason:           $st.status_reason,
            active_member_count:     ($st.active_member_count | if . then tonumber? else null end),
            available_member_count:  ($st.available_member_count | if . then tonumber? else null end),
            member_count:            ($st.member_count | if . then tonumber? else null end),
            members: [(.membersReference.items // [])[] | {
                name:                .name,
                address:             (.address // null),
                ratio:               (.ratio // null),
                connection_limit:    (.connectionLimit // null),
                session:             (.session // null),
                state:               (.state // null)
            }],
            monitors: (
                if .monitor then [.monitor | split(" and ") | .[] | ltrimstr("/Common/")] else [] end
            )
        }
    ]' > "$OUTPUT_FILE"; then
        echo "  ERROR: Falló la transformación JSON para ${F5_HOST}."
        (( FAIL++ )) || true; continue
    fi

    SAVED=$(jq length "$OUTPUT_FILE")
    echo "  ✓ ${SAVED} Pools guardados en: ${OUTPUT_FILE}"
    (( OK++ )) || true

done < "$HOSTS_FILE"

echo ""
echo "============================================================"
echo "  Resumen: ${OK} exitosos  |  ${FAIL} fallidos"
echo "============================================================"
[[ "$FAIL" -gt 0 ]] && exit 1 || exit 0
