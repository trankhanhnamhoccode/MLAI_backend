# ADR-007 — PostgreSQL Persistence Baseline

## Status

ACCEPTED — explicitly authorized by S0.2 on 2026-10-05.
Supersedes [ADR-003](ADR-003-sqlite-persistence.md) before business schema/data exists.

## Context

The initial scaffold selected SQLite. S0.2 explicitly corrects the local relational
persistence baseline before S1. Existing health, modular boundaries, test categories,
scripts and completion gates must be preserved; no business schema is authorized.

## Decision

- Use PostgreSQL as the Competition Edition relational database, SQLAlchemy 2.x,
  synchronous engine and Session, psycopg 3 and Alembic. No async driver/framework.
- Run local PostgreSQL through Docker Compose using the official PostgreSQL 17
  image, native `pg_isready` healthcheck and the `shelfcash-postgres-data` named volume.
  The backend remains native Python/venv; installing PostgreSQL on the host is unnecessary.
- Database files persist across normal container restart/recreation. Bind the native
  development connection to loopback `127.0.0.1` port 5432, configurable with
  `POSTGRES_PORT`. Explicit IPv4 avoids local hostname fallback delays.
- Database URLs come from settings/environment. Engine construction and app/domain
  import, startup and health do not connect; DB operations connect explicitly.
- Competition development resets are allowed. Use guarded Option B: drop/recreate
  `public` in the local `shelfcash` or `shelfcash_test` database, then migrate and
  optionally seed. Test environment may reset only `shelfcash_test`. Stop clients
  first; bound lock waits rather than killing arbitrary sessions.
- Tests own a separate local `shelfcash_test` database. No destructive test operation
  may target the ordinary development database. Tests run sequentially for now.
- Complex backwards-compatible migration engineering is not currently required;
  schema state/evolution must still be explicit through Alembic. Retain the empty
  `0001_scaffold` baseline; create no business tables in S0.2.
- SQLite is no longer an active application persistence backend; ADR-003 remains
  historical evidence. Local uploads/model artifacts and one backend process remain.

## Consequences

Docker must be running for integration tests, migrations and DB workflows. Unit/API
tests remain possible without a live DB. The official local image's role can create
the dedicated test database; these development credentials are not deployment IAM.
Schema reset destroys only target `public` objects, keeps the database/volume, and
does not touch uploads or model artifacts. Migration failures are reported and
retriable; no S1 implementation or public API change follows from this decision.

## Rejected/deferred alternatives

REJECTED: active dual database support, asyncpg, mandatory backend containerization,
normal reset through volume deletion and business repositories/models in this slice.
DEFERRED: backend Docker image, production retention/permissions and sophisticated
long-lived migration compatibility until concrete requirements exist.

## Revisit conditions and affected areas

An explicitly accepted superseding ADR is required to change database/transaction
intent. Affects backend config/infrastructure, dependencies, Alembic, Compose,
integration tests and local/demo verification; business computation remains plain Python.

Implementation references: [official PostgreSQL image](https://hub.docker.com/_/postgres)
and [SQLAlchemy psycopg dialect](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#module-sqlalchemy.dialects.postgresql.psycopg).
