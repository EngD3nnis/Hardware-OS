"""
HardwareOS AI service.

A separate FastAPI app that consumes the HardwareOS REST API (forwarding the
caller's JWT) and adds intelligence on top: revenue/demand forecasting,
stock-out prediction, and natural-language querying. It holds no database.
"""
from __future__ import annotations

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.client import HardwareOSClient, HardwareOSError
from app.config import settings
from app.forecasting import forecast_series, series_from_trend
from app.inventory import predict_stockouts
from app.llm import synthesize
from app.schemas import (
    AskRequest,
    AskResponse,
    ForecastResponse,
    HealthResponse,
    StockoutResponse,
)

app = FastAPI(
    title="HardwareOS AI Service",
    version="0.1.0",
    description="Forecasting, stock-out prediction, and natural-language querying.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_allow_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)


async def get_token(authorization: str = Header(default="")) -> str:
    """
    Extract the bearer token. We forward the caller's HardwareOS JWT so the AI
    service sees exactly the data the user is authorized for (RBAC + tenancy).
    """
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token.")
    return authorization.split(" ", 1)[1].strip()


def get_client(token: str = Depends(get_token)) -> HardwareOSClient:
    return HardwareOSClient(token)


def _handle_api_error(exc: HardwareOSError) -> HTTPException:
    # Surface auth/permission errors faithfully; wrap the rest as 502.
    if exc.status_code in (401, 403, 404):
        return HTTPException(status_code=exc.status_code, detail=exc.detail)
    return HTTPException(status_code=502, detail=f"Upstream API error: {exc.detail}")


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        llm_enabled=bool(settings.anthropic_api_key),
        model=settings.anthropic_model if settings.anthropic_api_key else "rule-based",
    )


@app.get("/ai/forecast/revenue", response_model=ForecastResponse)
async def forecast_revenue(
    horizon: int = 14,
    branch: str | None = None,
    client: HardwareOSClient = Depends(get_client),
) -> ForecastResponse:
    """Project revenue for the next `horizon` days from the recent daily trend."""
    try:
        overview = await client.dashboard_overview(branch)
    except HardwareOSError as exc:
        raise _handle_api_error(exc)

    points = (overview.get("trend", {}) or {}).get("daily_net_revenue", [])
    history = series_from_trend(points)
    return ForecastResponse(
        branch=branch,
        horizon_days=horizon,
        history_days=len(history),
        forecast=forecast_series(history, horizon),
    )


@app.get("/ai/forecast/stockouts", response_model=StockoutResponse)
async def forecast_stockouts(
    horizon: int = 14,
    days: int = 30,
    branch: str | None = None,
    client: HardwareOSClient = Depends(get_client),
) -> StockoutResponse:
    """Which products will stock out within `horizon` days, at current velocity."""
    try:
        feed = await client.forecast_feed(days=days, branch=branch)
    except HardwareOSError as exc:
        raise _handle_api_error(exc)

    risks = predict_stockouts(feed.get("items", []), horizon)
    return StockoutResponse(
        branch=branch, horizon_days=horizon, at_risk_count=len(risks), products=risks
    )


@app.post("/ai/ask", response_model=AskResponse)
async def ask(req: AskRequest, client: HardwareOSClient = Depends(get_client)) -> AskResponse:
    """
    Natural-language querying. Gathers the relevant facts from the API, then
    answers via Claude (if configured) or the deterministic engine.
    """
    try:
        context: dict = {"overview": await client.dashboard_overview(req.branch)}
        q = req.question.lower()
        if "revenue" in q or "sell" in q or "sales" in q:
            context["revenue"] = await client.revenue("month", req.branch)
        if "branch" in q:
            context["branches"] = await client.branch_ranking()
        if "stock" in q or "run out" in q or "reorder" in q:
            feed = await client.forecast_feed(days=30, branch=req.branch)
            context["stockouts"] = predict_stockouts(feed.get("items", []), 14)
    except HardwareOSError as exc:
        raise _handle_api_error(exc)

    answer, engine = synthesize(req.question, context)
    return AskResponse(question=req.question, answer=answer, engine=engine, branch=req.branch)
