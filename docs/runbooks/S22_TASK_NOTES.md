# S2.2 task notes

## Observation before implementation — CURRENT FACT

Branch feat/baseline_schema, SHA 10197895255af393607514266aaee95703d725fd.
S2.1 is implemented/reviewed but uncommitted: seven modified docs and eight new
slice files, plus unrelated backendContext folder/zip. Capture hashes of all existing
tracked/untracked files and original generated OpenAPI before editing; preserve WIP.

Read AGENTS and current authority, ADR-011/012, Forecast feature/task notes, complete
forecasting domain, execution contracts, S1 use cases/repository and S2.1 tests.
S2.1 contracts agree with the supplied task: fixed seven dates, captured sparse
observed sales, Decimal, full coverage and optional artifact identity. No blocker.
S1 idle-session lifecycle and empty supplied completion must remain unchanged.
Known old schema-era absence claims remain historical where superseded by later
sections; ForecastRun lifecycle-future docstring is existing documentation debt.
No local legacy source found by workspace parent search for legacy/training_pipeline;
no external legacy retrieval, heuristic reuse or dependency is required for S2.2.
ROADMAP has no named/frozen S2.3; do not invent one or start future work.

## Frozen plan — ACCEPTED DECISION (explicit S2.2 task)

- Baseline-specific readiness: each requested Product with zero observations is
  NOT_READY_NO_HISTORY; >=1 observation is READY. Include count and first/last dates.
  Observe the entire scope and reject all-or-nothing before quantile computation,
  reporting every no-history Product deterministically. This is not ML readiness.
- Use all captured quantities, including explicit zero; no imputation, filtering,
  weighting, seasonality, calendar features or reconstructed target. Historical
  quantiles use Decimal linear interpolation at (n-1)*q, q=.25/.50/.75. Exact math
  must not depend on ambient Decimal precision/exponent limits or round to integers.
- Revalidate PreparedForecastInput at safe public readiness/execution boundaries.
  Domain receives plain observed values, contains readiness/math/error values only,
  and imports no Pydantic/DB/HTTP/filesystem/LLM. Reuse canonical quantile semantics.
  Entry point assesses every Product before math, returns truthful baseline metadata
  historical_quantile_baseline / 1, None artifact and no evaluation metrics.
  Always call S2.1 validate_engine_result before returning, retaining date-then-UUID
  canonical ordering. No engine Protocol/framework, Session or persistence wiring.
- Files: new domain/forecasting/baseline.py, application/use_cases/forecast_baseline.py,
  tests/unit/test_forecast_baseline.py; update FORECAST_EXECUTION, CURRENT_STATE,
  ROADMAP, TESTING and precise architecture/domain current-fact summaries as needed;
  add these task notes. Do not modify S1/S2.1 code/tests or accepted ADRs.
- Freeze acceptance tests before implementation: empty/single/mixed Product scope;
  complete not-ready report and no prediction computation on rejection; sparse zero;
  known exact quantiles, unsorted/repeated samples, Decimal-context independence,
  deterministic ordering/metadata, capture mutation, mandatory malformed-result
  rejection, prevalidation, domain independence and unchanged S1 lifecycle regressions.
- BE: internal pure computation only. FE/public API: unchanged. ML/Data: transparent
  weak reference baseline for future comparison, no performance claim. Demo: callable
  in-memory baseline, still no ForecastRun execution/persistence end-to-end.
- Rollback only new S2.2 modules/tests and precise documentation edits. Preserve S2.1
  WIP, S1 schema/lifecycle/API. No DB/public API/migration downgrade required.

## Verification / governance

Targeted unit tests during implementation; then S2.1 + S2.2 units and existing Forecast
application/repository/empty-completion PostgreSQL regressions on shelfcash_test only.
Full regression exactly once at final gate after targeted green; rerun only to fix a
failure. Supported Compose/test/db_status commands, Alembic check/current, pip check,
generated/live OpenAPI and health, protected hashes and diff/whitespace checks.
No development reset or business seed. Record actual counts, skipped checks and limits.

No architecture changes or superseding intent: authorized algorithm/readiness policy
is documented explicitly as user-accepted S2.2 specification in FORECAST_EXECUTION.
Existing governance does not require a new ADR for every algorithm implementation;
preserve ADR-012's historical S2.1 deferral and all accepted ADRs unchanged.

## Final verification — CURRENT FACT, 2026-10-07

- First frozen-test command:
  `.\.venv\Scripts\python.exe -m pytest tests/unit/test_forecast_baseline.py -q`
  failed collection with expected missing application baseline module.
- Targeted implementation command:
  `.\.venv\Scripts\python.exe -m pytest tests/unit/test_forecast_baseline.py tests/unit/test_forecast_execution.py -q`
  **123 passed in 1.02s** (42 new baseline, 81 S2.1 unit tests).
- Final targeted acceptance command:
  `.\.venv\Scripts\python.exe -m pytest tests/unit/test_forecast_execution.py tests/unit/test_forecast_baseline.py tests/integration/test_forecast_execution_s1_regression.py tests/integration/test_application_paths.py tests/integration/test_repositories.py -q`
  **233 passed in 169.82s**: 123 unit + 110 PostgreSQL regressions.
- Final gate `./scripts/test.ps1 all`: **632 passed in 503.27s**, no skips,
  242 unit / 388 integration / 2 API, one existing Starlette/AnyIO warning.
  Full regression run count **1**, no rerun/failure. No new baseline DB test.
- `docker compose up -d --wait postgres`: healthy, existing named volume retained.
  `./scripts/db_status.ps1`: read-only development shelfcash remains at 0006 head,
  sixteen empty business tables and revision row count 1, PostgreSQL 17.11.
  Integration fixtures own shelfcash_test; no development reset or seed.
- `.\.venv\Scripts\alembic.exe check`: No new upgrade operations detected.
  `.\.venv\Scripts\alembic.exe current`: 0006_forecast_decision_persist (head).
  `.\.venv\Scripts\python.exe -m pip check`: No broken requirements found.
- Entire generated and live OpenAPI equal pre-edit schema; live /health HTTP 200
  with exact unchanged payload, only /health operation. Own verifier stopped.
- Both FORECAST_EXECUTION examples execute unchanged. Actual computed sparse
  Mon=10/Wed=0 report READY/count=2 and produce 2.5/5/7.5 for seven forecast dates,
  truthful historical_quantile_baseline/1/None. Example results are math fixtures,
  not measured forecast accuracy.
- Saved 190-file hashes preserve all pre-existing S1/S2.1 source/tests, schema/
  migrations, ADRs, dependencies and unrelated WIP (backendContext included).
  Six existing docs precisely extended: CURRENT_STATE, ROADMAP, ARCHITECTURE,
  DOMAIN_MODEL, TESTING, FORECAST_EXECUTION. Four new files: these notes, domain
  baseline, application baseline entrypoints, unit acceptance tests. No commit.
  SHA remains 10197895255af393607514266aaee95703d725fd; diff/status/whitespace,
  syntax and 39 local doc links reviewed. Native POSIX runtime not executed/claimed.
- S2.2 COMPLETE; S2 overall IN PROGRESS. No LightGBM/legacy adapter/feature engineering,
  evaluation/metrics/backtest/comparison, ForecastRun wiring/persistence, artifacts,
  public business API or S2.3+. Baseline-specific policy is the explicit authorized
  task specification; no accepted ADR modified or automatic new ADR introduced.
- Canonical ROADMAP defines no named/frozen S2.3. Remaining S2 concerns need separate
  scope acceptance; next top-level S3 is only after S2 completion. Nothing started.
- Rollback only the new S2.2 modules/test and precise docs edits relative to this
  slice's pre-edit snapshot. Preserve S1/S2.1 WIP; no DB/API/migration rollback.
