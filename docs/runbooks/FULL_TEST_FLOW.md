# Full local verification flow

CURRENT FACT (S2.3): isolated baseline persistence/replay checks and manual inspection
are in [S23_VERIFICATION](S23_VERIFICATION.md). No development reset is needed.
Historical setup/reset instructions below remain explicit destructive workflows, not
a prerequisite to running this slice against an existing development database.

## S2.1 contract-only verification — CURRENT FACT

After local PostgreSQL is healthy, run the targeted command in
[FORECAST_EXECUTION](../features/FORECAST_EXECUTION.md), its executable synthetic
example and full `./scripts/test.ps1 all` once at the final gate. Existing integration
fixtures plus the S1 empty-completion regression own only shelfcash_test and assert
fresh-session state. No development reset is needed for S2.1; fresh setup below is
unchanged. There is no forecast computation/end-to-end execution or business HTTP
operation. See CURRENT_STATE for exact acceptance evidence.

CURRENT FACT: this runbook verifies the PostgreSQL scaffold and S1.1/S1.2/S1.3/S1.4 persistence
schema on repository-local infrastructure. No business API/scenarios or demo seed
entities exist. ACCEPTED DECISION: ADR-007 uses
Docker Compose PostgreSQL, psycopg, synchronous SQLAlchemy and explicit Alembic.
Prerequisites: Python 3.11+, Docker with Linux containers/Compose, and Docker running.
No host PostgreSQL installation, hosted notebook or provider credential is needed.
Run from `backend/`; execute commands one at a time and stop on errors.

## Windows PowerShell: fresh environment

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[dev]'
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker compose config
docker compose up -d postgres
docker compose up -d --wait --wait-timeout 90 postgres
docker compose ps
.\scripts\db_status.ps1 -AllowUnmigrated
# Stop backend/database clients before resetting. Back up any wanted dev state.
.\scripts\reset_db.ps1
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\alembic.exe current
.\scripts\seed_demo.ps1
.\scripts\db_status.ps1
.\scripts\test.ps1 all
.\.venv\Scripts\python.exe -m pip check
```

`.env` must match `.env.example` for the documented local setup. Settings read it;
exported environment variables take precedence. If updating an existing `.env`,
set the new PostgreSQL `DATABASE_URL`/`TEST_DATABASE_URL` explicitly and add the
`POSTGRES_*` entries. Keep development credentials consistent with Compose.
Native URL defaults use `127.0.0.1` to match the published IPv4 port and avoid
Windows localhost IPv6 fallback delays; hostnames remain environment-configurable.
The image reads database/user/password on first volume initialization; changing
them later does not rewrite existing roles/databases. See DATABASE_RESET for recovery.

Expected results:

- Compose config succeeds; service `postgres` is healthy on `127.0.0.1:5432`.
- Initial status reports `reachable: true`, database `shelfcash`, schema `public`.
  On first startup: `at_head: false`, revisions `[]`, tables `{}`. The optional
  `-AllowUnmigrated` flag permits this; default status requires migration head.
- Reset recreates guarded local `public` and runs migrations. `alembic current`
  prints `0006_forecast_decision_persist (head)`; repeated upgrade is safe.
- Status after reset reports `at_head: true`, revisions `["0006_forecast_decision_persist"]`,
  tables `{"alembic_version": 1, "users": 0, "stores": 0, "store_memberships": 0, "products": 0, "ingredients": 0, "recipes": 0, "recipe_lines": 0, "suppliers": 0, "supplier_terms": 0, "sales_daily": 0, "inventory_lots": 0, "inventory_movements": 0, "business_constraints": 0, "forecast_runs": 0, "forecast_predictions": 0, "decision_runs": 0}`.
  Exactly sixteen business tables exist; no real/demo business data is seeded.
- Seed says `No business seed data`, verifies the current schema and writes no rows.
  Optional `.\scripts\reset_db.ps1 -Seed` combines reset/migration/seed.
- All automated tests pass. Integration tests create/own only `shelfcash_test`,
  never reset `shelfcash`; missing PostgreSQL causes failure, not a silent skip.
- `pip check` reports no broken requirements.

Start FastAPI in the same terminal:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In a second PowerShell terminal at `backend/`:

```powershell
$health = Invoke-RestMethod http://127.0.0.1:8000/health
if ($health.status -ne 'ok' -or $health.service -ne 'shelfcash-backend') { throw 'Unexpected health payload' }
$schema = Invoke-RestMethod http://127.0.0.1:8000/openapi.json
if (($schema.paths.PSObject.Properties.Name -join ',') -ne '/health') { throw 'Unexpected OpenAPI paths' }
.\scripts\db_status.ps1
.\.venv\Scripts\python.exe -c "from app.config import Settings; from app.infrastructure.database.engine import create_database_engine; from sqlalchemy import text; e=create_database_engine(Settings()); c=e.connect(); print(c.execute(text('SELECT version_num FROM public.alembic_version')).all()); print(c.execute(text('SELECT tablename FROM pg_tables WHERE schemaname = :schema ORDER BY tablename'), {'schema':'public'}).all()); c.close(); e.dispose()"
```

Expected SQL output: `[('0006_forecast_decision_persist',)]` and
`[('alembic_version',), ('business_constraints',), ('decision_runs',), ('forecast_predictions',), ('forecast_runs',), ('ingredients',), ('inventory_lots',), ('inventory_movements',), ('products',), ('recipe_lines',), ('recipes',), ('sales_daily',), ('store_memberships',), ('stores',), ('supplier_terms',), ('suppliers',), ('users',)]`.
Status before/after HTTP calls is identical; health is liveness and writes no DB
state. Interactive documentation routes remain disabled. Stop FastAPI with Ctrl+C.

## POSIX shell equivalent

Provided scripts share the same Python implementation. Check CURRENT_STATE/TESTING
for actual platform verification: syntax validation is not runtime execution.

```sh
set -eu
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
if [ ! -f .env ]; then cp .env.example .env; fi
docker compose config
docker compose up -d postgres
docker compose up -d --wait --wait-timeout 90 postgres
docker compose ps
sh scripts/db_status.sh --allow-unmigrated
# Stop backend/database clients and back up wanted local state first.
sh scripts/reset_db.sh
.venv/bin/alembic upgrade head
.venv/bin/alembic current
sh scripts/seed_demo.sh
sh scripts/db_status.sh
sh scripts/test.sh all
.venv/bin/python -m pip check
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In a second terminal at `backend/`:

```sh
set -eu
.venv/bin/python -c 'import json, urllib.request; h=json.load(urllib.request.urlopen("http://127.0.0.1:8000/health")); assert h == {"status":"ok","service":"shelfcash-backend"}; s=json.load(urllib.request.urlopen("http://127.0.0.1:8000/openapi.json")); assert set(s["paths"]) == {"/health"}; print("HTTP contracts verified")'
sh scripts/db_status.sh
.venv/bin/python -c 'from app.config import Settings; from app.infrastructure.database.engine import create_database_engine; from sqlalchemy import text; e=create_database_engine(Settings()); c=e.connect(); assert c.execute(text("SELECT version_num FROM public.alembic_version")).all() == [("0006_forecast_decision_persist",)]; assert c.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = :schema ORDER BY tablename"), {"schema":"public"}).all() == [("alembic_version",), ("business_constraints",), ("decision_runs",), ("forecast_predictions",), ("forecast_runs",), ("ingredients",), ("inventory_lots",), ("inventory_movements",), ("products",), ("recipe_lines",), ("recipes",), ("sales_daily",), ("store_memberships",), ("stores",), ("supplier_terms",), ("suppliers",), ("users",)]; c.close(); e.dispose(); print("Persisted schema verified")'
```

Expected results match Windows; `sh scripts/reset_db.sh --seed` is the combined
reset/migration/seed variant. Stop the server with Ctrl+C.

S1.3 domain fixtures/constraint inspection and schema limitations are in
[S13_VERIFICATION](S13_VERIFICATION.md). Inventory balance/movement atomic writes,
import correction and FEFO are not implemented; HTTP liveness does not prove them.

## Failure/reset/retry and future completion gate

Use [DATABASE_RESET](DATABASE_RESET.md) for guarded reset and error handling, and
[DEMO_SETUP](DEMO_SETUP.md) for current demo preparation. No Docker volume deletion
is needed for the normal workflow.

ACCEPTED DECISION: major features require implementation, automated tests, relevant
integration/persistence tests, usable manual steps, deterministic inputs where
practical, inspection/expected database state, and canonical feature documentation.
Verify committed rows through a fresh session, alongside API/application results.
HTTP 2xx alone is insufficient; no roadmap slice is complete with unusable steps.

PROPOSAL: add business flows with their authorized slices. Imports must verify job,
mapping/profile and canonical rows after processing. Computation features need direct
invariant tests and deterministic scenarios; preserve snapshots only where required.
LLM output must never be a business correctness oracle.

S1.3.1 receipt-date/source-semantics regression and read-only column inspection:
[S131_VERIFICATION](S131_VERIFICATION.md). Unknown receipt remains NULL; strict
supplier inputs have no fallback defaults. Warning/Import APIs remain unimplemented.

S1.4 run schema/fixture verification: [S14_VERIFICATION](S14_VERIFICATION.md).
Completed immutability is future-service policy, not a DB trigger; no engine exists.

S1.5 internal repository verification: [PERSISTENCE_ACCESS](../features/PERSISTENCE_ACCESS.md).
Run its targeted tests after the normal setup above; they own only shelfcash_test,
exercise caller-owned transactions and assert committed values through fresh sessions.
Development reset/seed and health/OpenAPI behavior are unchanged.

S1.6 internal typed application verification:
[APPLICATION_CONTRACTS](../features/APPLICATION_CONTRACTS.md) and
[S16_VERIFICATION](S16_VERIFICATION.md). Run its targeted application/unit tests
after the same setup; they use only shelfcash_test and verify committed/rolled-back
Forecast/Decision output through fresh Sessions. No business route or engine exists.

## S1.7 operational acceptance -- CURRENT FACT

[S17_VERIFICATION](S17_VERIFICATION.md) supplies the targeted operational checks,
individual manual scenarios and expected fresh-session state. Run targeted tests
first and full regression once at the final gate (repeat only after fixing a full
suite failure). S1.7 implements atomic receipt/corrections and Recipe version writes;
earlier schema-slice absence statements are HISTORICAL INFORMATION where superseded.
No Import/Forecast/Decision/FEFO computation or public business API is implemented.


## S2 trained evaluation/artifact/replay -- CURRENT FACT

Install declared pinned ML dependencies with the normal editable setup. Run
`python -m scripts.forecast_model --help` for pure synthetic/backtest/train/infer and
internal capture/execute/replay commands; see ../features/FORECAST_TRAINED.md.
`python -m scripts.verify_forecast_trained` is a labelled synthetic PostgreSQL demo,
only shelfcash_test, requires already-current head, never resets/migrates. Leaves
fixtures/artifacts for inspection. Development schema need not be upgraded for tests.
Quality on real observations remains NOT EVALUATED; test passing is not accuracy.
