# Scaffold and local database bootstrap

## Status and purpose

CURRENT FACT: S0 scaffold with S0.2 persistence correction; runtime acceptance
evidence/status is in CURRENT_STATE. Provides typed liveness, OpenAPI metadata,
PostgreSQL/Alembic infrastructure and local verification commands. The original S0
baseline was empty; S1.1 now adds only the
[identity/store schema](STORE_IDENTITY.md). No business APIs, authentication,
imports or computation are implemented.

## Invariants and relevant ADRs

ACCEPTED DECISION: ADR-002 retains one modular monolith; ADR-007 retains PostgreSQL,
psycopg, synchronous SQLAlchemy, Alembic and Compose named volume. ADR-001 keeps
future business truth independent of LLM. CURRENT FACT: import/startup/health do
not connect to the DB or providers. Guarded reset affects only local `public` in
`shelfcash`/`shelfcash_test`; test environment permits only the latter.

## API contract and persistence

See [API_CONTRACT](../API_CONTRACT.md). `GET /health` returns HTTP 200 and
`{"status":"ok","service":"shelfcash-backend"}` by default. `/openapi.json`
has only `/health` in paths. Interactive documentation remains disabled.
Health reads/writes no tables. Alembic writes `public.alembic_version`, one row
`0002_identity_store` at current head (`0001_scaffold` is historical baseline).
Status/seed read it through a fresh PostgreSQL read-only transaction.
Seed reports no business data and writes no rows.

## Happy path, inspection and expected state

Follow [FULL_TEST_FLOW](../runbooks/FULL_TEST_FLOW.md): start Compose, await health,
check reachability, reset/migrate/seed, run tests, start FastAPI, assert health and
OpenAPI, then inspect persisted PostgreSQL state through status and direct SQL.
Expected `public` tables: `alembic_version` (one row `0002_identity_store`) plus
empty `users`, `stores`, `store_memberships` after reset. No later tables exist.
No manual Docker exec or host database client is needed for inspection.

## Failure paths and reset/retry

Connection failures, unsafe reset targets, migration failures, invalid category,
missing environment or stale revisions return nonzero with an error message.
Reachable unmigrated status needs the explicit `AllowUnmigrated` option; seed
always requires head. HTTP health can succeed while PostgreSQL is unavailable.
See [DATABASE_RESET](../runbooks/DATABASE_RESET.md) for target guards, lock timeout,
transaction rollback, retry behavior and named-volume retention. Stop concurrent
DB users before reset; save local state first if needed.

## Automated tests and fixtures

- Unit: application/domain independence, config/driver, lazy engine/import/health,
  reset-target guards and invalid category.
- API: original typed health/OpenAPI/route inventory contract.
- Integration: actual local `shelfcash_test` connect/query/synchronous Session,
  migration up/down, fresh persisted reads, repeat reset/seed, rejection without
  data loss and reachable unmigrated status without state creation.

No fake DB replaces PostgreSQL integration checks. Fixtures are fixed/isolated and
never reset `shelfcash`. Tests run sequentially and own the test DB's public schema.
No hosted notebook, LLM oracle or business input fixture is needed for S0.

## Known limitations

No business seed, business API flow or e2e suite exists. PROPOSAL: business fixtures
and golden scenarios arrive with their authorized slices. PowerShell uses
`.venv/Scripts/python.exe`; POSIX uses `.venv/bin/python`. Runtime verification for
POSIX must be distinguished from syntax validation (see TESTING/CURRENT_STATE).
Only dedicated local default database names/hosts support reset. No backend Docker
image or DB HTTP administration endpoint is introduced.
