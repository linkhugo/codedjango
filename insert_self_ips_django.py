"""
insert_self_ips_django.py
Sincroniza Self IPs desde JSON hacia Django_DEV via ORM.
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

from lb_manager.models import SelfIP

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stderr,
)

PATH_JSON_FILES = Path("/var/lb/self_ips")

# ── Constantes de validación derivadas del modelo ────────────────────────────
INT_FIELDS = {"netmask_cidr"}
# allow_access_list es CharField(100) pero la F5 expone una lista JSON
# (ej. [{"name": "default:all"}]) — se serializa a string y se trunca a 100
JSONSTR_FIELDS = {"allow_access_list"}
MAX_LENGTHS = {
    "address":          32,
    "allow_access_list": 100,
    "floating":         100,
    "full_path":        100,
    "name":             100,
    "netmask":          100,
    "vlan":             100,
    "ltm_fqdn":         100,
}
SELFIP_FIELDS = list(MAX_LENGTHS.keys()) + list(INT_FIELDS)


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


def validate_selfip(raw: dict) -> dict:
    """
    Extrae y valida los campos de un dict JSON crudo.
    Lanza ValueError si faltan full_path o ltm_fqdn (unique constraint).
    """
    data: dict[str, Any] = {}
    for field in SELFIP_FIELDS:
        raw_value = raw.get(field)
        if field in INT_FIELDS:
            data[field] = _coerce_int(raw_value, field)
        elif field in JSONSTR_FIELDS:
            # Serializar lista/dict a JSON string y truncar al max_length
            serialized = _to_jsonstr(raw_value) if not isinstance(raw_value, str) else raw_value
            data[field] = _truncate(serialized, field, MAX_LENGTHS[field])
        else:
            data[field] = _truncate(raw_value, field, MAX_LENGTHS[field])

    if not data.get("full_path") or not data.get("ltm_fqdn"):
        raise ValueError(
            f"Self IP sin full_path o ltm_fqdn: "
            f"full_path={data.get('full_path')!r}, ltm_fqdn={data.get('ltm_fqdn')!r}"
        )
    return data


def upsert_selfip(data: dict) -> tuple[SelfIP, bool]:
    """
    Inserta o actualiza según unique constraint (full_path, ltm_fqdn).
    Retorna (instance, created).
    """
    lookup = {"full_path": data["full_path"], "ltm_fqdn": data["ltm_fqdn"]}
    defaults = {k: v for k, v in data.items() if k not in lookup}
    return SelfIP.objects.update_or_create(**lookup, defaults=defaults)


def process_json_file(file_path: Path) -> tuple[int, int]:
    """Procesa un archivo JSON. Retorna (insertados, actualizados)."""
    try:
        self_ips = json.loads(file_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logging.error("No se pudo leer '%s': %s", file_path, exc)
        return 0, 0

    if not isinstance(self_ips, list):
        logging.error("'%s' no contiene una lista JSON válida", file_path)
        return 0, 0

    inserted = updated = 0
    for raw in self_ips:
        try:
            data = validate_selfip(raw)
            _, created = upsert_selfip(data)
            if created:
                inserted += 1
            else:
                updated += 1
        except ValueError as exc:
            logging.warning("Self IP omitido en '%s': %s", file_path.name, exc)
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
