# Full local verification flow

CURRENT FACT: this flow verifies S0 on repository infrastructure. SQLite requires
no server, Docker, PostgreSQL or Kaggle. ADR-003 remains the ACCEPTED DECISION.
Business scenarios are PROPOSAL until implemented; this runbook claims only scaffold
behavior. Run from `backend/`, with Python 3.11+ installed.

## Fresh environment: Windows PowerShell

Run these commands one at a time; stop if any command fails. Scripts propagate errors
as nonzero exit codes. If local execution policy blocks scripts, invoke them with
`powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test.ps1 all` (similarly
for other scripts); no persistent policy change is necessary.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[dev]'
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
$env:ENVIRONMENT = 'development'
$env:DATABASE_URL = 'sqlite:///runtime/shelfcash.db'
$env:APP_NAME = 'shelfcash-backend'
# Stop any running backend/database clients first. Save a DB copy if needed.
.\scripts\reset_db.ps1 -Seed
.\scripts\db_status.ps1
.\scripts\seed_demo.ps1
.\scripts\test.ps1 all
.\.venv\Scripts\python.exe -m pip check
```

Reset applies `alembic upgrade head` internally. Expected status: `integrity_check`
is `ok`, `foreign_key_violations` is `[]`, `revisions` is `["0001_scaffold"]`,
`tables` is `{"alembic_version": 1}`. Seed says `No business seed data`, writes
nothing and succeeds. Repeating reset/seed produces the same revision/table state.
All automated tests must pass; `pip check` reports no broken requirements.

Start the server in this terminal:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In a second PowerShell terminal, change to `backend/` and run:

```powershell
$health = Invoke-RestMethod http://127.0.0.1:8000/health
if ($health.status -ne 'ok' -or $health.service -ne 'shelfcash-backend') { throw 'Unexpected health payload' }
$schema = Invoke-RestMethod http://127.0.0.1:8000/openapi.json
if (($schema.paths.PSObject.Properties.Name -join ',') -ne '/health') { throw 'Unexpected OpenAPI paths' }
$env:DATABASE_URL = 'sqlite:///runtime/shelfcash.db'
.\scripts\db_status.ps1
.\.venv\Scripts\python.exe -c "import sqlite3; c=sqlite3.connect('file:runtime/shelfcash.db?mode=ro', uri=True); print(c.execute('SELECT version_num FROM alembic_version').fetchall()); print(c.execute('SELECT name FROM sqlite_master WHERE type = ? ORDER BY name', ('table',)).fetchall()); c.close()"
```

Expected SQL output: `[('0001_scaffold',)]` and `[('alembic_version',)]`.
Expected status is identical before/after HTTP requests: HTTP liveness writes no DB
state. Stop the server with Ctrl+C. Do not reset while it or a database client is active.

## Fresh environment: POSIX shell

```sh
set -eu
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
if [ ! -f .env ]; then cp .env.example .env; fi
export ENVIRONMENT=development DATABASE_URL=sqlite:///runtime/shelfcash.db APP_NAME=shelfcash-backend
# Stop backend/database clients first; back up local state if needed.
sh scripts/reset_db.sh --seed
sh scripts/db_status.sh
sh scripts/seed_demo.sh
sh scripts/test.sh all
.venv/bin/python -m pip check
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In a second terminal at `backend/`:

```sh
set -eu
export DATABASE_URL=sqlite:///runtime/shelfcash.db
.venv/bin/python -c 'import json, urllib.request; h=json.load(urllib.request.urlopen("http://127.0.0.1:8000/health")); assert h == {"status":"ok","service":"shelfcash-backend"}; s=json.load(urllib.request.urlopen("http://127.0.0.1:8000/openapi.json")); assert set(s["paths"]) == {"/health"}; print("HTTP contracts verified")'
sh scripts/db_status.sh
.venv/bin/python -c 'import sqlite3; c=sqlite3.connect("file:runtime/shelfcash.db?mode=ro", uri=True); assert c.execute("SELECT version_num FROM alembic_version").fetchall() == [("0001_scaffold",)]; assert c.execute("SELECT name FROM sqlite_master WHERE type=? ORDER BY name", ("table",)).fetchall() == [("alembic_version",)]; c.close(); print("Persisted baseline verified")'
```

Expected results match Windows. Stop the server with Ctrl+C.

## Future feature completion gate

ACCEPTED DECISION: future persistence tests verify committed rows using a fresh
session/transaction, alongside application/API results. HTTP 2xx alone is insufficient.
Each major feature needs implementation, automated and relevant integration tests,
usable manual steps, deterministic inputs where practical, DB inspection/expected
state where applicable, and updated canonical feature/current-state documentation.
No roadmap slice is complete until these verification instructions are usable.

PROPOSAL: extend this flow with actual business API operations and fixture assertions
as slices ship. Imports must verify ImportJob, profile/mapping state, processing and
canonical rows, with explicit table inspection. Forecast/BOM/FEFO/procurement/
simulation/decision/what-if need direct invariant and deterministic scenario tests,
plus snapshots only where persistence is contracted. LLM output is never the oracle.
