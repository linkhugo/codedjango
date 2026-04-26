"""
insert_ssl_certs_django.py
Sincroniza certificados SSL desde JSON hacia Django_DEV via ORM.
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

from lb_manager.models import SSLCert

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stderr,
)

PATH_JSON_FILES = Path("/var/lb/ssl_certs")

# ── Constantes de validación derivadas del modelo ────────────────────────────
INT_FIELDS = {"expiration_timestamp", "key_size"}  # BigIntegerField / PositiveSmallIntegerField
TEXT_FIELDS = {"subject_alternative_name"}  # TextField — sin truncar
MAX_LENGTHS = {
    "create_time":      100,
    "expiration_date":  100,
    "last_update_time": 100,
    "ltm_fqdn":         100,
    "fingerprint":      128,
    "sha1_checksum":    128,
    "key_type":          50,
    "name":             255,
    "full_path":        255,
    "issuer":           500,
    "subject":          500,
    "is_bundle":         10,
}
CERT_FIELDS = (
    list(MAX_LENGTHS.keys())
    + list(INT_FIELDS)
    + list(TEXT_FIELDS)
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


def validate_cert(raw: dict) -> dict:
    """
    Extrae y valida los campos de un dict JSON crudo.
    Lanza ValueError si faltan full_path o ltm_fqdn (unique constraint).
    """
    data: dict[str, Any] = {}
    for field in CERT_FIELDS:
        raw_value = raw.get(field)
        if field in INT_FIELDS:
            data[field] = _coerce_int(raw_value, field)
        elif field in TEXT_FIELDS:
            data[field] = str(raw_value) if raw_value is not None else None
        else:
            data[field] = _truncate(raw_value, field, MAX_LENGTHS[field])

    if not data.get("full_path") or not data.get("ltm_fqdn"):
        raise ValueError(
            f"Certificado sin full_path o ltm_fqdn: "
            f"full_path={data.get('full_path')!r}, ltm_fqdn={data.get('ltm_fqdn')!r}"
        )
    return data


def upsert_cert(data: dict) -> tuple[SSLCert, bool]:
    """
    Inserta o actualiza según unique constraint (full_path, ltm_fqdn).
    Retorna (instance, created).
    """
    lookup = {"full_path": data["full_path"], "ltm_fqdn": data["ltm_fqdn"]}
    defaults = {k: v for k, v in data.items() if k not in lookup}
    return SSLCert.objects.update_or_create(**lookup, defaults=defaults)


def process_json_file(file_path: Path) -> tuple[int, int]:
    """Procesa un archivo JSON. Retorna (insertados, actualizados)."""
    try:
        certs = json.loads(file_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logging.error("No se pudo leer '%s': %s", file_path, exc)
        return 0, 0

    if not isinstance(certs, list):
        logging.error("'%s' no contiene una lista JSON válida", file_path)
        return 0, 0

    inserted = updated = 0
    for raw in certs:
        try:
            data = validate_cert(raw)
            _, created = upsert_cert(data)
            if created:
                inserted += 1
            else:
                updated += 1
        except ValueError as exc:
            logging.warning("Certificado omitido en '%s': %s", file_path.name, exc)
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
