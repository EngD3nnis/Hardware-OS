from __future__ import annotations

from rest_framework.decorators import action
from rest_framework.response import Response

from apps.analytics.services import DashboardService, InsightService
from apps.finance.periods import resolve_period
from apps.finance.services import FinanceReportService
from apps.inventory.repositories import (
    DeadStockQuery,
    StockLevelRepository,
    StockMovementRepository,
)
from apps.pos.repositories import SaleRepository
from core.rbac import Perm
from core.views import BaseViewSet


class DashboardViewSet(BaseViewSet):
    """
    The Executive Command Center.

    `overview` returns the full executive payload. The other actions return
    focused slices for drill-down screens. All accept an optional ?branch=<id>;
    revenue/inventory actions also accept ?period= / ?start=&end=.
    """

    permission_map = {
        "overview": Perm.DASHBOARD_VIEW,
        "revenue": Perm.ANALYTICS_VIEW,
        "inventory": Perm.ANALYTICS_VIEW,
        "branches": Perm.ANALYTICS_VIEW,
        "employees": Perm.ANALYTICS_VIEW,
        "insights": Perm.ANALYTICS_VIEW,
    }

    def _branch(self, request):
        return request.query_params.get("branch")

    @action(detail=False, methods=["get"])
    def overview(self, request):
        data = DashboardService(self.organization_id).executive_overview(self._branch(request))
        return Response(data)

    @action(detail=False, methods=["get"])
    def revenue(self, request):
        start, end, label = resolve_period(request.query_params)
        branch = self._branch(request)
        pnl = FinanceReportService(self.organization_id).profit_and_loss(start, end, branch)
        sales = SaleRepository(self.organization_id)
        return Response(
            {
                "period": label,
                "branch": branch,
                "summary": pnl,
                "top_products": sales.top_products(start, end, branch, limit=10),
                "daily_net_revenue": [
                    {"date": d, "amount": v}
                    for d, v in sorted(sales.daily_net_sales(start, end, branch).items())
                ],
            }
        )

    @action(detail=False, methods=["get"])
    def inventory(self, request):
        start, end, label = resolve_period(request.query_params)
        branch = self._branch(request)
        stock = StockLevelRepository(self.organization_id)
        dead = list(DeadStockQuery(self.organization_id).run(branch_id=branch, limit=50))
        return Response(
            {
                "period": label,
                "branch": branch,
                "stock_value": stock.total_inventory_value(branch),
                "low_stock": [
                    {"sku": lvl.product.sku, "name": lvl.product.name,
                     "quantity": lvl.quantity, "reorder_level": lvl.product.reorder_level}
                    for lvl in stock.low_stock(branch).select_related("product")[:50]
                ],
                "dead_stock": [
                    {"sku": lvl.product.sku, "name": lvl.product.name,
                     "quantity": lvl.quantity, "value": lvl.value}
                    for lvl in dead
                ],
                "fast_movers": StockMovementRepository(self.organization_id).fast_movers(
                    start, end, branch, limit=10
                ),
            }
        )

    @action(detail=False, methods=["get"])
    def branches(self, request):
        ranking = DashboardService(self.organization_id)._branch_ranking()
        return Response({"ranking": ranking})

    @action(detail=False, methods=["get"])
    def employees(self, request):
        start, end, label = resolve_period(request.query_params)
        branch = self._branch(request)
        return Response(
            {
                "period": label,
                "top_performers": SaleRepository(self.organization_id).top_cashiers(
                    start, end, branch, limit=10
                ),
                "note": "Attendance & productivity require the Employees module (later phase).",
            }
        )

    @action(detail=False, methods=["get"])
    def insights(self, request):
        data = InsightService(self.organization_id).generate(self._branch(request))
        return Response(data)
