"""
Views for LB Change Checklist (upgrades y migraciones).

Workflow:
  draft → pre_pending → in_progress → post_pending → completed
                                                    ↘ cancelled

CRUD de plantillas (LBChangeTemplate + items) y gestión de ChangeRequests,
incluyendo el workspace donde se responden los ítems y se firman las fases.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from ..forms import LBChangeRequestForm, LBChangeTemplateForm, LBChangeTemplateItemForm
from ..models import (
    LBChangeTemplate, LBChangeTemplateItem,
    LBChangeRequest, LBChangeItemResponse,
)

__all__ = [
    'LBChangeListView',
    'LBChangeCreateView',
    'LBChangeUpdateView',
    'LBChangeDeleteView',
    'lb_change_workspace',
    'LBChangeTemplateListView',
    'LBChangeTemplateCreateView',
    'LBChangeTemplateUpdateView',
    'LBChangeTemplateDeleteView',
    'template_item_list',
    'LBChangeTemplateItemUpdateView',
    'LBChangeTemplateItemDeleteView',
]

# ── LBChangeRequest CRUD ──────────────────────────────────────────────────────

class LBChangeListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """
    Lista de cambios planificados con estado, dispositivo y firmas.

    Returns:
        objects:        QuerySet de LBChangeRequest.
        active_count:   Cambios no completados ni cancelados.
        done_count:     Cambios completados.
    """

    model               = LBChangeRequest
    template_name       = 'lb_manager/lb_change_list.html'
    context_object_name = 'objects'
    permission_required = 'lb_manager.view_lbchangerequest'
    raise_exception     = True

    def get_queryset(self):
        return (
            LBChangeRequest.objects
            .select_related(
                'template', 'lb_physical', 'lb_guest',
                'target_version', 'created_by',
                'pre_signed_by', 'post_signed_by',
                'lb_physical__company', 'lb_guest__company',
            )
            .order_by('-created_at')
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        qs = ctx['objects']
        ctx['active_count'] = qs.exclude(status__in=['completed', 'cancelled']).count()
        ctx['done_count']   = qs.filter(status='completed').count()
        return ctx


class LBChangeCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    """
    Crear un nuevo LBChangeRequest.
    Al guardar, instancia LBChangeItemResponse vacíos para todos los ítems de la plantilla.
    """

    model               = LBChangeRequest
    form_class          = LBChangeRequestForm
    template_name       = 'lb_manager/crud_form.html'
    success_url         = reverse_lazy('lb_change_list')
    permission_required = 'lb_manager.add_lbchangerequest'
    raise_exception     = True

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update({
            'page_title': 'Nuevo cambio de LB',
            'list_url':   reverse_lazy('lb_change_list'),
            'list_label': 'Cambios de LB',
            'is_edit':    False,
        })
        return ctx

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        change   = self.object
        if change.template:
            LBChangeItemResponse.objects.bulk_create([
                LBChangeItemResponse(change=change, item=item, result='', comment='')
                for item in change.template.items.all()
            ], ignore_conflicts=True)
        return response


class LBChangeUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    """Editar datos básicos de un cambio (solo si no está en curso ni completado)."""

    model               = LBChangeRequest
    form_class          = LBChangeRequestForm
    template_name       = 'lb_manager/crud_form.html'
    success_url         = reverse_lazy('lb_change_list')
    permission_required = 'lb_manager.change_lbchangerequest'
    raise_exception     = True

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update({
            'page_title': f'Editar cambio — {self.object.ticket_ref or self.object.pk}',
            'list_url':   reverse_lazy('lb_change_list'),
            'list_label': 'Cambios de LB',
            'is_edit':    True,
        })
        return ctx


class LBChangeDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    """Eliminar un cambio (solo en estado draft o cancelled)."""

    model               = LBChangeRequest
    template_name       = 'lb_manager/crud_confirm_delete.html'
    success_url         = reverse_lazy('lb_change_list')
    permission_required = 'lb_manager.delete_lbchangerequest'
    raise_exception     = True

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update({
            'list_url':   reverse_lazy('lb_change_list'),
            'list_label': 'Cambios de LB',
        })
        return ctx

    def form_valid(self, form):
        if self.object.status not in ('cancelled', 'initial_pending', 'pre_pending'):
            messages.error(
                self.request,
                'No se puede eliminar un cambio en ejecución o completado.',
            )
            return redirect('lb_change_list')
        return super().form_valid(form)


# ── Workspace helpers ─────────────────────────────────────────────────────────

def _rows_signable(rows: list, phase: str) -> bool:
    """
    True si todos los ítems requeridos de la fase están listos para firmar.

    - initial: todos los required deben tener respuesta; si comment_required_on
      coincide con la respuesta, el comentario debe estar presente.
    - pre/post: todos los required deben responderse 'yes'.
    """
    if not rows:
        return False
    for row in rows:
        if not row['item'].required:
            continue
        resp = row['resp']
        if not resp or not resp.result:
            return False
        if phase in ('pre', 'post') and resp.result != 'yes':
            return False
        con = row['item'].comment_required_on
        if con and resp.result == con and not resp.comment:
            return False
    return True


def _validate_sign(change: 'LBChangeRequest', phase: str) -> str:
    """
    Valida que el cambio esté en el estado correcto y que los ítems estén completos.
    Retorna un mensaje de error o '' si todo está bien.
    """
    expected = {'initial': 'initial_pending', 'pre': 'pre_pending', 'in_progress': 'in_progress'}
    expected_status = {'initial': 'initial_pending', 'pre': 'pre_pending', 'post': 'in_progress'}
    if change.status != expected_status.get(phase, ''):
        return f'Estado incorrecto para firmar fase {phase}.'
    if not change.template:
        return 'El cambio no tiene plantilla asignada.'
    items     = list(change.template.items.filter(phase=phase, required=True))
    responses = {r.item_id: r for r in change.responses.filter(item__phase=phase)}
    for item in items:
        resp = responses.get(item.pk)
        if not resp or not resp.result:
            return f'Ítem obligatorio sin responder: "{item.text[:60]}"'
        if phase in ('pre', 'post') and resp.result != 'yes':
            return f'Ítem obligatorio debe responder Sí: "{item.text[:60]}"'
        if item.comment_required_on and resp.result == item.comment_required_on and not resp.comment:
            return f'Comentario requerido en: "{item.text[:60]}"'
    return ''


# ── Workspace ─────────────────────────────────────────────────────────────────

@login_required
@permission_required('lb_manager.view_lbchangerequest', raise_exception=True)
def lb_change_workspace(request, pk: int):
    """
    Workspace del cambio: muestra y gestiona el checklist pre/post.

    Acciones POST (via ?action=):
      - respond:    Actualiza un LBChangeItemResponse.
      - sign_pre:   Firma el pre-cambio → status 'in_progress'.
      - sign_post:  Firma el post-cambio → status 'completed'.
      - cancel:     Cancela el cambio.

    Validación antes de firmar:
      - sign_pre:  todos los ítems phase='pre' required=True con result='ok'.
      - sign_post: idem para phase='post'.

    Args:
        pk: ID del LBChangeRequest.
    """
    change = get_object_or_404(
        LBChangeRequest.objects.select_related(
            'template', 'lb_physical', 'lb_guest', 'target_version',
            'created_by', 'initial_signed_by', 'pre_signed_by', 'post_signed_by',
        ),
        pk=pk,
    )
    can_edit = request.user.has_perm('lb_manager.change_lbchangerequest')

    if request.method == 'POST':
        action = request.POST.get('action', '')

        if action == 'respond' and can_edit:
            item_id = request.POST.get('item_id')
            result  = request.POST.get('result', '')
            comment = request.POST.get('comment', '').strip()
            if item_id and result in ('yes', 'no', 'na'):
                LBChangeItemResponse.objects.update_or_create(
                    change=change, item_id=item_id,
                    defaults={'result': result, 'comment': comment, 'by': request.user},
                )

        elif action == 'sign_initial' and can_edit:
            err = _validate_sign(change, 'initial')
            if err:
                messages.error(request, err)
            else:
                change.initial_signed_by = request.user
                change.initial_signed_at = timezone.now()
                change.status            = 'pre_pending'
                change.save()
                messages.success(request, 'Validación Inicial firmada.')

        elif action == 'sign_pre' and can_edit:
            err = _validate_sign(change, 'pre')
            if err:
                messages.error(request, err)
            else:
                change.pre_signed_by = request.user
                change.pre_signed_at = timezone.now()
                change.status        = 'in_progress'
                change.save()
                messages.success(request, 'Pre-Check firmado. El cambio está en ejecución.')

        elif action == 'sign_post' and can_edit:
            err = _validate_sign(change, 'post')
            if err:
                messages.error(request, err)
            else:
                change.post_signed_by = request.user
                change.post_signed_at = timezone.now()
                change.status         = 'completed'
                change.save()
                messages.success(request, 'Post-Check firmado. Cambio completado.')

        elif action == 'cancel' and can_edit:
            if change.status == 'completed':
                messages.error(request, 'No se puede cancelar un cambio ya completado.')
            else:
                change.status = 'cancelled'
                change.save()
                messages.success(request, 'Cambio cancelado.')

        return redirect('lb_change_workspace', pk=pk)

    # ── GET ──────────────────────────────────────────────────────────────────
    initial_rows = []
    pre_rows     = []
    post_rows    = []

    if change.template:
        responses = {
            r.item_id: r
            for r in change.responses.select_related('by').all()
        }
        for item in change.template.items.select_related('linked_item').filter(
            phase='initial'
        ).order_by('order'):
            initial_rows.append({
                'item':        item,
                'resp':        responses.get(item.pk),
                'linked_resp': responses.get(item.linked_item_id) if item.linked_item_id else None,
            })
        for item in change.template.items.select_related('linked_item').filter(
            phase='pre'
        ).order_by('order'):
            pre_rows.append({
                'item':        item,
                'resp':        responses.get(item.pk),
                'linked_resp': responses.get(item.linked_item_id) if item.linked_item_id else None,
            })
        for item in change.template.items.select_related('linked_item').filter(
            phase='post'
        ).order_by('order'):
            post_rows.append({
                'item':        item,
                'resp':        responses.get(item.pk),
                'linked_resp': responses.get(item.linked_item_id) if item.linked_item_id else None,
            })

    initial_signable = change.status == 'initial_pending' and _rows_signable(initial_rows, 'initial')
    pre_signable     = change.status == 'pre_pending'     and _rows_signable(pre_rows, 'pre')
    post_signable    = change.status == 'in_progress'     and _rows_signable(post_rows, 'post')
    is_readonly      = change.status in ('completed', 'cancelled')

    return render(request, 'lb_manager/lb_change_workspace.html', {
        'change':           change,
        'initial_rows':     initial_rows,
        'pre_rows':         pre_rows,
        'post_rows':        post_rows,
        'initial_signable': initial_signable,
        'pre_signable':     pre_signable,
        'post_signable':    post_signable,
        'is_readonly':      is_readonly,
    })


# ── LBChangeTemplate CRUD ─────────────────────────────────────────────────────

class LBChangeTemplateListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """Lista de plantillas de checklist."""

    model               = LBChangeTemplate
    template_name       = 'lb_manager/lb_change_template_list.html'
    context_object_name = 'objects'
    permission_required = 'lb_manager.view_lbchangetemplate'
    raise_exception     = True

    def get_queryset(self):
        return LBChangeTemplate.objects.prefetch_related('items').order_by('change_type', 'name')


class LBChangeTemplateCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    """Crear una nueva plantilla de checklist."""

    model               = LBChangeTemplate
    form_class          = LBChangeTemplateForm
    template_name       = 'lb_manager/crud_form.html'
    success_url         = reverse_lazy('lb_change_template_list')
    permission_required = 'lb_manager.add_lbchangetemplate'
    raise_exception     = True

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update({
            'page_title': 'Nueva plantilla de checklist',
            'list_url':   reverse_lazy('lb_change_template_list'),
            'list_label': 'Plantillas de Cambio',
            'is_edit':    False,
        })
        return ctx


class LBChangeTemplateUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    """Editar una plantilla de checklist."""

    model               = LBChangeTemplate
    form_class          = LBChangeTemplateForm
    template_name       = 'lb_manager/crud_form.html'
    success_url         = reverse_lazy('lb_change_template_list')
    permission_required = 'lb_manager.change_lbchangetemplate'
    raise_exception     = True

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update({
            'page_title': f'Editar plantilla — {self.object.name}',
            'list_url':   reverse_lazy('lb_change_template_list'),
            'list_label': 'Plantillas de Cambio',
            'is_edit':    True,
        })
        return ctx


class LBChangeTemplateDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    """Eliminar una plantilla (bloqueado si tiene cambios activos)."""

    model               = LBChangeTemplate
    template_name       = 'lb_manager/crud_confirm_delete.html'
    success_url         = reverse_lazy('lb_change_template_list')
    permission_required = 'lb_manager.delete_lbchangetemplate'
    raise_exception     = True

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        active = LBChangeRequest.objects.filter(
            template=self.object,
        ).exclude(status__in=['completed', 'cancelled']).count()
        ctx.update({
            'list_url':     reverse_lazy('lb_change_template_list'),
            'list_label':   'Plantillas de Cambio',
            'has_links':    active > 0,
            'linked_count': active,
        })
        return ctx

    def form_valid(self, form):
        active = LBChangeRequest.objects.filter(
            template=self.object,
        ).exclude(status__in=['completed', 'cancelled']).count()
        if active:
            messages.error(
                self.request,
                f'No se puede eliminar: {active} cambio(s) activos usan esta plantilla.',
            )
            return redirect('lb_change_template_list')
        return super().form_valid(form)


# ── Template Item CRUD ────────────────────────────────────────────────────────

@login_required
@permission_required('lb_manager.view_lbchangetemplate', raise_exception=True)
def template_item_list(request, pk: int):
    """
    Lista y gestión de ítems de una plantilla de checklist.

    GET  → muestra ítems agrupados por fase con formulario de alta por fase.
    POST → crea un ítem nuevo en la plantilla.

    Args:
        pk: ID de la LBChangeTemplate.
    """
    template = get_object_or_404(LBChangeTemplate, pk=pk)
    can_edit = request.user.has_perm('lb_manager.change_lbchangetemplate')

    if request.method == 'POST':
        if not can_edit:
            messages.error(request, 'No tienes permiso para agregar ítems.')
            return redirect('lb_change_template_items', pk=pk)
        form = LBChangeTemplateItemForm(request.POST, template=template)
        if form.is_valid():
            item = form.save(commit=False)
            item.template = template
            item.save()
            messages.success(request, f'Ítem agregado a "{template.name}".')
            return redirect(f'{reverse("lb_change_template_items", kwargs={"pk": pk})}?tab={item.phase}')
        active_tab = request.POST.get('phase', 'initial')
    else:
        form       = LBChangeTemplateItemForm(template=template)
        active_tab = request.GET.get('tab', 'initial')

    all_items = list(template.items.select_related('linked_item').order_by('phase', 'order'))
    return render(request, 'lb_manager/lb_change_template_items.html', {
        'template':     template,
        'add_form':     form,
        'active_tab':   active_tab,
        'initial_items': [i for i in all_items if i.phase == 'initial'],
        'pre_items':    [i for i in all_items if i.phase == 'pre'],
        'post_items':   [i for i in all_items if i.phase == 'post'],
        'can_edit':     can_edit,
    })


class LBChangeTemplateItemUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    """Editar un ítem de plantilla."""

    model               = LBChangeTemplateItem
    form_class          = LBChangeTemplateItemForm
    template_name       = 'lb_manager/crud_form.html'
    permission_required = 'lb_manager.change_lbchangetemplate'
    raise_exception     = True
    pk_url_kwarg        = 'item_pk'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['template'] = self.object.template
        return kwargs

    def get_success_url(self):
        return (
            f'{reverse("lb_change_template_items", kwargs={"pk": self.object.template_id})}'
            f'?tab={self.object.phase}'
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update({
            'page_title': f'Editar ítem — {self.object.text[:60]}',
            'list_url':   reverse('lb_change_template_items', kwargs={'pk': self.object.template_id}),
            'list_label': f'Ítems de {self.object.template.name}',
            'is_edit':    True,
        })
        return ctx


class LBChangeTemplateItemDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    """Eliminar un ítem de plantilla (cascade elimina respuestas asociadas)."""

    model               = LBChangeTemplateItem
    template_name       = 'lb_manager/crud_confirm_delete.html'
    permission_required = 'lb_manager.change_lbchangetemplate'
    raise_exception     = True
    pk_url_kwarg        = 'item_pk'

    def get_success_url(self):
        return reverse('lb_change_template_items', kwargs={'pk': self.object.template_id})

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update({
            'list_url':   reverse('lb_change_template_items', kwargs={'pk': self.object.template_id}),
            'list_label': f'Ítems de {self.object.template.name}',
            'object_name': self.object.text[:80],
            'has_links':  False,
        })
        return ctx
