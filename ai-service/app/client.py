"""
Thin client over the HardwareOS REST API.

The AI service never touches the database — it reads facts through the API,
forwarding the caller's JWT so tenancy and RBAC are preserved end-to-end.
"""
from __future__ import annotations

from typing import Any

import httpx

from app.config import settings


class HardwareOSError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"HardwareOS API {status_code}: {detail}")


class HardwareOSClient:
    def __init__(self, token: str):
        self._token = token

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}", "Accept": "application/json"}

    async def _get(self, path: str, params: dict | None = None) -> Any:
        url = f"{settings.hardwareos_api_url.rstrip('/')}/{path.lstrip('/')}"
        async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
            resp = await client.get(url, headers=self._headers(), params=params or {})
        if resp.status_code >= 400:
            raise HardwareOSError(resp.status_code, resp.text[:500])
        return resp.json()

    # -- typed reads the AI features need -------------------------------- #
    async def dashboard_overview(self, branch: str | None = None) -> dict:
        return await self._get("analytics/dashboard/overview/", _branch(branch))

    async def revenue(self, period: str = "month", branch: str | None = None) -> dict:
        params = {"period": period, **_branch(branch)}
        return await self._get("analytics/dashboard/revenue/", params)

    async def branch_ranking(self) -> dict:
        return await self._get("analytics/dashboard/branches/")

    async def forecast_feed(self, days: int = 30, branch: str | None = None) -> dict:
        params = {"days": days, **_branch(branch)}
        return await self._get("inventory/stock/forecast-feed/", params)


def _branch(branch: str | None) -> dict:
    return {"branch": branch} if branch else {}
