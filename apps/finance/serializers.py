from __future__ import annotations

from rest_framework import serializers

from apps.finance.models import Expense, ExpenseCategory


class ExpenseCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ExpenseCategory
        fields = ("id", "name", "slug", "is_active", "created_at")
        read_only_fields = ("id", "created_at")


class ExpenseSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    branch_code = serializers.CharField(source="branch.code", read_only=True)
    recorded_by_name = serializers.CharField(source="recorded_by.full_name", read_only=True)

    class Meta:
        model = Expense
        fields = (
            "id", "branch", "branch_code", "category", "category_name", "amount",
            "description", "expense_date", "payment_method", "reference",
            "recorded_by", "recorded_by_name", "created_at",
        )
        read_only_fields = ("id", "created_at", "recorded_by")


class ExpenseWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Expense
        fields = ("branch", "category", "amount", "description", "expense_date", "payment_method", "reference")
