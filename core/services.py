"""Service layer base — owns use-cases, transactions and audit emission."""
from __future__ import annotations

from core.audit.services import diff_fields, record_audit


class BaseService:
    """
    Base for application services.

    Subclasses orchestrate repositories, enforce business rules inside
    transactions, and emit audit events. Keep ORM access in repositories and
    HTTP concerns in views — services are framework-agnostic use-cases.
    """

    # Helpers re-exported so services have one import surface.
    record_audit = staticmethod(record_audit)
    diff_fields = staticmethod(diff_fields)

    @staticmethod
    def snapshot(instance, fields: list[str]) -> dict:
        """Capture selected field values for before/after diffing."""
        return {f: getattr(instance, f) for f in fields}
