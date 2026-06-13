from django.contrib import admin

from apps.inventory.models import (
    Category,
    Product,
    StockLevel,
    StockMovement,
    Supplier,
)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "parent", "organization", "is_active")
    search_fields = ("name",)


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ("name", "contact_person", "phone", "is_active")
    search_fields = ("name",)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("sku", "name", "category", "cost_price", "selling_price", "is_active")
    list_filter = ("is_active", "category")
    search_fields = ("sku", "name", "barcode")


@admin.register(StockLevel)
class StockLevelAdmin(admin.ModelAdmin):
    list_display = ("product", "branch", "quantity")
    list_filter = ("branch",)
    search_fields = ("product__sku", "product__name")


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ("created_at", "movement_type", "product", "branch", "quantity_delta", "balance_after")
    list_filter = ("movement_type", "branch")
    search_fields = ("product__sku", "reference")
    readonly_fields = [f.name for f in StockMovement._meta.fields]
