# S2.1 task notes

Classification: CURRENT FACT for observed code; ACCEPTED DECISION only for the
user-approved semantics recorded in ADR-012. Future implementation is PROPOSAL.

## Before editing: observation and frozen plan

- Branch `feat/baseline_schema`, starting SHA
  `10197895255af393607514266aaee95703d725fd`.
- Unrelated WIP: untracked `backendContext/`, `backendContext.zip`; preserve both.
- S1 CURRENT FACT: start/complete/fail/get persist caller-supplied predictions;
  completion allows empty predictions, checks ownership/horizon/lifecycle, and
  receives model metadata/artifact_key at start. Writers require idle clean
  Session; reads may autobegin. No Product scope/full coverage execution exists.
- Relevant authority: ADR-001/004 backend/LLM authority, ADR-007 persistence,
  ADR-008 canonical sales identity, ADR-010 missing facts/readiness,
  ADR-011 captured values/actual metadata/historical policy. Preserve all ADRs.
- Observed documentation drift: ForecastRun model docstring still calls lifecycle
  enforcement future; FORECAST's schema-era status still says no repository.
  Architecture/domain schema-era inventory absence claims are superseded by their
  S1.7 sections. Do not change runtime or accepted ADRs to conceal these old claims.
- Files: add application/contracts/forecast_execution.py and plain Python
  domain/forecasting/validation.py; add focused unit acceptance tests; add
  FORECAST_EXECUTION feature doc, ADR-012 and separate future-import ADR-013;
  update DECISIONS, CURRENT_STATE, ROADMAP, FORECAST links, TESTING/runbook and
  the DOMAIN_MODEL current-fact introduction for new semantic validation.
- Freeze tests first: explicit unique nonempty Product scope; ordered history;
  D+1..D+7 including month/year edges; timezone rejection; exact sparse canonical
  observations/units/Store scope; no fabricated zero/stockout/closure; immutable
  capture; full 14-key output; invalid/missing/duplicate/extra output; finite ordered
  Decimal with existing float/bool rejection and no integer rounding; actual model
  metadata, optional artifact, deterministic ordering; S1 empty completion unchanged.
- BE: internal values/semantic validation only. FE/public API: unchanged.
  ML/Data: explicit observed-sales execution interface, no model/readiness policy.
  Demo: no executable forecast end-to-end. No Protocol until concrete engine use.
- Rollback: only new contracts/domain validators/tests and precise slice docs;
  S1/schema/public API/WIP unchanged. No DB downgrade.

## Verification plan and initial blocker

Targeted pytest first; supported `./scripts/test.ps1 all` once at final acceptance
gate, repeat only after fixing a failure. Integration fixtures own shelfcash_test;
no development reset. Save original tracked hashes and generated OpenAPI outside
the repository; compare after implementation and review diff/whitespace.

Initial `docker compose ps` failed: Docker Desktop Linux engine named pipe
`//./pipe/dockerDesktopLinuxEngine` does not exist. Resolve local availability if
possible; otherwise report full acceptance blocked rather than claiming success.

## Reuse / refactor / drop

REUSE existing Contract configuration, exact Decimal boundary types and exact Unit/
Metadata labels; preserve all S1 code/tests. New S2 rules belong in a separate module
and plain Python functions, not a refactor of lifecycle semantics. DROP legacy
reconstruction/filesystem pipeline coupling from this slice; legacy history and
hyperparameters are reference only, with no accepted threshold or model policy.

## Final verification — CURRENT FACT, 2026-10-07

- Freeze before implementation:
  `.\.venv\Scripts\python.exe -m pytest tests/unit/test_forecast_execution.py -q`
  failed collection with the expected ModuleNotFoundError for the new contract.
- Targeted implementation command:
  `.\.venv\Scripts\python.exe -m pytest tests/unit/test_forecast_execution.py tests/unit/test_application_contracts.py -q`
  passed 118 initially, then 119 after adding the domain independence check.
- Final targeted acceptance:
  `.\.venv\Scripts\python.exe -m pytest tests/unit/test_forecast_execution.py tests/unit/test_application_contracts.py tests/integration/test_forecast_execution_s1_regression.py tests/integration/test_application_paths.py -q`
  **164 passed in 25.70s** (119 unit / 45 PostgreSQL integration).
- Final full gate `./scripts/test.ps1 all`: **590 passed in 233.05s**, no skips,
  200 unit / 388 integration / 2 API; one existing Starlette/AnyIO warning.
  Full regression count **1**, no rerun. New coverage 81 unit + 1 S1 integration.
- Initial Docker blocker resolved by starting installed Docker Desktop hidden.
  `docker compose up -d postgres` and
  `docker compose up -d --wait --wait-timeout 90 postgres` both succeeded.
  `./scripts/db_status.ps1` is read-only: development shelfcash at unchanged
  0006 head, sixteen empty business tables, revision count 1; no dev reset/seed.
- Canonical FORECAST_EXECUTION example executed unchanged, outputs 14 keys and
  preserves sparse explicit zero. Exact generated and live OpenAPI comparison to
  original saved schema passed; live /health HTTP 200/payload unchanged, own
  verifier server stopped. No business routes registered.
- SHA remains `10197895255af393607514266aaee95703d725fd`, no commit. Saved hashes
  prove original source/tests/models/migrations/accepted ADRs/API_CONTRACT/
  dependencies unchanged; only seven existing docs edited, eight new slice files.
  Unrelated backendContext folder/zip unchanged. Syntax, 60 local document links,
  diff/whitespace reviewed. Native POSIX runtime not checked; no claim made.
- S2.1 COMPLETE; S2 overall IN PROGRESS. No baseline/model computation, readiness
  threshold/service, execution orchestration/persistence, dependency/migration,
  public business endpoint or import implementation. No S2.2 work started.
- Baseline slice must still decide estimator/quantiles, model-specific readiness,
  retention/hash/evaluation, actual-model publication timing and failure recovery.
  Rollback only new S2 contracts/domain validation/tests and exact slice docs.

## Documentation drift — CURRENT FACT / TECHNICAL DEBT

The original ForecastRun lifecycle-future docstring is documentation debt;
existing repository/application guards are proven by unchanged S1 tests. Original
schema-era absence narratives in feature/architecture/domain docs are HISTORICAL
INFORMATION when superseded by their S1.5/S1.6/S1.7 sections. A new FORECAST current
section links S2.1 and clarifies this; accepted ADR-010/011 were not changed.
