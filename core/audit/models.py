"""Immutable audit trail."""
import uuid

from django.conf import settings
from django.db import models


class AuditAction(models.TextChoices):
    CREATE = "create", "Create"
    UPDATE = "update", "Update"
    DELETE = "delete", "Delete"
    LOGIN = "login", "Login"
    LOGIN_FAILED = "login_failed", "Login Failed"
    LOGOUT = "logout", "Logout"
    PRICE_CHANGE = "price_change", "Price Change"
    STOCK_CHANGE = "stock_change", "Stock Change"
    FINANCIAL = "financial", "Financial Transaction"
    REFUND = "refund", "Refund"
    PERMISSION_CHANGE = "permission_change", "Permission Change"


class AuditLog(models.Model):
    """
    One row per critical action. Append-only — never updated or deleted.

    `changes` holds a field-level diff: {"field": {"old": x, "new": y}}.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_logs",
    )
    actor_label = models.CharField(max_length=255, blank=True)  # snapshot of who

    organization_id = models.UUIDField(null=True, blank=True, db_index=True)
    branch_id = models.UUIDField(null=True, blank=True, db_index=True)

    action = models.CharField(max_length=32, choices=AuditAction.choices, db_index=True)
    entity_type = models.CharField(max_length=100, db_index=True)
    entity_id = models.CharField(max_length=64, blank=True, db_index=True)

    changes = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    class Meta:
        ordering = ("-timestamp",)
        indexes = [
            models.Index(fields=["organization_id", "entity_type", "-timestamp"]),
            models.Index(fields=["actor", "-timestamp"]),
            models.Index(fields=["action", "-timestamp"]),
        ]

    def __str__(self) -> str:
        return f"{self.action} {self.entity_type}#{self.entity_id} @ {self.timestamp}"
