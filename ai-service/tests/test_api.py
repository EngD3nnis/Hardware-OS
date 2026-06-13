"""Endpoint wiring tests with the upstream HardwareOS client mocked."""
import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from app.client import HardwareOSClient  # noqa: E402
from app.main import app, get_client  # noqa: E402

AUTH = {"Authorization": "Bearer test-token"}

_OVERVIEW = {
    "trend": {"daily_net_revenue": [{"date": f"2026-06-{d:02d}", "amount": 100 + d} for d in range(1, 15)]},
    "revenue": {"today": 114, "week": 700, "month": 3000},
    "ai_insights": {"summary": "Revenue up 10%.", "items": ["Revenue up 10%."], "revenue_change_pct": 10.0},
    "branches": {"ranking": [
        {"name": "HQ", "code": "HQ", "net_revenue": 3000, "net_profit": 800, "transactions": 20, "rank": 1},
        {"name": "WL", "code": "WL", "net_revenue": 500, "net_profit": 50, "transactions": 4, "rank": 2},
    ]},
}
_FEED = {"items": [
    {"product_id": "1", "sku": "CEM-50", "name": "Cement", "quantity": 8,
     "reorder_level": 5, "avg_daily_sales": 2.0},
    {"product_id": "2", "sku": "ROOF", "name": "Roofing", "quantity": 500,
     "reorder_level": 10, "avg_daily_sales": 1.0},
]}


class FakeClient(HardwareOSClient):
    def __init__(self):
        super().__init__("fake")

    async def dashboard_overview(self, branch=None):
        return _OVERVIEW

    async def revenue(self, period="month", branch=None):
        return {"top_products": [{"name": "Cement", "revenue": 2000}]}

    async def branch_ranking(self):
        return {"ranking": _OVERVIEW["branches"]["ranking"]}

    async def forecast_feed(self, days=30, branch=None):
        return _FEED


@pytest.fixture
def client():
    app.dependency_overrides[get_client] = lambda: FakeClient()
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_health_no_auth_required():
    c = TestClient(app)
    r = c.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_missing_token_rejected():
    c = TestClient(app)
    assert c.get("/ai/forecast/revenue").status_code == 401


def test_revenue_forecast(client):
    r = client.get("/ai/forecast/revenue?horizon=7", headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["horizon_days"] == 7
    assert body["history_days"] == 14
    assert len(body["forecast"]["projected_daily"]) == 7


def test_stockout_forecast(client):
    r = client.get("/ai/forecast/stockouts?horizon=14&days=30", headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    skus = [p["sku"] for p in body["products"]]
    assert "CEM-50" in skus and "ROOF" not in skus  # cement runs out in 4 days, roofing safe


def test_ask_worst_branch(client):
    r = client.post("/ai/ask", json={"question": "Which branch performs worst?"}, headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert "WL" in body["answer"] or "WL" in body["answer"].upper()
    assert body["engine"] == "rule-based"
