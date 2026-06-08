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
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from ..forms import LBChangeRequestForm, LBChangeTemplateForm, LBChangeTemplateItemForm
from ..models import (
    LBChangeTemplate, LBChangeTemplateItem,
    LBChangeRequest, LBChangeItemResponse,
    LBPhysical, LBGuest,
)
from .mixins import CRUDContextMixin

__all__ = [
    'LBChangeListView',
    'LBChangeCreateView',
    'LBChangeUpdateView',
    'LBChangeDeleteView',
    'lb_change_workspace',
    'postmortem_history',
    'lb_change_device_version',
    'LBChangeTemplateListView',
    'LBChangeTemplateCreateView',
    'LBChangeTemplateUpdateView',
    'LBChangeTemplateDeleteView',
    'lb_change_template_clone',
    'template_item_list',
    'LBChangeTemplateItemUpdateView',
    'LBChangeTemplateItemDeleteView',
]

# Truncation cap for postmortem notes to prevent abuse via huge POST bodies.
_POSTMORTEM_NOTES_MAX = 5000

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
        qs = (
            LBChangeRequest.objects
            .select_related(
                'template', 'lb_physical', 'lb_guest',
                'target_version', 'created_by',
                'pre_signed_by', 'post_signed_by',
                'lb_physical__company', 'lb_guest__company',
            )
            .order_by('-created_at')
        )
        p = self.request.GET
        if v := p.get('status'):
            qs = qs.filter(status=v)
        if v := p.get('change_type'):
            qs = qs.filter(template__change_type=v)
        if v := p.get('template'):
            qs = qs.filter(template_id=v)
        if v := p.get('device'):
            qs = qs.filter(Q(lb_physical=v) | Q(lb_guest=v))
        if v := p.get('created_by'):
            qs = qs.filter(created_by_id=v)
        if p.get('issues') == '1':
            qs = qs.filter(postmortem_had_issues=True)
        if v := p.get('scheduled_from'):
            qs = qs.filter(scheduled_at__gte=v)
        if v := p.get('scheduled_to'):
            qs = qs.filter(scheduled_at__lte=v)
        return qs

    def get_context_data(self, **kwargs):
        from django.contrib.auth import get_user_model

        ctx = super().get_context_data(**kwargs)
        qs = ctx['objects']
        ctx['active_count'] = qs.exclude(status__in=['completed', 'cancelled']).count()
        ctx['done_count']   = qs.filter(status='completed').count()

        # Catálogos para los selects de filtro (todos los valores posibles, no solo los del qs filtrado).
        all_changes = LBChangeRequest.objects.all()
        ctx['filter_status_choices']   = LBChangeRequest.STATUS
        ctx['filter_change_types']     = LBChangeTemplate.CHANGE_TYPE
        ctx['filter_templates']        = LBChangeTemplate.objects.order_by('name').values('pk', 'name')
        ctx['filter_devices']          = sorted({
            d for d in (
                list(all_changes.exclude(lb_physical__isnull=True).values_list('lb_physical', flat=True).distinct())
                + list(all_changes.exclude(lb_guest__isnull=True).values_list('lb_guest', flat=True).distinct())
            ) if d
        })
        User = get_user_model()
        creator_ids = all_changes.values_list('created_by_id', flat=True).distinct()
        ctx['filter_creators'] = (
            User.objects.filter(pk__in=creator_ids)
            .order_by('username')
            .values('pk', 'username', 'first_name', 'last_name')
        )
        ctx['filters_applied'] = {
            k: v for k, v in self.request.GET.items() if v
        }
        return ctx


class LBChangeCreateView(CRUDContextMixin, LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    """
    Crear un nuevo LBChangeRequest.
    Al guardar, instancia LBChangeItemResponse vacíos para todos los ítems de la plantilla.
    """

    model               = LBChangeRequest
    form_class          = LBChangeRequestForm
    template_name       = 'lb_manager/lb_change_create.html'
    success_url         = reverse_lazy('lb_change_list')
    permission_required = 'lb_manager.add_lbchangerequest'
    raise_exception     = True
    crud_list_url     = 'lb_change_list'
    crud_list_label   = 'Cambios de LB'
    page_title_create = 'Nuevo cambio de LB'

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        change   = self.object
        if change.template:
            LBChangeItemResponse.objects.bulk_create([
                LBChangeItemResponse(
                    change=change,
                    item=item,
                    result='',
                    comment='',
                    item_phase_snapshot=item.phase or '',
                    item_order_snapshot=item.order or 0,
                    item_text_snapshot=(item.text or '')[:400],
                    item_required_snapshot=bool(item.required),
                    item_comment_required_on_snapshot=item.comment_required_on or '',
                )
                for item in change.template.items.all()
            ], ignore_conflicts=True)
        return response


class LBChangeUpdateView(CRUDContextMixin, LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    """Editar datos básicos de un cambio (solo si no está en curso ni completado)."""

    model               = LBChangeRequest
    form_class          = LBChangeRequestForm
    template_name       = 'lb_manager/crud_form.html'
    success_url         = reverse_lazy('lb_change_list')
    permission_required = 'lb_manager.change_lbchangerequest'
    raise_exception     = True
    crud_list_url   = 'lb_change_list'
    crud_list_label = 'Cambios de LB'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = f'Editar cambio — {self.object.ticket_ref or self.object.pk}'
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
        # Preferir snapshot del item (campo eff_*) si fue calculado, fallback al item vivo.
        required = row.get('eff_required', row['item'].required)
        if not required:
            continue
        resp = row['resp']
        if not resp or not resp.result:
            return False
        if phase in ('pre', 'post') and resp.result != 'yes':
            return False
        con = row.get('eff_comment_required_on', row['item'].comment_required_on)
        if con and resp.result == con and not resp.comment:
            return False
    return True


def _validate_sign(change: 'LBChangeRequest', phase: str) -> str:
    """
    Valida que el cambio esté en el estado correcto y que los ítems estén completos.
    Retorna un mensaje de error o '' si todo está bien.
    """
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

        elif action == 'save_postmortem':
            if not request.user.has_perm('lb_manager.change_lbchangerequest'):
                messages.error(request, 'No tienes permiso para guardar el Post-Mortem.')
            elif change.status not in ('in_progress', 'completed'):
                messages.error(request, 'El Post-Mortem solo se llena durante la ejecución o tras completar el cambio.')
            else:
                change.postmortem_had_issues = bool(request.POST.get('postmortem_had_issues'))
                change.postmortem_notes      = (request.POST.get('postmortem_notes') or '').strip()[:_POSTMORTEM_NOTES_MAX]
                change.postmortem_filled_by  = request.user
                change.postmortem_filled_at  = timezone.now()
                change.save()
                messages.success(request, 'Post-Validaciones guardadas.')

        return redirect('lb_change_workspace', pk=pk)

    # ── GET ──────────────────────────────────────────────────────────────────
    def _build_row(item, responses):
        """Construye un row con campos efectivos (snapshot si existe, item vivo si no)."""
        resp = responses.get(item.pk)
        # Si la respuesta tiene snapshot llenado, se considera la fuente de verdad.
        has_snap = bool(resp and resp.item_text_snapshot)
        return {
            'item':                     item,
            'resp':                     resp,
            'linked_resp':              responses.get(item.linked_item_id) if item.linked_item_id else None,
            'eff_text':                 resp.item_text_snapshot if has_snap else item.text,
            'eff_required':             resp.item_required_snapshot if has_snap else item.required,
            'eff_comment_required_on':  resp.item_comment_required_on_snapshot if has_snap else item.comment_required_on,
        }

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
            initial_rows.append(_build_row(item, responses))
        for item in change.template.items.select_related('linked_item').filter(
            phase='pre'
        ).order_by('order'):
            pre_rows.append(_build_row(item, responses))
        for item in change.template.items.select_related('linked_item').filter(
            phase='post'
        ).order_by('order'):
            post_rows.append(_build_row(item, responses))

    initial_signable = change.status == 'initial_pending' and _rows_signable(initial_rows, 'initial')
    pre_signable     = change.status == 'pre_pending'     and _rows_signable(pre_rows, 'pre')
    post_signable    = change.status == 'in_progress'     and _rows_signable(post_rows, 'post')
    is_readonly      = change.status in ('completed', 'cancelled')

    postmortem_editable = (
        change.status in ('in_progress', 'completed')
        and request.user.has_perm('lb_manager.change_lbchangerequest')
    )

    return render(request, 'lb_manager/lb_change_workspace.html', {
        'change':              change,
        'initial_rows':        initial_rows,
        'pre_rows':            pre_rows,
        'post_rows':           post_rows,
        'initial_signable':    initial_signable,
        'pre_signable':        pre_signable,
        'post_signable':       post_signable,
        'is_readonly':         is_readonly,
        'postmortem_editable': postmortem_editable,
        'postmortem_notes_max': _POSTMORTEM_NOTES_MAX,
    })


# ── Post-Mortem AJAX ─────────────────────────────────────────────────────────

@login_required
@permission_required('lb_manager.view_lbchangerequest', raise_exception=True)
def postmortem_history(request):
    """
    Devuelve hasta 5 cambios previos con Post-Mortem para un device.

    Si el device tiene ``ha_pair`` configurado, también se incluyen los
    cambios del partner — un cambio en uno de los dos lados del par suele
    coordinarse con el otro, y los detalles previos aplican a ambos.

    Query params:
        device — hostname del LBPhysical/LBGuest
        kind   — 'physical' o 'guest'
    """
    device = (request.GET.get('device') or '').strip()
    kind   = (request.GET.get('kind') or '').strip()
    if not device or kind not in ('physical', 'guest'):
        return JsonResponse({'rows': []})

    # Resolver el partner HA del device (si existe en el mismo modelo).
    model = LBPhysical if kind == 'physical' else LBGuest
    devices = [device]
    ha_pair = (
        model.objects
        .filter(device=device)
        .values_list('ha_pair', flat=True)
        .first()
    )
    if ha_pair:
        ha_pair = ha_pair.strip()
        if ha_pair and ha_pair != device and model.objects.filter(device=ha_pair).exists():
            devices.append(ha_pair)

    field = 'lb_physical__in' if kind == 'physical' else 'lb_guest__in'
    qs = (
        LBChangeRequest.objects
        .filter(**{field: devices})
        .filter(Q(postmortem_had_issues=True) | ~Q(postmortem_notes=''))
        .select_related('postmortem_filled_by', 'lb_physical', 'lb_guest')
        .order_by('-postmortem_filled_at', '-created_at')[:5]
    )

    rows = [
        {
            'pk':            obj.pk,
            'title':         obj.title or f'#{obj.pk}',
            'ticket_ref':    obj.ticket_ref or '',
            'status':        obj.status,
            'device':        obj.device_fqdn,
            'scheduled_at':  obj.scheduled_at.isoformat() if obj.scheduled_at else '',
            'filled_at':     obj.postmortem_filled_at.isoformat() if obj.postmortem_filled_at else '',
            'filled_by':     (obj.postmortem_filled_by.get_full_name()
                              or obj.postmortem_filled_by.username) if obj.postmortem_filled_by else '—',
            'had_issues':    obj.postmortem_had_issues,
            'notes':         obj.postmortem_notes or '',
            'workspace_url': reverse('lb_change_workspace', args=[obj.pk]),
        }
        for obj in qs
    ]
    return JsonResponse({'rows': rows, 'devices_searched': devices})


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


class LBChangeTemplateCreateView(CRUDContextMixin, LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    """Crear una nueva plantilla de checklist."""

    model               = LBChangeTemplate
    form_class          = LBChangeTemplateForm
    template_name       = 'lb_manager/crud_form.html'
    success_url         = reverse_lazy('lb_change_template_list')
    permission_required = 'lb_manager.add_lbchangetemplate'
    raise_exception     = True
    crud_list_url     = 'lb_change_template_list'
    crud_list_label   = 'Plantillas de Cambio'
    page_title_create = 'Nueva plantilla de checklist'


class LBChangeTemplateUpdateView(CRUDContextMixin, LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    """Editar una plantilla de checklist."""

    model               = LBChangeTemplate
    form_class          = LBChangeTemplateForm
    template_name       = 'lb_manager/crud_form.html'
    success_url         = reverse_lazy('lb_change_template_list')
    permission_required = 'lb_manager.change_lbchangetemplate'
    raise_exception     = True
    crud_list_url   = 'lb_change_template_list'
    crud_list_label = 'Plantillas de Cambio'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = f'Editar plantilla — {self.object.name}'
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


# ── Template Clone ────────────────────────────────────────────────────────────

@login_required
@permission_required('lb_manager.add_lbchangetemplate', raise_exception=True)
@require_POST
def lb_change_template_clone(request, pk: int):
    """
    Duplica una plantilla y todos sus ítems en una nueva entrada inactiva.

    La copia hereda ``change_type`` y ``description``. Su ``name`` recibe el
    sufijo ``(copia)`` y queda con ``active=False`` para que el operador
    revise antes de habilitarla. Los ``linked_item`` entre ítems se
    re-mapean a los nuevos ítems clonados (no quedan apuntando al original).
    """
    original = get_object_or_404(LBChangeTemplate, pk=pk)

    with transaction.atomic():
        clone = LBChangeTemplate.objects.create(
            name=f'{original.name} (copia)',
            change_type=original.change_type,
            description=original.description,
            active=False,
        )

        # Primer pase: clonar items sin linked_item; guardar mapeo old_pk → new instance.
        original_items = list(original.items.all().order_by('phase', 'order'))
        old_to_new: dict[int, LBChangeTemplateItem] = {}
        for item in original_items:
            new_item = LBChangeTemplateItem.objects.create(
                template=clone,
                phase=item.phase,
                order=item.order,
                text=item.text,
                required=item.required,
                comment_required_on=item.comment_required_on,
                linked_item=None,
            )
            old_to_new[item.pk] = new_item

        # Segundo pase: re-mapear linked_item a la copia correspondiente.
        for item in original_items:
            if item.linked_item_id and item.linked_item_id in old_to_new:
                new_item = old_to_new[item.pk]
                new_item.linked_item = old_to_new[item.linked_item_id]
                new_item.save(update_fields=['linked_item'])

    messages.success(
        request,
        f'Plantilla duplicada como "{clone.name}" (inactiva, revísala antes de habilitarla).',
    )
    return redirect('lb_change_template_edit', pk=clone.pk)


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


# ── AJAX: versión actual del cluster HA del device seleccionado ──────────────

@login_required
@permission_required('lb_manager.view_lbchangerequest', raise_exception=True)
def lb_change_device_version(request):
    """
    Devuelve la versión actual del device seleccionado y la del HA partner.

    Pensado para autocompletar ``from_version`` al crear un cambio: el cluster
    HA corre la misma versión en ambos lados, por lo que la versión del device
    elegido representa la del cluster.

    Query params:
        device — hostname del LBPhysical / LBGuest
        kind   — 'physical' o 'guest'

    Returns JSON:
        {
          "version":         "17.1.2",   // version string del device
          "f5_version_id":   42,         // pk catálogo (si aplica)
          "ha_pair":         "lb-prod-02",
          "ha_pair_version": "17.1.2",   // versión del partner (si existe)
          "match":           true,       // ambos lados coinciden
        }
    """
    device = (request.GET.get('device') or '').strip()
    kind   = (request.GET.get('kind') or '').strip()
    if not device or kind not in ('physical', 'guest'):
        return JsonResponse({})

    model = LBPhysical if kind == 'physical' else LBGuest
    obj   = (
        model.objects
        .filter(device=device)
        .values('version', 'f5_version_id', 'ha_pair')
        .first()
    )
    if not obj:
        return JsonResponse({})

    payload = {
        'version':       (obj['version'] or '').strip(),
        'f5_version_id': obj['f5_version_id'],
        'ha_pair':       (obj['ha_pair'] or '').strip(),
    }

    if payload['ha_pair']:
        partner = (
            model.objects
            .filter(device=payload['ha_pair'])
            .values('version')
            .first()
        )
        if partner:
            payload['ha_pair_version'] = (partner['version'] or '').strip()
            payload['match'] = payload['version'] == payload['ha_pair_version']
    return JsonResponse(payload)
