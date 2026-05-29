"""
Views for Credential Rotation Tracker.

Tracks when passwords were last rotated for each group of devices (F5, Infoblox, Otros).
A single row represents "all devices of type X use credential type Y".
Never stores the actual password — only rotation metadata.

CRUD for CredentialRotationPolicy and CredentialRotation,
plus a POST-only view to register a rotation event.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from ..forms import CredentialRotationPolicyForm, CredentialRotationForm
from ..models import CredentialRotationPolicy, CredentialRotation, CredentialRotationEvent

__all__ = [
    'CredentialListView',
    'CredentialCreateView',
    'CredentialUpdateView',
    'CredentialDeleteView',
    'credential_register_rotation',
    'credential_history',
    'CredentialPolicyListView',
    'CredentialPolicyCreateView',
    'CredentialPolicyUpdateView',
    'CredentialPolicyDeleteView',
]

# ── CredentialRotation CRUD ───────────────────────────────────────────────────

class CredentialListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """
    Lista de grupos de credenciales con semáforo de estado.

    Returns:
        objects:        QuerySet de CredentialRotation con select_related.
        ok_count:       Grupos en estado OK.
        warning_count:  Grupos próximos a vencer.
        overdue_count:  Grupos vencidos.
        unknown_count:  Grupos sin rotación registrada.
    """

    model               = CredentialRotation
    template_name       = 'lb_manager/credential_list.html'
    context_object_name = 'objects'
    permission_required = 'lb_manager.view_credentialrotation'
    raise_exception     = True

    def get_queryset(self):
        return (
            CredentialRotation.objects
            .select_related('policy', 'rotated_by')
            .order_by('device_type', 'credential_type')
        )

    def get_context_data(self, **kwargs: object) -> dict:
        ctx = super().get_context_data(**kwargs)
        counts = {'ok': 0, 'warning': 0, 'overdue': 0, 'unknown': 0}
        for obj in ctx['objects']:
            counts[obj.status] += 1
        ctx.update({
            'ok_count':      counts['ok'],
            'warning_count': counts['warning'],
            'overdue_count': counts['overdue'],
            'unknown_count': counts['unknown'],
        })
        return ctx


class CredentialCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    """Registrar un nuevo grupo de credencial."""

    model               = CredentialRotation
    form_class          = CredentialRotationForm
    template_name       = 'lb_manager/crud_form.html'
    success_url         = reverse_lazy('credential_list')
    permission_required = 'lb_manager.add_credentialrotation'
    raise_exception     = True

    def get_context_data(self, **kwargs: object) -> dict:
        ctx = super().get_context_data(**kwargs)
        ctx.update({
            'page_title': 'Nueva entrada de credencial',
            'list_url':   reverse_lazy('credential_list'),
            'list_label': 'Rotación de Credenciales',
            'is_edit':    False,
        })
        return ctx


class CredentialUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    """Editar la política de un grupo de credencial."""

    model               = CredentialRotation
    form_class          = CredentialRotationForm
    template_name       = 'lb_manager/crud_form.html'
    success_url         = reverse_lazy('credential_list')
    permission_required = 'lb_manager.change_credentialrotation'
    raise_exception     = True

    def get_context_data(self, **kwargs: object) -> dict:
        ctx = super().get_context_data(**kwargs)
        ctx.update({
            'page_title': f'Editar — {self.object}',
            'list_url':   reverse_lazy('credential_list'),
            'list_label': 'Rotación de Credenciales',
            'is_edit':    True,
        })
        return ctx


class CredentialDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    """Eliminar un grupo de credencial."""

    model               = CredentialRotation
    template_name       = 'lb_manager/crud_confirm_delete.html'
    success_url         = reverse_lazy('credential_list')
    permission_required = 'lb_manager.delete_credentialrotation'
    raise_exception     = True

    def get_context_data(self, **kwargs: object) -> dict:
        ctx = super().get_context_data(**kwargs)
        ctx.update({
            'list_url':   reverse_lazy('credential_list'),
            'list_label': 'Rotación de Credenciales',
        })
        return ctx


@login_required
@permission_required('lb_manager.change_credentialrotation', raise_exception=True)
@require_POST
def credential_register_rotation(request, pk: int):
    """
    Registra una rotación: actualiza last_rotated, rotated_by, ticket_ref, notes.

    Solo acepta POST. No almacena el password — únicamente la metadata del evento.

    Args:
        pk: ID del CredentialRotation a actualizar.
    """
    cred = get_object_or_404(CredentialRotation, pk=pk)
    now    = timezone.now()
    ticket = request.POST.get('ticket_ref', '').strip()
    notes  = request.POST.get('notes', '').strip()

    cred.last_rotated = now
    cred.rotated_by   = request.user
    if ticket:
        cred.ticket_ref = ticket
    if notes:
        cred.notes = notes
    cred.save()

    CredentialRotationEvent.objects.create(
        rotation   = cred,
        rotated_at = now,
        rotated_by = request.user,
        ticket_ref = ticket,
        notes      = notes,
    )

    messages.success(
        request,
        f'Rotación registrada: {cred.get_device_type_display()} — '
        f'{cred.get_credential_type_display()} [{cred.get_environment_display()}].',
    )
    return redirect('credential_list')


@login_required
@permission_required('lb_manager.view_credentialrotation', raise_exception=True)
def credential_history(request, pk: int):
    """
    Historial completo de rotaciones para un grupo de credencial.

    Args:
        pk: ID del CredentialRotation.

    Returns:
        rotation: objeto CredentialRotation.
        events:   QuerySet de CredentialRotationEvent ordenados por fecha desc.
    """
    from django.shortcuts import render as _render
    cred   = get_object_or_404(CredentialRotation, pk=pk)
    events = (
        CredentialRotationEvent.objects
        .filter(rotation=cred)
        .select_related('rotated_by')
        .order_by('-rotated_at')
    )
    return _render(request, 'lb_manager/credential_history.html', {
        'rotation': cred,
        'events':   events,
    })


# ── CredentialRotationPolicy CRUD ─────────────────────────────────────────────

class CredentialPolicyListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """Lista de políticas de rotación."""

    model               = CredentialRotationPolicy
    template_name       = 'lb_manager/credential_policy_list.html'
    context_object_name = 'objects'
    permission_required = 'lb_manager.view_credentialrotationpolicy'
    raise_exception     = True


class CredentialPolicyCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    """Crear una nueva política de rotación."""

    model               = CredentialRotationPolicy
    form_class          = CredentialRotationPolicyForm
    template_name       = 'lb_manager/crud_form.html'
    success_url         = reverse_lazy('credential_policy_list')
    permission_required = 'lb_manager.add_credentialrotationpolicy'
    raise_exception     = True

    def get_context_data(self, **kwargs: object) -> dict:
        ctx = super().get_context_data(**kwargs)
        ctx.update({
            'page_title': 'Nueva política de rotación',
            'list_url':   reverse_lazy('credential_policy_list'),
            'list_label': 'Políticas de rotación',
            'is_edit':    False,
        })
        return ctx


class CredentialPolicyUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    """Editar una política de rotación."""

    model               = CredentialRotationPolicy
    form_class          = CredentialRotationPolicyForm
    template_name       = 'lb_manager/crud_form.html'
    success_url         = reverse_lazy('credential_policy_list')
    permission_required = 'lb_manager.change_credentialrotationpolicy'
    raise_exception     = True

    def get_context_data(self, **kwargs: object) -> dict:
        ctx = super().get_context_data(**kwargs)
        ctx.update({
            'page_title': f'Editar política — {self.object.name}',
            'list_url':   reverse_lazy('credential_policy_list'),
            'list_label': 'Políticas de rotación',
            'is_edit':    True,
        })
        return ctx


class CredentialPolicyDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    """Eliminar una política de rotación."""

    model               = CredentialRotationPolicy
    template_name       = 'lb_manager/crud_confirm_delete.html'
    success_url         = reverse_lazy('credential_policy_list')
    permission_required = 'lb_manager.delete_credentialrotationpolicy'
    raise_exception     = True

    def get_context_data(self, **kwargs: object) -> dict:
        ctx = super().get_context_data(**kwargs)
        linked = CredentialRotation.objects.filter(policy=self.object).count()
        ctx.update({
            'list_url':     reverse_lazy('credential_policy_list'),
            'list_label':   'Políticas de rotación',
            'has_links':    linked > 0,
            'linked_count': linked,
        })
        return ctx

    def form_valid(self, form):
        linked = CredentialRotation.objects.filter(policy=self.object).count()
        if linked:
            messages.error(
                self.request,
                f'No se puede eliminar: {linked} grupo(s) de credenciales usan esta política. '
                'Reasígnalos primero.',
            )
            return redirect('credential_policy_list')
        return super().form_valid(form)
