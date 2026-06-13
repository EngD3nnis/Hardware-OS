from django.contrib import admin

from apps.branches.models import Branch, Organization


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "currency", "is_active")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "organization", "city", "manager", "is_active")
    list_filter = ("is_active", "organization")
    search_fields = ("name", "code", "city")
