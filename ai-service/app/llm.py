"""
Natural-language answer synthesis.

If an Anthropic API key is configured, questions are answered by Claude
(claude-opus-4-8 by default) grounded in JSON business facts fetched from the
HardwareOS API. Otherwise a deterministic intent engine answers the common
executive questions so the feature degrades gracefully with no external deps.
"""
from __future__ import annotations

import json

from app.config import settings

SYSTEM_PROMPT = (
    "You are the executive analyst for HardwareOS, the operating system of a "
    "multi-branch hardware business. Answer the owner's question using ONLY the "
    "JSON business data provided. Be concise and specific: cite actual numbers, "
    "name branches/products, and give a one-line recommendation when relevant. "
    "All monetary values are in the organization's currency (assume KES). If the "
    "data does not contain the answer, say so plainly. Do not invent figures."
)


def answer_with_claude(question: str, context: dict) -> tuple[str, str]:
    """Returns (answer_text, engine_id). Raises on SDK/network error."""
    from anthropic import Anthropic

    client = Anthropic(api_key=settings.anthropic_api_key)
    message = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=settings.anthropic_max_tokens,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Business data (JSON):\n{json.dumps(context, default=str)}\n\n"
                    f"Question: {question}"
                ),
            }
        ],
    )
    text = "".join(block.text for block in message.content if block.type == "text")
    return text.strip(), settings.anthropic_model


def synthesize(question: str, context: dict) -> tuple[str, str]:
    """Use Claude when configured; otherwise the deterministic engine."""
    if settings.anthropic_api_key:
        try:
            return answer_with_claude(question, context)
        except Exception as exc:  # network/SDK/key issue -> graceful fallback
            text = heuristic_answer(question, context)
            return f"{text}\n\n(Note: AI model unavailable — {type(exc).__name__}.)", "rule-based-fallback"
    return heuristic_answer(question, context), "rule-based"


# --------------------------------------------------------------------------- #
# Deterministic intent engine — handles the common executive questions.
# --------------------------------------------------------------------------- #
def heuristic_answer(question: str, context: dict) -> str:
    q = (question or "").lower()
    overview = context.get("overview", {})

    if "stock out" in q or "stockout" in q or "run out" in q:
        return _stockout_answer(context)
    if "worst" in q or ("which branch" in q and ("worst" in q or "lowest" in q or "underperform" in q)):
        return _branch_answer(context, worst=True)
    if "best branch" in q or "top branch" in q or "which branch" in q:
        return _branch_answer(context, worst=False)
    if "revenue" in q and ("why" in q or "drop" in q or "decline" in q or "fall" in q or "down" in q):
        return _revenue_change_answer(context)
    if "insight" in q or "summary" in q or "how are we doing" in q or "overview" in q:
        return _summary_answer(overview)
    return _summary_answer(overview)


def _summary_answer(overview: dict) -> str:
    insights = overview.get("ai_insights", {})
    summary = insights.get("summary")
    return summary or "No recent business activity to summarize."


def _revenue_change_answer(context: dict) -> str:
    overview = context.get("overview", {})
    insights = overview.get("ai_insights", {})
    change = insights.get("revenue_change_pct")
    rev = overview.get("revenue", {})
    parts = []
    if change is not None:
        direction = "up" if float(change) >= 0 else "down"
        parts.append(f"Week-over-week revenue is {direction} {abs(float(change))}%.")
    if rev:
        parts.append(
            f"This month: {rev.get('month')}, this week: {rev.get('week')}, today: {rev.get('today')}."
        )
    top = (context.get("revenue", {}) or {}).get("top_products") or []
    if top:
        names = ", ".join(f"{t['name']} ({t['revenue']})" for t in top[:3])
        parts.append(f"Top revenue drivers: {names}.")
    if insights.get("items"):
        parts.append(insights["items"][0])
    return " ".join(parts) or "Not enough data to explain the revenue change."


def _branch_answer(context: dict, worst: bool) -> str:
    ranking = (context.get("branches", {}) or {}).get("ranking") or \
        (context.get("overview", {}).get("branches", {}) or {}).get("ranking") or []
    if not ranking:
        return "No branch performance data available for this period."
    target = ranking[-1] if worst else ranking[0]
    label = "lowest-performing" if worst else "top-performing"
    return (
        f"The {label} branch this month is {target['name']} ({target['code']}) "
        f"with net revenue {target['net_revenue']} and net profit {target['net_profit']} "
        f"across {target['transactions']} transaction(s)."
    )


def _stockout_answer(context: dict) -> str:
    risks = context.get("stockouts") or []
    if not risks:
        return "No products are projected to stock out within the requested horizon."
    lines = [
        f"{r['name']} ({r['sku']}): ~{r['days_to_stockout']} days left "
        f"(suggest reordering {r['suggested_reorder_qty']})"
        for r in risks[:5]
    ]
    return "Products at risk of stocking out:\n- " + "\n- ".join(lines)
