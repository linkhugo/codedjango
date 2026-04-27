"""
insert_healthcheck_dns_django.py
Inserta registros de healthcheck DNS desde un CSV hacia Django via ORM.

El CSV debe tener los headers (case-insensitive):
  FQDN, UPTIME, NPROC, MAX_RECURSIVE_CLIENTS,
  USER_NICE_SYSTEM_IOWAIT_STEAL_IDLE, MEMORY_TOTAL, MEMORY_FREE,
  SWAP_TOTAL, SWAP_FREE, NAMED, NTP, FILESYSTEMS, BACKUP, FECHA, COMPANY

Usa update_or_create con unique constraint (fqdn, fecha) — upsert diario.

Uso:
  python insert_healthcheck_dns_django.py                   # busca /var/ddi/health_check_YYYY-MM-DD.csv
  python insert_healthcheck_dns_django.py /path/al/archivo.csv
"""
import csv
import datetime
import logging
import os
import sys
from pathlib import Path
from typing import Any

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "network_services.settings")

import django
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
django.setup()

from lb_manager.models import HealthCheckDNS

PATH_CSV = Path("/var/ddi/")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stderr,
)

# ── Mapeo header CSV → campo del modelo ───────────────────────────────────────
HEADER_MAP: dict[str, str] = {
    "fqdn":                               "fqdn",
    "uptime":                             "uptime",
    "nproc":                              "nproc",
    "max_recursive_clients":              "max_recursive_clients",
    "user_nice_system_iowait_steal_idle": "user_nice_iowait_steal_idle",
    "memory_total":                       "memory_total",
    "memory_free":                        "memory_free",
    "swap_total":                         "swap_total",
    "swap_free":                          "swap_free",
    "named":                              "named",
    "ntp":                                "ntp",
    "filesystems":                        "filesystems",
    "backup":                             "backup",
    "fecha":                              "fecha",
    "company":                            "company",
}

# ── Campos por tipo ────────────────────────────────────────────────────────────
INT_FIELDS   = {"nproc", "memory_total", "memory_free", "swap_total", "swap_free"}
FLOAT_FIELDS = {"uptime"}
DATE_FIELDS  = {"fecha"}

MAX_LENGTHS: dict[str, int] = {
    "fqdn":                       100,
    "max_recursive_clients":      100,
    "user_nice_iowait_steal_idle": 100,
    "named":                      100,
    "ntp":                        100,
    "filesystems":                100,
    "company":                    100,
    "backup":                      15,
}

MODEL_FIELDS = list(INT_FIELDS | FLOAT_FIELDS | DATE_FIELDS | MAX_LENGTHS.keys())


# ── Helpers de coerción ────────────────────────────────────────────────────────
def _coerce_int(value: Any, field: str) -> int | None:
    if value in (None, "", "null"):
        return None
    try:
        return int(float(value))
    except (ValueError, TypeError):
        logging.warning("Campo '%s': '%s' no convertible a int → None", field, value)
        return None


def _coerce_float(value: Any, field: str) -> float | None:
    if value in (None, "", "null"):
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        logging.warning("Campo '%s': '%s' no convertible a float → None", field, value)
        return None


def _coerce_date(value: Any, field: str) -> datetime.date | None:
    if value in (None, "", "null"):
        return None
    try:
        return datetime.date.fromisoformat(str(value).strip())
    except ValueError:
        logging.warning("Campo '%s': '%s' no es fecha ISO válida → None", field, value)
        return None


def _truncate(value: Any, field: str, max_len: int) -> str | None:
    if value in (None, "", "null"):
        return None
    s = str(value)
    if len(s) > max_len:
        logging.warning("Campo '%s': truncado de %d a %d chars", field, len(s), max_len)
        return s[:max_len]
    return s


# ── Normalización de headers ───────────────────────────────────────────────────
def _normalize_row(raw: dict) -> dict:
    """Convierte headers CSV (mayúsculas) a nombres de campo del modelo."""
    return {
        HEADER_MAP[k.lower()]: v
        for k, v in raw.items()
        if k.lower() in HEADER_MAP
    }


# ── Validación de fila ─────────────────────────────────────────────────────────
def validate_row(raw: dict) -> dict:
    """
    Normaliza y coerciona todos los campos de una fila CSV.
    Lanza ValueError si fqdn o fecha están vacíos.
    """
    normalized = _normalize_row(raw)
    data: dict[str, Any] = {}

    for field in MODEL_FIELDS:
        value = normalized.get(field)
        if field in INT_FIELDS:
            data[field] = _coerce_int(value, field)
        elif field in FLOAT_FIELDS:
            data[field] = _coerce_float(value, field)
        elif field in DATE_FIELDS:
            data[field] = _coerce_date(value, field)
        else:
            data[field] = _truncate(value, field, MAX_LENGTHS[field])

    if not data.get("fqdn"):
        raise ValueError(f"Fila sin fqdn: {raw}")
    if data.get("fecha") is None:
        raise ValueError(f"Fila sin fecha válida: {raw}")

    return data


# ── Procesamiento del CSV ──────────────────────────────────────────────────────
def process_csv(file_path: Path) -> tuple[int, int]:
    """Procesa el CSV. Retorna (upserted, errors)."""
    upserted = 0
    errors   = 0

    with file_path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for line_num, raw in enumerate(reader, start=2):
            try:
                data  = validate_row(raw)
                fqdn  = data.pop("fqdn")
                fecha = data.pop("fecha")
                _, created = HealthCheckDNS.objects.update_or_create(
                    fqdn=fqdn,
                    fecha=fecha,
                    defaults=data,
                )
                action = "creado" if created else "actualizado"
                logging.info("Línea %d: %s (%s) → %s", line_num, fqdn, fecha, action)
                upserted += 1
            except ValueError as exc:
                logging.warning("Línea %d omitida: %s", line_num, exc)
                errors += 1
            except Exception as exc:
                logging.error("Línea %d error inesperado: %s", line_num, exc)
                errors += 1

    return upserted, errors


def main() -> None:
    if len(sys.argv) >= 2:
        file_path = Path(sys.argv[1])
    else:
        today     = datetime.date.today().strftime("%Y-%m-%d")
        file_path = PATH_CSV / f"health_check_{today}.csv"

    if not file_path.is_file():
        logging.error("Archivo no encontrado: %s", file_path)
        sys.exit(1)

    upserted, errors = process_csv(file_path)
    logging.info("Finalizado: %d insertados/actualizados, %d errores", upserted, errors)

    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
