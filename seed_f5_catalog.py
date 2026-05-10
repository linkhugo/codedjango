"""
Management command: seed_f5_catalog

Extrae los valores únicos de version y model de las tablas lb_physical y
lb_guest para poblar los catálogos F5SoftwareVersion y F5HardwareModel,
y luego enlaza cada registro existente con su FK correspondiente.

Uso (una sola vez, después de aplicar la migración 0012):
    python manage.py seed_f5_catalog

Es seguro ejecutarlo más de una vez: usa get_or_create y no borra datos.
"""

from django.core.management.base import BaseCommand, CommandError

from lb_manager.models import F5HardwareModel, F5SoftwareVersion, LBGuest, LBPhysical


class Command(BaseCommand):
    """Seed F5 software version and hardware model catalogs from existing device data."""

    help = 'Puebla F5SoftwareVersion y F5HardwareModel desde datos existentes en lb_physical/lb_guest y enlaza los FKs.'

    def handle(self, *args: object, **options: object) -> None:
        """Execute the seed command."""
        self.stdout.write('=== seed_f5_catalog ===\n')

        # 1. Collect unique versions
        versions: set[str] = set()
        for v in LBPhysical.objects.exclude(version='').values_list('version', flat=True):
            versions.add(v.strip())
        for v in LBGuest.objects.filter(version__isnull=False).exclude(version='').values_list('version', flat=True):
            versions.add(v.strip())
        versions.discard('')

        created_v = 0
        for v in sorted(versions):
            _, is_new = F5SoftwareVersion.objects.get_or_create(version=v)
            if is_new:
                created_v += 1
        self.stdout.write(f'  F5SoftwareVersion: {len(versions)} entradas únicas, {created_v} creadas.')

        # 2. Collect unique hardware models
        models_set: set[str] = set()
        for m in LBPhysical.objects.exclude(model='').values_list('model', flat=True):
            models_set.add(m.strip())
        for m in LBGuest.objects.filter(model__isnull=False).exclude(model='').values_list('model', flat=True):
            models_set.add(m.strip())
        models_set.discard('')

        created_m = 0
        for m in sorted(models_set):
            _, is_new = F5HardwareModel.objects.get_or_create(name=m)
            if is_new:
                created_m += 1
        self.stdout.write(f'  F5HardwareModel:   {len(models_set)} entradas únicas, {created_m} creadas.')

        # 3. Build lookup dicts for fast FK assignment
        ver_map:   dict[str, F5SoftwareVersion] = {obj.version: obj for obj in F5SoftwareVersion.objects.all()}
        model_map: dict[str, F5HardwareModel]   = {obj.name: obj    for obj in F5HardwareModel.objects.all()}

        # 4. Link LBPhysical records
        phys_updated = 0
        for obj in LBPhysical.objects.all():
            changed = False
            if obj.version and obj.f5_version_id is None:
                fk = ver_map.get(obj.version.strip())
                if fk:
                    obj.f5_version = fk
                    changed = True
            if obj.model and obj.f5_model_id is None:
                fk = model_map.get(obj.model.strip())
                if fk:
                    obj.f5_model = fk
                    changed = True
            if changed:
                obj.save(update_fields=['f5_version', 'f5_model'])
                phys_updated += 1
        self.stdout.write(f'  LBPhysical enlazados: {phys_updated}')

        # 5. Link LBGuest records
        guest_updated = 0
        for obj in LBGuest.objects.all():
            changed = False
            if obj.version and obj.f5_version_id is None:
                fk = ver_map.get(obj.version.strip())
                if fk:
                    obj.f5_version = fk
                    changed = True
            if obj.model and obj.f5_model_id is None:
                fk = model_map.get(obj.model.strip())
                if fk:
                    obj.f5_model = fk
                    changed = True
            if changed:
                obj.save(update_fields=['f5_version', 'f5_model'])
                guest_updated += 1
        self.stdout.write(f'  LBGuest enlazados:    {guest_updated}')

        self.stdout.write(self.style.SUCCESS('\n¡Catálogo F5 poblado correctamente!'))
        self.stdout.write(
            'Próximo paso: agrega las fechas EoSS/EoTS en el admin o en '
            '/infrastructure/f5-versions/ y /infrastructure/f5-models/\n'
        )
