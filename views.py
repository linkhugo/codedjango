"""
ViewSets for the lb_manager REST API.

Each ViewSet provides full CRUD via DRF's ModelViewSet:
  GET    /api/v1/<resource>/          → list
  POST   /api/v1/<resource>/          → create
  GET    /api/v1/<resource>/<pk>/     → retrieve
  PUT    /api/v1/<resource>/<pk>/     → update
  PATCH  /api/v1/<resource>/<pk>/     → partial_update
  DELETE /api/v1/<resource>/<pk>/     → destroy

Authentication: JWT Bearer token (see /api/v1/token/).
Authorization:  DjangoModelPermissions — mirrors existing Django group permissions.
Filtering:      django-filter (exact match), SearchFilter (partial), OrderingFilter.
Pagination:     50 records per page (configured globally in REST_FRAMEWORK settings).
"""

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.filters import OrderingFilter, SearchFilter

from ddi_manager.models import HealthCheckDDI
from lb_manager.models import (
    BitacoraHardening,
    HealthCheckDHCP,
    HealthCheckDNS,
    HealthCheckF5,
    LBHardening,
)

from .serializers import (
    BitacoraHardeningSerializer,
    HealthCheckDDISerializer,
    HealthCheckDHCPSerializer,
    HealthCheckDNSSerializer,
    HealthCheckF5Serializer,
    LBHardeningSerializer,
)


class HealthCheckF5ViewSet(viewsets.ModelViewSet):
    """CRUD for daily F5 appliance health snapshots."""

    queryset = HealthCheckF5.objects.all().order_by('-fecha', 'fqdn')
    serializer_class = HealthCheckF5Serializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['fqdn', 'fecha', 'company']
    search_fields = ['fqdn', 'company']
    ordering_fields = ['fecha', 'fqdn', 'cpu_usage', 'uptime']


class HealthCheckDNSViewSet(viewsets.ModelViewSet):
    """CRUD for daily DNS server health snapshots."""

    queryset = HealthCheckDNS.objects.all().order_by('-fecha', 'fqdn')
    serializer_class = HealthCheckDNSSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['fqdn', 'fecha', 'company']
    search_fields = ['fqdn', 'company']
    ordering_fields = ['fecha', 'fqdn', 'uptime']


class HealthCheckDHCPViewSet(viewsets.ModelViewSet):
    """CRUD for daily DHCP server health snapshots."""

    queryset = HealthCheckDHCP.objects.all().order_by('-fecha', 'fqdn')
    serializer_class = HealthCheckDHCPSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['fqdn', 'fecha', 'company']
    search_fields = ['fqdn', 'company']
    ordering_fields = ['fecha', 'fqdn', 'uptime']


class LBHardeningViewSet(viewsets.ModelViewSet):
    """CRUD for LB hardening check results."""

    queryset = LBHardening.objects.all().order_by('-fecha', 'device', 'code')
    serializer_class = LBHardeningSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['device', 'code', 'resultado', 'fecha']
    search_fields = ['device', 'code', 'descripcion']
    ordering_fields = ['fecha', 'device', 'code', 'resultado']


class BitacoraHardeningViewSet(viewsets.ModelViewSet):
    """CRUD for hardening incident tickets."""

    queryset = BitacoraHardening.objects.select_related('hardening', 'assigned_user').order_by('-created_at')
    serializer_class = BitacoraHardeningSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status', 'device', 'code', 'fecha']
    search_fields = ['ticket_id', 'device', 'code', 'descripcion']
    ordering_fields = ['created_at', 'fecha', 'device', 'code', 'status']


class HealthCheckDDIViewSet(viewsets.ModelViewSet):
    """CRUD for daily DDI (Infoblox Grid member) health snapshots."""

    queryset         = HealthCheckDDI.objects.all().order_by('-fecha', 'fqdn')
    serializer_class = HealthCheckDDISerializer
    filter_backends  = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['fqdn', 'fecha', 'platform', 'grid_status']
    search_fields    = ['fqdn', 'platform', 'grid_status']
    ordering_fields  = ['fecha', 'fqdn', 'cpu_pct', 'mem_pct', 'disk_pct', 'uptime_dias']
