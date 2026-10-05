# Scaffold and local database bootstrap

## Status and purpose

CURRENT FACT: implemented S0. Provides typed liveness, OpenAPI metadata and an empty
SQLite/Alembic baseline, plus local verification commands. No business features,
authentication, imports or computation are implemented.

## Invariants and relevant ADRs

ACCEPTED DECISION: [ADR-002](../adr/ADR-002-modular-monolith.md) retains one modular
monolith; [ADR-003](../adr/ADR-003-sqlite-persistence.md) retains synchronous SQLite
and explicit migrations. [ADR-001](../adr/ADR-001-backend-business-authority.md)
keeps future business truth independent of LLM. CURRENT FACT: import/startup/health
do not connect to the database or providers. Reset requires development environment
and the canonical `backend/runtime/shelfcash.db` path; linked paths and SQLite
sidecars are refused. Stop database users before reset.

## API contract and persistence

See [API_CONTRACT](../API_CONTRACT.md). `GET /health` returns HTTP 200 with
`{"status":"ok","service":"shelfcash-backend"}` under default configuration.
`GET /openapi.json` has only `/health` in `paths`. Health writes/reads no tables.
Alembic upgrade writes `alembic_version`, with one row `0001_scaffold`.
Status/seed read it through a fresh read-only SQLite connection. Seed writes no
rows and explicitly reports that business seed data does not yet exist.

## Happy path and manual verification

Follow [FULL_TEST_FLOW](../runbooks/FULL_TEST_FLOW.md): reset with seed, inspect
revision/integrity/table counts, run tests, start backend and assert health/OpenAPI,
then inspect database again. Expected persisted state is exactly
`alembic_version: 1`; there are no business tables. The runbook includes direct SQL
inspection through Python's built-in sqlite3, so no separate database client is needed.

## Failure paths and reset/retry

- Missing database, stale revision, integrity or foreign-key violations: status
  exits nonzero. Health may still succeed because it is liveness only.
- Invalid category, invalid configuration, migration failure or missing virtual
  environment: commands fail with a nonzero exit and error message.
- Non-development or noncanonical reset target: reset fails before deletion.
- SQLite sidecar present: close database users, resolve/checkpoint the database,
  then retry. Do not manually delete active sidecars.
- Reset deletes the canonical development DB, then migrates it. Migration failure
  may leave a partial database; correct the error and retry reset. Preserve a backup
  beforehand if local state is needed. Uploads/model artifacts remain untouched.

## Automated tests and fixtures

`tests/unit/test_smoke.py`: application import and domain independence.
`tests/api/test_health.py`: health schema, routes and OpenAPI contract.
`tests/integration/test_database_bootstrap.py`: upgrade/downgrade, revision and
foreign-key enforcement with synchronous Session.
`tests/integration/test_verification_commands.py`: process-level rejection/status/
seed checks, fresh persisted reads, repeat reset and sidecar protection.
Fixtures use temporary SQLite and fixed expected values; no hosted notebook,
provider, random data or credentials are required.

## Known limitations

CURRENT FACT: no business seed, representative business API flow or e2e suite exists.
PROPOSAL: business fixtures and golden scenarios arrive with their authorized slices.
PowerShell scripts use `.venv/Scripts/python.exe`; POSIX scripts use `.venv/bin/python`.
Reset supports only the canonical development file; status can inspect another
configured file-backed SQLite database. Database health is verified by status, not
the HTTP health endpoint. Stop concurrent processes; reset is a local offline workflow.
