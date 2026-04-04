"""
CRUD views for DocEntry (documentation catalog) and DirectoryEntry (phone directory).
"""
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from ..forms import DirectoryEntryForm, DocEntryForm
from ..models import DirectoryEntry, DocEntry

__all__ = [
    'DocEntryListView',
    'DocEntryCreateView',
    'DocEntryUpdateView',
    'DocEntryDeleteView',
    'DirectoryEntryListView',
    'DirectoryEntryCreateView',
    'DirectoryEntryUpdateView',
    'DirectoryEntryDeleteView',
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
