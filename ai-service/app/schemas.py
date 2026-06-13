from __future__ import annotations

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(..., min_length=3, examples=["Why did revenue drop?"])
    branch: str | None = None


class AskResponse(BaseModel):
    question: str
    answer: str
    engine: str
    branch: str | None = None


class ForecastResponse(BaseModel):
    branch: str | None = None
    horizon_days: int
    history_days: int
    forecast: dict


class StockoutResponse(BaseModel):
    branch: str | None = None
    horizon_days: int
    at_risk_count: int
    products: list[dict]


class HealthResponse(BaseModel):
    status: str
    llm_enabled: bool
    model: str
