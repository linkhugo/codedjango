"""
Async / periodic task definitions for lb_manager.

These callables are executed by the django-q2 worker process (manage.py qcluster).
Schedules are registered via manage.py setup_schedules and are visible/editable
in Django Admin → Django Q → Scheduled Tasks.

Available tasks
---------------
evaluate_health_rules_task()
    Runs the evaluate_health_rules management command.
    Default schedule: every day at 07:00 (configurable from admin).

evaluate_certificate_alerts_task()
    Runs the evaluate_certificate_alerts management command.
    Default schedule: every day at 08:00 (configurable from admin).

run_csv_import_task(config_id)
    Imports a CSV file into a HealthCheck model according to a CSVImportConfig
    row.  Schedules are created/updated automatically when a CSVImportConfig
    is saved from Admin → CSV Import Configs.

run_script_task(config_id)
    Executes an external Python script with a date argument according to a
    ScriptRunConfig row.  Captures stdout/stderr and stores the result in
    last_run_message.  Schedules are created/updated automatically when a
    ScriptRunConfig is saved from Admin → Script Run Configs.
"""
import logging
import subprocess
import sys

from django.core.management import call_command
from django.utils import timezone

logger = logging.getLogger(__name__)


def evaluate_health_rules_task():
    """
    Invoke the evaluate_health_rules management command as a background task.

    The command queries the latest F5 health snapshots, compares them against
    HealthRule thresholds, and opens BitacoraHealth tickets when a rule fires.
    Duplicate-suppression logic inside the command prevents double-ticketing.
    """
    logger.info('django-q2: starting evaluate_health_rules task')
    try:
        call_command('evaluate_health_rules')
        logger.info('django-q2: evaluate_health_rules task completed')
    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception('django-q2: evaluate_health_rules task failed')
        raise  # re-raise so django-q2 marks the task as failed


def evaluate_certificate_alerts_task():
    """
    Invoke the evaluate_certificate_alerts management command as a background task.

    Checks today's HealthCheckCertificate snapshots for expired or expiring
    certificates and opens BitacoraHealth tickets for each affected device.
    Duplicate-suppression logic inside the command prevents double-ticketing.
    """
    logger.info('django-q2: starting evaluate_certificate_alerts task')
    try:
        call_command('evaluate_certificate_alerts')
        logger.info('django-q2: evaluate_certificate_alerts task completed')
    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception('django-q2: evaluate_certificate_alerts task failed')
        raise  # re-raise so django-q2 marks the task as failed


def run_csv_import_task(config_id):
    """
    Import a CSV file into a HealthCheck model using a CSVImportConfig row.

    Updates last_run_at, last_run_status, and last_run_message on the config
    so operators can see the result from Admin → CSV Import Configs.
    """
    from lb_manager.models import CSVImportConfig  # pylint: disable=import-outside-toplevel
    from lb_manager.csv_importers import import_csv  # pylint: disable=import-outside-toplevel

    logger.info('django-q2: starting csv import task for config_id=%s', config_id)
    try:
        config = CSVImportConfig.objects.get(pk=config_id)
    except CSVImportConfig.DoesNotExist:
        logger.error('django-q2: CSVImportConfig pk=%s not found — task aborted', config_id)
        return

    try:
        inserted, updated, errors = import_csv(config)
        msg = f'inserted={inserted}, updated={updated}, errors={errors}'
        status = CSVImportConfig.RunStatus.OK
        logger.info('django-q2: csv import [%s] done: %s', config.name, msg)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        msg = str(exc)
        status = CSVImportConfig.RunStatus.ERROR
        logger.exception('django-q2: csv import [%s] failed: %s', config.name, exc)

    CSVImportConfig.objects.filter(pk=config_id).update(
        last_run_at=timezone.now(),
        last_run_status=status,
        last_run_message=msg,
    )


def run_script_task(config_id):
    """
    Execute an external Python script defined in a ScriptRunConfig row.

    The script is called as:
        python <script_path> <run_date>
    where run_date is formatted using config.date_format.

    stdout and stderr are captured (up to 4 000 chars) and saved to
    last_run_message.  A non-zero exit code sets status to ERROR.
    """
    from lb_manager.models import ScriptRunConfig  # pylint: disable=import-outside-toplevel

    logger.info('django-q2: starting script task for config_id=%s', config_id)
    try:
        config = ScriptRunConfig.objects.get(pk=config_id)
    except ScriptRunConfig.DoesNotExist:
        logger.error('django-q2: ScriptRunConfig pk=%s not found — task aborted', config_id)
        return

    logger.info('django-q2: running script [%s]', config.name)

    try:
        result = subprocess.run(
            [sys.executable, config.script_path],
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
        combined = (result.stdout + result.stderr).strip()
        msg = f'exit_code={result.returncode}\n{combined}'[:4000]
        if result.returncode == 0:
            status = ScriptRunConfig.RunStatus.OK
            logger.info('django-q2: script [%s] exited OK', config.name)
        else:
            status = ScriptRunConfig.RunStatus.ERROR
            logger.error(
                'django-q2: script [%s] exited with code %d',
                config.name, result.returncode,
            )
    except subprocess.TimeoutExpired:
        msg = 'ERROR: script timed out after 600 seconds'
        status = ScriptRunConfig.RunStatus.ERROR
        logger.error('django-q2: script [%s] timed out', config.name)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        msg = str(exc)
        status = ScriptRunConfig.RunStatus.ERROR
        logger.exception('django-q2: script [%s] failed: %s', config.name, exc)

    ScriptRunConfig.objects.filter(pk=config_id).update(
        last_run_at=timezone.now(),
        last_run_status=status,
        last_run_message=msg,
    )
