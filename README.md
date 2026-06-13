# HardwareOS — Backend

The operating system for a multi-branch hardware business. Django modular
monolith (DRF + PostgreSQL + Redis + Celery) built around a primary objective:
the **Executive Command Center**.

> **Status — Phases 1–5.** Implemented & tested (38 passing tests: 20 Django + 18 AI): core kernel,
> RBAC, audit trail, authentication (JWT + MFA-ready), Organization/Branch,
> Inventory core (products, suppliers, categories, per-branch stock, immutable
> stock ledger), **POS** (sales decrement stock through the ledger, returns/refunds
> restock, receipts, customer history, idempotent submits, gap-free numbers),
> **Finance** (expenses + categories; P&L / cash flow / expense reports, net of
> returns), and the **Executive Command Center** (one dashboard payload: revenue
> by period, profit & margins, inventory value / dead stock / fast movers, branch
> ranking, top performers, cash flow, outstanding payments, daily trend, and an
> auto-generated executive insight summary; nightly `MetricSnapshot` rollups via
> Celery beat for scale), plus a separate **AI service** (FastAPI) for revenue
> forecasting, stock-out prediction, and natural-language querying. Next:
> **Next.js executive frontend**.
> See [ARCHITECTURE.md](ARCHITECTURE.md), [docs/ERD.md](docs/ERD.md) and
> [ai-service/README.md](ai-service/README.md).

---

## Quick start (Docker — recommended)

```bash
cp .env.example .env          # then edit SECRET_KEY etc.
docker compose up --build     # db, redis, web, celery worker + beat

# in another shell — seed roles, a demo org/branch/owner + sample products
docker compose exec web python manage.py bootstrap --demo-data \
    --email owner@demo.co --password 'Str0ngPass!23'
```

- API:        http://localhost:8000/api/v1/
- API docs:   http://localhost:8000/api/docs/  (Swagger UI from OpenAPI schema)
- Admin:      http://localhost:8000/admin/

## Quick start (local, no Docker)

```bash
python -m venv .venv && source .venv/Scripts/activate   # Windows Git Bash
pip install -r requirements.txt
# point POSTGRES_* / REDIS_URL at local services, or use docker for db+redis only
python manage.py migrate
python manage.py bootstrap --demo-data
python manage.py runserver
```

## Tests

```bash
DJANGO_SETTINGS_MODULE=config.settings.test pytest      # in-memory SQLite, no services needed
```

The stock-ledger invariants (purchase/sale/oversell/transfer) are covered in
[apps/inventory/tests/test_stock_service.py](apps/inventory/tests/test_stock_service.py).

---

## Layout

```
config/        settings (base/dev/prod/test), urls, celery, wsgi/asgi
core/          shared kernel: base models, repository, service, RBAC, exceptions
core/audit/    append-only AuditLog + request-context middleware
apps/accounts/ User, Role (RBAC), JWT auth, MFA enrollment, login auditing
apps/branches/ Organization (tenant root) + Branch CRUD & analytics stub
apps/inventory/ Category, Supplier, Product, StockLevel, StockMovement
```

Every module is layered **views → services → repositories → models**. Views are
thin; services own transactions + audit; repositories own all ORM access.

## RBAC roles (seeded by `bootstrap`)

`super_admin · owner · branch_manager · accountant · inventory_officer ·
cashier · sales_staff` — each a bundle of permission codes defined in
[core/rbac.py](core/rbac.py). Endpoints declare a `permission_map` per action.

## Key API endpoints (v1)

| Method | Path                                   | Permission        |
|--------|----------------------------------------|-------------------|
| POST   | `/api/v1/auth/login/`                  | public            |
| POST   | `/api/v1/auth/refresh/`                | public            |
| GET    | `/api/v1/auth/me/`                      | authenticated     |
| POST   | `/api/v1/auth/mfa/enroll/`             | authenticated     |
| CRUD   | `/api/v1/branches/`                    | branch.view/manage|
| GET    | `/api/v1/branches/{id}/analytics/`     | branch.view       |
| CRUD   | `/api/v1/inventory/products/`          | product.view/manage|
| GET    | `/api/v1/inventory/products/{id}/movements/` | stock.view  |
| GET    | `/api/v1/inventory/stock/?branch=`     | stock.view        |
| GET    | `/api/v1/inventory/stock/low-stock/`   | stock.view        |
| GET    | `/api/v1/inventory/stock/value/`       | stock.view        |
| POST   | `/api/v1/inventory/stock/movement/`    | stock.adjust      |
| POST   | `/api/v1/inventory/stock/transfer/`    | stock.transfer    |
| POST   | `/api/v1/inventory/stock/adjust/`      | stock.adjust      |
| GET    | `/api/v1/inventory/stock/forecast-feed/` | stock.view (AI service) |
| CRUD   | `/api/v1/pos/customers/`               | customer.view/manage |
| GET    | `/api/v1/pos/customers/{id}/history/`  | sale.view         |
| GET/POST| `/api/v1/pos/sales/`                   | sale.view / sale.create |
| POST   | `/api/v1/pos/sales/{id}/refund/`       | sale.refund       |
| POST   | `/api/v1/pos/sales/{id}/void/`         | sale.void         |
| GET    | `/api/v1/pos/sales/{id}/receipt/`      | sale.view         |
| CRUD   | `/api/v1/finance/expenses/`            | finance.view/manage |
| CRUD   | `/api/v1/finance/expense-categories/`  | finance.view/manage |
| GET    | `/api/v1/finance/reports/pnl/`         | finance.view      |
| GET    | `/api/v1/finance/reports/cash-flow/`   | finance.view      |
| GET    | `/api/v1/finance/reports/expenses-summary/` | finance.view |
| GET    | `/api/v1/analytics/dashboard/overview/`    | dashboard.view |
| GET    | `/api/v1/analytics/dashboard/revenue/`     | analytics.view |
| GET    | `/api/v1/analytics/dashboard/inventory/`   | analytics.view |
| GET    | `/api/v1/analytics/dashboard/branches/`    | analytics.view |
| GET    | `/api/v1/analytics/dashboard/employees/`   | analytics.view |
| GET    | `/api/v1/analytics/dashboard/insights/`    | analytics.view |

Report & dashboard endpoints accept `?period=today\|yesterday\|week\|month\|year`
or `?start=YYYY-MM-DD&end=YYYY-MM-DD`, plus an optional `?branch=<id>`.
`/analytics/dashboard/overview/` is the single Executive Command Center payload.

## Example: authenticate & read stock

```bash
TOKEN=$(curl -s -X POST localhost:8000/api/v1/auth/login/ \
  -H 'Content-Type: application/json' \
  -d '{"email":"owner@demo.co","password":"Str0ngPass!23"}' | jq -r .access)

curl -s localhost:8000/api/v1/inventory/products/ -H "Authorization: Bearer $TOKEN" | jq
curl -s localhost:8000/api/v1/inventory/stock/value/ -H "Authorization: Bearer $TOKEN" | jq
```

---

## Security highlights

- JWT access/refresh with rotation + blacklist; Argon2 password hashing.
- RBAC enforced at the API via permission codes; org-scoped object permissions.
- Append-only **AuditLog** written by services for every critical mutation —
  including dedicated `price_change`, `stock_change`, `login` / `login_failed`
  actions with field-level diffs, actor, IP and user-agent.
- Production settings enforce HTTPS redirect, HSTS, secure cookies, nosniff.
- Secrets via env (`.env` in dev, secret manager in prod) — never committed.

## Roadmap (next phases)

1. ~~**POS**~~ ✅ — Sale/SaleLine/Return/Refund/Receipt + customer history; sales
   decrement stock through `StockService.apply_movement`; DB-backed idempotency.
2. ~~**Finance**~~ ✅ — expenses + categories; P&L / cash-flow / expense-summary
   reports with period filters. Revenue & COGS are now **net of returns** by
   occurrence period (`SaleRepository.sales_summary` + `FinanceReportService`).
3. ~~**Analytics**~~ ✅ — Executive Command Center (`/analytics/dashboard/overview/`):
   revenue by period, profit & margins, inventory value / dead stock / fast movers,
   branch ranking, top performers, cash flow, receivables, daily trend, and an
   auto-generated insight summary. `MetricSnapshot` nightly rollups via Celery beat.
4. ~~**AI service**~~ ✅ — FastAPI app ([ai-service/](ai-service/)) consuming the REST
   API (JWT forwarded) for revenue forecasting, stock-out prediction, and NL
   querying. Uses Claude (`claude-opus-4-8`) when `ANTHROPIC_API_KEY` is set,
   else a deterministic engine. Adds `/inventory/stock/forecast-feed/` upstream.
5. **Frontend** — Next.js executive dashboard (Recharts, dark mode, real-time).
6. **DevOps** — GitHub Actions CI (ruff + mypy + pytest), staging/prod compose,
   Nginx reverse proxy with rate limiting.
```
