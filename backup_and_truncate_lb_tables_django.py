"""
backup_and_truncate_lb_tables_django.py
Crea un backup completo de la base de datos (todos los modelos Django)
y luego trunca las tablas de datos de red que serán recargadas desde JSON.

Orden de operaciones:
  1. Backup con dumpdata — serializa TODOS los modelos Django a JSON gzipeado
     (no requiere pg_dump ni herramientas externas)
  2. Truncate de las tablas objetivo SOLO si el backup fue exitoso

Restaurar: python manage.py loaddata <archivo>.json.gz

Se ejecuta como subprocess desde ScriptRunConfig (django-q2).
"""
import datetime
import gzip
import io
import logging
import os
import sys
from pathlib import Path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "network_services.settings")

import django
django.setup()

from django.core.management import call_command
from django.db import connection

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stderr,
)

# ── Configuración ─────────────────────────────────────────────────────────────
BACKUP_DIR = Path("/var/backups/lb_manager")

# Tablas que se truncarán. El orden no importa porque se ejecutan
# en un solo statement sin dependencias de FK entre ellas.
TABLES_TO_TRUNCATE = [
    "client_ssl_profiles",
    "ltm_nodes",
    "pools",
    "snats_translations",
    "ssl_certs",
    "vips",
    "self_ips",
]


def run_backup() -> Path:
    """
    Serializa TODOS los modelos Django con dumpdata y escribe un archivo
    JSON comprimido con gzip. No requiere pg_dump ni herramientas externas.
    Retorna la ruta del archivo generado.
    Lanza RuntimeError si dumpdata falla.
    """
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = BACKUP_DIR / f"full_backup_{timestamp}.json.gz"

    logging.info("Iniciando backup (dumpdata completo) → %s", backup_file)

    buf = io.StringIO()
    try:
        # Sin argumentos de app: exporta TODOS los modelos de la base de datos
        call_command(
            "dumpdata",
            indent=2,
            stdout=buf,
            stderr=sys.stderr,
        )
    except Exception as exc:
        raise RuntimeError(f"dumpdata falló: {exc}") from exc

    data = buf.getvalue()
    if not data.strip() or data.strip() == "[]":
        raise RuntimeError("dumpdata retornó datos vacíos — backup inválido, abortando.")

    with gzip.open(backup_file, "wt", encoding="utf-8") as f:
        f.write(data)

    size_mb = backup_file.stat().st_size / (1024 * 1024)
    logging.info("Backup completado: %s (%.2f MB)", backup_file.name, size_mb)
    return backup_file


def truncate_tables() -> None:
    """
    Ejecuta TRUNCATE en las tablas objetivo en un único statement.
    RESTART IDENTITY reinicia las secuencias de auto-incremento.
    """
    table_list = ", ".join(f'"{t}"' for t in TABLES_TO_TRUNCATE)
    sql = f"TRUNCATE TABLE {table_list} RESTART IDENTITY"

    logging.info("Truncando tablas: %s", ", ".join(TABLES_TO_TRUNCATE))
    with connection.cursor() as cursor:
        cursor.execute(sql)
    logging.info("Truncate completado exitosamente.")


def main() -> None:
    # Paso 1: backup — si falla, el script termina sin truncar nada
    try:
        run_backup()
    except RuntimeError as exc:
        logging.error("Abortando: no se procederá con el truncate sin un backup válido. %s", exc)
        sys.exit(1)

    # Paso 2: truncate — solo si el backup fue exitoso
    try:
        truncate_tables()
    except Exception as exc:
        logging.error("Error durante el truncate: %s", exc)
        sys.exit(1)

    logging.info("Proceso finalizado: backup OK + tablas truncadas.")


if __name__ == "__main__":
    main()
