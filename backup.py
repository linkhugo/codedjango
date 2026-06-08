"""
Database backup views.

Provides:
  - backup_list    : Page showing existing backups, configuration, and manual trigger
  - backup_create  : POST — runs pg_dump and saves to backup_path
  - backup_download: GET  — streams a backup file to the browser
  - backup_delete  : POST — deletes a backup file
"""

import logging
import os
import subprocess
import shutil
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import FileResponse, Http404
from django.shortcuts import redirect, render
from django.utils import timezone as dj_timezone
from django.views.decorators.http import require_POST

from lb_manager.models import SiteSettings

logger = logging.getLogger(__name__)

# Common pg_dump locations searched when backup_pg_dump_path is blank
_PG_DUMP_SEARCH_PATHS = [
    '/usr/bin/pg_dump',
    '/usr/local/bin/pg_dump',
    '/opt/homebrew/bin/pg_dump',
    '/usr/lib/postgresql/16/bin/pg_dump',
    '/usr/lib/postgresql/15/bin/pg_dump',
    '/usr/lib/postgresql/14/bin/pg_dump',
    '/usr/lib/postgresql/13/bin/pg_dump',
    '/usr/pgsql-16/bin/pg_dump',
    '/usr/pgsql-15/bin/pg_dump',
    '/usr/pgsql-14/bin/pg_dump',
]


def _find_pg_dump(configured_path=''):
    """
    Return the pg_dump binary path to use.
    Priority: configured_path → shutil.which → known locations → None.
    """
    if configured_path:
        p = Path(configured_path)
        if p.is_file() and os.access(p, os.X_OK):
            return str(p)
        return None  # configured but not found — fail clearly

    found = shutil.which('pg_dump')
    if found:
        return found

    for candidate in _PG_DUMP_SEARCH_PATHS:
        if Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return candidate

    return None


def _get_cfg():
    """Return SiteSettings backup fields with defaults if no record exists."""
    cfg = SiteSettings.objects.first()
    if cfg:
        return (
            cfg.backup_path,
            cfg.backup_retention_days,
            cfg.backup_schedule,
            cfg.backup_pg_dump_path or '',
        )
    return '/backups', 30, '0 2 * * *', ''


def _list_backups(backup_path):
    """Return a list of dicts for each .dump file in backup_path, newest first."""
    p = Path(backup_path)
    if not p.exists():
        return []
    files = sorted(p.glob('*.dump'), key=lambda f: f.stat().st_mtime, reverse=True)
    result = []
    for f in files:
        stat = f.stat()
        result.append({
            'name': f.name,
            'size_mb': round(stat.st_size / 1_048_576, 2),
            'created': datetime.fromtimestamp(stat.st_mtime).strftime('%d/%m/%Y %H:%M'),
            'mtime': stat.st_mtime,
        })
    return result


def _purge_old_backups(backup_path, retention_days):
    """Delete .dump files older than retention_days. Returns count deleted."""
    p = Path(backup_path)
    if not p.exists():
        return 0
    cutoff = dj_timezone.now().timestamp() - retention_days * 86400
    deleted = 0
    for f in p.glob('*.dump'):
        if f.stat().st_mtime < cutoff:
            f.unlink()
            deleted += 1
    return deleted


@staff_member_required
def backup_list(request):
    """Backup management page — list files, show config, allow manual trigger."""
    backup_path, retention_days, schedule, pg_dump_cfg = _get_cfg()
    backups = _list_backups(backup_path)

    pg_dump_bin = _find_pg_dump(pg_dump_cfg)

    # Build the crontab entry the admin should add to the system cron
    manage_py = Path(settings.BASE_DIR) / 'manage.py'
    python_bin = shutil.which('python') or 'python'
    crontab_line = f'{schedule} {python_bin} {manage_py} backup_db'

    return render(request, 'lb_manager/backup.html', {
        'page_title': 'Database Backups',
        'backups': backups,
        'backup_path': backup_path,
        'retention_days': retention_days,
        'schedule': schedule,
        'pg_dump_bin': pg_dump_bin,
        'crontab_line': crontab_line,
        'total_size_mb': round(sum(b['size_mb'] for b in backups), 2),
    })


@staff_member_required
@require_POST
def backup_create(request):
    """Trigger a manual pg_dump backup."""
    backup_path, retention_days, _, pg_dump_cfg = _get_cfg()
    p = Path(backup_path)
    try:
        p.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        messages.error(request, f'Cannot create backup directory: {e}')
        return redirect('backup_list')

    pg_dump_bin = _find_pg_dump(pg_dump_cfg)
    if not pg_dump_bin:
        hint = (
            ' Set the path in Site Settings → pg_dump Binary Path, '
            'or install postgresql-client in the container.'
        )
        messages.error(request, f'pg_dump not found.{hint}')
        return redirect('backup_list')

    db = settings.DATABASES['default']
    filename = f"backup_{dj_timezone.localtime(dj_timezone.now()).strftime('%Y%m%d_%H%M%S')}.dump"
    filepath = p / filename

    env = os.environ.copy()
    env['PGPASSWORD'] = db.get('PASSWORD', '')

    cmd = [
        pg_dump_bin,
        '--format=custom',
        '--no-password',
        f"--host={db.get('HOST', 'localhost')}",
        f"--port={db.get('PORT', '5432')}",
        f"--username={db.get('USER', 'postgres')}",
        f"--file={filepath}",
        db.get('NAME', 'network_services'),
    ]

    try:
        result = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
        if result.returncode != 0:
            messages.error(request, f'pg_dump failed: {result.stderr.strip() or "unknown error"}')
            return redirect('backup_list')
    except subprocess.TimeoutExpired:
        messages.error(request, 'pg_dump timed out after 10 minutes.')
        return redirect('backup_list')

    # Purge old backups after a successful run
    deleted = _purge_old_backups(backup_path, retention_days)
    msg = f'Backup created: {filename}'
    if deleted:
        msg += f' ({deleted} old backup{"s" if deleted > 1 else ""} purged)'
    messages.success(request, msg)
    logger.info("Backup creado: %s por %s", filename, request.user)
    return redirect('backup_list')


@staff_member_required
def backup_download(request, filename):
    """Stream a backup file to the browser."""
    backup_path, _, _, _ = _get_cfg()
    filepath = Path(backup_path) / filename

    # Security: ensure the resolved path is inside backup_path
    try:
        filepath.resolve().relative_to(Path(backup_path).resolve())
    except ValueError as exc:
        raise Http404 from exc

    if not filepath.exists() or not filepath.is_file():
        raise Http404

    logger.info("Backup descargado: %s por %s", filename, request.user)
    response = FileResponse(
        open(filepath, 'rb'),  # pylint: disable=consider-using-with
        content_type='application/octet-stream',
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response['Content-Length'] = filepath.stat().st_size
    return response


@staff_member_required
@require_POST
def backup_delete(request, filename):
    """Delete a backup file."""
    backup_path, _, _, _ = _get_cfg()
    filepath = Path(backup_path) / filename

    # Security: ensure the resolved path is inside backup_path
    try:
        filepath.resolve().relative_to(Path(backup_path).resolve())
    except ValueError as exc:
        raise Http404 from exc

    if filepath.exists() and filepath.is_file() and filepath.suffix == '.dump':
        filepath.unlink()
        messages.success(request, f'Backup deleted: {filename}')
        logger.warning("Backup eliminado: %s por %s", filename, request.user)
    else:
        messages.error(request, 'Backup file not found.')
    return redirect('backup_list')
