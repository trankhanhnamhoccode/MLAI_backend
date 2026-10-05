# Current state

Classification: CURRENT FACT unless explicitly marked otherwise.

- Project phase: **S1 — IN PROGRESS**; S0/S0.2 remain complete.
- Completed: **S1.1 — Identity + Store Schema Cluster** (persistence only).
- Completed: **S1.2 — Catalog + Recipe Schema Cluster** (persistence only).
- Greenfield Competition Edition; no legacy backend was imported.
- Current database: **PostgreSQL**, SQLAlchemy 2.x with psycopg and synchronous
  Session. ADR-007 is ACCEPTED; ADR-003 is SUPERSEDED. The empty Alembic
  baseline is `0001_scaffold`; current head is `0003_catalog_recipe`.
- Implemented business tables/models: `users`, `stores`, `store_memberships`,
  `products`, `ingredients`, `recipes`, `recipe_lines` only.
  Identity/store membership persistence exists; authentication/authorization does not.
  Plain Python domain packages remain empty. Repository/application service layers
  and public business APIs: not started. Remaining Schema v1 is PROPOSAL.
- Runtime: FastAPI app factory, Pydantic v2 settings and typed health schema.
  `GET /health` is the only API operation. `/openapi.json` is framework schema
  metadata. Interactive documentation routes are disabled.
- Import/startup/health do not initialize the database or contact external services.
- Local DB: Docker Compose official PostgreSQL 17, native `pg_isready` healthcheck,
  loopback port 5432 and persistent named volume `shelfcash-postgres-data`.
  Backend remains native Python/venv; no host PostgreSQL install is needed.
- Runtime directories are reserved for uploads and model artifacts.
  No upload/storage feature, Session dependency or repository is implemented yet.
- Canonical documents created: AGENTS, README, architecture, domain model, Schema v1
  proposal, API contract, decisions/ADRs 001–007, roadmap and testing guide.
- Local verification tooling: PowerShell/POSIX test, reset, seed and DB status
  scripts. Reset is restricted to development/test, local hosts and explicit
  `shelfcash`/`shelfcash_test` databases; test permits only the latter. It recreates
  `public`, migrates and optionally checks the seed baseline. Status reports
  reachability/database/server/revision/head and table counts via a fresh read-only
  transaction. `AllowUnmigrated` permits inspection before migration.
- Tests are organized into unit/integration/api/e2e/fixtures; no e2e/business seed
  or golden business scenarios exist yet. Seed reports no business rows written.
- [Full test flow](runbooks/FULL_TEST_FLOW.md) and
  [scaffold feature guide](features/SCAFFOLD.md) provide manual HTTP and persisted
  DB verification. All execution/testing/demo preparation remains local; no Kaggle
  or hosted notebook dependency. Only S1.1/S1.2 schema clusters are implemented; all
  later business features remain unimplemented. Seed verifies schema, writes no rows.
- Integration tests own only separate `shelfcash_test`, created if absent by the
  local role. Tests run sequentially and never reset normal development state.

## Verification

S1.2 verified on Windows/Python 3.11.9, 2026-10-05:
- Targeted `test_catalog_recipe_schema.py`: **51 passed** on shelfcash_test. Covers
  four-model commit/close/fresh-session reload, exact Decimal/defaults, scoped SKUs
  and nullable semantics, PK/FK/check/exclusion, inclusive/open-ended dates, version,
  yield/loss, quantities, duplicate lines, unit/cross-store integrity and parent updates.
- `./scripts/test.ps1 all`: **93 passed** (14 unit, 77 integration, 2 API), one
  existing upstream Starlette/AnyIO warning, no skips. S1.1 regressions preserved;
  metadata comparison passes. Fresh reset/upgrade and 0003->0002->head pass; bootstrap
  also downgrades through 0001/base and re-upgrades. Tests own only shelfcash_test.
- `docker compose config --quiet`, up, up --wait and ps succeed: PostgreSQL 17.11
  healthy. Development reset, upgrade/current, seed and status succeed. Head is
  0003_catalog_recipe; one revision row and seven empty business tables. Direct
  SQL inspection confirms constraints; no future tables exist.
- App/model/domain imports succeed with psycopg connection forbidden. OpenAPI
  matches the saved pre-S1.1 schema exactly; live /health HTTP 200 payload unchanged,
  live /openapi.json identical, verification server stopped afterward.
- `pip check` passes. Diff/status/scope reviewed, whitespace check passes. API_CONTRACT,
  public API code, domain code, repository layer, accepted ADRs/dependencies unchanged.
  No commit; no remaining S1.2 blocker. No BOM, API, auth or S1.3 implementation.
- PowerShell workflow runtime-verified. POSIX wrappers unchanged; historical syntax
  validation only, no POSIX runtime verification claimed for this slice.

### S1.1 acceptance — HISTORICAL INFORMATION

S1.1 verified on Windows/Python 3.11.9, 2026-10-05 (state before S1.2):
- Targeted `test_identity_store_schema.py`: **22 passed**, real shelfcash_test,
  covering metadata/migration agreement, fresh-session round trips, PostgreSQL
  constraints/defaults and UTC timestamp semantics. Development reset/upgrade/head,
  seed and table-count inspection pass at `0002_identity_store` with empty tables.
- `./scripts/test.ps1 all`: **42 passed** (14 unit, 26 integration, 2 API), one
  existing upstream Starlette/AnyIO deprecation warning; no skips. Integration
  writes/downgrades/resets own only shelfcash_test. Downgrade through the original
  scaffold and re-upgrade to head pass; model/migration comparison has no drift.
- Docker Compose up/ps: PostgreSQL 17.11 healthy. The feature guide's direct SQL
  column/constraint inspection command succeeds. Development status after tests/HTTP
  remains `alembic_version: 1`, `users: 0`, `stores: 0`, `store_memberships: 0`.
- App/model/domain imports with psycopg connection forbidden succeed; OpenAPI
  matches the pre-S1.1 schema exactly. Live `/health` returns unchanged HTTP 200
  payload, and `/openapi.json` adds no business operations; server stopped afterward.
- `pip check`: no broken requirements. Diff/status/scope and whitespace reviewed;
  API_CONTRACT, app API/schemas, dependencies, domain packages and repository layer
  untouched; no commit. No remaining S1.1 acceptance blocker.
- Storage semantics/known limits are recorded in DATABASE_SCHEMA and
  [STORE_IDENTITY](features/STORE_IDENTITY.md). POSIX scripts unchanged; prior syntax
  verification only, no native POSIX runtime verification claimed.

### S0.2 acceptance — HISTORICAL INFORMATION

S0.2 verified on Windows/Python 3.11.9, 2026-10-05:
- `docker compose config`, `docker compose up -d postgres`, `docker compose ps`:
  succeed; service healthy, named volume mounted. PostgreSQL server is 17.11.
- PowerShell status/reset/seed and Alembic upgrade/current succeed against fresh
  PostgreSQL. Persisted public state is only revision `0001_scaffold`, one row.
- `.venv/Scripts/python.exe -m pytest` and `./scripts/test.ps1 all`:
  **20 passed** each (14 unit, 4 integration, 2 API), one existing upstream
  Starlette/AnyIO deprecation warning. No skips; real PostgreSQL integration tests.
- `pip check` passes; psycopg/psycopg-binary 3.3.6 installed. App import and exact
  saved-before/generated-after OpenAPI comparison pass. Live Uvicorn `/health`
  returns unchanged HTTP 200 payload; `/openapi.json` is identical. Server stopped.
- `docker compose up -d --force-recreate --wait --wait-timeout 90 postgres`:
  healthy; subsequent fresh status retained revision/table state in the named volume.
  Reset without seed, upgrade/current, standalone seed and final status also pass.
- All five POSIX wrappers pass Git Bash `bash -n`: syntax-checked only, no native
  POSIX runtime verification. PowerShell workflow is runtime-verified.
- Diff/status reviewed, whitespace check passes; public API/migration/business
  model surface unchanged, no commit created. Remaining old persistence references
  are classified in [cleanup audit](runbooks/S02_SQLITE_AUDIT.md) as historical only.
- No remaining S0.2 acceptance blocker. Native URL defaults use explicit loopback
  to avoid this Windows machine's hostname/IPv6 fallback delay. URL remains configurable.

### Earlier local verification slice — HISTORICAL INFORMATION

Local verification tooling slice verified on 2026-10-05 (Windows/Python 3.11.9):
- `./scripts/test.ps1 all`: **13 passed**, one existing upstream Starlette/AnyIO
  deprecation warning. Includes guarded command failures, fresh persisted reads,
  repeated reset/seed on temporary SQLite and sidecar refusal without data loss.
- PowerShell reset with seed, standalone seed and DB status succeed on the canonical
  development database; only `alembic_version` exists with row `0001_scaffold`.
- Live Uvicorn health/OpenAPI assertions and independent read-only SQL checks pass;
  server stopped afterward. `pip check` succeeds. No public API/schema change.
- PowerShell wrapper propagates rejected reset as exit 1; the empty e2e selector
  reports no tests. POSIX wrapper syntax passes Git Bash `bash -n`; runtime
  execution on a native POSIX environment has not been verified in this session.

### Initial scaffold verification — HISTORICAL INFORMATION

Verified on 2026-10-05 with Python 3.11.9 (Windows):
- `.\.venv\Scripts\python.exe -m pytest`: **5 passed**, one upstream Starlette/AnyIO
  deprecation warning; no test failures. Tests cover app import, health contract,
  OpenAPI/route inventory, domain import independence, empty migration upgrade/downgrade
  and synchronous Session. No external HTTP calls; temporary SQLite/in-process ASGI.
- `.\.venv\Scripts\python.exe -m pip check`: no broken requirements.
- App import and JSON serialization of generated OpenAPI 3.1.0 succeed;
  OpenAPI paths contain only `/health`; runtime routes are `/health`, `/openapi.json`.
- `.\.venv\Scripts\alembic.exe upgrade head` / `current`: `0001_scaffold (head)`;
  local ignored `runtime/shelfcash.db` contains only the revision table.
- Uvicorn startup succeeds and local `/health` returns the documented payload;
  the verification server was stopped afterward.
- Git initialized for review, no commit created. Diff whitespace check, ADR links,
  canonical agent-document references, dependency inventory and empty-domain scope verified.

FastAPI is constrained to the tested 0.115 release line for HTTPX test-client/route
inventory compatibility. Verified stack: FastAPI 0.115.14, Pydantic 2.13.5,
SQLAlchemy 2.1.3, Alembic 1.20.0. Other dependencies use declared version ranges;
an exact transitive lockfile is not part of this scaffold.

## Next recommended slice — PROPOSAL

S1.3 — Supplier + Operational + Constraints Schema. Freeze that cluster's storage
semantics and persistence acceptance tests first. Do not begin S1.3 automatically;
completion of S1.2 authorizes no next slice.

## Known unresolved decisions — PROPOSAL

- Future Store API fields, validation and error contract. S1.1 UUID storage and
  timezone/currency defaults are frozen; public identifier/payload contracts are not.
- Authentication/bootstrap and minimum store isolation needed before data exposure.
- Currency precision/rounding, units/conversions and Vietnam business-date cutoff.
- Recipe resolver/API behavior beyond frozen inclusive date selection; forecast
  baseline/quantile calibration and simulator
  time granularity, objectives/tie breaks and constraint infeasibility policy.
- Decision package structure beyond required schema version 1 and historical context.
- Mapping confidence thresholds and human approval rules.

No known technical debt is recorded in the initial scaffold. These unresolved choices
are not accepted architecture and must not be silently treated as implementation facts.
