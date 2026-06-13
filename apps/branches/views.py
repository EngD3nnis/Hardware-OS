from __future__ import annotations

from rest_framework.decorators import action
from rest_framework.response import Response

from apps.branches.models import Branch
from apps.branches.repositories import BranchRepository
from apps.branches.serializers import BranchSerializer, BranchWriteSerializer
from apps.branches.services import BranchService
from core.rbac import Perm
from core.views import BaseModelViewSet


class BranchViewSet(BaseModelViewSet):
    """CRUD + analytics for branches, scoped to the caller's organization."""

    serializer_class = BranchSerializer
    filterset_fields = ("is_active", "city")
    search_fields = ("name", "code", "city")
    ordering_fields = ("name", "created_at")
    permission_map = {
        "list": Perm.BRANCH_VIEW,
        "retrieve": Perm.BRANCH_VIEW,
        "analytics": Perm.BRANCH_VIEW,
        "create": Perm.BRANCH_MANAGE,
        "update": Perm.BRANCH_MANAGE,
        "partial_update": Perm.BRANCH_MANAGE,
        "destroy": Perm.BRANCH_MANAGE,
    }

    def get_queryset(self):
        return BranchRepository(self.organization_id).all()

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return BranchWriteSerializer
        return BranchSerializer

    def _service(self) -> BranchService:
        return BranchService(self.organization_id)

    def create(self, request, *args, **kwargs):
        data = BranchWriteSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        branch = self._service().create_branch(**data.validated_data)
        return Response(BranchSerializer(branch).data, status=201)

    def update(self, request, *args, **kwargs):
        data = BranchWriteSerializer(data=request.data, partial=kwargs.get("partial", False))
        data.is_valid(raise_exception=True)
        branch = self._service().update_branch(kwargs["pk"], **data.validated_data)
        return Response(BranchSerializer(branch).data)

    def destroy(self, request, *args, **kwargs):
        self._service().delete_branch(kwargs["pk"])
        return Response(status=204)

    @action(detail=True, methods=["get"])
    def analytics(self, request, pk=None):
        """
        Placeholder branch analytics shape. Real figures arrive with the
        finance/analytics phase (revenue, profit, inventory value per branch).
        """
        branch: Branch = self.get_object()
        return Response(
            {
                "branch": BranchSerializer(branch).data,
                "metrics": {
                    "revenue_today": None,
                    "revenue_month": None,
                    "gross_profit_month": None,
                    "inventory_value": None,
                    "staff_count": branch.staff.count(),
                    "note": "Populated in the analytics phase.",
                },
            }
        )
