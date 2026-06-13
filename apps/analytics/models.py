"""
Pre-computed metric rollups.

Reading the executive dashboard live (SUM over every sale/expense) does not
scale to 10k+ txns/day. A Celery-beat job materialises one MetricSnapshot per
(branch, day) so the dashboard's historical series and trends read pre-aggregated
rows. Today's figures are still computed live for freshness.
"""
from __future__ import annotations

from decimal import Decimal

from django.db import models

from core.models import TenantScopedModel

MONEY = dict(max_digits=16, decimal_places=2)
ZERO = Decimal("0")


class MetricSnapshot(TenantScopedModel):
    # branch == NULL means an organisation-wide rollup for the day.
    branch = models.ForeignKey(
        "branches.Branch", null=True, blank=True, on_delete=models.CASCADE, related_name="snapshots"
    )
    snapshot_date = models.DateField(db_index=True)

    gross_sales = models.DecimalField(**MONEY, default=ZERO)
    refunds = models.DecimalField(**MONEY, default=ZERO)
    net_revenue = models.DecimalField(**MONEY, default=ZERO)   # pre-tax, net of returns
    cogs = models.DecimalField(**MONEY, default=ZERO)
    gross_profit = models.DecimalField(**MONEY, default=ZERO)
    operating_expenses = models.DecimalField(**MONEY, default=ZERO)
    net_profit = models.DecimalField(**MONEY, default=ZERO)
    transactions = models.PositiveIntegerField(default=0)
    inventory_value = models.DecimalField(**MONEY, default=ZERO)

    class Meta(TenantScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "branch", "snapshot_date"],
                name="uniq_snapshot_branch_day",
            )
        ]
        indexes = [models.Index(fields=["organization", "branch", "-snapshot_date"])]

    def __str__(self) -> str:
        scope = self.branch.code if self.branch else "ORG"
        return f"{scope} {self.snapshot_date}: rev={self.net_revenue}"
