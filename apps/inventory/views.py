from __future__ import annotations

from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone

from apps.inventory.repositories import (
    CategoryRepository,
    ProductRepository,
    StockLevelRepository,
    StockMovementRepository,
    SupplierRepository,
)
from apps.inventory.serializers import (
    AdjustInputSerializer,
    CategorySerializer,
    MovementInputSerializer,
    ProductSerializer,
    ProductWriteSerializer,
    StockLevelSerializer,
    StockMovementSerializer,
    SupplierSerializer,
    TransferInputSerializer,
)
from apps.inventory.services import ProductService, StockService
from core.rbac import Perm
from core.views import BaseModelViewSet, BaseViewSet


class CategoryViewSet(BaseModelViewSet):
    serializer_class = CategorySerializer
    search_fields = ("name",)
    permission_map = {
        "list": Perm.PRODUCT_VIEW, "retrieve": Perm.PRODUCT_VIEW,
        "create": Perm.PRODUCT_MANAGE, "update": Perm.PRODUCT_MANAGE,
        "partial_update": Perm.PRODUCT_MANAGE, "destroy": Perm.PRODUCT_MANAGE,
    }

    def get_queryset(self):
        return CategoryRepository(self.organization_id).all()

    def perform_create(self, serializer):
        serializer.save(organization_id=self.organization_id)


class SupplierViewSet(BaseModelViewSet):
    serializer_class = SupplierSerializer
    search_fields = ("name", "contact_person")
    permission_map = {
        "list": Perm.PRODUCT_VIEW, "retrieve": Perm.PRODUCT_VIEW,
        "create": Perm.SUPPLIER_MANAGE, "update": Perm.SUPPLIER_MANAGE,
        "partial_update": Perm.SUPPLIER_MANAGE, "destroy": Perm.SUPPLIER_MANAGE,
    }

    def get_queryset(self):
        return SupplierRepository(self.organization_id).all()

    def perform_create(self, serializer):
        serializer.save(organization_id=self.organization_id)


class ProductViewSet(BaseModelViewSet):
    serializer_class = ProductSerializer
    filterset_fields = ("category", "supplier", "is_active")
    search_fields = ("name", "sku", "barcode")
    ordering_fields = ("name", "selling_price", "created_at")
    permission_map = {
        "list": Perm.PRODUCT_VIEW, "retrieve": Perm.PRODUCT_VIEW,
        "create": Perm.PRODUCT_MANAGE, "update": Perm.PRODUCT_MANAGE,
        "partial_update": Perm.PRODUCT_MANAGE, "destroy": Perm.PRODUCT_MANAGE,
        "movements": Perm.STOCK_VIEW,
    }

    def get_queryset(self):
        return ProductRepository(self.organization_id).active()

    def _service(self):
        return ProductService(self.organization_id)

    def create(self, request, *args, **kwargs):
        data = ProductWriteSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        product = self._service().create_product(**data.validated_data)
        return Response(ProductSerializer(product).data, status=201)

    def update(self, request, *args, **kwargs):
        data = ProductWriteSerializer(data=request.data, partial=kwargs.get("partial", False))
        data.is_valid(raise_exception=True)
        product = self._service().update_product(kwargs["pk"], **data.validated_data)
        return Response(ProductSerializer(product).data)

    def destroy(self, request, *args, **kwargs):
        self._service().delete_product(kwargs["pk"])
        return Response(status=204)

    @action(detail=True, methods=["get"])
    def movements(self, request, pk=None):
        qs = StockMovementRepository(self.organization_id).history(pk)
        page = self.paginate_queryset(qs)
        return self.get_paginated_response(StockMovementSerializer(page, many=True).data)


class StockViewSet(BaseViewSet):
    """Stock levels + the movement/transfer/adjust operations."""

    permission_map = {
        "list": Perm.STOCK_VIEW, "low_stock": Perm.STOCK_VIEW, "value": Perm.STOCK_VIEW,
        "forecast_feed": Perm.STOCK_VIEW,
        "movement": Perm.STOCK_ADJUST, "adjust": Perm.STOCK_ADJUST, "transfer": Perm.STOCK_TRANSFER,
    }

    def _stock_service(self):
        return StockService(self.organization_id)

    def list(self, request):
        repo = StockLevelRepository(self.organization_id)
        branch = request.query_params.get("branch")
        qs = repo.for_branch(branch) if branch else repo.all().select_related("product", "branch")
        return Response(StockLevelSerializer(qs, many=True).data)

    @action(detail=False, methods=["get"], url_path="low-stock")
    def low_stock(self, request):
        repo = StockLevelRepository(self.organization_id)
        qs = repo.low_stock(request.query_params.get("branch"))
        return Response(StockLevelSerializer(qs, many=True).data)

    @action(detail=False, methods=["get"])
    def value(self, request):
        repo = StockLevelRepository(self.organization_id)
        total = repo.total_inventory_value(request.query_params.get("branch"))
        return Response({"inventory_value": total})

    @action(detail=False, methods=["get"], url_path="forecast-feed")
    def forecast_feed(self, request):
        """
        Per-product on-hand quantity + sales velocity over the last N days.
        Consumed by the AI service for stock-out prediction & demand forecasting.
        """
        days = max(int(request.query_params.get("days", 30) or 30), 1)
        branch = request.query_params.get("branch")
        end = timezone.now()
        start = end - timezone.timedelta(days=days)

        levels = StockLevelRepository(self.organization_id).quantity_by_product(branch)
        sold = StockMovementRepository(self.organization_id).sold_by_product(start, end, branch)

        items = []
        for lvl in levels:
            units_sold = sold.get(lvl["product_id"], 0)
            items.append(
                {
                    "product_id": lvl["product_id"],
                    "sku": lvl["sku"],
                    "name": lvl["name"],
                    "quantity": lvl["quantity"],
                    "reorder_level": lvl["reorder_level"],
                    "sold_last_n_days": units_sold,
                    "period_days": days,
                    "avg_daily_sales": (float(units_sold) / days),
                }
            )
        return Response({"period_days": days, "branch": branch, "items": items})

    @action(detail=False, methods=["post"])
    def movement(self, request):
        data = MovementInputSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        mv = self._stock_service().apply_movement(
            product_id=v["product"], branch_id=v["branch"],
            movement_type=v["movement_type"], quantity=v["quantity"],
            unit_cost=v.get("unit_cost"), reference=v.get("reference", ""), note=v.get("note", ""),
        )
        return Response(StockMovementSerializer(mv).data, status=201)

    @action(detail=False, methods=["post"])
    def transfer(self, request):
        data = TransferInputSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        out, into = self._stock_service().transfer(
            product_id=v["product"], from_branch_id=v["from_branch"],
            to_branch_id=v["to_branch"], quantity=v["quantity"], reference=v.get("reference", ""),
        )
        return Response(
            {"out": StockMovementSerializer(out).data, "in": StockMovementSerializer(into).data},
            status=201,
        )

    @action(detail=False, methods=["post"])
    def adjust(self, request):
        data = AdjustInputSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        mv = self._stock_service().adjust(
            product_id=v["product"], branch_id=v["branch"],
            quantity=v["quantity"], note=v.get("note", ""),
        )
        return Response(StockMovementSerializer(mv).data, status=201)
