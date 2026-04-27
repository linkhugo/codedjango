"""
URL routing for the lb_manager REST API (mounted at /api/v1/).

Token endpoints:
  POST /api/v1/token/          → obtain JWT access + refresh tokens
  POST /api/v1/token/refresh/  → rotate refresh token, get new access token
  POST /api/v1/token/verify/   → verify a token is still valid

Resource endpoints (full CRUD via DRF router):
  /api/v1/health/f5/
  /api/v1/health/dns/
  /api/v1/health/dhcp/
  /api/v1/hardening/checks/
  /api/v1/hardening/tickets/
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    TokenVerifyView,
)

from .views import (
    BitacoraHardeningViewSet,
    HealthCheckDDIViewSet,
    HealthCheckDHCPViewSet,
    HealthCheckDNSViewSet,
    HealthCheckF5ViewSet,
    LBHardeningViewSet,
)

router = DefaultRouter()
router.register(r'health/f5',          HealthCheckF5ViewSet,       basename='health-f5')
router.register(r'health/dns',         HealthCheckDNSViewSet,      basename='health-dns')
router.register(r'health/dhcp',        HealthCheckDHCPViewSet,     basename='health-dhcp')
router.register(r'health/ddi',         HealthCheckDDIViewSet,      basename='health-ddi')
router.register(r'hardening/checks',   LBHardeningViewSet,         basename='hardening-checks')
router.register(r'hardening/tickets',  BitacoraHardeningViewSet,   basename='hardening-tickets')

urlpatterns = [
    path('token/',         TokenObtainPairView.as_view(),  name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(),     name='token_refresh'),
    path('token/verify/',  TokenVerifyView.as_view(),      name='token_verify'),
    path('', include(router.urls)),
]
