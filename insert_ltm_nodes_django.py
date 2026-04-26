"""
insert_ltm_nodes_django.py
Sincroniza LTM nodes desde JSON hacia Django_DEV via ORM.
Se ejecuta como subprocess desde ScriptRunConfig (django-q2).
"""
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

from lb_manager.models import LTMNode

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stderr,
)

PATH_JSON_FILES = Path("/var/lb/ltm_nodes")

# ── Constantes de validación derivadas del modelo ────────────────────────────
INT_FIELDS  = {"connection_limit", "dynamic_ratio", "rate_limit", "ratio"}
JSON_FIELDS = {"monitors"}
MAX_LENGTHS = {
    "address": 32,
    "ltm_fqdn": 100,
    "availability_status": 255,
    "enabled_status": 255,
    "full_path": 255,
    "monitor_rule": 255,
    "monitor_status": 255,
    "monitor_type": 255,
    "name": 255,
    "session_status": 255,
    "status_reason": 255,
}
NODE_FIELDS = list(MAX_LENGTHS.keys()) + list(INT_FIELDS) + list(JSON_FIELDS)


def _coerce_int(value: Any, field: str) -> int | None:
    """Convierte a int; registra warning y devuelve None si falla."""
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        logging.warning("Campo '%s': valor '%s' no convertible a int — se asigna None", field, value)
        return None


def _truncate(value: Any, field: str, max_len: int) -> str | None:
    """Trunca strings que excedan el max_length del modelo."""
    if value is None:
        return None
    s = str(value)
    if len(s) > max_len:
        logging.warning("Campo '%s': truncado de %d a %d caracteres", field, len(s), max_len)
        return s[:max_len]
    return s


def validate_node(raw: dict) -> dict:
    """
    Extrae y valida los campos de un dict JSON crudo.
    Lanza ValueError si faltan full_path o ltm_fqdn (unique constraint).
    """
    data: dict[str, Any] = {}
    for field in NODE_FIELDS:
        raw_value = raw.get(field)
        if field in INT_FIELDS:
            data[field] = _coerce_int(raw_value, field)
        elif field in JSON_FIELDS:
            data[field] = raw_value  # JSONField acepta list/dict directamente
        else:
            data[field] = _truncate(raw_value, field, MAX_LENGTHS[field])

    if not data.get("full_path") or not data.get("ltm_fqdn"):
        raise ValueError(
            f"Node sin full_path o ltm_fqdn: "
            f"full_path={data.get('full_path')!r}, ltm_fqdn={data.get('ltm_fqdn')!r}"
        )
    return data


def upsert_node(data: dict) -> tuple[LTMNode, bool]:
    """
    Inserta o actualiza según unique constraint (full_path, ltm_fqdn).
    Retorna (instance, created).
    """
    lookup = {"full_path": data["full_path"], "ltm_fqdn": data["ltm_fqdn"]}
    defaults = {k: v for k, v in data.items() if k not in lookup}
    return LTMNode.objects.update_or_create(**lookup, defaults=defaults)


def process_json_file(file_path: Path) -> tuple[int, int]:
    """Procesa un archivo JSON. Retorna (insertados, actualizados)."""
    try:
        nodes = json.loads(file_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logging.error("No se pudo leer '%s': %s", file_path, exc)
        return 0, 0

    if not isinstance(nodes, list):
        logging.error("'%s' no contiene una lista JSON válida", file_path)
        return 0, 0

    inserted = updated = 0
    for raw in nodes:
        try:
            data = validate_node(raw)
            _, created = upsert_node(data)
            if created:
                inserted += 1
            else:
                updated += 1
        except ValueError as exc:
            logging.warning("Node omitido en '%s': %s", file_path.name, exc)
        except Exception as exc:
            logging.error("Error inesperado en '%s': %s", file_path.name, exc)

    return inserted, updated


def main() -> None:
    if not PATH_JSON_FILES.is_dir():
        logging.error("Directorio no encontrado: %s", PATH_JSON_FILES)
        sys.exit(1)

    json_files = [f for f in PATH_JSON_FILES.iterdir() if f.suffix == ".json"]
    if not json_files:
        logging.warning("No se encontraron archivos .json en %s", PATH_JSON_FILES)
        return

    total_inserted = total_updated = 0
    for file_path in json_files:
        ins, upd = process_json_file(file_path)
        total_inserted += ins
        total_updated += upd
        logging.info("'%s' → %d insertados, %d actualizados", file_path.name, ins, upd)

    logging.info(
        "Finalizado: %d insertados, %d actualizados en total",
        total_inserted,
        total_updated,
    )


if __name__ == "__main__":
    main()
