"""
insert_vips_tmsh_django.py
Inserta VIPs desde el output tmsh de F5 obtenido via SSH.

Estructura de archivos esperada:
  tmsh/virtual_servers/lba01.gotzeus.corp
  tmsh/virtual_servers/lba02.gotzeus.corp

El ltm_fqdn se toma del nombre del archivo.

Genera cada archivo en el F5 con:
  tmsh -q list ltm virtual one-line > /var/tmp/lba01.gotzeus.corp
  scp admin@<F5_HOST>:/var/tmp/lba01.gotzeus.corp ./tmsh/virtual_servers/

Uso:
  python insert_vips_tmsh_django.py                        # procesa todos los archivos en PATH_DIR
  python insert_vips_tmsh_django.py tmsh/virtual_servers/  # directorio específico
"""
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "network_services.settings")

import django
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
django.setup()

from lb_manager.models import VIP

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stderr,
)

PATH_DIR = Path("/var/lb/tmsh/virtual_servers")

# Línea tmsh one-line:  ltm virtual /Common/name { ... }
VIP_LINE_RE = re.compile(r'^ltm virtual (\S+)\s+\{(.+)\}\s*$')


# ── Helpers de extracción ──────────────────────────────────────────────────────
def _val(body: str, key: str) -> str | None:
    """Extrae valor simple: 'key valor'."""
    m = re.search(rf'\b{re.escape(key)}\s+(\S+)', body)
    return m.group(1) if m else None


def _nested(body: str, key: str) -> str | None:
    """Extrae contenido de bloque anidado: 'key { contenido }'."""
    m = re.search(rf'\b{re.escape(key)}\s+\{{([^}}]*)\}}', body)
    return m.group(1).strip() if m else None


def _truncate(value: str | None, max_len: int) -> str | None:
    if not value:
        return None
    return value[:max_len] if len(value) > max_len else value


def _parse_destination(dest: str | None) -> tuple[str | None, int | None]:
    """'/Common/10.0.0.1%0:80' → ('10.0.0.1', 80)."""
    if not dest:
        return None, None
    try:
        parts = dest.split(":")
        ip    = parts[0].split("/")[-1].split("%")[0]
        port  = int(parts[1]) if len(parts) > 1 else None
        return ip or None, port
    except Exception:
        return None, None


# ── Parseo de una línea tmsh ───────────────────────────────────────────────────
def parse_vip_line(line: str, ltm_fqdn: str) -> dict[str, Any] | None:
    """Parsea una línea tmsh one-line y retorna dict listo para el modelo."""
    m = VIP_LINE_RE.match(line.strip())
    if not m:
        return None

    full_path, body = m.group(1), m.group(2)
    name = full_path.split("/")[-1]

    dest                     = _val(body, "destination")
    dest_ip, dest_port       = _parse_destination(dest)

    # SNAT — bloque: source-address-translation { type automap pool /x }
    snat_block = _nested(body, "source-address-translation")
    snat_type  = _val(snat_block, "type")  if snat_block else None
    snat_pool  = _val(snat_block, "pool")  if snat_block else None

    # Persistence — bloque: persist { cookie { } }
    persist_block      = _nested(body, "persist")
    persistence_profile = persist_block.split()[0] if persist_block else None

    # enabled: si aparece "disabled" en el body, la VIP está deshabilitada
    enabled = "no" if re.search(r'\bdisabled\b', body) else "yes"

    conn_limit_raw = _val(body, "connection-limit")
    try:
        conn_limit = int(conn_limit_raw) if conn_limit_raw else None
    except ValueError:
        conn_limit = None

    return {
        "name":                   _truncate(name, 100),
        "full_path":              _truncate(full_path, 100),
        "ltm_fqdn":               _truncate(ltm_fqdn, 100),
        "description":            _val(body, "description"),
        "destination":            _truncate(dest, 100),
        "destination_address":    _truncate(dest_ip, 50),
        "destination_port":       dest_port,
        "protocol":               _truncate(_val(body, "ip-protocol"), 10),
        "type":                   _truncate(_val(body, "vs-type"), 30),
        "source_address":         _truncate(_val(body, "source"), 50),
        "source_port_behavior":   _truncate(_val(body, "source-port"), 50),
        "enabled":                enabled,
        "availability_status":    None,
        "status_reason":          None,
        "default_pool":           _truncate(_val(body, "pool"), 100),
        "snat_type":              _truncate(snat_type, 50),
        "snat_pool":              _truncate(snat_pool, 100),
        "persistence_profile":    _truncate(persistence_profile, 100),
        "profiles":               [],   # tmsh one-line no expande perfiles
        "policies":               None,
        "translate_address":      _truncate(_val(body, "translate-address"), 10),
        "translate_port":         _truncate(_val(body, "translate-port"), 10),
        "nat64_enabled":          _truncate(_val(body, "nat64"), 10),
        "connection_limit":       conn_limit,
        "connection_mirror_enabled": _truncate(_val(body, "mirror"), 10),
        "rate_limit":             None,
        "rate_limit_mode":        None,
        "rate_limit_destination_mask": None,
        "cmp_enabled":            _truncate(_val(body, "cmp-enabled"), 10),
        "cmp_mode":               _truncate(_val(body, "cmp"), 10),
        "hardware_syn_cookie_instances": None,
        "syn_cookies_status":     None,
        "auto_lasthop":           _truncate(_val(body, "auto-lasthop"), 50),
        "gtm_score":              None,
    }


# ── Procesamiento del archivo ──────────────────────────────────────────────────
def process_file(file_path: Path, ltm_fqdn: str) -> tuple[int, int]:
    inserted = updated = 0

    for line_num, line in enumerate(file_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.startswith("ltm virtual "):
            continue
        try:
            data = parse_vip_line(line, ltm_fqdn)
            if not data:
                continue
            if not data["full_path"]:
                logging.warning("Línea %d: sin full_path, omitida", line_num)
                continue

            lookup   = {"full_path": data["full_path"], "ltm_fqdn": data["ltm_fqdn"]}
            defaults = {k: v for k, v in data.items() if k not in lookup}
            _, created = VIP.objects.update_or_create(**lookup, defaults=defaults)
            inserted += created
            updated  += not created
        except Exception as exc:
            logging.error("Línea %d error: %s", line_num, exc)

    return inserted, updated


def main() -> None:
    base_dir = Path(sys.argv[1]) if len(sys.argv) >= 2 else PATH_DIR

    if not base_dir.is_dir():
        logging.error("Directorio no encontrado: %s", base_dir)
        sys.exit(1)

    files = [f for f in base_dir.iterdir() if f.is_file()]
    if not files:
        logging.warning("No se encontraron archivos en %s", base_dir)
        return

    total_ins = total_upd = 0
    for file_path in sorted(files):
        ltm_fqdn = file_path.name          # nombre del archivo = ltm_fqdn
        ins, upd = process_file(file_path, ltm_fqdn)
        total_ins += ins
        total_upd += upd
        logging.info("'%s' → %d insertados, %d actualizados", ltm_fqdn, ins, upd)

    logging.info("Finalizado: %d insertados, %d actualizados en total", total_ins, total_upd)


if __name__ == "__main__":
    main()
