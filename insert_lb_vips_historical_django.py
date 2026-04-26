"""
insert_lb_vips_historical_django.py
Inserta snapshots históricos de VIPs desde JSON hacia Django_DEV via ORM.
Se ejecuta como subprocess desde ScriptRunConfig (django-q2).

Nota: LBVIPHistorical no tiene unique constraint — cada ejecución inserta
nuevos registros con la fecha del día. Es el comportamiento esperado para
una tabla de snapshots históricos.
"""
import datetime
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "network_services.settings")

import django
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
django.setup()

from lb_manager.models import LBVIPHistorical

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stderr,
)

PATH_JSON_FILES = Path("/var/lb/lb_vips_historical")

# ── Constantes de validación derivadas del modelo ────────────────────────────
INT_FIELDS = {
    "destination_port",
    "connection_limit",
    "rate_limit",
    "rate_limit_destination_mask",
    "hardware_syn_cookie_instances",
    "gtm_score",
}
# profiles → TextField, policies → CharField(100): ambos se serializan con json.dumps
JSONSTR_FIELDS = {"profiles", "policies"}
TEXT_FIELDS = {"description", "status_reason"}  # TextField — sin truncar
MAX_LENGTHS = {
    "name":                  100,
    "full_path":             100,
    "ltm_fqdn":              100,
    "destination":           100,
    "default_pool":          100,
    "snat_pool":             100,
    "persistence_profile":   100,
    "policies":              100,  # truncar json.dumps a 100
    "destination_address":    50,
    "source_address":         50,
    "snat_type":              50,
    "rate_limit_mode":        50,
    "cmp_mode":               50,
    "syn_cookies_status":     50,
    "auto_lasthop":           50,
    "availability_status":    50,
    "source_port_behavior":   50,
    "type":                   30,
    "enabled":                20,
    "protocol":               10,
    "translate_address":      10,
    "translate_port":         10,
    "nat64_enabled":          10,
    "connection_mirror_enabled": 10,
    "cmp_enabled":            10,
}
# profiles es TextField (sin max_length), se maneja por separado en JSONSTR_FIELDS
HIST_FIELDS = (
    list(MAX_LENGTHS.keys())
    + list(INT_FIELDS)
    + list(TEXT_FIELDS)
    + ["profiles"]  # JSONSTR TextField sin max_length
)


def _coerce_int(value: Any, field: str) -> int | None:
    """Convierte a int; registra warning y devuelve None si falla."""
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        logging.warning(
            "Campo '%s': valor '%s' no convertible a int — se asigna None", field, value
        )
        return None


def _truncate(value: Any, field: str, max_len: int) -> str | None:
    """Trunca strings que excedan el max_length del modelo."""
    if value is None:
        return None
    s = str(value)
    if len(s) > max_len:
        logging.warning(
            "Campo '%s': truncado de %d a %d caracteres", field, len(s), max_len
        )
        return s[:max_len]
    return s


def _to_jsonstr(value: Any) -> str | None:
    """Serializa a JSON string; devuelve None si value es None."""
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def validate_snapshot(raw: dict) -> dict:
    """
    Extrae y valida los campos de un dict JSON crudo.
    Lanza ValueError si faltan full_path o ltm_fqdn.
    """
    data: dict[str, Any] = {}
    for field in HIST_FIELDS:
        raw_value = raw.get(field)
        if field in INT_FIELDS:
            data[field] = _coerce_int(raw_value, field)
        elif field in TEXT_FIELDS:
            data[field] = str(raw_value) if raw_value is not None else None
        elif field == "profiles":
            # TextField → serializar como JSON string sin truncar
            data[field] = _to_jsonstr(raw_value)
        else:
            data[field] = _truncate(raw_value, field, MAX_LENGTHS[field])

    # policies en MAX_LENGTHS: serializar y truncar
    policies_raw = raw.get("policies")
    if policies_raw is not None and not isinstance(policies_raw, str):
        data["policies"] = _truncate(
            _to_jsonstr(policies_raw), "policies", MAX_LENGTHS["policies"]
        )
    # si ya fue procesado como string en el bucle anterior, dejarlo tal cual

    if not data.get("full_path") or not data.get("ltm_fqdn"):
        raise ValueError(
            f"Snapshot sin full_path o ltm_fqdn: "
            f"full_path={data.get('full_path')!r}, ltm_fqdn={data.get('ltm_fqdn')!r}"
        )
    return data


def process_json_file(file_path: Path, snapshot_date: datetime.date) -> int:
    """Procesa un archivo JSON. Retorna cantidad de registros insertados."""
    try:
        records = json.loads(file_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logging.error("No se pudo leer '%s': %s", file_path, exc)
        return 0

    if not isinstance(records, list):
        logging.error("'%s' no contiene una lista JSON válida", file_path)
        return 0

    inserted = 0
    for raw in records:
        try:
            data = validate_snapshot(raw)
            data["date"] = snapshot_date
            LBVIPHistorical.objects.create(**data)
            inserted += 1
        except ValueError as exc:
            logging.warning("Snapshot omitido en '%s': %s", file_path.name, exc)
        except Exception as exc:
            logging.error("Error inesperado en '%s': %s", file_path.name, exc)

    return inserted


def main() -> None:
    if not PATH_JSON_FILES.is_dir():
        logging.error("Directorio no encontrado: %s", PATH_JSON_FILES)
        sys.exit(1)

    json_files = [f for f in PATH_JSON_FILES.iterdir() if f.suffix == ".json"]
    if not json_files:
        logging.warning("No se encontraron archivos .json en %s", PATH_JSON_FILES)
        return

    snapshot_date = datetime.date.today()
    total_inserted = 0
    for file_path in json_files:
        ins = process_json_file(file_path, snapshot_date)
        total_inserted += ins
        logging.info("'%s' → %d insertados (fecha: %s)", file_path.name, ins, snapshot_date)

    logging.info("Finalizado: %d snapshots insertados en total", total_inserted)


if __name__ == "__main__":
    main()
