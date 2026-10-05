# Current state

Classification: CURRENT FACT unless explicitly marked otherwise.

- Project phase: **SCAFFOLD / ARCHITECTURE FREEZE** (S0).
- Greenfield Competition Edition; no legacy backend was imported.
- Current database: **SQLite**, synchronous SQLAlchemy 2.x. The empty Alembic
  baseline is `0001_scaffold`; only `alembic_version` is created by upgrade.
- Business implementation status: **not started**. Domain packages are empty.
- Runtime: FastAPI app factory, Pydantic v2 settings and typed health schema.
  `GET /health` is the only API operation. `/openapi.json` is framework schema
  metadata. Interactive documentation routes are disabled.
- Import/startup/health do not initialize the database or contact external services.
- Runtime directories are reserved for SQLite, uploads and model artifacts.
  No upload/storage feature, Session dependency or repository is implemented yet.
- Canonical documents created: AGENTS, README, architecture, domain model, Schema v1
  proposal, API contract, decisions/ADRs 001–006, roadmap and testing guide.
- Local verification tooling: PowerShell/POSIX test, reset, seed and DB status
  scripts. Reset is restricted to development and canonical `runtime/shelfcash.db`,
  applies migrations and optionally checks the seed baseline. Status verifies
  integrity/foreign keys/revision and table counts via a fresh read-only connection.
- Tests are organized into unit/integration/api/e2e/fixtures; no e2e/business seed
  or golden business scenarios exist yet. Seed reports no business rows written.
- [Full test flow](runbooks/FULL_TEST_FLOW.md) and
  [scaffold feature guide](features/SCAFFOLD.md) provide manual HTTP and persisted
  DB verification. All execution/testing/demo preparation remains local; no Kaggle
  or hosted notebook dependency. Accepted SQLite ADR-003 is unchanged.

## Verification

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

Begin S1 with one Store create/read path through API → application → SQLite, with
explicit Pydantic schemas, one migration, store isolation groundwork and acceptance
tests. Freeze the precise contract first. This does not authorize starting S1.

## Known unresolved decisions — PROPOSAL

- S1 Store API fields, identifier format, validation and error contract.
- Authentication/bootstrap and minimum store isolation needed before data exposure.
- Currency precision/rounding, units/conversions and Vietnam business-date cutoff.
- Recipe version selection, forecast baseline/quantile calibration and simulator
  time granularity, objectives/tie breaks and constraint infeasibility policy.
- Decision package structure beyond required schema version 1 and historical context.
- Mapping confidence thresholds and human approval rules.

No known technical debt is recorded in the initial scaffold. These unresolved choices
are not accepted architecture and must not be silently treated as implementation facts.
