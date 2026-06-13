from django.contrib import admin

from apps.finance.models import Expense, ExpenseCategory


@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "organization", "is_active")
    search_fields = ("name",)


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ("expense_date", "branch", "category", "amount", "payment_method", "recorded_by")
    list_filter = ("payment_method", "branch", "category")
    search_fields = ("description", "reference")
    date_hierarchy = "expense_date"
