from __future__ import annotations

from rest_framework import serializers

from apps.branches.models import Branch, Organization


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ("id", "name", "slug", "legal_name", "currency", "timezone", "is_active")
        read_only_fields = ("id",)


class BranchSerializer(serializers.ModelSerializer):
    manager_name = serializers.CharField(source="manager.full_name", read_only=True)

    class Meta:
        model = Branch
        fields = (
            "id", "name", "code", "address", "city", "phone", "email",
            "manager", "manager_name", "is_active", "opened_on", "created_at",
        )
        read_only_fields = ("id", "created_at")


class BranchWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Branch
        fields = ("name", "code", "address", "city", "phone", "email", "manager", "is_active", "opened_on")
