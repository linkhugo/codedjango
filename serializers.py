"""
Serializers for the lb_manager REST API.

Each serializer maps directly to its model with all fields exposed.
BitacoraHardeningSerializer uses a PrimaryKeyRelatedField for assigned_user
so that the field accepts a PK on write while returning the PK on read.
"""

from django.contrib.auth import get_user_model
from rest_framework import serializers

from ddi_manager.models import HealthCheckDDI
from lb_manager.models import (
    BitacoraHardening,
    HealthCheckDHCP,
    HealthCheckDNS,
    HealthCheckF5,
    LBHardening,
)


class HealthCheckF5Serializer(serializers.ModelSerializer):
    """Serializer for daily F5 appliance health snapshots."""

    class Meta:
        model = HealthCheckF5
        fields = '__all__'


class HealthCheckDNSSerializer(serializers.ModelSerializer):
    """Serializer for daily DNS server health snapshots."""

    class Meta:
        model = HealthCheckDNS
        fields = '__all__'


class HealthCheckDHCPSerializer(serializers.ModelSerializer):
    """Serializer for daily DHCP server health snapshots."""

    class Meta:
        model = HealthCheckDHCP
        fields = '__all__'


class LBHardeningSerializer(serializers.ModelSerializer):
    """Serializer for LB hardening check results."""

    class Meta:
        model = LBHardening
        fields = '__all__'


class BitacoraHardeningSerializer(serializers.ModelSerializer):
    """
    Serializer for hardening incident tickets.

    assigned_user is exposed as a nullable PK so that API clients can assign
    a user by ID without needing to embed the full user object.
    """

    assigned_user = serializers.PrimaryKeyRelatedField(
        read_only=False,
        allow_null=True,
        required=False,
        queryset=get_user_model().objects.all(),
    )

    class Meta:
        model = BitacoraHardening
        fields = '__all__'
        read_only_fields = ('ticket_id', 'created_at')


class HealthCheckDDISerializer(serializers.ModelSerializer):
    """Serializer for daily DDI (Infoblox Grid member) health snapshots."""

    class Meta:
        model  = HealthCheckDDI
        fields = '__all__'
