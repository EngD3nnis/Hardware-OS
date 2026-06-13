"""
Request-scoped context (thread-local).

Carries the acting user + request metadata so the service layer can write
audit records without threading `request` through every function signature.
"""
from __future__ import annotations

import contextvars
from dataclasses import dataclass
from typing import Any


@dataclass
class RequestContext:
    user: Any = None
    organization_id: str | None = None
    ip_address: str | None = None
    user_agent: str = ""
    request_id: str | None = None


_ctx: contextvars.ContextVar[RequestContext] = contextvars.ContextVar(
    "request_context", default=RequestContext()
)


def set_context(ctx: RequestContext) -> contextvars.Token:
    return _ctx.set(ctx)


def reset_context(token: contextvars.Token) -> None:
    _ctx.reset(token)


def get_context() -> RequestContext:
    return _ctx.get()
