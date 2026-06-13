"""Stock-out prediction from the forecast feed (pure functions)."""
from __future__ import annotations

import math


def predict_stockouts(items: list[dict], horizon_days: int) -> list[dict]:
    """
    Given per-product {quantity, avg_daily_sales, reorder_level}, estimate days
    until each product hits zero, and flag those at risk within `horizon_days`.

    Returns at-risk products sorted by soonest stock-out. Products with no sales
    velocity are not "stocking out" (no demand) but are surfaced separately by
    the caller as dead stock.
    """
    horizon_days = max(int(horizon_days), 1)
    at_risk: list[dict] = []

    for item in items:
        qty = float(item.get("quantity") or 0)
        avg_daily = float(item.get("avg_daily_sales") or 0)
        reorder = float(item.get("reorder_level") or 0)

        if avg_daily <= 0:
            continue  # no demand -> not a stock-out risk

        days_to_zero = qty / avg_daily
        days_to_reorder = (qty - reorder) / avg_daily if qty > reorder else 0.0

        if days_to_zero <= horizon_days:
            # Suggest ordering enough to cover the horizon plus the reorder buffer.
            suggested = math.ceil(avg_daily * horizon_days + reorder - qty)
            at_risk.append(
                {
                    "product_id": item.get("product_id"),
                    "sku": item.get("sku"),
                    "name": item.get("name"),
                    "quantity": qty,
                    "avg_daily_sales": round(avg_daily, 3),
                    "days_to_stockout": round(days_to_zero, 1),
                    "days_to_reorder_level": round(days_to_reorder, 1),
                    "suggested_reorder_qty": max(suggested, 0),
                    "stockout_date_offset_days": math.floor(days_to_zero),
                }
            )

    at_risk.sort(key=lambda r: r["days_to_stockout"])
    return at_risk
