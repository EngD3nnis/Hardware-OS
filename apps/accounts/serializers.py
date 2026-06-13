from __future__ import annotations

from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from apps.accounts.models import Role, User


class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ("id", "slug", "name", "description", "level", "permissions")


class UserSerializer(serializers.ModelSerializer):
    roles = RoleSerializer(many=True, read_only=True)
    full_name = serializers.CharField(read_only=True)
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id", "email", "first_name", "last_name", "full_name", "phone",
            "organization", "branch", "roles", "permissions", "mfa_enabled",
            "is_active", "created_at",
        )
        read_only_fields = ("id", "created_at", "mfa_enabled")

    def get_permissions(self, obj: User) -> list[str]:
        return sorted(obj.permission_codes())


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, style={"input_type": "password"})
    mfa_code = serializers.CharField(required=False, allow_blank=True)


class TokenPairSerializer(TokenObtainPairSerializer):
    """Embeds identity + permission claims in the access token."""

    @classmethod
    def get_token(cls, user: User):
        token = super().get_token(user)
        token["email"] = user.email
        token["organization_id"] = str(user.organization_id or "")
        token["branch_id"] = str(user.branch_id or "")
        token["roles"] = user.role_slugs
        return token


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=10)


class MFAConfirmSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=6)
