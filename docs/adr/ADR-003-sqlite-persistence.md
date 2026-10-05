# ADR-003 — SQLite persistence for Competition Edition

## Status
ACCEPTED

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
