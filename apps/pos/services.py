"""
POS use-cases.

`SaleService.create_sale` is the revenue entry point: it prices the basket,
snapshots COGS, allocates a gap-free document number, persists the sale, and
moves stock out through the inventory ledger — all in one transaction, so a
stock shortfall rolls the whole sale back. `ReturnService.process_return`
reverses it: stock back in, refund recorded, sale status updated.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.inventory.models import MovementType
from apps.inventory.repositories import ProductRepository
from apps.inventory.services import StockService
from apps.pos.models import (
    Customer,
    DocumentCounter,
    Sale,
    SaleLine,
    SaleReturn,
    SaleReturnLine,
    SaleStatus,
)
from apps.pos.repositories import CustomerRepository, SaleRepository
from core.audit.context import get_context
from core.audit.services import AuditAction
from core.exceptions import ConflictError, NotFoundError, ValidationError
from core.services import BaseService

CENTS = Decimal("0.01")
ZERO = Decimal("0")


def _money(value) -> Decimal:
    return Decimal(value).quantize(CENTS, rounding=ROUND_HALF_UP)


def _actor():
    user = get_context().user
    return user if user and user.is_authenticated else None


def next_document_number(org_id, *, branch_code: str, doc_type: str, prefix: str) -> str:
    """Allocate the next monotonic number for a document scope (locked)."""
    counter, _ = DocumentCounter.objects.select_for_update().get_or_create(
        organization_id=org_id, branch_code=branch_code, doc_type=doc_type
    )
    counter.last_number += 1
    counter.save(update_fields=["last_number"])
    return f"{prefix}-{branch_code}-{counter.last_number:06d}"


class SaleService(BaseService):
    def __init__(self, organization_id: UUID | str):
        self.organization_id = organization_id
        self.sales = SaleRepository(organization_id)
        self.products = ProductRepository(organization_id)
        self.stock = StockService(organization_id)

    @transaction.atomic
    def create_sale(
        self,
        *,
        branch_id: UUID | str,
        lines: list[dict],
        customer_id: UUID | str | None = None,
        payment_method: str = "cash",
        tax_rate: Decimal | str = ZERO,
        amount_paid: Decimal | str | None = None,
        note: str = "",
        idempotency_key: str = "",
    ) -> Sale:
        # Idempotency — a retried submit returns the original sale, not a dupe.
        existing = self.sales.by_idempotency_key(idempotency_key)
        if existing:
            return existing

        if not lines:
            raise ValidationError("A sale must have at least one line.")

        branch = self._branch(branch_id)
        tax_rate = Decimal(tax_rate or 0)

        priced: list[dict] = []
        subtotal = ZERO
        discount_total = ZERO
        cost_total = ZERO
        for raw in lines:
            product = self.products.get_by_id(raw["product"])
            if not product.is_active:
                raise ValidationError(f"Product {product.sku} is not active.")
            qty = Decimal(raw["quantity"])
            if qty <= 0:
                raise ValidationError("Line quantity must be positive.")
            unit_price = _money(raw.get("unit_price") or product.selling_price)
            discount = _money(raw.get("discount") or 0)
            gross = _money(unit_price * qty)
            line_total = _money(gross - discount)
            if line_total < 0:
                raise ValidationError("Line discount cannot exceed the line total.")
            unit_cost = _money(product.cost_price)

            subtotal += gross
            discount_total += discount
            cost_total += _money(unit_cost * qty)
            priced.append(
                {
                    "product": product, "qty": qty, "unit_price": unit_price,
                    "discount": discount, "line_total": line_total, "unit_cost": unit_cost,
                }
            )

        net = subtotal - discount_total
        tax_total = _money(net * tax_rate / Decimal("100"))
        total = _money(net + tax_total)
        amount_paid = _money(amount_paid if amount_paid is not None else total)
        change_due = _money(max(amount_paid - total, ZERO))

        sale = Sale.objects.create(
            organization_id=self.organization_id,
            number=next_document_number(
                self.organization_id, branch_code=branch.code, doc_type="sale", prefix="SALE"
            ),
            branch=branch,
            cashier=_actor(),
            customer_id=customer_id,
            status=SaleStatus.COMPLETED,
            payment_method=payment_method,
            subtotal=_money(subtotal),
            discount_total=_money(discount_total),
            tax_rate=tax_rate,
            tax_total=tax_total,
            total=total,
            cost_total=_money(cost_total),
            amount_paid=amount_paid,
            change_due=change_due,
            note=note,
            idempotency_key=idempotency_key,
            completed_at=timezone.now(),
            created_by=_actor(),
        )

        for p in priced:
            SaleLine.objects.create(
                organization_id=self.organization_id,
                sale=sale, product=p["product"], description=p["product"].name,
                quantity=p["qty"], unit_price=p["unit_price"], unit_cost=p["unit_cost"],
                discount=p["discount"], line_total=p["line_total"],
            )
            # Decrement stock via the ledger — raises InsufficientStockError to
            # roll back the entire sale if any line can't be fulfilled.
            self.stock.apply_movement(
                product_id=p["product"].id, branch_id=branch.id,
                movement_type=MovementType.SALE, quantity=p["qty"],
                unit_cost=p["unit_cost"], reference=sale.number,
            )

        self.record_audit(
            action=AuditAction.FINANCIAL, entity=sale, entity_type="Sale",
            changes={"total": str(total), "lines": len(priced)},
            metadata={"payment_method": payment_method, "number": sale.number},
            branch_id=str(branch.id),
        )
        return sale

    @transaction.atomic
    def void_sale(self, sale_id: UUID | str, reason: str = "") -> Sale:
        """Void a sale and return all its stock (no money handling here)."""
        sale = self._sale_for_update(sale_id)
        if sale.status != SaleStatus.COMPLETED:
            raise ConflictError("Only completed sales can be voided.")
        for line in sale.lines.all():
            if line.returnable_quantity > 0:
                self.stock.apply_movement(
                    product_id=line.product_id, branch_id=sale.branch_id,
                    movement_type=MovementType.RETURN_IN, quantity=line.returnable_quantity,
                    reference=sale.number, note="void",
                )
        sale.status = SaleStatus.VOIDED
        sale.save(update_fields=["status", "updated_at"])
        self.record_audit(
            action=AuditAction.REFUND, entity=sale, entity_type="Sale",
            metadata={"action": "void", "reason": reason}, branch_id=str(sale.branch_id),
        )
        return sale

    def _branch(self, branch_id):
        from apps.branches.repositories import BranchRepository

        return BranchRepository(self.organization_id).get_by_id(branch_id)

    def _sale_for_update(self, sale_id) -> Sale:
        sale = (
            Sale.objects.select_for_update()
            .filter(organization_id=self.organization_id, pk=sale_id)
            .first()
        )
        if sale is None:
            raise NotFoundError("Sale not found.")
        return sale


class ReturnService(BaseService):
    def __init__(self, organization_id: UUID | str):
        self.organization_id = organization_id
        self.stock = StockService(organization_id)

    @transaction.atomic
    def process_return(
        self,
        *,
        sale_id: UUID | str,
        lines: list[dict],
        reason: str = "",
        restock: bool = True,
    ) -> SaleReturn:
        sale = (
            Sale.objects.select_for_update()
            .filter(organization_id=self.organization_id, pk=sale_id)
            .first()
        )
        if sale is None:
            raise NotFoundError("Sale not found.")
        if sale.status == SaleStatus.VOIDED:
            raise ConflictError("Cannot return a voided sale.")
        if not lines:
            raise ValidationError("A return must have at least one line.")

        sale_return = SaleReturn.objects.create(
            organization_id=self.organization_id,
            number=next_document_number(
                self.organization_id, branch_code=sale.branch.code,
                doc_type="return", prefix="RET",
            ),
            sale=sale, branch=sale.branch, processed_by=_actor(),
            reason=reason, restock=restock, created_by=_actor(),
        )

        refund_total = ZERO
        tax_factor = (Decimal("1") + sale.tax_rate / Decimal("100"))
        for raw in lines:
            line = (
                SaleLine.objects.select_for_update()
                .filter(organization_id=self.organization_id, sale=sale, pk=raw["sale_line"])
                .first()
            )
            if line is None:
                raise NotFoundError("Sale line not found on this sale.")
            qty = Decimal(raw["quantity"])
            if qty <= 0:
                raise ValidationError("Return quantity must be positive.")
            if qty > line.returnable_quantity:
                raise ValidationError(
                    f"Only {line.returnable_quantity} of {line.description} can be returned."
                )

            per_unit_net = line.line_total / line.quantity
            net_amount = _money(per_unit_net * qty)
            refund_amount = _money(net_amount * tax_factor)
            cost_amount = _money(line.unit_cost * qty)
            refund_total += refund_amount

            SaleReturnLine.objects.create(
                organization_id=self.organization_id,
                sale_return=sale_return, sale_line=line,
                quantity=qty, refund_amount=refund_amount,
                net_amount=net_amount, cost_amount=cost_amount,
            )
            line.refunded_quantity += qty
            line.save(update_fields=["refunded_quantity", "updated_at"])

            if restock:
                self.stock.apply_movement(
                    product_id=line.product_id, branch_id=sale.branch_id,
                    movement_type=MovementType.RETURN_IN, quantity=qty,
                    reference=sale_return.number, note="customer return",
                )

        sale_return.refund_total = _money(refund_total)
        sale_return.save(update_fields=["refund_total", "updated_at"])

        sale.refunded_total = _money(sale.refunded_total + refund_total)
        fully = all(line.returnable_quantity == 0 for line in sale.lines.all())
        sale.status = SaleStatus.REFUNDED if fully else SaleStatus.PARTIALLY_REFUNDED
        sale.save(update_fields=["refunded_total", "status", "updated_at"])

        self.record_audit(
            action=AuditAction.REFUND, entity=sale_return, entity_type="SaleReturn",
            changes={"refund_total": str(refund_total)},
            metadata={"sale": sale.number, "return": sale_return.number},
            branch_id=str(sale.branch_id),
        )
        return sale_return


class CustomerService(BaseService):
    def __init__(self, organization_id: UUID | str):
        self.organization_id = organization_id
        self.repo = CustomerRepository(organization_id)

    @transaction.atomic
    def create(self, **data) -> Customer:
        customer = self.repo.create(created_by=_actor(), updated_by=_actor(), **data)
        self.record_audit(action=AuditAction.CREATE, entity=customer)
        return customer

    @transaction.atomic
    def update(self, customer_id, **data) -> Customer:
        customer = self.repo.get_by_id(customer_id)
        before = self.snapshot(customer, list(data.keys()))
        data["updated_by"] = _actor()
        customer = self.repo.update(customer, **data)
        changes = self.diff_fields(before, self.snapshot(customer, [k for k in data if k != "updated_by"]))
        if changes:
            self.record_audit(action=AuditAction.UPDATE, entity=customer, changes=changes)
        return customer
