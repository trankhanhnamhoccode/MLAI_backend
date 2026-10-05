# S1.5 task notes

## Current request review -- ACCEPTED DECISION / CURRENT FACT

The current workspace already contains the earlier S1.5 insert/read implementation
and uncommitted S1.1-S1.4 work. Preserve all of it. The current request requires
minimal Forecast/Decision lifecycle access guards, which the earlier completion
claim explicitly deferred. Treat that claim as historical pending this verification.
Models, migrations, accepted ADRs, API contract and dependencies are frozen; hashes
and generated OpenAPI are captured in runtime/s15_review_baseline.json.

Authorized delta: Forecast prediction append only while RUNNING; explicit
RUNNING -> COMPLETED/FAILED methods for Forecast and Decision. Lock/refresh the
Store-scoped run before checking state so competing repository writers serialize.
Terminal states reject subsequent writes with InvalidLifecycleTransition; missing
or wrong-Store run returns None. No commit/rollback/session lifecycle ownership.
Full package validation, input capture, inventory mutation and engines stay future.

Acceptance: real PostgreSQL lifecycle commit/close/fresh reads, terminal rejection,
Store isolation, shared transaction rollback and stale Session/concurrent locking.
Retain existing 16-table/date-query/transaction acceptance tests. Run targeted and
full supported suite, reset/upgrade/status, migration drift, import/OpenAPI/live HTTP
and pip check. BE persistence only; FE/API/ML computation/demo behavior unchanged.
Rollback only this review's repository/test/documentation delta, no data migration.
S1 remains IN PROGRESS under canonical roadmap; no next slice is authorized.

## Current request acceptance outcome -- CURRENT FACT

COMPLETE: targeted 80 passed (65 repository integration + 15 unit); supported full
suite 320 passed (289 integration / 29 unit / 2 API), no skips, one existing warning.
Compose PostgreSQL 17.11 healthy; supported development reset/upgrade/status pass,
head unchanged 0006, sixteen empty business tables. Alembic check reports no new
upgrade operations. Protected files and generated/live OpenAPI match baseline;
live health HTTP 200 unchanged, verification server stopped; pip check, compile,
structure/transaction-ownership and diff checks pass. No schema/ADR/API/dependency
change, engine, operational service, commit or S2+ work. Prior WIP preserved.
Earlier lifecycle deferral is corrected by guarded repository methods only;
full application validation/direct ORM/SQL protection remains future.
S1 remains IN PROGRESS because canonical roadmap has additional application gates.

## Earlier insert/read delivery -- HISTORICAL INFORMATION

The following notes describe the prior delivery; lifecycle deferrals below are
superseded by the current request review above.

Classification: ACCEPTED DECISION for the user-authorized access contract below;
CURRENT FACT for observed baseline; PROPOSAL for unimplemented future services.

Observed baseline: 16 models/tables, head 0006_forecast_decision_persist, empty
repositories/application packages, health-only public API. Existing uncommitted
S1.1-S1.4 code/docs/tests are preserved. Models/migrations/ADRs/API contract hashes
and generated OpenAPI captured in ignored runtime files before editing.
Relevant authority: ADR-002/007 (layers/sync Session), 008 (sales insert identity),
009 (lot + movement atomicity), 010 (unknown values), 005/011 (run history).
No schema defect requiring a migration was observed. Documentation still saying
repositories are absent is the baseline, to be updated after verified implementation.

Frozen contract:
- Concrete domain repositories in app/repositories; caller supplies one synchronous
  Session shared by all repositories in a use case. No repository commits, rolls
  back, closes sessions, constructs engines or owns transactions. Queries retain
  SQLAlchemy's ordinary autoflush; add methods defer flush except aggregate run
  insertion requiring a generated parent identity or ordering parent before supplied
  predictions. Flush includes other pending writes; caller handles DB errors.
- Explicit UUID Store arguments on owned queries and inserts. Missing/wrong-store
  reads return None/[]; mismatched row Store raises ValueError before staging.
  Composite database FKs remain authoritative for referenced Store/unit integrity.
- ORM rows are infrastructure results for application orchestration, never domain
  computation inputs directly. No speculative Protocol/DTO/framework. Insert-only
  methods accept new transient typed models, never merge detached/persisted rows.
- Lists have documented deterministic ordering, include inactive/history by default;
  effective lookups use inclusive dates, NULL unbounded ends and active flags only
  where the schema has them. Invalid sales date ranges raise ValueError.
- No update/delete/upsert methods. Recipe/term/constraint versions and movements
  are inserted/read. Inventory exposes a scoped lock read and append only movement;
  caller may mutate the loaded lot and append movement within the same transaction.
  No balance computation, audit validation or mutation service is implemented.
- Forecast inserts a new run with its complete supplied prediction collection in
  one caller transaction, no append-to-existing-run writer. Decision inserts new
  runs only. RUNNING/FAILED storage is permitted; status transitions, horizon/full
  package validation and immutable read DTOs remain future engine/use-case work.
  Loaded ORM objects/direct Session writes can bypass lifecycle policy; no SQL or
  session-wide immutability framework is claimed.

Acceptance tests before implementation: real shelfcash_test repository round trips
for all tables with close/fresh reads; every read scoped including loaded identity
map; wrong-store insert rejection; related cross-store FK rejection; exact Decimal/
NULL/JSON; effective period boundaries/inactive/history; inclusive chronological
sales; duplicate insertion rejection; shared transaction commit/rollback; movement
failure rolls back an already flushed lot change; run reruns and insert-only guards.
Run targeted then full supported suite, unchanged OpenAPI/hash/schema checks and
read-only development db-status. No development reset or business seed is needed.

Affected BE: new persistence access path only. FE/public API unchanged. ML/Data:
sales and snapshot retrieval available, no computation/import. Demo: reproducible
isolated repository tests/manual guide, no fabricated business entities.
Rollback: remove S1.5 repository/test/docs additions and only its documentation
edits; no migration/data rollback required. No next slice authorized.

## Implementation observation -- CURRENT FACT

SQLAlchemy models do not declare relationships for the run/prediction/decision
graph. Initial repository fixture flush exposed a pending parent FK failure.
Forecast aggregate insertion now flushes its parent before staging supplied
predictions; the caller must flush before staging other aggregates referencing
an explicitly identified pending parent. No schema defect/drift or migration was
introduced. Contract/API/accepted ADR intent remain unchanged.

## Acceptance outcome -- CURRENT FACT

COMPLETE on Windows/Python 3.11.9, 2026-10-05. Supported test.ps1 all:
310 passed (29 unit/279 integration/2 API), one existing upstream warning, no skips.
Final repository coverage 55 integration + 15 new unit checks. Models/migrations/
accepted ADRs/API/dependencies hashes unchanged; OpenAPI identical; pip check pass;
read-only development status at unchanged 0006 head with sixteen empty tables.
Prior WIP preserved, no development reset/seed mutation, no commit or next slice.
See CURRENT_STATE and PERSISTENCE_ACCESS for verification and explicit limitations.
