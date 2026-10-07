# Local scaffold demo setup

CURRENT FACT: local setup demonstrates health/OpenAPI and PostgreSQL migration/
inspection, including sixteen empty S1.1/S1.2/S1.3/S1.4 business tables. No public business
API, demo seed entities, imports, Forecast or Decision computation exist yet; run storage alone exists.
ACCEPTED DECISION: local Compose PostgreSQL and native backend/venv (ADR-007).

Follow [FULL_TEST_FLOW](FULL_TEST_FLOW.md) for first-time Python/Docker setup, then
from `backend/` in PowerShell:

```powershell
docker compose up -d --wait --wait-timeout 90 postgres
.\scripts\db_status.ps1 -AllowUnmigrated
.\scripts\reset_db.ps1 -Seed
.\scripts\test.ps1 all
.\scripts\db_status.ps1
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Stop existing backend/DB clients before reset. Seed reports no business data; status
must show reachable `shelfcash`, `at_head: true` and `alembic_version: 1`.
In a second terminal use the runbook's HTTP assertions and persisted SQL queries:
health payload is `{"status":"ok","service":"shelfcash-backend"}`, OpenAPI paths
contain only `/health`, and PostgreSQL contains revision `0006_forecast_decision_persist`
alongside empty `users`, `stores`, `store_memberships`, `products`, `ingredients`,
`recipes`, `recipe_lines`, `suppliers`, `supplier_terms`, `sales_daily`, `inventory_lots`,
`inventory_movements`, `business_constraints`, `forecast_runs`, `forecast_predictions`, `decision_runs` after reset.
Ctrl+C stops FastAPI; `docker compose stop postgres` stops PostgreSQL while retaining
the named volume. No provider credential or hosted notebook is required.

POSIX equivalents: `sh scripts/reset_db.sh --seed`, `sh scripts/test.sh all`,
`sh scripts/db_status.sh`, `.venv/bin/python -m uvicorn app.main:app ...`.
See TESTING/CURRENT_STATE for syntax-versus-runtime verification status.
PROPOSAL: deterministic business demo fixtures/golden scenarios arrive only with
their authorized feature slices. Do not present health success as business readiness.
