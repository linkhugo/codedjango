"""
Vistas para Reuniones Mensuales F5 y sus acuerdos.

Incluye:
  - CRUD de F5Meeting (lista + detalle + create/update).
  - CRUD de F5Agreement con cierre rápido y filtros avanzados.
  - Dashboard de progreso del mes (stat cards + 3 charts).
  - Export CSV mensual para anexar al ticket de la reunión.
"""

import csv
from collections import OrderedDict
from datetime import date, datetime, timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone as dj_timezone
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from ..forms import F5AgreementForm, F5MeetingForm
from ..models import F5Agreement, F5Meeting
from .mixins import CRUDContextMixin

__all__ = [
    'F5MeetingListView',
    'F5MeetingDetailView',
    'F5MeetingCreateView',
    'F5MeetingUpdateView',
    'F5MeetingDeleteView',
    'F5AgreementListView',
    'F5AgreementCreateView',
    'F5AgreementUpdateView',
    'F5AgreementDeleteView',
    'f5_agreement_close',
    'f5_meetings_dashboard',
    'f5_meetings_export_csv',
]


# ── Reuniones ────────────────────────────────────────────────────────────────

class F5MeetingListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """Listado de reuniones F5, con filtro opcional por año/mes."""

    model               = F5Meeting
    template_name       = 'lb_manager/f5_meeting_list.html'
    context_object_name = 'objects'
    permission_required = 'lb_manager.view_f5meeting'
    raise_exception     = True

    def get_queryset(self):
        qs = (
            F5Meeting.objects
            .select_related('created_by')
            .annotate(num_agreements=Count('agreements'))
            .order_by('-meeting_date')
        )
        p = self.request.GET
        if v := p.get('year'):
            qs = qs.filter(meeting_date__year=v)
        if v := p.get('month'):
            qs = qs.filter(meeting_date__month=v)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        years = (
            F5Meeting.objects.dates('meeting_date', 'year', order='DESC')
        )
        ctx['filter_years'] = [d.year for d in years]
        ctx['filters_applied'] = {k: v for k, v in self.request.GET.items() if v}
        return ctx


class F5MeetingDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    """Detalle de una reunión + tabla de sus acuerdos."""

    model               = F5Meeting
    template_name       = 'lb_manager/f5_meeting_detail.html'
    context_object_name = 'meeting'
    permission_required = 'lb_manager.view_f5meeting'
    raise_exception     = True

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['agreements'] = (
            self.object.agreements
            .select_related('owner', 'closed_by')
            .order_by('status', 'due_date', '-created_at')
        )
        ctx['today'] = dj_timezone.localdate()
        return ctx


class F5MeetingCreateView(CRUDContextMixin, LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model               = F5Meeting
    form_class          = F5MeetingForm
    template_name       = 'lb_manager/f5_meeting_form.html'
    success_url         = reverse_lazy('f5_meeting_list')
    permission_required = 'lb_manager.add_f5meeting'
    raise_exception     = True
    crud_list_url       = 'f5_meeting_list'
    crud_list_label     = 'Reuniones F5'
    page_title_create   = 'Nueva reunión F5'

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        super().form_valid(form)
        messages.success(self.request, f'Reunión "{self.object.title}" creada.')
        return redirect('f5_meeting_detail', pk=self.object.pk)


class F5MeetingUpdateView(CRUDContextMixin, LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model               = F5Meeting
    form_class          = F5MeetingForm
    template_name       = 'lb_manager/f5_meeting_form.html'
    success_url         = reverse_lazy('f5_meeting_list')
    permission_required = 'lb_manager.change_f5meeting'
    raise_exception     = True
    crud_list_url       = 'f5_meeting_list'
    crud_list_label     = 'Reuniones F5'
    page_title_edit     = 'Editar reunión F5'


class F5MeetingDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model               = F5Meeting
    template_name       = 'lb_manager/crud_confirm_delete.html'
    success_url         = reverse_lazy('f5_meeting_list')
    permission_required = 'lb_manager.delete_f5meeting'
    raise_exception     = True

    def form_valid(self, form):
        messages.success(self.request, f'Reunión "{self.object.title}" eliminada.')
        return super().form_valid(form)


# ── Acuerdos ────────────────────────────────────────────────────────────────

class F5AgreementListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """Lista global de acuerdos con filtros server-side."""

    model               = F5Agreement
    template_name       = 'lb_manager/f5_agreement_list.html'
    context_object_name = 'objects'
    permission_required = 'lb_manager.view_f5agreement'
    raise_exception     = True

    def get_queryset(self):
        qs = (
            F5Agreement.objects
            .select_related('meeting', 'owner', 'created_by', 'closed_by')
            .order_by('due_date', '-created_at')
        )
        p = self.request.GET
        if v := p.get('status'):
            qs = qs.filter(status=v)
        if v := p.get('priority'):
            qs = qs.filter(priority=v)
        if v := p.get('owner'):
            qs = qs.filter(owner_id=v)
        if v := p.get('meeting'):
            qs = qs.filter(meeting_id=v)
        if v := p.get('due_from'):
            qs = qs.filter(due_date__gte=v)
        if v := p.get('due_to'):
            qs = qs.filter(due_date__lte=v)
        if p.get('overdue') == '1':
            today = dj_timezone.localdate()
            qs = qs.filter(due_date__lt=today, status__in=F5Agreement.ACTIVE_STATES)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        qs = ctx['objects']
        today = dj_timezone.localdate()
        ctx['active_count']  = qs.filter(status__in=F5Agreement.ACTIVE_STATES).count()
        ctx['done_count']    = qs.filter(status='DONE').count()
        ctx['overdue_count'] = qs.filter(
            due_date__lt=today, status__in=F5Agreement.ACTIVE_STATES
        ).count()

        ctx['filter_status_choices']   = F5Agreement.STATUS_CHOICES
        ctx['filter_priority_choices'] = F5Agreement.PRIORITY_CHOICES
        ctx['filter_meetings'] = (
            F5Meeting.objects.order_by('-meeting_date').values('pk', 'title', 'meeting_date')
        )
        owner_ids = F5Agreement.objects.values_list('owner_id', flat=True).distinct()
        User = get_user_model()
        ctx['filter_owners'] = (
            User.objects.filter(pk__in=owner_ids)
            .order_by('username').values('pk', 'username', 'first_name', 'last_name')
        )
        ctx['filters_applied'] = {k: v for k, v in self.request.GET.items() if v}
        ctx['today'] = today
        return ctx


class F5AgreementCreateView(CRUDContextMixin, LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model               = F5Agreement
    form_class          = F5AgreementForm
    template_name       = 'lb_manager/crud_form.html'
    permission_required = 'lb_manager.add_f5agreement'
    raise_exception     = True
    crud_list_url       = 'f5_agreement_list'
    crud_list_label     = 'Acuerdos F5'
    page_title_create   = 'Nuevo acuerdo F5'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        meeting_id = self.request.GET.get('meeting')
        if meeting_id:
            kwargs['meeting'] = get_object_or_404(F5Meeting, pk=meeting_id)
        return kwargs

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        messages.success(self.request, f'Acuerdo "{self.object.title}" creado.')
        return response

    def get_success_url(self):
        return reverse_lazy('f5_meeting_detail', kwargs={'pk': self.object.meeting_id})


class F5AgreementUpdateView(CRUDContextMixin, LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model               = F5Agreement
    form_class          = F5AgreementForm
    template_name       = 'lb_manager/crud_form.html'
    permission_required = 'lb_manager.change_f5agreement'
    raise_exception     = True
    crud_list_url       = 'f5_agreement_list'
    crud_list_label     = 'Acuerdos F5'
    page_title_edit     = 'Editar acuerdo F5'

    def get_success_url(self):
        return reverse_lazy('f5_meeting_detail', kwargs={'pk': self.object.meeting_id})


class F5AgreementDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model               = F5Agreement
    template_name       = 'lb_manager/crud_confirm_delete.html'
    permission_required = 'lb_manager.delete_f5agreement'
    raise_exception     = True

    def get_success_url(self):
        return reverse_lazy('f5_meeting_detail', kwargs={'pk': self.object.meeting_id})

    def form_valid(self, form):
        messages.success(self.request, f'Acuerdo "{self.object.title}" eliminado.')
        return super().form_valid(form)


@login_required
@permission_required('lb_manager.change_f5agreement', raise_exception=True)
@require_POST
def f5_agreement_close(request, pk: int):
    """Marca un acuerdo como cerrado (DONE) con timestamp + autor.

    Idempotente: si ya está DONE, no rescribe la fecha de cierre.
    """
    agreement = get_object_or_404(F5Agreement, pk=pk)
    notes = (request.POST.get('closure_notes') or '').strip()
    if agreement.status != 'DONE':
        agreement.status = 'DONE'
        agreement.progress_pct = 100
        agreement.closed_at = dj_timezone.now()
        agreement.closed_by = request.user
    if notes:
        agreement.closure_notes = notes[:4000]
    agreement.save()
    messages.success(request, f'Acuerdo "{agreement.title}" marcado como cerrado.')
    next_url = request.POST.get('next') or request.META.get('HTTP_REFERER')
    if next_url:
        return redirect(next_url)
    return redirect('f5_meeting_detail', pk=agreement.meeting_id)


# ── Dashboard del mes ────────────────────────────────────────────────────────

def _parse_ym(value: str) -> tuple[int, int]:
    """Parse ``YYYY-MM`` → ``(year, month)``. Falla seguro al mes actual."""
    today = dj_timezone.localdate()
    if value:
        try:
            dt = datetime.strptime(value, '%Y-%m')
            return dt.year, dt.month
        except ValueError:
            pass
    return today.year, today.month


def _month_window(year: int, month: int) -> tuple[date, date]:
    """Return ``(first_day, last_day_inclusive)`` for the given year/month."""
    first = date(year, month, 1)
    if month == 12:
        next_first = date(year + 1, 1, 1)
    else:
        next_first = date(year, month + 1, 1)
    last = next_first - timedelta(days=1)
    return first, last


def _agreements_for_month(year: int, month: int):
    """QuerySet con los acuerdos cuya reunión pertenece a `year/month`."""
    return (
        F5Agreement.objects
        .select_related('meeting', 'owner', 'closed_by')
        .filter(meeting__meeting_date__year=year, meeting__meeting_date__month=month)
    )


def _build_history(months: int = 6) -> dict:
    """Devuelve {labels, created, closed} para los últimos N meses (incluye actual)."""
    today = dj_timezone.localdate()
    labels, created, closed = [], [], []
    for offset in range(months - 1, -1, -1):
        target_month = today.month - offset
        target_year = today.year
        while target_month <= 0:
            target_month += 12
            target_year -= 1
        first, last = _month_window(target_year, target_month)
        labels.append(f'{target_year}-{target_month:02d}')
        created.append(
            F5Agreement.objects.filter(created_at__date__gte=first, created_at__date__lte=last).count()
        )
        closed.append(
            F5Agreement.objects
            .filter(closed_at__date__gte=first, closed_at__date__lte=last, status='DONE')
            .count()
        )
    return {'labels': labels, 'created': created, 'closed': closed}


def _build_owner_breakdown(qs, today):
    """Devuelve los top-10 owners ordenados por total de acuerdos en el mes."""
    rows = (
        qs.values('owner__username', 'owner__first_name', 'owner__last_name')
        .annotate(
            total       = Count('id'),
            done        = Count('id', filter=Q(status='DONE')),
            in_progress = Count('id', filter=Q(status='IN_PROGRESS')),
            open_       = Count('id', filter=Q(status='OPEN')),
            overdue     = Count('id', filter=Q(
                due_date__lt=today, status__in=F5Agreement.ACTIVE_STATES
            )),
        )
        .order_by('-total')[:10]
    )
    labels, done, in_progress, open_, overdue = [], [], [], [], []
    for r in rows:
        full = (f"{r['owner__first_name']} {r['owner__last_name']}".strip()
                or r['owner__username'])
        labels.append(full)
        done.append(r['done'])
        in_progress.append(r['in_progress'])
        open_.append(r['open_'])
        overdue.append(r['overdue'])
    return {
        'labels': labels, 'done': done, 'in_progress': in_progress,
        'open': open_, 'overdue': overdue,
    }


@login_required
@permission_required('lb_manager.view_f5agreement', raise_exception=True)
def f5_meetings_dashboard(request):
    """Dashboard de cierre de mes — stat cards + donut + bar by owner + línea histórica."""
    year, month = _parse_ym(request.GET.get('ym', ''))
    today = dj_timezone.localdate()
    qs = _agreements_for_month(year, month)

    status_counts = OrderedDict()
    for code, label in F5Agreement.STATUS_CHOICES:
        status_counts[code] = qs.filter(status=code).count()

    total    = qs.count()
    overdue  = qs.filter(
        due_date__lt=today, status__in=F5Agreement.ACTIVE_STATES
    ).count()
    done     = status_counts['DONE']
    progress = status_counts['IN_PROGRESS']
    open_    = status_counts['OPEN']

    stats = [
        {'value': total,    'label': 'Total del mes',        'color': 'primary',   'icon': 'fa-list-check'},
        {'value': open_,    'label': 'Abiertos',             'color': 'info',      'icon': 'fa-folder-open'},
        {'value': progress, 'label': 'En curso',             'color': 'warning',   'icon': 'fa-spinner'},
        {'value': done,     'label': 'Cerrados',             'color': 'success',   'icon': 'fa-circle-check'},
        {'value': overdue,  'label': 'Vencidos sin cerrar',  'color': 'danger',    'icon': 'fa-triangle-exclamation'},
    ]

    donut = {
        'labels': [label for _, label in F5Agreement.STATUS_CHOICES],
        'data':   list(status_counts.values()),
    }
    owners  = _build_owner_breakdown(qs, today)
    history = _build_history(months=6)

    first, _ = _month_window(year, month)
    month_label = f'{first.strftime("%B").capitalize()} {year}'

    context = {
        'ym':            f'{year}-{month:02d}',
        'year':          year,
        'month':         month,
        'month_label':   month_label,
        'stats':         stats,
        'donut_data':    donut,
        'owner_data':    owners,
        'history_data':  history,
        'agreements':    qs.order_by('status', 'due_date', '-created_at'),
        'today':         today,
        'recent_months': [
            (date(today.year, ((today.month - i - 1) % 12) + 1, 1).strftime('%Y-%m'))
            for i in range(12)
        ],
    }
    return render(request, 'lb_manager/f5_meetings_dashboard.html', context)


@login_required
@permission_required('lb_manager.view_f5agreement', raise_exception=True)
def f5_meetings_export_csv(request):
    """Export CSV de los acuerdos del mes — pensado para anexar al ticket."""
    year, month = _parse_ym(request.GET.get('ym', ''))
    qs = _agreements_for_month(year, month).order_by('status', 'due_date', '-created_at')

    filename = f'f5_acuerdos_{year:04d}-{month:02d}.csv'
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    writer.writerow([
        'ID', 'Reunión', 'Fecha reunión', 'Acuerdo', 'Responsable',
        'Fecha compromiso', 'Prioridad', 'Estado', '% Avance',
        'Cerrado por', 'Cerrado en', 'Notas de cierre',
    ])
    for a in qs:
        owner = a.owner.get_full_name() or a.owner.username
        closed_by = ((a.closed_by.get_full_name() or a.closed_by.username)
                     if a.closed_by_id else '')
        writer.writerow([
            a.pk,
            a.meeting.title,
            a.meeting.meeting_date.isoformat(),
            a.title,
            owner,
            a.due_date.isoformat() if a.due_date else '',
            a.get_priority_display(),
            a.get_status_display(),
            a.progress_pct,
            closed_by,
            a.closed_at.isoformat(sep=' ', timespec='minutes') if a.closed_at else '',
            (a.closure_notes or '').replace('\r', ' ').replace('\n', ' '),
        ])
    return response
