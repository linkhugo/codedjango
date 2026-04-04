"""
HTML form definitions for create/edit operations on infrastructure models.

Each form class controls:
  - Which fields appear in the add/edit page
  - The HTML widget used for each field (text input, dropdown, date picker, etc.)
  - Validation rules beyond what the database enforces

Forms are rendered through the generic crud_form.html template and are used
by the CreateView and UpdateView classes in views.py.

Only infrastructure models (Company, Datacenter, LBPhysical, LBGuest) have
editable forms — F5 configuration objects (VIPs, Pools, Nodes, etc.) are
read-only because they are synced automatically from the devices.
"""

from django import forms
from .models import Company, Datacenter, LBPhysical, LBGuest, HealthRule, VIP, DocEntry, DirectoryEntry


class CompanyForm(forms.ModelForm):
    """Form for creating or editing a Company (client) record."""

    class Meta:
        model = Company
        fields = ['name', 'client_code']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Company name'}),
            'client_code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Client code'}),
        }


class DatacenterForm(forms.ModelForm):
    """Form for creating or editing a Datacenter location record."""

    class Meta:
        model = Datacenter
        fields = ['datacenter', 'location']
        widgets = {
            'datacenter': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Datacenter name'}),
            'location': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Location'}),
        }


def _validate_and_reset_mgmt_ip(form, cleaned_data, is_create, physical_pk=None, guest_pk=None):
    """
    Shared mgmt_ip validation for LBPhysicalForm and LBGuestForm.

    Checks uniqueness across both tables (excluding the current record's own
    table by pk) and resets integration flags when the IP changes on edit.

    Returns True if the IP was changed (caller should set _ip_reset_warning).
    """
    mgmt_ip = cleaned_data.get('mgmt_ip')
    if not mgmt_ip:
        return False

    phy_qs = LBPhysical.objects.filter(mgmt_ip=mgmt_ip)
    if physical_pk:
        phy_qs = phy_qs.exclude(pk=physical_pk)
    gst_qs = LBGuest.objects.filter(mgmt_ip=mgmt_ip)
    if guest_pk:
        gst_qs = gst_qs.exclude(pk=guest_pk)

    if phy_qs.exists():
        form.add_error('mgmt_ip', f'La MGMT IP "{mgmt_ip}" ya está asignada en Physical LB.')
    if gst_qs.exists():
        form.add_error('mgmt_ip', f'La MGMT IP "{mgmt_ip}" ya está asignada en Guest LB.')

    if not is_create and form.instance and mgmt_ip != form.instance.mgmt_ip:
        cleaned_data['monitoreo'] = False
        cleaned_data['cyberark']  = False
        cleaned_data['cmdb_snmp'] = False
        return True

    return False


class LBPhysicalForm(forms.ModelForm):
    """
    Form for creating or editing a physical F5 appliance record.

    Validation rules enforced here (not just in the database):
      - ``device``, ``ci_id``, and ``mgmt_ip`` must be unique across both
        LBPhysical and LBGuest tables (checked on creation only).
      - ``device`` becomes read-only after the record is created because it
        is the primary key and changing it would break relationships.
      - If ``mgmt_ip`` is changed on an existing record, the ``monitoreo``
        and ``cyberark`` flags are automatically reset to False, since those
        integrations need to be re-validated for the new IP.
    """

    class Meta:
        model = LBPhysical
        fields = [
            'device', 'ci_id', 'mgmt_ip', 'version', 'distro', 'model',
            'serial', 'snow_link', 'environment', 'service', 'vendor_support',
            'location', 'ansible_group', 'company', 'datacenter', 'purpose',
            'ha_pair', 'monitoreo', 'cmdb_snmp', 'cyberark', 'user_cyberark',
            'url_cyberark',
        ]
        widgets = {
            'device':        forms.TextInput(attrs={'class': 'form-control'}),
            'ci_id':         forms.TextInput(attrs={'class': 'form-control'}),
            'mgmt_ip':       forms.TextInput(attrs={'class': 'form-control', 'placeholder': '192.168.1.1'}),
            'version':       forms.TextInput(attrs={'class': 'form-control', 'data-autocomplete': 'lb_physical,version'}),
            'distro':        forms.TextInput(attrs={'class': 'form-control', 'data-autocomplete': 'lb_physical,distro'}),
            'model':         forms.TextInput(attrs={'class': 'form-control', 'data-autocomplete': 'lb_physical,model'}),
            'serial':        forms.TextInput(attrs={'class': 'form-control'}),
            'snow_link':     forms.URLInput(attrs={'class': 'form-control'}),
            'environment':   forms.Select(
                choices=[('', '---------'), ('DRP', 'DRP'), ('PRE-PRODUCTION', 'PRE-PRODUCTION'), ('PRODUCTION', 'PRODUCTION')],
                attrs={'class': 'form-select'}
            ),
            'service':       forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}, format='%Y-%m-%d'),
            'vendor_support': forms.TextInput(attrs={'class': 'form-control', 'data-autocomplete': 'lb_physical,vendor_support'}),
            'location':      forms.TextInput(attrs={'class': 'form-control', 'data-autocomplete': 'lb_physical,location'}),
            'ansible_group': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'company':       forms.Select(attrs={'class': 'form-select'}),
            'datacenter':    forms.Select(attrs={'class': 'form-select'}),
            'purpose':       forms.Select(
                choices=[('', '---------'), ('Virtualizador', 'Virtualizador'), ('LTM', 'LTM'), ('GTM', 'GTM')],
                attrs={'class': 'form-select'}
            ),
            'ha_pair':       forms.TextInput(attrs={'class': 'form-control',
                                                    'placeholder': 'Hostname del equipo HA partner'}),
            'monitoreo':     forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'cmdb_snmp':     forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'cyberark':      forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'user_cyberark': forms.TextInput(attrs={'class': 'form-control',
                                                   'placeholder': 'usuario_cyberark'}),
            'url_cyberark':  forms.URLInput(attrs={'class': 'form-control',
                                                   'placeholder': 'https://cyberark.empresa.com/...'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Required fields
        for field in ('mgmt_ip', 'version', 'distro', 'model', 'serial',
                      'environment', 'service', 'company', 'purpose'):
            self.fields[field].required = True
        # Device is not editable after creation
        if self.instance and self.instance.pk:
            self.fields['device'].disabled = True
            self.fields['device'].widget.attrs['class'] += ' bg-light'
        self._ip_reset_warning = False

    def clean(self):
        cleaned_data = super().clean()
        is_create = not (self.instance and self.instance.pk)
        current_pk = self.instance.pk if self.instance else None

        device   = cleaned_data.get('device')
        ci_id    = cleaned_data.get('ci_id')


        # ── Validaciones solo en creación ──────────────────────────────────────
        if is_create:
            if device:
                if LBPhysical.objects.filter(device=device).exists():
                    self.add_error('device', f'El device "{device}" ya existe en Physical LB.')
                if LBGuest.objects.filter(device=device).exists():
                    self.add_error('device', f'El device "{device}" ya existe en Guest LB.')

            if ci_id:
                if LBPhysical.objects.filter(ci_id=ci_id).exists():
                    self.add_error('ci_id', f'El CI ID "{ci_id}" ya existe en Physical LB.')
                if LBGuest.objects.filter(ci_id=ci_id).exists():
                    self.add_error('ci_id', f'El CI ID "{ci_id}" ya existe en Guest LB.')

        # ── MGMT IP única en ambas tablas + reset flags si cambia ─────────────
        if _validate_and_reset_mgmt_ip(self, cleaned_data, is_create,
                                       physical_pk=current_pk, guest_pk=None):
            self._ip_reset_warning = True

        return cleaned_data


class LBGuestForm(forms.ModelForm):
    """
    Form for creating or editing a virtual (guest) F5 instance record.

    Simpler than LBPhysicalForm: no service-date, no datacenter.
    Includes the same Dado de Alta fields as LBPhysicalForm: monitoreo,
    cmdb_snmp, cyberark, user_cyberark, url_cyberark. The ``device``
    field is locked after creation for the same reason as in LBPhysicalForm.
    """

    class Meta:
        model = LBGuest
        fields = [
            'device', 'ci_id', 'mgmt_ip', 'version', 'distro', 'model',
            'serial', 'snow_link', 'environment', 'ansible_group', 'company',
            'ha_pair', 'monitoreo', 'cmdb_snmp', 'cyberark', 'user_cyberark',
            'url_cyberark',
        ]
        widgets = {
            'device':        forms.TextInput(attrs={'class': 'form-control'}),
            'ci_id':         forms.TextInput(attrs={'class': 'form-control'}),
            'mgmt_ip':       forms.TextInput(attrs={'class': 'form-control', 'placeholder': '192.168.1.1'}),
            'version':       forms.TextInput(attrs={'class': 'form-control', 'data-autocomplete': 'lb_guest,version'}),
            'distro':        forms.TextInput(attrs={'class': 'form-control', 'data-autocomplete': 'lb_guest,distro'}),
            'model':         forms.TextInput(attrs={'class': 'form-control', 'data-autocomplete': 'lb_guest,model'}),
            'serial':        forms.TextInput(attrs={'class': 'form-control'}),
            'snow_link':     forms.URLInput(attrs={'class': 'form-control'}),
            'environment':   forms.Select(
                choices=[('', '---------'), ('DRP', 'DRP'), ('PRE-PRODUCTION', 'PRE-PRODUCTION'), ('PRODUCTION', 'PRODUCTION')],
                attrs={'class': 'form-select'}
            ),
            'ansible_group': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'company':       forms.Select(attrs={'class': 'form-select'}),
            'ha_pair':       forms.TextInput(attrs={'class': 'form-control',
                                                    'placeholder': 'Hostname del equipo HA partner'}),
            'monitoreo':     forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'cmdb_snmp':     forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'cyberark':      forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'user_cyberark': forms.TextInput(attrs={'class': 'form-control',
                                                   'placeholder': 'usuario_cyberark'}),
            'url_cyberark':  forms.URLInput(attrs={'class': 'form-control',
                                                   'placeholder': 'https://cyberark.empresa.com/...'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Required fields
        for field in ('device', 'mgmt_ip', 'version', 'model', 'company'):
            self.fields[field].required = True
        # Device is not editable after creation
        if self.instance and self.instance.pk:
            self.fields['device'].disabled = True
            self.fields['device'].widget.attrs['class'] += ' bg-light'
        self._ip_reset_warning = False

    def clean(self):
        cleaned_data = super().clean()
        is_create = not (self.instance and self.instance.pk)
        current_pk = self.instance.pk if self.instance else None

        # ── Validaciones solo en creación ──────────────────────────────────────
        if is_create:
            device = cleaned_data.get('device')
            ci_id  = cleaned_data.get('ci_id')
            if device:
                if LBPhysical.objects.filter(device=device).exists():
                    self.add_error('device', f'El device "{device}" ya existe en Physical LB.')
                if LBGuest.objects.filter(device=device).exists():
                    self.add_error('device', f'El device "{device}" ya existe en Guest LB.')
            if ci_id:
                if LBPhysical.objects.filter(ci_id=ci_id).exists():
                    self.add_error('ci_id', f'El CI ID "{ci_id}" ya existe en Physical LB.')
                if LBGuest.objects.filter(ci_id=ci_id).exists():
                    self.add_error('ci_id', f'El CI ID "{ci_id}" ya existe en Guest LB.')

        # ── MGMT IP única en ambas tablas + reset flags si cambia ─────────────
        if _validate_and_reset_mgmt_ip(self, cleaned_data, is_create,
                                       physical_pk=None, guest_pk=current_pk):
            self._ip_reset_warning = True

        return cleaned_data


class HealthRuleForm(forms.ModelForm):
    """Form for creating or editing a HealthRule threshold."""

    class Meta:
        model = HealthRule
        fields = ['field_name', 'operator', 'threshold', 'severity', 'message']
        widgets = {
            'field_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. cpu_usage'}),
            'operator':   forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. > == contains'}),
            'threshold':  forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 90'}),
            'severity':   forms.Select(attrs={'class': 'form-select'}),
            'message':    forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Human-readable alert description'}),
        }


class VIPForm(forms.ModelForm):
    """
    Allows manual override of a VIP's operational state fields.

    VIPs are normally read-only (synced from F5), but operators may need to
    manually correct the enabled/availability state or add context via the
    description and status_reason fields.
    """

    ENABLED_CHOICES = [('yes', 'yes — activa'), ('no', 'no — inactiva')]
    AVAIL_CHOICES = [
        ('available',   'available'),
        ('offline',     'offline'),
        ('unknown',     'unknown'),
        ('unavailable', 'unavailable'),
    ]

    enabled = forms.ChoiceField(
        choices=ENABLED_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Enabled',
    )
    availability_status = forms.ChoiceField(
        choices=AVAIL_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Availability Status',
        required=False,
    )

    class Meta:
        model = VIP
        fields = ['enabled', 'availability_status', 'status_reason', 'description']
        widgets = {
            'status_reason': forms.Textarea(attrs={'class': 'form-control', 'rows': 3,
                                                   'placeholder': 'Motivo del estado actual…'}),
            'description':   forms.Textarea(attrs={'class': 'form-control', 'rows': 3,
                                                   'placeholder': 'Descripción / observaciones…'}),
        }


class DocEntryForm(forms.ModelForm):
    """Form for creating or editing a documentation entry."""

    class Meta:
        model  = DocEntry
        fields = ['name', 'category', 'url', 'description']
        widgets = {
            'name':        forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre del documento'}),
            'category':    forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Procedimientos, Diseño, Proveedores…'}),
            'url':         forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://…'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.fields['name'].required = True
        self.fields['url'].required  = True


class DirectoryEntryForm(forms.ModelForm):
    """Form for creating or editing a directory (important numbers) entry."""

    class Meta:
        model  = DirectoryEntry
        fields = ['name', 'number', 'description']
        widgets = {
            'name':        forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre o proveedor'}),
            'number':      forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+52 55 1234 5678'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.fields['name'].required   = True
        self.fields['number'].required = True
