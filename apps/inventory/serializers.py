from __future__ import annotations

from rest_framework import serializers

from apps.inventory.models import (
    Category,
    Product,
    StockLevel,
    StockMovement,
    Supplier,
)


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ("id", "name", "slug", "parent", "is_active", "created_at")
        read_only_fields = ("id", "created_at")


class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = ("id", "name", "contact_person", "phone", "email", "address", "is_active")
        read_only_fields = ("id",)


class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    margin = serializers.DecimalField(max_digits=6, decimal_places=2, read_only=True)

    class Meta:
        model = Product
        fields = (
            "id", "sku", "barcode", "name", "description", "category", "category_name",
            "supplier", "unit", "cost_price", "selling_price", "margin",
            "reorder_level", "is_active", "created_at",
        )
        read_only_fields = ("id", "created_at", "margin")


class ProductWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = (
            "sku", "barcode", "name", "description", "category", "supplier",
            "unit", "cost_price", "selling_price", "reorder_level", "is_active",
        )


class StockLevelSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    sku = serializers.CharField(source="product.sku", read_only=True)
    branch_code = serializers.CharField(source="branch.code", read_only=True)
    is_low = serializers.BooleanField(read_only=True)

    class Meta:
        model = StockLevel
        fields = ("id", "product", "product_name", "sku", "branch", "branch_code", "quantity", "is_low")


class StockMovementSerializer(serializers.ModelSerializer):
    sku = serializers.CharField(source="product.sku", read_only=True)

    class Meta:
        model = StockMovement
        fields = (
            "id", "product", "sku", "branch", "movement_type", "quantity_delta",
            "balance_after", "unit_cost", "reference", "note", "created_at",
        )


# --- action payloads -------------------------------------------------------- #
class MovementInputSerializer(serializers.Serializer):
    product = serializers.UUIDField()
    branch = serializers.UUIDField()
    movement_type = serializers.ChoiceField(choices=StockMovement._meta.get_field("movement_type").choices)
    quantity = serializers.DecimalField(max_digits=14, decimal_places=3, min_value=0)
    unit_cost = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, allow_null=True)
    reference = serializers.CharField(required=False, allow_blank=True)
    note = serializers.CharField(required=False, allow_blank=True)


class TransferInputSerializer(serializers.Serializer):
    product = serializers.UUIDField()
    from_branch = serializers.UUIDField()
    to_branch = serializers.UUIDField()
    quantity = serializers.DecimalField(max_digits=14, decimal_places=3, min_value=0)
    reference = serializers.CharField(required=False, allow_blank=True)


class AdjustInputSerializer(serializers.Serializer):
    product = serializers.UUIDField()
    branch = serializers.UUIDField()
    quantity = serializers.DecimalField(max_digits=14, decimal_places=3)  # signed
    note = serializers.CharField(required=False, allow_blank=True)
