"""
insert_healthcheck_certificate_django.py
Inserta registros de healthcheck de certificados SSL/TLS desde un CSV hacia Django via ORM.

El CSV debe tener los headers (case-insensitive):
  Device, Expiration_Date, Days_Remaining, Certificate_type, Comments, Altername

La fecha se toma del día de ejecución.
Si Expiration_Date o Days_Remaining contienen "NA", Days_Remaining se inserta como 1000.

Usa update_or_create con (device, fecha, expiration_date) — upsert diario.

Uso:
  python insert_healthcheck_certificate_django.py                  # busca /var/ddi/health_check_YYYY-MM-DD.csv
  python insert_healthcheck_certificate_django.py /path/al/archivo.csv
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

from lb_manager.models import HealthCheckCertificate

PATH_CSV = Path("/var/ddi/")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stderr,
)

# ── Mapeo header CSV → campo del modelo ───────────────────────────────────────
HEADER_MAP: dict[str, str] = {
    "device":           "device",
    "expiration_date":  "expiration_date",
    "days_remaining":   "days_remaining",
    "certificates_type": "certificate_type",
    "comments":          "comments",
    "alternames":        "alternames",
}

NA_AS_INT = 1000  # valor a usar cuando days_remaining viene como "NA"

MAX_LENGTHS: dict[str, int] = {
    "device":           255,
    "expiration_date":  100,
    "certificate_type": 100,
}


# ── Helpers de coerción ────────────────────────────────────────────────────────
def _coerce_int_na(value: Any, field: str) -> int | None:
    """Convierte a int; si el valor es 'NA' o vacío devuelve NA_AS_INT."""
    if value in (None, "", "null"):
        return None
    if str(value).strip().upper() == "NA":
        logging.info("Campo '%s': 'NA' → %d", field, NA_AS_INT)
        return NA_AS_INT
    try:
        return int(float(value))
    except (ValueError, TypeError):
        logging.warning("Campo '%s': '%s' no convertible a int → None", field, value)
        return None


def _coerce_str(value: Any, field: str, max_len: int | None = None) -> str | None:
    if value in (None, "", "null"):
        return None
    s = str(value)
    if max_len and len(s) > max_len:
        logging.warning("Campo '%s': truncado de %d a %d chars", field, len(s), max_len)
        return s[:max_len]
    return s


# ── Normalización de headers ───────────────────────────────────────────────────
def _normalize_row(raw: dict) -> dict:
    return {
        HEADER_MAP[k.lower().strip()]: v
        for k, v in raw.items()
        if k.lower().strip() in HEADER_MAP
    }


# ── Validación de fila ─────────────────────────────────────────────────────────
def validate_row(raw: dict, fecha: datetime.date) -> dict:
    """
    Normaliza y coerciona todos los campos de una fila CSV.
    Lanza ValueError si device está vacío.
    """
    n = _normalize_row(raw)
    data: dict[str, Any] = {
        "fecha":            fecha,
        "device":           _coerce_str(n.get("device"), "device", 255),
        "expiration_date":  _coerce_str(n.get("expiration_date"), "expiration_date", 100),
        "days_remaining":   _coerce_int_na(n.get("days_remaining"), "days_remaining"),
        "certificate_type": _coerce_str(n.get("certificate_type"), "certificate_type", 100),
        "comments":         _coerce_str(n.get("comments"), "comments"),
        "alternames":       _coerce_str(n.get("alternames"), "alternames"),
    }

    if not data.get("device"):
        raise ValueError(f"Fila sin device: {raw}")

    return data


# ── Procesamiento del CSV ──────────────────────────────────────────────────────
def process_csv(file_path: Path, fecha: datetime.date) -> tuple[int, int]:
    """Procesa el CSV. Retorna (upserted, errors)."""
    upserted = 0
    errors   = 0

    with file_path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for line_num, raw in enumerate(reader, start=2):
            try:
                data             = validate_row(raw, fecha)
                device           = data.pop("device")
                fecha_row        = data.pop("fecha")
                expiration_date  = data.get("expiration_date")

                _, created = HealthCheckCertificate.objects.update_or_create(
                    device=device,
                    fecha=fecha_row,
                    expiration_date=expiration_date,
                    defaults=data,
                )
                action = "creado" if created else "actualizado"
                logging.info("Línea %d: %s (%s) → %s", line_num, device, fecha_row, action)
                upserted += 1
            except ValueError as exc:
                logging.warning("Línea %d omitida: %s", line_num, exc)
                errors += 1
            except Exception as exc:
                logging.error("Línea %d error inesperado: %s", line_num, exc)
                errors += 1

    return upserted, errors


def main() -> None:
    today = datetime.date.today()

    if len(sys.argv) >= 2:
        file_path = Path(sys.argv[1])
    else:
        fecha_str = today.strftime("%Y-%m-%d")
        file_path = PATH_CSV / f"health_check_{fecha_str}.csv"

    if not file_path.is_file():
        logging.error("Archivo no encontrado: %s", file_path)
        sys.exit(1)

    upserted, errors = process_csv(file_path, today)
    logging.info("Finalizado: %d insertados/actualizados, %d errores", upserted, errors)

    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
