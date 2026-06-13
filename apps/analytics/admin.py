from django.contrib import admin

from apps.analytics.models import MetricSnapshot


@admin.register(MetricSnapshot)
class MetricSnapshotAdmin(admin.ModelAdmin):
    list_display = (
        "snapshot_date", "branch", "net_revenue", "gross_profit",
        "net_profit", "transactions", "inventory_value",
    )
    list_filter = ("branch", "snapshot_date")
    date_hierarchy = "snapshot_date"
    readonly_fields = [f.name for f in MetricSnapshot._meta.fields]
