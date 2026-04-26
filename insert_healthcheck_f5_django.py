"""
insert_healthcheck_f5_django.py
Inserta registros de healthcheck F5 desde un CSV hacia Django_DEV via ORM.

El CSV debe tener el header:
  fqdn,uptime,failover,failsafe,sync,ltm_logs,cpu_usage,cpu_plane_use,
  cpu_analysis_use,top_connections,tmm_memory,tmm_memory_used,nodes,nodes_up,
  nodes_down,nodes_user_down,vips,vips_up,vips_offline,vips_unknown,fecha,
  company,last_folder,file_backup,backup_path

Usa update_or_create con unique constraint (fqdn, fecha) — upsert diario.

Uso:
  python insert_healthcheck_f5_django.py                  # busca healthcheck_f5_YYYY-MM-DD.csv
  python insert_healthcheck_f5_django.py /path/al/archivo.csv
"""
import csv
import datetime
import logging
import sys
import os
from pathlib import Path
from typing import Any

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "network_services.settings")

import django
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
django.setup()

from lb_manager.models import HealthCheckF5

PATH_CSV = Path("/var/lb/healthcheck/")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stderr,
)

# ── Campos por tipo ────────────────────────────────────────────────────────────
INT_FIELDS = {
    "ltm_logs", "cpu_usage", "cpu_plane_use", "cpu_analysis_use",
    "nodes", "nodes_up", "nodes_down", "nodes_user_down",
    "vips", "vips_up", "vips_offline", "vips_unknown",
}
FLOAT_FIELDS = {"uptime"}
DATE_FIELDS = {"fecha"}

MAX_LENGTHS = {
    "fqdn":             100,
    "failover":         100,
    "failsafe":         100,
    "sync":             100,
    "top_connections":  100,
    "tmm_memory":       100,
    "tmm_memory_used":  100,
    "company":          100,
    "last_folder":      100,
    "file_backup":       15,
    "backup_path":      255,
}

# Campos que se insertan en el modelo (excluye id)
MODEL_FIELDS = (
    list(INT_FIELDS) + list(FLOAT_FIELDS) + list(DATE_FIELDS) + list(MAX_LENGTHS.keys())
)


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
        return datetime.date.fromisoformat(str(value))
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


# ── Validación de fila ─────────────────────────────────────────────────────────
def validate_row(raw: dict) -> dict:
    """
    Extrae y coerciona todos los campos de una fila CSV.
    Lanza ValueError si fqdn o fecha están vacíos.
    """
    data: dict[str, Any] = {}

    for field in MODEL_FIELDS:
        raw_value = raw.get(field)
        if field in INT_FIELDS:
            data[field] = _coerce_int(raw_value, field)
        elif field in FLOAT_FIELDS:
            data[field] = _coerce_float(raw_value, field)
        elif field in DATE_FIELDS:
            data[field] = _coerce_date(raw_value, field)
        else:
            data[field] = _truncate(raw_value, field, MAX_LENGTHS[field])

    if not data.get("fqdn"):
        raise ValueError(f"Fila sin fqdn: {raw}")
    if data.get("fecha") is None:
        raise ValueError(f"Fila sin fecha válida: {raw}")

    return data


# ── Procesamiento del CSV ──────────────────────────────────────────────────────
def process_csv(file_path: Path) -> tuple[int, int]:
    """Procesa el CSV. Retorna (upserted, errors)."""
    upserted = 0
    errors = 0

    with file_path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for line_num, raw in enumerate(reader, start=2):
            try:
                data = validate_row(raw)
                fqdn = data.pop("fqdn")
                fecha = data.pop("fecha")
                _, created = HealthCheckF5.objects.update_or_create(
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
        today = datetime.date.today().strftime("%Y-%m-%d")
        file_path = PATH_CSV / f"healthcheck_f5_{today}.csv"

    if not file_path.is_file():
        logging.error("Archivo no encontrado: %s", file_path)
        sys.exit(1)

    upserted, errors = process_csv(file_path)
    logging.info("Finalizado: %d insertados/actualizados, %d errores", upserted, errors)

    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
