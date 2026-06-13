"""Finance reporting: P&L nets returns, expenses cut net profit, cash flow nets out."""
from datetime import date
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.branches.models import Branch, Organization
from apps.finance.models import Expense, ExpenseCategory
from apps.finance.services import FinanceReportService, FinanceService
from apps.inventory.models import MovementType, Product
from apps.inventory.services import StockService
from apps.pos.services import ReturnService, SaleService

pytestmark = pytest.mark.django_db


@pytest.fixture
def org():
    return Organization.objects.create(name="Acme", slug="acme")


@pytest.fixture
def branch(org):
    return Branch.objects.create(organization=org, name="HQ", code="HQ")


@pytest.fixture
def product(org):
    return Product.objects.create(
        organization=org, sku="CEM-50", name="Cement 50kg",
        cost_price=Decimal("650"), selling_price=Decimal("780"), reorder_level=Decimal("20"),
    )


@pytest.fixture
def stocked(org, branch, product):
    StockService(org.id).apply_movement(
        product_id=product.id, branch_id=branch.id,
        movement_type=MovementType.PURCHASE, quantity=Decimal("100"),
    )
    return product


def _window():
    today = timezone.localdate()
    start = timezone.make_aware(timezone.datetime.combine(today, timezone.datetime.min.time()))
    end = start + timezone.timedelta(days=1)
    return start, end


def test_pnl_revenue_cogs_and_gross_profit(org, branch, stocked):
    # 10 bags @ 780, cost 650, no tax → revenue 7800, cogs 6500, gp 1300
    SaleService(org.id).create_sale(branch_id=branch.id, lines=[{"product": stocked.id, "quantity": Decimal("10")}])
    start, end = _window()
    pnl = FinanceReportService(org.id).profit_and_loss(start, end, branch.id)
    assert pnl["net_revenue"] == Decimal("7800.00")
    assert pnl["cogs"] == Decimal("6500.00")
    assert pnl["gross_profit"] == Decimal("1300.00")
    assert pnl["operating_expenses"] == Decimal("0")
    assert pnl["net_profit"] == Decimal("1300.00")


def test_pnl_nets_out_returns_for_revenue_and_cogs(org, branch, stocked):
    sale = SaleService(org.id).create_sale(
        branch_id=branch.id, lines=[{"product": stocked.id, "quantity": Decimal("10")}]
    )
    ReturnService(org.id).process_return(
        sale_id=sale.id, lines=[{"sale_line": sale.lines.first().id, "quantity": Decimal("4")}]
    )
    start, end = _window()
    pnl = FinanceReportService(org.id).profit_and_loss(start, end, branch.id)
    # 6 bags net: revenue 4680, cogs 3900, gp 780 — returns fully netted, not approximate
    assert pnl["net_revenue"] == Decimal("4680.00")
    assert pnl["cogs"] == Decimal("3900.00")
    assert pnl["gross_profit"] == Decimal("780.00")
    assert pnl["refunds"] == Decimal("3120.00")


def test_expenses_reduce_net_profit(org, branch, stocked):
    SaleService(org.id).create_sale(branch_id=branch.id, lines=[{"product": stocked.id, "quantity": Decimal("10")}])
    cat = ExpenseCategory.objects.create(organization=org, name="Rent", slug="rent")
    FinanceService(org.id).create_expense(
        branch=branch, category=cat, amount=Decimal("500"),
        description="Daily rent", expense_date=date.today(),
    )
    start, end = _window()
    pnl = FinanceReportService(org.id).profit_and_loss(start, end, branch.id)
    assert pnl["operating_expenses"] == Decimal("500.00")
    assert pnl["net_profit"] == Decimal("800.00")           # 1300 gross - 500 opex
    assert pnl["expenses_by_category"][0]["category"] == "Rent"


def test_cash_flow_inflows_minus_outflows(org, branch, stocked):
    SaleService(org.id).create_sale(
        branch_id=branch.id, payment_method="cash",
        lines=[{"product": stocked.id, "quantity": Decimal("10")}], amount_paid=Decimal("7800"),
    )
    cat = ExpenseCategory.objects.create(organization=org, name="Transport", slug="transport")
    FinanceService(org.id).create_expense(
        branch=branch, category=cat, amount=Decimal("300"),
        expense_date=date.today(), payment_method="cash",
    )
    start, end = _window()
    cf = FinanceReportService(org.id).cash_flow(start, end, branch.id)
    assert cf["total_inflows"] == Decimal("7800.00")
    assert cf["total_outflows"] == Decimal("300.00")
    assert cf["net_cash_flow"] == Decimal("7500.00")
