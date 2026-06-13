from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from django.db.models import Sum

from apps.finance.models import Expense, ExpenseCategory
from core.repositories import TenantRepository

ZERO = Decimal("0")


class ExpenseCategoryRepository(TenantRepository[ExpenseCategory]):
    model = ExpenseCategory

    def __init__(self, organization_id):
        super().__init__(organization_id, ExpenseCategory)


class ExpenseRepository(TenantRepository[Expense]):
    model = Expense

    def __init__(self, organization_id):
        super().__init__(organization_id, Expense)

    def in_period(self, start, end, branch_id: UUID | None = None):
        qs = self.get_queryset().filter(expense_date__gte=start, expense_date__lt=end)
        if branch_id:
            qs = qs.filter(branch_id=branch_id)
        return qs

    def total(self, start, end, branch_id: UUID | None = None) -> Decimal:
        agg = self.in_period(start, end, branch_id).aggregate(t=Sum("amount"))
        return agg["t"] or ZERO

    def by_category(self, start, end, branch_id: UUID | None = None) -> list[dict]:
        rows = (
            self.in_period(start, end, branch_id)
            .values("category__name")
            .annotate(amount=Sum("amount"))
            .order_by("-amount")
        )
        return [
            {"category": row["category__name"] or "Uncategorized", "amount": row["amount"] or ZERO}
            for row in rows
        ]

    def by_method(self, start, end, branch_id: UUID | None = None) -> dict:
        rows = self.in_period(start, end, branch_id).values("payment_method").annotate(amount=Sum("amount"))
        return {row["payment_method"]: (row["amount"] or ZERO) for row in rows}
