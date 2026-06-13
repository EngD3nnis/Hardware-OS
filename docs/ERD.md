# HardwareOS — Entity Relationship Diagram (Phase 1)

Covers the modules built so far: accounts, branches, inventory, audit.
POS, finance and analytics entities are sketched at the bottom for continuity.

```
                         ┌────────────────────┐
                         │   Organization     │  (tenant root)
                         │  id, name, slug,   │
                         │  currency, tz      │
                         └─────────┬──────────┘
              ┌────────────────────┼───────────────────────┐
              │ 1                  │ 1                     │ 1
              ▼ N                  ▼ N                     ▼ N
       ┌────────────┐      ┌──────────────┐        ┌──────────────┐
       │   Branch   │      │     User     │        │  Category    │
       │ id, code,  │◄─────│ email, roles │        │ name, slug,  │
       │ city, mgr  │ N  1 │ org, branch  │        │ parent(self) │
       └─────┬──────┘      └──────┬───────┘        └──────┬───────┘
             │                    │ M:N                   │ 1
             │                    ▼                       │ N
             │              ┌──────────┐                  ▼
             │              │   Role   │            ┌──────────────┐
             │              │ slug,    │            │   Product    │
             │              │ perms[]  │            │ sku, barcode,│
             │              └──────────┘            │ cost, sell,  │
             │                                      │ reorder, unit│
             │                                      └──────┬───────┘
             │                            ┌────────────────┼───────────────┐
             │ 1                          │ 1              │ 1             │ N
             │                            ▼ N              ▼ N             ▼
             │                     ┌────────────┐   ┌──────────────┐ ┌──────────┐
             └────────────────────►│ StockLevel │   │StockMovement │ │ Supplier │
                       1        N  │ product,   │   │ type, delta, │ │ name,    │
                                   │ branch,    │   │ balance_after│ │ contact  │
                                   │ quantity   │   │ ref, branch  │ └──────────┘
                                   └────────────┘   └──────────────┘
                            UNIQUE(product,branch)   (immutable ledger)

   ┌──────────────────────────────────────────────────────────────────┐
   │ AuditLog (append-only, not FK-bound): actor, org_id, branch_id,    │
   │ action, entity_type, entity_id, changes(JSON), ip, user_agent      │
   │ LoginEvent: user, email, successful, ip, user_agent, created_at    │
   └──────────────────────────────────────────────────────────────────┘
```

## Key relationships & rules
- **Organization 1—N Branch / User / Product / Category / Supplier** — every
  tenant-scoped row carries `organization_id`; repositories filter on it.
- **User M—N Role** — permissions are the union of role permission codes.
- **Product 1—N StockLevel** — one row per (product, branch); `UNIQUE(product, branch)`.
- **Product 1—N StockMovement** — immutable ledger; `balance_after` snapshots
  the running total; sales/transfers/adjustments all write here.
- **Branch.manager → User** (SET NULL) — a branch optionally has a manager.

## Indexing highlights (scale)
- `(organization, is_active)` on Branch / Product / Supplier.
- `(organization, sku)` unique partial (alive rows) on Product; `barcode` indexed.
- `(branch, product)` on StockLevel; `(organization, product, -created_at)` on movements.
- AuditLog: `(organization_id, entity_type, -timestamp)`, `(actor, -timestamp)`.

## POS (Phase 2 — built)
```
Customer (org, name, phone)
Sale (org, number, branch, cashier, customer, status, totals, cost_total, idempotency_key)
  └─ SaleLine (product, qty, unit_price, unit_cost, discount, line_total, refunded_qty)
       ──► each line writes StockMovement(SALE) via StockService
SaleReturn (org, number, sale, branch, refund_total, restock)
  └─ SaleReturnLine (sale_line, qty, refund_amount, net_amount, cost_amount)
       ──► writes StockMovement(RETURN_IN) when restock=True
DocumentCounter (org, branch_code, doc_type, last_number)  — gap-free numbering
```
Receipt/invoice are projections of Sale (no separate table). `net_amount` and
`cost_amount` on return lines let P&L net out returned revenue/tax/COGS via ORM.

## Finance (Phase 3 — built)
```
ExpenseCategory (org, name, slug)
Expense (org, branch, category, amount, expense_date, payment_method, recorded_by)
```
No revenue/COGS tables — those are derived from POS (single source of truth).
`FinanceReportService` combines `SaleRepository.sales_summary` (net of returns)
with expenses to produce P&L, cash flow, and per-branch financials.

## Analytics (Phase 4 — built)
```
MetricSnapshot (org, branch[nullable=org-wide], snapshot_date,
                gross_sales, refunds, net_revenue, cogs, gross_profit,
                operating_expenses, net_profit, transactions, inventory_value)
  UNIQUE(org, branch, snapshot_date)   — daily rollup, upserted by Celery beat
```
No new transactional tables — the dashboard is *computed* from POS + Finance +
Inventory via DashboardService. MetricSnapshot exists only to pre-aggregate
historical days so the dashboard scales (today is still computed live).
InsightService generates the executive summary (rule engine; AI service later).

## Coming next
```
AI service (FastAPI) — consumes the REST API; forecasting, stock-out prediction,
                       NL querying. Plugs into InsightService seam.
Employees module — profiles, attendance, performance (fills dashboard people block)
Next.js executive frontend — renders /analytics/dashboard/overview/
```
