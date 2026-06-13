"""
Analytics & the Executive Command Center.

DashboardService assembles the single executive payload (revenue, profit,
inventory, branches, people, finance, trend, insights). InsightService produces
an automatic executive summary with a deterministic rule engine today — the
FastAPI AI service (next phase) plugs in here for natural-language querying.
SnapshotService materialises daily rollups for scale (run by Celery beat).
"""
from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from django.utils import timezone

from apps.branches.repositories import BranchRepository
from apps.finance.periods import named_bounds
from apps.finance.repositories import ExpenseRepository
from apps.finance.services import FinanceReportService
from apps.inventory.repositories import DeadStockQuery, StockLevelRepository, StockMovementRepository
from apps.pos.repositories import SaleRepository, day_bounds
from core.services import BaseService

ZERO = Decimal("0")
_PERIODS = ["today", "yesterday", "week", "month", "year"]


def _pct_change(current: Decimal, previous: Decimal) -> Decimal:
    if previous == 0:
        return Decimal("100") if current > 0 else ZERO
    return ((current - previous) / previous * 100).quantize(Decimal("0.1"))


class DashboardService(BaseService):
    def __init__(self, organization_id: UUID | str):
        self.organization_id = organization_id
        self.sales = SaleRepository(organization_id)
        self.expenses = ExpenseRepository(organization_id)
        self.stock = StockLevelRepository(organization_id)
        self.movements = StockMovementRepository(organization_id)
        self.branches = BranchRepository(organization_id)
        self.finance = FinanceReportService(organization_id)

    def executive_overview(self, branch_id: UUID | None = None) -> dict:
        m_start, m_end = named_bounds("month")
        month_pnl = self.finance.profit_and_loss(m_start, m_end, branch_id)

        return {
            "generated_at": timezone.now(),
            "scope": "branch" if branch_id else "organization",
            "branch": str(branch_id) if branch_id else None,
            "revenue": self._revenue_by_period(branch_id),
            "profit": {
                "gross_profit": month_pnl["gross_profit"],
                "net_profit": month_pnl["net_profit"],
                "gross_margin": month_pnl["gross_margin"],
                "net_margin": month_pnl["net_margin"],
                "period": "month",
            },
            "inventory": self._inventory_block(branch_id),
            "branches": {"ranking": self._branch_ranking()},
            "employees": self._employee_block(branch_id),
            "finance": self._finance_block(branch_id, month_pnl),
            "trend": {"daily_net_revenue": self._trend(branch_id)},
            "ai_insights": InsightService(self.organization_id).generate(branch_id),
        }

    # -- blocks ----------------------------------------------------------- #
    def _revenue_by_period(self, branch_id) -> dict:
        out = {}
        for period in _PERIODS:
            start, end = named_bounds(period)
            out[period] = self.sales.sales_summary(start, end, branch_id)["net_revenue"]
        return out

    def _inventory_block(self, branch_id) -> dict:
        m_start, m_end = named_bounds("month")
        dead = list(DeadStockQuery(self.organization_id).run(branch_id=branch_id, limit=20))
        dead_value = sum((lvl.value for lvl in dead), ZERO)
        return {
            "stock_value": self.stock.total_inventory_value(branch_id),
            "low_stock_count": self.stock.low_stock(branch_id).count(),
            "dead_stock_count": len(dead),
            "dead_stock_value": dead_value,
            "fast_movers": self.movements.fast_movers(m_start, m_end, branch_id, limit=5),
        }

    def _branch_ranking(self) -> list[dict]:
        m_start, m_end = named_bounds("month")
        ranking = []
        for branch in self.branches.active():
            summary = self.sales.sales_summary(m_start, m_end, branch.id)
            opex = self.expenses.total(m_start.date(), m_end.date(), branch.id)
            ranking.append(
                {
                    "branch_id": str(branch.id),
                    "name": branch.name,
                    "code": branch.code,
                    "net_revenue": summary["net_revenue"],
                    "gross_profit": summary["gross_profit"],
                    "net_profit": summary["gross_profit"] - opex,
                    "transactions": summary["transactions"],
                }
            )
        ranking.sort(key=lambda r: r["net_revenue"], reverse=True)
        for i, row in enumerate(ranking, start=1):
            row["rank"] = i
        return ranking

    def _employee_block(self, branch_id) -> dict:
        m_start, m_end = named_bounds("month")
        return {
            "top_performers": self.sales.top_cashiers(m_start, m_end, branch_id, limit=5),
            # attendance & productivity require the Employees module (later phase).
            "attendance": None,
            "productivity": None,
        }

    def _finance_block(self, branch_id, month_pnl) -> dict:
        m_start, m_end = named_bounds("month")
        cash = self.finance.cash_flow(m_start, m_end, branch_id)
        return {
            "expenses_month": month_pnl["operating_expenses"],
            "expenses_by_category": month_pnl["expenses_by_category"],
            "net_cash_flow_month": cash["net_cash_flow"],
            "outstanding_payments": self.sales.outstanding_receivables(branch_id),
        }

    def _trend(self, branch_id, days: int = 30) -> list[dict]:
        end = timezone.now()
        start = end - timezone.timedelta(days=days)
        series = self.sales.daily_net_sales(start, end, branch_id)
        return [{"date": d, "amount": series[d]} for d in sorted(series)]


class InsightService(BaseService):
    """Deterministic executive summary. Swappable for the AI service later."""

    def __init__(self, organization_id: UUID | str):
        self.organization_id = organization_id
        self.sales = SaleRepository(organization_id)
        self.stock = StockLevelRepository(organization_id)

    def generate(self, branch_id: UUID | None = None) -> dict:
        w_start, w_end = named_bounds("week")
        prev_start = w_start - timezone.timedelta(days=7)
        prev_end = w_start

        this_week = self.sales.sales_summary(w_start, w_end, branch_id)
        last_week = self.sales.sales_summary(prev_start, prev_end, branch_id)
        change = _pct_change(this_week["net_revenue"], last_week["net_revenue"])

        items: list[str] = []
        direction = "increased" if change >= 0 else "declined"
        items.append(
            f"Revenue {direction} by {abs(change)}% this week "
            f"(KES {this_week['net_revenue']:.0f} vs KES {last_week['net_revenue']:.0f})."
        )

        top = self.sales.top_products(w_start, w_end, branch_id, limit=1)
        if top:
            items.append(
                f"Top performer: {top[0]['name']} — KES {top[0]['revenue']:.0f} "
                f"across {top[0]['quantity']:.0f} units."
            )

        low = self.stock.low_stock(branch_id).count()
        if low:
            items.append(f"{low} product(s) at or below reorder level — restock to avoid stockouts.")

        dead = list(DeadStockQuery(self.organization_id).run(branch_id=branch_id, limit=20))
        if dead:
            dead_value = sum((lvl.value for lvl in dead), ZERO)
            items.append(
                f"KES {dead_value:.0f} tied up in {len(dead)} slow/dead-stock item(s) "
                f"with no sales in 60 days."
            )

        if this_week["gross_margin"]:
            items.append(f"Gross margin this week: {this_week['gross_margin']:.1f}%.")

        return {
            "summary": " ".join(items) or "No sales activity recorded this week.",
            "items": items,
            "revenue_change_pct": change,
            "generated_by": "HardwareOS rule engine. Natural-language querying available via the AI service.",
        }


class SnapshotService(BaseService):
    """Materialise daily MetricSnapshot rows (idempotent upsert)."""

    def __init__(self, organization_id: UUID | str):
        self.organization_id = organization_id
        self.sales = SaleRepository(organization_id)
        self.expenses = ExpenseRepository(organization_id)
        self.stock = StockLevelRepository(organization_id)
        self.branches = BranchRepository(organization_id)
        from apps.analytics.repositories import MetricSnapshotRepository

        self.snapshots = MetricSnapshotRepository(organization_id)

    def compute_for_date(self, target_date) -> int:
        """Snapshot every branch + an org-wide rollup for target_date."""
        start, end = day_bounds(target_date)
        scopes: list[UUID | None] = [None] + [b.id for b in self.branches.active()]
        for branch_id in scopes:
            summary = self.sales.sales_summary(start, end, branch_id)
            opex_total = self.expenses.total(target_date, _next_day(target_date), branch_id)
            gross_profit = summary["gross_profit"]
            self.snapshots.upsert(
                branch_id=branch_id,
                snapshot_date=target_date,
                gross_sales=summary["gross_sales"],
                refunds=summary["refunds"],
                net_revenue=summary["net_revenue"],
                cogs=summary["cogs"],
                gross_profit=gross_profit,
                operating_expenses=opex_total,
                net_profit=gross_profit - opex_total,
                transactions=int(summary["transactions"]),
                inventory_value=self.stock.total_inventory_value(branch_id),
            )
        return len(scopes)


def _next_day(d):
    return d + timezone.timedelta(days=1)
