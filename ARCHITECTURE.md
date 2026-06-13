# HardwareOS — System Architecture

> The operating system for a multi-branch hardware business.
> Primary objective: the **Executive Command Center**.

---

## 1. Architectural style

**Modular monolith** (Django) with a strict internal module boundary, plus a
**separate AI service** (FastAPI). One deployable backend today; designed to be
split into services later without rewriting domain logic.

```
                       ┌────────────────────────────┐
                       │   Next.js Executive Frontend│
                       │  (React / TS / Tailwind)    │
                       └──────────────┬──────────────┘
                                      │ HTTPS / JWT
                          ┌───────────▼───────────┐
                          │        Nginx           │  TLS termination, rate limit
                          └───────────┬───────────┘
              ┌───────────────────────┼───────────────────────┐
              │                       │                        │
   ┌──────────▼──────────┐  ┌─────────▼──────────┐   ┌─────────▼─────────┐
   │  Django API (DRF)   │  │   Celery workers   │   │  AI Service        │
   │  modular monolith   │  │   (async + beat)   │   │  (FastAPI)         │
   └──────────┬──────────┘  └─────────┬──────────┘   └─────────┬─────────┘
              │                       │                        │
       ┌──────▼──────┐         ┌──────▼──────┐          ┌──────▼──────┐
       │ PostgreSQL  │         │    Redis    │◄─────────┤ reads metrics│
       │  (primary)  │         │ broker+cache│          │  via API     │
       └─────────────┘         └─────────────┘          └─────────────┘
```

The AI service **never** touches the database directly. It calls the Django API
(service-to-service token) for facts and returns insights. This keeps the domain
single-sourced and lets the AI service scale/deploy independently.

---

## 2. Layering (Clean Architecture + DDD)

Every business module follows the same four layers. Dependencies point inward.

```
HTTP (views/serializers)   ← Interface / API layer       (DRF)
        │ calls
Service layer              ← Application / use-cases      (transactions, orchestration)
        │ calls
Repository layer           ← Data access abstraction      (querysets behind interfaces)
        │ uses
Domain models              ← Entities + invariants        (Django models, value objects)
```

- **Views** are thin: parse, authorize (RBAC), delegate to a service, serialize.
- **Services** own use-cases and transactions. They emit audit events and
  domain side-effects (e.g. a sale decrements stock + writes a StockMovement).
- **Repositories** wrap all ORM access. No `.objects` calls leak into services
  or views. This is the seam we cut when extracting a microservice.
- **Models** hold invariants and are persistence-aware but logic-light.

### Module dependency rule
Modules talk to each other **only through service interfaces**, never by
importing another module's models directly. Allowed import direction:

```
analytics → finance → pos → inventory → branches → accounts → core
```

A lower module never imports a higher one. `core` depends on nothing.

---

## 3. Multi-tenant & multi-branch model

- **Organization** = tenant (the company). Multi-tenant ready via a single
  `organization_id` discriminator on every tenant-scoped row + a row-level
  query filter applied in repositories. Single-org today; flip on by routing.
- **Branch** = physical location under an organization. Stock, sales, finance,
  and employees are branch-scoped. The Executive Dashboard aggregates across
  branches the requesting user is allowed to see.
- Scope resolution order: `Organization → Branch → User`. Every request carries
  a resolved `TenantContext` (org + visible branch ids) built from the JWT.

---

## 4. Security architecture

| Concern              | Mechanism                                                        |
|----------------------|------------------------------------------------------------------|
| AuthN                | JWT (access ~15m / refresh ~7d), rotation + blacklist, MFA-ready |
| AuthZ                | RBAC: roles → permission codes, enforced by DRF permission class |
| Audit                | `AuditLog` written by services for every critical mutation       |
| Change tracking      | Field-level diff captured in audit `changes` JSON                |
| Rate limiting        | Nginx + DRF throttling (scoped per role/endpoint)                |
| Encryption in transit| TLS at Nginx                                                     |
| Encryption at rest   | Postgres volume + disk encryption; secrets via env/secret store  |
| Secrets              | `.env` in dev, secret manager in prod (never committed)          |
| PII / financial      | Audited on every read-sensitive + all writes                     |

Critical auditable actions: stock changes, price changes, login activity,
financial transactions, role/permission changes, refunds.

---

## 5. Scalability strategy

Initial: 5 branches · 500 employees · 50k products · 10k txns/day.
Target: 1M users.

- **DB indexing**: composite indexes on every `(organization, branch, *)` access
  path; partial indexes for `is_active`; GIN on search fields/barcodes.
- **Caching**: Redis for dashboard aggregates (short TTL + invalidate-on-write),
  session/JWT blacklist, and idempotency keys for POS.
- **Async**: Celery for notifications, report generation, AI refresh, heavy
  aggregation. Beat for scheduled rollups (hourly/daily metric snapshots).
- **Read scaling**: dashboard reads served from pre-computed
  `MetricSnapshot` tables (materialized rollups) rather than live SUM over txns.
- **Horizontal**: stateless API + workers behind Nginx; Postgres read replicas
  and table partitioning (sales by month) when volume demands.
- **Extraction path**: repository seams + module service interfaces let POS,
  Inventory, and AI become independent services with minimal change.

---

## 6. Module map

| Module        | Responsibility                                              | Phase |
|---------------|-------------------------------------------------------------|-------|
| `core`        | base models, repo/service bases, RBAC, audit, exceptions    | ✅ now |
| `accounts`    | users, roles, JWT, MFA, sessions, password reset            | ✅ now |
| `branches`    | organization (tenant), branches, branch analytics           | ✅ now |
| `inventory`   | categories, suppliers, products, per-branch stock, movements| ✅ now |
| `pos`         | sales, invoices, receipts, discounts, returns/refunds       | next  |
| `finance`     | expenses, revenue, profit, cash flow, branch P&L            | next  |
| `analytics`   | executive dashboard, rollups, rankings, AI insight feed     | next  |
| `employees`   | profiles, attendance, performance, tasks                    | later |
| `notifications`| email, SMS, WhatsApp, push                                 | later |

---

## 7. Repository folder structure

```
store-backend/
├── config/                 # project: settings (base/dev/prod), urls, celery, wsgi/asgi
├── core/                   # shared kernel: base models, repo/service, rbac, audit
├── apps/
│   ├── accounts/           # auth, users, roles
│   ├── branches/           # organization + branches
│   ├── inventory/          # products, stock, suppliers
│   ├── pos/                # (next)
│   ├── finance/            # (next)
│   └── analytics/          # (next)
├── manage.py
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── docs/  (ERD.md, API.md)
```

Each app: `models.py · repositories.py · services.py · serializers.py ·
views.py · urls.py · permissions.py · admin.py · apps.py · migrations/ · tests/`.

---

## 8. Testing strategy

- **Unit**: services & repositories (pytest + factory_boy), domain invariants.
- **Integration**: API endpoints via DRF `APIClient`, RBAC matrix per role.
- **Contract**: OpenAPI schema (drf-spectacular) — frontend + AI service consume it.
- **Data**: migration tests, audit-coverage tests (every critical mutation logs).
- **Targets**: ≥85% on services/repos; full RBAC permission matrix coverage.
- CI runs lint (ruff) + type (mypy) + tests on every PR (GitHub Actions).
```
