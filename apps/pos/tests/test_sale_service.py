"""POS revenue path: sales move stock, refunds restock, money math holds."""
from decimal import Decimal

import pytest

from apps.branches.models import Branch, Organization
from apps.inventory.models import MovementType, Product
from apps.inventory.services import StockService
from apps.pos.models import Sale, SaleStatus
from apps.pos.services import ReturnService, SaleService
from core.exceptions import InsufficientStockError, ValidationError

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


def _line(product, qty, price=None):
    line = {"product": product.id, "quantity": Decimal(qty)}
    if price is not None:
        line["unit_price"] = Decimal(price)
    return line


def test_sale_prices_basket_and_decrements_stock(org, branch, stocked):
    sale = SaleService(org.id).create_sale(
        branch_id=branch.id, lines=[_line(stocked, "10")], amount_paid=Decimal("8000"),
    )
    assert sale.status == SaleStatus.COMPLETED
    assert sale.subtotal == Decimal("7800.00")          # 10 * 780
    assert sale.total == Decimal("7800.00")
    assert sale.cost_total == Decimal("6500.00")         # 10 * 650
    assert sale.gross_profit == Decimal("1300.00")
    assert sale.change_due == Decimal("200.00")
    assert stocked.stock_levels.get(branch=branch).quantity == Decimal("90.000")
    assert sale.number.startswith("SALE-HQ-")


def test_sale_applies_tax_and_line_discount(org, branch, stocked):
    sale = SaleService(org.id).create_sale(
        branch_id=branch.id, tax_rate=Decimal("16"),
        lines=[{"product": stocked.id, "quantity": Decimal("2"), "discount": Decimal("100")}],
    )
    # subtotal 1560 - 100 discount = 1460 net; +16% tax = 1693.60
    assert sale.subtotal == Decimal("1560.00")
    assert sale.discount_total == Decimal("100.00")
    assert sale.tax_total == Decimal("233.60")
    assert sale.total == Decimal("1693.60")


def test_oversell_rolls_back_entire_sale(org, branch, stocked):
    with pytest.raises(InsufficientStockError):
        SaleService(org.id).create_sale(branch_id=branch.id, lines=[_line(stocked, "200")])
    assert Sale.objects.count() == 0  # no orphaned sale
    assert stocked.stock_levels.get(branch=branch).quantity == Decimal("100.000")


def test_idempotency_key_prevents_duplicate(org, branch, stocked):
    svc = SaleService(org.id)
    s1 = svc.create_sale(branch_id=branch.id, lines=[_line(stocked, "5")], idempotency_key="abc-123")
    s2 = svc.create_sale(branch_id=branch.id, lines=[_line(stocked, "5")], idempotency_key="abc-123")
    assert s1.id == s2.id
    assert Sale.objects.count() == 1
    assert stocked.stock_levels.get(branch=branch).quantity == Decimal("95.000")


def test_refund_restocks_and_updates_status(org, branch, stocked):
    sale = SaleService(org.id).create_sale(branch_id=branch.id, lines=[_line(stocked, "10")])
    line = sale.lines.first()

    sret = ReturnService(org.id).process_return(
        sale_id=sale.id, lines=[{"sale_line": line.id, "quantity": Decimal("4")}],
    )
    sale.refresh_from_db()
    line.refresh_from_db()
    assert sret.refund_total == Decimal("3120.00")        # 4 * 780
    assert line.refunded_quantity == Decimal("4.000")
    assert sale.status == SaleStatus.PARTIALLY_REFUNDED
    assert stocked.stock_levels.get(branch=branch).quantity == Decimal("94.000")  # 90 + 4


def test_cannot_return_more_than_sold(org, branch, stocked):
    sale = SaleService(org.id).create_sale(branch_id=branch.id, lines=[_line(stocked, "3")])
    line = sale.lines.first()
    with pytest.raises(ValidationError):
        ReturnService(org.id).process_return(
            sale_id=sale.id, lines=[{"sale_line": line.id, "quantity": Decimal("5")}],
        )


def test_full_refund_marks_sale_refunded(org, branch, stocked):
    sale = SaleService(org.id).create_sale(branch_id=branch.id, lines=[_line(stocked, "2")])
    line = sale.lines.first()
    ReturnService(org.id).process_return(
        sale_id=sale.id, lines=[{"sale_line": line.id, "quantity": Decimal("2")}],
    )
    sale.refresh_from_db()
    assert sale.status == SaleStatus.REFUNDED
