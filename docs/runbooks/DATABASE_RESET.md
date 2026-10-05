# Development database reset

ACCEPTED DECISION: ADR-007 allows Competition development resets while retaining
explicit Alembic schema state. CURRENT FACT: scripts implement Option B, transactional
drop/recreate of `public`, followed by `alembic upgrade head` and optional seed.
Database, role, named volume, uploads and model artifacts are retained.

## Preconditions and guards

Stop the backend and database clients; preserve a backup if development data matters.
Docker/Compose PostgreSQL must be running. Reset refuses targets before connecting
unless all are true:

- `ENVIRONMENT` is `development` or `test`.
- URL uses synchronous `postgresql+psycopg` with an explicit host/database.
- Host is `localhost`, `127.0.0.1`, `::1` or Compose service `postgres`.
- Database is `shelfcash` or `shelfcash_test`; `test` permits only `shelfcash_test`.
- URL has no query overrides that could redirect the guarded connection.

The connected database name is checked before DDL. The schema reset has a 5-second
lock timeout and 15-second statement timeout; it does not kill unrelated sessions.
These guards support the dedicated local Competition topology, not production admin.
Never forward a remote database onto this local endpoint for a reset workflow.

## Commands from backend/

```powershell
docker compose up -d --wait --wait-timeout 90 postgres
.\scripts\db_status.ps1 -AllowUnmigrated
.\scripts\reset_db.ps1 -Seed
.\scripts\db_status.ps1
.\.venv\Scripts\alembic.exe current
```

```sh
docker compose up -d --wait --wait-timeout 90 postgres
sh scripts/db_status.sh --allow-unmigrated
sh scripts/reset_db.sh --seed
sh scripts/db_status.sh
.venv/bin/alembic current
```

Omit `-Seed`/`--seed` for reset+migration only. Seed writes no business data.
Expected persisted result: database `shelfcash`, schema `public`, `alembic_version`
with one row `0002_identity_store`, plus empty `users`, `stores`, `store_memberships`.
Alembic current is at head. Reset destroys any existing rows in that public schema.

For an explicit test-database reset in PowerShell:

```powershell
$env:ENVIRONMENT = 'test'
$env:DATABASE_URL = 'postgresql+psycopg://shelfcash:shelfcash@127.0.0.1:5432/shelfcash_test'
.\scripts\reset_db.ps1
Remove-Item Env:ENVIRONMENT
Remove-Item Env:DATABASE_URL
```

The test suite creates `shelfcash_test` if absent; direct reset expects the target
database already to exist. Do not run multiple suites/reset clients against that
test DB concurrently. Tests never require deleting development state.

## Failure behavior and persistence

Unsafe configuration exits nonzero before connection. Connection/permission errors
exit nonzero. If the schema transaction fails, PostgreSQL rolls it back; close the
blocking client and retry. If schema recreation commits but migration fails, the
database can be empty/partially migrated: fix the migration/configuration and retry.
Status requires head by default; `AllowUnmigrated` checks reachability even before
migration. Status counts public tables in a read-only transaction and writes no state.

`docker compose stop`/`up`, `restart`, and normal container recreation retain the
named volume. `docker compose down` without `-v` also retains it. The image's
`POSTGRES_DB/USER/PASSWORD` initialize a new volume only; keep `.env` and database
credentials aligned on later runs. Changing credentials requires an explicit role
update, not schema reset. Volume deletion is a destructive emergency option and is
not the supported normal reset procedure.
