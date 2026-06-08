"""
Infrastructure views: LBPhysical, LBGuest, Company, Datacenter, inventory, and CMDB validation.
"""

from django.contrib import messages
from django.contrib.admin.models import LogEntry, ADDITION, CHANGE, DELETION
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView

from ..models import (
    Company, Datacenter, LBPhysical, LBGuest, LBDeviceChangeLog,
    LBDecommissioned, SiteSettings,
)
from ..forms import CompanyForm, DatacenterForm, LBPhysicalForm, LBGuestForm
from .mixins import CRUDContextMixin
from .utils import (
    _IP_RESET_WARNING_MSG, COMPLIANCE_ENVIRONMENTS,
    _dt_params, _log_wiki_change, _record_device_changes,
)


class LBPhysicalListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """
    Physical LB inventory list. Supports optional ?environment= filter in the URL
    to pre-filter the table to a specific environment (DRP, PRE-PRODUCTION, PRODUCTION).
    """

    model = LBPhysical
    template_name = 'lb_manager/lb_physical_list.html'
    context_object_name = 'objects'
    paginate_by = None
    permission_required = 'lb_manager.view_lbphysical'
    raise_exception = True

    def get_queryset(self):
        qs = super().get_queryset().select_related('company', 'datacenter')
        env = self.request.GET.get('environment')
        if env:
            qs = qs.filter(environment__iexact=env)
        company = self.request.GET.get('company')
        if company:
            qs = qs.filter(company__client_code__iexact=company)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = 'Physical Load Balancers'
        ctx['page_icon'] = 'fa-hdd'
        ctx['environment'] = self.request.GET.get('environment', '')
        ctx['company_filter'] = self.request.GET.get('company', '')
        ctx['companies'] = Company.objects.order_by('client_code').values('client_code', 'name')
        return ctx


class LBGuestListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """Virtual (guest) LB inventory list."""

    model = LBGuest
    template_name = 'lb_manager/lb_guest_list.html'
    context_object_name = 'objects'
    paginate_by = None
    permission_required = 'lb_manager.view_lbguest'
    raise_exception = True

    def get_queryset(self):
        qs = super().get_queryset().select_related('company')
        company = self.request.GET.get('company')
        if company:
            qs = qs.filter(company__client_code__iexact=company)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = 'Guest Load Balancers'
        ctx['page_icon'] = 'fa-cloud-upload-alt'
        ctx['company_filter'] = self.request.GET.get('company', '')
        ctx['companies'] = Company.objects.order_by('client_code').values('client_code', 'name')
        return ctx


class CompanyListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """Client/company catalog list."""

    model = Company
    template_name = 'lb_manager/company_list.html'
    context_object_name = 'objects'
    paginate_by = None
    permission_required = 'lb_manager.view_company'
    raise_exception = True

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = 'Companies'
        ctx['page_icon'] = 'fa-building'
        return ctx


class DatacenterListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """Datacenter location catalog list."""

    model = Datacenter
    template_name = 'lb_manager/datacenter_list.html'
    context_object_name = 'objects'
    paginate_by = None
    permission_required = 'lb_manager.view_datacenter'
    raise_exception = True

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = 'Datacenters'
        ctx['page_icon'] = 'fa-warehouse'
        return ctx


# ============================================================
#  COMPANY CRUD
#  Requires permission: lb_manager.add/change/delete_company
#  Returns HTTP 403 (not redirect) if the user lacks the permission.
# ============================================================
class CompanyCreateView(CRUDContextMixin, LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    """Create a new Company record. Requires the 'add_company' permission."""
    model = Company
    form_class = CompanyForm
    template_name = 'lb_manager/crud_form.html'
    success_url = reverse_lazy('company_list')
    permission_required = 'lb_manager.add_company'
    raise_exception = True
    crud_list_url     = 'company_list'
    crud_list_label   = 'Companies'
    page_title_create = 'Add Company'

    def form_valid(self, form):
        messages.success(self.request, 'Company created successfully.')
        return super().form_valid(form)


class CompanyUpdateView(CRUDContextMixin, LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    """Edit an existing Company record. Requires the 'change_company' permission."""

    model = Company
    form_class = CompanyForm
    template_name = 'lb_manager/crud_form.html'
    success_url = reverse_lazy('company_list')
    permission_required = 'lb_manager.change_company'
    raise_exception = True
    crud_list_url   = 'company_list'
    crud_list_label = 'Companies'
    page_title_edit = 'Edit Company: {obj}'

    def form_valid(self, form):
        messages.success(self.request, 'Company updated successfully.')
        return super().form_valid(form)


class CompanyDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    """Delete a Company record after confirmation. Requires the 'delete_company' permission."""

    model = Company
    template_name = 'lb_manager/crud_confirm_delete.html'
    success_url = reverse_lazy('company_list')
    permission_required = 'lb_manager.delete_company'
    raise_exception = True

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = 'Delete Company'
        ctx['list_url'] = reverse_lazy('company_list')
        ctx['list_label'] = 'Companies'
        ctx['object_name'] = str(self.object)
        return ctx

    def form_valid(self, form):
        messages.success(self.request, 'Company deleted successfully.')
        return super().form_valid(form)


# ============================================================
#  DATACENTER CRUD
# ============================================================
class DatacenterCreateView(CRUDContextMixin, LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    """Create a new Datacenter record. Requires the 'add_datacenter' permission."""

    model = Datacenter
    form_class = DatacenterForm
    template_name = 'lb_manager/crud_form.html'
    success_url = reverse_lazy('datacenter_list')
    permission_required = 'lb_manager.add_datacenter'
    raise_exception = True
    crud_list_url     = 'datacenter_list'
    crud_list_label   = 'Datacenters'
    page_title_create = 'Add Datacenter'

    def form_valid(self, form):
        messages.success(self.request, 'Datacenter created successfully.')
        return super().form_valid(form)


class DatacenterUpdateView(CRUDContextMixin, LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    """Edit an existing Datacenter record. Requires the 'change_datacenter' permission."""

    model = Datacenter
    form_class = DatacenterForm
    template_name = 'lb_manager/crud_form.html'
    success_url = reverse_lazy('datacenter_list')
    permission_required = 'lb_manager.change_datacenter'
    raise_exception = True
    crud_list_url   = 'datacenter_list'
    crud_list_label = 'Datacenters'
    page_title_edit = 'Edit Datacenter: {obj}'

    def form_valid(self, form):
        messages.success(self.request, 'Datacenter updated successfully.')
        return super().form_valid(form)


class DatacenterDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    """Delete a Datacenter record after confirmation. Requires the 'delete_datacenter' permission."""

    model = Datacenter
    template_name = 'lb_manager/crud_confirm_delete.html'
    success_url = reverse_lazy('datacenter_list')
    permission_required = 'lb_manager.delete_datacenter'
    raise_exception = True

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = 'Delete Datacenter'
        ctx['list_url'] = reverse_lazy('datacenter_list')
        ctx['list_label'] = 'Datacenters'
        ctx['object_name'] = str(self.object)
        return ctx

    def form_valid(self, form):
        messages.success(self.request, 'Datacenter deleted successfully.')
        return super().form_valid(form)


# ============================================================
#  LB PHYSICAL CRUD
# ============================================================
class LBPhysicalCreateView(CRUDContextMixin, LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    """Register a new physical F5 appliance. Requires the 'add_lbphysical' permission."""

    model = LBPhysical
    form_class = LBPhysicalForm
    template_name = 'lb_manager/crud_form.html'
    success_url = reverse_lazy('lb_physical_list')
    permission_required = 'lb_manager.add_lbphysical'
    raise_exception = True
    crud_list_url     = 'lb_physical_list'
    crud_list_label   = 'Physical LBs'
    page_title_create = 'Add Physical LB'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['dado_de_alta_fields'] = ['monitoreo', 'netdeck', 'cmdb_snmp', 'cyberark', 'user_cyberark', 'url_cyberark']
        return ctx

    def form_valid(self, form):
        messages.success(self.request, 'Physical LB created successfully.')
        return super().form_valid(form)


class LBPhysicalUpdateView(CRUDContextMixin, LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    """Edit an existing physical F5 appliance record. Requires the 'change_lbphysical' permission."""

    model = LBPhysical
    form_class = LBPhysicalForm
    template_name = 'lb_manager/crud_form.html'
    success_url = reverse_lazy('lb_physical_list')
    permission_required = 'lb_manager.change_lbphysical'
    raise_exception = True
    crud_list_url   = 'lb_physical_list'
    crud_list_label = 'Physical LBs'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = f'Edit Physical LB: {self.object.device}'
        ctx['dado_de_alta_fields'] = ['monitoreo', 'netdeck', 'cmdb_snmp', 'cyberark', 'user_cyberark', 'url_cyberark']
        return ctx

    def form_valid(self, form):
        try:
            old = LBPhysical.objects.select_related('company', 'datacenter').get(pk=self.object.pk)
        except LBPhysical.DoesNotExist:
            old = None
        response = super().form_valid(form)
        if old:
            _record_device_changes(self.request.user, old, self.object, 'physical', form.changed_data)
        _log_wiki_change(self.request.user, self.object, CHANGE)
        if getattr(form, '_ip_reset_warning', False):
            messages.warning(self.request, _IP_RESET_WARNING_MSG)
        messages.success(self.request, 'Physical LB updated successfully.')
        return response


class LBPhysicalDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    """Delete a physical F5 appliance record after confirmation. Requires the 'delete_lbphysical' permission."""

    model = LBPhysical
    template_name = 'lb_manager/lb_decommission_confirm.html'
    success_url = reverse_lazy('lb_physical_list')
    permission_required = 'lb_manager.delete_lbphysical'
    raise_exception = True

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = 'Decomisionar Physical LB'
        ctx['list_url'] = reverse_lazy('lb_physical_list')
        ctx['list_label'] = 'Physical LBs'
        ctx['object_name'] = self.object.device
        ctx['device_type'] = 'Physical'
        return ctx

    def form_valid(self, form):
        obj = self.get_object()
        LBDecommissioned.objects.create(
            device=obj.device,
            device_type='Physical',
            ci_id=obj.ci_id,
            mgmt_ip=obj.mgmt_ip,
            version=obj.version,
            model=obj.model,
            serial=obj.serial,
            environment=obj.environment,
            company=obj.company.client_code if obj.company else None,
            comments=self.request.POST.get('comments', '').strip() or None,
            decommissioned_by=self.request.user,
        )
        messages.success(self.request, f'Physical LB "{obj.device}" decomisado y eliminado.')
        return super().form_valid(form)


# ============================================================
#  LB GUEST CRUD
# ============================================================
class LBGuestCreateView(CRUDContextMixin, LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    """Register a new virtual (guest) F5 instance. Requires the 'add_lbguest' permission."""

    model = LBGuest
    form_class = LBGuestForm
    template_name = 'lb_manager/crud_form.html'
    success_url = reverse_lazy('lb_guest_list')
    permission_required = 'lb_manager.add_lbguest'
    raise_exception = True
    crud_list_url     = 'lb_guest_list'
    crud_list_label   = 'Guest LBs'
    page_title_create = 'Add Guest LB'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['dado_de_alta_fields'] = ['monitoreo', 'netdeck', 'cmdb_snmp', 'cyberark', 'user_cyberark', 'url_cyberark']
        return ctx

    def form_valid(self, form):
        messages.success(self.request, 'Guest LB created successfully.')
        return super().form_valid(form)


class LBGuestUpdateView(CRUDContextMixin, LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    """Edit an existing virtual F5 instance record. Requires the 'change_lbguest' permission."""

    model = LBGuest
    form_class = LBGuestForm
    template_name = 'lb_manager/crud_form.html'
    success_url = reverse_lazy('lb_guest_list')
    permission_required = 'lb_manager.change_lbguest'
    raise_exception = True
    crud_list_url   = 'lb_guest_list'
    crud_list_label = 'Guest LBs'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = f'Edit Guest LB: {self.object.device}'
        ctx['dado_de_alta_fields'] = ['monitoreo', 'netdeck', 'cmdb_snmp', 'cyberark', 'user_cyberark', 'url_cyberark']
        return ctx

    def form_valid(self, form):
        try:
            old = LBGuest.objects.select_related('company').get(pk=self.object.pk)
        except LBGuest.DoesNotExist:
            old = None
        response = super().form_valid(form)
        if old:
            _record_device_changes(self.request.user, old, self.object, 'guest', form.changed_data)
        _log_wiki_change(self.request.user, self.object, CHANGE)
        if getattr(form, '_ip_reset_warning', False):
            messages.warning(self.request, _IP_RESET_WARNING_MSG)
        messages.success(self.request, 'Guest LB updated successfully.')
        return response


class LBGuestDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    """Delete a virtual F5 instance record after confirmation. Requires the 'delete_lbguest' permission."""

    model = LBGuest
    template_name = 'lb_manager/lb_decommission_confirm.html'
    success_url = reverse_lazy('lb_guest_list')
    permission_required = 'lb_manager.delete_lbguest'
    raise_exception = True

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = 'Decomisionar Guest LB'
        ctx['list_url'] = reverse_lazy('lb_guest_list')
        ctx['list_label'] = 'Guest LBs'
        ctx['object_name'] = self.object.device
        ctx['device_type'] = 'Guest'
        return ctx

    def form_valid(self, form):
        obj = self.get_object()
        LBDecommissioned.objects.create(
            device=obj.device,
            device_type='Guest',
            ci_id=obj.ci_id,
            mgmt_ip=obj.mgmt_ip,
            version=obj.version,
            model=obj.model,
            serial=obj.serial,
            environment=obj.environment,
            company=obj.company.client_code if obj.company else None,
            comments=self.request.POST.get('comments', '').strip() or None,
            decommissioned_by=self.request.user,
        )
        messages.success(self.request, f'Guest LB "{obj.device}" decomisado y eliminado.')
        return super().form_valid(form)


class LBDecommissionedListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """
    Historial de equipos LBPhysical y LBGuest decomisados.

    Solo lectura. Requiere permiso ``lb_manager.view_lbdecommissioned``.
    Cada registro es un snapshot inmutable creado por LBPhysicalDeleteView
    o LBGuestDeleteView en el momento del borrado.
    """

    model = LBDecommissioned
    template_name = 'lb_manager/lb_decommissioned_list.html'
    context_object_name = 'objects'
    paginate_by = None
    permission_required = 'lb_manager.view_lbdecommissioned'
    raise_exception = True

    def get_context_data(self, **kwargs: object) -> dict:
        """Agrega título y ícono de página al contexto."""
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = 'Equipos Decomisados'
        ctx['page_icon'] = 'fa-trash-can-arrow-up'
        return ctx


@login_required
@permission_required('lb_manager.view_lbdevicechangelog', raise_exception=True)
def lb_device_history(_request, device):
    """
    AJAX — return the field-level change history for a single LB device.

    Returns JSON ``{data: [...]}`` where each item has:
      timestamp, user, field, old_value, new_value
    """
    _lb_hist_cfg = SiteSettings.objects.first()
    _lb_hist_limit = _lb_hist_cfg.lb_device_history_limit if _lb_hist_cfg else 200
    entries = (
        LBDeviceChangeLog.objects
        .filter(device=device)
        .select_related('user')
        .order_by('-timestamp')[:_lb_hist_limit]
    )
    data = [
        {
            'timestamp': e.timestamp.strftime('%d/%m/%Y %H:%M'),
            'user': e.user.get_full_name() or e.user.username if e.user else '—',
            'field': e.field_name,
            'old': e.old_value or '—',
            'new': e.new_value or '—',
        }
        for e in entries
    ]
    return JsonResponse({'data': data})


# ============================================================
#  UNIFIED LB INVENTORY  (LBGuest UNION LBPhysical)
# ============================================================
class LBInventoryListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """
    Unified inventory combining every LBGuest and every LBPhysical in one table.

    Replicates the SQL UNION query:
      - Part 1: All LBGuest rows, left-joined to LBPhysical by serial number
        so each guest inherits the physical host's datacenter, location,
        service date, vendor support, and virtualizador name.
      - Part 2: All LBPhysical rows (standalone appliances).

    Rows are loaded asynchronously via lb_inventory_data.
    """

    model = LBGuest  # dummy model — real data comes from the AJAX endpoint
    template_name = 'lb_manager/lb_inventory_list.html'
    context_object_name = 'objects'
    paginate_by = None
    permission_required = 'lb_manager.view_lbphysical'
    raise_exception = True

    def get_queryset(self):
        return LBGuest.objects.none()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = 'LB Inventory'
        ctx['page_icon'] = 'fa-table-list'
        ctx['total'] = LBGuest.objects.count() + LBPhysical.objects.count()
        ctx['companies'] = Company.objects.order_by('client_code').values('client_code', 'name')

        lb_ct_ids = list(ContentType.objects.filter(
            app_label='lb_manager', model__in=['lbguest', 'lbphysical']
        ).values_list('id', flat=True))
        _inv_cfg = SiteSettings.objects.first()
        _inv_limit = _inv_cfg.inventory_recent_changes_limit if _inv_cfg else 50
        recent = (
            LogEntry.objects
            .filter(content_type_id__in=lb_ct_ids)
            .select_related('user', 'content_type')
            .order_by('-action_time')[:_inv_limit]
        )
        ACTION_LABEL = {ADDITION: 'Agregado', CHANGE: 'Modificado', DELETION: 'Eliminado'}
        ACTION_COLOR = {ADDITION: 'success', CHANGE: 'primary', DELETION: 'danger'}
        ctx['inventory_changes'] = [
            {
                'timestamp': e.action_time,
                'user': e.user.get_full_name() or e.user.username if e.user else '—',
                'model': 'Physical LB' if e.content_type.model == 'lbphysical' else 'Guest LB',
                'device': e.object_repr,
                'action': ACTION_LABEL.get(e.action_flag, str(e.action_flag)),
                'color': ACTION_COLOR.get(e.action_flag, 'secondary'),
                'detail': e.get_change_message() or '—',
            }
            for e in recent
        ]
        return ctx


@login_required
@permission_required('lb_manager.view_lbphysical', raise_exception=True)
def lb_inventory_data(request):
    """
    AJAX endpoint — unified LBGuest + LBPhysical inventory for DataTables.

    Executes the canonical UNION SQL query directly against PostgreSQL so the
    result is identical to running the query manually in a DB client.

    Columns returned (0-indexed):
      0  type            – 'Guest' or 'Physical'
      1  device          – Hostname of the LB
      2  ci_id           – Configuration Item ID
      3  mgmt_ip         – Management IP address
      4  name            – Client company name
      5  client_code     – Company client code
      6  version         – Software version
      7  model           – Hardware/software model
      8  serial          – Serial (COALESCE: physical serial takes priority for guests)
      9  virtualizador   – Physical host device name (COALESCE: physical device for guests)
      10 environment     – DRP / PRE-PRODUCTION / PRODUCTION
      11 service         – Vendor service/support expiry date
      12 distro          – OS/distribution
      13 vendor_support  – Vendor support level
      14 datacenter      – Data-center name
      15 location        – Physical rack/room location
      16 snow_link       – ServiceNow CI link
      17 last_modified   – Timestamp of last record update
      18 monitoreo       – Monitoring integration enabled
      19 cmdb_snmp       – CMDB SNMP integration enabled
      20 cyberark        – CyberArk integration enabled
      21 ansible_group   – Ansible inventory group(s)
      22 netdeck         – Netdeck integration enabled (LTM/GTM)
    """
    SQL = """
        SELECT
            'Guest'                                        AS type,
            lb_guest.device,
            lb_guest.ci_id,
            lb_guest.mgmt_ip,
            company.name,
            company.client_code,
            lb_guest.version,
            lb_guest.model,
            COALESCE(lb_physical.serial,  lb_guest.serial) AS serial,
            COALESCE(lb_physical.device,  lb_guest.device) AS virtualizador,
            lb_guest.environment,
            lb_physical.service,
            lb_guest.distro,
            lb_physical.vendor_support,
            datacenter.datacenter,
            lb_physical.location,
            lb_guest.snow_link,
            lb_guest.last_modified,
            lb_guest.monitoreo,
            lb_guest.cmdb_snmp,
            lb_guest.cyberark,
            lb_guest.ansible_group,
            lb_guest.netdeck
        FROM lb_guest
        LEFT JOIN lb_physical  ON lb_guest.serial         = lb_physical.serial
        LEFT JOIN company      ON lb_guest.company_id     = company.id
        LEFT JOIN datacenter   ON lb_physical.datacenter_id = datacenter.id

        UNION

        SELECT
            'Physical'                AS type,
            lb_physical.device,
            lb_physical.ci_id,
            lb_physical.mgmt_ip,
            company.name,
            company.client_code,
            lb_physical.version,
            lb_physical.model,
            lb_physical.serial        AS serial,
            lb_physical.device        AS virtualizador,
            lb_physical.environment,
            lb_physical.service,
            lb_physical.distro,
            lb_physical.vendor_support,
            datacenter.datacenter,
            lb_physical.location,
            lb_physical.snow_link,
            lb_physical.last_modified,
            lb_physical.monitoreo,
            lb_physical.cmdb_snmp,
            lb_physical.cyberark,
            lb_physical.ansible_group,
            lb_physical.netdeck
        FROM lb_physical
        LEFT JOIN company    ON lb_physical.company_id    = company.id
        LEFT JOIN datacenter ON lb_physical.datacenter_id = datacenter.id
    """

    # Column names aligned with the SELECT position (0-indexed)
    _INV_SORT_COLS = [
        'type', 'device', 'ci_id', 'mgmt_ip', 'name', 'client_code',
        'version', 'model', 'serial', 'virtualizador', 'environment',
        'service', 'distro', 'vendor_support', 'datacenter', 'location',
        'snow_link', 'last_modified', 'monitoreo', 'cmdb_snmp', 'cyberark',
        'ansible_group', 'netdeck',
    ]
    # Text-searchable columns (exclude booleans and dates to keep the WHERE fast)
    _INV_SEARCH_COLS = [
        'type', 'device', 'ci_id', 'mgmt_ip', 'name', 'client_code',
        'version', 'model', 'serial', 'virtualizador', 'environment',
        'distro', 'vendor_support', 'datacenter', 'location', 'ansible_group',
    ]

    draw, start, length, search, col_idx, col_dir = _dt_params(request, default_col=1)
    search = search.lower()

    sort_col  = _INV_SORT_COLS[col_idx] if col_idx < len(_INV_SORT_COLS) else 'device'
    direction = 'DESC' if col_dir == 'desc' else 'ASC'

    # ── Total (before search) ─────────────────────────────────────────────────
    with connection.cursor() as cursor:
        cursor.execute(f'SELECT COUNT(*) FROM ({SQL}) AS _inv_total')
        total = cursor.fetchone()[0]

    # ── Build optional WHERE clause for full-text search ──────────────────────
    where_sql    = ''
    where_params = []
    if search:
        like = f'%{search}%'
        conditions = ' OR '.join(
            f"lower(COALESCE({c}::text, '')) LIKE %s" for c in _INV_SEARCH_COLS
        )
        where_sql    = f'WHERE {conditions}'
        where_params = [like] * len(_INV_SEARCH_COLS)

    company = request.GET.get('company', '').strip()
    if company:
        company_cond = "lower(COALESCE(client_code::text, '')) = lower(%s)"
        where_sql    = f'WHERE {company_cond}' if not where_sql else f'{where_sql} AND {company_cond}'
        where_params.append(company)

    # ── Filtered count ────────────────────────────────────────────────────────
    with connection.cursor() as cursor:
        cursor.execute(
            f'SELECT COUNT(*) FROM ({SQL}) AS _inv_filtered {where_sql}',
            where_params,
        )
        filtered = cursor.fetchone()[0]

    # ── Fetch only the requested page, sorted at DB level ────────────────────
    # sort_col comes from _INV_SORT_COLS whitelist (safe for identifier interpolation).
    # direction is hardcoded to 'ASC'/'DESC' (safe).
    # LIMIT/OFFSET use parameterized placeholders to avoid any injection risk.
    if length != -1:
        limit_sql    = 'LIMIT %s OFFSET %s'
        limit_params = [length, start]
    else:
        limit_sql    = ''
        limit_params = []
    with connection.cursor() as cursor:
        cursor.execute(
            f'SELECT * FROM ({SQL}) AS _inv {where_sql}'
            f' ORDER BY {sort_col} {direction} NULLS LAST {limit_sql}',
            where_params + limit_params,
        )
        raw_rows = cursor.fetchall()

    # Normalise: None → '-', dates/datetimes → strings, booleans → 'True'/'False'
    def _fmt(i: int, val) -> str:
        if val is None:
            return '-'
        if i == 11:
            return str(val)             # service (date)
        if i == 17:
            return str(val)[:16]        # last_modified (datetime)
        if i in (18, 19, 20):
            return 'True' if val else 'False'  # boolean flags
        return val if isinstance(val, str) else str(val)

    rows = [[_fmt(i, val) for i, val in enumerate(raw)] for raw in raw_rows]

    return JsonResponse({'draw': draw, 'recordsTotal': total, 'recordsFiltered': filtered, 'data': rows})


# ============================================================
#  AUTOCOMPLETE
# ============================================================
@login_required
@permission_required('lb_manager.view_lbphysical', raise_exception=True)
def autocomplete_data(request):
    """
    AJAX endpoint — return distinct non-empty values for a given model field.

    Used by the LBGuest and LBPhysical create/edit forms to suggest existing
    values as the user types (HTML5 <datalist> autocomplete).

    GET parameters:
        model  – 'lb_guest' or 'lb_physical'
        field  – one of the allowed fields for that model

    Returns JSON: {"values": ["val1", "val2", ...]}
    """
    ALLOWED = {
        'lb_guest': {
            'model': LBGuest,
            'fields': ['version', 'distro', 'model'],
        },
        'lb_physical': {
            'model': LBPhysical,
            'fields': ['version', 'distro', 'model', 'vendor_support', 'location'],
        },
    }

    model_key = request.GET.get('model', '')
    field     = request.GET.get('field', '')

    entry = ALLOWED.get(model_key)
    if not entry or field not in entry['fields']:
        return JsonResponse({'values': []})

    values = list(
        entry['model'].objects
            .exclude(**{f'{field}__isnull': True})
            .exclude(**{f'{field}': ''})
            .values_list(field, flat=True)
            .distinct()
            .order_by(field)[:200]
    )
    return JsonResponse({'values': values})


@login_required
@permission_required('lb_manager.view_lbphysical', raise_exception=True)
def company_compliance(request: 'HttpRequest') -> HttpResponse:
    """
    Dashboard de cumplimiento por empresa.

    Agrega monitoreo, CyberArk y CMDB-SNMP de LBPhysical y LBGuest
    en 2 queries SQL (una por modelo) y los combina en Python.

    Args:
        request: HTTP request.

    Returns:
        Rendered compliance dashboard.
    """
    # Physical: aggregate por company ─────────────────────────────────────────
    # Solo equipos en PRE-PRODUCTION/PRODUCTION (DRP excluido del compliance operacional)
    phys_map: dict[int, dict] = {
        row['company_id']: row
        for row in LBPhysical.objects
        .filter(company__isnull=False, environment__in=COMPLIANCE_ENVIRONMENTS)
        .values('company_id', 'company__client_code', 'company__name')
        .annotate(
            total=Count('device'),
            mon=Count('device', filter=Q(monitoreo=True)),
            net=Count('device', filter=Q(netdeck=True)),
            cy=Count('device',  filter=Q(cyberark=True)),
            cmdb=Count('device', filter=Q(cmdb_snmp=True)),
        )
    }

    # Guest: aggregate por company ─────────────────────────────────────────────
    guest_map: dict[int, dict] = {
        row['company_id']: row
        for row in LBGuest.objects
        .filter(company__isnull=False, environment__in=COMPLIANCE_ENVIRONMENTS)
        .values('company_id', 'company__client_code', 'company__name')
        .annotate(
            total=Count('device'),
            mon=Count('device', filter=Q(monitoreo=True)),
            net=Count('device', filter=Q(netdeck=True)),
            cy=Count('device',  filter=Q(cyberark=True)),
            cmdb=Count('device', filter=Q(cmdb_snmp=True)),
        )
    }

    def _pct(n: int, d: int) -> int:
        return round(n / d * 100) if d else 0

    def _badge(pct: int) -> str:
        if pct >= 80:
            return 'success'
        if pct >= 50:
            return 'warning'
        return 'danger'

    rows = []
    for cid in sorted(
        set(phys_map) | set(guest_map),
        key=lambda c: ((phys_map.get(c) or guest_map[c])['company__client_code'] or ''),
    ):
        p    = phys_map.get(cid, {})
        g    = guest_map.get(cid, {})
        meta = p or g

        total = (p.get('total') or 0) + (g.get('total') or 0)
        mon   = (p.get('mon')   or 0) + (g.get('mon')   or 0)
        net   = (p.get('net')   or 0) + (g.get('net')   or 0)
        cy    = (p.get('cy')    or 0) + (g.get('cy')    or 0)
        cmdb  = (p.get('cmdb')  or 0) + (g.get('cmdb')  or 0)

        mon_pct  = _pct(mon,  total)
        net_pct  = _pct(net,  total)
        cy_pct   = _pct(cy,   total)
        cmdb_pct = _pct(cmdb, total)

        rows.append({
            'client_code': meta['company__client_code'],
            'name':        meta['company__name'],
            'total':       total,
            'phys_total':  p.get('total', 0),
            'guest_total': g.get('total', 0),
            'mon_n':       mon,   'mon_pct':  mon_pct,  'mon_badge':  _badge(mon_pct),
            'net_n':       net,   'net_pct':  net_pct,  'net_badge':  _badge(net_pct),
            'cy_n':        cy,    'cy_pct':   cy_pct,   'cy_badge':   _badge(cy_pct),
            'cmdb_n':      cmdb,  'cmdb_pct': cmdb_pct, 'cmdb_badge': _badge(cmdb_pct),
        })

    total_devices = sum(r['total'] for r in rows)

    return render(request, 'lb_manager/company_compliance.html', {
        'rows':            rows,
        'total_companies': len(rows),
        'total_devices':   total_devices,
        'global_mon':      _pct(sum(r['mon_n']  for r in rows), total_devices),
        'global_net':      _pct(sum(r['net_n']  for r in rows), total_devices),
        'global_cy':       _pct(sum(r['cy_n']   for r in rows), total_devices),
        'global_cmdb':     _pct(sum(r['cmdb_n'] for r in rows), total_devices),
    })


@login_required
@permission_required('lb_manager.view_lbphysical', raise_exception=True)
def version_drift(request: 'HttpRequest') -> HttpResponse:
    """
    Muestra todos los dispositivos con versión de software registrada.

    La detección de drift (versión fuera del estándar) se realiza en el
    cliente mediante un prefijo configurable por el usuario en tiempo real,
    lo que permite matching parcial (ej. "17.5" acepta "17.5.1", "17.5.2").

    Args:
        request: HTTP request.

    Returns:
        Rendered version drift dashboard.
    """
    rows: list[dict] = []
    for obj in LBPhysical.objects.select_related('company').exclude(version__isnull=True).exclude(version=''):
        rows.append({
            'company_code': obj.company.client_code if obj.company else '-',
            'company_name': obj.company.name        if obj.company else '-',
            'device':       obj.device,
            'tipo':         'Physical',
            'version':      obj.version,
            'environment':  obj.environment or '-',
        })
    for obj in LBGuest.objects.select_related('company').exclude(version__isnull=True).exclude(version=''):
        rows.append({
            'company_code': obj.company.client_code if obj.company else '-',
            'company_name': obj.company.name        if obj.company else '-',
            'device':       obj.device,
            'tipo':         'Guest',
            'version':      obj.version,
            'environment':  obj.environment or '-',
        })

    rows.sort(key=lambda r: (r['company_code'] or '', r['device']))
    return render(request, 'lb_manager/version_drift.html', {
        'rows':          rows,
        'total_devices': len(rows),
        'companies':     Company.objects.order_by('client_code').values('client_code', 'name'),
    })


# cmdb_vs_lb_inventory, _parse_ini_hostnames y ansible_inventory
# fueron movidos a infrastructure_tools.py para mantener este archivo < 1000 líneas.
# Se re-exportan desde views/__init__.py; todos los imports existentes siguen funcionando.
# pylint: disable=wrong-import-position,unused-import
from .infrastructure_tools import (  # noqa: F401,E402
    cmdb_vs_lb_inventory, _parse_ini_hostnames, ansible_inventory,
)
