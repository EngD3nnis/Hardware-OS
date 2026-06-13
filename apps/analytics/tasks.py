"""Scheduled rollups for the executive dashboard."""
from __future__ import annotations

from celery import shared_task
from django.utils import timezone


@shared_task(name="analytics.compute_daily_snapshots")
def compute_daily_snapshots(target_date: str | None = None) -> dict:
    """
    Materialise MetricSnapshot rows for every active organization.

    Runs nightly (Celery beat) for the previous day so end-of-day figures are
    final. Idempotent — safe to re-run / backfill.
    """
    from apps.analytics.services import SnapshotService
    from apps.branches.models import Organization

    if target_date:
        day = timezone.datetime.fromisoformat(target_date).date()
    else:
        day = timezone.localdate() - timezone.timedelta(days=1)

    processed = {}
    for org in Organization.objects.filter(is_active=True):
        count = SnapshotService(org.id).compute_for_date(day)
        processed[str(org.id)] = count
    return {"date": day.isoformat(), "organizations": processed}
