"""DRF permission classes that enforce the RBAC registry."""
from __future__ import annotations

from rest_framework.permissions import BasePermission


class HasPermission(BasePermission):
    """
    Checks a single required permission code declared on the view as
    ``required_permission`` (or a per-action map ``permission_map``).

    Usage::

        class ProductViewSet(ViewSet):
            permission_classes = [IsAuthenticated, HasPermission]
            permission_map = {
                "list": Perm.PRODUCT_VIEW,
                "create": Perm.PRODUCT_MANAGE,
            }
    """

    message = "You do not have permission to perform this action."

    def has_permission(self, request, view) -> bool:
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True

        required = self._resolve_required(request, view)
        if required is None:
            return True  # no explicit requirement => authenticated is enough
        return user.has_perm_code(required)

    @staticmethod
    def _resolve_required(request, view) -> str | None:
        permission_map = getattr(view, "permission_map", None)
        if permission_map:
            action = getattr(view, "action", None) or request.method.lower()
            return permission_map.get(action)
        return getattr(view, "required_permission", None)


class IsSameOrganization(BasePermission):
    """Object-level guard: object must belong to the request's organization."""

    def has_object_permission(self, request, view, obj) -> bool:
        org_id = getattr(request, "organization_id", None)
        obj_org = getattr(obj, "organization_id", None)
        if obj_org is None:
            return True
        return str(obj_org) == str(org_id)
