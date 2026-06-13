from __future__ import annotations

from rest_framework.decorators import action
from rest_framework.response import Response

from apps.pos.models import Sale
from apps.pos.repositories import CustomerRepository, SaleRepository
from apps.pos.serializers import (
    CustomerSerializer,
    ReturnCreateSerializer,
    SaleCreateSerializer,
    SaleReturnSerializer,
    SaleSerializer,
)
from apps.pos.services import CustomerService, ReturnService, SaleService
from core.rbac import Perm
from core.views import BaseModelViewSet


class CustomerViewSet(BaseModelViewSet):
    serializer_class = CustomerSerializer
    search_fields = ("name", "phone", "email")
    permission_map = {
        "list": Perm.CUSTOMER_VIEW, "retrieve": Perm.CUSTOMER_VIEW, "history": Perm.SALE_VIEW,
        "create": Perm.CUSTOMER_MANAGE, "update": Perm.CUSTOMER_MANAGE,
        "partial_update": Perm.CUSTOMER_MANAGE, "destroy": Perm.CUSTOMER_MANAGE,
    }

    def get_queryset(self):
        return CustomerRepository(self.organization_id).all()

    def _service(self):
        return CustomerService(self.organization_id)

    def create(self, request, *args, **kwargs):
        data = CustomerSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        customer = self._service().create(**data.validated_data)
        return Response(CustomerSerializer(customer).data, status=201)

    def update(self, request, *args, **kwargs):
        data = CustomerSerializer(data=request.data, partial=kwargs.get("partial", False))
        data.is_valid(raise_exception=True)
        customer = self._service().update(kwargs["pk"], **data.validated_data)
        return Response(CustomerSerializer(customer).data)

    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        """Purchase history for a customer."""
        qs = SaleRepository(self.organization_id).for_customer(pk)
        page = self.paginate_queryset(qs)
        return self.get_paginated_response(SaleSerializer(page, many=True).data)


class SaleViewSet(BaseModelViewSet):
    serializer_class = SaleSerializer
    http_method_names = ["get", "post", "head", "options"]  # sales are immutable once made
    filterset_fields = ("branch", "status", "payment_method", "customer")
    search_fields = ("number", "note")
    ordering_fields = ("created_at", "total")
    permission_map = {
        "list": Perm.SALE_VIEW, "retrieve": Perm.SALE_VIEW, "receipt": Perm.SALE_VIEW,
        "create": Perm.SALE_CREATE, "refund": Perm.SALE_REFUND, "void": Perm.SALE_VOID,
    }

    def get_queryset(self):
        return SaleRepository(self.organization_id).detailed()

    def create(self, request, *args, **kwargs):
        data = SaleCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        sale = SaleService(self.organization_id).create_sale(
            branch_id=v["branch"],
            lines=[dict(line) for line in v["lines"]],
            customer_id=v.get("customer"),
            payment_method=v["payment_method"],
            tax_rate=v.get("tax_rate") or 0,
            amount_paid=v.get("amount_paid"),
            note=v.get("note", ""),
            idempotency_key=v.get("idempotency_key", ""),
        )
        return Response(SaleSerializer(sale).data, status=201)

    @action(detail=True, methods=["post"])
    def refund(self, request, pk=None):
        data = ReturnCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        sale_return = ReturnService(self.organization_id).process_return(
            sale_id=pk,
            lines=[dict(line) for line in v["lines"]],
            reason=v.get("reason", ""),
            restock=v["restock"],
        )
        return Response(SaleReturnSerializer(sale_return).data, status=201)

    @action(detail=True, methods=["post"])
    def void(self, request, pk=None):
        sale = SaleService(self.organization_id).void_sale(pk, reason=request.data.get("reason", ""))
        return Response(SaleSerializer(sale).data)

    @action(detail=True, methods=["get"])
    def receipt(self, request, pk=None):
        """Formatted receipt/invoice payload for printing."""
        sale: Sale = self.get_object()
        org = request.user.organization
        return Response(
            {
                "document": "RECEIPT",
                "organization": {"name": getattr(org, "name", ""), "currency": getattr(org, "currency", "")},
                "branch": {"name": sale.branch.name, "code": sale.branch.code, "phone": sale.branch.phone},
                "number": sale.number,
                "date": sale.completed_at,
                "cashier": getattr(sale.cashier, "full_name", ""),
                "customer": getattr(sale.customer, "name", ""),
                "items": [
                    {
                        "description": line.description,
                        "quantity": line.quantity,
                        "unit_price": line.unit_price,
                        "discount": line.discount,
                        "line_total": line.line_total,
                    }
                    for line in sale.lines.all()
                ],
                "totals": {
                    "subtotal": sale.subtotal,
                    "discount": sale.discount_total,
                    "tax": sale.tax_total,
                    "total": sale.total,
                    "paid": sale.amount_paid,
                    "change": sale.change_due,
                },
                "status": sale.status,
            }
        )
