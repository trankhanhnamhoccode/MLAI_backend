# S2 remaining implementation — work plan (2026-10-07)

Classification: CURRENT FACT for inspection; ACCEPTED DECISION for authorized scope;
provisional operational policies are not measured quality thresholds.

Authorization: user attachment e21574f3-7a85-4507-b0f0-6219063159c1,
complete remaining S2 policies/trained LightGBM/evaluation/artifacts/retained replay.
Branch feat/baseline_schema, HEAD 10197895255af393607514266aaee95703d725fd.
Existing S2.1–S2.3/corrective changes are uncommitted and preserved. Existing
backendContext and context ZIPs are unrelated historical exports, preserved.
No real dataset, frontend, trained weights or ML dependency was available at inspection.
Local network installation succeeded for LightGBM 4.6.0 / NumPy 2.2.6 / SciPy 1.17.1.

## Contract / affected behavior / acceptance before edits

ADR-007/010/011/012/014, S1 empty completion and baseline algorithm remain intact.
Add only internal trained execution; no public API, S3, import, LLM or stochastic mode.
BE/ML/Data: causal features, three quantile boosters, temporal comparison, immutable
trusted local artifacts and purpose-specific execution metadata. FE unaffected.
Demo/evaluation uses labelled synthetic observations, never real quality evidence.

Sequential slices: S2.4 policy + immutable typed values; S2.5 causal feature/model
boundary; S2.6 rolling-origin evaluation/selection; S2.7 artifact + persistence/replay.
Check each slice before proceeding; final targeted persistence, S1/baseline regressions,
full suite after code changes and unchanged OpenAPI comparison. PostgreSQL assertions
use fresh Sessions. Only shelfcash_test may be reset/migrated by supported fixtures.

Acceptance: future changes cannot affect earlier features/training rows; zero differs
from missing; train/inference feature names agree; full coverage and Decimal output;
negative/crossing diagnostics; chronological validation/untouched holdout selection;
zero-denominator/missing/uneven metric counts; artifact hashes/compatibility/errors;
truthful persisted fallback/warnings; replay exact old artifact/input after live changes;
atomic start/completion and genuine-uncertain-only reconciliation, primary error retained.

## Rollback scope before edits

Remove only new S2.4–S2.7 modules/tests/commands and reverse their precise doc/manifests
changes. New migration 0008 adds execution metadata only; downgrade loses metadata,
preserves runs/input/predictions (export first). No development migration/downgrade/reset.
Never delete referenced artifacts or earlier WIP. Existing state/hash/OpenAPI snapshots
are outside the repository, referenced by ignored runtime/s2_trained_verification_path.txt.

Implementation/check results will be appended as slices finish.

S2.4 COMPLETE: policy ADR-015 and immutable typed model/evaluation/metadata contracts.
Check: `.venv/Scripts/python.exe -m pytest tests/unit/test_forecast_model_contracts.py
tests/unit/test_forecast_execution.py -q`: 85 passed (0.19s). No DB writes.

S2.5 COMPLETE: causal features and three deterministic LightGBM quantile boosters.
Initial targeted run found two test-fixture assumptions (tuple pop; Pydantic already
rejects overflowing quantities); corrected tests without relaxing the contract.
Final slice check: `.venv/Scripts/python.exe -m pytest tests/unit/test_forecast_trained.py
tests/unit/test_forecast_model_contracts.py tests/unit/test_forecast_baseline.py -q`:
56 passed (0.50s). SYNTHETIC model mechanics only; no DB or real quality evidence.

S2.6 COMPLETE: chronological paired-target backtest, typed metrics/breakdowns,
validation-only selection, holdout and missing/excluded reports. First run exposed
one fixture missing date outside scored horizons, corrected to an evaluated target.
Check: `.venv/Scripts/python.exe -m pytest tests/unit/test_forecast_evaluation.py
tests/unit/test_forecast_trained.py tests/unit/test_forecast_model_contracts.py -q`:
21 passed (0.70s). Policy count thresholds and synthetic scores are not calibration.

S2.7 first targeted persistence check: `.venv/Scripts/python.exe -m pytest
tests/integration/test_forecast_trained_execution.py tests/unit/test_application_contracts.py -q`:
53 passed (16.42s), including 17 new PostgreSQL cases. Exact fresh-session model/key,
retained input, 14 predictions, warnings/fallback, correction-resistant replay/new UUID,
atomic start failure and post-commit programming vs transport/40001 outcomes checked.
Typed transport and known-failure injections are not real network loss/concurrency.

Further targeted gates (2026-10-07):

- `.venv/Scripts/python.exe -m pytest tests/integration/test_forecast_trained_execution.py
  tests/integration/test_forecast_execution_flow.py tests/integration/test_forecast_execution_s1_regression.py
  tests/unit/test_forecast_artifacts.py tests/unit/test_forecast_trained.py
  tests/unit/test_forecast_evaluation.py tests/unit/test_forecast_model_contracts.py -q`:
  **98 passed in 61.11s**. Baseline/S1/recovery and fresh-session persistence included.
- `.venv/Scripts/python.exe -m pytest tests/unit/test_forecast_artifacts.py
  tests/unit/test_forecast_evaluation.py tests/unit/test_forecast_trained.py
  tests/unit/test_forecast_model_contracts.py tests/unit/test_forecast_commit_errors.py
  tests/integration/test_forecast_trained_execution.py tests/integration/test_forecast_execution_flow.py
  tests/integration/test_forecast_execution_s1_regression.py
  tests/integration/test_forecast_decision_persistence.py tests/integration/test_verification_commands.py -q`:
  **183 passed in 103.48s**. Earlier targeted gate, before final added fault cases.
- `.venv/Scripts/python.exe -m pytest tests/unit/test_forecast_artifacts.py
  tests/unit/test_forecast_evaluation.py tests/unit/test_forecast_trained.py
  tests/unit/test_forecast_model_contracts.py tests/integration/test_forecast_trained_execution.py -q`:
  **60 passed in 26.12s**. Strict versions/date maximum/float32 label limit included.
- Final fault-case gate `.venv/Scripts/python.exe -m pytest
  tests/unit/test_forecast_artifacts.py tests/integration/test_forecast_trained_execution.py -q`:
  **33 passed in 25.20s**. Failed fsync/publication and failed staging cleanup preserve
  primary cause; arbitrary loader bug never fallback; mismatched committed metadata
  prevents uncertain-success, retaining actual COMPLETED state.
- `python -m pip check`: no broken requirements. `git diff --check`: exit 0 after
  correcting one new trailing blank line in the ADR index. CRLF notices are Git notices.
- Original-file hash audit: no original file removed; all changes confined to authorized
  docs/manifest/schema expectation/module registration scope. ForecastRun source,
  baseline/S1 algorithms, corrective code, secrets and backendContext unchanged.
- OpenAPI factory JSON equals pre-edit snapshot. `.\scripts\db_status.ps1 -AllowUnmigrated`:
  development shelfcash remains revision 0006, sixteen empty business tables, one
  revision row; repository expected head 0008, at_head false. Read-only check only.

Pure runnable synthetic/backtest/train/infer commands exited 0, producing report
[S2_SYNTHETIC_COMPARISON](../reports/S2_SYNTHETIC_COMPARISON.md). No DB needed.

## Implementation map / handoff

New contracts: app/application/contracts/forecast_model.py. Pure computation:
app/domain/forecasting/features.py and evaluation.py. Concrete ML/float boundary:
app/infrastructure/forecast_model.py. Comparison orchestrator:
app/application/use_cases/forecast_evaluation.py. Trusted immutable artifact store:
app/infrastructure/storage/forecast_artifacts.py. Persistence integration:
app/application/use_cases/forecast_trained_execution.py, app/models/forecast_execution_metadata.py,
app/repositories/forecast_execution_metadata.py, alembic/versions/0008_forecast_execution_meta.py.
Operator commands: scripts/forecast_model.py, scripts/forecast_demo.py,
scripts/verify_forecast_trained.py. New tests: four forecast_model/trained/evaluation/artifacts
unit modules and tests/integration/test_forecast_trained_execution.py.
Existing schema tests and scripts/dev.py change only expected head/table set/count.
pyproject.toml pins three authorized ML dependencies. Existing fixed-baseline code and
S1 contracts/schema remain unchanged. ADR-015 is an authorized extension, not rewritten
ADR-012/014 intent. Source/export ZIPs are preserved historical S2.3 context, not refreshed.

Policy decisions are delegated routine implementation choices under the user task:
pooled exact scope/direct horizons, provisional 28-observation/14-row readiness,
fixed CPU config and versions, Decimal float conversion/clamp/rearrangement,
validation mean-pinball strict tie-to-baseline rule, exact immutable artifact replay,
retain-all/no automatic cleanup, purpose-specific execution metadata. None is a
claimed real-data quality threshold or independently user-selected number.

Limits/open quality work: real observed-sales dataset absent; no measured operational
quality, superiority or calibration. Missing-day semantics/source correction timing and
stable historical units need trustworthy real provenance. Point-in-time availability
is not reconstructed by date filtering. Loss mixes Product volume/unit scales; see
per-Product breakdown. Fixed exact dependency compatibility is conservative. Model-side
float32 labels/float64 features lose Decimal precision; captured facts retain exactness.
No network lost-ack/power-loss simulation, cross-platform bitwise retraining claim,
filesystem+DB distributed transaction, purge policy, automated crash recovery or actor
authorization. No next slice authorized; S3 remains unstarted.

Final full gate attempt 1: `.\scripts\test.ps1 all` collected 767; **766 passed,
1 failed, 1 existing Starlette/AnyIO deprecation warning in 325.12s**. Failure was
test_identity_store_schema's sorted expected-table list: new metadata table was
inserted out of alphabetical order. Corrected only the list order; no schema/runtime
change. Follow-up `.venv/Scripts/python.exe -m pytest
tests/integration/test_identity_store_schema.py::test_schema_exact_tables_constraints_indexes_and_metadata -q`:
**1 passed in 0.96s**, including Alembic/model metadata equality. Final full attempt 2
was required; do not use attempt 1 as a green gate.

## Final gate and persisted manual evidence — CURRENT FACT

Final full attempt 2: `.\scripts\test.ps1 all`: **767 passed, 1 warning in 325.76s**,
exit 0, zero skips (308 unit / 457 PostgreSQL / 2 API). One pre-existing Starlette/AnyIO
deprecation warning. No code changes after green; subsequent edits are final evidence/docs.
Two full attempts total because of the one schema test ordering correction.
Existing S1, fixed baseline, capture/serializer and corrective source hashes are unchanged.

Executed `.venv/Scripts/python.exe -m scripts.verify_forecast_trained`: exit 0,
SYNTHETIC only, no reset/migration. Fresh Sessions verified 14 persisted predictions
per run, exact model/artifact/input/metadata, replay after live sales changed to 999
and selling units changed. Store `546d51b3-d3fb-4671-9845-3e7aeb64ab4f`;
original run `f06781dc-78eb-4269-9a85-65b9d6ecedae`, manual replay
`e8eeacf6-551d-4890-bfdf-5e985d786ca0`, artifact
`d57e4ff89c6d669bff5fb949848a10d22bcfa31ce088e3fbc36d4b105d5ef6d7`.
Fixtures/artifacts remain for test-DB inspection until a later guarded test reset.

Executed both CLI commands, exit 0:

```powershell
.\.venv\Scripts\python.exe -m scripts.forecast_model replay --database test --store-id 546d51b3-d3fb-4671-9845-3e7aeb64ab4f --run-id f06781dc-78eb-4269-9a85-65b9d6ecedae --output runtime/s2_cli_replay.json
.\.venv\Scripts\python.exe -m scripts.forecast_model replay --database test --store-id 546d51b3-d3fb-4671-9845-3e7aeb64ab4f --run-id f06781dc-78eb-4269-9a85-65b9d6ecedae --persist --output runtime/s2_cli_replay_persisted.json
```

CLI new run `b26a2e0b-0d0b-4474-a100-2fcbba7da0e1`. Separate fresh-Session assertions
verified three distinct COMPLETED runs, 3 retained inputs, 3 metadata rows, 42 exact
predictions, common original fingerprint/artifact, and still-corrected live values.
Pure CLI output exactly matches persisted CLI replay prediction values. No retraining/
latest/operational-value lookup during replay. This is database evidence, not HTTP 2xx.

Final read-only `.\scripts\db_status.ps1 -AllowUnmigrated`: shelfcash still revision
0006, sixteen empty business tables + one Alembic row, expected head0008/at_head=false.
Development never reset/migrated. Final OpenAPI equality and original-file protection
audit passed. `git diff --check` passed. Branch/HEAD unchanged, nothing staged/committed.

S2.4/S2.5/S2.6/S2.7 implementation COMPLETE; persistence/replay integration VERIFIED;
S2 implementation complete / real-data evaluation pending. Real-data quality NOT
EVALUATED; superiority and calibration UNPROVEN. Suitable dataset/provenance requirements
are in FORECAST_TRAINED and comparison report. Implementation is ready for review/commit,
not a real-data forecast quality sign-off. No S3 or subsequent feature started.
