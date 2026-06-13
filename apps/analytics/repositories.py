from __future__ import annotations

from uuid import UUID

from apps.analytics.models import MetricSnapshot
from core.repositories import TenantRepository


class MetricSnapshotRepository(TenantRepository[MetricSnapshot]):
    model = MetricSnapshot

    def __init__(self, organization_id):
        super().__init__(organization_id, MetricSnapshot)

    def upsert(self, *, branch_id: UUID | None, snapshot_date, **metrics) -> MetricSnapshot:
        obj, _ = MetricSnapshot.objects.update_or_create(
            organization_id=self.organization_id,
            branch_id=branch_id,
            snapshot_date=snapshot_date,
            defaults=metrics,
        )
        return obj

    def series(self, start_date, end_date, branch_id: UUID | None = None):
        qs = self.get_queryset().filter(
            snapshot_date__gte=start_date, snapshot_date__lte=end_date, branch_id=branch_id
        )
        return qs.order_by("snapshot_date")
