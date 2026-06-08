"""
Health check and Bitacora (incident log) views.
"""

import csv
import json
import re

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.http import Http404, JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone as dj_timezone
from django.views.decorators.http import require_POST
from django.views.generic import ListView, CreateView, UpdateView, DeleteView

from ..models import (
    HealthCheckF5, HealthCheckDHCP, HealthCheckDNS, HealthCheckCertificate,
    BitacoraHealth, BitacoraEvent, HealthRule, SiteSettings,
)
from ..forms import HealthRuleForm
from .mixins import CRUDContextMixin, permission_json_required
from .utils import _dt_params, apply_search_filter, format_user_display


class HealthF5ListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """
    F5 health snapshot list, filterable by date range, device name, failsafe, and sync status.
    Shows an empty table until at least one filter is applied to avoid loading the full history.
    """

    model = HealthCheckF5
    template_name = 'lb_manager/health_f5_list.html'
    context_object_name = 'objects'
    paginate_by = None
    permission_required = 'lb_manager.view_healthcheckf5'
    raise_exception = True

    def get_queryset(self):
        fecha_desde = self.request.GET.get('fecha_desde')
        fecha_hasta = self.request.GET.get('fecha_hasta')
        fqdn = self.request.GET.get('fqdn')
        failsafe = self.request.GET.get('failsafe')
        sync = self.request.GET.get('sync')
        if not any([fecha_desde, fecha_hasta, fqdn, failsafe, sync]):
            return HealthCheckF5.objects.none()
        qs = super().get_queryset().order_by('-fecha')
        if fecha_desde:
            qs = qs.filter(fecha__gte=fecha_desde)
        if fecha_hasta:
            qs = qs.filter(fecha__lte=fecha_hasta)
        if fqdn:
            qs = qs.filter(fqdn__icontains=fqdn)
        if failsafe:
            qs = qs.filter(failsafe=failsafe)
        if sync:
            qs = qs.filter(sync=sync)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = 'F5 Health Checks'
        ctx['page_icon'] = 'fa-heart-pulse'
        ctx['fecha_desde'] = self.request.GET.get('fecha_desde', '')
        ctx['fecha_hasta'] = self.request.GET.get('fecha_hasta', '')
        ctx['fqdn'] = self.request.GET.get('fqdn', '')
        ctx['failsafe'] = self.request.GET.get('failsafe', '')
        ctx['sync'] = self.request.GET.get('sync', '')
        ctx['filter_applied'] = any([ctx['fecha_desde'], ctx['fecha_hasta'], ctx['fqdn'], ctx['failsafe'], ctx['sync']])
        ctx['fechas_disponibles'] = [
            d.strftime('%Y-%m-%d') for d in
            HealthCheckF5.objects.order_by('-fecha').values_list('fecha', flat=True).distinct()[:10]
            if d
        ]
        return ctx


class HealthF5BackupsView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """
    Shows F5 backup status for the most recent available date.
    Always displays the latest snapshot — no date filter needed.
    Columns: fqdn, company, last_folder, file_backup, backup_path.
    """

    model = HealthCheckF5
    template_name = 'lb_manager/health_f5_backups.html'
    context_object_name = 'objects'
    paginate_by = None
    permission_required = 'lb_manager.view_healthcheckf5'

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._latest_date = None

    def get_queryset(self):
        self._latest_date = (
            HealthCheckF5.objects
            .order_by('-fecha')
            .values_list('fecha', flat=True)
            .first()
        )
        if not self._latest_date:
            return HealthCheckF5.objects.none()
        return (
            HealthCheckF5.objects
            .filter(fecha=self._latest_date)
            .only('fqdn', 'company', 'last_folder', 'file_backup', 'backup_path')
            .order_by('fqdn')
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['latest_date'] = getattr(self, '_latest_date', None)
        return ctx


class HealthDHCPListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """
    DHCP health snapshot list, filterable by date range and device name.
    Shows an empty table until at least one filter is applied.
    """

    model = HealthCheckDHCP
    template_name = 'lb_manager/health_dhcp_list.html'
    context_object_name = 'objects'
    paginate_by = None
    permission_required = 'lb_manager.view_healthcheckdhcp'
    raise_exception = True

    def get_queryset(self):
        fecha_desde = self.request.GET.get('fecha_desde')
        fecha_hasta = self.request.GET.get('fecha_hasta')
        fqdn = self.request.GET.get('fqdn')
        if not any([fecha_desde, fecha_hasta, fqdn]):
            return HealthCheckDHCP.objects.none()
        qs = super().get_queryset().order_by('-fecha')
        if fecha_desde:
            qs = qs.filter(fecha__gte=fecha_desde)
        if fecha_hasta:
            qs = qs.filter(fecha__lte=fecha_hasta)
        if fqdn:
            qs = qs.filter(fqdn__icontains=fqdn)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = 'DHCP Health Checks'
        ctx['page_icon'] = 'fa-server'
        ctx['fecha_desde'] = self.request.GET.get('fecha_desde', '')
        ctx['fecha_hasta'] = self.request.GET.get('fecha_hasta', '')
        ctx['fqdn'] = self.request.GET.get('fqdn', '')
        ctx['list_url_name'] = 'health_dhcp_list'
        ctx['filter_applied'] = any([ctx['fecha_desde'], ctx['fecha_hasta'], ctx['fqdn']])
        _hc_cfg = SiteSettings.objects.first()
        _hc_limit = _hc_cfg.health_check_dates_limit if _hc_cfg else 60
        ctx['fechas_disponibles'] = [
            d.strftime('%Y-%m-%d') for d in
            HealthCheckDHCP.objects.order_by('-fecha').values_list('fecha', flat=True).distinct()[:_hc_limit]
            if d
        ]
        return ctx


class HealthDNSListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """
    DNS health snapshot list, filterable by date range and device name.
    Shows an empty table until at least one filter is applied.
    """

    model = HealthCheckDNS
    template_name = 'lb_manager/health_dns_list.html'
    context_object_name = 'objects'
    paginate_by = None
    permission_required = 'lb_manager.view_healthcheckdns'
    raise_exception = True

    def get_queryset(self):
        fecha_desde = self.request.GET.get('fecha_desde')
        fecha_hasta = self.request.GET.get('fecha_hasta')
        fqdn = self.request.GET.get('fqdn')
        if not any([fecha_desde, fecha_hasta, fqdn]):
            return HealthCheckDNS.objects.none()
        qs = super().get_queryset().order_by('-fecha')
        if fecha_desde:
            qs = qs.filter(fecha__gte=fecha_desde)
        if fecha_hasta:
            qs = qs.filter(fecha__lte=fecha_hasta)
        if fqdn:
            qs = qs.filter(fqdn__icontains=fqdn)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = 'DNS Health Checks'
        ctx['page_icon'] = 'fa-magnifying-glass-location'
        ctx['fecha_desde'] = self.request.GET.get('fecha_desde', '')
        ctx['fecha_hasta'] = self.request.GET.get('fecha_hasta', '')
        ctx['fqdn'] = self.request.GET.get('fqdn', '')
        ctx['list_url_name'] = 'health_dns_list'
        ctx['filter_applied'] = any([ctx['fecha_desde'], ctx['fecha_hasta'], ctx['fqdn']])
        ctx['fechas_disponibles'] = [
            d.strftime('%Y-%m-%d') for d in
            HealthCheckDNS.objects.order_by('-fecha').values_list('fecha', flat=True).distinct()[:10]
            if d
        ]
        return ctx


class BitacoraListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """Renders the Bitacora (health incidents) list page shell. Rows are loaded via bitacora_data."""

    model = BitacoraHealth
    template_name = 'lb_manager/bitacora_list.html'
    context_object_name = 'objects'
    paginate_by = None
    permission_required = 'lb_manager.view_bitacorahealth'
    raise_exception = True

    def get_queryset(self):
        return BitacoraHealth.objects.none()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = 'Bitacora de Salud'
        ctx['page_icon'] = 'fa-book-medical'
        ctx['total'] = BitacoraHealth.objects.count()
        User = get_user_model()
        ctx['filter_users'] = User.objects.filter(is_active=True).order_by('first_name', 'last_name', 'username')
        return ctx


@login_required
@permission_required('lb_manager.view_bitacorahealth', raise_exception=True)
def bitacora_data(request):
    """AJAX endpoint — returns paginated BitacoraHealth rows as JSON for DataTables."""

    COLUMNS = ['ticket_id', 'fqdn', 'fecha', 'severity', 'status', 'assigned_user__username',
               'creation_reason', 'created_at', 'closed_at']
    draw, start, length, search, col_idx, col_dir = _dt_params(request)

    tab = request.GET.get('tab', 'active')
    if tab == 'closed':
        qs = BitacoraHealth.objects.filter(status=BitacoraHealth.Status.CLOSED)
    else:
        qs = BitacoraHealth.objects.exclude(status=BitacoraHealth.Status.CLOSED)
    total = qs.count()

    # ── Advanced filters ──────────────────────────────────────────────────
    f_severity  = request.GET.get('f_severity', '').strip()
    f_status    = request.GET.get('f_status', '').strip()
    f_date_from = request.GET.get('f_date_from', '').strip()
    f_date_to   = request.GET.get('f_date_to', '').strip()
    f_user      = request.GET.get('f_user', '').strip()
    if f_severity in ('HIGH', 'MEDIUM', 'LOW'):
        qs = qs.filter(severity=f_severity)
    if f_status in ('OPEN', 'IN_PROGRESS') and tab != 'closed':
        qs = qs.filter(status=f_status)
    if f_date_from:
        qs = qs.filter(fecha__gte=f_date_from)
    if f_date_to:
        qs = qs.filter(fecha__lte=f_date_to)
    if f_user:
        qs = qs.filter(assigned_user_id=f_user)

    qs = apply_search_filter(qs, search, [
        'fqdn', 'severity', 'status', 'ticket_id', 'creation_reason',
        'assigned_user__username', 'assigned_user__first_name', 'assigned_user__last_name',
    ])
    filtered = qs.count()
    order_col = COLUMNS[col_idx] if col_idx < len(COLUMNS) else 'ticket_id'
    if col_dir == 'desc':
        order_col = f'-{order_col}'
    qs = qs.select_related('assigned_user').order_by(order_col)
    if length != -1:
        qs = qs[start:start + length]

    data = [[b.id, b.ticket_id or f'NSINC{b.pk:07d}', b.fqdn or '-', str(b.fecha) if b.fecha else '-',
             b.severity or '-', b.status or '-', format_user_display(b.assigned_user),
             (b.creation_reason or '-')[:80],
             str(b.created_at)[:16] if b.created_at else '-',
             str(b.closed_at)[:16] if b.closed_at else '-',
             b.comments or '-'] for b in qs]
    return JsonResponse({'draw': draw, 'recordsTotal': total, 'recordsFiltered': filtered, 'data': data})


@login_required
@permission_required('lb_manager.change_bitacorahealth', raise_exception=True)
def bitacora_edit(request, pk):
    """
    GET  → returns JSON with current values + list of active users (for the modal).
    POST → updates assigned_user, status, comments; requires manage_bitacora permission.
    """
    bitacora = get_object_or_404(BitacoraHealth.objects.select_related('assigned_user'), pk=pk)
    User = get_user_model()

    if request.method == 'POST':
        if not request.user.has_perm('lb_manager.manage_bitacora'):
            return JsonResponse({'ok': False, 'error': 'Sin permisos'}, status=403)

        assigned_user_id = request.POST.get('assigned_user', '').strip() or None
        status           = request.POST.get('status', '').strip() or None
        _comment_cfg     = SiteSettings.objects.first()
        _comment_limit   = _comment_cfg.bitacora_max_comment_length if _comment_cfg else 2000
        new_comment      = request.POST.get('comments', '').strip()[:_comment_limit]

        # Resolve assigned user FK
        if assigned_user_id:
            try:
                bitacora.assigned_user = User.objects.get(pk=assigned_user_id)
            except (User.DoesNotExist, ValueError):
                bitacora.assigned_user = None
        else:
            bitacora.assigned_user = None

        if status in [c[0] for c in BitacoraHealth.Status.choices]:
            bitacora.status = status

        # Accumulate comments with timestamp instead of overwriting
        if new_comment:
            ts = dj_timezone.localtime(dj_timezone.now()).strftime('%Y-%m-%d %H:%M')
            entry = f"[{ts} – {request.user.username}] {new_comment}"
            bitacora.comments = (
                f"{bitacora.comments}\n{entry}" if bitacora.comments else entry
            )

        if status == BitacoraHealth.Status.CLOSED and not bitacora.closed_at:
            bitacora.closed_at   = dj_timezone.now()
            bitacora.closed_user = request.user.username
        elif status != BitacoraHealth.Status.CLOSED:
            bitacora.closed_at   = None
            bitacora.closed_user = None
        bitacora.save()

        assigned_display = '-'
        if bitacora.assigned_user:
            name = f"{bitacora.assigned_user.first_name} {bitacora.assigned_user.last_name}".strip()
            assigned_display = name or bitacora.assigned_user.username

        event_parts = [f"Status → {status}", f"Assigned → {assigned_display}"]
        if new_comment:
            event_parts.append(f"Comment: {new_comment}")
        BitacoraEvent.objects.create(
            bitacora=bitacora,
            message=f"[{request.user.username}] " + " | ".join(event_parts),
        )
        return JsonResponse({'ok': True})

    # GET — return current data + user list
    qs_users = (
        User.objects.filter(is_active=True, last_login__isnull=False)
        .order_by('first_name', 'last_name', 'username')
    )
    users = [
        {
            'value': u.pk,
            'label': f"{u.first_name} {u.last_name}".strip() or u.username,
        }
        for u in qs_users
    ]
    history_qs = (
        BitacoraHealth.objects
        .filter(fqdn=bitacora.fqdn, status=BitacoraHealth.Status.CLOSED)
        .exclude(pk=bitacora.pk)
        .select_related('assigned_user')
        .order_by('-fecha')
    )
    history_data = [
        {
            'fecha':           str(h.fecha) if h.fecha else '-',
            'severity':        h.severity or '-',
            'creation_reason': h.creation_reason or '-',
            'closed_at':       str(h.closed_at)[:16] if h.closed_at else '-',
            'assigned_user': (
                (f"{h.assigned_user.first_name} {h.assigned_user.last_name}".strip()
                 or h.assigned_user.username)
                if h.assigned_user else '-'
            ),
            'comments':        h.comments or '-',
        }
        for h in history_qs
    ]
    events = [
        {
            'created_at': str(e.created_at)[:19] if e.created_at else '-',
            'message':    e.message or '-',
        }
        for e in BitacoraEvent.objects.filter(bitacora=bitacora).order_by('created_at')
    ]
    return JsonResponse({
        'id':               bitacora.pk,
        'ticket_id':        bitacora.ticket_id or f'NSINC{bitacora.pk:07d}',
        'fqdn':             bitacora.fqdn or '',
        'fecha':            str(bitacora.fecha) if bitacora.fecha else '',
        'severity':         bitacora.severity or '',
        'status':           bitacora.status or '',
        'assigned_user_id': bitacora.assigned_user_id or '',
        'comments':         bitacora.comments or '',
        'creation_reason':  bitacora.creation_reason or '',
        'users':            users,
        'history':          history_data,
        'events':           events,
    })


@login_required
@permission_required('lb_manager.view_bitacorahealth', raise_exception=True)
def bitacora_ticket_redirect(_request, ticket_ref):
    """
    Redirect to the Bitácora list page with the ticket's modal auto-opened.
    ticket_ref can be the NSINC format (e.g. NSINC0001234) or a numeric pk.
    """
    ticket = BitacoraHealth.objects.filter(ticket_id__iexact=ticket_ref).first()
    if not ticket and ticket_ref.isdigit():
        ticket = BitacoraHealth.objects.filter(pk=int(ticket_ref)).first()
    if not ticket:
        m = re.search(r'\d+$', ticket_ref)
        if m:
            ticket = BitacoraHealth.objects.filter(pk=int(m.group())).first()
    if not ticket:
        raise Http404('Ticket no encontrado')

    tab = 'closed' if ticket.status == BitacoraHealth.Status.CLOSED else 'active'
    return redirect(f"{reverse('bitacora_list')}?open={ticket.pk}&tab={tab}")


@login_required
@permission_required('lb_manager.change_bitacorahealth', raise_exception=True)
@permission_json_required('lb_manager.manage_bitacora')
@require_POST
def bitacora_bulk_action(request):  # pylint: disable=too-many-return-statements
    """Bulk close or reassign multiple Bitácora tickets. Requires manage_bitacora permission."""
    try:
        payload = json.loads(request.body)
    except (ValueError, KeyError):
        return JsonResponse({'ok': False, 'error': 'Invalid payload'}, status=400)

    action = payload.get('action')
    raw_ids = payload.get('ids', [])
    _bulk_cfg = SiteSettings.objects.first()
    _bulk_limit = _bulk_cfg.bulk_close_limit if _bulk_cfg else 500
    ids = [int(i) for i in raw_ids if str(i).isdigit()][:_bulk_limit]

    if not ids:
        return JsonResponse({'ok': False, 'error': 'No hay tickets seleccionados'})

    qs = BitacoraHealth.objects.filter(pk__in=ids)

    if action == 'close':
        updated = qs.exclude(status=BitacoraHealth.Status.CLOSED).update(
            status=BitacoraHealth.Status.CLOSED,
            closed_at=dj_timezone.now(),
        )
        return JsonResponse({'ok': True, 'updated': updated})

    if action == 'assign':
        user_id = payload.get('user_id')
        if user_id:
            User = get_user_model()
            try:
                user = User.objects.get(pk=int(user_id))
            except (User.DoesNotExist, ValueError, TypeError):
                return JsonResponse({'ok': False, 'error': 'Usuario no encontrado'})
            qs.update(assigned_user=user)
        else:
            qs.update(assigned_user=None)
        return JsonResponse({'ok': True, 'updated': len(ids)})

    return JsonResponse({'ok': False, 'error': 'Acción desconocida'})


@login_required
@permission_required('lb_manager.view_bitacorahealth', raise_exception=True)
@permission_json_required('lb_manager.manage_bitacora')
def bitacora_export(request):
    """Stream a CSV file of BitacoraHealth records (defaults to closed tickets).
    Pass ?ids=1,2,3 to export a specific selection.
    Requires manage_bitacora permission to prevent IDOR data leakage.
    """

    ids_param = request.GET.get('ids', '').strip()
    if ids_param:
        _csv_cfg = SiteSettings.objects.first()
        _csv_limit = _csv_cfg.csv_export_limit if _csv_cfg else 1000
        ids = [int(i) for i in ids_param.split(',') if i.strip().isdigit()][:_csv_limit]
        qs = BitacoraHealth.objects.filter(pk__in=ids)
        filename = 'bitacora_seleccion.csv'
    else:
        # Whitelist tab values to prevent HTTP response header injection via filename
        tab = request.GET.get('tab', 'closed')
        if tab not in ('closed', 'active'):
            tab = 'closed'
        if tab == 'closed':
            qs = BitacoraHealth.objects.filter(status=BitacoraHealth.Status.CLOSED)
        else:
            qs = BitacoraHealth.objects.exclude(status=BitacoraHealth.Status.CLOSED)
        filename = f'bitacora_{tab}.csv'
    qs = qs.select_related('assigned_user').order_by('-created_at')

    class _Echo:
        def write(self, value):
            return value

    def _rows():
        writer = csv.writer(_Echo())
        yield writer.writerow([
            'Ticket ID', 'FQDN', 'Fecha', 'Severity', 'Status',
            'Assigned User', 'Reason', 'Created At', 'Closed At', 'Comments',
        ])
        for b in qs:
            yield writer.writerow([
                b.ticket_id or f'NSINC{b.pk:07d}',
                b.fqdn or '-',
                str(b.fecha) if b.fecha else '-',
                b.severity or '-',
                b.status or '-',
                format_user_display(b.assigned_user),
                b.creation_reason or '-',
                str(b.created_at)[:16] if b.created_at else '-',
                str(b.closed_at)[:16] if b.closed_at else '-',
                b.comments or '-',
            ])

    response = StreamingHttpResponse(_rows(), content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


class HealthRuleListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """Renders the Health Rule list. Rules are loaded directly (not via AJAX) as the table is small."""

    model = HealthRule
    template_name = 'lb_manager/health_rule_list.html'
    context_object_name = 'objects'
    paginate_by = None
    permission_required = 'lb_manager.view_healthrule'
    raise_exception = True

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = 'Health Rules'
        ctx['page_icon'] = 'fa-ruler'
        return ctx


class HealthRuleCreateView(CRUDContextMixin, LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = HealthRule
    form_class = HealthRuleForm
    template_name = 'lb_manager/crud_form.html'
    success_url = reverse_lazy('health_rule_list')
    permission_required = 'lb_manager.add_healthrule'
    raise_exception = True
    crud_list_url     = 'health_rule_list'
    crud_list_label   = 'Health Rules'
    page_title_create = 'Add Health Rule'

    def form_valid(self, form):
        messages.success(self.request, 'Health Rule created successfully.')
        return super().form_valid(form)


class HealthRuleUpdateView(CRUDContextMixin, LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = HealthRule
    form_class = HealthRuleForm
    template_name = 'lb_manager/crud_form.html'
    success_url = reverse_lazy('health_rule_list')
    permission_required = 'lb_manager.change_healthrule'
    raise_exception = True
    crud_list_url   = 'health_rule_list'
    crud_list_label = 'Health Rules'
    page_title_edit = 'Edit Health Rule: {obj}'

    def form_valid(self, form):
        messages.success(self.request, 'Health Rule updated successfully.')
        return super().form_valid(form)


class HealthRuleDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = HealthRule
    template_name = 'lb_manager/crud_confirm_delete.html'
    success_url = reverse_lazy('health_rule_list')
    permission_required = 'lb_manager.delete_healthrule'
    raise_exception = True

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['object_name'] = str(self.object)
        ctx['list_url'] = reverse_lazy('health_rule_list')
        ctx['list_label'] = 'Health Rules'
        return ctx

    def form_valid(self, form):
        messages.success(self.request, 'Health Rule deleted.')
        return super().form_valid(form)


class HealthCertificateListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """
    Certificate health snapshot list, filterable by date range, device, and
    expiration threshold (days_max).

    Shows an empty table until at least one filter is applied to avoid loading
    the full history. The ``days_max`` filter is useful for surfacing only
    certificates expiring within N days.
    """

    model = HealthCheckCertificate
    template_name = 'lb_manager/health_certificate_list.html'
    context_object_name = 'objects'
    paginate_by = None
    permission_required = 'lb_manager.view_healthcheckcertificate'
    raise_exception = True

    def get_queryset(self):
        fecha_desde = self.request.GET.get('fecha_desde')
        fecha_hasta = self.request.GET.get('fecha_hasta')
        fqdn        = self.request.GET.get('fqdn')
        days_max    = self.request.GET.get('days_max')
        if not any([fecha_desde, fecha_hasta, fqdn, days_max]):
            return HealthCheckCertificate.objects.none()
        qs = super().get_queryset()
        if fecha_desde:
            qs = qs.filter(fecha__gte=fecha_desde)
        if fecha_hasta:
            qs = qs.filter(fecha__lte=fecha_hasta)
        if fqdn:
            qs = qs.filter(device__icontains=fqdn)
        if days_max:
            try:
                qs = qs.filter(days_remaining__lte=int(days_max))
            except ValueError:
                pass
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['page_title']     = 'Certificate Health Checks'
        ctx['page_icon']      = 'fa-shield-halved'
        ctx['fecha_desde']    = self.request.GET.get('fecha_desde', '')
        ctx['fecha_hasta']    = self.request.GET.get('fecha_hasta', '')
        ctx['fqdn']           = self.request.GET.get('fqdn', '')
        ctx['days_max']       = self.request.GET.get('days_max', '')
        ctx['list_url_name']  = 'health_certificate_list'
        ctx['filter_applied'] = any([ctx['fecha_desde'], ctx['fecha_hasta'], ctx['fqdn'], ctx['days_max']])
        _hc_cfg   = SiteSettings.objects.first()
        _hc_limit = _hc_cfg.health_check_dates_limit if _hc_cfg else 60
        ctx['fechas_disponibles'] = [
            d.strftime('%Y-%m-%d') for d in
            HealthCheckCertificate.objects.order_by('-fecha').values_list('fecha', flat=True).distinct()[:_hc_limit]
            if d
        ]
        return ctx
