"""Shared view/viewset base classes."""
from __future__ import annotations

from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet, ViewSet

from core.audit.context import get_context, set_context
from core.permissions import HasPermission, IsSameOrganization


class TenantContextMixin:
    """
    Re-binds the request context to the DRF-authenticated user.

    Middleware runs before JWT auth, so it can only see the session user. DRF
    resolves the real user later; this mixin refreshes the thread-local context
    inside ``initial()`` so services downstream see the correct actor + org.
    """

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        user = request.user
        if user and user.is_authenticated:
            ctx = get_context()
            ctx.user = user
            ctx.organization_id = str(getattr(user, "organization_id", "") or "") or None
            set_context(ctx)
            request.organization_id = ctx.organization_id

    @property
    def organization_id(self):
        return getattr(self.request, "organization_id", None)


class BaseModelViewSet(TenantContextMixin, ModelViewSet):
    """Authenticated, RBAC-guarded, org-scoped model viewset."""

    permission_classes = [IsAuthenticated, HasPermission, IsSameOrganization]


class BaseViewSet(TenantContextMixin, ViewSet):
    permission_classes = [IsAuthenticated, HasPermission]
