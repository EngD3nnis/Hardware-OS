"""
Finance domain: operating expenses.

Revenue, COGS and gross profit are derived from the POS module (sales are the
single source of revenue truth). Finance owns the *expense* side and combines
both into P&L and cash-flow reports — see services.FinanceReportService.
"""
from __future__ import annotations

from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models

from core.models import TenantScopedModel

MONEY = dict(max_digits=14, decimal_places=2)
ZERO = Decimal("0")


class ExpenseCategory(TenantScopedModel):
    """e.g. Rent, Salaries, Utilities, Transport, Marketing."""

    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140)
    is_active = models.BooleanField(default=True)

    class Meta(TenantScopedModel.Meta):
        verbose_name_plural = "expense categories"
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "slug"],
                condition=models.Q(is_deleted=False),
                name="uniq_expensecategory_slug_per_org",
            )
        ]

    def __str__(self) -> str:
        return self.name


class PaymentMethod(models.TextChoices):
    CASH = "cash", "Cash"
    MPESA = "mpesa", "M-Pesa"
    BANK = "bank", "Bank Transfer"
    CARD = "card", "Card"


class Expense(TenantScopedModel):
    branch = models.ForeignKey("branches.Branch", on_delete=models.PROTECT, related_name="expenses")
    category = models.ForeignKey(
        ExpenseCategory, null=True, blank=True, on_delete=models.SET_NULL, related_name="expenses"
    )
    amount = models.DecimalField(**MONEY, validators=[MinValueValidator(Decimal("0.01"))])
    description = models.CharField(max_length=255, blank=True)
    expense_date = models.DateField(db_index=True)
    payment_method = models.CharField(max_length=12, choices=PaymentMethod.choices, default=PaymentMethod.CASH)
    reference = models.CharField(max_length=64, blank=True)
    recorded_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="recorded_expenses"
    )

    class Meta(TenantScopedModel.Meta):
        indexes = [
            models.Index(fields=["organization", "branch", "-expense_date"]),
            models.Index(fields=["organization", "category"]),
        ]

    def __str__(self) -> str:
        return f"{self.description or self.category} — {self.amount}"
