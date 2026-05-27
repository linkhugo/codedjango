"""
Modelos de configuración operativa del sistema.

Incluye: CMDBFieldConfig, CSVImportConfig, CSVColumnMapping,
         CSVTableUploadConfig, CSVTableColumnMapping, ScriptRunConfig,
         AnsibleGroupVar, AnsibleInventoryFile, DocEntry, DirectoryEntry.

Separado de models.py para mantener cada archivo por debajo de 1000 líneas.
"""
from datetime import date

from django.db import models


class CMDBFieldConfig(models.Model):
    """Valores aceptados para campos CMDB (assignment_group, support_group). Múltiples filas = OR."""

    class Field(models.TextChoices):
        ASSIGNMENT_GROUP = 'assignment_group', 'Assignment Group'
        SUPPORT_GROUP    = 'support_group',    'Support Group'
    field_name     = models.CharField(max_length=50, choices=Field.choices, verbose_name='CMDB Field')
    expected_value = models.CharField(max_length=255, verbose_name='Accepted Value')
    active         = models.BooleanField(default=True)

    class Meta:
        db_table = 'cmdb_field_config'
        verbose_name = 'CMDB Field Config'
        verbose_name_plural = 'CMDB Field Configs'
        ordering = ['field_name', 'expected_value']

    def __str__(self) -> str:
        return f'{self.get_field_name_display()} = "{self.expected_value}"'


class CSVTableUploadConfig(models.Model):
    """Declara una tabla Django como elegible para carga manual de CSV desde la UI."""

    label         = models.CharField(max_length=100, verbose_name='Label')
    model_path    = models.CharField(max_length=200, default='', verbose_name='Model')
    unique_fields = models.CharField(max_length=500, blank=True, default='', verbose_name='Unique Fields')
    active        = models.BooleanField(default=True)
    description   = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'csv_table_upload_config'
        verbose_name = 'CSV Table Upload Config'
        verbose_name_plural = 'CSV Table Upload Configs'
        ordering = ['label']
        unique_together = [('model_path',)]

    def __str__(self) -> str:
        return str(self.label)

    def get_model_class(self):
        """Return the Django model class for this config."""
        from django.apps import apps  # pylint: disable=import-outside-toplevel
        app_label, model_name = self.model_path.split('.')
        return apps.get_model(app_label, model_name)

    def get_unique_fields_list(self) -> list[str]:
        """Return unique_fields as a clean list."""
        return [f.strip() for f in self.unique_fields.split(',') if f.strip()]


class CSVTableColumnMapping(models.Model):
    """Mapea una columna CSV a un campo del modelo para un CSVTableUploadConfig."""

    config      = models.ForeignKey(CSVTableUploadConfig, on_delete=models.CASCADE, related_name='column_mappings')
    csv_column  = models.CharField(max_length=200)
    model_field = models.CharField(max_length=100)

    class Meta:
        db_table = 'csv_table_column_mapping'
        verbose_name = 'Column Mapping'
        verbose_name_plural = 'Column Mappings'
        unique_together = [('config', 'csv_column')]
        ordering = ['csv_column']

    def __str__(self) -> str:
        return f'{self.csv_column} → {self.model_field}'


class CSVImportConfig(models.Model):
    """Job programado de importación CSV. `file_path_template` soporta {date} como placeholder."""

    class RunStatus(models.TextChoices):
        NEVER = 'never', 'Never run'
        OK    = 'ok',    'OK'
        ERROR = 'error', 'Error'

    name               = models.CharField(max_length=100)
    table_config       = models.ForeignKey(
        CSVTableUploadConfig, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name='Type', related_name='import_configs', limit_choices_to={'active': True},
    )
    file_path_template = models.CharField(max_length=500, verbose_name='File path template')
    date_format        = models.CharField(max_length=30, default='%Y-%m-%d')
    cron_schedule      = models.CharField(max_length=50)
    active             = models.BooleanField(default=True)
    last_run_at        = models.DateTimeField(null=True, blank=True, editable=False)
    last_run_status    = models.CharField(max_length=10, choices=RunStatus.choices, default=RunStatus.NEVER, editable=False)
    last_run_message   = models.TextField(blank=True, default='', editable=False)

    class Meta:
        db_table = 'csv_import_config'
        verbose_name = 'CSV Import Config'
        verbose_name_plural = 'CSV Import Configs'
        ordering = ['name']

    def __str__(self) -> str:
        return str(self.name)


class CSVColumnMapping(models.Model):
    """Mapea una columna CSV a un campo del modelo para un CSVImportConfig."""

    config      = models.ForeignKey(CSVImportConfig, on_delete=models.CASCADE, related_name='column_mappings')
    csv_column  = models.CharField(max_length=100)
    model_field = models.CharField(max_length=100)

    class Meta:
        db_table = 'csv_column_mapping'
        verbose_name = 'Column Mapping'
        verbose_name_plural = 'Column Mappings'
        unique_together = [('config', 'csv_column')]
        ordering = ['csv_column']

    def __str__(self) -> str:
        return f'{self.csv_column} → {self.model_field}'


class ScriptRunConfig(models.Model):
    """Script Python ejecutado on-demand o en schedule vía django-q2."""

    class RunStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        OK      = 'ok',      'OK'
        ERROR   = 'error',   'Error'

    name             = models.CharField(max_length=120, unique=True)
    description      = models.TextField(blank=True)
    script_path      = models.CharField(max_length=500)
    run_date         = models.DateField(default=date.today)
    date_format      = models.CharField(max_length=30, default='%Y-%m-%d')
    cron_schedule    = models.CharField(max_length=100, blank=True)
    active           = models.BooleanField(default=True)
    last_run_at      = models.DateTimeField(null=True, blank=True, editable=False)
    last_run_status  = models.CharField(max_length=20, choices=RunStatus.choices, default=RunStatus.PENDING, editable=False)
    last_run_message = models.TextField(blank=True, editable=False)

    class Meta:
        db_table = 'script_run_config'
        verbose_name = 'Script Run Config'
        verbose_name_plural = 'Script Run Configs'
        ordering = ['name']

    def __str__(self) -> str:
        return str(self.name)


class AnsibleGroupVar(models.Model):
    """Variable clave-valor para un grupo de inventario Ansible."""

    group_name   = models.CharField(max_length=100)
    key          = models.CharField(max_length=100)
    value        = models.CharField(max_length=1000, blank=True)
    is_sensitive = models.BooleanField(default=False)
    notes        = models.CharField(max_length=200, blank=True)

    class Meta:
        db_table = 'ansible_group_var'
        verbose_name = 'Ansible Group Var'
        verbose_name_plural = 'Ansible Group Vars'
        unique_together = [('group_name', 'key')]
        ordering = ['group_name', 'key']

    def __str__(self) -> str:
        return f'{self.group_name} / {self.key}'


class AnsibleInventoryFile(models.Model):
    """Archivo de inventario INI de Ansible en el filesystem del servidor."""

    ENV_PRODUCTION = 'PRODUCTION'
    ENV_PRE        = 'PRE-PRODUCTION'
    ENV_DRP        = 'DRP'
    ENV_CHOICES = [
        (ENV_PRODUCTION, 'Production'),
        (ENV_PRE,        'Pre-Production'),
        (ENV_DRP,        'DRP'),
    ]
    name        = models.CharField(max_length=100)
    file_path   = models.CharField(max_length=500)
    environment = models.CharField(max_length=20, choices=ENV_CHOICES)
    description = models.CharField(max_length=300, blank=True)

    class Meta:
        db_table = 'ansible_inventory_file'
        verbose_name = 'Ansible Inventory File'
        verbose_name_plural = 'Ansible Inventory Files'
        ordering = ['environment', 'name']

    def __str__(self) -> str:
        return f'{self.name} ({self.get_environment_display()})'


class DocEntry(models.Model):
    """Catálogo de documentos con enlace a recursos externos."""

    name        = models.CharField(max_length=200, verbose_name='Nombre')
    description = models.TextField(blank=True, verbose_name='Descripción')
    url         = models.URLField(max_length=500, verbose_name='URL')
    category    = models.CharField(max_length=100, blank=True, verbose_name='Categoría')
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table            = 'doc_entry'
        ordering            = ['category', 'name']
        verbose_name        = 'Doc Entry'
        verbose_name_plural = 'Doc Entries'

    def __str__(self) -> str:
        return self.name


class DirectoryEntry(models.Model):
    """Directorio de números importantes (proveedores, soporte, emergencias)."""

    name        = models.CharField(max_length=200, verbose_name='Nombre / Proveedor')
    number      = models.CharField(max_length=100, verbose_name='Número')
    description = models.TextField(blank=True, verbose_name='Descripción')
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table            = 'directory_entry'
        ordering            = ['name']
        verbose_name        = 'Directory Entry'
        verbose_name_plural = 'Directory Entries'

    def __str__(self) -> str:
        return f"{self.name} — {self.number}"
