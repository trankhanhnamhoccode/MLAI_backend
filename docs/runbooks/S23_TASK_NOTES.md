# S2.3 task notes

## Frozen plan before editing — ACCEPTED DECISION / CURRENT FACT

Authorization: explicit user S2.3 attachment, 2026-10-07. Branch
feat/baseline_schema, HEAD 10197895255af393607514266aaee95703d725fd.
Preserve all S2.1/S2.2 uncommitted work and backendContext folder/zip.
Protected pre-edit hashes/OpenAPI saved outside repo; marker in ignored runtime.

Current contracts: S1 supplied prediction lifecycle owns commit/rollback, writes
require idle clean Session and reads autobegin. Empty completion remains valid.
S2.1 immutable capture/full coverage and S2.2 per-Product >=1 observation readiness,
exact historical Decimal quantiles remain. ADR-007/010/011/012/013 preserved;
new ADR-014 records only explicit S2.3 accepted retention/execution decisions.

Plan: freeze serialization unit and real PostgreSQL execution acceptance first;
add canonical serialization/errors, retained-input ORM/repository and 0007 migration;
add explicit Engine-composed internal execution with owned capture/start/complete/read
Sessions, integrity-verified load/pure replay/persisted replay. Share two baseline
identity constants without changing math/readiness. Capture read-only REPEATABLE READ;
compute after Sessions close. Start run+input atomic, complete predictions+status atomic.
Reconcile uncertain commit via fresh Session; preserve errors/run IDs, never silently
convert programming errors into success. No worker or automatic retry.

Tests: complete scope/sparse zero/window/snapshot concurrency; hash equivalence and
integrity; atomic start/flush/commit failure; 14 fresh-session predictions/metadata;
no transaction during math; replay after operational corrections; new UUID per replay;
failure recording/unknown/committed completion; missing retention/FK scope; isolated
migration roundtrip, S1/S2 regressions. Update existing schema/head assertions only
where the accepted added table requires it, preserving their behavioral coverage.

BE internal trusted caller only; FE/public OpenAPI unchanged. ML/Data uses baseline
unchanged, no accuracy claim. Demo gains isolated runnable persisted baseline example.
No model/import/RBAC/provider/evaluation/fallback/S3 work. Unit stable-history assumption
and snapshot-vs-PIT limitations explicit. Empty warnings current fact, not quality policy.

Rollback: new code/tests/docs and 0007 structure only; S1/S2.1/S2.2 WIP preserved.
Downgrade loses retained inputs: export/backup before real-data downgrade; run/prediction
tables remain. No development reset/migration during verification; tests only shelfcash_test.
Targeted during work; full supported regression once final gate, rerun only after failure.
Alembic roundtrip/check on isolated DB, pip check, generated/live OpenAPI/health,
fresh-session evidence, protected hashes/diff and canonical docs/manual runbook.

## Verification so far - CURRENT FACT, 2026-10-07

- Frozen new unit/integration tests first failed collection with expected missing
  serialization/execution modules. No fake success before implementation.
- `python -m pytest tests/unit/test_forecast_serialization.py tests/unit/test_forecast_baseline.py tests/unit/test_forecast_execution.py -q`:
  133 passed in 0.39s (123 unchanged S2 unit +10 serialization).
- Initial 13 real PostgreSQL flow tests: 13 passed in 10.12s. Expanded flow now 30 tests.
- Expanded targeted suite across S1 Forecast/application/repositories and all seven
  changed schema/head verification modules: 494 passed, 1 failed in 251.44s.
  Only failure was missing new-table expectation in bootstrap test, fixed precisely;
  standalone bootstrap rerun 1 passed in 1.06s. Initial combined collection also
  exposed a duplicate pytest basename; new integration module renamed to
  test_forecast_execution_flow.py, no existing module/package behavior changed.
- Final targeted command:
  `.\.venv\Scripts\python.exe -m pytest tests/unit/test_forecast_serialization.py tests/unit/test_forecast_execution.py tests/unit/test_forecast_baseline.py tests/integration/test_forecast_execution_flow.py tests/integration/test_forecast_execution_s1_regression.py tests/integration/test_database_bootstrap.py -q`
  165 passed in 20.29s (133 unit +32 PostgreSQL). No skip.
- `docker compose up -d --wait postgres`: healthy PostgreSQL 17.11, existing volume.
- Alembic commands run under guarded ENVIRONMENT=test/DATABASE_URL=test_database_url
  selected explicitly with Settings and validate_reset_target (URL never printed):
  `.\.venv\Scripts\alembic.exe check` -> No new upgrade operations detected;
  `.\.venv\Scripts\alembic.exe current` -> 0007_forecast_input_retention (head).
  Retention roundtrip test downgrades to 0006 preserving 14 predictions/run, upgrades
  to head with no input row, demonstrating real retained-input data loss on downgrade.
- `.\.venv\Scripts\python.exe -m pip check`: No broken requirements found.
- `.\.venv\Scripts\python.exe -B -m scripts.verify_forecast_execution`: runnable
  guarded synthetic manual verification passed; fresh Sessions confirmed two distinct
  UUID COMPLETED runs with same fingerprint/retained input and seven 2.5/5/7.5 rows.
  It wrote only shelfcash_test; full integration fixtures subsequently own cleanup.
- `.\scripts\db_status.ps1 -AllowUnmigrated`: development shelfcash reachable,
  unchanged 0006 revision, 16 empty business tables +revision row1. Expected repo head
  0007, at_head=false intentionally: no development migration/reset/seed performed.
- Pre-edit 194 files all retained. Original S1 use case/contracts and S2.1/S2.2 unit
  tests, ADR-010/011/012/013 and backendContext hashes unchanged. Two S2.2 source files
  differ only by shared model identity constants/import, no algorithm/readiness change.
  Model registration/docstring, seed schema guard and seven existing head/table tests
  changed as required by new schema; no widened lifecycle assertions.
- Generated and live entire OpenAPI equal pre-edit /health-only schema; own loopback
  hidden verifier exact health200/payload passed, then terminated/waited. AST parse pass.
  Full supported regression started once after targeted green; result pending below.

## Final gate - CURRENT FACT

Supported `.\scripts\test.ps1 all`: 672 passed in 273.90s (4:33), zero skips;
252 unit /418 integration /2 API, one existing Starlette/AnyIO deprecation warning.
Full regression run count: 1. No full failure or rerun. Final source/tests unchanged
since targeted gate; documentation finalized after full green. S2.3 COMPLETE,
S2 overall IN PROGRESS. No commit, no S3, native POSIX not executed/claimed.
New slice files: application serializer/execution, retained-input model/repository,
0007 migration, two test modules, manual verification script, ADR-014, these notes
and S23_VERIFICATION (11 files). Existing changes: 10 docs; registration/model wording,
shared baseline identity (two source files), seed table guard and seven schema/head
expectation modules. No S1 lifecycle change or unrelated WIP removal.


## Corrective patch frozen plan - ACCEPTED DECISION / CURRENT FACT

Explicit user authorization, 2026-10-07: fix only review P2 commit classification
and cleanup masking. Preserve baseline, prepared/result contracts, schema/migration,
retention scope, S1/S2.1/S2.2 behavior and all unrelated WIP/backendContext.
Current drift: every commit exception becomes uncertain; rollback/Session context
cleanup can replace primary error; start programming/cleanup errors can escape
without run ID. No FE/public API/ML policy/demo schema change.

Plan: private S2.3 Session cleanup preserves primary exception and logs/notes secondary
rollback/close/invalidation failures; fresh Session reconciliation only after owned
Session cleanup. Narrow SQLAlchemy/psycopg commit classifier uses exception types,
SQLSTATE and dialect disconnect evidence, never message strings. Known transaction
failures and programming errors cannot return success, even if durable COMPLETED.
S2.3 failure writer keeps existing lifecycle semantics without relying on S1's
unprotected cleanup; S1 source remains unchanged.

Acceptance: unit classifier matrix and actual Session after_commit regression;
PostgreSQL fresh-session run/input/prediction assertions for start/completion
rollback+close failures, post-commit ValueError, recognized connection-loss commit
errors, known failed transaction, failure-recording/cleanup and unknown outcomes.
Tests are frozen before implementation. Transport injections use real driver exception
types/disconnect flags; they do not claim real network lost-ack reproduction.
Targeted first, then supported full regression once; if red, fix/targeted/full again.
Docs clarify ADR-014 intent and classifier limits; CURRENT_STATE/ROADMAP updated.

Rollback: revert only this patch's execution source/tests/docs, checking pre-edit hashes
(saved outside repo; marker runtime/s23_corrective_path.txt). No Alembic change or
DB rollback/reset/migration needed. Integration fixtures own only shelfcash_test;
never reset/migrate development DB. No commit or next slice.


### Corrective targeted verification - CURRENT FACT

- Frozen unit tests before implementation: 17 failed (missing classifier/session guard),
  expected red. PostgreSQL pre-patch cleanup regressions also failed and left a faulty
  Session holding its transaction, blocking isolated fixture cleanup; the targeted
  subprocess was interrupted. No full regression/development DB action occurred.
- After implementation: classifier/real unbound Session callback suite 17 passed in
  0.29s; first combined targeted 194 passed in 32.22s.
- Added stronger PostgreSQL after_commit callback and server-generated 40001 checks,
  full aggregate verification rejection and secondary invalidation failure coverage.
- Final targeted command:
  `.\.venv\Scripts\python.exe -m pytest tests/unit/test_forecast_commit_errors.py tests/unit/test_forecast_serialization.py tests/unit/test_forecast_execution.py tests/unit/test_forecast_baseline.py tests/integration/test_forecast_execution_flow.py tests/integration/test_forecast_execution_s1_regression.py tests/integration/test_database_bootstrap.py -q --tb=short`
  **200 passed in 33.33s**, no skips. 151 unit +49 PostgreSQL cases.
- 35 new cases: 18 unit (16 classifier cases +actual Session callback +invalidation
  failures), 17 PostgreSQL (13 initial cases +2 actual after_commit callbacks +actual
  server SQLSTATE40001 +corrupt completed aggregate rejection). Original lost-ack tests
  now inject typed SQLAlchemy/psycopg errors, not generic RuntimeError.
- Fresh Sessions assert run/input/predictions and outcomes: uncommitted start absent;
  committed start reported by run ID then FAILED; completion bug remains COMPLETED
  with14 predictions; failed completion has0 predictions; failed failure recording
  reports RUNNING/FAILED accurately. Pool checkedout0 after rollback/close failures.
- Primary cause remains through rollback/close/invalidation, failed recording/read/
  verification; logs/notes record secondaries. Transport injection is not a real
  network-loss test. SQLSTATE40001 is intentionally raised by PostgreSQL, not an
  organically concurrent serialization conflict. No accuracy claim.
- Final supported full regression pending. Corrective rollback changes no DB schema.

### Corrective full-gate failure and scoped follow-up - CURRENT FACT

First `./scripts/test.ps1 all`: **706 passed, 1 failed in312.48s**, one existing warning.
Failure: existing test_application_has_no_http_or_direct_queries forbids direct
application `.close()` calls. The corrective owned-Session helper introduced one.
Do not weaken this architecture assertion: move only the concrete S2.3 cleanup and
secondary-diagnostic helpers into app/infrastructure/database/forecast_execution_session.py;
application composition imports them. No business rules/classifier/domain/schema change.
Acceptance: existing architectural test plus all corrective/S2 units and real PostgreSQL
execution tests, then supported full gate again. Rollback also removes this single new
infrastructure module; preserve unrelated WIP. No development DB action.

Follow-up targeted:
`.\.venv\Scripts\python.exe -m pytest tests/unit/test_application_contracts.py tests/unit/test_forecast_commit_errors.py tests/unit/test_forecast_serialization.py tests/unit/test_forecast_execution.py tests/unit/test_forecast_baseline.py tests/integration/test_forecast_execution_flow.py tests/integration/test_forecast_execution_s1_regression.py tests/integration/test_database_bootstrap.py -q --tb=short`
**238 passed in33.13s**, no skips; includes the unchanged architecture assertion.
189 unit +49 PostgreSQL cases. Application no longer calls close directly; the concrete
infrastructure helper performs owned cleanup. Second full gate pending.

### Corrective final gate - CURRENT FACT, 2026-10-07

Second supported `.\scripts\test.ps1 all`: **707 passed in283.16s**, zero skips;
270 unit /435 integration /2 API, one existing Starlette/AnyIO deprecation warning.
Corrective full attempts:2, first failed architectural assertion then scoped fix,
targeted238 green and full707 green. Code/tests unchanged after the successful full gate.
Earlier "pending" entries are chronological historical progress, resolved here.

Read-only `.\scripts\db_status.ps1 -AllowUnmigrated`: shelfcash remains0006,
sixteen empty business tables and one revision row; expected head0007/at_head=false.
No development reset/migration/seed. Generated OpenAPI equal the saved S2.3 schema.
AST passes;22 local documentation links resolve; git diff --check passes (existing
line-ending warning only). Hash audit:8 pre-existing files modified,2 added,0 deleted;
all other pre-existing208-file snapshot entries preserved, including backendContext,
S1 source/contracts, S2.1/S2.2 math/contracts, model/repository/serialization/migration.

Patch files: application forecast_execution; new concrete infrastructure
forecast_execution_session; existing PostgreSQL flow tests; new18-case unit module;
CURRENT_STATE/ROADMAP/ADR-014/FORECAST_EXECUTION/S23_TASK_NOTES/S23_VERIFICATION.
ADR clarification preserves accepted intent; no schema/API/business-policy change.
Classifier is deliberately conservative, unsupported families never qualify for success.
Cleanup cannot guarantee resource release if rollback/close/invalidation all fail;
diagnostics retain secondaries and fresh-state reads may report UNKNOWN. No genuine
network lost-ack reproduction, native POSIX or forecast-accuracy claim.
Corrective patch COMPLETE, ready for commit subject to user instruction; no commit,
staging, next slice or unrelated WIP modification performed.
