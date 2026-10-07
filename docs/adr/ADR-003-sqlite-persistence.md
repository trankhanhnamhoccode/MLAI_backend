# ADR-003 — SQLite persistence for Competition Edition

## Status
SUPERSEDED by [ADR-007 — PostgreSQL Persistence Baseline](ADR-007-postgresql-persistence-baseline.md).

SQLite was accepted during the initial scaffold. The explicit S0.2 correction
superseded it before any business schema or real business data was implemented.
PostgreSQL is now the Competition Edition persistence baseline. SQLite is no
longer an active application persistence backend.

The original decision below is preserved as HISTORICAL INFORMATION, not active
architectural authority.

## Context
Competition development/demo values clarity and reproducible state over long-lived
production migration compatibility. Databases may be reset between versions.

## Decision
Use SQLAlchemy 2.x with synchronous Session and SQLite. No external database driver
is required. Use Alembic to describe schema evolution explicitly; reset between
versions is acceptable. Long-lived backwards-compatible migration engineering is
not a current goal. Start with an empty baseline, not invented business tables.

## Consequences
Local database files are ignored runtime artifacts. Migrations must be reproducible
on a clean database and SQLite foreign keys enabled. Future models must respect
SQLite capabilities. Domain computation remains independent of persistence.

## Rejected/Deferred alternatives
REJECTED for this Edition: PostgreSQL, MongoDB and compatibility machinery for old
ShelfCash schemas. DEFERRED: production retention and long-lived migration support.

## Revisit conditions
Concrete deployment/concurrency or retention requirements exceeding SQLite's fit,
with evidence and an explicitly accepted replacement decision.

## Affected areas
BE configuration, SQLAlchemy persistence, Alembic, integration tests, developer setup
and reproducible demo state.
