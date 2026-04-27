#!/usr/bin/env bash
# =============================================================================
# get_self_ips_f5.sh
# Obtiene Self IPs de múltiples equipos F5 via iControl REST API
# Salida: /var/lb/self_ips/<fqdn>.json  (compatible con insert_self_ips_django.py)
# Uso   : ./get_self_ips_f5.sh [archivo_hosts]   Default: ./hosts.txt
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
echo "  F5 Self IPs — Extracción via iControl REST API"
echo "  Hosts: ${HOST_COUNT} equipos desde ${HOSTS_FILE}"
echo "============================================================"
read -rp  "Usuario  : " F5_USER
read -rsp "Password : " F5_PASS
echo

OUTPUT_DIR="/var/lb/self_ips"
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

    echo "  → Obteniendo Self IPs..."
    SELFIPS=$(_get "https://${F5_HOST}/mgmt/tm/net/self?\$top=10000")

    if ! echo "$SELFIPS" | jq -e '.items' >/dev/null 2>&1; then
        echo "  ERROR: No se pudo obtener Self IPs. Verifica credenciales/conectividad."
        (( FAIL++ )) || true; continue
    fi

    echo "  → Generando JSON..."
    if ! jq -n \
        --arg     fqdn    "$F5_HOST" \
        --argjson selfips "$SELFIPS" \
    '[$selfips.items[] | {
        name:      .name,
        full_path: .fullPath,
        ltm_fqdn:  $fqdn,
        address:   (.address | split("%")[0]),
        netmask:   (.netmask // null),
        netmask_cidr: (
            .address | if test("/") then split("/")[1] | tonumber? else null end
        ),
        vlan:      (.vlan // null),
        floating:  (.floating // null),
        allow_access_list: (
            (.allowService // []) | tojson
        )
    }]' > "$OUTPUT_FILE"; then
        echo "  ERROR: Falló la transformación JSON para ${F5_HOST}."
        (( FAIL++ )) || true; continue
    fi

    SAVED=$(jq length "$OUTPUT_FILE")
    echo "  ✓ ${SAVED} Self IPs guardados en: ${OUTPUT_FILE}"
    (( OK++ )) || true

done < "$HOSTS_FILE"

echo ""
echo "============================================================"
echo "  Resumen: ${OK} exitosos  |  ${FAIL} fallidos"
echo "============================================================"
[[ "$FAIL" -gt 0 ]] && exit 1 || exit 0
