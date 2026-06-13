from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from apps.accounts.models import LoginEvent, Role, User


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "level", "is_system")
    search_fields = ("name", "slug")


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ("email",)
    list_display = ("email", "full_name", "organization", "branch", "is_active", "mfa_enabled")
    list_filter = ("is_active", "is_staff", "roles")
    search_fields = ("email", "first_name", "last_name")
    filter_horizontal = ("roles", "groups", "user_permissions")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Profile", {"fields": ("first_name", "last_name", "phone")}),
        ("Tenancy", {"fields": ("organization", "branch", "roles")}),
        ("Security", {"fields": ("mfa_enabled", "is_active", "is_staff", "is_superuser")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "password1", "password2")}),
    )


@admin.register(LoginEvent)
class LoginEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "email_attempted", "successful", "ip_address")
    list_filter = ("successful",)
    readonly_fields = [f.name for f in LoginEvent._meta.fields]
