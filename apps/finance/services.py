"""
Finance use-cases: expense management + the reporting engine.

FinanceReportService is the canonical P&L / cash-flow source the executive
dashboard (analytics phase) will consume. It combines POS revenue/COGS (already
net of returns) with operating expenses.
"""
from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from django.db import transaction

from apps.finance.models import Expense
from apps.finance.repositories import ExpenseCategoryRepository, ExpenseRepository
from apps.pos.repositories import SaleRepository
from core.audit.context import get_context
from core.audit.services import AuditAction
from core.services import BaseService

ZERO = Decimal("0")


def _actor():
    user = get_context().user
    return user if user and user.is_authenticated else None


class FinanceService(BaseService):
    """Expense + category mutations (all audited as FINANCIAL)."""

    def __init__(self, organization_id: UUID | str):
        self.organization_id = organization_id
        self.expenses = ExpenseRepository(organization_id)
        self.categories = ExpenseCategoryRepository(organization_id)

    @transaction.atomic
    def create_expense(self, **data) -> Expense:
        expense = self.expenses.create(recorded_by=_actor(), created_by=_actor(), updated_by=_actor(), **data)
        self.record_audit(
            action=AuditAction.FINANCIAL, entity=expense, entity_type="Expense",
            changes={"amount": str(expense.amount)}, branch_id=str(expense.branch_id),
        )
        return expense

    @transaction.atomic
    def update_expense(self, expense_id, **data) -> Expense:
        expense = self.expenses.get_by_id(expense_id)
        tracked = ["amount", "category_id", "description", "expense_date", "payment_method"]
        before = self.snapshot(expense, tracked)
        data["updated_by"] = _actor()
        expense = self.expenses.update(expense, **data)
        changes = self.diff_fields(before, self.snapshot(expense, tracked))
        if changes:
            self.record_audit(
                action=AuditAction.FINANCIAL, entity=expense, entity_type="Expense",
                changes=changes, branch_id=str(expense.branch_id),
            )
        return expense

    @transaction.atomic
    def delete_expense(self, expense_id) -> None:
        expense = self.expenses.get_by_id(expense_id)
        self.expenses.delete(expense)
        self.record_audit(
            action=AuditAction.FINANCIAL, entity=expense, entity_type="Expense",
            metadata={"action": "delete"}, branch_id=str(expense.branch_id),
        )


class FinanceReportService(BaseService):
    """Read-only financial reporting (P&L, cash flow, expense breakdown)."""

    def __init__(self, organization_id: UUID | str):
        self.organization_id = organization_id
        self.sales = SaleRepository(organization_id)
        self.expenses = ExpenseRepository(organization_id)

    def profit_and_loss(self, start, end, branch_id: UUID | None = None) -> dict:
        sales = self.sales.sales_summary(start, end, branch_id)
        opex = self.expenses.total(start.date(), end.date(), branch_id)
        gross_profit = sales["gross_profit"]
        net_profit = gross_profit - opex
        net_revenue = sales["net_revenue"]
        return {
            "net_revenue": net_revenue,
            "cogs": sales["cogs"],
            "gross_profit": gross_profit,
            "gross_margin": round(sales["gross_margin"], 2),
            "operating_expenses": opex,
            "expenses_by_category": self.expenses.by_category(start.date(), end.date(), branch_id),
            "net_profit": net_profit,
            "net_margin": round((net_profit / net_revenue * 100), 2) if net_revenue else ZERO,
            "transactions": sales["transactions"],
            "refunds": sales["refunds"],
        }

    def cash_flow(self, start, end, branch_id: UUID | None = None) -> dict:
        inflows = self.sales.cash_inflows_by_method(start, end, branch_id)
        sales = self.sales.sales_summary(start, end, branch_id)
        expense_out = self.expenses.by_method(start.date(), end.date(), branch_id)

        total_in = sum(inflows.values(), ZERO)
        total_expense_out = sum(expense_out.values(), ZERO)
        refunds = sales["refunds"]
        total_out = total_expense_out + refunds
        return {
            "inflows": inflows,
            "total_inflows": total_in,
            "outflows": {"expenses": expense_out, "refunds": refunds},
            "total_outflows": total_out,
            "net_cash_flow": total_in - total_out,
        }
