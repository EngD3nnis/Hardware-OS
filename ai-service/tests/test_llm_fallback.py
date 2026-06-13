"""The deterministic engine must answer the common executive questions."""
from app.llm import heuristic_answer

CONTEXT = {
    "overview": {
        "revenue": {"today": 1000, "week": 5000, "month": 20000},
        "ai_insights": {
            "summary": "Revenue increased by 12% this week.",
            "items": ["Revenue increased by 12% this week."],
            "revenue_change_pct": 12.0,
        },
        "branches": {
            "ranking": [
                {"name": "Head Office", "code": "HQ", "net_revenue": 20000,
                 "net_profit": 5000, "transactions": 40, "rank": 1},
                {"name": "Westlands", "code": "WL", "net_revenue": 3000,
                 "net_profit": 200, "transactions": 8, "rank": 2},
            ]
        },
    },
    "stockouts": [
        {"name": "Cement 50kg", "sku": "CEM-50", "days_to_stockout": 4.0, "suggested_reorder_qty": 30},
    ],
}


def test_worst_branch():
    ans = heuristic_answer("Which branch performs worst?", CONTEXT)
    assert "Westlands" in ans and "lowest" in ans.lower()


def test_best_branch():
    ans = heuristic_answer("Which is the best branch?", CONTEXT)
    assert "Head Office" in ans


def test_revenue_why():
    ans = heuristic_answer("Why did revenue change?", CONTEXT)
    assert "%" in ans


def test_stockout_question():
    ans = heuristic_answer("What will run out of stock?", CONTEXT)
    assert "CEM-50" in ans and "reorder" in ans.lower()


def test_default_summary():
    ans = heuristic_answer("How are we doing?", CONTEXT)
    assert "Revenue increased by 12% this week." in ans
