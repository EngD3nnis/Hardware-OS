from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from django.db.models import Count, F, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from apps.pos.models import Customer, Sale, SaleLine, SaleReturn, SaleReturnLine
from core.repositories import TenantRepository

_REVENUE_STATUSES = ["completed", "partially_refunded", "refunded"]

ZERO = Decimal("0")


def _d(value) -> Decimal:
    return value if value is not None else ZERO


class CustomerRepository(TenantRepository[Customer]):
    model = Customer

    def __init__(self, organization_id):
        super().__init__(organization_id, Customer)

    def search(self, term: str):
        return self.get_queryset().filter(name__icontains=term) | self.get_queryset().filter(
            phone__icontains=term
        )


class SaleRepository(TenantRepository[Sale]):
    model = Sale

    def __init__(self, organization_id):
        super().__init__(organization_id, Sale)

    def detailed(self):
        return self.get_queryset().select_related("branch", "cashier", "customer").prefetch_related("lines")

    def by_idempotency_key(self, key: str) -> Sale | None:
        if not key:
            return None
        return self.get_queryset().filter(idempotency_key=key).first()

    def for_customer(self, customer_id: UUID):
        return self.detailed().filter(customer_id=customer_id)

    # -- aggregates (canonical revenue/COGS, net of returns) -------------- #
    def sales_summary(self, start, end, branch_id: UUID | None = None) -> dict:
        """
        Period sales figures, with returns netted out by the period in which the
        return occurred. Revenue figures are pre-tax (VAT is a liability, not
        revenue); gross_sales/net_sales are tax-inclusive for cash reconciliation.
        """
        sales = self.get_queryset().filter(
            status__in=["completed", "partially_refunded", "refunded"],
            created_at__gte=start,
            created_at__lt=end,
        )
        if branch_id:
            sales = sales.filter(branch_id=branch_id)
        s = sales.aggregate(
            gross=Sum("total"), tax=Sum("tax_total"), cogs=Sum("cost_total"),
            subtotal=Sum("subtotal"), discount=Sum("discount_total"), count=Count("id"),
        )

        returns = SaleReturn.objects.filter(
            organization_id=self.organization_id, created_at__gte=start, created_at__lt=end
        )
        if branch_id:
            returns = returns.filter(branch_id=branch_id)
        r = SaleReturnLine.objects.filter(sale_return__in=returns).aggregate(
            gross=Sum("refund_amount"), net=Sum("net_amount"), cogs=Sum("cost_amount")
        )

        net_revenue = (_d(s["subtotal"]) - _d(s["discount"])) - _d(r["net"])   # pre-tax
        net_cogs = _d(s["cogs"]) - _d(r["cogs"])
        gross_profit = net_revenue - net_cogs
        return {
            "gross_sales": _d(s["gross"]),
            "refunds": _d(r["gross"]),
            "net_sales": _d(s["gross"]) - _d(r["gross"]),
            "net_revenue": net_revenue,
            "tax_collected": _d(s["tax"]) - (_d(r["gross"]) - _d(r["net"])),
            "cogs": net_cogs,
            "gross_profit": gross_profit,
            "gross_margin": (gross_profit / net_revenue * 100) if net_revenue else ZERO,
            "transactions": _d(s["count"]),
        }

    def cash_inflows_by_method(self, start, end, branch_id: UUID | None = None) -> dict:
        qs = self.get_queryset().filter(created_at__gte=start, created_at__lt=end)
        if branch_id:
            qs = qs.filter(branch_id=branch_id)
        rows = qs.values("payment_method").annotate(amount=Sum("amount_paid"))
        return {row["payment_method"]: _d(row["amount"]) for row in rows}

    def revenue_today(self, branch_id: UUID | None = None) -> dict:
        start, end = day_bounds()
        return self.sales_summary(start, end, branch_id)

    # -- leaderboards / trends (dashboard) -------------------------------- #
    def _sales_in(self, start, end, branch_id):
        qs = self.get_queryset().filter(
            status__in=_REVENUE_STATUSES, created_at__gte=start, created_at__lt=end
        )
        return qs.filter(branch_id=branch_id) if branch_id else qs

    def top_products(self, start, end, branch_id=None, limit=5) -> list[dict]:
        qs = SaleLine.objects.filter(
            organization_id=self.organization_id,
            sale__status__in=_REVENUE_STATUSES,
            sale__created_at__gte=start, sale__created_at__lt=end,
        )
        if branch_id:
            qs = qs.filter(sale__branch_id=branch_id)
        rows = (
            qs.values("product_id", "description")
            .annotate(quantity=Sum("quantity"), revenue=Sum("line_total"))
            .order_by("-revenue")[:limit]
        )
        return [
            {"product_id": str(r["product_id"]), "name": r["description"],
             "quantity": _d(r["quantity"]), "revenue": _d(r["revenue"])}
            for r in rows
        ]

    def top_cashiers(self, start, end, branch_id=None, limit=5) -> list[dict]:
        rows = (
            self._sales_in(start, end, branch_id)
            .values("cashier_id", "cashier__first_name", "cashier__last_name", "cashier__email")
            .annotate(revenue=Sum("total"), sales=Count("id"))
            .order_by("-revenue")[:limit]
        )
        out = []
        for r in rows:
            if not r["cashier_id"]:
                name = "Unassigned"
            else:
                name = (
                    f"{r['cashier__first_name'] or ''} {r['cashier__last_name'] or ''}".strip()
                    or r["cashier__email"]
                    or "—"
                )
            out.append({"cashier_id": str(r["cashier_id"]) if r["cashier_id"] else None,
                        "name": name, "revenue": _d(r["revenue"]), "sales": r["sales"]})
        return out

    def daily_net_sales(self, start, end, branch_id=None) -> dict:
        """date -> pre-tax net sales (sales minus returns), for the trend chart."""
        sales = (
            self._sales_in(start, end, branch_id)
            .annotate(d=TruncDate("created_at"))
            .values("d")
            .annotate(net=Sum(F("subtotal") - F("discount_total")))
        )
        series = {row["d"].isoformat(): _d(row["net"]) for row in sales}

        rets = SaleReturn.objects.filter(
            organization_id=self.organization_id, created_at__gte=start, created_at__lt=end
        )
        if branch_id:
            rets = rets.filter(branch_id=branch_id)
        ret_rows = (
            SaleReturnLine.objects.filter(sale_return__in=rets)
            .annotate(d=TruncDate("created_at"))
            .values("d")
            .annotate(net=Sum("net_amount"))
        )
        for row in ret_rows:
            key = row["d"].isoformat()
            series[key] = series.get(key, ZERO) - _d(row["net"])
        return series

    def outstanding_receivables(self, branch_id=None) -> Decimal:
        """Unpaid balance on credit sales (accounts receivable)."""
        qs = self.get_queryset().filter(
            payment_method="credit", status__in=_REVENUE_STATUSES, total__gt=F("amount_paid")
        )
        if branch_id:
            qs = qs.filter(branch_id=branch_id)
        agg = qs.aggregate(due=Sum(F("total") - F("amount_paid")))
        return _d(agg["due"])


def day_bounds(day=None):
    day = day or timezone.localdate()
    start = timezone.make_aware(timezone.datetime.combine(day, timezone.datetime.min.time()))
    return start, start + timezone.timedelta(days=1)


class SaleReturnRepository(TenantRepository[SaleReturn]):
    model = SaleReturn

    def __init__(self, organization_id):
        super().__init__(organization_id, SaleReturn)
