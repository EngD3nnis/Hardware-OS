from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from django.db.models import F, Sum
from django.db.models.functions import Abs
from django.utils import timezone

from apps.inventory.models import (
    Category,
    Product,
    StockLevel,
    StockMovement,
    Supplier,
)
from core.repositories import TenantRepository


class CategoryRepository(TenantRepository[Category]):
    model = Category

    def __init__(self, organization_id):
        super().__init__(organization_id, Category)


class SupplierRepository(TenantRepository[Supplier]):
    model = Supplier

    def __init__(self, organization_id):
        super().__init__(organization_id, Supplier)


class ProductRepository(TenantRepository[Product]):
    model = Product

    def __init__(self, organization_id):
        super().__init__(organization_id, Product)

    def get_by_sku(self, sku: str) -> Product | None:
        return self.get_queryset().filter(sku=sku).first()

    def active(self):
        return self.get_queryset().filter(is_active=True).select_related("category", "supplier")


class StockLevelRepository(TenantRepository[StockLevel]):
    model = StockLevel

    def __init__(self, organization_id):
        super().__init__(organization_id, StockLevel)

    def get_or_create(self, *, product_id: UUID, branch_id: UUID) -> StockLevel:
        obj, _ = StockLevel.objects.get_or_create(
            organization_id=self.organization_id,
            product_id=product_id,
            branch_id=branch_id,
            defaults={"quantity": Decimal("0")},
        )
        return obj

    def for_branch(self, branch_id: UUID):
        return self.get_queryset().filter(branch_id=branch_id).select_related("product")

    def low_stock(self, branch_id: UUID | None = None):
        qs = self.get_queryset().select_related("product")
        if branch_id:
            qs = qs.filter(branch_id=branch_id)
        return qs.filter(quantity__lte=F("product__reorder_level"))

    def quantity_by_product(self, branch_id: UUID | None = None) -> list[dict]:
        """On-hand quantity per product (summed across branches if none given)."""
        qs = self.get_queryset()
        if branch_id:
            qs = qs.filter(branch_id=branch_id)
        rows = (
            qs.values("product_id", "product__sku", "product__name", "product__reorder_level")
            .annotate(quantity=Sum("quantity"))
            .order_by("product__name")
        )
        return [
            {
                "product_id": str(r["product_id"]),
                "sku": r["product__sku"],
                "name": r["product__name"],
                "reorder_level": r["product__reorder_level"],
                "quantity": r["quantity"],
            }
            for r in rows
        ]

    def total_inventory_value(self, branch_id: UUID | None = None) -> Decimal:
        """Sum(quantity * product.cost_price) — current stock valuation."""
        qs = self.get_queryset()
        if branch_id:
            qs = qs.filter(branch_id=branch_id)
        result = qs.aggregate(
            value=Sum(F("quantity") * F("product__cost_price"))
        )["value"]
        return result or Decimal("0")


class StockMovementRepository(TenantRepository[StockMovement]):
    model = StockMovement

    def __init__(self, organization_id):
        super().__init__(organization_id, StockMovement)

    def history(self, product_id: UUID):
        return self.get_queryset().filter(product_id=product_id)

    def fast_movers(self, start, end, branch_id: UUID | None = None, limit=5) -> list[dict]:
        """Top products by quantity sold in the window (SALE outflows)."""
        qs = self.get_queryset().filter(
            movement_type="sale", created_at__gte=start, created_at__lt=end
        )
        if branch_id:
            qs = qs.filter(branch_id=branch_id)
        rows = (
            qs.values("product_id", "product__name")
            .annotate(sold=Abs(Sum("quantity_delta")))
            .order_by("-sold")[:limit]
        )
        return [
            {"product_id": str(r["product_id"]), "name": r["product__name"], "sold": r["sold"]}
            for r in rows
        ]

    def sold_by_product(self, start, end, branch_id: UUID | None = None) -> dict:
        """Map product_id -> units sold in the window (for velocity/forecasting)."""
        qs = self.get_queryset().filter(
            movement_type="sale", created_at__gte=start, created_at__lt=end
        )
        if branch_id:
            qs = qs.filter(branch_id=branch_id)
        rows = qs.values("product_id").annotate(sold=Abs(Sum("quantity_delta")))
        return {str(r["product_id"]): r["sold"] for r in rows}


class DeadStockQuery:
    """Products holding stock that have not sold since a cutoff (capital tied up)."""

    def __init__(self, organization_id):
        self.organization_id = organization_id

    def run(self, days: int = 60, branch_id: UUID | None = None, limit: int = 50):
        cutoff = timezone.now() - timezone.timedelta(days=days)
        sold_recently = StockMovement.objects.filter(
            organization_id=self.organization_id, movement_type="sale", created_at__gte=cutoff
        )
        if branch_id:
            sold_recently = sold_recently.filter(branch_id=branch_id)
        recent_ids = sold_recently.values_list("product_id", flat=True).distinct()

        levels = (
            StockLevel.objects.filter(organization_id=self.organization_id, quantity__gt=0)
            .exclude(product_id__in=recent_ids)
            .select_related("product")
        )
        if branch_id:
            levels = levels.filter(branch_id=branch_id)
        return levels.annotate(value=F("quantity") * F("product__cost_price"))[:limit]
