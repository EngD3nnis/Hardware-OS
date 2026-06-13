"""Organization (tenant root) and Branch (physical location)."""
from __future__ import annotations

import uuid

from django.db import models

from core.models import BaseModel, TenantScopedModel


class Organization(models.Model):
    """
    The tenant. Top of the scope hierarchy. Everything else hangs off this so
    a single deployment can serve multiple companies (multi-tenant ready).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=80, unique=True)
    legal_name = models.CharField(max_length=200, blank=True)
    currency = models.CharField(max_length=3, default="KES")  # ISO 4217
    timezone = models.CharField(max_length=64, default="Africa/Nairobi")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


class Branch(TenantScopedModel):
    """A physical store location under an organization."""

    name = models.CharField(max_length=150)
    code = models.CharField(max_length=20)  # unique per org (see constraint)
    address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=32, blank=True)
    email = models.EmailField(blank=True)
    manager = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="managed_branches",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    opened_on = models.DateField(null=True, blank=True)

    class Meta(TenantScopedModel.Meta):
        verbose_name_plural = "branches"
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "code"],
                condition=models.Q(is_deleted=False),
                name="uniq_branch_code_per_org",
            )
        ]
        indexes = [models.Index(fields=["organization", "is_active"])]

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"
