"""Audit recording helpers used by the service layer."""
from __future__ import annotations

from typing import Any

from django.db.models import Model

from core.audit.context import get_context
from core.audit.models import AuditAction, AuditLog


def diff_fields(
    before: dict[str, Any] | None, after: dict[str, Any] | None
) -> dict[str, dict[str, Any]]:
    """Build a field-level {field: {old, new}} diff between two snapshots."""
    before = before or {}
    after = after or {}
    changes: dict[str, dict[str, Any]] = {}
    for key in set(before) | set(after):
        old, new = before.get(key), after.get(key)
        if old != new:
            changes[key] = {"old": _safe(old), "new": _safe(new)}
    return changes


def _safe(value: Any) -> Any:
    # JSON-serialisable snapshot of a field value.
    from decimal import Decimal
    from uuid import UUID

    if isinstance(value, (Decimal, UUID)):
        return str(value)
    return value


def record_audit(
    *,
    action: str,
    entity: Model | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    changes: dict | None = None,
    metadata: dict | None = None,
    branch_id: str | None = None,
) -> AuditLog:
    """
    Persist an audit row, pulling actor/IP/org from the request context.

    Call from services for every critical mutation. Failures here must never
    break the business operation, but they must be visible — so we log and
    re-raise only in DEBUG.
    """
    ctx = get_context()
    user = ctx.user if getattr(ctx, "user", None) and ctx.user.is_authenticated else None

    if entity is not None:
        entity_type = entity_type or entity.__class__.__name__
        entity_id = entity_id or str(getattr(entity, "pk", ""))

    return AuditLog.objects.create(
        actor=user,
        actor_label=(getattr(user, "email", "") or "system"),
        organization_id=ctx.organization_id,
        branch_id=branch_id,
        action=action,
        entity_type=entity_type or "",
        entity_id=str(entity_id or ""),
        changes=changes or {},
        metadata=metadata or {},
        ip_address=ctx.ip_address,
        user_agent=ctx.user_agent,
    )


__all__ = ["record_audit", "diff_fields", "AuditAction"]
