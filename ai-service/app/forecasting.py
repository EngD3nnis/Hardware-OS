"""
Lightweight, dependency-light forecasting.

These are pure functions over already-fetched data so they're trivially testable
and have no I/O. They favour robust, explainable methods (linear trend + recent
average + residual-based bands) over opaque ML — appropriate for a hardware
business with modest history and a need to justify the numbers to an owner.
"""
from __future__ import annotations

import numpy as np


def forecast_series(history: list[float], horizon: int) -> dict:
    """
    Project the next `horizon` daily values from a daily history.

    Blends a least-squares linear trend with the recent 7-day average, and
    derives a ± band from the residual standard deviation. Never returns
    negative projections (you can't sell negative units).
    """
    horizon = max(int(horizon), 1)
    series = np.array([float(x) for x in history], dtype=float)

    if series.size == 0:
        return {
            "method": "insufficient_data",
            "horizon_days": horizon,
            "projected_daily": [0.0] * horizon,
            "projected_total": 0.0,
            "confidence_band": {"low": 0.0, "high": 0.0},
            "daily_average": 0.0,
            "trend_per_day": 0.0,
        }

    n = series.size
    x = np.arange(n)
    recent = series[-7:] if n >= 7 else series
    recent_avg = float(recent.mean())

    if n >= 3:
        slope, intercept = np.polyfit(x, series, 1)
        fitted = slope * x + intercept
        residual_std = float(np.std(series - fitted))
        future_x = np.arange(n, n + horizon)
        trend_proj = slope * future_x + intercept
        # Weight trend and recent average so a single noisy day can't dominate.
        projected = 0.6 * trend_proj + 0.4 * recent_avg
        method = "linear_trend+recent_avg"
        trend_per_day = float(slope)
    else:
        projected = np.full(horizon, recent_avg)
        residual_std = float(np.std(series)) if n > 1 else 0.0
        method = "recent_average"
        trend_per_day = 0.0

    projected = np.clip(projected, 0.0, None)
    total = float(projected.sum())
    band = 1.96 * residual_std * np.sqrt(horizon)  # ~95% interval on the total

    return {
        "method": method,
        "horizon_days": horizon,
        "projected_daily": [round(v, 2) for v in projected.tolist()],
        "projected_total": round(total, 2),
        "confidence_band": {
            "low": round(max(total - band, 0.0), 2),
            "high": round(total + band, 2),
        },
        "daily_average": round(recent_avg, 2),
        "trend_per_day": round(trend_per_day, 4),
    }


def series_from_trend(daily_points: list[dict], value_key: str = "amount") -> list[float]:
    """Extract an ordered numeric series from dashboard trend points."""
    return [float(p.get(value_key) or 0) for p in daily_points]
