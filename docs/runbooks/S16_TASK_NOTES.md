# S1.6 task notes

## Observation and frozen scope -- ACCEPTED DECISION / CURRENT FACT

User-authorized S1.6 only. Before editing: read AGENTS, CURRENT_STATE, DECISIONS,
ADRs 001-011 (003 superseded), architecture/domain/schema/API/roadmap/testing,
feature guides, FULL_TEST_FLOW, all S1.5 repositories, empty application package,
Pydantic health convention and related unit/integration tests. Git status was clean;
there is no unrelated working-tree change to overwrite. Protected-file hashes and
generated OpenAPI baseline saved under ignored runtime/s16 before implementation.

Current contract: sixteen tables, Alembic head 0006_forecast_decision_persist,
only public GET /health; concrete repositories return tracked ORM and never own
transactions. ADR-008 prohibits sales upsert/correction, ADR-009 reserves audited
inventory mutations, ADR-010 prohibits fabricated facts, ADR-011 freezes history.

S1.6 adds typed Product create/read, Sales insert/inclusive history, Forecast and
Decision start/complete/fail, and effective Recipe read with typed lines. No engine,
public route, schema, migration, dependency, actor authorization or inventory writer.
Application input is Pydantic v2; output is frozen by-value data. Same-store missing
and wrong-store references both report NOT_FOUND without cross-store probing.
Shape errors retain Pydantic ValidationError; state errors use small application
categories. Known named unique constraints map to CONFLICT; unexpected errors rethrow.

Write use cases require an idle, clean caller-supplied Session, explicitly begin,
flush/map before commit, commit on success and roll back on failure. They do not close
the Session. Reject an existing transaction before touching it, preserving caller
work. Reads suppress autoflush and never commit. Locked lifecycle lookup extensions
are permitted to validate current metadata under the same repository lock. Decision
requires a completed same-store Forecast; supplied object JSON remains an opaque
fixture/internal persistence envelope, not a frozen full business package schema.
Caller supplies deliberately sanitized failure code/summary; no sanitization engine.

Acceptance: contract validation before writes; Store isolation; exact Decimal/NULL;
duplicate conflicts; ordered ranges/quantiles/windows; horizon membership; completed
forecast reference; terminal guards; detached outputs; explicit commit/rollback and
fresh-session atomic Forecast/Decision evidence, including injected downstream DB
failure after flush. Targeted tests first, then full supported suite, Alembic/pip
checks, protected-file hashes, generated/live OpenAPI/health and DB status.

Affected BE: internal boundary only. FE: no API changes. ML/Data: supplied fixtures
only, no forecasting. Demo: reproducible local integration commands, no seed data.
Rollback: revert S1.6 application/tests/docs and two small repository lock lookups;
no database rollback. S1 overall must be assessed against existing roadmap gates;
full operational inventory/correction validation must not be claimed implemented.

## Documentation drift observed -- CURRENT FACT

Some earlier feature-doc bodies still state repositories/application guards absent
despite S1.5 headers and current code/tests. Those are historical schema-slice limits,
not current repository facts. S1.6 will explicitly link current application behavior
and retain historical schema tests, including direct SQL horizon bypass evidence.

## Final acceptance -- CURRENT FACT

2026-10-06, Windows/Python 3.11.9: initial contract tests failed at collection because
the application modules were absent (expected red stage). Final targeted command
passes 82 (38 unit, 44 integration); supported full runner passes 402 (67 unit,
333 integration, 2 API) with no skips and one existing Starlette/AnyIO deprecation.
Downstream Forecast CHECK and Decision OperationalError after real flush roll back
fully through fresh-session evidence; unexpected errors retain their original type.
Canonical conflicts/Store boundaries/lifecycle/stale cache/copied output/read-only/
caller transaction preservation and commit failure pass. Two four-line repository
extensions expose the existing locks; no repository ownership change.

Healthy Compose PostgreSQL 17.11; supported development reset/upgrade/current/seed
and status verify unchanged 0006 head, sixteen empty business tables, one revision.
Alembic check and pip check pass; protected hashes unchanged, generated/live OpenAPI
equal saved baseline, live health unchanged, server stopped. New-file syntax/types/
whitespace and docs links verified; diff/status scope reviewed. No commit or S2+.
S1.6 COMPLETE; S1 overall IN PROGRESS for the precise remaining canonical operational
flow/rules/correction gates now listed in ROADMAP and CURRENT_STATE. Native POSIX
runtime not verified. No acceptance blocker remains for the authorized S1.6 slice.
