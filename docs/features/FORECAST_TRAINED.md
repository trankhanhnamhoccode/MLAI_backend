# Internal trained forecast — S2.4–S2.7

Classification: CURRENT FACT for code/checks, ACCEPTED DECISION for
[ADR-015](../adr/ADR-015-trained-observed-sales-forecast.md). Implementation and
synthetic verification are distinct from real-data quality, which is NOT EVALUATED.
No public API/auth/import/S3/stochastic/residual/N_eff/LLM/What-if was added.

## Contract, model and causal features

The frozen S2.1 observed DAILY Product-sales capture is unchanged: Store-local D,
exact captured units, inclusive requested history, D+1..7, missing unknown, explicit
zero observed, no duplicates, exact full Product/date output coverage. Baseline/S1
remain callable unchanged, including S1 empty completion. Domain validation, features,
baseline and metrics use plain Python; LightGBM/NumPy live only in infrastructure.

`forecast_model.py` contracts contain readiness, strict immutable metric summaries,
evaluation, artifact manifest and execution details. `TrainedForecastExecutionUseCases`
is a concrete internal extension sharing S2.3 capture/recovery, not a model registry.
No callable accepts uploaded arbitrary model binaries. Internal caller remains trusted;
Store scope is a persistence boundary, not actor authentication.

Three pooled Store/exact-Product-scope quantile boosters (`lightgbm_quantile / 1`)
use direct horizons 1..7, chronological Product UUID codes and feature version 1:
product_code/horizon/origin weekday/target weekday/target month; exact-date lag 0/1/7;
observed-only mean+count over trailing 7/28 days ending at origin. Lag 0 is origin-day
sales, which is known at the accepted end-of-day cutoff. Rolling Decimal arithmetic
uses independent precision 40 before float conversion. No global preprocessing
statistics or future quantities feed features. Training includes only observed targets
at origin+h <= training cutoff, and only origins with >=28 observed rows per Product.
Sparse targets are skipped, missing features become NaN, and zero remains zero.

Training requires >=28 observations and >=14 usable supervised rows per Product;
inference requires >=28 observations. These **provisional mechanics minima are not
quality thresholds**; baseline needs only one. Readiness applies to the entire scope.
Model scope/units/timezone/versions must match; its training cutoff cannot exceed D.
Inactive current Products are not filtered. Historical Product codes/units come from
capture, without inventing prior catalog availability or prior unit changes.

Config is fixed: CPU, one thread, seed 1729, deterministic/force_col_wise, 40 rounds,
7 leaves, min_data_in_leaf 5, learning_rate .05. No search/tuning. Quantities/features
enter float64; native LightGBM labels are float32, so huge labels reject explicitly.
This loses model-side Decimal precision; exact retained facts are unchanged.
Nonfinite model inputs/outputs reject. Decimal outputs use `Decimal(str(float(value)))`,
clamp negatives to zero and sort the three quantiles at each key. No integer/unit/money
rounding. Record negative-value count, raw crossing-row count and WARNING describing
applied postprocessing. Sorting enforces the contract, not predictive calibration.

## Backtest, metrics and selection

Origins start history_start+41, advance seven days, and stop when origin+7 exceeds
captured cutoff. First floor(n/2) origins are validation; later origins are holdout.
Each origin rebuilds the same causal training/inference from observed history <=origin.
Future corrections do not change earlier features, training rows or validation scores.
Corrections already contained in capture are NOT historical point-in-time knowledge;
true as-known-at-origin evaluation requires source availability/version history.

Only observed actuals score. Both families use identical valid keys at eligible origins;
if any Product fails training readiness, the whole origin is excluded and every
Product gets a reason (`SCOPE_NOT_READY` for otherwise-ready Products). Missing-target
count covers all planned Product×horizon keys, including excluded origins. Report
counts for overall/horizon/Product/Product×horizon; empty groups have null metrics.
Zero actual sum makes WAPE null, even for zero error (undefined denominator).
MAE P50, WAPE as ratio, pinball for each quantile/mean of three, inclusive [P25,P75]
coverage (nominal 0.50), mean width, raw/post crossings use observed-target weights.
Metric arithmetic uses independent precision 40; final display rounding is cosmetic.

At least two usable validation and two usable holdout origins are required to select
trained. Selection compares validation overall mean pinball, strict improvement only;
tie/worse/insufficient evidence selects baseline. Holdout scores do not select/tune.
Fixed configuration is never searched on either partition. Final artifact retrains on
all captured observations through its cutoff after evaluation; the rolling-origin report
is evidence for the family/config, not an unseen score of the final fitted booster.
Aggregate loss can favor higher-volume Products and mixes captured selling-unit scales;
per-Product metrics expose this limitation, without claiming unit-normalized utility.
Small empirical coverage near 50% is not proven calibration. Historical empirical
baseline quantiles are not evaluated/calibrated predictive distributions by definition.

`dataset_label=SYNTHETIC` or `USER_PROVIDED_UNVERIFIED`, `real_data_quality=NOT EVALUATED`
are explicit. An operator-provided file alone cannot prove data quality/PIT correctness.
No claim that the model beats baseline on suitable real observations is made.

## Artifact lifecycle and failures

`ForecastArtifactStore(root)` publishes three native LightGBM text files plus strict
canonical JSON manifest: versions, feature names, fixed config/seed/dependency versions,
exact training prepared snapshot+fingerprint, units/timezone/window and full evaluation.
SHA-256 over version-prefixed canonical manifest (which includes every model hash)
is the directory key and artifact identity. Input identity remains model-independent.
Files are fsynced then staging directory renamed on the same filesystem. Readers see
a complete directory; this is not a power-loss/directory-fsync durability guarantee.
Concurrent identical publication verifies existing content, never overwrites it.
Partial publication cleans only its private staging directory; cleanup errors preserve
the primary cause and trusted logs/notes. Published but unreferenced artifacts may
remain after DB failure. No FS/DB atomic transaction or automatic cleanup/TTL is claimed.
All artifacts/retained values for RUNNING/FAILED/COMPLETED remain; inspect references,
export/back up before manually deleting. `.pending-*` crash leftovers require inspection.

Load verifies key/path, exact file set, canonical manifest bytes, versions, training
digest, model hashes, feature/objective/alpha/seed consistency before inference.
Only exact pinned LightGBM 4.6.0/NumPy 2.2.6/SciPy 1.17.1 are compatible. Text is not
pickle and no arbitrary upload loader exists; hashes are integrity, not signatures
against a privileged malicious filesystem writer. New dependencies require new
validated artifacts/policy. Same-platform deterministic training is tested;
bitwise cross-platform retraining reproducibility is not promised.

## Execution, persistence and replay

1. Existing read-only REPEATABLE READ capture closes Session/connection.
2. Verify artifact and entire-scope readiness outside transactions. Recognized absence,
   model-not-ready or evaluation baseline selection chooses baseline for the entire
   scope; if baseline also not ready, typed error, no durable run. Invalid identity,
   corruption/incompatibility/programming errors never become successful fallback.
3. Known actual model_type/version/key is inserted atomically with retained JSONB
   input and purpose-specific execution metadata in a short transaction.
4. Compute outside every Session/row lock; validate full coverage/output before write.
5. Check retained digest, model identity and stable selection details under RUNNING
   lock. Predictions, completed warnings/counts and COMPLETED commit atomically.
   `metrics_json` remains absent: no inference metrics or arbitrary provenance.
6. Fresh-session verification compares retained input, all prediction values, actual
   model/version/key, warnings and full execution details before returning success.

`get_with_metadata` returns typed `{run, execution}` internally; original S1 `get`
and public OpenAPI are unchanged. Model start is known before compute; ForecastRun
training_start/end continue to denote execution input window for compatibility.
The artifact manifest contains the actual fitting window/cutoff; these can differ.
Execution details persist candidate identity, selection/fallback reason, postprocess
version/counts and structured warnings separately from evaluation metrics.

Replay loads only retained facts and original metadata/artifact; no current sales/catalog
values, latest model or retraining. Trained artifact missing/corrupt/incompatible is a
typed error, no fallback. Baseline replay preserves its fallback warning/reason even
if a candidate has since appeared. Persisted replay creates a new UUID and checks
current Store/Product identities/FKs without replacing captured units/values.
S1 runs without retention reject; old S2.3 baselines remain warning-free, no metadata row.

Protected cleanup/primary cause and conservative genuine uncertain-commit classifier
are inherited from the corrective patch. Only recognized uncertain completion can
reconcile into success after whole-aggregate verification. Durable programming errors
report run ID/COMPLETED, never rewrite to FAILED. Failed recording reports actual
RUNNING/FAILED/COMPLETED/UNKNOWN outcome. Process crash can leave RUNNING; no worker,
automatic retries/timeouts. Retry is explicit and creates a new UUID.

Migration 0008 adds only `forecast_execution_metadata` (scoped composite FK, object/v1).
Repository allows guarded initial insert/completion-only details update, no delete,
and no terminal update. Immutable-by-application, no trigger against privileged SQL.
Downgrade drops metadata only; retained input/runs/predictions survive, but new-path
warning/fallback audit is lost. Export before downgrade. Development DB was not migrated.

## Runnable commands

From backend (all output paths below must be new; commands refuse overwriting):

```powershell
.\.venv\Scripts\python.exe -m scripts.forecast_model synthetic --output runtime/demo-input.json
.\.venv\Scripts\python.exe -m scripts.forecast_model backtest --input runtime/demo-input.json --dataset-label SYNTHETIC --output runtime/demo-comparison.json
.\.venv\Scripts\python.exe -m scripts.forecast_model train --input runtime/demo-input.json --dataset-label SYNTHETIC --output runtime/demo-artifact.json
# Use artifact_identity printed by train, never 'latest'.
.\.venv\Scripts\python.exe -m scripts.forecast_model infer --input runtime/demo-input.json --artifact <identity> --output runtime/demo-predictions.json
# request.json is ForecastExecutionInput, not operational import data.
.\.venv\Scripts\python.exe -m scripts.forecast_model capture --database test --input request.json --output runtime/captured.json
.\.venv\Scripts\python.exe -m scripts.forecast_model execute --database test --input request.json --artifact <identity> --output runtime/persisted-run.json
.\.venv\Scripts\python.exe -m scripts.forecast_model replay --database test --store-id <uuid> --run-id <uuid> --output runtime/replayed.json
.\.venv\Scripts\python.exe -m scripts.forecast_model replay --database test --store-id <uuid> --run-id <uuid> --persist --output runtime/new-run.json
```

DB commands read-only-check migration head before use and never reset/migrate. Test
DB is default; development explicitly selectable only if already migrated by an
authorized operator. Training/backtest/infer need no DB. Capture -> train -> execute
captures fresh operational input for execution; replay is the exact retained path.
No automatic training/latest artifact lookup exists. See task notes for exact checks
and the synthetic comparison report. Suitable real Store-local daily observed sales,
stable captured units, sufficiently long window/Products, zero/missing semantics and
correction availability history are still needed to evaluate quality honestly.

One-command guarded persisted demo (requires shelfcash_test already at head, no reset):
`.venv/Scripts/python.exe -m scripts.verify_forecast_trained`. It creates isolated
SYNTHETIC identities, trains/evaluates, persists, corrects live sales/units and verifies
pure/new-UUID replay through fresh Sessions. Leaves demo rows/artifacts for inspection.

Warning classification: missing/readiness/selection fallback and applied negative/
crossing postprocessing are WARNING, not errors and not evidence of poor/good quality.
Corruption/incompatibility/nonfinite output is a typed error, not a warning that permits
success. Baseline-only S2.2 warnings remain empty; no new warning policy is retroactive.
