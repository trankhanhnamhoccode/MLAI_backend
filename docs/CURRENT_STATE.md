# Current state

Classification: CURRENT FACT unless explicitly marked otherwise.

- Project phase: **S1 — COMPLETE**; S0/S0.2 remain complete.
- Completed: **S1.1 — Identity + Store Schema Cluster** (persistence only).
- Completed: **S1.2 — Catalog + Recipe Schema Cluster** (persistence only).
- Completed: **S1.3 — Supplier + Operational + Constraints Schema** (persistence only).
- Completed: **S1.3.1 -- Data Completeness & Source Semantics Correction**.
  Schema changed: only unknown inventory receipt dates become nullable (no default),
  with an explicit both-known expiry check. Supplier price/effective date unchanged.
  ADR-010 Data Completeness and Missing Business Facts Policy is ACCEPTED.
- Completed: **S1.4 -- Forecast + Decision Persistence Schema** (storage only).
  ADR-011 Historical Run Immutability and Snapshot Policy is ACCEPTED.
  Forecast computation: NOT STARTED. Decision computation: NOT STARTED.
  Repository layer: implemented by S1.5 (see below). Public business API: NONE.
  S1.6/S1.7 now cover the authorized operational application/Pydantic flow;
  S1.7 final acceptance closes the canonical S1 operational gates.
- Completed: **S1.5 -- Persistence Access Contract + Repository Layer**.
  Nine domain modules / ten concrete repositories cover all sixteen tables.
  Store-owned access requires explicit Store scope; application supplies the shared
  synchronous Session and owns commit/rollback. No generic CRUD or public API.
  Forecast/Decision RUNNING-only lifecycle writers and inventory lock/append
  primitives exist; completed/failed run writes are rejected by repository guards.
  S1.7 implements atomic receipt/corrections; full engine validation remains future.
  Contract/manual verification: [PERSISTENCE_ACCESS](features/PERSISTENCE_ACCESS.md).
- Completed: **S1.6 -- Application Contracts + Validated Read/Write Paths**.
  Typed Product create/read, Sales
  insert/history, Forecast/Decision start/complete/fail/read and dated Recipe+lines
  read use S1.5 repositories. By-value outputs, explicit Store context, internal
  errors and application commit/rollback exist. Forecast horizon/Product validation
  and completed same-store Forecast consumption by Decision are implemented;
  full package/evaluation/provenance validation and engines remain absent.
  [APPLICATION_CONTRACTS](features/APPLICATION_CONTRACTS.md) freezes the boundary;
  [S16_VERIFICATION](runbooks/S16_VERIFICATION.md) provides usable local steps.
- Completed: **S1.7 -- Application Coverage + Inventory Transaction Closure**.
  Typed Store/Ingredient create/read,
  SupplierTerm version create/read, atomic Recipe version+lines, positive receipt
  lot+RECEIPT and justified delta COUNT_CORRECTION/MANUAL_ADJUSTMENT exist.
  Scoped lot row locks refresh current balances; exact plain Python domain arithmetic
  rejects negative results. Every mutation owns one balance+movement transaction.
  Money/unit/business-date/event-time/correction conventions are frozen in
  [APPLICATION_CONTRACTS](features/APPLICATION_CONTRACTS.md); reproducible checks
  are in [S17_VERIFICATION](runbooks/S17_VERIFICATION.md).
- Greenfield Competition Edition; no legacy backend was imported.
- Current database: **PostgreSQL**, SQLAlchemy 2.x with psycopg and synchronous
  Session. ADR-007 is ACCEPTED; ADR-003 is SUPERSEDED. The empty Alembic
  baseline is `0001_scaffold`; current head is `0006_forecast_decision_persist`.
- Implemented business tables/models: `users`, `stores`, `store_memberships`,
  `products`, `ingredients`, `recipes`, `recipe_lines`, `suppliers`, `supplier_terms`,
  `sales_daily`, `inventory_lots`, `inventory_movements`, `business_constraints`,
  `forecast_runs`, `forecast_predictions`, `decision_runs` -- sixteen business tables.
  ADR-008 Import Idempotency and Correction Policy and ADR-009 Inventory Mutation
  and Audit Policy are ACCEPTED. S1.7 enforces atomic audited receipt/corrections
  at the trusted internal application boundary. Import/FEFO and full Sales correction
  remain absent. No balance/expiry/audit trigger exists.
  Identity/store membership persistence exists; authentication/authorization does not.
  Plain Python domain implements only exact nonnegative inventory balance arithmetic;
  other domain engines remain absent. S1.5 concrete repositories cover all sixteen
  tables. S1.6/S1.7 internal application use cases exist;
  public business APIs remain not started.
  Remaining Schema v1 is PROPOSAL.
- Runtime: FastAPI app factory, Pydantic v2 settings and typed health schema.
  `GET /health` is the only API operation. `/openapi.json` is framework schema
  metadata. Interactive documentation routes are disabled.
- Import/startup/health do not initialize the database or contact external services.
- Local DB: Docker Compose official PostgreSQL 17, native `pg_isready` healthcheck,
  loopback port 5432 and persistent named volume `shelfcash-postgres-data`.
  Backend remains native Python/venv; no host PostgreSQL install is needed.
- Runtime directories are reserved for uploads and model artifacts.
  No upload/storage feature or API Session dependency is implemented yet.
  Repositories receive a caller-owned synchronous Session.
- Canonical documents created: AGENTS, README, architecture, domain model, Schema v1
  proposal, API contract, decisions/ADRs 001–011, roadmap and testing guide.
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
  or hosted notebook dependency. S1.1/S1.2/S1.3/S1.4 schema clusters are implemented; all
  later computation/public business features remain unimplemented; S1.5/S1.6/S1.7 provide
  internal persistence/application paths. Seed verifies schema, writes no rows.
- Integration tests own only separate `shelfcash_test`, created if absent by the
  local role. Tests run sequentially and never reset normal development state.

## Verification

### S1.7 final acceptance -- CURRENT FACT

S1.7 COMPLETE; S1 overall COMPLETE. Verified on Windows/Python 3.11.9, 2026-10-06:
- New S1.7 targeted coverage: **106 passed** (52 unit/domain, 54 actual PostgreSQL
  integration). Final targeted command after authorized reset/upgrade includes
  unchanged S1.6 regression: **188 passed** (90 unit, 98 integration).
- Supported test.ps1 all: **508 passed** (119 unit, 387 integration, 2 API), no skips;
  one existing upstream Starlette/AnyIO deprecation warning. Full regression run
  count for S1.7: **1**, only at final gate after targeted green; no rerun needed.
- Store/Ingredient/SupplierTerm create/read and Recipe atomic version+lines pass
  scoped validation, exact Decimal, required dates, duplicate/period conflicts and
  typed fresh-session retrieval without silent overwrite/auto-close.
- Positive receipt creates exactly one lot and RECEIPT together. Tracked expiry
  is required, unknown received_date stays NULL, source refs stay paired, unit/cost
  remain canonical, aware supplied events preserve their instant normalized UTC.
- Correcting deltas require COUNT_CORRECTION/MANUAL_ADJUSTMENT and nonblank note;
  negative results fail without new history. Locked materialized balance and
  appended movement commit together. Pure domain arithmetic stays exact despite
  small ambient precision and imports without HTTP/ORM/infrastructure.
- Recipe downstream CHECK after header/line flush leaves no aggregate; receipt
  downstream failures after lot or movement flush leave no partial state; movement
  CHECK after balance flush restores old balance/history. All six new writers'
  commit failures roll back. Caller-owned transactions remain untouched; reads
  neither flush nor commit pending work. Success/failure assertions use fresh Sessions.
- PostgreSQL pg_stat_activity confirms actual second-writer Lock wait; first -5
  and second -7 yield 50 ->45 ->38 with three movements summing to 38. Cached old
  balance also refreshes correctly. Complete S1 operational application chain passes;
  Supplier identity remains the explicitly authorized repository prerequisite.
- Compose PostgreSQL 17.11 healthy; supported development reset, Alembic upgrade/
  current and no-op seed succeed. Final db-status: shelfcash at unchanged head
  0006_forecast_decision_persist, sixteen empty business tables and one revision row.
  Tests own only shelfcash_test. Alembic check detects no new upgrade operations;
  pip check reports no broken requirements.
- 53 pre-S1.7 protected-file hashes match: models/migrations/accepted ADRs/public
  API contract/dependencies/all existing tests unchanged. All 160 pre-existing
  files remain present; changes stay within authorized extensions/docs. Prior S1.6
  WIP is preserved. Application import/construction does not connect to DB.
  Exact generated/live OpenAPI comparison and live health 200/payload pass;
  verifier server stopped. Diff/status, document links, AST and whitespace reviewed.
- Canonical contracts/feature docs/testing/state/roadmap/manual guide distinguish
  current paths from historical schema-only absence claims. No schema/migration,
  public business API, auth/actor enforcement, import/computation engine, commit or
  S2+ implementation. Native POSIX runtime is not claimed. Rollback affects only
  S1.7 application/domain/tests/docs, with no database rollback.

### S1.6 final acceptance -- HISTORICAL INFORMATION

S1.6 COMPLETE. Verified on Windows/Python 3.11.9, 2026-10-06:
- Targeted application command: **82 passed** (38 contract/unit, 44 actual
  PostgreSQL integration). Supported test.ps1 all: **402 passed** (67 unit,
  333 integration, 2 API), no skips, one existing Starlette/AnyIO warning.
- Product typed create/scoped read and canonical Sales insert/inclusive ordered
  history pass with exact Decimal/NULL, conflict/no-overwrite and Store isolation.
  Effective Recipe+typed lines verifies inclusive/open-ended/no-version behavior.
- Forecast/Decision start/complete/fail/read, current locked lifecycle, terminal
  guards, stale cached status refresh, horizon/Product/terminal-time checks and
  completed same-store Forecast consumption pass. Outputs are by-value; JSON/input
  mutations do not change stored values. Supplied fixtures do not claim engines.
- Explicit commit and failure rollback, untouched caller-owned transaction, read
  no-commit/no-autoflush, commit failure and fresh-session persistence pass.
  A Forecast downstream CHECK failure rolls back an already flushed prediction;
  a Decision downstream OperationalError rolls back all flushed completion fields.
  Known named unique conflicts map to application errors; unexpected DB errors
  propagate after rollback. Repository transaction-ownership regressions pass.
- Compose PostgreSQL 17.11 healthy. Supported authorized development reset,
  upgrade/current/seed/status pass; sixteen business tables remain empty at
  0006_forecast_decision_persist with one revision row. Tests own only shelfcash_test.
  Alembic check: No new upgrade operations detected. pip check passes.
- Pre-S1.6 protected hashes confirm models/migrations/accepted ADRs/API_CONTRACT/
  dependencies unchanged. Application import/construction causes no DB connection;
  generated/live OpenAPI equal saved baseline, live health exact unchanged HTTP 200.
  Verification server stopped. Syntax/type/dependency/query/whitespace/link audits
  and diff/status review pass. Initial working tree was clean; no prior WIP removed.
- APPLICATION_CONTRACTS, S16_VERIFICATION and S16_TASK_NOTES document the frozen
  scope, limitations, rollback and manual verification. Current architecture,
  roadmap/testing/schema/domain and affected feature docs explicitly distinguish
  S1.6 application behavior from historical schema/repository-only limitations.
- No schema change/migration, public business API, engine, inventory mutation,
  import/correction, authentication/authorization, commit or S2+ work. Native POSIX
  runtime is not claimed. S1 overall remains IN PROGRESS; remaining gates below.

### S1.5 final acceptance -- HISTORICAL INFORMATION

S1.5 -- Persistence Access Contract + Repository Layer COMPLETE.
Verified on Windows/Python 3.11.9, 2026-10-05:
- Targeted repository integration + unit contract/guard command: **80 passed**
  (65 real PostgreSQL integration, 15 unit). Supported test.ps1 all: **320 passed**
  (289 integration, 29 unit, 2 API), no skips; one existing Starlette/AnyIO warning.
- All sixteen tables are covered by nine domain modules / ten concrete repositories.
  Store-scoped reads, dated Recipe/SupplierTerm/Constraint queries, chronological
  Sales history, inventory lot/movement reads and caller transactions pass.
- RUNNING Forecast/Decision completion/failure, RUNNING-only prediction append,
  repeated/terminal-write rejection, copied JSON, Store isolation, row-lock lifetime,
  stale cached status refresh and commit/close/fresh-session reload pass.
  Multi-repository rollback leaves neither run; inventory movement failure rolls
  back the flushed lot change. No operational mutation or computation service.
- Compose PostgreSQL 17.11 healthy. Authorized supported development reset and
  Alembic upgrade pass; head stays 0006_forecast_decision_persist, sixteen empty
  business tables. Integration fixtures own only shelfcash_test.
- Alembic check: No new upgrade operations detected. All models/migrations/accepted
  ADRs/API_CONTRACT/pyproject hashes match the start-of-review baseline. No migration.
- App import, generated and live OpenAPI equal baseline; live health returns exact
  unchanged HTTP 200 payload. Verification server stopped. pip check and syntax/
  transaction-ownership/structure audits pass; diff/status reviewed, WIP preserved.
- Known access limit: tracked ORM/direct SQL mutation can bypass repository guards;
  full package/horizon/authorization and audited inventory mutation remain future.
  S1 overall IN PROGRESS under ROADMAP. No business API, engines, commit or S2+ work.

### Earlier S1.5 insert/read verification -- HISTORICAL INFORMATION

S1.5 insert/read baseline verified on Windows/Python 3.11.9, 2026-10-05:
- `./scripts/test.ps1 all`: **310 passed** (29 unit, 279 integration, 2 API),
  one existing Starlette/AnyIO deprecation warning, no skips. New S1.5 coverage:
  55 repository integration and 15 unit tests. Earlier standalone targeted run:
  47 passed before final coverage additions; all final additions pass in full suite.
- All sixteen tables round-trip through concrete repositories and close/fresh
  Session reads. Explicit Store scope, identity-map isolation, exact Decimal/NULL/
  JSON, inclusive/open-ended/inactive date queries, duplicate/no-upsert/new-row
  guards, caller transaction visibility/rollback and same-store FK failures pass.
- Inventory fixture transactions prove valid balance+movement commit, failed
  movement rolls back an already flushed balance, and scoped SELECT FOR UPDATE
  refreshes cached balance and holds its lock until caller rollback. These tests
  do not implement an inventory mutation service. Generated Forecast parent flush
  and predictions remain rollbackable; no append-to-existing-run writer exists.
- Protected-file SHA-256 checks match pre-S1.5: all models/migrations, accepted
  ADRs, API_CONTRACT and pyproject unchanged. Generated OpenAPI exactly matches
  pre-S1.5. Existing health/import/domain independence and migration/metadata tests
  pass. pip check passes. No schema/public API/dependency/engine implementation.
- Read-only supported db-status reports development shelfcash at head
  0006_forecast_decision_persist, sixteen empty business tables and one revision row;
  no development reset or business seed write. Tests own only shelfcash_test.
- Contract and reproducible manual verification are in PERSISTENCE_ACCESS and
  S15_TASK_NOTES; current docs/roadmap/testing/runbook updated, prior WIP preserved.
  New-file syntax and scope/diff/whitespace reviewed; no commit or next slice.
  PowerShell runtime verified; POSIX wrappers unchanged, no new POSIX runtime claim.
- Limit: repositories return tracked mutable ORM rows; completed-run lifecycle/
  immutability, full package/horizon validation and audited operational inventory
  mutation remain future authorized use cases. S1 overall remains IN PROGRESS.

### S1.4 acceptance -- HISTORICAL INFORMATION

S1.4 verified on Windows/Python 3.11.9, 2026-10-05:
- Targeted test_forecast_decision_persistence.py: **58 passed**, actual isolated
  shelfcash_test. Run status/windows/time/metadata, finite ordered quantiles, business
  key, same-store references, exact fresh-session JSON/Decimal, completed minimum
  fields, partial/failed outputs, JSON null rejection, independent copied input values,
  same-fingerprint reruns and zero/equal quantiles tested. Fixtures are not engine output.
- `./scripts/test.ps1 all`: **240 passed** (14 unit, 224 integration, 2 API), one
  existing Starlette/AnyIO deprecation warning, no skips. All previous tests preserved;
  metadata/migration agreement and fresh/down/up succeed. Initial bootstrap assertion
  expecting thirteen tables was updated to sixteen; final complete rerun is green.
- Compose config/up --wait/ps pass; PostgreSQL 17.11 healthy. Development reset,
  upgrade/current/status/seed pass at 0006_forecast_decision_persist, sixteen empty
  business tables and one revision row. S14_VERIFICATION read-only column/constraint/
  index/row commands execute successfully; three run row queries return [].
- Generated/live OpenAPI exactly matches saved pre-S1.1 baseline. App/model/domain
  imports with DB connection forbidden pass. Live /health returns exact unchanged
  HTTP 200 payload; verification server stopped. pip check passes.
- Pre-task hashes confirm prior models/migrations 0001-0005/accepted ADRs/API_CONTRACT
  unchanged; only model registration is extended. Scope/diff/status/whitespace and
  new-file syntax reviewed. No additional tables, dependencies, API, repository,
  service, computation, snapshot builder/hasher or S2 implementation; no commit.
- PowerShell commands runtime verified. POSIX wrappers unchanged; historical syntax
  validation only, no native POSIX runtime claim. No remaining S1.4 acceptance blocker.

### S1.3.1 acceptance -- HISTORICAL INFORMATION

S1.3.1 verified on Windows/Python 3.11.9, 2026-10-05:
- Targeted test_data_semantics_correction.py: **9 passed**, actual isolated
  shelfcash_test. ORM NULL/raw SQL omitted/NULL receipt persistence via fresh sessions,
  no fabricated snapshot date/default, strict supplier NULL rejection, exact pack cost,
  known-row downgrade/re-upgrade and transactional refusal with unknown receipt dates.
- `./scripts/test.ps1 all`: **182 passed** (14 unit, 166 integration, 2 API),
  one existing Starlette/AnyIO deprecation warning, no skips. All S1.1/S1.2/S1.3
  regressions and metadata/migration agreement pass. Fresh upgrade and downgrade/
  re-upgrade on isolated PostgreSQL pass. No tests mutate normal development state.
- Compose config/up --wait/ps pass; PostgreSQL 17.11 healthy. Development reset,
  upgrade/current/status/seed pass at 0005_data_semantics_correction; thirteen empty
  business tables and one Alembic row. Read-only inspection confirms received_date
  nullable/no default, strict supplier columns nonnullable/no defaults and expiry check.
- Application/model/domain imports with psycopg connection forbidden pass. Generated
  and live OpenAPI exactly match saved pre-S1.1 baseline. Live /health is HTTP 200
  with unchanged payload; verification server stopped. pip check passes.
- Scope/diff/status/whitespace reviewed. Pre-task hashes prove all prior models except
  InventoryLot, all migrations including 0004, accepted ADRs including 008/009 and
  API_CONTRACT preserved byte-for-byte. No new tables, services, repositories, import
  implementation or public endpoints. Existing S1.3 WIP preserved; no commit.
- PowerShell runtime verified; POSIX wrappers unchanged, historical syntax-only
  verification retained. No POSIX runtime claim. No remaining acceptance blocker.

### S1.3 acceptance -- HISTORICAL INFORMATION

S1.3 verified on Windows/Python 3.11.9, 2026-10-05:
- Targeted `test_supplier_operational_constraints.py`: **80 passed**, actual isolated
  shelfcash_test. Six-model commit/close/fresh-session reload, many-to-many terms,
  version/active overlap, pack/minimum/cost/lead/shelf-life, canonical sales identity,
  lot expiry/unit/store, movement type/sign/reference/lot consistency, controlled
  scope/registry and NULL STORE uniqueness tested. Boundaries/limits explicit.
- `./scripts/test.ps1 all`: **173 passed** (14 unit, 157 integration, 2 API), one
  existing Starlette/AnyIO deprecation warning, no skips. All prior S1.1/S1.2 tests
  remain passing; metadata/migration comparison passes. Fresh reset/upgrade and
  0004->0003->head succeed on shelfcash_test; bootstrap reaches scaffold/base and
  re-upgrades. No test mutates ordinary development state.
- Compose config/up --wait/ps pass; PostgreSQL 17.11 healthy. Development reset,
  upgrade/current, seed/status pass at 0004_supplier_ops_constraints. Exactly thirteen
  empty business tables and one Alembic revision row. S13_VERIFICATION's actual
  read-only inspection commands execute successfully, including columns/constraints
  and six domain row queries returning []. No S1.4/import/order tables present.
- App/model/domain import with psycopg connection forbidden passes; generated
  OpenAPI exactly matches saved pre-S1.1 baseline. Live /health HTTP 200 unchanged;
  live /openapi.json identical, verification server stopped afterward.
- pip check passes. Diff/status/scope/whitespace reviewed; prior business models and
  migrations, API_CONTRACT, API/domain/repository code and dependencies unchanged.
  ADR-008/009 indexed ACCEPTED, no commit, no remaining S1.3 acceptance blocker.
- PowerShell workflow runtime-verified; POSIX wrappers unchanged, previous syntax
  checks only. No POSIX runtime verification claimed for this slice.

### S1.2 acceptance — HISTORICAL INFORMATION

S1.2 verified on Windows/Python 3.11.9, 2026-10-05 (state before S1.3):
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

## Next slice -- PROPOSAL

S1.7 implements the remaining authorized S1 operational contracts and writes.
S1.7 and S1 are COMPLETE after final acceptance; no canonical operational S1
gate remains open. The next canonical phase is
**S2 -- Forecast**, PROPOSAL / NOT STARTED. Freeze forecast cutoff/horizon,
baseline/quantile behavior and provenance with separately authorized work.
No next slice, business API or engine starts automatically.

## Current schema-only limitations — CURRENT FACT

- Repository writers guard RUNNING-only transitions and prediction append.
  Direct tracked ORM/SQL mutation can bypass these guards. S1.6 validates prediction
  horizon membership and completed forecast consumption in its application paths.
  Full package/evaluation validation, sanitization
  and authorized snapshot capture remain future service responsibilities (ADR-011).
  DB enforces local state/shape/FKs but has no immutability/horizon triggers.
- S1.5 repositories expose explicit insert/read/lifecycle primitives, no arbitrary
  completed-row update/delete writer. Reads are tracked mutable ORM rows; direct
  Session/SQL can bypass policy. S1.6 returns by-value outputs and guards its lifecycle
  paths; wider immutable application boundaries remain future.
- Standalone forecast input retention, artifact service, deterministic hashing and
  full versioned algorithm/package schemas remain future engine slice requirements.
  Fingerprint alone is not captured training content or a replay guarantee.

- Inventory balance and ledger are independently stored. S1.7 receipt/correction
  paths require movement and balance in one locked application transaction and
  reject negative results. They append history without edit/delete. Direct ORM/SQL
  can bypass policy: no append-only/reconciliation/audit trigger or actor permission
  exists. Optional paired source refs are retained; authentication is not implemented.
- S1.7 tracked Ingredient receipts require expiry and both-known dates enforce order;
  unknown receipt remains NULL. DATE facts are explicit and separate from UTC event
  instants. No future-date derivation, automatic expiry or engine cutoff is invented.
  All supplied money inherits Store.currency; no budget writer is in this slice.
  Future budget boundaries must enforce the unchanged budget unit=Store.currency rule.
- No import parser/hash/classification/mode/correction/provenance engine, full Sales
  correction, FEFO, Forecast or Decision computation. No public business API.
  Internal persistence access is documented in features/PERSISTENCE_ACCESS.md.

## Known unresolved decisions — PROPOSAL

- Future public Store API fields, validation and transport error contract. S1.1 UUID storage and
  timezone/currency defaults are frozen; public identifier/payload contracts are not.
- Authentication/bootstrap and minimum store isolation needed before data exposure.
- Engine-specific currency rounding, explicit unit conversions and Vietnam
  forecast/expiry business-day cutoff. S1.7 already freezes exact Decimal,
  Store.currency inheritance, exact units and separate DATE/aware UTC instants.
- Recipe resolver/API behavior beyond frozen inclusive date selection; forecast
  baseline/quantile calibration and simulator
  time granularity, objectives/tie breaks and constraint infeasibility policy.
- Decision package structure beyond required schema version 1 and historical context.
- Mapping confidence thresholds and human approval rules.

No known technical debt is recorded in the initial scaffold. These unresolved choices
are not accepted architecture and must not be silently treated as implementation facts.
