# Scaffold and local database bootstrap

## Status and purpose

CURRENT FACT: scaffold infrastructure remains part of the modular monolith.
`app/main.py` now composes Auth/Store/Staff, Import, Inventory, Planning, Assistant,
PDF and collaboration APIs. Follow [GETTING_STARTED](../GETTING_STARTED.md) for
current local bootstrap and [CURRENT_STATE](../CURRENT_STATE.md) for source/runtime
status. Interactive docs remain disabled; OpenAPI is available separately.

HISTORICAL INFORMATION: the original S0/S0.2 baseline was empty. S1.1/S1.2/S1.3 added the
[identity/store](STORE_IDENTITY.md) and [catalog/recipe](CATALOG_RECIPE.md) schemas plus
[S1.3 supplier/operational/constraints](../runbooks/FULL_TEST_FLOW.md). No business APIs, authentication,
imports or computation were implemented at the S0 checkpoint. The bootstrap/test
details below retain their S0/S1 scope; they are not current setup expectations.

## Invariants and relevant ADRs

ACCEPTED DECISION: ADR-002 retains one modular monolith; ADR-007 retains PostgreSQL,
psycopg, synchronous SQLAlchemy, Alembic and Compose named volume. ADR-001 keeps
business truth independent of LLM. CURRENT FACT: module import/health do not connect
to DB/providers; configured lifespan workers can use DB after startup. Source:
`app/main.py::create_app`. `scripts/dev.py` guards resets with explicit local DB/role
allowlists; [TESTING](../TESTING.md) owns current profile selection.

## API contract and persistence

CURRENT FACT: see [API_CONTRACT](../API_CONTRACT.md). `GET /health` returns HTTP 200 and
`{"status":"ok","service":"shelfcash-backend"}` by default. `/openapi.json`
included only `/health` at S0; current operations are in [OpenAPI](../handoff/openapi.json).
Health reads/writes no tables. HISTORICAL INFORMATION: Alembic wrote
`public.alembic_version`, one row `0006_forecast_decision_persist` at S1.4
(`0001_scaffold` was the initial baseline).
Status/seed read it through a fresh PostgreSQL read-only transaction.
The scaffold seed reported no business data and wrote no rows; later optional
synthetic account/data seeds are separate workflows in the runbook.

## Happy path, inspection and expected state

HISTORICAL INFORMATION — S0/S1 verification recipe, not current customer setup:
the [FULL_TEST_FLOW](../runbooks/FULL_TEST_FLOW.md) checkpoint used Compose/health,
reachability checks, reset/migrate/seed, tests and FastAPI, then inspected
persisted PostgreSQL state through status and direct SQL.
Expected `public` tables: `alembic_version` (one row `0006_forecast_decision_persist`) plus
empty `users`, `stores`, `store_memberships`, `products`, `ingredients`, `recipes`,
`recipe_lines`, `suppliers`, `supplier_terms`, `sales_daily`, `inventory_lots`,
`inventory_movements`, `business_constraints`, `forecast_runs`, `forecast_predictions`, `decision_runs` after reset. S1.4 run tables also exist; no Import/Order/What-if tables.
No manual Docker exec or host database client is needed for inspection.

## Failure paths and reset/retry

Connection failures, unsafe reset targets, migration failures, invalid category,
missing environment or stale revisions return nonzero with an error message.
Reachable unmigrated status needs the explicit `AllowUnmigrated` option; seed
always requires head. HTTP health can succeed while PostgreSQL is unavailable.
See [DATABASE_RESET](../runbooks/FULL_TEST_FLOW.md) for target guards, lock timeout,
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

HISTORICAL INFORMATION: S0 had no business seed, business API flow or e2e suite;
business fixtures/goldens were future work at that checkpoint. Current acceptance
limits are in [CURRENT_STATE](../CURRENT_STATE.md). PowerShell uses
`.venv/Scripts/python.exe`; POSIX uses `.venv/bin/python`. Runtime verification for
POSIX must be distinguished from syntax validation (see TESTING/CURRENT_STATE).
Only dedicated local default database names/hosts support reset. No backend Docker
image or DB HTTP administration endpoint is introduced.
