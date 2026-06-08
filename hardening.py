"""
LB Hardening and Bitácora Hardening views.
"""

import json
from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db.models import Count, F, Max, Q, TextField, Value
from django.db.models.functions import Coalesce, Concat, TruncMonth
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone as dj_timezone
from django.views.decorators.http import require_POST
from django.views.generic import ListView

from ..models import LBHardening, BitacoraHardening, SiteSettings, Company, LBPhysical, LBGuest
from .utils import _dt_params, apply_search_filter, format_user_display


class LBHardeningListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """Hardening / vulnerability checks for LB devices."""

    model = LBHardening
    template_name = 'lb_manager/lb_hardening_list.html'
    context_object_name = 'objects'
    paginate_by = None
    permission_required = 'lb_manager.view_lbhardening'
    raise_exception = True

    def get_queryset(self):
        return LBHardening.objects.none()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['total'] = LBHardening.objects.count()
        ctx['devices'] = (
            LBHardening.objects
            .values_list('device', flat=True)
            .distinct()
            .order_by('device')
        )
        ctx['codes'] = (
            LBHardening.objects
            .values_list('code', flat=True)
            .distinct()
            .order_by('code')
        )
        return ctx


@login_required
@permission_required('lb_manager.view_lbhardening', raise_exception=True)
def lb_hardening_data(request):
    """
    AJAX endpoint — LB hardening checks for DataTables (server-side).

    Columns (0-indexed):
      0  id
      1  device
      2  code
      3  descripcion
      4  valor_obtenido
      5  valor_recomendado
      6  resultado
      7  comando_para_validar
      8  fecha
    """
    draw, start, length, search, col_idx, col_dir = _dt_params(request, default_col=1)
    search = search.lower()

    device_filter    = request.GET.get('device', '').strip()
    code_filter      = request.GET.get('code', '').strip()
    resultado_filter = request.GET.get('resultado', '').strip().lower()
    date_from        = request.GET.get('date_from', '').strip()
    date_to          = request.GET.get('date_to', '').strip()

    _HRD_ORDER_COLS = {1: 'device', 2: 'code', 3: 'descripcion', 6: 'resultado', 8: 'fecha'}

    qs = LBHardening.objects.all()
    if device_filter:
        qs = qs.filter(device=device_filter)
    if code_filter:
        qs = qs.filter(code=code_filter)
    if resultado_filter:
        qs = qs.filter(resultado__iexact=resultado_filter)
    if date_from:
        qs = qs.filter(fecha__gte=date_from)
    if date_to:
        qs = qs.filter(fecha__lte=date_to)

    total = qs.count()

    qs = apply_search_filter(qs, search, [
        'device', 'code', 'descripcion', 'valor_obtenido',
        'valor_recomendado', 'resultado', 'comando_para_validar',
    ])
    filtered = qs.count()

    sort_col = _HRD_ORDER_COLS.get(col_idx, 'device')
    if col_dir == 'desc':
        sort_col = f'-{sort_col}'
    qs = qs.order_by(sort_col)
    if length != -1:
        qs = qs[start:start + length]

    data = [
        [
            h.pk,
            h.device or '-',
            h.code or '-',
            h.descripcion or '-',
            h.valor_obtenido or '-',
            h.valor_recomendado or '-',
            h.resultado or '-',
            h.comando_para_validar or '-',
            str(h.fecha) if h.fecha else '-',
        ]
        for h in qs
    ]

    return JsonResponse({
        'draw': draw,
        'recordsTotal': total,
        'recordsFiltered': filtered,
        'data': data,
    })


# ============================================================
#  BITÁCORA HARDENING
# ============================================================

class BitacoraHardeningListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """Hardening incident tickets (auto-created for failed checks)."""

    model = BitacoraHardening
    template_name = 'lb_manager/bitacora_hardening_list.html'
    context_object_name = 'objects'
    paginate_by = None
    permission_required = 'lb_manager.view_bitacorahardening'
    raise_exception = True

    def get_queryset(self):
        return BitacoraHardening.objects.none()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['total'] = BitacoraHardening.objects.count()
        User = get_user_model()
        ctx['filter_users'] = User.objects.filter(is_active=True).order_by('first_name', 'last_name', 'username')
        ctx['devices'] = (
            BitacoraHardening.objects
            .values_list('device', flat=True).distinct().order_by('device')
        )
        ctx['codes'] = (
            BitacoraHardening.objects
            .values_list('code', flat=True).distinct().order_by('code')
        )
        return ctx


@login_required
@permission_required('lb_manager.view_bitacorahardening', raise_exception=True)
def bitacora_hardening_data(request):
    """
    AJAX endpoint for Bitácora Hardening DataTables.

    Columns (0-indexed):
      0  id
      1  ticket_id
      2  device
      3  code
      4  descripcion
      5  valor_obtenido
      6  status
      7  assigned_user
      8  fecha
      9  created_at
      10 closed_at
      11 comments
    """
    COLUMNS = ['ticket_id', 'device', 'code', 'descripcion', 'valor_obtenido',
               'status', 'assigned_user__username', 'fecha', 'created_at', 'closed_at']

    draw, start, length, search, col_idx, col_dir = _dt_params(request)

    tab = request.GET.get('tab', 'active')
    if tab == 'closed':
        qs = BitacoraHardening.objects.filter(status=BitacoraHardening.Status.CLOSED)
    else:
        qs = BitacoraHardening.objects.exclude(status=BitacoraHardening.Status.CLOSED)
    total = qs.count()

    f_device     = request.GET.get('f_device', '').strip()
    f_code       = request.GET.get('f_code', '').strip()
    f_status     = request.GET.get('f_status', '').strip()
    f_date_from  = request.GET.get('f_date_from', '').strip()
    f_date_to    = request.GET.get('f_date_to', '').strip()
    f_user       = request.GET.get('f_user', '').strip()

    if f_device:
        qs = qs.filter(device=f_device)
    if f_code:
        qs = qs.filter(code=f_code)
    if f_status in ('OPEN', 'IN_PROGRESS') and tab != 'closed':
        qs = qs.filter(status=f_status)
    if f_date_from:
        qs = qs.filter(fecha__gte=f_date_from)
    if f_date_to:
        qs = qs.filter(fecha__lte=f_date_to)
    if f_user:
        qs = qs.filter(assigned_user_id=f_user)

    qs = apply_search_filter(qs, search, [
        'device', 'code', 'ticket_id', 'descripcion', 'assigned_user__username',
    ])
    filtered = qs.count()

    order_col = COLUMNS[col_idx] if col_idx < len(COLUMNS) else 'ticket_id'
    if col_dir == 'desc':
        order_col = f'-{order_col}'
    qs = qs.select_related('assigned_user').order_by(order_col)
    if length != -1:
        qs = qs[start:start + length]

    data = [
        [
            b.pk,
            b.ticket_id or f'NSHRD{b.pk:07d}',
            b.device or '-',
            b.code or '-',
            (b.descripcion or '-')[:80],
            b.valor_obtenido or '-',
            b.status or '-',
            format_user_display(b.assigned_user),
            str(b.fecha) if b.fecha else '-',
            str(b.created_at)[:16] if b.created_at else '-',
            str(b.closed_at)[:16] if b.closed_at else '-',
            b.comments or '-',
        ]
        for b in qs
    ]
    return JsonResponse({'draw': draw, 'recordsTotal': total, 'recordsFiltered': filtered, 'data': data})


@login_required
@permission_required('lb_manager.change_bitacorahardening', raise_exception=True)
def bitacora_hardening_edit(request, pk):
    """
    GET  → JSON with ticket data + user list (for edit modal).
    POST → update status, assigned_user, comments. Requires manage_bitacora_hardening.
    """
    ticket = get_object_or_404(
        BitacoraHardening.objects.select_related('assigned_user'), pk=pk
    )
    User = get_user_model()

    if request.method == 'POST':
        if not request.user.has_perm('lb_manager.manage_bitacora_hardening'):
            return JsonResponse({'ok': False, 'error': 'Sin permiso.'}, status=403)

        assigned_user_id = request.POST.get('assigned_user', '').strip()
        status = request.POST.get('status', '').strip()
        _hrd_cfg     = SiteSettings.objects.first()
        _hrd_limit   = _hrd_cfg.bitacora_max_comment_length if _hrd_cfg else 2000
        new_comment  = request.POST.get('comments', '').strip()[:_hrd_limit]

        try:
            if assigned_user_id:
                ticket.assigned_user = User.objects.get(pk=assigned_user_id)
            else:
                ticket.assigned_user = None
        except User.DoesNotExist:
            ticket.assigned_user = None

        if status in [c[0] for c in BitacoraHardening.Status.choices]:
            ticket.status = status

        if new_comment:
            tz = dj_timezone
            ts = tz.now().strftime('%d/%m/%Y %H:%M')
            entry = f"[{ts} — {request.user.username}] {new_comment}"
            ticket.comments = f"{ticket.comments}\n{entry}" if ticket.comments else entry

        if status == BitacoraHardening.Status.CLOSED and not ticket.closed_at:
            ticket.closed_at   = dj_timezone.now()
            ticket.closed_user = request.user.username
        elif status != BitacoraHardening.Status.CLOSED:
            ticket.closed_at   = None
            ticket.closed_user = None

        ticket.save()

        name = ''
        if ticket.assigned_user:
            name = f"{ticket.assigned_user.first_name} {ticket.assigned_user.last_name}".strip()
            name = name or ticket.assigned_user.username
        return JsonResponse({'ok': True, 'assigned_display': name or '—'})

    # GET — return ticket data
    users = [
        {'value': u.pk, 'label': f"{u.first_name} {u.last_name}".strip() or u.username}
        for u in User.objects.filter(is_active=True).order_by('first_name', 'last_name')
    ]
    return JsonResponse({
        'id':               ticket.pk,
        'ticket_id':        ticket.ticket_id or f'NSHRD{ticket.pk:07d}',
        'device':           ticket.device or '',
        'code':             ticket.code or '',
        'descripcion':      ticket.descripcion or '',
        'valor_obtenido':   ticket.valor_obtenido or '',
        'valor_recomendado': ticket.valor_recomendado or '',
        'fecha':            str(ticket.fecha) if ticket.fecha else '',
        'status':           ticket.status or '',
        'assigned_user_id': ticket.assigned_user_id or '',
        'comments':         ticket.comments or '',
        'users':            users,
    })



@login_required
@require_POST
@permission_required('lb_manager.manage_bitacora_hardening', raise_exception=True)
def bitacora_hardening_bulk_action(request):
    """
    Bulk assign-to-user + In Progress, or bulk close, for Hardening tickets.

    JSON payload:
      action='assign': {action, ids, user_id} → sets assigned_user + status=IN_PROGRESS (skips CLOSED)
      action='close':  {action, ids}          → validates same code + same assigned_user, then closes
    """
    try:
        payload = json.loads(request.body)
    except (ValueError, KeyError):
        return JsonResponse({'ok': False, 'error': 'Payload inválido'}, status=400)

    action  = payload.get('action')
    raw_ids = payload.get('ids', [])
    _cfg    = SiteSettings.objects.first()
    _limit  = _cfg.bulk_close_limit if _cfg else 500
    ids     = [int(i) for i in raw_ids if str(i).isdigit()][:_limit]

    if not ids:
        return JsonResponse({'ok': False, 'error': 'No hay tickets seleccionados'})

    qs = BitacoraHardening.objects.filter(pk__in=ids)

    if action == 'assign':
        User = get_user_model()
        user_id = payload.get('user_id')
        if not user_id:
            return JsonResponse({'ok': False, 'error': 'Usuario requerido'})
        try:
            user = User.objects.get(pk=int(user_id))
        except (User.DoesNotExist, ValueError, TypeError):
            return JsonResponse({'ok': False, 'error': 'Usuario no encontrado'})
        updated = qs.exclude(status=BitacoraHardening.Status.CLOSED).update(
            assigned_user=user,
            status=BitacoraHardening.Status.IN_PROGRESS,
        )
        return JsonResponse({'ok': True, 'updated': updated})

    if action == 'close':
        comment_text = str(payload.get('comment', '') or '').strip()
        # Filter to non-closed tickets FIRST, then validate only those
        to_close = qs.exclude(status=BitacoraHardening.Status.CLOSED)

        if not to_close.exists():
            return JsonResponse({'ok': False, 'error': 'Todos los tickets seleccionados ya están cerrados.'})

        # Normalize codes: strip whitespace and treat NULL as empty string
        raw_codes = to_close.values_list('code', flat=True).distinct()
        codes = list({(c or '').strip() for c in raw_codes})
        if len(codes) != 1:
            return JsonResponse({
                'ok': False,
                'error': 'Solo puedes cerrar tickets que compartan el mismo Code.',
            })
        assigned = list(to_close.order_by().values_list('assigned_user_id', flat=True).distinct())
        if len(assigned) != 1 or assigned[0] is None:
            User = get_user_model()
            user_labels = []
            for uid in assigned:
                if uid is None:
                    user_labels.append('(sin asignar)')
                else:
                    try:
                        u = User.objects.get(pk=uid)
                        name = f'{u.first_name} {u.last_name}'.strip() or u.username
                        user_labels.append(name)
                    except User.DoesNotExist:
                        user_labels.append(f'(usuario eliminado id={uid})')
            return JsonResponse({
                'ok': False,
                'error': (
                    f'Todos los tickets deben tener el mismo usuario asignado. '
                    f'IDs recibidos: {ids}. '
                    f'assigned_user_ids encontrados: {assigned}. '
                    f'Nombres: {", ".join(user_labels)}.'
                ),
            })
        now = dj_timezone.now()
        now_local = dj_timezone.localtime(now).strftime('%Y-%m-%d %H:%M')
        if comment_text:
            comment_entry = f'\n[{now_local} — {request.user.username}] {comment_text}'
            updated = to_close.update(
                status=BitacoraHardening.Status.CLOSED,
                closed_at=now,
                closed_user=request.user.username,
                comments=Concat(Coalesce(F('comments'), Value(''), output_field=TextField()), Value(comment_entry), output_field=TextField()),
            )
        else:
            updated = to_close.update(
                status=BitacoraHardening.Status.CLOSED,
                closed_at=now,
                closed_user=request.user.username,
            )
        return JsonResponse({'ok': True, 'updated': updated})

    return JsonResponse({'ok': False, 'error': 'Acción desconocida'})


# ── Hardening Chart ──────────────────────────────────────────────────────────

@login_required
@permission_required('lb_manager.view_lbhardening', raise_exception=True)
def hardening_chart(request):
    """Page view — hardening pie chart with date-range, device and company filters."""
    devices = (
        LBHardening.objects
        .order_by('device')
        .values_list('device', flat=True)
        .distinct()
    )
    companies = Company.objects.order_by('client_code').values('client_code', 'name')

    # Map device → client_code so the JS can filter the device dropdown by company
    phys_map  = {p.device: p.company.client_code
                 for p in LBPhysical.objects.select_related('company').filter(company__isnull=False)}
    guest_map = {g.device: g.company.client_code
                 for g in LBGuest.objects.select_related('company').filter(company__isnull=False)}
    device_company_map = {**phys_map, **guest_map}

    return render(request, 'lb_manager/hardening_chart.html', {
        'devices':            devices,
        'companies':          companies,
        'device_company_map': json.dumps(device_company_map),
    })


@login_required
@permission_required('lb_manager.view_lbhardening', raise_exception=True)
def hardening_chart_data(request):
    """
    AJAX endpoint — returns passed/failed counts for the pie chart.

    Query params:
      date_from  YYYY-MM-DD  (required)
      date_to    YYYY-MM-DD  (required)
      device     device name (optional, '' = all)
    """
    date_from = request.GET.get('date_from', '')
    date_to   = request.GET.get('date_to',   '')
    device    = request.GET.get('device',    '').strip()
    company   = request.GET.get('company',   '').strip()

    # Validate date format to prevent Django ORM DataError (500) on invalid input
    def _parse_date(val):
        if not val:
            return None
        try:
            return datetime.strptime(val.strip(), '%Y-%m-%d').date()
        except ValueError:
            return None

    parsed_from = _parse_date(date_from)
    parsed_to   = _parse_date(date_to)

    qs = LBHardening.objects.all()

    if parsed_from:
        qs = qs.filter(fecha__gte=parsed_from)
    if parsed_to:
        qs = qs.filter(fecha__lte=parsed_to)
    if company:
        phys_devs  = LBPhysical.objects.filter(company__client_code__iexact=company).values_list('device', flat=True)
        guest_devs = LBGuest.objects.filter(company__client_code__iexact=company).values_list('device', flat=True)
        qs = qs.filter(device__in=list(phys_devs) + list(guest_devs))
    if device:
        qs = qs.filter(device=device)

    total  = qs.count()
    passed = qs.filter(resultado__iexact='passed').count()
    failed = qs.filter(resultado__iexact='failed').count()
    other  = total - passed - failed

    passed_pct = round(passed / total * 100, 1) if total else 0
    failed_pct = round(failed / total * 100, 1) if total else 0
    other_pct  = round(other  / total * 100, 1) if total else 0

    return JsonResponse({
        'total':       total,
        'passed':      passed,
        'failed':      failed,
        'other':       other,
        'passed_pct':  passed_pct,
        'failed_pct':  failed_pct,
        'other_pct':   other_pct,
    })


# ── Hardening Heatmap & Recurrence ───────────────────────────────────────────

_HEATMAP_DEVICE_LIMIT = 50
_HEATMAP_CODE_LIMIT   = 30
_TOP_LIMIT            = 10
_RECURRENCE_MIN_MONTHS = 3


def _hardening_window_qs(request):
    """Return a base QuerySet filtered by ``window`` days and optional company."""
    try:
        window = int(request.GET.get('window', '90'))
    except ValueError:
        window = 90
    window = max(7, min(window, 365))
    cutoff = dj_timezone.localdate() - timedelta(days=window)

    qs = LBHardening.objects.filter(fecha__gte=cutoff)
    company = request.GET.get('company', '').strip()
    if company:
        phys_devs  = LBPhysical.objects.filter(company__client_code__iexact=company).values_list('device', flat=True)
        guest_devs = LBGuest.objects.filter(company__client_code__iexact=company).values_list('device', flat=True)
        qs = qs.filter(device__in=list(phys_devs) + list(guest_devs))
    return qs, window


@login_required
@permission_required('lb_manager.view_lbhardening', raise_exception=True)
def hardening_heatmap_data(request):
    """
    AJAX — heatmap data (device × code) using each pair's latest result.

    Filters the window of last N days (parameter ``window``, default 90,
    clamped to [7, 365]) and optional ``company``. Returns up to 50 devices
    and 30 codes ordered alphabetically. Each cell carries the latest
    resultado plus ``valor_obtenido`` and ``valor_recomendado``.
    """
    qs, window = _hardening_window_qs(request)

    # Latest fecha per (device, code) within the window.
    latest = (
        qs.values('device', 'code')
        .annotate(last=Max('fecha'))
    )
    latest_map = {(row['device'], row['code']): row['last'] for row in latest}

    if not latest_map:
        return JsonResponse({'window': window, 'devices': [], 'codes': [], 'cells': {}})

    # Pull rows that match the (device, code, last_fecha) tuples.
    detail_rows = qs.filter(
        fecha__in=set(latest_map.values()),
    ).values('device', 'code', 'fecha', 'resultado', 'valor_obtenido', 'valor_recomendado')

    cells: dict[str, dict[str, dict]] = {}
    for r in detail_rows:
        key = (r['device'], r['code'])
        if latest_map.get(key) != r['fecha']:
            continue
        cells.setdefault(r['device'], {})[r['code']] = {
            'r':  (r['resultado'] or '').lower(),
            'vo': (r['valor_obtenido']  or '')[:120],
            'vr': (r['valor_recomendado'] or '')[:120],
        }

    devices = sorted(cells.keys())[:_HEATMAP_DEVICE_LIMIT]
    codes_set: set[str] = set()
    for d in devices:
        codes_set.update(cells.get(d, {}).keys())
    codes = sorted(codes_set)[:_HEATMAP_CODE_LIMIT]

    # Trim cells to the included devices/codes to keep payload small.
    trimmed = {d: {c: cells[d][c] for c in codes if c in cells.get(d, {})} for d in devices}
    return JsonResponse({
        'window':  window,
        'devices': devices,
        'codes':   codes,
        'cells':   trimmed,
    })


@login_required
@permission_required('lb_manager.view_lbhardening', raise_exception=True)
def hardening_top_failed_codes(request):
    """AJAX — top N codes (by failed count) within the window."""
    qs, window = _hardening_window_qs(request)
    rows = list(
        qs.values('code')
        .annotate(
            failed=Count('id', filter=Q(resultado__iexact='failed')),
            total=Count('id'),
        )
        .order_by('-failed')[:_TOP_LIMIT]
    )
    for r in rows:
        r['pct'] = round(r['failed'] / r['total'] * 100, 1) if r['total'] else 0
    return JsonResponse({'window': window, 'rows': rows})


@login_required
@permission_required('lb_manager.view_lbhardening', raise_exception=True)
def hardening_top_failed_devices(request):
    """AJAX — top N devices (by failed count) within the window."""
    qs, window = _hardening_window_qs(request)
    rows = list(
        qs.values('device')
        .annotate(
            failed=Count('id', filter=Q(resultado__iexact='failed')),
            total=Count('id'),
        )
        .order_by('-failed')[:_TOP_LIMIT]
    )
    for r in rows:
        r['pct'] = round(r['failed'] / r['total'] * 100, 1) if r['total'] else 0
    return JsonResponse({'window': window, 'rows': rows})


@login_required
@permission_required('lb_manager.view_lbhardening', raise_exception=True)
def hardening_recurrence(request):
    """
    AJAX — (device, code) pairs that failed in ≥ 3 distinct months within
    the window. A high ``months_failed`` value flags persistent re-work.
    """
    qs, window = _hardening_window_qs(request)
    rows = list(
        qs.filter(resultado__iexact='failed')
        .annotate(month=TruncMonth('fecha'))
        .values('device', 'code')
        .annotate(months_failed=Count('month', distinct=True))
        .filter(months_failed__gte=_RECURRENCE_MIN_MONTHS)
        .order_by('-months_failed', 'device', 'code')[:50]
    )
    return JsonResponse({'window': window, 'rows': rows})
