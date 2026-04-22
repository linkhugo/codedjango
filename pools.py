"""
Pool, Node, SelfIP, SNAT and Servicio views.

Lookup tools (pool_lookup, ip_balance_check) and all DataTables AJAX endpoints
for network-infrastructure objects that live "below" the VIP layer.
"""

from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db.models import OuterRef, Q, Subquery
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone as dj_timezone
from django.views.decorators.http import require_POST
from django.views.generic import ListView

from ..models import (
    VIP, Pool, LTMNode, SelfIP, SNATTranslation, Servicio, LBPhysical, LBGuest,
)
from .utils import _dt_length, _unassigned_pools_qs, _unassigned_nodes_qs


# ---------------------------------------------------------------------------
# Pool Lookup
# ---------------------------------------------------------------------------

@login_required
@permission_required('lb_manager.view_pool', raise_exception=True)
def pool_lookup(request):
    """
    Pool Lookup — find pools by member IP address and see their associated VIPs.

    Accepts a POST form with one IP per line. For each IP the view:
      1. Finds all Pool records whose ``members`` JSON array contains a member
         with that ``address`` (uses PostgreSQL JSONB @> containment check).
      2. Finds all VIPs that point to each matching pool via ``default_pool``
         and ``ltm_fqdn``.
      3. Returns both the pool details and the VIP list for display.
    """
    from collections import defaultdict

    ips_raw  = ''
    results  = []
    searched = False

    if request.method == 'POST':
        ips_raw  = request.POST.get('ips', '')
        searched = True
        terms    = [ip.strip() for ip in ips_raw.splitlines() if ip.strip()]

        if terms:
            # Find every pool that has at least one member with any of the IPs
            q = Q()
            for ip in terms:
                q |= Q(members__contains=[{'address': ip}])
            pools = list(Pool.objects.filter(q))

            # Fetch VIPs that reference any of those pools (same device)
            pool_paths = [p.full_path for p in pools]
            vip_map = defaultdict(list)
            for vip in VIP.objects.filter(default_pool__in=pool_paths):
                vip_map[(vip.default_pool, vip.ltm_fqdn)].append(vip)

            for pool in pools:
                members = []
                for m in (pool.members or []):
                    if isinstance(m, dict):
                        members.append({
                            'name':    m.get('name', '-'),
                            'address': m.get('address', '-'),
                        })

                vips = vip_map.get((pool.full_path, pool.ltm_fqdn), [])

                results.append({
                    'ltm_fqdn':       pool.ltm_fqdn or '-',
                    'pool_name':      pool.name or '-',
                    'pool_full_path': pool.full_path or '-',
                    'lb_method':      pool.lb_method or '-',
                    'members':        members,
                    'monitors':       pool.monitors or [],
                    'vips': [
                        {
                            'name':                v.name,
                            'destination_address': v.destination_address,
                            'destination_port':    v.destination_port,
                            'enabled':             v.enabled,
                        }
                        for v in vips
                    ],
                })

    return render(request, 'lb_manager/pool_lookup.html', {
        'ips_raw':  ips_raw,
        'results':  results,
        'searched': searched,
    })


# ---------------------------------------------------------------------------
# IP Balance Check
# ---------------------------------------------------------------------------

@login_required
@permission_required('lb_manager.view_vip', raise_exception=True)
def ip_balance_check(request):
    """
    IP Balance Check — verify whether one or more IPs are load-balanced.

    For each searched IP:
      - If found as a pool member: shows all pools/VIPs where it appears (Balanceado).
      - If not found in any pool: marks it as "No balanceado".

    The export (CSV/Excel) includes an "IP Buscada" and "Estado" column so
    the result can be shared directly as a report.
    """
    from collections import defaultdict

    ips_raw  = ''
    results  = []
    searched = False

    if request.method == 'POST':
        ips_raw  = request.POST.get('ips', '')
        searched = True
        terms    = [ip.strip() for ip in ips_raw.splitlines() if ip.strip()]

        if terms:
            all_pool_paths = set()
            ip_pool_map = defaultdict(list)
            terms_set = set(terms)

            # Single query: find all pools that contain any of the searched IPs
            q = Q()
            for ip in terms:
                q |= Q(members__contains=[{'address': ip}])
            for pool in Pool.objects.filter(q):
                for m in (pool.members or []):
                    if isinstance(m, dict) and m.get('address') in terms_set:
                        ip_pool_map[m['address']].append(pool)
                        all_pool_paths.add(pool.full_path)

            vip_map = defaultdict(list)
            for vip in VIP.objects.filter(default_pool__in=all_pool_paths):
                vip_map[(vip.default_pool, vip.ltm_fqdn)].append(vip)

            for ip in terms:
                pools_for_ip = ip_pool_map.get(ip, [])

                if not pools_for_ip:
                    results.append({'searched_ip': ip, 'not_found': True})
                    continue

                for pool in pools_for_ip:
                    members = []
                    for m in (pool.members or []):
                        if isinstance(m, dict):
                            full_path = m.get('full_path', '')
                            port = full_path.rsplit(':', 1)[-1] if ':' in full_path else ''
                            members.append({
                                'name':    m.get('name', '-'),
                                'address': m.get('address', '-'),
                                'port':    port,
                            })

                    vips = vip_map.get((pool.full_path, pool.ltm_fqdn), [])
                    results.append({
                        'searched_ip':    ip,
                        'not_found':      False,
                        'ltm_fqdn':       pool.ltm_fqdn or '-',
                        'pool_name':      pool.name or '-',
                        'pool_full_path': pool.full_path or '-',
                        'lb_method':      pool.lb_method or '-',
                        'members':        members,
                        'monitors':       pool.monitors or [],
                        'vips': [
                            {
                                'name':                v.name,
                                'destination_address': v.destination_address,
                                'destination_port':    v.destination_port,
                                'enabled':             v.enabled,
                            }
                            for v in vips
                        ],
                    })

    return render(request, 'lb_manager/ip_balance_check.html', {
        'ips_raw':     ips_raw,
        'results':     results,
        'searched':    searched,
        'terms_count': len([ip.strip() for ip in ips_raw.splitlines() if ip.strip()]),
    })


# ---------------------------------------------------------------------------
# Servicio (Service Catalog)
# ---------------------------------------------------------------------------

class ServicioListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """Renders the Services list page shell. Rows are loaded via servicio_data."""

    model = Servicio
    template_name = 'lb_manager/servicio_list.html'
    context_object_name = 'objects'
    paginate_by = None
    permission_required = 'lb_manager.view_servicio'
    raise_exception = True

    def get_queryset(self):
        return Servicio.objects.none()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = 'Servicios'
        ctx['page_icon'] = 'fa-network-wired'
        ctx['total'] = Servicio.objects.count()
        ctx['ltm_fqdns'] = (
            Servicio.objects.exclude(ltm_fqn__isnull=True).exclude(ltm_fqn='')
            .values_list('ltm_fqn', flat=True).distinct().order_by('ltm_fqn')
        )
        raw_servicios = (
            Servicio.objects.exclude(servicio__isnull=True).exclude(servicio='')
            .values_list('servicio', flat=True).distinct()
        )
        seen = set()
        servicios = []
        for svc in raw_servicios:
            prefix = svc.split(',')[0].strip()
            if prefix and prefix not in seen:
                seen.add(prefix)
                servicios.append(prefix)
        ctx['servicios'] = sorted(servicios)
        return ctx


@login_required
@permission_required('lb_manager.change_servicio', raise_exception=True)
@require_POST
def servicio_sync(request):
    """
    POST endpoint — syncs vips → servicio:
      - INSERT rows for VIPs not yet in servicio (matched on name + ltm_fqdn/ltm_fqn)
      - UPDATE ``enabled`` for existing rows when the value changed in vips
    Other fields (servicio, comentarios, description…) are never modified.
    Returns JSON: { inserted: N, updated: N }
    """
    if not request.user.has_perm('lb_manager.change_servicio'):
        return JsonResponse({'ok': False, 'error': 'Sin permisos'}, status=403)

    existing = {
        (s.name, s.ltm_fqn): s
        for s in Servicio.objects.only('id', 'name', 'ltm_fqn', 'enabled')
    }

    to_insert = []
    to_update = []

    for vip in VIP.objects.all().only('name', 'enabled', 'description', 'ltm_fqdn'):
        key = (vip.name, vip.ltm_fqdn)
        if key not in existing:
            to_insert.append(Servicio(
                name=vip.name,
                enabled=vip.enabled,
                servicio=(vip.description or '')[:100],
                ltm_fqn=vip.ltm_fqdn,
                ultima_modificacion=dj_timezone.now(),
                comentarios='',
                description='',
            ))
        else:
            srv = existing[key]
            if srv.enabled != vip.enabled:
                srv.enabled = vip.enabled
                srv.ultima_modificacion = dj_timezone.now()
                to_update.append(srv)

    if to_insert:
        Servicio.objects.bulk_create(to_insert)
    if to_update:
        Servicio.objects.bulk_update(to_update, ['enabled', 'ultima_modificacion'])

    return JsonResponse({'inserted': len(to_insert), 'updated': len(to_update)})


@login_required
@permission_required('lb_manager.change_servicio', raise_exception=True)
@require_POST
def servicio_edit(request, pk):
    """
    POST endpoint — updates the manually-managed fields of a Servicio row.
    Only ``servicio``, ``comentarios``, and ``description`` are editable;
    ``name``, ``enabled``, and ``ltm_fqn`` come from VIPs and are not touched.
    Returns JSON: { ok: true } or { ok: false, error: '...' }
    """
    if not request.user.has_perm('lb_manager.change_servicio'):
        return JsonResponse({'ok': False, 'error': 'Sin permisos'}, status=403)

    try:
        srv = Servicio.objects.get(pk=pk)
    except Servicio.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'Not found'}, status=404)

    srv.servicio    = request.POST.get('servicio',    srv.servicio    or '')
    srv.comentarios = request.POST.get('comentarios', srv.comentarios or '')
    srv.ultima_modificacion = dj_timezone.now()
    srv.save(update_fields=['servicio', 'comentarios', 'ultima_modificacion'])

    return JsonResponse({'ok': True})


@login_required
@permission_required('lb_manager.view_servicio', raise_exception=True)
def servicio_data(request):
    """
    AJAX endpoint — returns paginated, filtered, and sorted Servicio rows as JSON.
    Called by the DataTables library on the servicio_list page.
    Supports full-text search across name, servicio, ltm_fqn, and comentarios.
    """
    COLUMNS = ['id', 'name', 'enabled', 'servicio', 'ltm_fqn',
               'ultima_modificacion', 'comentarios']
    draw       = int(request.GET.get('draw', 1))
    start      = int(request.GET.get('start', 0))
    length     = _dt_length(request)
    search     = request.GET.get('search[value]', '').strip()
    col_idx    = int(request.GET.get('order[0][column]', 0))
    col_dir    = request.GET.get('order[0][dir]', 'asc')
    f_ltm      = request.GET.get('ltm_fqdn', '').strip()
    f_servicio = request.GET.get('servicio_filter', '').strip()

    avail_subq = VIP.objects.filter(
        name=OuterRef('name'),
        ltm_fqdn=OuterRef('ltm_fqn'),
    ).values('availability_status')[:1]

    qs = Servicio.objects.annotate(availability=Subquery(avail_subq))
    if f_ltm:
        qs = qs.filter(ltm_fqn=f_ltm)
    if f_servicio:
        qs = qs.filter(servicio__startswith=f_servicio)
    total = qs.count()
    if search:
        qs = qs.filter(
            Q(name__icontains=search) | Q(servicio__icontains=search) |
            Q(ltm_fqn__icontains=search) | Q(comentarios__icontains=search)
        )
    filtered = qs.count()
    order_col = COLUMNS[col_idx] if col_idx < len(COLUMNS) else 'id'
    if col_dir == 'desc':
        order_col = f'-{order_col}'
    qs = qs.order_by(order_col)[start:start + length]
    data = [[
        s.id,
        s.name or '-',
        str(s.enabled) if s.enabled is not None else '-',
        s.servicio or '-',
        s.ltm_fqn or '-',
        str(s.ultima_modificacion) if s.ultima_modificacion else '-',
        (s.comentarios or '-')[:80],
        s.availability or '-',
    ] for s in qs]
    return JsonResponse({'draw': draw, 'recordsTotal': total, 'recordsFiltered': filtered, 'data': data})


# ---------------------------------------------------------------------------
# Pool List + AJAX
# ---------------------------------------------------------------------------

class PoolListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """Renders the Pool list page shell. Rows are loaded via pool_data."""

    model = Pool
    template_name = 'lb_manager/pool_list.html'
    context_object_name = 'objects'
    paginate_by = None
    permission_required = 'lb_manager.view_pool'
    raise_exception = True

    def get_queryset(self):
        return Pool.objects.none()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = 'Pools'
        ctx['page_icon'] = 'fa-layer-group'
        ctx['total'] = Pool.objects.count()
        return ctx


@login_required
@permission_required('lb_manager.view_pool', raise_exception=True)
def pool_data(request):
    """AJAX endpoint — returns paginated Pool rows as JSON for DataTables."""

    COLUMNS = ['id', 'name', 'availability_status', 'enabled_status',
               'lb_method', 'member_count', 'status_reason', 'ltm_fqdn']

    draw    = int(request.GET.get('draw', 1))
    start   = int(request.GET.get('start', 0))
    length  = _dt_length(request)
    search  = request.GET.get('search[value]', '').strip()
    col_idx = int(request.GET.get('order[0][column]', 0))
    col_dir = request.GET.get('order[0][dir]', 'asc')

    qs = Pool.objects.all()
    total = qs.count()

    if search:
        qs = qs.filter(
            Q(name__icontains=search) |
            Q(availability_status__icontains=search) |
            Q(enabled_status__icontains=search) |
            Q(lb_method__icontains=search) |
            Q(status_reason__icontains=search) |
            Q(ltm_fqdn__icontains=search)
        )
    filtered = qs.count()

    order_col = COLUMNS[col_idx] if col_idx < len(COLUMNS) else 'id'
    if col_dir == 'desc':
        order_col = f'-{order_col}'
    qs = qs.order_by(order_col)[start:start + length]

    ha_lookup = dict(LBPhysical.objects.values_list('device', 'ha_pair'))
    ha_lookup.update(LBGuest.objects.values_list('device', 'ha_pair'))

    data = [[p.id, p.name or '-', p.availability_status or '-', p.enabled_status or '-',
             p.lb_method or '-', p.member_count or 0, (p.status_reason or '-')[:100],
             p.ltm_fqdn or '-', ha_lookup.get(p.ltm_fqdn) or '-'] for p in qs]

    return JsonResponse({'draw': draw, 'recordsTotal': total, 'recordsFiltered': filtered, 'data': data})


# ---------------------------------------------------------------------------
# Node List + AJAX
# ---------------------------------------------------------------------------

class NodeListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """Renders the LTM Node list page shell. Rows are loaded via node_data."""

    model = LTMNode
    template_name = 'lb_manager/node_list.html'
    context_object_name = 'objects'
    paginate_by = None
    permission_required = 'lb_manager.view_ltmnode'
    raise_exception = True

    def get_queryset(self):
        return LTMNode.objects.none()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = 'LTM Nodes'
        ctx['page_icon'] = 'fa-circle-nodes'
        ctx['total'] = LTMNode.objects.count()
        return ctx


@login_required
@permission_required('lb_manager.view_ltmnode', raise_exception=True)
def node_data(request):
    """AJAX endpoint — returns paginated LTM Node rows as JSON for DataTables.

    Columns (0-indexed):
      0  id                  1  name
      2  address             3  availability_status
      4  enabled_status      5  monitor_status
      6  monitor_rule        7  monitor_type
      8  session_status      9  status_reason
      10 connection_limit    11 dynamic_ratio
      12 rate_limit          13 ratio
      14 full_path           15 ltm_fqdn
      16 ha_pair
    """
    COLUMNS = [
        'id', 'name', 'address', 'availability_status', 'enabled_status',
        'monitor_status', 'monitor_rule', 'monitor_type', 'session_status',
        'status_reason', 'connection_limit', 'dynamic_ratio', 'rate_limit',
        'ratio', 'full_path', 'ltm_fqdn',
    ]

    draw    = int(request.GET.get('draw', 1))
    start   = int(request.GET.get('start', 0))
    length  = _dt_length(request)
    search  = request.GET.get('search[value]', '').strip()
    col_idx = int(request.GET.get('order[0][column]', 1))
    col_dir = request.GET.get('order[0][dir]', 'asc')

    qs = LTMNode.objects.all()
    total = qs.count()

    if search:
        qs = qs.filter(
            Q(name__icontains=search) |
            Q(address__icontains=search) |
            Q(availability_status__icontains=search) |
            Q(enabled_status__icontains=search) |
            Q(monitor_status__icontains=search) |
            Q(monitor_rule__icontains=search) |
            Q(status_reason__icontains=search) |
            Q(full_path__icontains=search) |
            Q(ltm_fqdn__icontains=search)
        )
    filtered = qs.count()

    order_col = COLUMNS[col_idx] if col_idx < len(COLUMNS) else 'name'
    if col_dir == 'desc':
        order_col = f'-{order_col}'
    qs = qs.order_by(order_col)[start:start + length]

    ha_lookup = dict(LBPhysical.objects.values_list('device', 'ha_pair'))
    ha_lookup.update(LBGuest.objects.values_list('device', 'ha_pair'))

    def s(v):
        return v if v is not None else '-'

    data = [[
        n.id,                        # 0
        s(n.name),                   # 1
        s(n.address),                # 2
        s(n.availability_status),    # 3
        s(n.enabled_status),         # 4
        s(n.monitor_status),         # 5
        s(n.monitor_rule),           # 6
        s(n.monitor_type),           # 7
        s(n.session_status),         # 8
        s(n.status_reason),          # 9
        n.connection_limit if n.connection_limit is not None else '-',  # 10
        n.dynamic_ratio   if n.dynamic_ratio   is not None else '-',   # 11
        n.rate_limit      if n.rate_limit      is not None else '-',   # 12
        n.ratio           if n.ratio           is not None else '-',   # 13
        s(n.full_path),              # 14
        s(n.ltm_fqdn),               # 15
        ha_lookup.get(n.ltm_fqdn) or '-',  # 16 ha_pair
    ] for n in qs]

    return JsonResponse({'draw': draw, 'recordsTotal': total, 'recordsFiltered': filtered, 'data': data})


# ---------------------------------------------------------------------------
# Unassigned Pools
# ---------------------------------------------------------------------------

class UnassignedPoolListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """Renders the Unassigned Pools list page shell. Rows loaded via unassigned_pool_data."""

    model = Pool
    template_name = 'lb_manager/unassigned_pool_list.html'
    context_object_name = 'objects'
    paginate_by = None
    permission_required = 'lb_manager.view_pool'
    raise_exception = True

    def get_queryset(self):
        return Pool.objects.none()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = 'Unassigned Pools'
        ctx['page_icon'] = 'fa-circle-exclamation'
        ctx['total'] = _unassigned_pools_qs().count()
        ctx['ltm_fqdns'] = (
            Pool.objects.values_list('ltm_fqdn', flat=True)
            .distinct().order_by('ltm_fqdn')
        )
        return ctx


@login_required
@permission_required('lb_manager.view_pool', raise_exception=True)
def unassigned_pool_data(request):
    """AJAX endpoint — returns Pool rows not referenced by any VIP."""

    COLUMNS = ['id', 'name', 'full_path', 'availability_status', 'enabled_status',
               'lb_method', 'member_count', 'status_reason', 'ltm_fqdn']

    draw    = int(request.GET.get('draw', 1))
    start   = int(request.GET.get('start', 0))
    length  = _dt_length(request)
    search  = request.GET.get('search[value]', '').strip()
    col_idx = int(request.GET.get('order[0][column]', 1))
    col_dir = request.GET.get('order[0][dir]', 'asc')
    ltm_filter = request.GET.get('ltm_fqdn', '').strip()

    qs = _unassigned_pools_qs(ltm_fqdn_filter=ltm_filter or None)
    total = qs.count()

    if search:
        qs = qs.filter(
            Q(name__icontains=search) |
            Q(full_path__icontains=search) |
            Q(availability_status__icontains=search) |
            Q(enabled_status__icontains=search) |
            Q(lb_method__icontains=search) |
            Q(status_reason__icontains=search) |
            Q(ltm_fqdn__icontains=search)
        )
    filtered = qs.count()

    order_col = COLUMNS[col_idx] if col_idx < len(COLUMNS) else 'name'
    if col_dir == 'desc':
        order_col = f'-{order_col}'
    qs = qs.order_by(order_col)[start:start + length]

    def s(v):
        return v if v is not None else '-'

    data = [[
        p.id,
        s(p.name),
        s(p.full_path),
        s(p.availability_status),
        s(p.enabled_status),
        s(p.lb_method),
        p.member_count if p.member_count is not None else '-',
        s(p.status_reason),
        s(p.ltm_fqdn),
    ] for p in qs]

    return JsonResponse({'draw': draw, 'recordsTotal': total, 'recordsFiltered': filtered, 'data': data})


# ---------------------------------------------------------------------------
# Unassigned Nodes
# ---------------------------------------------------------------------------

class UnassignedNodeListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """Renders the Unassigned Nodes list page shell. Rows loaded via unassigned_node_data."""

    model = LTMNode
    template_name = 'lb_manager/unassigned_node_list.html'
    context_object_name = 'objects'
    paginate_by = None
    permission_required = 'lb_manager.view_ltmnode'
    raise_exception = True

    def get_queryset(self):
        return LTMNode.objects.none()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = 'Unassigned Nodes'
        ctx['page_icon'] = 'fa-circle-exclamation'
        ctx['total'] = _unassigned_nodes_qs().count()
        ctx['ltm_fqdns'] = (
            LTMNode.objects.values_list('ltm_fqdn', flat=True)
            .distinct().order_by('ltm_fqdn')
        )
        return ctx


@login_required
@permission_required('lb_manager.view_ltmnode', raise_exception=True)
def unassigned_node_data(request):
    """AJAX endpoint — returns LTM Nodes not assigned to any pool."""

    COLUMNS = ['id', 'ltm_fqdn', 'name', 'address',
               'availability_status', 'enabled_status', 'monitor_status']

    draw    = int(request.GET.get('draw', 1))
    start   = int(request.GET.get('start', 0))
    length  = _dt_length(request)
    search  = request.GET.get('search[value]', '').strip()
    col_idx = int(request.GET.get('order[0][column]', 0))
    col_dir = request.GET.get('order[0][dir]', 'asc')
    ltm_filter = request.GET.get('ltm_fqdn', '').strip()

    qs = _unassigned_nodes_qs(ltm_fqdn_filter=ltm_filter or None)
    total = qs.count()

    if search:
        qs = qs.filter(
            Q(name__icontains=search) |
            Q(address__icontains=search) |
            Q(availability_status__icontains=search) |
            Q(enabled_status__icontains=search) |
            Q(monitor_status__icontains=search) |
            Q(ltm_fqdn__icontains=search)
        )
    filtered = qs.count()

    order_col = COLUMNS[col_idx] if col_idx < len(COLUMNS) else 'id'
    if col_dir == 'desc':
        order_col = f'-{order_col}'
    qs = qs.order_by(order_col)[start:start + length]

    data = [[n.id, n.ltm_fqdn or '-', n.name or '-', n.address or '-',
             n.availability_status or '-', n.enabled_status or '-',
             n.monitor_status or '-'] for n in qs]

    return JsonResponse({'draw': draw, 'recordsTotal': total, 'recordsFiltered': filtered, 'data': data})


# ---------------------------------------------------------------------------
# Self IPs
# ---------------------------------------------------------------------------

class SelfIPListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """Renders the Self IP list page shell. Rows are loaded via self_ip_data."""

    model = SelfIP
    template_name = 'lb_manager/self_ip_list.html'
    context_object_name = 'objects'
    paginate_by = None
    permission_required = 'lb_manager.view_selfip'
    raise_exception = True

    def get_queryset(self):
        return SelfIP.objects.none()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = 'Self IPs'
        ctx['page_icon'] = 'fa-ethernet'
        ctx['total'] = SelfIP.objects.count()
        return ctx


@login_required
@permission_required('lb_manager.view_selfip', raise_exception=True)
def self_ip_data(request):
    """AJAX endpoint — returns paginated Self IP rows as JSON for DataTables."""

    COLUMNS = ['id', 'name', 'address', 'netmask', 'netmask_cidr', 'vlan', 'floating', 'ltm_fqdn']
    draw    = int(request.GET.get('draw', 1))
    start   = int(request.GET.get('start', 0))
    length  = _dt_length(request)
    search  = request.GET.get('search[value]', '').strip()
    col_idx = int(request.GET.get('order[0][column]', 0))
    col_dir = request.GET.get('order[0][dir]', 'asc')

    qs = SelfIP.objects.all()
    total = qs.count()
    if search:
        qs = qs.filter(Q(name__icontains=search) | Q(address__icontains=search) |
                       Q(vlan__icontains=search) | Q(ltm_fqdn__icontains=search))
    filtered = qs.count()
    order_col = COLUMNS[col_idx] if col_idx < len(COLUMNS) else 'id'
    if col_dir == 'desc':
        order_col = f'-{order_col}'
    qs = qs.order_by(order_col)[start:start + length]
    data = [[s.id, s.name or '-', s.address or '-', s.netmask or '-',
             s.netmask_cidr or '-', s.vlan or '-', s.floating or '-',
             s.ltm_fqdn or '-'] for s in qs]
    return JsonResponse({'draw': draw, 'recordsTotal': total, 'recordsFiltered': filtered, 'data': data})


# ---------------------------------------------------------------------------
# SNAT Translations
# ---------------------------------------------------------------------------

class SNATListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """Renders the SNAT Translation list page shell. Rows are loaded via snat_data."""

    model = SNATTranslation
    template_name = 'lb_manager/snat_list.html'
    context_object_name = 'objects'
    paginate_by = None
    permission_required = 'lb_manager.view_snattranslation'
    raise_exception = True

    def get_queryset(self):
        return SNATTranslation.objects.none()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = 'SNAT Translations'
        ctx['page_icon'] = 'fa-arrows-left-right'
        ctx['total'] = SNATTranslation.objects.count()
        return ctx


@login_required
@permission_required('lb_manager.view_snattranslation', raise_exception=True)
def snat_data(request):
    """AJAX endpoint — returns paginated SNAT Translation rows as JSON for DataTables."""

    COLUMNS = ['id', 'name', 'snat', 'ltm_fqdn']
    draw    = int(request.GET.get('draw', 1))
    start   = int(request.GET.get('start', 0))
    length  = _dt_length(request)
    search  = request.GET.get('search[value]', '').strip()
    col_idx = int(request.GET.get('order[0][column]', 0))
    col_dir = request.GET.get('order[0][dir]', 'asc')

    qs = SNATTranslation.objects.all()
    total = qs.count()
    if search:
        qs = qs.filter(Q(name__icontains=search) | Q(snat__icontains=search) |
                       Q(ltm_fqdn__icontains=search))
    filtered = qs.count()
    order_col = COLUMNS[col_idx] if col_idx < len(COLUMNS) else 'id'
    if col_dir == 'desc':
        order_col = f'-{order_col}'
    qs = qs.order_by(order_col)[start:start + length]
    data = [[s.id, s.name or '-', s.snat or '-', s.ltm_fqdn or '-'] for s in qs]
    return JsonResponse({'draw': draw, 'recordsTotal': total, 'recordsFiltered': filtered, 'data': data})
