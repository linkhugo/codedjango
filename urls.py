"""
URL routing for the ddi_manager application.
"""

from django.urls import path
from . import views

urlpatterns = [
    path('ddi/inventory/', views.DDIInventoryListView.as_view(), name='ddi_inventory_list'),
    path('ddi/inventory/data/', views.ddi_inventory_data, name='ddi_inventory_data'),
    path('ddi/inventory/device-history/<int:device_id>/', views.ddi_device_history, name='ddi_device_history'),

    path('ddi/devices/', views.DDIDeviceListView.as_view(), name='ddi_device_list'),
    path('ddi/devices/data/', views.ddi_device_list_data, name='ddi_device_list_data'),
    path('ddi/devices/add/', views.DDIDeviceCreateView.as_view(), name='ddi_device_add'),
    path('ddi/devices/<int:pk>/edit/', views.DDIDeviceUpdateView.as_view(), name='ddi_device_edit'),
    path('ddi/devices/<int:pk>/delete/', views.DDIDeviceDeleteView.as_view(), name='ddi_device_delete'),

    path('ddi/services/', views.DDIServiceListView.as_view(), name='ddi_service_list'),
    path('ddi/services/add/', views.DDIServiceCreateView.as_view(), name='ddi_service_add'),
    path('ddi/services/<str:pk>/edit/', views.DDIServiceUpdateView.as_view(), name='ddi_service_edit'),
    path('ddi/services/<str:pk>/delete/', views.DDIServiceDeleteView.as_view(), name='ddi_service_delete'),

    path('ddi/licenses/', views.DDILicenseListView.as_view(), name='ddi_license_list'),
    path('ddi/licenses/add/', views.DDILicenseCreateView.as_view(), name='ddi_license_add'),
    path('ddi/licenses/<str:pk>/edit/', views.DDILicenseUpdateView.as_view(), name='ddi_license_edit'),
    path('ddi/licenses/<str:pk>/delete/', views.DDILicenseDeleteView.as_view(), name='ddi_license_delete'),

    # Version Chart
    path('ddi/version-chart/',       views.ddi_version_chart,      name='ddi_version_chart'),
    path('ddi/version-chart/data/',  views.ddi_version_chart_data,  name='ddi_version_chart_data'),

    # DDI Healthcheck
    path('ddi/healthcheck/',      views.DDIHealthCheckListView.as_view(), name='ddi_healthcheck_list'),
    path('ddi/healthcheck/data/', views.ddi_healthcheck_data,             name='ddi_healthcheck_data'),
]
