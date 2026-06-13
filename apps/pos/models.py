"""
Point-of-sale domain.

A Sale is the source document for both the invoice and the receipt. Completing
a sale decrements stock through the inventory ledger (StockService), so on-hand
quantities, the immutable StockMovement trail, and the audit log stay in lockstep
with revenue. Returns add stock back the same way.
"""
from __future__ import annotations

from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models

from core.models import TenantScopedModel

MONEY = dict(max_digits=14, decimal_places=2)
QTY = dict(max_digits=14, decimal_places=3)
ZERO = Decimal("0")


class Customer(TenantScopedModel):
    """Optional customer attached to sales — powers purchase history."""

    name = models.CharField(max_length=180)
    phone = models.CharField(max_length=32, blank=True, db_index=True)
    email = models.EmailField(blank=True)
    address = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta(TenantScopedModel.Meta):
        indexes = [models.Index(fields=["organization", "name"])]

    def __str__(self) -> str:
        return self.name


class PaymentMethod(models.TextChoices):
    CASH = "cash", "Cash"
    MPESA = "mpesa", "M-Pesa"
    CARD = "card", "Card"
    BANK = "bank", "Bank Transfer"
    CREDIT = "credit", "On Credit"


class SaleStatus(models.TextChoices):
    COMPLETED = "completed", "Completed"
    VOIDED = "voided", "Voided"
    PARTIALLY_REFUNDED = "partially_refunded", "Partially Refunded"
    REFUNDED = "refunded", "Refunded"


class Sale(TenantScopedModel):
    number = models.CharField(max_length=32, db_index=True)  # e.g. SALE-HQ-000123
    branch = models.ForeignKey("branches.Branch", on_delete=models.PROTECT, related_name="sales")
    cashier = models.ForeignKey(
        "accounts.User", null=True, on_delete=models.SET_NULL, related_name="sales"
    )
    customer = models.ForeignKey(
        Customer, null=True, blank=True, on_delete=models.SET_NULL, related_name="sales"
    )

    status = models.CharField(
        max_length=20, choices=SaleStatus.choices, default=SaleStatus.COMPLETED, db_index=True
    )
    payment_method = models.CharField(max_length=12, choices=PaymentMethod.choices, default=PaymentMethod.CASH)

    # Monetary breakdown (all derived from lines + sale-level adjustments).
    subtotal = models.DecimalField(**MONEY, default=ZERO)
    discount_total = models.DecimalField(**MONEY, default=ZERO)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=ZERO)  # percent
    tax_total = models.DecimalField(**MONEY, default=ZERO)
    total = models.DecimalField(**MONEY, default=ZERO)
    cost_total = models.DecimalField(**MONEY, default=ZERO)        # COGS snapshot
    amount_paid = models.DecimalField(**MONEY, default=ZERO)
    change_due = models.DecimalField(**MONEY, default=ZERO)
    refunded_total = models.DecimalField(**MONEY, default=ZERO)

    note = models.CharField(max_length=255, blank=True)
    idempotency_key = models.CharField(max_length=64, blank=True)  # dedupe double-submit
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta(TenantScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "number"], name="uniq_sale_number_per_org"
            ),
            models.UniqueConstraint(
                fields=["organization", "idempotency_key"],
                condition=~models.Q(idempotency_key=""),
                name="uniq_sale_idempotency_per_org",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "branch", "-created_at"]),
            models.Index(fields=["status", "-created_at"]),
        ]

    def __str__(self) -> str:
        return self.number

    @property
    def gross_profit(self) -> Decimal:
        return self.total - self.tax_total - self.cost_total

    @property
    def balance_due(self) -> Decimal:
        return max(self.total - self.amount_paid, ZERO)


class SaleLine(TenantScopedModel):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey("inventory.Product", on_delete=models.PROTECT, related_name="sale_lines")
    description = models.CharField(max_length=200, blank=True)  # snapshot of product name
    quantity = models.DecimalField(**QTY, validators=[MinValueValidator(Decimal("0.001"))])
    unit_price = models.DecimalField(**MONEY)
    unit_cost = models.DecimalField(**MONEY, default=ZERO)  # cost snapshot for COGS/profit
    discount = models.DecimalField(**MONEY, default=ZERO)
    line_total = models.DecimalField(**MONEY, default=ZERO)
    refunded_quantity = models.DecimalField(**QTY, default=ZERO)

    class Meta(TenantScopedModel.Meta):
        indexes = [models.Index(fields=["sale"])]

    def __str__(self) -> str:
        return f"{self.description} x{self.quantity}"

    @property
    def returnable_quantity(self) -> Decimal:
        return self.quantity - self.refunded_quantity


class SaleReturn(TenantScopedModel):
    """A return/refund against a completed sale."""

    number = models.CharField(max_length=32, db_index=True)
    sale = models.ForeignKey(Sale, on_delete=models.PROTECT, related_name="returns")
    branch = models.ForeignKey("branches.Branch", on_delete=models.PROTECT, related_name="sale_returns")
    processed_by = models.ForeignKey(
        "accounts.User", null=True, on_delete=models.SET_NULL, related_name="processed_returns"
    )
    reason = models.CharField(max_length=255, blank=True)
    refund_total = models.DecimalField(**MONEY, default=ZERO)
    restock = models.BooleanField(default=True)  # whether returned items re-enter stock

    class Meta(TenantScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "number"], name="uniq_return_number_per_org"
            )
        ]

    def __str__(self) -> str:
        return self.number


class SaleReturnLine(TenantScopedModel):
    sale_return = models.ForeignKey(SaleReturn, on_delete=models.CASCADE, related_name="lines")
    sale_line = models.ForeignKey(SaleLine, on_delete=models.PROTECT, related_name="return_lines")
    quantity = models.DecimalField(**QTY)
    refund_amount = models.DecimalField(**MONEY, default=ZERO)   # gross (tax-inclusive)
    net_amount = models.DecimalField(**MONEY, default=ZERO)       # pre-tax revenue reversed
    cost_amount = models.DecimalField(**MONEY, default=ZERO)      # COGS reversed (qty * unit_cost)


class DocumentCounter(models.Model):
    """
    Per-(org, branch, doc_type) monotonic counter for human-friendly,
    gap-free document numbers. Incremented under SELECT FOR UPDATE.
    """

    organization_id = models.UUIDField(db_index=True)
    branch_code = models.CharField(max_length=20, default="")
    doc_type = models.CharField(max_length=20)  # "sale" | "return"
    last_number = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization_id", "branch_code", "doc_type"],
                name="uniq_counter_scope",
            )
        ]
