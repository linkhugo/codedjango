"""
CRUD views for:
  - DocEntry / DirectoryEntry (documentation & phone catalog)
  - F5SoftwareVersion / F5HardwareModel (F5 EoL catalog)
  - eol_timeline: upcoming End-of-Life events dashboard
"""
import json
from datetime import date

from dateutil.relativedelta import relativedelta
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db.models import Q
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from ..forms import DirectoryEntryForm, DocEntryForm, F5SoftwareVersionForm, F5HardwareModelForm
from ..models import (
    Company, DirectoryEntry, DocEntry,
    F5SoftwareVersion, F5HardwareModel,
    LBPhysical, LBGuest,
)

__all__ = [
    'DocEntryListView',
    'DocEntryCreateView',
    'DocEntryUpdateView',
    'DocEntryDeleteView',
    'DirectoryEntryListView',
    'DirectoryEntryCreateView',
    'DirectoryEntryUpdateView',
    'DirectoryEntryDeleteView',
    'F5SoftwareVersionListView',
    'F5SoftwareVersionCreateView',
    'F5SoftwareVersionUpdateView',
    'F5SoftwareVersionDeleteView',
    'F5HardwareModelListView',
    'F5HardwareModelCreateView',
    'F5HardwareModelUpdateView',
    'F5HardwareModelDeleteView',
    'eol_timeline',
    'eol_charts',
]


# ── DocEntry ──────────────────────────────────────────────────────────────────

class DocEntryListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """Lista de entradas de documentación."""

    model               = DocEntry
    template_name       = 'lb_manager/doc_entry_list.html'
    context_object_name = 'objects'
    permission_required = 'lb_manager.view_docentry'
    raise_exception     = True
    ordering            = ['category', 'name']

    def get_context_data(self, **kwargs: object) -> dict:
        ctx = super().get_context_data(**kwargs)
        ctx['categories'] = (
            DocEntry.objects
            .values_list('category', flat=True)
            .distinct()
            .order_by('category')
        )
        return ctx


class DocEntryCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    """Crear una nueva entrada de documentación."""

    model               = DocEntry
    form_class          = DocEntryForm
    template_name       = 'lb_manager/crud_form.html'
    success_url         = reverse_lazy('doc_entry_list')
    permission_required = 'lb_manager.add_docentry'
    raise_exception     = True

    def get_context_data(self, **kwargs: object) -> dict:
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = 'Agregar Documento'
        ctx['list_url']   = reverse_lazy('doc_entry_list')
        ctx['list_label'] = 'Documentación'
        return ctx

    def form_valid(self, form: DocEntryForm) -> object:
        messages.success(self.request, 'Documento creado correctamente.')
        return super().form_valid(form)


class DocEntryUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    """Editar una entrada de documentación existente."""

    model               = DocEntry
    form_class          = DocEntryForm
    template_name       = 'lb_manager/crud_form.html'
    success_url         = reverse_lazy('doc_entry_list')
    permission_required = 'lb_manager.change_docentry'
    raise_exception     = True

    def get_context_data(self, **kwargs: object) -> dict:
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = f'Editar: {self.object.name}'
        ctx['list_url']   = reverse_lazy('doc_entry_list')
        ctx['list_label'] = 'Documentación'
        ctx['is_edit']    = True
        return ctx

    def form_valid(self, form: DocEntryForm) -> object:
        messages.success(self.request, 'Documento actualizado.')
        return super().form_valid(form)


class DocEntryDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    """Eliminar una entrada de documentación (con confirmación)."""

    model               = DocEntry
    template_name       = 'lb_manager/crud_confirm_delete.html'
    success_url         = reverse_lazy('doc_entry_list')
    permission_required = 'lb_manager.delete_docentry'
    raise_exception     = True

    def get_context_data(self, **kwargs: object) -> dict:
        ctx = super().get_context_data(**kwargs)
        ctx['page_title']  = 'Eliminar Documento'
        ctx['list_url']    = reverse_lazy('doc_entry_list')
        ctx['list_label']  = 'Documentación'
        ctx['object_name'] = str(self.object)
        return ctx

    def form_valid(self, form: object) -> object:
        messages.success(self.request, 'Documento eliminado.')
        return super().form_valid(form)


# ── DirectoryEntry ────────────────────────────────────────────────────────────

class DirectoryEntryListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """Lista del directorio de números importantes."""

    model               = DirectoryEntry
    template_name       = 'lb_manager/directory_entry_list.html'
    context_object_name = 'objects'
    permission_required = 'lb_manager.view_directoryentry'
    raise_exception     = True
    ordering            = ['name']


class DirectoryEntryCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    """Crear una nueva entrada en el directorio."""

    model               = DirectoryEntry
    form_class          = DirectoryEntryForm
    template_name       = 'lb_manager/crud_form.html'
    success_url         = reverse_lazy('directory_entry_list')
    permission_required = 'lb_manager.add_directoryentry'
    raise_exception     = True

    def get_context_data(self, **kwargs: object) -> dict:
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = 'Agregar Número'
        ctx['list_url']   = reverse_lazy('directory_entry_list')
        ctx['list_label'] = 'Directorio'
        return ctx

    def form_valid(self, form: DirectoryEntryForm) -> object:
        messages.success(self.request, 'Entrada creada correctamente.')
        return super().form_valid(form)


class DirectoryEntryUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    """Editar una entrada del directorio existente."""

    model               = DirectoryEntry
    form_class          = DirectoryEntryForm
    template_name       = 'lb_manager/crud_form.html'
    success_url         = reverse_lazy('directory_entry_list')
    permission_required = 'lb_manager.change_directoryentry'
    raise_exception     = True

    def get_context_data(self, **kwargs: object) -> dict:
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = f'Editar: {self.object.name}'
        ctx['list_url']   = reverse_lazy('directory_entry_list')
        ctx['list_label'] = 'Directorio'
        ctx['is_edit']    = True
        return ctx

    def form_valid(self, form: DirectoryEntryForm) -> object:
        messages.success(self.request, 'Entrada actualizada.')
        return super().form_valid(form)


class DirectoryEntryDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    """Eliminar una entrada del directorio (con confirmación)."""

    model               = DirectoryEntry
    template_name       = 'lb_manager/crud_confirm_delete.html'
    success_url         = reverse_lazy('directory_entry_list')
    permission_required = 'lb_manager.delete_directoryentry'
    raise_exception     = True

    def get_context_data(self, **kwargs: object) -> dict:
        ctx = super().get_context_data(**kwargs)
        ctx['page_title']  = 'Eliminar Entrada'
        ctx['list_url']    = reverse_lazy('directory_entry_list')
        ctx['list_label']  = 'Directorio'
        ctx['object_name'] = str(self.object)
        return ctx

    def form_valid(self, form: object) -> object:
        messages.success(self.request, 'Entrada eliminada.')
        return super().form_valid(form)


# ── F5SoftwareVersion CRUD ────────────────────────────────────────────────────

class F5SoftwareVersionListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """Lista del catálogo de versiones de software F5 con fechas EoSS/EoTS."""

    model               = F5SoftwareVersion
    template_name       = 'lb_manager/f5_version_list.html'
    context_object_name = 'objects'
    permission_required = 'lb_manager.view_f5softwareversion'
    raise_exception     = True
    ordering            = ['version']


class F5SoftwareVersionCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    """Agregar una versión de software F5 al catálogo."""

    model               = F5SoftwareVersion
    form_class          = F5SoftwareVersionForm
    template_name       = 'lb_manager/crud_form.html'
    success_url         = reverse_lazy('f5_version_list')
    permission_required = 'lb_manager.add_f5softwareversion'
    raise_exception     = True

    def get_context_data(self, **kwargs: object) -> dict:
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = 'Agregar versión F5'
        ctx['list_url']   = reverse_lazy('f5_version_list')
        ctx['list_label'] = 'Versiones F5'
        return ctx

    def form_valid(self, form: F5SoftwareVersionForm) -> object:
        messages.success(self.request, 'Versión creada correctamente.')
        return super().form_valid(form)


class F5SoftwareVersionUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    """Editar una versión de software F5 (principalmente para agregar fechas EoSS/EoTS)."""

    model               = F5SoftwareVersion
    form_class          = F5SoftwareVersionForm
    template_name       = 'lb_manager/crud_form.html'
    success_url         = reverse_lazy('f5_version_list')
    permission_required = 'lb_manager.change_f5softwareversion'
    raise_exception     = True

    def get_context_data(self, **kwargs: object) -> dict:
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = f'Editar: {self.object.version}'
        ctx['list_url']   = reverse_lazy('f5_version_list')
        ctx['list_label'] = 'Versiones F5'
        ctx['is_edit']    = True
        return ctx

    def form_valid(self, form: F5SoftwareVersionForm) -> object:
        messages.success(self.request, 'Versión actualizada.')
        return super().form_valid(form)


class F5SoftwareVersionDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    """Eliminar una versión del catálogo F5 (con confirmación). Bloqueado si hay dispositivos vinculados."""

    model               = F5SoftwareVersion
    template_name       = 'lb_manager/crud_confirm_delete.html'
    success_url         = reverse_lazy('f5_version_list')
    permission_required = 'lb_manager.delete_f5softwareversion'
    raise_exception     = True

    def get_context_data(self, **kwargs: object) -> dict:
        ctx = super().get_context_data(**kwargs)
        phys_count  = self.object.lb_physicals.count()
        guest_count = self.object.lb_guests.count()
        ctx['page_title']  = 'Eliminar versión F5'
        ctx['list_url']    = reverse_lazy('f5_version_list')
        ctx['list_label']  = 'Versiones F5'
        ctx['object_name'] = str(self.object)
        ctx['phys_count']  = phys_count
        ctx['guest_count'] = guest_count
        ctx['has_links']   = phys_count > 0 or guest_count > 0
        return ctx

    def form_valid(self, form: object) -> object:
        if self.object.lb_physicals.exists() or self.object.lb_guests.exists():
            messages.error(
                self.request,
                f'No se puede eliminar "{self.object}" porque está asignada a dispositivos.',
            )
            return redirect('f5_version_list')
        messages.success(self.request, 'Versión eliminada.')
        return super().form_valid(form)


# ── F5HardwareModel CRUD ──────────────────────────────────────────────────────

class F5HardwareModelListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """Lista del catálogo de modelos de hardware F5 con fechas EoSS/EoTS."""

    model               = F5HardwareModel
    template_name       = 'lb_manager/f5_model_list.html'
    context_object_name = 'objects'
    permission_required = 'lb_manager.view_f5hardwaremodel'
    raise_exception     = True
    ordering            = ['name']


class F5HardwareModelCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    """Agregar un modelo de hardware F5 al catálogo."""

    model               = F5HardwareModel
    form_class          = F5HardwareModelForm
    template_name       = 'lb_manager/crud_form.html'
    success_url         = reverse_lazy('f5_model_list')
    permission_required = 'lb_manager.add_f5hardwaremodel'
    raise_exception     = True

    def get_context_data(self, **kwargs: object) -> dict:
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = 'Agregar modelo F5'
        ctx['list_url']   = reverse_lazy('f5_model_list')
        ctx['list_label'] = 'Modelos F5'
        return ctx

    def form_valid(self, form: F5HardwareModelForm) -> object:
        messages.success(self.request, 'Modelo creado correctamente.')
        return super().form_valid(form)


class F5HardwareModelUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    """Editar un modelo de hardware F5 (principalmente para agregar fechas EoSS/EoTS)."""

    model               = F5HardwareModel
    form_class          = F5HardwareModelForm
    template_name       = 'lb_manager/crud_form.html'
    success_url         = reverse_lazy('f5_model_list')
    permission_required = 'lb_manager.change_f5hardwaremodel'
    raise_exception     = True

    def get_context_data(self, **kwargs: object) -> dict:
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = f'Editar: {self.object.name}'
        ctx['list_url']   = reverse_lazy('f5_model_list')
        ctx['list_label'] = 'Modelos F5'
        ctx['is_edit']    = True
        return ctx

    def form_valid(self, form: F5HardwareModelForm) -> object:
        messages.success(self.request, 'Modelo actualizado.')
        return super().form_valid(form)


class F5HardwareModelDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    """Eliminar un modelo del catálogo F5 (con confirmación). Bloqueado si hay dispositivos vinculados."""

    model               = F5HardwareModel
    template_name       = 'lb_manager/crud_confirm_delete.html'
    success_url         = reverse_lazy('f5_model_list')
    permission_required = 'lb_manager.delete_f5hardwaremodel'
    raise_exception     = True

    def get_context_data(self, **kwargs: object) -> dict:
        ctx = super().get_context_data(**kwargs)
        phys_count  = self.object.lb_physicals.count()
        guest_count = self.object.lb_guests.count()
        ctx['page_title']  = 'Eliminar modelo F5'
        ctx['list_url']    = reverse_lazy('f5_model_list')
        ctx['list_label']  = 'Modelos F5'
        ctx['object_name'] = str(self.object)
        ctx['phys_count']  = phys_count
        ctx['guest_count'] = guest_count
        ctx['has_links']   = phys_count > 0 or guest_count > 0
        return ctx

    def form_valid(self, form: object) -> object:
        if self.object.lb_physicals.exists() or self.object.lb_guests.exists():
            messages.error(
                self.request,
                f'No se puede eliminar "{self.object}" porque está asignado a dispositivos.',
            )
            return redirect('f5_model_list')
        messages.success(self.request, 'Modelo eliminado.')
        return super().form_valid(form)


# ── EoL Timeline ──────────────────────────────────────────────────────────────

@login_required
@permission_required('lb_manager.view_lbphysical', raise_exception=True)
def eol_timeline(request):
    """
    Dashboard de proximidad a End-of-Life de versiones y modelos F5.

    Muestra todos los eventos EoSS/EoTS (software y hardware) dentro del
    horizonte seleccionado (12 o 24 meses), ordenados por fecha más próxima.
    Cada fila es un par (device, evento), para que sean accionables uno a uno.

    Args:
        request: HTTP request con parámetros opcionales:
                 months (int, default 24), company (str), environment (str).

    Returns:
        Rendered EoL timeline dashboard.
    """
    today = date.today()
    months = int(request.GET.get('months', '24'))
    cutoff = today + relativedelta(months=months)
    company_filter = request.GET.get('company', '')
    env_filter     = request.GET.get('environment', '')

    rows: list[dict] = []

    def _urgency(event_date: date) -> str:
        """Return Bootstrap color class based on days remaining."""
        days = (event_date - today).days
        if days < 0:
            return 'danger'
        if days <= 90:
            return 'danger'
        if days <= 180:
            return 'warning'
        return 'success'

    def _collect(qs, tipo: str) -> None:
        for obj in qs:
            co_code = obj.company.client_code if obj.company else '-'
            co_name = obj.company.name        if obj.company else '-'
            env     = getattr(obj, 'environment', '') or '-'

            if obj.f5_version:
                v = obj.f5_version
                # Software: EoSD (End of Software Development)
                if v.eosd_date and v.eosd_date <= cutoff:
                    rows.append({
                        'device':       obj.device,
                        'company_code': co_code,
                        'company_name': co_name,
                        'tipo':         tipo,
                        'environment':  env,
                        'category':     'Software',
                        'ref':          v.version,
                        'event':        'EoSD',
                        'event_date':   v.eosd_date,
                        'days':         (v.eosd_date - today).days,
                        'urgency':      _urgency(v.eosd_date),
                        'tbd':          False,
                    })
                # Software: EoTS (End of Technical Support)
                if v.eots_date and v.eots_date <= cutoff:
                    rows.append({
                        'device':       obj.device,
                        'company_code': co_code,
                        'company_name': co_name,
                        'tipo':         tipo,
                        'environment':  env,
                        'category':     'Software',
                        'ref':          v.version,
                        'event':        'EoTS',
                        'event_date':   v.eots_date,
                        'days':         (v.eots_date - today).days,
                        'urgency':      _urgency(v.eots_date),
                        'tbd':          False,
                    })

            if obj.f5_model:
                m = obj.f5_model
                # Hardware: EoSS (End of Software Support)
                if m.eoss_date and m.eoss_date <= cutoff:
                    rows.append({
                        'device':       obj.device,
                        'company_code': co_code,
                        'company_name': co_name,
                        'tipo':         tipo,
                        'environment':  env,
                        'category':     'Hardware',
                        'ref':          m.name,
                        'event':        'EoSS',
                        'event_date':   m.eoss_date,
                        'days':         (m.eoss_date - today).days,
                        'urgency':      _urgency(m.eoss_date),
                        'tbd':          False,
                    })
                # Hardware: EoTS (End of Technical Support)
                if m.eots_date and m.eots_date <= cutoff:
                    rows.append({
                        'device':       obj.device,
                        'company_code': co_code,
                        'company_name': co_name,
                        'tipo':         tipo,
                        'environment':  env,
                        'category':     'Hardware',
                        'ref':          m.name,
                        'event':        'EoTS',
                        'event_date':   m.eots_date,
                        'days':         (m.eots_date - today).days,
                        'urgency':      _urgency(m.eots_date),
                        'tbd':          False,
                    })

    def _collect_tbd(qs, tipo: str) -> None:
        """Collect hardware devices with eol_tbd=True and no dates set."""
        for obj in qs:
            if not obj.f5_model or not obj.f5_model.eol_tbd:
                continue
            m = obj.f5_model
            if m.eoss_date or m.eots_date:
                continue  # ya tienen fechas, aparecen en el timeline normal
            co_code = obj.company.client_code if obj.company else '-'
            co_name = obj.company.name        if obj.company else '-'
            env     = getattr(obj, 'environment', '') or '-'
            tbd_rows.append({
                'device':       obj.device,
                'company_code': co_code,
                'company_name': co_name,
                'tipo':         tipo,
                'environment':  env,
                'ref':          m.name,
            })

    tbd_rows: list[dict] = []

    phys_qs = (
        LBPhysical.objects
        .select_related('company', 'f5_version', 'f5_model')
        .filter(
            Q(f5_version__eosd_date__lte=cutoff) | Q(f5_version__eots_date__lte=cutoff) |
            Q(f5_model__eoss_date__lte=cutoff)   | Q(f5_model__eots_date__lte=cutoff)
        )
    )
    guest_qs = (
        LBGuest.objects
        .select_related('company', 'f5_version', 'f5_model')
        .filter(
            Q(f5_version__eosd_date__lte=cutoff) | Q(f5_version__eots_date__lte=cutoff) |
            Q(f5_model__eoss_date__lte=cutoff)   | Q(f5_model__eots_date__lte=cutoff)
        )
    )
    phys_tbd_qs  = LBPhysical.objects.select_related('company', 'f5_model').filter(f5_model__eol_tbd=True)
    guest_tbd_qs = LBGuest.objects.select_related('company', 'f5_model').filter(f5_model__eol_tbd=True)

    if company_filter:
        phys_qs      = phys_qs.filter(company__client_code=company_filter)
        guest_qs     = guest_qs.filter(company__client_code=company_filter)
        phys_tbd_qs  = phys_tbd_qs.filter(company__client_code=company_filter)
        guest_tbd_qs = guest_tbd_qs.filter(company__client_code=company_filter)
    if env_filter:
        phys_qs      = phys_qs.filter(environment=env_filter)
        guest_qs     = guest_qs.filter(environment=env_filter)
        phys_tbd_qs  = phys_tbd_qs.filter(environment=env_filter)
        guest_tbd_qs = guest_tbd_qs.filter(environment=env_filter)

    _collect(phys_qs,  'Physical')
    _collect(guest_qs, 'Guest')
    _collect_tbd(phys_tbd_qs,  'Physical')
    _collect_tbd(guest_tbd_qs, 'Guest')

    rows.sort(key=lambda r: r['event_date'])

    sw_chart, hw_chart = _build_chart_data(company_filter, env_filter)

    return render(request, 'lb_manager/eol_timeline.html', {
        'rows':      rows,
        'total':     len(rows),
        'tbd_rows':  tbd_rows,
        'companies': Company.objects.order_by('client_code').values('client_code', 'name'),
        'months':    months,
        'today':     today,
        'cutoff':    cutoff,
    })


# ── Shared chart data helper ──────────────────────────────────────────────────

def _build_chart_data(company_filter: str, env_filter: str) -> tuple[dict, dict]:
    """
    Build software and hardware EoL chart data filtered by company/environment.

    Returns:
        Tuple of (sw_chart, hw_chart) dicts keyed by version/model string.
    """
    def _iso(d: date | None) -> str | None:
        return d.isoformat() if d else None

    chart_phys  = LBPhysical.objects.select_related('f5_version', 'f5_model')
    chart_guest = LBGuest.objects.select_related('f5_version', 'f5_model')
    if company_filter:
        chart_phys  = chart_phys.filter(company__client_code=company_filter)
        chart_guest = chart_guest.filter(company__client_code=company_filter)
    if env_filter:
        chart_phys  = chart_phys.filter(environment=env_filter)
        chart_guest = chart_guest.filter(environment=env_filter)

    sw: dict[str, dict] = {}
    hw: dict[str, dict] = {}
    for obj in [*chart_phys, *chart_guest]:
        if obj.f5_version:
            v = obj.f5_version
            if v.version not in sw:
                sw[v.version] = {'eosd': _iso(v.eosd_date), 'eots': _iso(v.eots_date)}
        if obj.f5_model:
            m = obj.f5_model
            if m.name not in hw:
                hw[m.name] = {'eoss': _iso(m.eoss_date), 'eots': _iso(m.eots_date), 'tbd': m.eol_tbd}
    return sw, hw


# ── EoL Charts (dedicated full-page view) ─────────────────────────────────────

@login_required
@permission_required('lb_manager.view_lbphysical', raise_exception=True)
def eol_charts(request):
    """
    Dedicated full-page view for F5 EoL timeline charts.

    Shows two large horizontal bar charts (software versions and hardware models)
    positioned on a date axis with a "Today" marker. Each chart has a PNG
    download button. Filterable by company and environment.

    Args:
        request: HTTP request with optional GET params: company, environment.

    Returns:
        Rendered EoL charts page.
    """
    company_filter = request.GET.get('company', '')
    env_filter     = request.GET.get('environment', '')
    sw, hw         = _build_chart_data(company_filter, env_filter)
    return render(request, 'lb_manager/eol_charts.html', {
        'companies':     Company.objects.order_by('client_code').values('client_code', 'name'),
        'sw_chart_json': json.dumps(sw),
        'hw_chart_json': json.dumps(hw),
        'today':         date.today(),
    })
