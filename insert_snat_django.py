"""
insert_snat_django.py
Sincroniza SNAT Translations desde JSON hacia Django_DEV via ORM.
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

from lb_manager.models import SNATTranslation

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stderr,
)

PATH_JSON_FILES = Path("/var/lb/snat")

# ── Constantes de validación derivadas del modelo ────────────────────────────
# Unique constraint: (name, ltm_fqdn) — distinto al patrón general (full_path, ltm_fqdn)
MAX_LENGTHS = {
    "snat":     100,
    "ltm_fqdn": 100,
    "name":     100,
}
SNAT_FIELDS = list(MAX_LENGTHS.keys())


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


def validate_snat(raw: dict) -> dict:
    """
    Extrae y valida los campos de un dict JSON crudo.
    Lanza ValueError si faltan name o ltm_fqdn (unique constraint).
    """
    data: dict[str, Any] = {}
    for field in SNAT_FIELDS:
        data[field] = _truncate(raw.get(field), field, MAX_LENGTHS[field])

    if not data.get("name") or not data.get("ltm_fqdn"):
        raise ValueError(
            f"SNAT sin name o ltm_fqdn: "
            f"name={data.get('name')!r}, ltm_fqdn={data.get('ltm_fqdn')!r}"
        )
    return data


def upsert_snat(data: dict) -> tuple[SNATTranslation, bool]:
    """
    Inserta o actualiza según unique constraint (name, ltm_fqdn).
    Retorna (instance, created).
    """
    lookup = {"name": data["name"], "ltm_fqdn": data["ltm_fqdn"]}
    defaults = {k: v for k, v in data.items() if k not in lookup}
    return SNATTranslation.objects.update_or_create(**lookup, defaults=defaults)


def process_json_file(file_path: Path) -> tuple[int, int]:
    """Procesa un archivo JSON. Retorna (insertados, actualizados)."""
    try:
        snats = json.loads(file_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logging.error("No se pudo leer '%s': %s", file_path, exc)
        return 0, 0

    if not isinstance(snats, list):
        logging.error("'%s' no contiene una lista JSON válida", file_path)
        return 0, 0

    inserted = updated = 0
    for raw in snats:
        try:
            data = validate_snat(raw)
            _, created = upsert_snat(data)
            if created:
                inserted += 1
            else:
                updated += 1
        except ValueError as exc:
            logging.warning("SNAT omitido en '%s': %s", file_path.name, exc)
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
