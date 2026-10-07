# ADR-014 — Retained internal baseline execution

Status: ACCEPTED — explicit user S2.3 task, 2026-10-07.
Classification: ACCEPTED DECISION. ADR-007/010/011/012/013 remain unchanged.

## Decision and implementation boundary

- Trusted internal caller only; Store scope is not actor authorization. No HTTP/RBAC.
- Capture Store timezone, explicit Products/current selling units and all canonical
  Sales in inclusive requested window using one read-only REPEATABLE READ snapshot.
  No active filtering, missing-day filling, freshness threshold or partial scope.
  Product unit is assumed stable within the history window; historical unit recovery
  and historical data availability at D are not claimed.
- Validate immutable prepared values and all-Product baseline readiness before durable
  start. No-history requests create no run. READY means this baseline can run, not
  confidence/accuracy/freshness. S2.2 algorithm/readiness remains unchanged.
- Retain prepared JSONB in forecast_run_inputs, one immutable-by-application record
  per execution run with same-Store FK, serialization version, SHA-256 and created_at.
  Run + input start atomically. Old S1 runs need no retained input. Repositories expose
  scoped insert/read only; no update/delete/dedup/TTL/immutability triggers.
- Version-1 canonical JSON covers all prepared values, sorted keys/compact UTF-8,
  S2.1 array order, UUID/date strings and exact Decimal strings. Numerically equal
  Decimal scales share identity; signed zero is 0; no rounding/context normalization.
  Digest prefix is shelfcash.forecast-input.v1 followed by newline. Input identity
  excludes run/timestamp/model/result. Revalidate/canonicalize/verify on load.
- Fixed truthful historical_quantile_baseline / 1 / no artifact is known before start.
  Existing training fields record requested input history window, not actual training.
  Compute from retained values after capture/start Sessions close, with no transaction
  or row lock. Validate full result and match metadata/input at completion; persist
  predictions and COMPLETED atomically with metrics_json absent.
- Pure replay loads only retained run/input. Persisted replay/rerun creates new UUID,
  checks current identity/FK but never replaces captured provenance with current rows.
  S1 missing retention, unsupported version, malformed payload and digest mismatch reject.
- Known failures after start record sanitized FAILED in a new transaction and retain
  input. Only a recognized transport/unknown-resolution error during commit can
  reconcile into verified COMPLETED success. Programming, integrity and known
  transaction failures never become success, even if completion is already durable;
  report execution error with run ID/COMPLETED and never change it to FAILED.
  Cleanup cannot replace the primary error; secondary failures remain diagnostic.
  Reconcile via fresh read after owned Session cleanup; unknown outcome/failed recording
  returns explicit run ID/state, never claims success or FAILED without evidence.
  Crash may leave RUNNING; manual inspection only, no automatic worker/retry/timeout.

Clarification, 2026-10-07 corrective patch: the earlier phrase "error from the commit
call" meant uncertain database commit outcome, not permission to convert arbitrary
commit-call exceptions into success. Accepted intent/scope is unchanged. The concrete
classifier and conservative unsupported cases are CURRENT FACT in
[FORECAST_EXECUTION](../features/FORECAST_EXECUTION.md).

## Storage / rollback / deferred

Migration 0007_forecast_input_retention adds only the retention table. Downgrade
destroys retained inputs while preserving ForecastRun/predictions; back up/export
before real-history downgrade. Keep inputs for RUNNING/FAILED/COMPLETED; purge policy
deferred. JSONB is structured input, not model binary; binaries remain local per ADR-011.
metrics_json is evaluation only, never generic provenance. No trained model, evaluation,
fallback, warning threshold, public API, import or S3. S2 overall remains IN PROGRESS.
