# S0.2 persistence correction task notes

Classification: HISTORICAL INFORMATION for the completed S0.2 correction. The
authorized scope/observations below preceded S1.1; later identity/store schema
implementation is documented in S11_TASK_NOTES and CURRENT_STATE.

- Observed state: clean working tree; S0 scaffold and local verification harness,
  no business models/tables/data, empty `0001_scaffold`, no backend Dockerfile.
- Frozen public contract: `/health` and generated OpenAPI remain identical;
  `/openapi.json` remains metadata, interactive documentation disabled.
- Authority: preserve ADR-003 as superseded history; accept ADR-007 for PostgreSQL,
  SQLAlchemy 2.x synchronous Session, psycopg, Alembic and local Compose named volume.
- Acceptance: real PostgreSQL connectivity, fresh migration/round-trip/downgrade,
  guarded reset, deterministic no-op seed, read-only status, import safety, existing
  API/domain tests, categorized runners and usable manual verification instructions.
- Reset scope: Option B, transactional drop/recreate of `public` only, local hosts
  and `shelfcash`/`shelfcash_test` only, development/test environments only. Reject
  unsafe targets before connecting; bounded lock timeout. Stop DB clients first.
- Test isolation: create/use `shelfcash_test` with Compose's local role; never reset
  the normal development DB during tests. Sequential execution owns the test DB.
- Affected BE: config/engine/Alembic and developer tooling. FE/ML/Data: none.
  Demo: local PostgreSQL readiness and persisted revision evidence, no business seed.
- Rollback: code/docs/dependency/Compose changes only; no business data to migrate.
  Preserve historical decisions and ignored runtime artifacts; no commit requested.
- Verification: Docker config/start/health/connectivity, both pytest and PowerShell
  runner, status/reset/seed/Alembic, import/OpenAPI/live health, pip check, diff review.
  Native POSIX execution must not be claimed from shell syntax validation alone.

## Final S0.2 verification — HISTORICAL INFORMATION

S0.2 acceptance gates passed on Windows/Python 3.11.9 on 2026-10-05.

| Command/check | Outcome |
| --- | --- |
| `.venv/Scripts/python.exe -m pip install -e '.[dev]'` | Success, psycopg and binary 3.3.6 installed |
| `docker compose config` | Success, localhost port, native healthcheck and named volume |
| `docker compose up -d postgres` | Success |
| `docker compose ps` / inspect | PostgreSQL 17.11 healthy; named volume mounted |
| `./scripts/db_status.ps1 -AllowUnmigrated` | Fresh PostgreSQL reachable; initially no public tables/revision |
| `./scripts/reset_db.ps1 -Seed` and `./scripts/reset_db.ps1` | Success, clean public at head, optional no-op seed |
| `.venv/Scripts/alembic.exe upgrade head` | Success, fresh and repeated |
| `.venv/Scripts/alembic.exe current` | `0001_scaffold (head)` |
| `./scripts/seed_demo.ps1` | Success, no business seed data/rows |
| `./scripts/db_status.ps1` | Reachable shelfcash, at_head true, only alembic_version: 1 |
| `.venv/Scripts/python.exe -m pytest` | 20 passed, 1 existing upstream warning, no skips |
| `./scripts/test.ps1 all` | 20 passed (14 unit / 4 integration / 2 API), same warning |
| Python app import / OpenAPI comparison | Success, exact pre-change generated schema |
| Live Uvicorn HTTP requests | Health HTTP 200 unchanged; OpenAPI exact; server stopped |
| Independent SQLAlchemy SQL inspection | SELECT 1 succeeds; public contains only revision table at head |
| `docker compose up -d --force-recreate --wait --wait-timeout 90 postgres` | Healthy; revision/table state survives recreation |
| `.venv/Scripts/python.exe -m pip check` | No broken requirements |
| Git Bash `bash -n` on all five `.sh` files | Syntax passed only; native POSIX runtime not executed |
| `git diff`, `git status`, `git diff --check` | Scoped changes reviewed; no whitespace errors; no commit |

Existing health/OpenAPI/import/domain and developer workflow coverage is preserved;
obsolete file/sidecar checks were adapted to PostgreSQL target and persisted-state
guards. Integration tests own only `shelfcash_test`; final development SQL inspection
still contains only `0001_scaffold`, no business schema/data. Completion authorizes
no S1 implementation. Next phase remains PROPOSAL pending separate authorization.
