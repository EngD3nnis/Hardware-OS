"""Middleware that establishes the request context for auditing + tenancy."""
from __future__ import annotations

import uuid

from core.audit.context import RequestContext, reset_context, set_context


def _client_ip(request) -> str | None:
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


class AuditContextMiddleware:
    """
    Populates a thread-local RequestContext for the duration of each request,
    and exposes ``request.organization_id`` for views/permissions.

    JWT auth runs inside DRF (after middleware), so ``request.user`` here is the
    session/anonymous user. We therefore set the user lazily via a thin wrapper:
    DRF re-resolves the user, and services read it through ``get_context`` which
    reflects the latest assignment made in the view base class.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        org_id = None
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            org_id = str(getattr(user, "organization_id", "") or "") or None

        ctx = RequestContext(
            user=user,
            organization_id=org_id,
            ip_address=_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:1000],
            request_id=str(uuid.uuid4()),
        )
        token = set_context(ctx)
        request.organization_id = org_id
        request.request_id = ctx.request_id
        try:
            response = self.get_response(request)
        finally:
            reset_context(token)
        response["X-Request-ID"] = ctx.request_id
        return response
