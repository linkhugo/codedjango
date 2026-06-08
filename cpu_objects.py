"""
Analytics views — CPU (Plane / Analysis) vs cantidad de objetos por equipo F5.

Tres endpoints servidos en /healthcheck/cpu-vs-objects/:
  * page shell             → renderiza la página con scatter, drill-down y top 10
  * fleet scatter (AJAX)   → un punto por equipo, ventana 30 d, segmento opcional
  * per-device series (AJAX) → time-series diario de un equipo (CPU + objetos)
"""

import statistics
from datetime import timedelta

from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Avg, Count
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone as dj_timezone

from ..models import HealthCheckF5, LBPhysical, LBGuest


_CPU_OBJ_SEGMENTS = ('all', 'physical', 'guest')
_CPU_OBJ_WINDOW_DAYS = 30
_CPU_OBJ_MIN_SAMPLES = 3
_CPU_OBJ_TOP_N = 10


# ── Helpers ──────────────────────────────────────────────────────────────────

def _device_type_sets():
    """Return ``(physical_set, guest_set)`` with all device hostnames."""
    return (
        set(LBPhysical.objects.values_list('device', flat=True)),
        set(LBGuest.objects.values_list('device', flat=True)),
    )


def _classify(fqdn, physical_set, guest_set):
    if fqdn in physical_set:
        return 'physical'
    if fqdn in guest_set:
        return 'guest'
    return 'unknown'


def _aggregate_fleet(since):
    """
    Aggregate HealthCheckF5 rows by fqdn in [since, today].

    Returns a list of dicts with the averages and a stable sample count.
    Devices with fewer than ``_CPU_OBJ_MIN_SAMPLES`` rows are dropped.
    """
    return list(
        HealthCheckF5.objects
        .filter(fecha__gte=since)
        .exclude(fqdn__isnull=True).exclude(fqdn='')
        .values('fqdn')
        .annotate(
            cpu_plane_avg    = Avg('cpu_plane_use'),
            cpu_analysis_avg = Avg('cpu_analysis_use'),
            vips_avg         = Avg('vips'),
            nodes_avg        = Avg('nodes'),
            samples          = Count('id'),
        )
        .filter(samples__gte=_CPU_OBJ_MIN_SAMPLES)
    )


def _row_to_point(row, dtype):
    """Convert an aggregated row to the point dict consumed by the chart."""
    cpu_plane    = row['cpu_plane_avg']
    cpu_analysis = row['cpu_analysis_avg']
    vips_avg     = row['vips_avg']  or 0
    nodes_avg    = row['nodes_avg'] or 0
    return {
        'fqdn':         row['fqdn'],
        'objetos':      int(round(vips_avg + nodes_avg)),
        'cpu_plane':    round(cpu_plane, 1)    if cpu_plane    is not None else None,
        'cpu_analysis': round(cpu_analysis, 1) if cpu_analysis is not None else None,
        'type':         dtype,
    }


def _cpu_obj_trend(points, key):
    """
    Simple linear regression for one CPU series across all devices.

    Returns two extreme points describing the trend line, or ``None`` if
    there is not enough data.
    """
    valid = [(p['objetos'], p[key]) for p in points if p[key] is not None]
    if len(valid) < 2:
        return None
    xs = [v[0] for v in valid]
    ys = [v[1] for v in valid]
    if len(set(xs)) < 2:
        return None
    try:
        slope, intercept = statistics.linear_regression(xs, ys)
    except (statistics.StatisticsError, ValueError):
        return None
    x_min, x_max = min(xs), max(xs)
    return {
        'x_min': x_min,
        'y_min': round(slope * x_min + intercept, 1),
        'x_max': x_max,
        'y_max': round(slope * x_max + intercept, 1),
    }


def _build_top10(rows, physical_set, guest_set):
    """
    Top N equipos ordenados por CPU Plane promedio descendente.

    Empates por CPU Plane se desempatan por número de objetos (más cargado primero).
    """
    enriched = []
    for row in rows:
        cpu_plane = row['cpu_plane_avg']
        if cpu_plane is None:
            continue
        dtype = _classify(row['fqdn'], physical_set, guest_set)
        enriched.append(_row_to_point(row, dtype))
    enriched.sort(
        key=lambda p: (p['cpu_plane'] or 0, p['objetos']),
        reverse=True,
    )
    return enriched[:_CPU_OBJ_TOP_N]


# ── Page shell + endpoints ──────────────────────────────────────────────────

@login_required
@permission_required('lb_manager.view_healthcheckf5', raise_exception=True)
def cpu_vs_objects_chart(request):
    """Page shell — scatter de la flota, drill-down por equipo y tabla Top 10."""
    since = dj_timezone.localdate() - timedelta(days=_CPU_OBJ_WINDOW_DAYS)
    fqdns = list(
        HealthCheckF5.objects
        .filter(fecha__gte=since)
        .exclude(fqdn__isnull=True).exclude(fqdn='')
        .values_list('fqdn', flat=True)
        .distinct()
        .order_by('fqdn')
    )
    return render(request, 'lb_manager/cpu_vs_objects_chart.html', {
        'window_days': _CPU_OBJ_WINDOW_DAYS,
        'fqdns':       fqdns,
    })


@login_required
@permission_required('lb_manager.view_healthcheckf5', raise_exception=True)
def cpu_vs_objects_data(request):
    """
    AJAX — scatter de CPU vs cantidad de objetos para toda la flota.

    Cada punto = un equipo (promedio diario de la ventana). Incluye también
    el Top 10 por CPU Plane para alimentar la tabla en la misma carga.

    Query params:
      segment  'all' | 'physical' | 'guest'  (default: all)
    """
    segment = (request.GET.get('segment') or 'all').lower()
    if segment not in _CPU_OBJ_SEGMENTS:
        segment = 'all'

    since = dj_timezone.localdate() - timedelta(days=_CPU_OBJ_WINDOW_DAYS)
    rows  = _aggregate_fleet(since)
    physical_set, guest_set = _device_type_sets()

    points = []
    for row in rows:
        dtype = _classify(row['fqdn'], physical_set, guest_set)
        if segment not in ('all', dtype):
            continue
        if row['cpu_plane_avg'] is None and row['cpu_analysis_avg'] is None:
            continue
        points.append(_row_to_point(row, dtype))
    points.sort(key=lambda p: p['objetos'])

    return JsonResponse({
        'segment':        segment,
        'window_days':    _CPU_OBJ_WINDOW_DAYS,
        'points':         points,
        'trend_plane':    _cpu_obj_trend(points, 'cpu_plane'),
        'trend_analysis': _cpu_obj_trend(points, 'cpu_analysis'),
        'total_devices':  len(points),
        'top10':          _build_top10(rows, physical_set, guest_set),
    })


@login_required
@permission_required('lb_manager.view_healthcheckf5', raise_exception=True)
def cpu_vs_objects_device_data(request):
    """
    AJAX — time-series diario para un solo equipo.

    Devuelve una serie por día con CPU Plane, CPU Analysis y VIPs+Nodos,
    para que el front renderice un line chart de doble eje y se pueda ver
    cómo se mueve la carga junto con los objetos en ese equipo.

    Query params:
      fqdn (required)
    """
    fqdn = (request.GET.get('fqdn') or '').strip()
    if not fqdn:
        return JsonResponse({'error': 'fqdn is required'}, status=400)

    since = dj_timezone.localdate() - timedelta(days=_CPU_OBJ_WINDOW_DAYS)
    rows = (
        HealthCheckF5.objects
        .filter(fqdn=fqdn, fecha__gte=since)
        .order_by('fecha')
        .values('fecha', 'cpu_plane_use', 'cpu_analysis_use', 'vips', 'nodes')
    )

    labels, cpu_plane, cpu_analysis, objetos = [], [], [], []
    for r in rows:
        labels.append(r['fecha'].isoformat())
        cpu_plane.append(r['cpu_plane_use'])
        cpu_analysis.append(r['cpu_analysis_use'])
        if r['vips'] is None and r['nodes'] is None:
            objetos.append(None)
        else:
            objetos.append((r['vips'] or 0) + (r['nodes'] or 0))

    physical_set, guest_set = _device_type_sets()
    dtype = _classify(fqdn, physical_set, guest_set)

    return JsonResponse({
        'fqdn':         fqdn,
        'type':         dtype,
        'window_days':  _CPU_OBJ_WINDOW_DAYS,
        'labels':       labels,
        'cpu_plane':    cpu_plane,
        'cpu_analysis': cpu_analysis,
        'objetos':      objetos,
        'total_points': len(labels),
    })
