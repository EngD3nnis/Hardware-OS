from __future__ import annotations

from rest_framework import serializers

from apps.pos.models import (
    Customer,
    PaymentMethod,
    Sale,
    SaleLine,
    SaleReturn,
    SaleReturnLine,
)


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = ("id", "name", "phone", "email", "address", "is_active", "created_at")
        read_only_fields = ("id", "created_at")


class SaleLineSerializer(serializers.ModelSerializer):
    sku = serializers.CharField(source="product.sku", read_only=True)
    returnable_quantity = serializers.DecimalField(max_digits=14, decimal_places=3, read_only=True)

    class Meta:
        model = SaleLine
        fields = (
            "id", "product", "sku", "description", "quantity", "unit_price",
            "unit_cost", "discount", "line_total", "refunded_quantity", "returnable_quantity",
        )


class SaleSerializer(serializers.ModelSerializer):
    lines = SaleLineSerializer(many=True, read_only=True)
    cashier_name = serializers.CharField(source="cashier.full_name", read_only=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    gross_profit = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    balance_due = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = Sale
        fields = (
            "id", "number", "branch", "cashier", "cashier_name", "customer", "customer_name",
            "status", "payment_method", "subtotal", "discount_total", "tax_rate", "tax_total",
            "total", "cost_total", "gross_profit", "amount_paid", "change_due", "balance_due",
            "refunded_total", "note", "completed_at", "created_at", "lines",
        )


# --- write payloads --------------------------------------------------------- #
class SaleLineInputSerializer(serializers.Serializer):
    product = serializers.UUIDField()
    quantity = serializers.DecimalField(max_digits=14, decimal_places=3, min_value=0)
    unit_price = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, allow_null=True)
    discount = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, allow_null=True)


class SaleCreateSerializer(serializers.Serializer):
    branch = serializers.UUIDField()
    customer = serializers.UUIDField(required=False, allow_null=True)
    payment_method = serializers.ChoiceField(choices=PaymentMethod.choices, default=PaymentMethod.CASH)
    tax_rate = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, default=0)
    amount_paid = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, allow_null=True)
    note = serializers.CharField(required=False, allow_blank=True)
    idempotency_key = serializers.CharField(required=False, allow_blank=True, max_length=64)
    lines = SaleLineInputSerializer(many=True)


class ReturnLineInputSerializer(serializers.Serializer):
    sale_line = serializers.UUIDField()
    quantity = serializers.DecimalField(max_digits=14, decimal_places=3, min_value=0)


class ReturnCreateSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True)
    restock = serializers.BooleanField(default=True)
    lines = ReturnLineInputSerializer(many=True)


class SaleReturnLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = SaleReturnLine
        fields = ("id", "sale_line", "quantity", "refund_amount")


class SaleReturnSerializer(serializers.ModelSerializer):
    lines = SaleReturnLineSerializer(many=True, read_only=True)

    class Meta:
        model = SaleReturn
        fields = (
            "id", "number", "sale", "branch", "processed_by", "reason",
            "refund_total", "restock", "created_at", "lines",
        )
