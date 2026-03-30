"""
backup_and_truncate_lb_tables_django.py
Crea un backup completo de la base de datos PostgreSQL y luego trunca
las tablas de datos de red que serán recargadas desde JSON.

Orden de operaciones:
  1. Backup con pg_dump (formato custom, comprimido)
  2. Truncate de las tablas objetivo SOLO si el backup fue exitoso

Se ejecuta como subprocess desde ScriptRunConfig (django-q2).
"""
import datetime
import logging
import os
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "network_services.settings")

import django
django.setup()

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


def _get_db_settings() -> dict:
    """Extrae los parámetros de conexión desde Django settings."""
    s = connection.settings_dict
    return {
        "host":     s.get("HOST") or "localhost",
        "port":     str(s.get("PORT") or 5432),
        "dbname":   s["NAME"],
        "user":     s["USER"],
        "password": s.get("PASSWORD", ""),
    }


def run_backup(db: dict) -> Path:
    """
    Ejecuta pg_dump en formato custom (comprimido).
    Retorna la ruta del archivo generado.
    Lanza RuntimeError si pg_dump falla.
    """
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = BACKUP_DIR / f"lb_manager_{timestamp}.dump"

    cmd = [
        "pg_dump",
        "-h", db["host"],
        "-p", db["port"],
        "-U", db["user"],
        "-d", db["dbname"],
        "-F", "c",           # custom format: comprimido, restaurable con pg_restore
        "-f", str(backup_file),
    ]

    env = os.environ.copy()
    env["PGPASSWORD"] = db["password"]

    logging.info("Iniciando backup → %s", backup_file)
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)

    if result.returncode != 0:
        logging.error("pg_dump falló (código %d):\n%s", result.returncode, result.stderr)
        raise RuntimeError(f"pg_dump terminó con código {result.returncode}")

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
    db = _get_db_settings()

    # Paso 1: backup — si falla, el script termina sin truncar nada
    try:
        run_backup(db)
    except RuntimeError:
        logging.error("Abortando: no se procederá con el truncate sin un backup válido.")
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
