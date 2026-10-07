# ShelfCash Competition Edition

ShelfCash is a Decision Intelligence backend for Vietnamese F&B stores. It will
help a store decide what ingredients to buy, how much, when and under which strategy,
balancing shortages, waste and capital. The owner/manager makes the final decision.

**CURRENT FACT:** S0 infrastructure and S1 operational truth are complete. The backend
runs a typed health endpoint with PostgreSQL/Alembic infrastructure. S1.1 implements
User/Store/StoreMembership; S1.2 adds Product/Ingredient/Recipe/RecipeLine; S1.3 adds
Supplier/SupplierTerm/SalesDaily/InventoryLot/InventoryMovement/BusinessConstraint
persistence. S1.4 adds Forecast/Decision run storage; S1.5 adds concrete typed
repositories covering all sixteen tables. S1.6/S1.7 add typed internal operational
application paths, atomic Recipe/receipt writes and locked movement-backed inventory
corrections. Domain has exact inventory arithmetic and causal forecast features/metrics/baseline.
S2 has internal LightGBM training/evaluation, immutable artifacts and retained execution/
replay; real-data quality is NOT EVALUATED. Public business APIs/auth and Decision
computation remain absent. See [trained forecast](docs/features/FORECAST_TRAINED.md). See
[identity/store verification](docs/features/STORE_IDENTITY.md) and
[catalog/recipe verification](docs/features/CATALOG_RECIPE.md) and
[S1.3 verification](docs/runbooks/S13_VERIFICATION.md). ADR-008 freezes import
idempotency/corrections; ADR-009 freezes audited lot mutations. S1.7 enforces its
receipt/correction paths at the application boundary; no Import engine exists.
See [application contracts](docs/features/APPLICATION_CONTRACTS.md) and
[S1.7 verification](docs/runbooks/S17_VERIFICATION.md).

**ACCEPTED DECISION — future pipeline:** operational data → forecast → BOM/recipe
expansion → ingredient demand → inventory/FEFO → supplier/business constraints →
LEAN/BALANCED/PROTECTED candidates → exact simulator → comparison → recommendation
→ explanation/what-if → human decision. Forecast alone is not the product.
Deterministic backend code owns business truth. LLMs never compute or select decisions.

## Setup and run

Python 3.11+, Docker with Linux containers and Docker Compose are required.
PostgreSQL runs in Compose; the backend stays native Python/venv. From this
repository's workspace root, in PowerShell:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[dev]'
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker compose up -d postgres
docker compose up -d --wait --wait-timeout 90 postgres
.\scripts\db_status.ps1 -AllowUnmigrated
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

On POSIX use `.venv/bin/python` and `.venv/bin/alembic`; copy `.env.example` with `cp`.
Run commands from `backend/`. The local default is
`postgresql+psycopg://shelfcash:shelfcash@127.0.0.1:5432/shelfcash`; environment/.env
configures the URL, credentials and test URL. Native PostgreSQL installation is
unnecessary. Alembic uses Settings and `.env` as the
configuration source; `alembic.ini` records the default URL for reference.
The original baseline creates only Alembic's revision table; current head
`0008_forecast_execution_meta` contains eighteen business tables across S1 and S2. Application import,
startup and health checks do not initialize/connect to the DB, create directories
or contact OpenRouter. No provider key is required.

```powershell
.\scripts\test.ps1 all
.\scripts\db_status.ps1
.\.venv\Scripts\python.exe -c "from app.main import app; print(app.openapi())"
```

For a clean development database, stop the backend/database clients, then run
`.\scripts\reset_db.ps1 -Seed`. This recreates the guarded local PostgreSQL `public`
schema and reapplies migrations. No demo seed rows exist; the seed command
verifies the current schema explicitly and writes no data. POSIX equivalents are
`sh scripts/test.sh all`, `sh scripts/db_status.sh` and
`sh scripts/reset_db.sh --seed`. See the
[full local verification runbook](docs/runbooks/FULL_TEST_FLOW.md) for fresh setup,
expected HTTP results and direct persisted database checks.

Compose binds PostgreSQL to `127.0.0.1:5432` by default (`POSTGRES_PORT` is configurable)
and persists it in named volume `shelfcash-postgres-data`. Restart/recreation retains
data; normal reset keeps the volume. Integration tests own only separate
`shelfcash_test`, creating it when needed; Docker must be healthy for `test all`.
Unit/API categories need no live database. See
[database reset](docs/runbooks/DATABASE_RESET.md) and
[demo setup](docs/runbooks/DEMO_SETUP.md) for safeguards and expected state.

`GET /health` returns `{"status":"ok","service":"shelfcash-backend"}` by default.
`GET /openapi.json` exposes the schema; interactive documentation is disabled.
Health is liveness, not a database or business readiness probe.
Runtime data, local credentials and virtual environments are ignored by Git.
Trusted immutable local LightGBM artifact storage exists; upload storage remains reserved.

## Canonical documents

- [AGENTS.md](AGENTS.md): mandatory engineering rules and authority order.
- [Current state](docs/CURRENT_STATE.md): runtime reality and verification.
- [Decisions](docs/DECISIONS.md): accepted ADR index.
- [Architecture](docs/ARCHITECTURE.md): target modular monolith and authority boundaries.
- [API contract](docs/API_CONTRACT.md): implemented public contract.
- [Domain model](docs/DOMAIN_MODEL.md): boundaries, relationships and invariants.
- [Database schema](docs/DATABASE_SCHEMA.md): implemented S1.1/S1.2/S1.3 clusters and remaining Schema v1 proposals.
- [Roadmap](docs/ROADMAP.md): vertical slices and acceptance gates.
- [Testing](docs/TESTING.md): verification layers and future golden scenarios.

Development PostgreSQL schemas may be reset between versions. Alembic still records
schema evolution; long-lived compatible migrations are not a current requirement.

S1.3.1 / ADR-010 accepts explicit completeness and source-fact policies. Unknown lot
receipt dates remain NULL; strict supplier dates and per-pack costs are unchanged.
No import engine or business API exists. See docs/runbooks/S131_VERIFICATION.md.

S1.4 implements ForecastRun/ForecastPrediction/DecisionRun storage and ADR-011
historical policy. Internal Forecast baseline/trained execution now exists; Decision
Engine and public business APIs remain NOT STARTED. Eighteen tables are implemented;
see the labelled synthetic manual forecast verification, not a decision pipeline demo. See docs/features/FORECAST.md, docs/features/DECISION_RUN.md and
docs/runbooks/S14_VERIFICATION.md. S1 overall status is in CURRENT_STATE/ROADMAP.

S1.5 provides [persistence access](docs/features/PERSISTENCE_ACCESS.md): explicit
Store scope, domain-specific insert/read/lifecycle methods and caller-owned synchronous
transactions. Repositories never commit/rollback. Forecast/Decision writers guard
RUNNING-only transitions and prediction append. S1.6/S1.7 application paths provide
operational validation and atomic inventory audit; Decision engine/auth remain future. Targeted verification:
`.\.venv\Scripts\python.exe -m pytest tests/integration/test_repositories.py -q`.
