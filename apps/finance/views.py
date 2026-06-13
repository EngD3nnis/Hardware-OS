from __future__ import annotations

from rest_framework.decorators import action
from rest_framework.response import Response

from apps.finance.periods import resolve_period
from apps.finance.repositories import ExpenseCategoryRepository, ExpenseRepository
from apps.finance.serializers import (
    ExpenseCategorySerializer,
    ExpenseSerializer,
    ExpenseWriteSerializer,
)
from apps.finance.services import FinanceReportService, FinanceService
from core.rbac import Perm
from core.views import BaseModelViewSet, BaseViewSet


class ExpenseCategoryViewSet(BaseModelViewSet):
    serializer_class = ExpenseCategorySerializer
    search_fields = ("name",)
    permission_map = {
        "list": Perm.FINANCE_VIEW, "retrieve": Perm.FINANCE_VIEW,
        "create": Perm.FINANCE_MANAGE, "update": Perm.FINANCE_MANAGE,
        "partial_update": Perm.FINANCE_MANAGE, "destroy": Perm.FINANCE_MANAGE,
    }

    def get_queryset(self):
        return ExpenseCategoryRepository(self.organization_id).all()

    def perform_create(self, serializer):
        serializer.save(organization_id=self.organization_id)


class ExpenseViewSet(BaseModelViewSet):
    serializer_class = ExpenseSerializer
    filterset_fields = ("branch", "category", "payment_method")
    search_fields = ("description", "reference")
    ordering_fields = ("expense_date", "amount")
    permission_map = {
        "list": Perm.FINANCE_VIEW, "retrieve": Perm.FINANCE_VIEW,
        "create": Perm.FINANCE_MANAGE, "update": Perm.FINANCE_MANAGE,
        "partial_update": Perm.FINANCE_MANAGE, "destroy": Perm.FINANCE_MANAGE,
    }

    def get_queryset(self):
        return ExpenseRepository(self.organization_id).all().select_related("branch", "category")

    def _service(self):
        return FinanceService(self.organization_id)

    def create(self, request, *args, **kwargs):
        data = ExpenseWriteSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        expense = self._service().create_expense(**data.validated_data)
        return Response(ExpenseSerializer(expense).data, status=201)

    def update(self, request, *args, **kwargs):
        data = ExpenseWriteSerializer(data=request.data, partial=kwargs.get("partial", False))
        data.is_valid(raise_exception=True)
        expense = self._service().update_expense(kwargs["pk"], **data.validated_data)
        return Response(ExpenseSerializer(expense).data)

    def destroy(self, request, *args, **kwargs):
        self._service().delete_expense(kwargs["pk"])
        return Response(status=204)


class FinanceReportViewSet(BaseViewSet):
    """
    Read-only financial reports. All accept ?period= or ?start=&end= and an
    optional ?branch= filter.
    """

    permission_map = {
        "pnl": Perm.FINANCE_VIEW,
        "cash_flow": Perm.FINANCE_VIEW,
        "expenses_summary": Perm.FINANCE_VIEW,
    }

    def _period_branch(self, request):
        start, end, label = resolve_period(request.query_params)
        return start, end, label, request.query_params.get("branch")

    @action(detail=False, methods=["get"], url_path="pnl")
    def pnl(self, request):
        start, end, label, branch = self._period_branch(request)
        data = FinanceReportService(self.organization_id).profit_and_loss(start, end, branch)
        return Response({"period": label, "branch": branch, **data})

    @action(detail=False, methods=["get"], url_path="cash-flow")
    def cash_flow(self, request):
        start, end, label, branch = self._period_branch(request)
        data = FinanceReportService(self.organization_id).cash_flow(start, end, branch)
        return Response({"period": label, "branch": branch, **data})

    @action(detail=False, methods=["get"], url_path="expenses-summary")
    def expenses_summary(self, request):
        start, end, label, branch = self._period_branch(request)
        repo = ExpenseRepository(self.organization_id)
        return Response(
            {
                "period": label,
                "branch": branch,
                "total": repo.total(start.date(), end.date(), branch),
                "by_category": repo.by_category(start.date(), end.date(), branch),
                "by_method": repo.by_method(start.date(), end.date(), branch),
            }
        )
