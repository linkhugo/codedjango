#!/usr/bin/env bash
# get_vips_f5.sh - Virtual Servers via iControl REST API
# Uso: ./get_vips_f5.sh [archivo_hosts]   Default: ./hosts.txt
# Salida: <script_dir>/vips/<fqdn>.json

for cmd in curl jq; do
    command -v "$cmd" >/dev/null 2>&1 || { echo "ERROR: $cmd no encontrado."; exit 1; }
done

HOSTS_FILE="${1:-hosts.txt}"
if [ ! -f "$HOSTS_FILE" ]; then
    echo "ERROR: Archivo no encontrado: $HOSTS_FILE"; exit 1
fi
HOST_COUNT=$(grep -cE '^[^#[:space:]]' "$HOSTS_FILE" || true)
if [ "$HOST_COUNT" -eq 0 ]; then
    echo "ERROR: No hay hosts validos en $HOSTS_FILE"; exit 1
fi

echo "============================================================"
echo "  F5 Virtual Servers - $HOST_COUNT equipos desde $HOSTS_FILE"
echo "============================================================"
read -rp  "Usuario  : " F5_USER
read -rsp "Password : " F5_PASS
echo

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OUTPUT_DIR="$SCRIPT_DIR/vips"
mkdir -p "$OUTPUT_DIR"

_get() {
    curl -sk --connect-timeout 15 --max-time 120 \
        -u "$F5_USER:$F5_PASS" -H "Content-Type: application/json" "$1"
}

OK=0
FAIL=0

while IFS= read -r F5_HOST || [ -n "$F5_HOST" ]; do
    case "$F5_HOST" in ''|'#'*) continue;; esac

    echo ""
    echo "--- $F5_HOST ---"
    OUTPUT_FILE="$OUTPUT_DIR/$F5_HOST.json"

    echo "  -> Verificando failover..."
    FAILOVER_RAW=$(_get "https://$F5_HOST/mgmt/tm/cm/failover-status")
    FAILOVER_STATE=$(echo "$FAILOVER_RAW" | jq -r '.entries | to_entries[0].value.nestedStats.entries.status.description // "UNKNOWN"' 2>/dev/null)
    if [ -z "$FAILOVER_STATE" ]; then FAILOVER_STATE="UNKNOWN"; fi

    if [ "$FAILOVER_STATE" = "ACTIVE" ]; then
        echo "  [SKIP] Equipo ACTIVE - solo se extrae desde Standby"
        continue
    elif [ "$FAILOVER_STATE" = "STANDBY" ]; then
        echo "  [OK] Equipo STANDBY"
    else
        echo "  [SKIP] Estado desconocido: $FAILOVER_STATE"
        FAIL=$((FAIL + 1)); continue
    fi

    echo "  -> Obteniendo Virtual Servers..."
    VS_LIST=$(_get "https://$F5_HOST/mgmt/tm/ltm/virtual?\$top=10000&expandSubcollections=true")
    if ! echo "$VS_LIST" | jq -e '.items' >/dev/null 2>&1; then
        echo "  ERROR: No se pudo obtener VS."
        FAIL=$((FAIL + 1)); continue
    fi

    VS_COUNT=$(echo "$VS_LIST" | jq '.items | length')
    echo "  -> $VS_COUNT VS encontrados"

    echo "  -> Obteniendo estadisticas..."
    VS_STATS=$(_get "https://$F5_HOST/mgmt/tm/ltm/virtual/stats")

    echo "  -> Generando JSON..."
    if ! jq -n \
        --arg     fqdn  "$F5_HOST" \
        --argjson vs    "$VS_LIST" \
        --argjson stats "$VS_STATS" \
    '($stats.entries // {} | to_entries | map({
        key: (.value.nestedStats.entries["tmName"].description // ""),
        value: {
            availability_status: (.value.nestedStats.entries["status.availabilityState"].description // null),
            enabled_state:       (.value.nestedStats.entries["status.enabledState"].description // null)
        }
    }) | from_entries) as $sm |
    [$vs.items[] |
        ($sm[.fullPath] // {availability_status: null, enabled_state: null}) as $st |
        {
            name:            .name,
            full_path:       .fullPath,
            ltm_fqdn:        $fqdn,
            description:     (.description // null),
            destination:         (.destination // null),
            destination_address: (.destination // "" | if . == "" then null else split(":")[0] | split("/")[-1] | split("%")[0] end),
            destination_port:    (.destination // "" | if . == "" then null else split(":")[1] | tonumber? end),
            protocol:             (.ipProtocol // null),
            type:                 (.vsType // null),
            source_address:       (.source // null),
            source_port_behavior: (.sourcePort // null),
            enabled:             (if (.disabled // false) then "no" else "yes" end),
            availability_status: $st.availability_status,
            status_reason:       null,
            default_pool:        (.pool // null),
            snat_type:           (.sourceAddressTranslation.type // null),
            snat_pool:           (.sourceAddressTranslation.pool // null),
            persistence_profile: ((.persist // []) | if length > 0 then .[0].name else null end),
            profiles:            [(.profilesReference.items // [])[] | {name: .name, context: .context}],
            policies:            ([(.policies // [])[]?.name] | if length == 0 then null else join(",") end),
            translate_address:         (.translateAddress // null),
            translate_port:            (.translatePort // null),
            nat64_enabled:             (.nat64 // null),
            connection_limit:          (.connectionLimit // null),
            connection_mirror_enabled: (.mirror // null),
            rate_limit:                ((.rateLimit // "disabled") | if . == "disabled" then null else tonumber? end),
            rate_limit_mode:             (.rateLimitMode // null),
            rate_limit_destination_mask: (.rateLimitDstMask // null),
            cmp_enabled:                   (.cmpEnabled // null),
            cmp_mode:                      (.cmpMode // null),
            hardware_syn_cookie_instances: (.hwSynCookie // null),
            syn_cookies_status:            (.synCookiesStatus // null),
            auto_lasthop: (.autoLasthop // null),
            gtm_score:    (.gtmScore // null)
        }
    ]' > "$OUTPUT_FILE"; then
        echo "  ERROR: Fallo la transformacion JSON."
        FAIL=$((FAIL + 1)); continue
    fi

    SAVED=$(jq length "$OUTPUT_FILE")
    echo "  [OK] $SAVED VIPs -> $OUTPUT_FILE"
    OK=$((OK + 1))

done < "$HOSTS_FILE"

echo ""
echo "============================================================"
echo "  Resumen: $OK exitosos | $FAIL fallidos"
echo "============================================================"
[ "$FAIL" -gt 0 ] && exit 1 || exit 0
