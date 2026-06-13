from django.contrib import admin

from core.audit.models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("timestamp", "action", "entity_type", "entity_id", "actor_label")
    list_filter = ("action", "entity_type")
    search_fields = ("entity_id", "actor_label", "entity_type")
    date_hierarchy = "timestamp"
    readonly_fields = [f.name for f in AuditLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False  # append-only trail
