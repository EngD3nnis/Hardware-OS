from django.contrib import admin

from apps.pos.models import (
    Customer,
    DocumentCounter,
    Sale,
    SaleLine,
    SaleReturn,
    SaleReturnLine,
)


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "email", "is_active")
    search_fields = ("name", "phone", "email")


class SaleLineInline(admin.TabularInline):
    model = SaleLine
    extra = 0
    readonly_fields = [f.name for f in SaleLine._meta.fields]
    can_delete = False


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ("number", "branch", "status", "total", "payment_method", "created_at")
    list_filter = ("status", "payment_method", "branch")
    search_fields = ("number", "customer__name")
    date_hierarchy = "created_at"
    inlines = [SaleLineInline]
    readonly_fields = [f.name for f in Sale._meta.fields]


class SaleReturnLineInline(admin.TabularInline):
    model = SaleReturnLine
    extra = 0


@admin.register(SaleReturn)
class SaleReturnAdmin(admin.ModelAdmin):
    list_display = ("number", "sale", "branch", "refund_total", "created_at")
    search_fields = ("number", "sale__number")
    inlines = [SaleReturnLineInline]


@admin.register(DocumentCounter)
class DocumentCounterAdmin(admin.ModelAdmin):
    list_display = ("organization_id", "branch_code", "doc_type", "last_number")
