"""Stock ledger invariants — the most safety-critical part of inventory."""
from decimal import Decimal

import pytest

from apps.branches.models import Branch, Organization
from apps.inventory.models import MovementType, Product, StockMovement
from apps.inventory.services import StockService
from core.exceptions import InsufficientStockError

pytestmark = pytest.mark.django_db


@pytest.fixture
def org():
    return Organization.objects.create(name="Acme", slug="acme")


@pytest.fixture
def branch(org):
    return Branch.objects.create(organization=org, name="HQ", code="HQ")


@pytest.fixture
def branch_b(org):
    return Branch.objects.create(organization=org, name="Westlands", code="WL")


@pytest.fixture
def product(org):
    return Product.objects.create(
        organization=org, sku="CEM-50", name="Cement 50kg",
        cost_price=Decimal("650"), selling_price=Decimal("780"),
        reorder_level=Decimal("20"),
    )


def test_purchase_increases_stock_and_writes_ledger(org, branch, product):
    svc = StockService(org.id)
    mv = svc.apply_movement(
        product_id=product.id, branch_id=branch.id,
        movement_type=MovementType.PURCHASE, quantity=Decimal("100"),
    )
    assert mv.balance_after == Decimal("100.000")
    assert StockMovement.objects.count() == 1
    assert product.stock_levels.get(branch=branch).quantity == Decimal("100.000")


def test_sale_decrements_stock(org, branch, product):
    svc = StockService(org.id)
    svc.apply_movement(
        product_id=product.id, branch_id=branch.id,
        movement_type=MovementType.PURCHASE, quantity=Decimal("100"),
    )
    svc.apply_movement(
        product_id=product.id, branch_id=branch.id,
        movement_type=MovementType.SALE, quantity=Decimal("30"),
    )
    assert product.stock_levels.get(branch=branch).quantity == Decimal("70.000")


def test_oversell_raises_and_does_not_mutate(org, branch, product):
    svc = StockService(org.id)
    svc.apply_movement(
        product_id=product.id, branch_id=branch.id,
        movement_type=MovementType.PURCHASE, quantity=Decimal("10"),
    )
    with pytest.raises(InsufficientStockError):
        svc.apply_movement(
            product_id=product.id, branch_id=branch.id,
            movement_type=MovementType.SALE, quantity=Decimal("11"),
        )
    assert product.stock_levels.get(branch=branch).quantity == Decimal("10.000")


def test_transfer_moves_stock_between_branches(org, branch, branch_b, product):
    svc = StockService(org.id)
    svc.apply_movement(
        product_id=product.id, branch_id=branch.id,
        movement_type=MovementType.PURCHASE, quantity=Decimal("50"),
    )
    svc.transfer(
        product_id=product.id, from_branch_id=branch.id,
        to_branch_id=branch_b.id, quantity=Decimal("20"),
    )
    assert product.stock_levels.get(branch=branch).quantity == Decimal("30.000")
    assert product.stock_levels.get(branch=branch_b).quantity == Decimal("20.000")
