"""
Inventory use-cases.

ProductService handles catalog mutations with explicit **price-change** audit
events. StockService is the only path that mutates quantities: it locks the
stock row, writes an immutable StockMovement, and audits the change. Every
quantity change in the system flows through `apply_movement`.
"""
from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from django.db import transaction

from apps.inventory.models import MovementType, Product, StockLevel, StockMovement
from apps.inventory.repositories import (
    ProductRepository,
    StockLevelRepository,
    StockMovementRepository,
)
from core.audit.context import get_context
from core.audit.services import AuditAction
from core.exceptions import ConflictError, InsufficientStockError, ValidationError
from core.services import BaseService

# Movement types that decrease stock.
_OUTFLOWS = {MovementType.SALE, MovementType.TRANSFER_OUT, MovementType.RETURN_OUT}
_PRODUCT_TRACKED = ["name", "cost_price", "selling_price", "reorder_level", "category_id", "is_active"]


class ProductService(BaseService):
    def __init__(self, organization_id: UUID | str):
        self.organization_id = organization_id
        self.repo = ProductRepository(organization_id)

    @transaction.atomic
    def create_product(self, **data) -> Product:
        if self.repo.get_by_sku(data["sku"]):
            raise ConflictError(f"SKU '{data['sku']}' already exists.")
        actor = _actor()
        product = self.repo.create(created_by=actor, updated_by=actor, **data)
        self.record_audit(action=AuditAction.CREATE, entity=product)
        return product

    @transaction.atomic
    def update_product(self, product_id: UUID | str, **data) -> Product:
        product = self.repo.get_by_id(product_id)
        before = self.snapshot(product, _PRODUCT_TRACKED)
        data["updated_by"] = _actor()
        product = self.repo.update(product, **data)
        after = self.snapshot(product, _PRODUCT_TRACKED)
        changes = self.diff_fields(before, after)

        if changes:
            # Price changes get a dedicated, separately-queryable audit action.
            price_changed = {"cost_price", "selling_price"} & set(changes)
            self.record_audit(
                action=AuditAction.PRICE_CHANGE if price_changed else AuditAction.UPDATE,
                entity=product,
                changes=changes,
            )
        return product

    @transaction.atomic
    def delete_product(self, product_id: UUID | str) -> None:
        product = self.repo.get_by_id(product_id)
        self.repo.delete(product)
        self.record_audit(action=AuditAction.DELETE, entity=product)


class StockService(BaseService):
    """All quantity mutations funnel through here for a consistent ledger."""

    def __init__(self, organization_id: UUID | str):
        self.organization_id = organization_id
        self.levels = StockLevelRepository(organization_id)
        self.movements = StockMovementRepository(organization_id)

    @transaction.atomic
    def apply_movement(
        self,
        *,
        product_id: UUID | str,
        branch_id: UUID | str,
        movement_type: str,
        quantity: Decimal,
        unit_cost: Decimal | None = None,
        reference: str = "",
        note: str = "",
    ) -> StockMovement:
        """
        Atomically adjust on-hand stock and record an immutable movement.

        `quantity` is always positive; direction is derived from movement_type.
        Raises InsufficientStockError if an outflow would go negative.
        """
        quantity = Decimal(quantity)
        if quantity <= 0:
            raise ValidationError("Quantity must be positive.")

        # Lock the stock row to serialise concurrent sales/transfers.
        level = (
            StockLevel.objects.select_for_update()
            .filter(
                organization_id=self.organization_id,
                product_id=product_id,
                branch_id=branch_id,
            )
            .first()
        )
        if level is None:
            level = self.levels.get_or_create(product_id=product_id, branch_id=branch_id)
            level = StockLevel.objects.select_for_update().get(pk=level.pk)

        delta = -quantity if movement_type in _OUTFLOWS else quantity
        new_balance = level.quantity + delta
        if new_balance < 0:
            raise InsufficientStockError(
                f"Only {level.quantity} available; tried to remove {quantity}."
            )

        level.quantity = new_balance
        level.save(update_fields=["quantity", "updated_at"])

        movement = StockMovement.objects.create(
            organization_id=self.organization_id,
            product_id=product_id,
            branch_id=branch_id,
            movement_type=movement_type,
            quantity_delta=delta,
            balance_after=new_balance,
            unit_cost=unit_cost,
            reference=reference,
            note=note,
            created_by=_actor(),
        )
        self.record_audit(
            action=AuditAction.STOCK_CHANGE,
            entity=movement,
            entity_type="StockLevel",
            entity_id=str(level.pk),
            changes={"quantity": {"old": str(level.quantity - delta), "new": str(new_balance)}},
            metadata={"movement_type": movement_type, "reference": reference},
            branch_id=str(branch_id),
        )
        return movement

    @transaction.atomic
    def transfer(
        self,
        *,
        product_id: UUID | str,
        from_branch_id: UUID | str,
        to_branch_id: UUID | str,
        quantity: Decimal,
        reference: str = "",
    ) -> tuple[StockMovement, StockMovement]:
        if from_branch_id == to_branch_id:
            raise ValidationError("Source and destination branches must differ.")
        out = self.apply_movement(
            product_id=product_id, branch_id=from_branch_id,
            movement_type=MovementType.TRANSFER_OUT, quantity=quantity, reference=reference,
        )
        into = self.apply_movement(
            product_id=product_id, branch_id=to_branch_id,
            movement_type=MovementType.TRANSFER_IN, quantity=quantity, reference=reference,
        )
        return out, into

    def adjust(
        self, *, product_id, branch_id, quantity: Decimal, note: str = ""
    ) -> StockMovement:
        """Manual correction (stock count). Positive adds, negative removes."""
        quantity = Decimal(quantity)
        mtype = MovementType.ADJUSTMENT
        if quantity < 0:
            # apply_movement expects positive qty; route negatives as outflow.
            return self.apply_movement(
                product_id=product_id, branch_id=branch_id,
                movement_type=MovementType.TRANSFER_OUT, quantity=abs(quantity),
                note=note or "manual adjustment (decrease)",
            )
        return self.apply_movement(
            product_id=product_id, branch_id=branch_id,
            movement_type=mtype, quantity=quantity, note=note or "manual adjustment",
        )


def _actor():
    user = get_context().user
    return user if user and user.is_authenticated else None
