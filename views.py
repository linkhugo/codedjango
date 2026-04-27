"""
View layer for the ddi_manager application.

Provides:
  - DDIInventoryListView    : Main inventory page (server-side DataTables)
  - ddi_inventory_data      : AJAX endpoint for DataTables
  - ddi_device_history      : AJAX per-device changelog
  - DDIDeviceListView/Create/Update/Delete  : CRUD for DDIDevice
  - DDIServiceListView/Create/Update/Delete : CRUD for DDIService
  - DDILicenseListView/Create/Update/Delete : CRUD for DDILicense
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib.admin.models import LogEntry, ADDITION, CHANGE
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.db.models import Count
from django.http import HttpRequest, JsonResponse
from django.shortcuts import render
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from lb_manager.models import SiteSettings

from .models import DDIDevice, DDIService, DDILicense, DDISnow, DDIDeviceChangeLog, HealthCheckDDI
from .forms import DDIDeviceForm, DDIServiceForm, DDILicenseForm


# ---------------------------------------------------------------------------
# Field label map used when recording changelog entries
# ---------------------------------------------------------------------------
_DDI_FIELD_LABELS = {
    'device': 'Device', 'service': 'Service', 'platform': 'Platform',
    'license': 'License (HWID)', 'model': 'Model', 'hwplatform': 'HW Platform',
    'mgmt_ip': 'MGMT IP', 'service_ip': 'Service IP', 'sw_version': 'SW Version',
    'datacenter': 'Datacenter', 'phy_location': 'Physical Location',
    'company': 'Company', 'role': 'Role', 'environment': 'Environment',
    'net_zone': 'Net Zone', 'vendor_support': 'Vendor Support',
    'master_candidate': 'Master Candidate', 'grid_master': 'Grid Master',
    'monitoreo': 'Monitoreo',
    'cyberark': 'CyberArk', 'user_cyberark': 'CyberArk User',
    'url_cyberark': 'CyberArk URL',
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _log_ddi_change(user, obj, action_flag):
    """Write a Django admin LogEntry for a DDI device change made via the UI."""
    LogEntry.objects.create(
        user_id=user.pk,
        content_type_id=ContentType.objects.get_for_model(obj).pk,
        object_id=str(obj.pk),
        object_repr=str(obj)[:200],
        action_flag=action_flag,
        change_message='Modified via UI' if action_flag == CHANGE else '',
    )


def _record_ddi_changes(user, old_obj, new_obj, changed_fields):
    """
    Save one DDIDeviceChangeLog row per changed field.

    Only fields listed in ``changed_fields`` (from form.changed_data) are
    inspected.  FK fields are stringified so history shows names not IDs.
    """
    records = []
    for field in changed_fields:
        old_val = str(getattr(old_obj, field, '') or '')
        new_val = str(getattr(new_obj, field, '') or '')
        if old_val != new_val:
            records.append(DDIDeviceChangeLog(
                device_id=new_obj.pk,
                device=str(new_obj.device or new_obj.pk),
                user=user,
                field_name=_DDI_FIELD_LABELS.get(field, field),
                old_value=old_val[:500],
                new_value=new_val[:500],
            ))
    if records:
        DDIDeviceChangeLog.objects.bulk_create(records)


# ---------------------------------------------------------------------------
# DDI Inventory (unified view)
# ---------------------------------------------------------------------------

class DDIInventoryListView(LoginRequiredMixin, ListView):
    """
    DDI device inventory page.  Table rows are loaded asynchronously via
    ddi_inventory_data (server-side DataTables).
    """

    model = DDIDevice
    template_name = 'ddi_manager/ddi_inventory_list.html'
    context_object_name = 'objects'
    paginate_by = None

    def get_queryset(self):
        return DDIDevice.objects.none()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = 'DDI Inventory'
        ctx['total'] = DDIDevice.objects.count()

        _inv_cfg = SiteSettings.objects.first()
        _inv_limit = _inv_cfg.inventory_recent_changes_limit if _inv_cfg else 50
        recent = (
            DDIDeviceChangeLog.objects
            .select_related('user')
            .order_by('-timestamp')[:_inv_limit]
        )
        ctx['inventory_changes'] = [
            {
                'timestamp': e.timestamp,
                'user': e.user.get_full_name() or e.user.username if e.user else '—',
                'device': e.device,
                'field': e.field_name,
                'old': e.old_value or '—',
                'new': e.new_value or '—',
            }
            for e in recent
        ]
        return ctx


@login_required
def ddi_inventory_data(request):
    """
    AJAX endpoint — DDI device inventory for DataTables (server-side).

    Columns returned (0-indexed):
      0  device_id        – DDIDevice PK (hidden, used for history link)
      1  device           – Hostname
      2  platform
      3  model
      4  hwplatform
      5  mgmt_ip
      6  service_ip
      7  sw_version
      8  role
      9  environment
      10 net_zone
      11 phy_location
      12 vendor_support
      13 master_candidate – 'Yes' / 'No'
      14 grid_master
      15 service_name
      16 service_status
      17 license_type
      18 expiry_date
      19 expiration_status
      20 company
      21 datacenter
      22 cmdb_id
      23 snow_link
      24 last_modified
      25 monitoreo       – boolean
      26 cyberark        – boolean
      27 user_cyberark
      28 url_cyberark
    """
    SQL = """
        SELECT
            d.id AS device_id,
            d.device,
            d.platform,
            d.model,
            d.hwplatform,
            d.mgmt_ip,
            d.service_ip,
            d.sw_version,
            d.role,
            d.environment,
            d.net_zone,
            d.phy_location,
            d.vendor_support,
            CASE WHEN d.master_candidate THEN 'Yes' ELSE 'No' END AS master_candidate,
            d.grid_master,
            svc.service AS service_name,
            svc.status  AS service_status,
            lic.type    AS license_type,
            lic.expiry_date,
            lic.expiration_status,
            co.name     AS company,
            dc.datacenter,
            sn.cmdb_id,
            sn.snow_link,
            d.last_modified,
            d.monitoreo,
            d.cyberark,
            d.user_cyberark,
            d.url_cyberark
        FROM ddi_devices d
        LEFT JOIN ddi_services  svc ON d._ref          = svc._ref
        LEFT JOIN ddi_licenses  lic ON d.hwid           = lic.hwid
        LEFT JOIN company       co  ON d.company_id     = co.id
        LEFT JOIN datacenter    dc  ON d.datacenter_id  = dc.id
        LEFT JOIN ddi_snow      sn  ON d.id             = sn.device_id
    """

    # Sortable column names matching the SELECT aliases above (index = DataTables col index)
    _DDI_INV_SORT_COLS = [
        'device_id', 'device', 'platform', 'model', 'hwplatform',
        'mgmt_ip', 'service_ip', 'sw_version', 'role', 'environment',
        'net_zone', 'phy_location', 'vendor_support', 'master_candidate',
        'grid_master', 'service_name', 'service_status', 'license_type',
        'expiry_date', 'expiration_status', 'company', 'datacenter',
        'cmdb_id', 'snow_link', 'last_modified',
        'monitoreo', 'cyberark', 'user_cyberark', 'url_cyberark',
    ]
    # Columns included in the global search
    _DDI_INV_SEARCH_COLS = [
        'device', 'platform', 'model', 'hwplatform', 'mgmt_ip', 'service_ip',
        'sw_version', 'role', 'environment', 'net_zone', 'phy_location',
        'vendor_support', 'service_name', 'company', 'datacenter',
    ]

    draw    = int(request.GET.get('draw', 1))
    start   = int(request.GET.get('start', 0))
    _dt_cfg = SiteSettings.objects.first()
    _dt_default = _dt_cfg.datatable_default_page_length if _dt_cfg else 25
    _dt_max = _dt_cfg.datatable_max_rows if _dt_cfg else 5000
    length  = int(request.GET.get('length', _dt_default))
    if length == -1 or length > _dt_max:
        length = _dt_max
    search  = request.GET.get('search[value]', '').strip()
    col_idx = int(request.GET.get('order[0][column]', 1))
    col_dir = request.GET.get('order[0][dir]', 'asc')

    sort_col  = _DDI_INV_SORT_COLS[col_idx] if col_idx < len(_DDI_INV_SORT_COLS) else 'device'
    direction = 'DESC' if col_dir == 'desc' else 'ASC'

    with connection.cursor() as cursor:
        # Total (before search)
        cursor.execute(f'SELECT COUNT(*) FROM ({SQL}) AS _ddi_total')
        total = cursor.fetchone()[0]

        if search:
            like = f'%{search.lower()}%'
            conditions = ' OR '.join(
                f"lower(COALESCE({c}::text, '')) LIKE %s" for c in _DDI_INV_SEARCH_COLS
            )
            where_sql    = f'WHERE {conditions}'
            where_params = [like] * len(_DDI_INV_SEARCH_COLS)
        else:
            where_sql    = ''
            where_params = []

        # Filtered count
        cursor.execute(
            f'SELECT COUNT(*) FROM ({SQL}) AS _ddi_filtered {where_sql}',
            where_params,
        )
        filtered = cursor.fetchone()[0]

        # Paginated fetch
        limit_sql = f'LIMIT {length} OFFSET {start}'
        cursor.execute(
            f'SELECT * FROM ({SQL}) AS _ddi {where_sql} ORDER BY {sort_col} {direction} NULLS LAST {limit_sql}',
            where_params,
        )
        raw_rows = cursor.fetchall()

    def _norm(i, val):
        if val is None:
            return '-'
        if i == 18:                 # expiry_date
            return str(val)[:10]
        if i == 24:                 # last_modified
            return str(val)[:16]
        if i in (25, 26):           # monitoreo, cyberark (booleans)
            return str(val)
        return val if isinstance(val, (str, int)) else str(val)

    data = [[_norm(i, val) for i, val in enumerate(raw)] for raw in raw_rows]

    return JsonResponse({
        'draw': draw,
        'recordsTotal': total,
        'recordsFiltered': filtered,
        'data': data,
    })


@login_required
def ddi_device_list_data(request):
    """
    AJAX endpoint — DDI Manage Devices DataTable (server-side).

    Returns only columns that exist directly in the ddi_devices table,
    plus resolved company/datacenter names.

    Columns (0-indexed):
      0  id               – DDIDevice PK (hidden)
      1  device           – Hostname
      2  _ref             – Service ref FK value
      3  platform
      4  hwid             – License hwid FK value
      5  model
      6  hwplatform
      7  mgmt_ip
      8  service_ip
      9  sw_version
      10 role
      11 tipo
      12 environment
      13 net_zone
      14 phy_location
      15 vendor_support
      16 master_candidate – 'Yes' / 'No'
      17 grid_master
      18 company
      19 datacenter
      20 last_modified
    """
    SQL = """
        SELECT
            d.id,
            d.device,
            d._ref,
            d.platform,
            d.hwid,
            d.model,
            d.hwplatform,
            d.mgmt_ip,
            d.service_ip,
            d.sw_version,
            d.role,
            d.tipo,
            d.environment,
            d.net_zone,
            d.phy_location,
            d.vendor_support,
            CASE WHEN d.master_candidate THEN 'Yes' ELSE 'No' END AS master_candidate,
            d.grid_master,
            co.name     AS company,
            dc.datacenter,
            d.last_modified
        FROM ddi_devices d
        LEFT JOIN company    co ON d.company_id    = co.id
        LEFT JOIN datacenter dc ON d.datacenter_id = dc.id
    """

    _DDI_DEV_SORT_COLS = [
        'id', 'device', '_ref', 'platform', 'hwid', 'model', 'hwplatform',
        'mgmt_ip', 'service_ip', 'sw_version', 'role', 'tipo', 'environment',
        'net_zone', 'phy_location', 'vendor_support', 'master_candidate',
        'grid_master', 'company', 'datacenter', 'last_modified',
    ]
    _DDI_DEV_SEARCH_COLS = [
        'device', 'platform', 'model', 'hwplatform', 'mgmt_ip', 'service_ip',
        'sw_version', 'role', 'tipo', 'environment', 'net_zone', 'phy_location',
        'vendor_support', 'company', 'datacenter',
    ]

    draw    = int(request.GET.get('draw', 1))
    start   = int(request.GET.get('start', 0))
    _dt_cfg = SiteSettings.objects.first()
    _dt_default = _dt_cfg.datatable_default_page_length if _dt_cfg else 25
    _dt_max = _dt_cfg.datatable_max_rows if _dt_cfg else 5000
    length  = int(request.GET.get('length', _dt_default))
    if length == -1 or length > _dt_max:
        length = _dt_max
    search  = request.GET.get('search[value]', '').strip()
    col_idx = int(request.GET.get('order[0][column]', 1))
    col_dir = request.GET.get('order[0][dir]', 'asc')

    sort_col  = _DDI_DEV_SORT_COLS[col_idx] if col_idx < len(_DDI_DEV_SORT_COLS) else 'device'
    direction = 'DESC' if col_dir == 'desc' else 'ASC'

    with connection.cursor() as cursor:
        cursor.execute(f'SELECT COUNT(*) FROM ({SQL}) AS _ddi_dev_total')
        total = cursor.fetchone()[0]

        if search:
            like = f'%{search.lower()}%'
            conditions = ' OR '.join(
                f"lower(COALESCE({c}::text, '')) LIKE %s" for c in _DDI_DEV_SEARCH_COLS
            )
            where_sql    = f'WHERE {conditions}'
            where_params = [like] * len(_DDI_DEV_SEARCH_COLS)
        else:
            where_sql    = ''
            where_params = []

        cursor.execute(
            f'SELECT COUNT(*) FROM ({SQL}) AS _ddi_dev_filtered {where_sql}',
            where_params,
        )
        filtered = cursor.fetchone()[0]

        limit_sql = f'LIMIT {length} OFFSET {start}'
        cursor.execute(
            f'SELECT * FROM ({SQL}) AS _ddi_dev {where_sql} ORDER BY {sort_col} {direction} NULLS LAST {limit_sql}',
            where_params,
        )
        raw_rows = cursor.fetchall()

    def _norm(i, val):
        if val is None:
            return '-'
        if i == 20:   # last_modified
            return str(val)[:16]
        return val if isinstance(val, (str, int)) else str(val)

    data = [[_norm(i, val) for i, val in enumerate(raw)] for raw in raw_rows]

    return JsonResponse({
        'draw': draw,
        'recordsTotal': total,
        'recordsFiltered': filtered,
        'data': data,
    })


@login_required
def ddi_device_history(_request, device_id):
    """
    AJAX — return the field-level change history for a single DDI device.

    Returns JSON ``{data: [...]}`` where each item has:
      timestamp, user, field, old, new
    """
    _ddi_hist_cfg = SiteSettings.objects.first()
    _ddi_hist_limit = _ddi_hist_cfg.ddi_device_history_limit if _ddi_hist_cfg else 200
    entries = (
        DDIDeviceChangeLog.objects
        .filter(device_id=device_id)
        .select_related('user')
        .order_by('-timestamp')[:_ddi_hist_limit]
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


# ---------------------------------------------------------------------------
# DDI Device CRUD
# ---------------------------------------------------------------------------

class DDIDeviceListView(LoginRequiredMixin, ListView):
    """Management list of all DDI devices."""

    model = DDIDevice
    template_name = 'ddi_manager/ddi_device_list.html'
    context_object_name = 'objects'
    paginate_by = None

    def get_queryset(self):
        return DDIDevice.objects.none()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = 'DDI Devices'
        ctx['total'] = DDIDevice.objects.count()
        return ctx


class DDIDeviceCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    """Register a new DDI device. Requires the 'add_ddidevice' permission."""

    model = DDIDevice
    form_class = DDIDeviceForm
    template_name = 'lb_manager/crud_form.html'
    success_url = reverse_lazy('ddi_device_list')
    permission_required = 'ddi_manager.add_ddidevice'
    raise_exception = True

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = 'Add DDI Device'
        ctx['list_url'] = reverse_lazy('ddi_device_list')
        ctx['list_label'] = 'DDI Devices'
        ctx['dado_de_alta_fields'] = ['monitoreo', 'cyberark', 'user_cyberark', 'url_cyberark']
        return ctx

    def form_valid(self, form):
        response = super().form_valid(form)
        # Save SNOW data
        cmdb_id   = form.cleaned_data.get('cmdb_id', '')
        snow_link = form.cleaned_data.get('snow_link', '')
        if cmdb_id or snow_link:
            DDISnow.objects.update_or_create(
                device=self.object,
                defaults={'cmdb_id': cmdb_id, 'snow_link': snow_link},
            )
        _log_ddi_change(self.request.user, self.object, ADDITION)
        messages.success(self.request, 'DDI Device created successfully.')
        return response


class DDIDeviceUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    """Edit an existing DDI device record. Requires the 'change_ddidevice' permission."""

    model = DDIDevice
    form_class = DDIDeviceForm
    template_name = 'lb_manager/crud_form.html'
    success_url = reverse_lazy('ddi_device_list')
    permission_required = 'ddi_manager.change_ddidevice'
    raise_exception = True

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = f'Edit DDI Device: {self.object.device}'
        ctx['list_url'] = reverse_lazy('ddi_device_list')
        ctx['list_label'] = 'DDI Devices'
        ctx['is_edit'] = True
        ctx['dado_de_alta_fields'] = ['monitoreo', 'cyberark', 'user_cyberark', 'url_cyberark']
        return ctx

    def form_valid(self, form):
        old = DDIDevice.objects.select_related('service', 'license', 'company', 'datacenter').get(pk=self.object.pk)

        # Capture old SNOW values before saving
        try:
            old_snow = old.snow
            old_cmdb   = old_snow.cmdb_id or ''
            old_snow_link = old_snow.snow_link or ''
        except DDISnow.DoesNotExist:
            old_cmdb = ''
            old_snow_link = ''

        response = super().form_valid(form)

        # Record model field changes
        _record_ddi_changes(self.request.user, old, self.object, form.changed_data)

        # Save SNOW data and record SNOW field changes
        new_cmdb   = form.cleaned_data.get('cmdb_id', '') or ''
        new_snow_link = form.cleaned_data.get('snow_link', '') or ''
        DDISnow.objects.update_or_create(
            device=self.object,
            defaults={'cmdb_id': new_cmdb, 'snow_link': new_snow_link},
        )
        snow_change_records = []
        if old_cmdb != new_cmdb:
            snow_change_records.append(DDIDeviceChangeLog(
                device_id=self.object.pk,
                device=str(self.object.device or self.object.pk),
                user=self.request.user,
                field_name='CMDB ID',
                old_value=old_cmdb[:500],
                new_value=new_cmdb[:500],
            ))
        if old_snow_link != new_snow_link:
            snow_change_records.append(DDIDeviceChangeLog(
                device_id=self.object.pk,
                device=str(self.object.device or self.object.pk),
                user=self.request.user,
                field_name='SNOW Link',
                old_value=old_snow_link[:500],
                new_value=new_snow_link[:500],
            ))
        if snow_change_records:
            DDIDeviceChangeLog.objects.bulk_create(snow_change_records)

        _log_ddi_change(self.request.user, self.object, CHANGE)
        messages.success(self.request, 'DDI Device updated successfully.')
        return response


class DDIDeviceDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    """Delete a DDI device record. Requires the 'delete_ddidevice' permission."""

    model = DDIDevice
    template_name = 'lb_manager/crud_confirm_delete.html'
    success_url = reverse_lazy('ddi_device_list')
    permission_required = 'ddi_manager.delete_ddidevice'
    raise_exception = True

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = 'Delete DDI Device'
        ctx['list_url'] = reverse_lazy('ddi_device_list')
        ctx['list_label'] = 'DDI Devices'
        ctx['object_name'] = self.object.device or str(self.object.pk)
        return ctx

    def form_valid(self, form):
        messages.success(self.request, 'DDI Device deleted successfully.')
        return super().form_valid(form)


# ---------------------------------------------------------------------------
# DDI Service CRUD
# ---------------------------------------------------------------------------

class DDIServiceListView(LoginRequiredMixin, ListView):
    """List all DDI Services."""

    model = DDIService
    template_name = 'ddi_manager/ddi_service_list.html'
    context_object_name = 'objects'
    paginate_by = None

    def get_queryset(self):
        return DDIService.objects.annotate(device_count=Count('devices')).order_by('service')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = 'DDI Services'
        ctx['total'] = DDIService.objects.count()
        return ctx


class DDIServiceCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    """Register a new DDI Service. Requires the 'add_ddiservice' permission."""

    model = DDIService
    form_class = DDIServiceForm
    template_name = 'lb_manager/crud_form.html'
    success_url = reverse_lazy('ddi_service_list')
    permission_required = 'ddi_manager.add_ddiservice'
    raise_exception = True

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = 'Add DDI Service'
        ctx['list_url'] = reverse_lazy('ddi_service_list')
        ctx['list_label'] = 'DDI Services'
        return ctx

    def form_valid(self, form):
        messages.success(self.request, 'DDI Service created successfully.')
        return super().form_valid(form)


class DDIServiceUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    """Edit a DDI Service record. Requires the 'change_ddiservice' permission."""

    model = DDIService
    form_class = DDIServiceForm
    template_name = 'lb_manager/crud_form.html'
    success_url = reverse_lazy('ddi_service_list')
    permission_required = 'ddi_manager.change_ddiservice'
    raise_exception = True

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = f'Edit DDI Service: {self.object.service or self.object.ref}'
        ctx['list_url'] = reverse_lazy('ddi_service_list')
        ctx['list_label'] = 'DDI Services'
        ctx['is_edit'] = True
        return ctx

    def form_valid(self, form):
        messages.success(self.request, 'DDI Service updated successfully.')
        return super().form_valid(form)


class DDIServiceDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    """Delete a DDI Service record. Requires the 'delete_ddiservice' permission."""

    model = DDIService
    template_name = 'lb_manager/crud_confirm_delete.html'
    success_url = reverse_lazy('ddi_service_list')
    permission_required = 'ddi_manager.delete_ddiservice'
    raise_exception = True

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = 'Delete DDI Service'
        ctx['list_url'] = reverse_lazy('ddi_service_list')
        ctx['list_label'] = 'DDI Services'
        ctx['object_name'] = self.object.service or self.object.ref
        return ctx

    def form_valid(self, form):
        messages.success(self.request, 'DDI Service deleted successfully.')
        return super().form_valid(form)


# ---------------------------------------------------------------------------
# DDI License CRUD
# ---------------------------------------------------------------------------

class DDILicenseListView(LoginRequiredMixin, ListView):
    """List all DDI Licenses."""

    model = DDILicense
    template_name = 'ddi_manager/ddi_license_list.html'
    context_object_name = 'objects'
    paginate_by = None

    def get_queryset(self):
        return DDILicense.objects.annotate(device_count=Count('devices')).order_by('hwid')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = 'DDI Licenses'
        ctx['total'] = DDILicense.objects.count()
        return ctx


class DDILicenseCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    """Register a new DDI License. Requires the 'add_ddilicense' permission."""

    model = DDILicense
    form_class = DDILicenseForm
    template_name = 'lb_manager/crud_form.html'
    success_url = reverse_lazy('ddi_license_list')
    permission_required = 'ddi_manager.add_ddilicense'
    raise_exception = True

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = 'Add DDI License'
        ctx['list_url'] = reverse_lazy('ddi_license_list')
        ctx['list_label'] = 'DDI Licenses'
        return ctx

    def form_valid(self, form):
        messages.success(self.request, 'DDI License created successfully.')
        return super().form_valid(form)


class DDILicenseUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    """Edit a DDI License record. Requires the 'change_ddilicense' permission."""

    model = DDILicense
    form_class = DDILicenseForm
    template_name = 'lb_manager/crud_form.html'
    success_url = reverse_lazy('ddi_license_list')
    permission_required = 'ddi_manager.change_ddilicense'
    raise_exception = True

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = f'Edit DDI License: {self.object.hwid}'
        ctx['list_url'] = reverse_lazy('ddi_license_list')
        ctx['list_label'] = 'DDI Licenses'
        ctx['is_edit'] = True
        return ctx

    def form_valid(self, form):
        messages.success(self.request, 'DDI License updated successfully.')
        return super().form_valid(form)


class DDILicenseDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    """Delete a DDI License record. Requires the 'delete_ddilicense' permission."""

    model = DDILicense
    template_name = 'lb_manager/crud_confirm_delete.html'
    success_url = reverse_lazy('ddi_license_list')
    permission_required = 'ddi_manager.delete_ddilicense'
    raise_exception = True

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = 'Delete DDI License'
        ctx['list_url'] = reverse_lazy('ddi_license_list')
        ctx['list_label'] = 'DDI Licenses'
        ctx['object_name'] = self.object.hwid
        return ctx

    def form_valid(self, form):
        messages.success(self.request, 'DDI License deleted successfully.')
        return super().form_valid(form)


# ---------------------------------------------------------------------------
# DDI Version Chart
# ---------------------------------------------------------------------------

@login_required
@permission_required('ddi_manager.view_ddidevice', raise_exception=True)
def ddi_version_chart(request):
    """Page view — DDI sw_version distribution bar chart."""
    from lb_manager.models import Company

    companies    = Company.objects.order_by('name')
    environments = (
        DDIDevice.objects
        .exclude(environment__isnull=True)
        .exclude(environment='')
        .values_list('environment', flat=True)
        .distinct()
        .order_by('environment')
    )
    return render(request, 'ddi_manager/ddi_version_chart.html', {
        'companies':    companies,
        'environments': list(environments),
    })


@login_required
@permission_required('ddi_manager.view_ddidevice', raise_exception=True)
def ddi_version_chart_data(request):
    """
    AJAX endpoint — sw_version distribution for DDI devices.

    Query params (all optional):
      environment   filter by environment string
      company       filter by Company pk
    """
    environment = request.GET.get('environment', '').strip()
    company_id  = request.GET.get('company',     '').strip()

    qs = DDIDevice.objects.exclude(sw_version__isnull=True).exclude(sw_version='')

    if environment:
        qs = qs.filter(environment=environment)
    if company_id:
        qs = qs.filter(company_id=company_id)

    # Per-version totals
    version_rows = (
        qs.values('sw_version')
        .annotate(count=Count('id'))
        .order_by('-count', 'sw_version')
    )

    versions = [r['sw_version'] for r in version_rows]
    counts   = [r['count']      for r in version_rows]
    total    = sum(counts)

    # Breakdown by environment (for stacked tooltip context)
    env_breakdown = {}
    if not environment:
        for v in versions:
            env_breakdown[v] = {
                row['environment']: row['count']
                for row in (
                    DDIDevice.objects
                    .filter(sw_version=v)
                    .values('environment')
                    .annotate(count=Count('id'))
                )
            }

    return JsonResponse({
        'total':         total,
        'versions':      versions,
        'counts':        counts,
        'env_breakdown': env_breakdown,
    })


# ── DDI Healthcheck ───────────────────────────────────────────────────────────

_HC_DDI_SORT_COLS: dict[int, str] = {
    0: 'fqdn',  1: 'fecha',             2: 'platform',         3: 'grid_status',
    4: 'dns_service', 5: 'dns_zones_count', 6: 'dhcp_service', 7: 'dhcp_failover',
    8: 'leases_activos', 9: 'networks_total', 10: 'networks_en_riesgo',
    11: 'networks_criticas', 12: 'backup_status',
    13: 'cpu_pct', 14: 'mem_pct', 15: 'disk_pct', 16: 'uptime_dias',
}
_HC_DDI_SEARCH_COLS = (
    'fqdn', 'platform', 'grid_status',
    'dns_service', 'dhcp_service', 'dhcp_failover', 'backup_status',
)


class DDIHealthCheckListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """Page shell — server-side DataTables for DDI daily health snapshots."""

    model              = HealthCheckDDI
    template_name      = 'ddi_manager/ddi_healthcheck_list.html'
    permission_required = 'ddi_manager.view_healthcheckddi'
    paginate_by        = None

    def get_queryset(self):
        """Return empty queryset; data is loaded via AJAX."""
        return HealthCheckDDI.objects.none()


@login_required
@permission_required('ddi_manager.view_healthcheckddi', raise_exception=True)
def ddi_healthcheck_data(request: HttpRequest) -> JsonResponse:
    """AJAX endpoint — server-side DataTables for DDI health snapshots."""
    from django.db.models import Q as _Q

    draw    = int(request.GET.get('draw', 1))
    start   = int(request.GET.get('start', 0))
    length  = int(request.GET.get('length', 25))
    search  = request.GET.get('search[value]', '').strip()
    col_idx = int(request.GET.get('order[0][column]', 0))
    col_dir = request.GET.get('order[0][dir]', 'desc')

    fqdn_f        = request.GET.get('fqdn', '').strip()
    fecha_desde_f = request.GET.get('fecha_desde', '').strip()
    fecha_hasta_f = request.GET.get('fecha_hasta', '').strip()
    platform_f    = request.GET.get('platform', '').strip()

    qs = HealthCheckDDI.objects.all()

    if fqdn_f:
        qs = qs.filter(fqdn__icontains=fqdn_f)
    if fecha_desde_f:
        qs = qs.filter(fecha__gte=fecha_desde_f)
    if fecha_hasta_f:
        qs = qs.filter(fecha__lte=fecha_hasta_f)
    if platform_f:
        qs = qs.filter(platform__iexact=platform_f)
    if search:
        q = _Q()
        for col in _HC_DDI_SEARCH_COLS:
            q |= _Q(**{f'{col}__icontains': search})
        qs = qs.filter(q)

    total_records = HealthCheckDDI.objects.count()
    filtered      = qs.count()

    order_col = _HC_DDI_SORT_COLS.get(col_idx, 'fecha')
    prefix    = '' if col_dir == 'asc' else '-'
    qs        = qs.order_by(f'{prefix}{order_col}')

    rows = [
        [
            obj.fqdn,               str(obj.fecha),          obj.platform or '',
            obj.grid_status or '',  obj.dns_service or '',   obj.dns_zones_count,
            obj.dhcp_service or '', obj.dhcp_failover or '', obj.leases_activos,
            obj.networks_total,     obj.networks_en_riesgo,  obj.networks_criticas,
            obj.backup_status or '', obj.cpu_pct,            obj.mem_pct,
            obj.disk_pct,           obj.uptime_dias,
        ]
        for obj in qs[start: start + length]
    ]

    return JsonResponse({
        'draw':            draw,
        'recordsTotal':    total_records,
        'recordsFiltered': filtered,
        'data':            rows,
    })
