#!/usr/bin/env bash
# =============================================================================
# get_vips_f5.sh
# Obtiene Virtual Servers de múltiples equipos F5 via iControl REST API
# y genera un archivo JSON por equipo, compatible con insert_vips_django.py
#
# Dependencias : curl, jq
# Uso          : ./get_vips_f5.sh [archivo_hosts]
#                Default: ./hosts.txt
# Salida       : /var/lb/vips/<fqdn>.json  (uno por host)
# =============================================================================

# ── Validar dependencias ──────────────────────────────────────────────────────
for cmd in curl jq; do
    command -v "$cmd" >/dev/null 2>&1 \
        || { echo "ERROR: '${cmd}' no encontrado. Instálalo antes de continuar."; exit 1; }
done

# ── Archivo de hosts ──────────────────────────────────────────────────────────
HOSTS_FILE="${1:-hosts.txt}"

if [[ ! -f "$HOSTS_FILE" ]]; then
    echo "ERROR: Archivo de hosts no encontrado: ${HOSTS_FILE}"
    echo "       Crea el archivo con un host por línea (# para comentarios)."
    exit 1
fi

# Contar hosts activos (no vacíos, no comentarios)
HOST_COUNT=$(grep -cE '^[^#[:space:]]' "$HOSTS_FILE" || true)
if [[ "$HOST_COUNT" -eq 0 ]]; then
    echo "ERROR: El archivo '${HOSTS_FILE}' no contiene hosts válidos."
    exit 1
fi

# ── Solicitar credenciales (una sola vez) ─────────────────────────────────────
echo "============================================================"
echo "  F5 Virtual Servers — Extracción via iControl REST API"
echo "  Hosts: ${HOST_COUNT} equipos desde ${HOSTS_FILE}"
echo "============================================================"
read -rp  "Usuario  : " F5_USER
read -rsp "Password : " F5_PASS
echo

OUTPUT_DIR="/var/lb/vips"
mkdir -p "$OUTPUT_DIR"

# ── Helper: GET autenticado ───────────────────────────────────────────────────
_get() {
    curl -sk \
        --connect-timeout 15 \
        --max-time 120 \
        -u "${F5_USER}:${F5_PASS}" \
        -H "Content-Type: application/json" \
        "$1"
}

# ── Loop por cada host ────────────────────────────────────────────────────────
OK=0
FAIL=0

while IFS= read -r F5_HOST || [[ -n "$F5_HOST" ]]; do
    # Ignorar líneas vacías y comentarios
    [[ -z "$F5_HOST" || "$F5_HOST" == \#* ]] && continue

    echo ""
    echo "------------------------------------------------------------"
    echo "  Host: ${F5_HOST}"
    echo "------------------------------------------------------------"

    OUTPUT_FILE="${OUTPUT_DIR}/${F5_HOST}.json"

    # ── 1. Obtener lista de Virtual Servers ───────────────────────────────────
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

    echo "  → Obteniendo Virtual Servers..."
    VS_LIST=$(_get "https://${F5_HOST}/mgmt/tm/ltm/virtual?\$top=10000&expandSubcollections=true")

    if ! echo "$VS_LIST" | jq -e '.items' >/dev/null 2>&1; then
        echo "  ERROR: No se pudo obtener la lista de VS. Verifica credenciales/conectividad."
        (( FAIL++ )) || true
        continue
    fi

    VS_COUNT=$(echo "$VS_LIST" | jq '.items | length')
    echo "  → ${VS_COUNT} Virtual Servers encontrados"

    # ── 2. Obtener estadísticas (availability + enabled state) ────────────────
    echo "  → Obteniendo estado de disponibilidad..."
    VS_STATS=$(_get "https://${F5_HOST}/mgmt/tm/ltm/virtual/stats")

    # ── 3. Transformar y combinar ─────────────────────────────────────────────
    echo "  → Generando JSON..."
    if ! jq -n \
        --arg     fqdn  "$F5_HOST" \
        --argjson vs    "$VS_LIST" \
        --argjson stats "$VS_STATS" \
    '
    # Mapa: fullPath → {availability_status, enabled_state}
    ($stats.entries // {} | to_entries | map({
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
            destination_address: (
                .destination // "" |
                if . == "" then null
                else split(":")[0] | split("/")[-1] | split("%")[0]
                end
            ),
            destination_port: (
                .destination // "" |
                if . == "" then null
                else split(":")[1] | tonumber?
                end
            ),
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
            policies:            (
                [(.policies // [])[]?.name] |
                if length == 0 then null else join(",") end
            ),

            translate_address: (.translateAddress // null),
            translate_port:    (.translatePort // null),
            nat64_enabled:     (.nat64 // null),

            connection_limit:          (.connectionLimit // null),
            connection_mirror_enabled: (.mirror // null),
            rate_limit: (
                (.rateLimit // "disabled") |
                if . == "disabled" then null else tonumber? end
            ),
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
        echo "  ERROR: Falló la transformación JSON para ${F5_HOST}."
        (( FAIL++ )) || true
        continue
    fi

    SAVED=$(jq length "$OUTPUT_FILE")
    echo "  ✓ ${SAVED} VIPs guardados en: ${OUTPUT_FILE}"
    (( OK++ )) || true

done < "$HOSTS_FILE"

# ── Resumen final ─────────────────────────────────────────────────────────────
echo ""
echo "============================================================"
echo "  Resumen: ${OK} exitosos  |  ${FAIL} fallidos"
echo "============================================================"

[[ "$FAIL" -gt 0 ]] && exit 1 || exit 0
