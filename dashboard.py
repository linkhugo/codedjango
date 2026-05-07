"""
Dashboard, wiki, charts, global-search, and healthcheck-chart views.
"""

import calendar
from datetime import date as dt_date

from django.contrib.admin.models import LogEntry, ADDITION, CHANGE, DELETION
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.contenttypes.models import ContentType
from django.db.models import Avg, Count, Max, Min, OuterRef, Q, Subquery, IntegerField
from django.db.models.functions import Coalesce
from django.db.models.functions import TruncMonth
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.urls import reverse
from django.utils import timezone as dj_timezone

from ddi_manager.models import DDIDevice, DDILicense

from ..models import (
    Company, LBPhysical, LBGuest, HealthCheckF5, VIP, Pool, LTMNode,
    SSLCert, BitacoraHealth, BitacoraHardening, HealthCheckCertificate,
)
from .utils import (
    WIKI_ENVIRONMENTS, _vip_ssl_cert_counts, _bita_avg_resolution, _bita_weekly_trend,
    get_site_settings,
)


@login_required
def contact_admin(request):
    """Shown when the user has no group redirect configured."""
    return render(request, 'lb_manager/contact_admin.html')


@login_required
def dashboard(request):
    """
    Home page — summary counters and active operational alerts.
    Only accessible to staff and superusers; all others are redirected.
    """
    if not (request.user.is_staff or request.user.is_superuser):
        return redirect('contact_admin')

    today_minus5 = dj_timezone.localdate()
    _cfg = get_site_settings()

    today_str = today_minus5.strftime('%Y-%m-%d')
    f5_url = reverse('health_f5_list')

    # Construir lista de alertas
    alertas = []

    fuera_servicio = LBPhysical.objects.filter(
        service__isnull=False,
        service__lt=today_minus5
    ).count()
    if fuera_servicio > 0:
        alertas.append({
            'tipo': 'warning',
            'icono': 'fa-triangle-exclamation',
            'titulo': 'Alerta de Soporte',
            'mensaje': f'Existe {fuera_servicio} equipo(s) físico(s)/virtual(es) con soporte vencido.',
            'url': reverse('lb_physical_list'),
            'url_label': 'Ver Physical LBs',
        })

    # Single aggregate query for today's F5 health alerts (3 filters → 1 round-trip)
    hc_today_agg = HealthCheckF5.objects.filter(fecha=today_minus5).aggregate(
        failsafe_warn=Count('id', filter=Q(failsafe='Warning')),
        disconnected=Count('id', filter=Q(sync='Disconnected')),
        no_backup=Count('id', filter=Q(file_backup__icontains='False')),
    )
    lb_failsafe    = hc_today_agg['failsafe_warn']
    lb_disconnected = hc_today_agg['disconnected']
    backup_lb       = hc_today_agg['no_backup']

    if lb_failsafe > 0:
        alertas.append({
            'tipo': 'error',
            'icono': 'fa-circle-xmark',
            'titulo': 'Healthcheck Load Balancer Daily',
            'mensaje': f'Existe {lb_failsafe} equipo(s) con posible desvio de trafico o forceoffline.',
            'url': f'{f5_url}?failsafe=Warning&fecha_desde={today_str}&fecha_hasta={today_str}',
            'url_label': 'Ver F5 Health Checks',
        })

    if lb_disconnected > 0:
        alertas.append({
            'tipo': 'warning',
            'icono': 'fa-plug-circle-xmark',
            'titulo': 'Healthcheck Load Balancer Daily',
            'mensaje': f'Existe {lb_disconnected} equipo(s) que se encuentran en modo Disconnect.',
            'url': f'{f5_url}?sync=Disconnect&fecha_desde={today_str}&fecha_hasta={today_str}',
            'url_label': 'Ver F5 Health Checks',
        })

    if backup_lb > 0:
        alertas.append({
            'tipo': 'error',
            'icono': 'fa-cloud-arrow-up',
            'titulo': 'Healthcheck Load Balancer Daily',
            'mensaje': f'Existe {backup_lb} equipo(s) que no se transfirio el Backup Semanal a la Maquina de Backups.',
            'url': f'{f5_url}?fecha_desde={today_str}&fecha_hasta={today_str}',
            'url_label': 'Ver F5 Health Checks',
        })

    show_popup_alertas = len(alertas) > 0

    # ── Aggregate queries: replace ~20 individual COUNT round-trips with 4 ──
    vip_agg = VIP.objects.aggregate(
        total=Count('id'),
        yes_available=Count('id', filter=Q(enabled='yes', availability_status='available')),
        no=Count('id', filter=Q(enabled='no')),
    )
    node_agg = LTMNode.objects.aggregate(
        total=Count('id'),
        available=Count('id', filter=Q(availability_status='available')),
        offline=Count('id', filter=~Q(availability_status='available')),
    )
    ssl_agg = SSLCert.objects.aggregate(
        total=Count('id'),
        expired=Count('id', filter=Q(expiration_date__lt=today_str)),
        valid=Count('id', filter=Q(expiration_date__gte=today_str)),
    )
    bita_agg = BitacoraHealth.objects.aggregate(
        open_=Count('id', filter=Q(status=BitacoraHealth.Status.OPEN)),
        in_progress=Count('id', filter=Q(status=BitacoraHealth.Status.IN_PROGRESS)),
        closed=Count('id', filter=Q(status=BitacoraHealth.Status.CLOSED)),
        high=Count(
            'id',
            filter=Q(severity=BitacoraHealth.Severity.HIGH) & ~Q(status=BitacoraHealth.Status.CLOSED),
        ),
        medium=Count(
            'id',
            filter=Q(severity=BitacoraHealth.Severity.MEDIUM) & ~Q(status=BitacoraHealth.Status.CLOSED),
        ),
        low=Count(
            'id',
            filter=Q(severity=BitacoraHealth.Severity.LOW) & ~Q(status=BitacoraHealth.Status.CLOSED),
        ),
    )

    # ── Certificados por vencer (HealthCheckCertificate) ─────────────────────
    _latest_cert_fecha = HealthCheckCertificate.objects.aggregate(
        Max('fecha')
    )['fecha__max']

    cert_expired    = []
    cert_warning    = []
    cert_n_expired  = 0
    cert_n_critical = 0
    cert_n_warning  = 0

    if _latest_cert_fecha:
        _cert_base = HealthCheckCertificate.objects.filter(
            fecha=_latest_cert_fecha,
            days_remaining__isnull=False,
        )
        cert_n_expired  = _cert_base.filter(days_remaining__lte=0).count()
        cert_n_critical = _cert_base.filter(days_remaining__gte=1, days_remaining__lte=15).count()
        cert_n_warning  = _cert_base.filter(days_remaining__gte=16, days_remaining__lte=30).count()
        cert_expired    = list(_cert_base.filter(days_remaining__lte=15).order_by('days_remaining')[:10])
        cert_warning    = list(_cert_base.filter(days_remaining__gte=16, days_remaining__lte=30).order_by('days_remaining')[:5])

    # Hardening tickets asignados — contar total y mostrar últimos 10
    _hrd_base = BitacoraHardening.objects.filter(
        assigned_user=request.user,
        status__in=[BitacoraHardening.Status.OPEN, BitacoraHardening.Status.IN_PROGRESS],
    )
    hrd_my_count   = _hrd_base.count()
    hrd_my_tickets = _hrd_base.order_by('-fecha', 'device')[:10]

    context = {
        'page_title': 'Dashboard',
        'stats': {
            'vips': vip_agg['total'],
            'vips_yes_available': vip_agg['yes_available'],
            'vips_no': vip_agg['no'],
            'pools': Pool.objects.count(),
            'nodes': node_agg['total'],
            'nodes_available': node_agg['available'],
            'nodes_offline': node_agg['offline'],
            'ssl_certs': ssl_agg['total'],
            'ssl_expired': ssl_agg['expired'],
            'ssl_valid': ssl_agg['valid'],
            'lb_physical': LBPhysical.objects.count(),
            'lb_guest': LBGuest.objects.count(),
            'lb_eol_count': fuera_servicio,
            'companies': Company.objects.count(),
            'ddi_devices': DDIDevice.objects.count(),
            'ddi_licenses_expired': DDILicense.objects.filter(
                expiry_date__lt=dj_timezone.now()
            ).count(),
            **dict(zip(
                ('vips_cert_expired', 'vips_cert_soon'),
                _vip_ssl_cert_counts(),
            )),
        },
        'recent_alerts': BitacoraHealth.objects.exclude(
            status='CLOSED'
        ).select_related('assigned_user').order_by('-created_at')[:_cfg.dashboard_recent_alerts if _cfg else 10],
        'recent_f5_health': HealthCheckF5.objects.order_by('-fecha')[:_cfg.dashboard_recent_health if _cfg else 5],
        'alertas': alertas,
        'show_popup_alertas': show_popup_alertas,
        'today': today_str,
        # ── Bitácora metrics ──────────────────────────────────────────────
        'bita_open':        bita_agg['open_'],
        'bita_in_progress': bita_agg['in_progress'],
        'bita_closed':      bita_agg['closed'],
        'bita_high':        bita_agg['high'],
        'bita_medium':      bita_agg['medium'],
        'bita_low':         bita_agg['low'],
        'bita_avg_hours': _bita_avg_resolution(),
        'bita_weekly': _bita_weekly_trend(today_minus5, days=_cfg.dashboard_history_days if _cfg else 7),
        # ── Bitácora Hardening — tickets asignados al usuario actual ──────
        'hrd_my_tickets': hrd_my_tickets,
        'hrd_my_count': hrd_my_count,
        # ── Certificados por vencer ───────────────────────────────────────
        'cert_n_expired':   cert_n_expired,
        'cert_n_critical':  cert_n_critical,
        'cert_n_warning':   cert_n_warning,
        'cert_expired':     cert_expired,
        'cert_warning':     cert_warning,
        'cert_latest_fecha': _latest_cert_fecha,
    }
    return render(request, 'dashboard.html', context)


@login_required
@permission_required('lb_manager.view_wiki', raise_exception=True)
def wiki(request):
    """
    Operational wiki — device inventory grouped by environment and company.

    Builds a tree structure: Environment → Company → [devices], where each
    device entry includes its failover state (Active/Standby), model, distro,
    and the parent physical host (resolved by matching the guest's serial
    number to the physical appliance's serial field).

    Only LBGuest devices and LBPhysical devices with purpose='LTM' appear
    here, because those are the ones that actually serve traffic.
    Environments are rendered in the order defined by WIKI_ENVIRONMENTS.
    """
    # Build failover_map: latest failover per fqdn — single query via Subquery
    latest_failover = (
        HealthCheckF5.objects
        .filter(fqdn=OuterRef('fqdn'))
        .order_by('-fecha')
        .values('failover')[:1]
    )
    failover_map = dict(
        HealthCheckF5.objects
        .values('fqdn')
        .annotate(failover=Subquery(latest_failover))
        .values_list('fqdn', 'failover')
    )

    # Build serial → physical device map for Host resolution
    serial_to_physical = {
        p.serial: p.device
        for p in LBPhysical.objects.filter(serial__isnull=False).only('device', 'serial')
    }

    devices = []

    # LBGuest: Host = physical device matched by serial, fallback to guest device
    for g in LBGuest.objects.select_related('company').all():
        host = serial_to_physical.get(g.serial, g.device) if g.serial else g.device
        devices.append({
            'device': g.device,
            'failover': failover_map.get(g.device),
            'tipo': g.model,
            'distro': g.distro,
            'host': host,
            'environment': (g.environment or '').upper(),
            'company': g.company.client_code if g.company else '-',
            'url_cyberark': g.url_cyberark,
        })

    # LBPhysical with purpose=LTM: Host = device itself
    for p in LBPhysical.objects.select_related('company').filter(purpose='LTM'):
        devices.append({
            'device': p.device,
            'failover': failover_map.get(p.device),
            'tipo': p.model,
            'distro': p.distro,
            'host': p.device,
            'environment': (p.environment or '').upper(),
            'company': p.company.client_code if p.company else '-',
            'url_cyberark': p.url_cyberark,
        })

    # Group: environment → company → [devices]
    environments = WIKI_ENVIRONMENTS
    tree = {env: {} for env in environments}
    for d in devices:
        env = d['environment']
        if env not in tree:
            tree[env] = {}
        company = d['company'] or '-'
        tree[env].setdefault(company, []).append(d)

    # Physical hosts por environment
    host_tree: dict[str, list] = {}
    for p in LBPhysical.objects.select_related('company').order_by('device'):
        env = (p.environment or '').upper()
        host_tree.setdefault(env, []).append({
            'device':      p.device or '-',
            'model':       p.model or '-',
            'version':     p.version or '-',
            'purpose':     p.purpose or '-',
            'serial':      p.serial or '-',
            'service':     p.service,
            'company':     p.company.client_code if p.company else '-',
            'url_cyberark': p.url_cyberark,
        })

    # Sort companies within each env and build a list for the template
    env_list = []
    for env in environments:
        companies_sorted = sorted(tree[env].items())
        env_list.append({
            'name': env,
            'hosts': host_tree.get(env, []),
            'companies': [
                {'name': co, 'devices': sorted(devs, key=lambda d: d['device'])}
                for co, devs in companies_sorted
            ],
        })

    lb_ct_ids = list(ContentType.objects.filter(
        app_label='lb_manager', model__in=['lbguest', 'lbphysical']
    ).values_list('id', flat=True))
    _wiki_cfg = get_site_settings()
    recent_wiki_changes = (
        LogEntry.objects
        .filter(content_type_id__in=lb_ct_ids)
        .select_related('user', 'content_type')
        .order_by('-action_time')[:_wiki_cfg.dashboard_recent_wiki_actions if _wiki_cfg else 20]
    )

    ACTION_LABEL = {ADDITION: 'Agregado', CHANGE: 'Modificado', DELETION: 'Eliminado'}
    ACTION_COLOR = {ADDITION: 'success', CHANGE: 'primary', DELETION: 'danger'}

    wiki_changes = [
        {
            'timestamp': entry.action_time,
            'user': entry.user.get_full_name() or entry.user.username if entry.user else '—',
            'model': 'Physical LB' if entry.content_type.model == 'lbphysical' else 'Guest LB',
            'device': entry.object_repr,
            'action': ACTION_LABEL.get(entry.action_flag, str(entry.action_flag)),
            'color': ACTION_COLOR.get(entry.action_flag, 'secondary'),
        }
        for entry in recent_wiki_changes
    ]

    # ── DDI GRID MASTERs ────────────────────────────────────────────────────
    ddi_tree = {env: {} for env in WIKI_ENVIRONMENTS}
    for dev in DDIDevice.objects.select_related('company', 'datacenter').filter(
        Q(tipo='Infoblox', role__iexact='GRID MASTER') |
        Q(tipo='Other DNS') |
        Q(tipo='NTP')
    ):
        env = (dev.environment or '').upper()
        if env not in ddi_tree:
            ddi_tree[env] = {}
        company = dev.company.client_code if dev.company else '-'
        ddi_tree[env].setdefault(company, []).append({
            'device':      dev.device or '-',
            'platform':    dev.platform or '-',
            'tipo':        dev.tipo or '-',
            'role':        dev.role or '-',
            'environment': env,
            'company':     company,
        })

    ddi_env_list = []
    for env in WIKI_ENVIRONMENTS:
        companies_sorted = sorted(ddi_tree[env].items())
        ddi_env_list.append({
            'name': env,
            'companies': [
                {'name': co, 'devices': sorted(devs, key=lambda d: d['device'])}
                for co, devs in companies_sorted
            ],
        })

    return render(request, 'lb_manager/wiki.html', {
        'env_list': env_list,
        'ddi_env_list': ddi_env_list,
        'wiki_changes': wiki_changes,
        'today': dj_timezone.localdate(),
    })


@login_required
@permission_required('lb_manager.view_lbguest', raise_exception=True)
def charts(request):
    """
    Statistics page — bar charts of software-version distribution.

    Counts how many physical and how many guest LBs run each version of
    the F5 software. The union of all versions is sorted alphabetically
    and passed to the template as three parallel lists (versions, physical
    counts, guest counts) consumed by Chart.js in the browser.
    """
    physical_qs = (
        LBPhysical.objects
        .exclude(version='')
        .values('version')
        .annotate(total=Count('device'))
    )
    guest_qs = (
        LBGuest.objects
        .exclude(version__isnull=True)
        .exclude(version='')
        .values('version')
        .annotate(total=Count('device'))
    )

    physical_map = {r['version']: r['total'] for r in physical_qs}
    guest_map    = {r['version']: r['total'] for r in guest_qs}

    # All unique versions, sorted alphabetically
    all_versions = sorted(set(physical_map) | set(guest_map))

    total_physical = sum(physical_map.values())
    total_guest    = sum(guest_map.values())
    total_lb       = total_physical + total_guest

    return render(request, 'lb_manager/charts.html', {
        'page_title':      'Gráficas',
        'total_lb':        total_lb,
        'total_physical':  total_physical,
        'total_guest':     total_guest,
        'total_versions':  len(all_versions),
        'versions_list':   all_versions,
        'physical_list':   [physical_map.get(v, 0) for v in all_versions],
        'guest_list':      [guest_map.get(v, 0)    for v in all_versions],
    })


@login_required
@permission_required('lb_manager.view_vip', raise_exception=True)
def global_search(request):
    """
    Cross-table IP/name search.

    Searches VIPs (by destination_address), LTM Nodes (by address),
    Self IPs (by address), and SNAT translations (by snat IP) all at once.
    Returns up to 100 combined results. Input is capped at 200 characters
    to prevent overly broad queries.
    """
    from ..models import SelfIP, SNATTranslation

    _search_cfg = get_site_settings()
    _search_limit = _search_cfg.global_search_results_per_type if _search_cfg else 100
    q = request.GET.get('q', '').strip()[:200]
    results = []
    if q:
        # Use exact match (iexact) to avoid substring false positives.
        # e.g. searching "10.0.0.1" must NOT return "10.0.0.10" or "10.0.0.100".
        # Self IPs may include CIDR suffix (/24); match the IP portion exactly via
        # iexact on the plain address or icontains anchored to "/"-prefixed boundary.
        for obj in VIP.objects.filter(destination_address__iexact=q).values('ltm_fqdn', 'destination_address', 'name')[:_search_limit]:
            results.append({'tipo': 'VIP', 'ltm_fqdn': obj['ltm_fqdn'], 'address': obj['destination_address'], 'name': obj['name']})
        for obj in LTMNode.objects.filter(address__iexact=q).values('ltm_fqdn', 'address', 'name')[:_search_limit]:
            results.append({'tipo': 'LTM Node', 'ltm_fqdn': obj['ltm_fqdn'], 'address': obj['address'], 'name': obj['name']})
        for obj in SelfIP.objects.filter(
            Q(address__iexact=q) | Q(address__istartswith=q + '/')
        ).values('ltm_fqdn', 'address', 'name')[:_search_limit]:
            results.append({'tipo': 'Self IP', 'ltm_fqdn': obj['ltm_fqdn'], 'address': obj['address'], 'name': obj['name']})
        for obj in SNATTranslation.objects.filter(snat__iexact=q).values('ltm_fqdn', 'snat', 'name')[:_search_limit]:
            results.append({'tipo': 'SNAT', 'ltm_fqdn': obj['ltm_fqdn'], 'address': obj['snat'], 'name': obj['name']})
        results = results[:_search_limit]
    return render(request, 'lb_manager/global_search.html', {
        'q': q,
        'results': results,
        'total': len(results),
    })


@login_required
@permission_required('lb_manager.view_healthcheckf5', raise_exception=True)
def healthcheck_lb_chart(request):
    """Page view — HealthCheck LB availability bar chart by month."""
    companies = (
        HealthCheckF5.objects
        .order_by('company')
        .values_list('company', flat=True)
        .distinct()
    )
    return render(request, 'lb_manager/healthcheck_lb_chart.html', {'companies': companies})


@login_required
@permission_required('lb_manager.view_healthcheckf5', raise_exception=True)
def healthcheck_lb_chart_data(request):
    """
    AJAX endpoint — returns daily availability for HealthCheck LB.

    Query params:
      month    MM    (required)
      year     YYYY  (required)
      company        (optional, '' = all companies)

    Returns per-day arrays and monthly totals.
    A check is considered "unreachable" when failover icontains 'unreachable'.
    """
    def _parse_int(val):
        try:
            return int(val)
        except (ValueError, TypeError):
            return None

    m = _parse_int(request.GET.get('month', ''))
    y = _parse_int(request.GET.get('year',  ''))
    company = request.GET.get('company', '').strip()

    if not m or not y:
        return JsonResponse({'error': 'Invalid month/year'}, status=400)

    num_days  = calendar.monthrange(y, m)[1]
    date_from = dt_date(y, m, 1)
    date_to   = dt_date(y, m, num_days)

    qs = HealthCheckF5.objects.filter(fecha__gte=date_from, fecha__lte=date_to)
    if company:
        qs = qs.filter(company=company)

    daily_qs = (
        qs.values('fecha')
        .annotate(
            total=Count('id'),
            unreachable=Count('id', filter=Q(failover__icontains='unreachable')),
        )
        .order_by('fecha')
    )
    daily_map = {row['fecha']: row for row in daily_qs}

    days = []
    totals = []
    unreachable_list = []
    good_list = []
    pct_list = []

    for d in range(1, num_days + 1):
        dt = dt_date(y, m, d)
        row = daily_map.get(dt)
        total_d = row['total']       if row else 0
        unr_d   = row['unreachable'] if row else 0
        good_d  = total_d - unr_d
        days.append(str(d))
        totals.append(total_d)
        unreachable_list.append(unr_d)
        good_list.append(good_d)
        pct_list.append(round(good_d / total_d * 100, 1) if total_d else None)

    total_month       = sum(totals)
    unreachable_month = sum(unreachable_list)
    good_month        = total_month - unreachable_month
    pct_month         = round(good_month / total_month * 100, 1) if total_month else 0

    return JsonResponse({
        'days':               days,
        'totals':             totals,
        'unreachable':        unreachable_list,
        'good':               good_list,
        'pct':                pct_list,
        'total_month':        total_month,
        'unreachable_month':  unreachable_month,
        'good_month':         good_month,
        'pct_month':          pct_month,
    })


# ── CPU Usage Chart ───────────────────────────────────────────────────────────

@login_required
@permission_required('lb_manager.view_healthcheckf5', raise_exception=True)
def cpu_chart(request):
    """Page shell for the F5 CPU usage trend chart."""
    today = dt_date.today()
    fqdns = (
        HealthCheckF5.objects
        .exclude(fqdn__isnull=True).exclude(fqdn='')
        .order_by('fqdn')
        .values_list('fqdn', flat=True)
        .distinct()
    )
    years = sorted(
        HealthCheckF5.objects
        .exclude(fecha__isnull=True)
        .values_list('fecha__year', flat=True)
        .distinct(),
        reverse=True,
    )
    return render(request, 'lb_manager/cpu_chart.html', {
        'fqdns':        list(fqdns),
        'years':        years,
        'current_year': today.year,
        'current_month': today.month,
    })


@login_required
@permission_required('lb_manager.view_healthcheckf5', raise_exception=True)
def cpu_chart_data(request):
    """
    AJAX endpoint — CPU usage trend for a single F5 device.

    Query params:
      fqdn   (required)
      mode   'month' | 'year'   (default: month)
      year   YYYY
      month  MM                 (only used in month mode)

    Month mode: returns one data point per day (raw cpu_usage reading).
    Year mode:  returns one data point per month (average cpu_usage + max).
    Both modes also return vips count to show capacity context.
    """
    def _parse_int(val, default=None):
        try:
            return int(val)
        except (ValueError, TypeError):
            return default

    fqdn  = request.GET.get('fqdn', '').strip()
    mode  = request.GET.get('mode', 'month')
    today = dt_date.today()
    year  = _parse_int(request.GET.get('year'),  today.year)
    month = _parse_int(request.GET.get('month'), today.month)

    if not fqdn:
        return JsonResponse({'error': 'fqdn is required'}, status=400)

    base_qs = HealthCheckF5.objects.filter(fqdn=fqdn).exclude(cpu_usage__isnull=True)

    if mode == 'year':
        rows = (
            base_qs
            .filter(fecha__year=year)
            .annotate(month=TruncMonth('fecha'))
            .values('month')
            .annotate(
                avg_cpu=Avg('cpu_usage'),
                max_cpu=Max('cpu_usage'),
                min_cpu=Min('cpu_usage'),
                avg_vips=Avg('vips'),
            )
            .order_by('month')
        )
        labels, avg_data, max_data, min_data, vips_data = [], [], [], [], []
        for row in rows:
            labels.append(calendar.month_abbr[row['month'].month] + ' ' + str(year))
            avg_data.append(round(row['avg_cpu'], 1) if row['avg_cpu'] is not None else None)
            max_data.append(row['max_cpu'])
            min_data.append(row['min_cpu'])
            vips_data.append(round(row['avg_vips'], 0) if row['avg_vips'] is not None else None)

        all_cpu = [v for v in avg_data if v is not None]
        stats = {
            'avg': round(sum(all_cpu) / len(all_cpu), 1) if all_cpu else None,
            'max': max(max_data) if max_data else None,
            'min': min(min_data) if min_data else None,
        }
        return JsonResponse({
            'mode':     'year',
            'labels':   labels,
            'avg':      avg_data,
            'max':      max_data,
            'min':      min_data,
            'vips':     vips_data,
            'stats':    stats,
            'total_points': len(labels),
        })

    # ── Month mode ─────────────────────────────────────────────────────────
    num_days  = calendar.monthrange(year, month)[1]
    date_from = dt_date(year, month, 1)
    date_to   = dt_date(year, month, num_days)

    qs = (
        base_qs
        .filter(fecha__gte=date_from, fecha__lte=date_to)
        .order_by('fecha')
        .values('fecha', 'cpu_usage', 'vips', 'nodes_up', 'nodes_down', 'tmm_memory_used')
    )
    row_map = {row['fecha']: row for row in qs}

    labels, cpu_data, vips_data, nodes_data = [], [], [], []
    for d in range(1, num_days + 1):
        dt = dt_date(year, month, d)
        row = row_map.get(dt)
        labels.append(str(d))
        cpu_data.append(row['cpu_usage'] if row else None)
        vips_data.append(row['vips'] if row else None)
        nodes_data.append(
            (row['nodes_up'] or 0) + (row['nodes_down'] or 0) if row else None
        )

    valid_cpu = [v for v in cpu_data if v is not None]
    stats = {
        'avg': round(sum(valid_cpu) / len(valid_cpu), 1) if valid_cpu else None,
        'max': max(valid_cpu) if valid_cpu else None,
        'min': min(valid_cpu) if valid_cpu else None,
    }
    return JsonResponse({
        'mode':         'month',
        'labels':       labels,
        'cpu':          cpu_data,
        'vips':         vips_data,
        'nodes':        nodes_data,
        'stats':        stats,
        'total_points': len([v for v in cpu_data if v is not None]),
    })
