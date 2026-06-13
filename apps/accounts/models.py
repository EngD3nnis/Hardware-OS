"""User, Role and Session models — the identity + RBAC core."""
from __future__ import annotations

import uuid

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models

from apps.accounts.managers import UserManager


class Role(models.Model):
    """
    A bundle of permission codes (see core.rbac). Seeded from
    ROLE_DEFINITIONS by the `bootstrap` management command.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    level = models.PositiveIntegerField(default=0)  # hierarchy weight
    permissions = models.JSONField(default=list, blank=True)  # list[str] of codes
    is_system = models.BooleanField(default=False)  # protected from deletion
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-level",)

    def __str__(self) -> str:
        return self.name


class User(AbstractBaseUser, PermissionsMixin):
    """Custom user — authenticates by email, scoped to an organization + branch."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, db_index=True)
    first_name = models.CharField(max_length=80, blank=True)
    last_name = models.CharField(max_length=80, blank=True)
    phone = models.CharField(max_length=32, blank=True)

    organization = models.ForeignKey(
        "branches.Organization",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="users",
    )
    branch = models.ForeignKey(
        "branches.Branch",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="staff",
    )
    roles = models.ManyToManyField(Role, blank=True, related_name="users")

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    # MFA-ready (TOTP). Enrollment endpoints come with the auth module hardening.
    mfa_enabled = models.BooleanField(default=False)
    mfa_secret = models.CharField(max_length=64, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        ordering = ("email",)
        indexes = [models.Index(fields=["organization", "branch"])]

    def __str__(self) -> str:
        return self.email

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip() or self.email

    # -- RBAC ------------------------------------------------------------- #
    def permission_codes(self) -> set[str]:
        """Union of permission codes across all assigned roles (cached per instance)."""
        cached = getattr(self, "_perm_cache", None)
        if cached is None:
            cached = set()
            for role in self.roles.all():
                cached.update(role.permissions or [])
            self._perm_cache = cached
        return cached

    def has_perm_code(self, code: str) -> bool:
        if self.is_superuser:
            return True
        return code in self.permission_codes()

    @property
    def role_slugs(self) -> list[str]:
        return list(self.roles.values_list("slug", flat=True))


class LoginEvent(models.Model):
    """Session/login activity record (complements the audit trail)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="logins"
    )
    email_attempted = models.EmailField(blank=True)
    successful = models.BooleanField(default=False)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["user", "-created_at"])]
