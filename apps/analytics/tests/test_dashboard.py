"""Executive dashboard assembly, insights, and snapshot rollups."""
from datetime import date
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.analytics.models import MetricSnapshot
from apps.analytics.services import DashboardService, InsightService, SnapshotService
from apps.branches.models import Branch, Organization
from apps.finance.models import ExpenseCategory
from apps.finance.services import FinanceService
from apps.inventory.models import MovementType, Product
from apps.inventory.services import StockService
from apps.pos.services import SaleService

pytestmark = pytest.mark.django_db


@pytest.fixture
def org():
    return Organization.objects.create(name="Acme", slug="acme")


@pytest.fixture
def hq(org):
    return Branch.objects.create(organization=org, name="HQ", code="HQ")


@pytest.fixture
def west(org):
    return Branch.objects.create(organization=org, name="Westlands", code="WL")


@pytest.fixture
def product(org):
    return Product.objects.create(
        organization=org, sku="CEM-50", name="Cement 50kg",
        cost_price=Decimal("650"), selling_price=Decimal("780"), reorder_level=Decimal("20"),
    )


def _stock_and_sell(org, branch, product, purchase, sell):
    StockService(org.id).apply_movement(
        product_id=product.id, branch_id=branch.id,
        movement_type=MovementType.PURCHASE, quantity=Decimal(purchase),
    )
    if sell:
        SaleService(org.id).create_sale(
            branch_id=branch.id, lines=[{"product": product.id, "quantity": Decimal(sell)}]
        )


def test_overview_has_all_executive_blocks(org, hq, product):
    _stock_and_sell(org, hq, product, "100", "10")
    data = DashboardService(org.id).executive_overview()
    for key in ("revenue", "profit", "inventory", "branches", "employees", "finance", "trend", "ai_insights"):
        assert key in data
    assert set(data["revenue"]) == {"today", "yesterday", "week", "month", "year"}
    assert data["revenue"]["today"] == Decimal("7800.00")
    assert data["profit"]["gross_profit"] == Decimal("1300.00")
    assert data["inventory"]["stock_value"] == Decimal("58500.00")  # 90 * 650 after selling 10
    assert data["inventory"]["low_stock_count"] == 0


def test_branch_ranking_orders_by_revenue(org, hq, west, product):
    _stock_and_sell(org, hq, product, "100", "10")     # HQ sells more
    _stock_and_sell(org, west, product, "100", "3")
    ranking = DashboardService(org.id).executive_overview()["branches"]["ranking"]
    assert [r["code"] for r in ranking] == ["HQ", "WL"]
    assert ranking[0]["rank"] == 1
    assert ranking[0]["net_revenue"] > ranking[1]["net_revenue"]


def test_finance_block_reflects_expenses_and_receivables(org, hq, product):
    StockService(org.id).apply_movement(
        product_id=product.id, branch_id=hq.id, movement_type=MovementType.PURCHASE, quantity=Decimal("100")
    )
    # credit sale -> outstanding receivable
    SaleService(org.id).create_sale(
        branch_id=hq.id, payment_method="credit", amount_paid=Decimal("0"),
        lines=[{"product": product.id, "quantity": Decimal("5")}],
    )
    cat = ExpenseCategory.objects.create(organization=org, name="Rent", slug="rent")
    FinanceService(org.id).create_expense(branch=hq, category=cat, amount=Decimal("400"), expense_date=date.today())

    fin = DashboardService(org.id).executive_overview()["finance"]
    assert fin["expenses_month"] == Decimal("400.00")
    assert fin["outstanding_payments"] == Decimal("3900.00")  # 5 * 780 unpaid


def test_insights_detect_revenue_growth(org, hq, product):
    _stock_and_sell(org, hq, product, "100", "10")
    insights = InsightService(org.id).generate()
    assert "items" in insights and insights["items"]
    assert insights["revenue_change_pct"] >= 0
    assert any("Revenue" in line for line in insights["items"])


def test_snapshot_rollup_persists_daily_metrics(org, hq, product):
    _stock_and_sell(org, hq, product, "100", "10")
    scopes = SnapshotService(org.id).compute_for_date(date.today())
    assert scopes == 2  # org-wide + HQ
    org_snap = MetricSnapshot.objects.get(organization=org, branch__isnull=True, snapshot_date=date.today())
    assert org_snap.net_revenue == Decimal("7800.00")
    assert org_snap.gross_profit == Decimal("1300.00")
    assert org_snap.transactions == 1
    # re-running is idempotent (upsert), not duplicated
    SnapshotService(org.id).compute_for_date(date.today())
    assert MetricSnapshot.objects.filter(organization=org, snapshot_date=date.today()).count() == 2
