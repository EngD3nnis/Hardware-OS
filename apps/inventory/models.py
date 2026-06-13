"""Inventory domain: catalog (category/supplier/product) + per-branch stock."""
from __future__ import annotations

from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models

from core.models import TenantScopedModel

MONEY = dict(max_digits=14, decimal_places=2)
QTY = dict(max_digits=14, decimal_places=3)  # supports kg / metres / bags


class Category(TenantScopedModel):
    """Product category — self-referential tree (e.g. Building > Cement)."""

    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140)
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="children"
    )
    is_active = models.BooleanField(default=True)

    class Meta(TenantScopedModel.Meta):
        verbose_name_plural = "categories"
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "slug"],
                condition=models.Q(is_deleted=False),
                name="uniq_category_slug_per_org",
            )
        ]

    def __str__(self) -> str:
        return self.name


class Supplier(TenantScopedModel):
    name = models.CharField(max_length=180)
    contact_person = models.CharField(max_length=120, blank=True)
    phone = models.CharField(max_length=32, blank=True)
    email = models.EmailField(blank=True)
    address = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta(TenantScopedModel.Meta):
        indexes = [models.Index(fields=["organization", "name"])]

    def __str__(self) -> str:
        return self.name


class Product(TenantScopedModel):
    """A sellable / stockable item. Stock is tracked per branch in StockLevel."""

    sku = models.CharField(max_length=64)
    barcode = models.CharField(max_length=64, blank=True, db_index=True)  # barcode/QR ready
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    category = models.ForeignKey(
        Category, null=True, blank=True, on_delete=models.SET_NULL, related_name="products"
    )
    supplier = models.ForeignKey(
        Supplier, null=True, blank=True, on_delete=models.SET_NULL, related_name="products"
    )

    unit = models.CharField(max_length=20, default="pcs")  # pcs / kg / bag / m
    cost_price = models.DecimalField(**MONEY, validators=[MinValueValidator(Decimal("0"))])
    selling_price = models.DecimalField(**MONEY, validators=[MinValueValidator(Decimal("0"))])
    reorder_level = models.DecimalField(**QTY, default=Decimal("0"))

    is_active = models.BooleanField(default=True, db_index=True)

    class Meta(TenantScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "sku"],
                condition=models.Q(is_deleted=False),
                name="uniq_product_sku_per_org",
            )
        ]
        indexes = [
            models.Index(fields=["organization", "is_active"]),
            models.Index(fields=["organization", "category"]),
            models.Index(fields=["name"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} [{self.sku}]"

    @property
    def margin(self) -> Decimal:
        if not self.selling_price:
            return Decimal("0")
        return ((self.selling_price - self.cost_price) / self.selling_price) * 100


class StockLevel(TenantScopedModel):
    """Current on-hand quantity of a product at a branch."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="stock_levels")
    branch = models.ForeignKey("branches.Branch", on_delete=models.CASCADE, related_name="stock_levels")
    quantity = models.DecimalField(**QTY, default=Decimal("0"))

    class Meta(TenantScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["product", "branch"], name="uniq_stock_product_branch"
            )
        ]
        indexes = [models.Index(fields=["branch", "product"])]

    def __str__(self) -> str:
        return f"{self.product.sku} @ {self.branch.code}: {self.quantity}"

    @property
    def is_low(self) -> bool:
        return self.quantity <= self.product.reorder_level


class MovementType(models.TextChoices):
    PURCHASE = "purchase", "Purchase In"
    SALE = "sale", "Sale Out"
    TRANSFER_IN = "transfer_in", "Transfer In"
    TRANSFER_OUT = "transfer_out", "Transfer Out"
    ADJUSTMENT = "adjustment", "Adjustment"
    RETURN_IN = "return_in", "Customer Return In"
    RETURN_OUT = "return_out", "Supplier Return Out"


class StockMovement(TenantScopedModel):
    """
    Immutable ledger of every stock change. `quantity_delta` is signed
    (positive = in, negative = out); `balance_after` snapshots the running total.
    """

    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="movements")
    branch = models.ForeignKey("branches.Branch", on_delete=models.PROTECT, related_name="movements")
    movement_type = models.CharField(max_length=20, choices=MovementType.choices, db_index=True)
    quantity_delta = models.DecimalField(**QTY)
    balance_after = models.DecimalField(**QTY)
    unit_cost = models.DecimalField(**MONEY, null=True, blank=True)
    reference = models.CharField(max_length=64, blank=True, db_index=True)  # PO/sale/transfer id
    note = models.CharField(max_length=255, blank=True)

    class Meta(TenantScopedModel.Meta):
        indexes = [
            models.Index(fields=["organization", "product", "-created_at"]),
            models.Index(fields=["branch", "movement_type", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.movement_type} {self.quantity_delta} {self.product.sku}"
