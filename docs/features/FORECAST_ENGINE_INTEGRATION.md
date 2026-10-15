# Forecast engine integration — compatibility, causal harness and benchmark protocol

## Authority and status

ACCEPTED DECISION (explicit E1 request, 2026-10-14): current Competition BE remains
host; a separate forecast adapter admits the new engine as a challenger. Preserve
host BOM, reciprocal loss, Product serving/FEFO, procurement/2, requirements,
winner and retained Planning. E1–E5 make no LLM/OpenRouter calls. Stochastic
scenarios, new procurement, explanation/chatbot and what-if are outside this work.

CURRENT FACT: E1 supplies static boundary traces, a frozen synthetic protocol,
portable admission fixtures and small offline validators. E2 implements the
separate opt-in detached adapter and private filesystem retention; fixed native
inference/cache/fresh-process replay are verified on tiny synthetic artifacts.
E3 implements bounded causal A/B/C training and paired scoring; newly fitted native
residual/point/CQR artifacts and all three arms replay exactly in a fresh process
on synthetic correctness data. E3 is PARTIAL / REAL_BENCHMARK_BLOCKED, not real
accuracy VERIFIED. Operational DB/public serving wiring and promotion have not run.
No public API, schema, permission, accepted ADR or production configuration changes.
E4–E5 remain NOT_STARTED.

Authority: [ADR-012](../adr/ADR-012-observed-sales-forecast-execution-contract.md),
[ADR-014](../adr/ADR-014-retained-baseline-execution.md),
[ADR-015](../adr/ADR-015-trained-observed-sales-forecast.md),
[ADR-A1](../adr/ADR-A1-observed-stockout-demand-policy.md),
[ADR-020](../adr/ADR-020-product-requirements-procurement-selector.md),
[ADR-021](../adr/ADR-021-operational-decision-v2-temporal-scope.md),
[ADR-022](../adr/ADR-022-internal-durable-planning.md).
Shared conventions stay in [API](../API_CONTRACT.md); Planning workflow stays in
[Planning](../PROCUREMENT_API_CONTRACT_VI.md); current authorization stays in
[Authorization](../AUTHORIZATION_CONTRACT_VI.md). This document owns the new
integration compatibility and experiment protocol, not those existing contracts.

## Source snapshots and trace reliability

CURRENT FACT: host main/base `052cddee075e165af2c0cea42ebc2e616c396760`, clean when
observed. E1 branch `feat/forecast-engine-challenger`, isolated sibling worktree
`backend-forecast-engine-challenger`, created from main. New engine HEAD
`62b94fa4d67cb04141d32be4e57d6f9740c2a8fc`; tracked tree clean, untracked review
reports/ZIPs and DATA_REQUIREMENTS preserved. Legacy is **archive-only** at review
SHA `cac7c5a6a46c5751063be6b27866e3672acd2e2a`; no live legacy checkout verified.

Read existing CURRENT_BE `REPORT.md`/manifest, NEW_ENGINE review and data
requirements, comparison report, and legacy `REVIEW_GUIDE.md` plus its two forecast
entrypoints. Review claims are historical/static context; their test reports are
not fresh E1 execution. Exact ZIP identities, traced source hashes and metadata
inventory belong to [snapshot_inventory.json](../../tests/fixtures/forecast_engine/snapshot_inventory.json).
No ZIP extraction into source, customer-row export, model activation or engine edits.

### CURRENT FACT — host boundary (wired source, not deployment evidence)

| Boundary | Source/symbol and behavior |
| --- | --- |
| Prepare | `app/application/forecast_preparation.py:prepare_observations`: active scope/current selling units; start−1 cutoff; schema2/causal_stockout_v1; sparse canonical observations and seven dates. `contracts/forecast_execution.py:PreparedForecastInput` validates and derives separate demand_records. Explicit schema1 remains observed_sales_v1. |
| Stockout | `app/domain/forecasting/stockout.py:reconstruct`: strictly earlier known-false samples within42 days; same weekday when≥3, otherwise≥3 overall; lower median bounded below by observed quantity. Unsupported censored rows excluded; unknown uses observed quantity with warning. `forecast_demand.py:usable_histories/demand_warnings` feeds both host families. |
| Baseline | `app/domain/forecasting/baseline.py:historical_quantiles/assess_product_readiness`, `use_cases/forecast_baseline.py:run_historical_quantile_baseline`: empirical linear quantiles,≥1 usable observation per Product; same quantiles across7 dates. READY is computability, not quality. |
| Trained | `app/infrastructure/forecast_model.py:training_rows/train_quantiles/predict_quantiles/require_compatible`: pooled3 LightGBM4.6.0 quantile boosters; exact-date lag0/1/7, observed-only7/28 mean/count, weekdays/month, Product code and horizon.≥28 usable observations and≥14 supervised rows/Product. Float→Decimal(str(float)); clip negative, sort quantiles with raw diagnostics. |
| Evaluation | `use_cases/forecast_evaluation.py:at_origin/backtest/choose_family`:7-day origin spacing, first chronological half validation, later holdout; strict lower equal-target mean pinball selects trained, ties/insufficient select baseline. Censored actuals excluded; unknown observed actuals currently included. Internal report has two family literals; cannot store C by relabelling it LightGBM. |
| Artifacts | `infrastructure/storage/forecast_artifacts.py:ForecastArtifactStore.load/publish`: text boosters + strict canonical manifest, content address/hash and dependency checks; no pickle/latest; atomic immutable publication. Manifest embeds training capture/evaluation/policy. Corrupt/incompatible is error. |
| Retention | `forecast_serialization.py:serialize_prepared/restore_prepared`: serialization1 and domain prefix `shelfcash.forecast-input.v1`; schema1 elides newer fields to preserve historical bytes; schema2 includes observations/stockout/derived policy/evidence. `forecast_trained_execution.py:TrainedForecastExecutionUseCases` captures/starts/computes/completes and replays exact retained input/artifact, outside model/FS transactions. |
| Serving | `use_cases/forecast_serving.py:ForecastServing.prepare/choice/identity/serve`: accepted BASELINE or trained configuration, explicit compatible fallback, actual/candidate identities and dependency pins, full output validation, exact identity reuse. No public automatic training. |
| Planning | `app/main.py:create_app` wires ForecastServing→`use_cases/planning_worker.py:PlanningExecution.execute`→`infrastructure/database/planning_capture.py:PostgresPlanningCapture.read`→retain→`decision_pipeline_v2.py:execute_captured_pipeline_v2`→`bom.py:expand_bom`→procurement/2→comparison/selector→fenced finalization. Captured source/config digest mismatch permits at most2 re-preparations. Retained GET/PDF does not infer again. |

### CURRENT FACT — new engine boundary (wired vs library)

All paths here are relative to `Forecast_Engine_FandB` at the pinned snapshot.

| Boundary | Source/symbol, wiring and gap |
| --- | --- |
| Public inference | `shelfcash_forecast/pipeline/inference_pipeline.py:predict_demand` calls predict_m1→correct_forecast_point→calibrate_forecast→build_forecast_package. Used by application/stage runners; accepts canonical DataFrames, artifact directory, inclusive cutoff and horizon. It is not an HTTP/DB host adapter. |
| Input | `data/adapter.py:adapt_sales_history/adapt_forecast_input`, `data/validator.py:validate_sales/validate_calendar`: names can generate IDs/default Store and validator can aggregate duplicates; host must validate strict captured IDs/grain before this permissive boundary. Never use name-derived identities or silent aggregation. |
| Dense panel | `data/panel_builder.py:build_daily_panel/resolve_missing_sales`: missing open-day sales remain missing; absent closure defaults false. Known closed rows have quantity cleared for model eligibility, with row_observed retained. Host observations must remain immutable; contradictory positive-sales/closure evidence blocks. |
| Reconstruction | `data/demand_reconstruction.py:reconstruct_demand`: prior known-false same Store/Product, default84-day lookback/min3; same-weekday preference; ordinary median + support/recency/IQR confidence gates; apply only medium/high, unsupported censored excluded from train/features. Unknown uses observed. This differs from host42-day/lower-median policy. |
| Features | `features/specification.py:MODEL_FEATURES/CategoryEncoder`, `historical.py:add_historical_features`, `training_table.py:build_runtime_rows/add_target_seasonal_lags`: codes, horizon, history count,1/2/7/14/28 lags,7/14/28 means/medians/std, trend, stockout features and causal seasonal target references. Unknown encoded identity or<28 observations blocks public fixed inference absent explicit overrides. Overrides are outside this integration. |
| Future availability | `features/future.py:add_calendar_future_features`: target calendar join, weather only forecast-kind with issued_at/available_at≤origin; unavailable weather masked. Missing calendar becomes holiday/closure0, availability0. Calendar has no equivalent vintage gate. Host must supply independently captured known-at facts, not hide absence. Engine compares weather to normalized D midnight, stricter than host inclusive EOD D: a vintage issued later on D can be masked despite being known before next run. Preserve this gap; do not claim an aware admission fixture proves native feature inclusion. |
| Quantile model | `models/predictor.py:predict_raw_quantiles`:3 boosters; absolute or signed seasonal residual + causal seasonal-naive anchor, then nonnegative clip. `baselines/seasonal_naive.py` anchor has fallback; MA/ETS are training/evaluation comparators, not a missing-artifact runtime fallback. |
| Postprocess | `calibration/crossing.py:correct_quantile_crossing`; `calibration/point.py:apply_point_corrector` applies frozen common offset once (clip at zero); `calibration/cqr.py:apply_cqr_calibrator` emits separate interval bounds. Inference state guards stage order. calibrate_forecast zeros quantiles, intervals and baseline on factual planned-closed dates. |
| Training vs research | `pipeline/training_pipeline.py:train_forecast_core` is executable opt-in default training: absolute target through train_model_bundle, identity point corrector, CQR. `models/trainer.py:train_model_bundle` permits residual target options; `calibration/point.py:fit_point_corrector` is library-only in inspected tracked caller graph. Demo metadata declares signed residual + fitted point corrector; no corresponding full research fit caller was found. Do not claim default training reproduces that artifact. |
| Registry | `registry/loader.py:load_artifacts/_verify_checksums`: supports feature schema2.0/3.0, exact feature list, CQR order-statistic-v2; schema2.0 can synthesize identity point corrector. Missing checksum manifest only warns; checksum coverage is caller-provided. `registry/writer.py:write_artifacts/_publish_staged_directory` can replace existing target via backup; not host content-addressed immutability. E2 must own stricter admission/storage. |
| Temporal eligibility | predict_m1 checks training/calibration label dates≤D; production needs promoted + production_available_at date≤D. It does not independently gate point-fit date/full aware publication instant. Adapter must check all windows and actual publication/availability, not only normalized dates. Demo/backtest_replay modes do not prove production eligibility. |

HISTORICAL INFORMATION: legacy ZIP `app/services/forecast_service.py:ForecastService`
defaults to `ExistingForecastCoreProvider` from `app/forecasting/providers.py` and
`shelfcash_core`; optional ShelfCashForecastProvider is shadow. That structure and
its schemas are reference only, not something to port into the greenfield host.

## Adapter compatibility matrix and E2 boundary

ACCEPTED DECISION / CURRENT FACT E2 — detached input: host-owned validated raw
observations plus explicit scoped calendar/closure, real inference availability
instant, pinned challenger artifact and versioned adapter configuration. Weather
is excluded in this arm. The current PreparedForecastInput contains
host-derived demand_records; pass **only observations** to challenger sales_history.
Keep original host capture/digest intact and give challenger projection its own
policy identity/digest. Never relabel host demand_records as challenger estimates.

| Topic | Frozen compatibility requirement | Support/gap |
| --- | --- | --- |
| Identity/scope | One captured Store, explicit sorted UUID Products, exact selling units; per-row Store/Product checks before engine coercion. Product_name may be opaque UUID display text; names never keys. Preserve all requested Products. | E2 strict preflight/mapping implemented; no operational host wiring. |
| Time | Store-local DATE D inclusive; history_start…D; D+1…D+7. Known-at uses aware actual execution instant after EOD D, separately retained; no fabricated23:59:59 cutoff. At backtests state explicit next-run availability assumption. | E2 aware instant/Store-date gates implemented; weather disabled. |
| Sparse/zero | Absence is missing; explicit Decimal0 remains observed. Dense model panels never write canonical rows. No fill of canonical quantities or missing forecast outputs. Native last_observed_demand uses forward fill as a separate feature; never treat it as an observation. | Supported observations; host/engine different derived panels preserved by policy. |
| Units | Output quantity is Product selling_unit, no integer rounding/unit conversion/Ingredient inference. Reject absent/wrong unit, overflow or float conversion failure. | E2 rejects absent/wrong native units and float overflow. |
| Coverage | Exact Product×7 dates, no duplicates/unexpected keys; target horizon consistent. All requested Product readiness before execution; no partial success. | Existing host validator reusable for final result. |
| Stockout | true/false/null preserved; sales≠estimated demand. C arm reconstructs original observations exactly once using native policy. Never pass usable_histories or host demand_quantity as quantity_sold. | E2 uses native boundary; model+estimator changes expressly declared. |
| Quantiles | P25/P50/P75 are demand quantiles mapped directly to host LOW/BASE/HIGH. Preserve engine raw crossings/clipping diagnostics and frozen postprocess identity; reject final crossing/nonfinite/negative. Decimal(str(float)), no extra silent repair. | Supported after strict output validation; raw diagnostics need state capture. |
| CQR | Separate interval_lower/upper, coverage target, calibrator and point IDs/fit provenance. Never replace P25/P75; no joint path/probability guarantee. | E2 separate typed CQR/evidence envelope implemented; host persistence unchanged. |
| Closure | Zero only from same-Store, sourced, known-at closure facts covering dense historical panel and forecast dates. Known open/holiday false also need evidence; missing is data-blocked. Positive observed sales on declared closed date require resolution. | CalendarEvent history is not complete daily operating calendar. Host closure/weather capture currently absent. |
| Artifact | Explicit immutable content identity covering all3 boosters, config, features, category mappings, point, CQR, metadata and training manifest. Verify hashes/paths/versions/scope/units/timezone before native load. No optional checksums, schema2 implicit corrector, latest, download, train or promotion. | E2 strict schema3/content-addressed envelope implemented before native load. |
| Temporal | Training, point-fit and calibration labels and their known-at boundaries must precede artifact fit; artifact publication/availability must precede inference; production additionally needs explicit promoted identity and production_available_at. Original exposed holdout remains inadmissible promotion evidence. | E2 checks actual windows/publication; production mode remains disabled. |
| Reuse/replay | Separate challenger model_type/version, host input digest, projection/policy/config/source/features/postprocess/dependency/artifact identities and supplemental capture digest. Stable ordering and canonical decimals. Cache only exact identity, partition by Store; replay exact captured input and bytes, no current lookup/retrain/fallback. | E2 separate typed contracts/private filesystem cache/replay implemented; host-only literals and schema1 untouched. |
| Failure | UNSUPPORTED: incompatible schema/unit/scope/horizon/basis. DATA_BLOCKED: missing history/calendar, unsafe vintage/temporally ineligible/unpromoted artifact. TECHNICAL_ERROR: absent/corrupt pinned bytes, invalid native output, dependency/load/inference error. Sanitized code/detail, never broad success fallback. | E2 typed errors implemented: UNSUPPORTED, DATA_BLOCKED, ARTIFACT_CORRUPTION, DEPENDENCY_MISMATCH, TECHNICAL_FAILURE. |

ACCEPTED DECISION: adapter cannot query/write operational DB or authorize users.
Host owns permission checks, capture, persistence and transactions. No BOM calls,
new multiplicative loss, Ingredient service, BALANCED-first winner, scenario weights,
overrides or scenario probability. Explicit host fallback policy remains historical;
benchmark arms disable fallback so failures cannot masquerade as challenger scores.

Determinism means same captured input/config/versions/artifact produces the same
canonical predictions on the verified runtime. It does not promise bitwise
retraining across platforms. E2 must test repeated/fresh-process replay and document
any native numerical tolerance separately from exact retained byte/digest integrity.

<a id="e2-runtime"></a>
## CURRENT FACT — E2 implementation and reproducible execution

Internal entrypoint `app/application/use_cases/forecast_challenger.py:ForecastChallenger`
defaults enabled=false. `scripts/forecast_challenger.py` requires `--enable`, offers
infer/replay only and uses this checkout's `runtime/challenger`. `app/main.py`,
ForecastServing, worker flags, public endpoints and operational storage are unchanged.
OFF is tested in a fresh process without importing pandas/LightGBM/ORM/FastAPI/app.main.
This internal caller is trusted; it confers no actor/Store authorization.

`contracts/forecast_challenger.py` supplies frozen typed raw observations with
available_at/source, sourced closed/holiday facts, artifact/provenance/windows,
separate ForecastEngineResult/CQR/raw-stage/reconstruction evidence and typed errors.
Unknown stockout is preserved; missing days stay absent in the canonical input.
Dense reconstruction evidence is diagnostic float-projected state, not canonical
Decimal observations. Native unsupported censored proxy can still contain observed
lower bound; feature_demand=null/train_eligible=false explains its exclusion.
`forecast_challenger_validation.py` validates scope/unit/date/coverage/availability,
actual fit windows, reconstruction lineage, outputs and research/production status.

`infrastructure/forecast_challenger_native.py` composes unchanged pinned native
functions: adapt/validate → dense panel → reconstruction **once** → historical/
seasonal/future features → category/schema/readiness → fixed3 boosters → native
crossing repair → point correction once → CQR and factual closure → native public
package. This narrower composition is necessary to retain reconstruction and raw
stage diagnostics; an independent test compares quantiles and CQR against native
predict_demand on the same admitted fixture. No override path or new BOM/procurement/
scenario/provider function is called. Weather fields cannot enter the typed input;
target weather features remain NaN. Decimal conversion is Decimal(str(float)),
float_policy=decimal_str_float/1; raw signed residuals are allowed, final quantities
must be finite/nonnegative/ordered. Quantiles and CQR never replace each other.

The non-editable distribution `shelfcash-forecast-challenger-snapshot`
version0.1.0+62b94fa.e2 contains21 inference modules/29 Python files under
`vendor/forecast_challenger`. Algorithm files are byte-identical to engine62b94fa;
aggregate initializers alone are replaced with inert initializers. Optional lazy
forecast_overrides import is not packaged and cannot be reached through this adapter.
No full engine/application/train writer/BOM/procurement/stochastic/LLM package is copied.
[Snapshot provenance](../../vendor/forecast_challenger/shelfcash_forecast/snapshot_provenance.json)
records original/emitted hashes, transformations and source_digest
`99ef7c2631f3bb349c303b311718fb0bd81471469715928fb99c9e28de28aca4`.
No upstream LICENSE/COPYING file was found; original source notices are preserved.
`.gitattributes` preserves snapshot byte line endings so checkout/build retains hashes.

Runtime admission checks installed distribution version, every declared source byte,
file set/import location, exact dependency pins, Python/platform/machine and adapter/
shared-boundary code hashes. It rejects editable/shadow source or changed identities.
The [runtime/build lock](../../scripts/requirements-forecast-challenger.lock.txt)
keeps LightGBM4.6.0/NumPy2.2.6/SciPy1.17.1, adds pandas2.2.3 and pins transitives;
[test lock](../../scripts/requirements-forecast-challenger-test.lock.txt) supplies
focused offline test imports. No separate inference process/service or host dependency
upgrade is necessary for this selected compatible environment. E2 runs Python3.11.9
on Windows AMD64. Exact replay compatibility is conservative; dependency upgrades
require new artifact/runtime identity, never weakening old replay.

Artifacts live at artifacts/<identity> under private runtime. Strict content identity
covers schema3, boosters, category/config/features, point/CQR, training/native metadata,
checksum manifest, scoped units/timezone, dependency/code identity and fit/publication
windows. Missing pinned bytes are a technical failure; bad hashes/manifest bindings
are corruption; incompatible schema/scope/config is unsupported; missing facts or
future labels/publication are data-blocked. No latest/download/train/fallback path.
`ChallengerStorage.publish_artifact` is an explicit trusted setup/import operation,
never called by inference; it does not create production eligibility.
Native original metadata must match envelope windows/model/dependencies, point/CQR
binding and scoped training provenance. Existing exposed demo is not silently
rewrapped as compatible or promoted. Production requests first check eligibility,
then still reject PRODUCTION_SERVING_NOT_ENABLED_E2. No artifact is promoted in E2.

`forecast_challenger_serialization.py` has separate role-prefixed version1 canonical
UTF-8 JSON/digests: UTC instants, sorted captured keys/arrays and exact numeric-equivalent
Decimal strings. Cache identity covers arm/raw observations/calendar/availability,
artifact/config/postprocess and runtime/code; no cross-Store/arm reuse. Immutable
runs/<identity>/evidence.json retains full input/output plus hash. Atomic staging
publication never overwrites existing evidence; failures retain pending directories
for inspection. Every reuse rechecks pinned bytes/runtime and semantic bindings.
Replay reads retained input, computes again with exact pinned artifact, compares full
canonical output equality, and never writes repaired/recomputed evidence. No live DB
or current facts. Identity hashing is not authenticity/tamper-proof security; privileged
filesystem writes can bypass application immutability. Runtime versions/source checks
are not a universal cross-platform numeric proof or full native-binary supply-chain audit.

From this isolated worktree, create/install only its own venv (do not run main's
local_runtime commands):

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r scripts/requirements-forecast-challenger-test.lock.txt
.venv/Scripts/python.exe -m pip wheel --no-deps --no-build-isolation --wheel-dir runtime/challenger/wheels ./vendor/forecast_challenger
.venv/Scripts/python.exe -m pip install --no-deps runtime/challenger/wheels/shelfcash_forecast_challenger_snapshot-0.1.0+62b94fa.e2-py3-none-any.whl
.venv/Scripts/python.exe -m scripts.verify_forecast_challenger
```

The last command explicitly creates a tiny bounded correctness setup:3 constant
quantile boosters,14 rows each,2 rounds,1 thread; fixed synthetic point/CQR offsets,
two selling units, sparse/zero/stockout states and sourced closure. Model text stays
ignored runtime, never Git. Inputs/code/windows/config/artifact/output identities
are retained. The setup is **not** the frozen E3 C training recipe, empirical
calibration, forecast accuracy or promotion evidence. The ordinary infer/replay CLI
never trains. Verifier prints an input path/cache identity for manual continuation:

```powershell
.venv/Scripts/python.exe -m scripts.forecast_challenger --enable infer --input runtime/challenger/input-<identity>.json
.venv/Scripts/python.exe -m scripts.forecast_challenger --enable replay --identity <identity>
.venv/Scripts/python.exe -m pytest tests/unit/test_forecast_challenger.py -q
```

Coverage distinguishes real native fixed inference/public-stage equivalence/replay,
metadata/filesystem guards and deliberately mocked runtime/nonfinite/foreign-output/
exception failures. Host regressions cover forecast execution semantics, schema1/2
serialization, stockout/causal prefixes and baseline. No DB/server/provider/worker or
OpenAPI execution is needed; API source is unchanged. Checks/results/fail→fix belong
to the conversation, not a cumulative PASS log. E3 still needs an authorized unseen
population/vintages, sourced daily operating calendar and frozen causal training/
point/CQR harness with per-origin resources. Public/persistent host integration and
permission acceptance belong to later authorized work.

## Frozen accuracy benchmark protocol — E3 proposal, no run in E1

Machine-readable [benchmark_manifest.json](../../tests/fixtures/forecast_engine/benchmark_manifest.json)
freezes arm names, configuration content digests, selection, scoring and promotion
gates. It is **synthetic correctness only**, benchmark_enabled=false and
promotion_enabled=false. Concrete sample origins/windows are illustrative, not a
claim that real data or per-origin trained bundles exist. E3 must instantiate a new
real-data execution manifest and freeze its full digest **before scoring**; unchanged
policy IDs apply, sample dates do not authorize a run or tuning by old holdout.

| Arm | Frozen configuration and interpretation |
| --- | --- |
| A_be_baseline_causal_v1 | Host empirical baseline/1 + causal_stockout_v1;≥1 usable observation; no artifact. |
| B_be_lightgbm_causal_v1 | Host ADR-015 exact config: seed1729,40 rounds,7 leaves,min leaf5,rate.05,1 thread, deterministic/force_col_wise, features/1/postprocess/1 + causal_stockout_v1. Train only explicit E3 per-origin captures; use trained output regardless host validation preference, no fallback. |
| C_engine_native_reconstruction_v1 | Native84-day reconstruction/confidence gates + full feature schema3 + signed seasonal residual/anchor λ1; all3 objectives quantile; point horizon_shrunk_median_residual (min30 tasks/7 distinct dates, shrink20); CQR order-statistic-v2, nominal.50/min20. Native sample config frozen in manifest, n_jobs changed4→1 for this proposed experiment,1500 estimators, no early stopping/search. This is an estimator+features+model+postprocess challenger, not a pure model substitution. |

Only these three arms are registered. A BE-reconstruction-fed challenger is
**unsupported by predict_demand** without a separate projection/stage adapter.
If authorized later, add a distinctly named/versioned arm, retrain for that policy
and refreeze before results; do not disable stockout flags to sneak it through.
Neither default public train_forecast_core nor old demo artifact is the C fit recipe;
E3 requires an explicit harness using existing low-level trainer/point/CQR functions.
That harness must preserve the external engine source and record its own code hash.
For C training, the supervised residual is native demand_proxy minus the causal
seasonal anchor at that task's origin; record anchor fallback and reference dates,
never subtract a target-date actual or use a reference after origin. Fit point/CQR
only on observed known-false OOS targets under the declared masks.
The registered C arm excludes all weather features (NaN), with that policy in its
config identity; calendar/closure still require facts. Any later weather-enabled
experiment needs a separate frozen configuration and tests reconciling aware
availability with the native midnight gate. E1 safe-weather fixtures check metadata
admission only, not that a native model used the weather.

### Eligibility, chronology and availability

Use the same declared Store/Product/unit scope, canonical observation snapshot,
history window, origins,7-day horizon and scoring masks across paired A/B/C.
Predeclare eligibility using facts/readiness, not errors/scores. Publish population,
all arm-specific exclusions, unknown/missing/censored counts and failures even when
primary comparison uses the paired intersection. Paired coverage below100% of
predeclared eligible scoring tasks makes promotion insufficient evidence; never
remove a hard Product/date afterward to improve scores. Each Product must have
complete inference output even when some target actuals are unscoreable.

Chronological origin spacing7 days; first half validation, later untouched holdout,
minimum2 origins in each. No target-window overlap across these origins. Preserve
task key(Store,Product,origin,horizon) and distinct outcome key(Store,Product,date).
If supplementary overlapping origins are declared, report both counts and cluster
uncertainty/resampling by Store/date blocks, never independent task-row significance.

At each origin O freeze available canonical facts/labels. A/B train/project at O;
C booster training labels end O−56, point-fit targets O−55…O−28, calibration targets
O−27…O, inference O+1…O+7. Point-fit and calibration are separate OOS predictions:
purge point tasks whose origin precedes booster-fit availability; purge calibration
tasks whose origin precedes frozen point-fit availability. All features/reconstruction
use their own forecast-origin prefixes and known-at gates. Include actual fitting,
publication and prediction instants; same-day fit→prediction ordering needs evidence.
If training/task support falls below native minima, block/report rather than shorten
windows after observing scores. Earlier holdout facts can enter later rolling-origin
training only once genuinely available under the frozen expanding-window protocol;
they cannot tune configuration or choose family. Audit this separately from tuning.

Target-date filtering is not vintage recovery. No revisions/availability history was
established in E1. When unavailable, declare retrospective-current-revision and
EOD-next-run assumptions, publish affected fields and limitations; do not claim
full point-in-time fidelity. Future realized weather is never a feature. Calendar
holiday/closure must have sourced known-ahead vintage, otherwise C is blocked.
Research simulated_available_at is not real production publication.

### Scoring, selection and promotion

Primary metric follows host convention: equal-target aggregate mean of P25/P50/P75
pinball losses on paired **observed known-false** targets, validation only. For error
e=y−qτ, pinball=max(τe,(τ−1)e). Strict lower loss wins; ties order A then B then C.
Known-false primary mask is an explicit integration protocol choice; host historical
evaluation includes unknown observed targets too, so report that compatibility mask
separately and never compare the two aggregates as the same metric.

Report MAE=mean|P50−y|, WAPE=sum|P50−y|/sum y (null when denominator0), signed
bias=mean(P50−y) and normalized bias=sum(P50−y)/sum y (null at0); each pinball and
mean; P25–P75 coverage/width separately from CQR coverage/width and nominal target.
Count raw/final crossings, clipping, nonfinite failures, Products, horizon1…7,
partition and stockout strata. Unknown-stockout observed scores are supplementary
with censorship warning. Known-stockout scores are only censored lower-bound
diagnostics; neither observed sales nor reconstructed proxy is latent-demand ground
truth. Missing actuals are excluded with reason/count. No target imputation.

Also record train/inference wall time, verification/load/serialization time, peak
memory if measured, artifact total bytes, runtime/dependency hashes, repeated and
fresh-process replay. No E1 timing is an accuracy or production latency benchmark.

Promotion gates are frozen technical criteria, not statistical guarantees: C strictly
improves mean pinball against **both** A and B on validation and independent unseen
holdout;≥2 origins and≥28 distinct paired outcomes per partition; complete requested
output and100% predeclared paired scoring coverage; final crossing/nonfinite0;
exact retained replay digest; E4/E5 host Planning acceptance. Numeric minima only
screen obviously insufficient evidence. Publish per-Product/horizon regressions and
block-level uncertainty; no automatic activation, user approval remains required.
No old15.35% WAPE, exposed holdout, synthetic results or lack of unseen data can pass.
Holdout gates can reject the validation-selected challenger; they cannot select a
different family/configuration or trigger a second tuned run on the same holdout.
Too little real evidence yields EXPLORATORY or INSUFFICIENT_EVIDENCE, not superiority.
Resource ceilings and the full real-data run manifest must be fixed before E3 execution.

## E4 Planning impact protocol

PROPOSAL: capture one immutable operational/2 context per experiment including
recipes/dated assignments/yields/loss, original lots/receipt/expiry/current balances,
terms/arrivals/fees, budget/capacity/supplier limits/completeness, requirements,
policy and exact search resource limits. Hold all of it identical across A/B/C;
replace only forecast Product/date quantities plus truthful arm provenance. Same
host BOM, serving/FEFO, procurement search, exact validator, comparison and selector.
Freeze candidate-generation seeds/bounds/solve counts/deadlines; retain journal,
incumbent/rejection/proof scope and timings. Search variability is evidence, not
an excuse to attribute every difference to forecast quality.

Report outlay (purchase+payable fees), each Product/path service and lost servings,
Ingredient shortage/expiry/ending stock in their own units, hard validity, customer
pass, winner/no-winner, incomplete/unproven/technical error and search evidence.
Compare independently simulated realized outcomes only with independently sourced
demand; censored sales cannot certify service against latent demand. If historical
operational facts are absent, use declared counterfactual fixtures/current-capture
hypothetical basis, never claim actual historical stock or realized monetary savings.
Forecast paths are deterministic assumptions, not weighted stochastic scenarios.

## Data/artifact inventory and requirements

CURRENT FACT: metadata-only [snapshot inventory](../../tests/fixtures/forecast_engine/snapshot_inventory.json)
records names/sizes/hashes and model metadata, never customer rows. No DB inspected.
Original BE runtime/model_artifacts contains two artifact directories; file bytes
were hashed, not loaded or parsed as training data. Their active serving selection,
customer provenance and temporal admissibility are unknown. E1 owns an empty private
artifact directory, not copies of those operational artifacts.

New demo/artifacts has21 files, including3 text boosters, schema/config/mappings,
point/CQR, training metadata and prediction/residual parquet assets. Core10 checksum
entries matched at inspection (parquet not loaded). Model metadata:
`m1-m2-research-res_07-seed42`, schema3.0, trained_candidate, production_available_at=null,
fit2026-10-04; train/point/calibration cutoffs2026-06-16/06-30/07-15;
test cutoff2026-08-12; EXPLORATORY_OLD_HOLDOUT_ALREADY_EXPOSED and
UNSEEN_DATA_UNAVAILABLE. Metadata claims Python3.14.4/LightGBM4.7.0/NumPy2.5.3/
pandas3.0.6; those versions were not installed or validated by E1. Host pins
Python3.11+/LightGBM4.6.0/NumPy2.2.6/SciPy1.17.1. Dependency resolution and native
artifact compatibility must be verified in E2's own environment; no host upgrade.

Six demo workbooks exist (POS, usage, stock/supplier, recipes/rules, context/calendar,
menu); E1 recorded file sizes/hashes only, no worksheets/rows loaded. File presence
does not prove Store identities, units, complete daily calendar, vintage or training
sufficiency. Existing synthetic host fixture is120 days/two Products with no missing
or zero days; E1 adds explicit sparse/error cases. Neither establishes real quality.

| Needed by | Required input/provenance | Current gap |
| --- | --- | --- |
| E2 | Resolvable isolated dependency pins, schema3 complete fixed artifact, scoped Products/units/timezone; closure/holiday coverage and known-at provenance; point/CQR fit binding and publication instants. | E2 isolated dependencies and tiny synthetic native artifact verified; real/research artifact admission and operational supplemental capture absent. |
| E3 | Authorized unseen daily sales, stable scope/units, tri-state stockout, observations and revision/availability times; enough prefix history for native minima plus point/calibration windows; sourced calendar and optional forecast-weather vintages. | No authorized real unseen dataset/version manifest; no vintage fidelity evidence. Demo exposed. |
| E4 | Historical operational snapshots and actual demand/receipts/expiry/outlay evidence, or explicit counterfactual fixtures; host policies/search resources captured exactly. | No historical operational population established; empty user Store is not benchmark data. |
| E5 | Same-runtime accuracy/impact evidence, exact replay, opt-in serving/persistence/error/revocation acceptance and explicit promotion/rollback selection. | Deferred; no production candidate accepted. |

PROPOSAL — real execution manifest must retain: schema/protocol digest, code commit
and working-tree/source hashes for BE/engine/harness, frozen configs and seeds,
dependency lock/interpreter/platform, dataset/schema hashes and authorized scope,
units/timezone, origin/target masks/exclusions, revision/availability assumptions,
all train/point/CQR windows and purged tasks, per-origin artifact files/digests/fit/
publication/eligibility, stage/diagnostic versions, captured operational digest for
E4, prediction/score/replay digests, task/distinct outcome counts and resource limits.
Hashing proves identity, not authenticity or authorization. Retain original provenance;
never overwrite older baseline comparisons. Raw private execution outputs belong in
owned ignored runtime; reusable synthetic acceptance inputs stay in tests/fixtures.

## E3 offline benchmark

CURRENT FACT: `scripts/forecast_benchmark.py` is an explicitly enabled offline caller,
with no database/provider/worker dependencies. Typed dataset/plan admission freezes
scope, units, source revision, known-at assumptions and E1 protocol digest before fits.
One configuration per A/B/C, four origins, one thread, maximum24 booster fits,
8 point/CQR fits and300 seconds are frozen. The wall budget is cooperative, checked
between causal prefixes and booster iterations; it is not a hard process deadline.
Completed fits and handled-failure resource receipts survive resume. Complete runs
reuse only matching input/config/training/runtime/host-source identities after replay;
report changes use `rescore`, with no fitting and no overwrite of earlier evidence.

Training builds each feature row from its independently availability-filtered raw
prefix. A/B retain causal_stockout_v1; C reconstructs raw observations once per prefix
with native policy, signed seasonal residual anchor and the frozen E1 configuration.
The harness maps n_estimators/n_jobs explicitly to low-level LightGBM rounds/threads,
then invokes pinned native point and CQR fit functions. This is a new candidate fit,
not reproduction of the old research artifact. C labels end O−56, point uses
O−55..O−28, CQR O−27..O; postprocess tasks originating before the preceding fit is
available are purged. ACCEPTED DECISION (explicit E3 request): all holdout target
dates are quarantined from fitting in every arm, including later origins, without
changing windows, masks or criteria. Mature earlier observations may be inference
features, but holdout labels never select/tune parameters. Weather remains excluded.
Quantiles and separate CQR intervals retain actual clipping/crossing diagnostics.

Artifacts retain actual fit/publication/execution instants alongside historical
origin/window cutoffs. Offline inference runs after the new local artifact is
published, not with a fabricated historical publication date. This proves causal
retrospective correctness on admitted inputs, not historical deployment availability.
Schema3 artifacts use E2 strict checksum/runtime/scope/point/CQR admission and replay.
No artifact is promoted and production_available_at remains null.

CURRENT FACT data inventory: only the portable synthetic generator
`tests/fixtures/forecast_engine/benchmark_setup.py` is admitted for this execution.
It declares fictional calendar independently before sales generation, with missing,
zero, known-false, censored and unknown observations; two synthetic Products use cup
and piece, daily history2025-11-01..2026-06-29, explicit calendar through2026-07-06,
generated next-run availability. Origins2026-06-01/08/15/22 follow the unchanged E1
two-validation/two-holdout/window policies. Dates in E1's template are illustrative;
the execution dates were frozen before training and before actual local artifact fits.
Dataset digest is `3178e138eff2be24654400e07a03033a3df29b89e4cca3f6ce658d8ad6451b80`.
The earlier120-day host fixture lacks a sourced operating calendar and sufficient
native split evidence; the E2 tiny artifact proves inference correctness only.
The six external demo workbooks remain metadata-only inventory with unverified
scope/schema/units/vintages/use rights; the old research holdout is exposed. Neither
operational shelfcash_local nor customer/demo rows were queried/copied for E3.

REAL_BENCHMARK_BLOCKED: no authorized real unseen dataset with stable Store/Product
scope/units, tri-state stockout, complete sourced known-at daily calendar and adequate
prefix/point/CQR/validation/holdout coverage is established. Real inputs must include
source revisions and historical availability evidence; retrospective current revisions
must disclose their limitation. Missing labels stay missing and only already available
actuals are scored. Unknown/censored strata remain separate from primary known-false.
Synthetic scores cannot establish real accuracy, calibration quality or savings.
Promotion remains INSUFFICIENT_EVIDENCE, irrespective of synthetic ranking.

Reproduce in the isolated E2 venv after installing its pinned wheel/dependencies:

```powershell
.venv/Scripts/python.exe -m scripts.forecast_benchmark --enable synthetic-inputs
$benchmarkInputs = 'runtime/challenger/benchmarks/inputs/3178e138eff2be24654400e07a03033a3df29b89e4cca3f6ce658d8ad6451b80'
.venv/Scripts/python.exe -m scripts.forecast_benchmark --enable freeze --dataset "$benchmarkInputs/dataset.json" --plan "$benchmarkInputs/plan.json"
.venv/Scripts/python.exe -m scripts.forecast_benchmark --enable smoke --dataset "$benchmarkInputs/dataset.json" --plan "$benchmarkInputs/plan.json"
.venv/Scripts/python.exe -m scripts.forecast_benchmark --enable run --dataset "$benchmarkInputs/dataset.json" --plan "$benchmarkInputs/plan.json"
.venv/Scripts/python.exe -m scripts.forecast_benchmark --enable replay --experiment <printed-experiment-identity>
.venv/Scripts/python.exe -m scripts.forecast_benchmark --enable rescore --experiment <printed-experiment-identity>
.venv/Scripts/python.exe -m pytest tests/unit/test_forecast_benchmark.py tests/unit/test_forecast_challenger.py -q
```

The initial smoke's completed checkpoints are reused by the full run. Hash envelopes,
environment/source receipts, fit tables, artifact identities, raw predictions/targets/
masks, per-product/horizon/partition/stockout metrics and resource receipts stay in
owned ignored `runtime/challenger/benchmarks`; native artifacts/evidence remain in
E2 private storage. CLI stdout is aggregate only. `replay` recomputes all completed
A/B/C forecasts without fitting and audits train/point/CQR target dates/availability
and holdout quarantine; native C also compares E2 exact stage evidence in a fresh
process. Source/hash mismatch or missing bytes fails closed, with no family fallback.

PROPOSAL / E4 inputs already available: explicitly pinned per-origin C artifacts and
E2 captured inputs/forecast/quantile/CQR/diagnostic evidence, matching retained A/B
forecasts, the dataset/plan/environment/source digests and target masks. These can
support a separately authorized synthetic counterfactual comparison. They contain
no operational recipe/BOM/loss, inventory/lot/expiry/receipts, supplier/pack/price/fee,
budget/constraint/policy or search-resource capture. E4 must separately freeze the
same host operational context for all arms; no historical impact/savings evidence
exists from E3. E4/E5 are not executed here.

## Offline verification and lifecycle

CURRENT FACT tooling: `scripts/forecast_benchmark_protocol.py` validates frozen
manifest policy/config digests and synthetic detached admission/output examples.
`scripts/verify_forecast_engine_protocol.py` exercises named fixtures and prints
protocol digest. `tests/unit/test_forecast_engine_protocol.py` additionally checks
temporal partitions/masks/config drift and calls the **existing pure host** stockout
projection on supported/unsupported/unknown/future-support fixtures. This is not an
adapter, native booster parser, benchmark runner or production registry validator.
Synthetic artifact strings deliberately cannot load as models.

E1 checks run from the isolated worktree (Python3.11.9, private venv; Windows needs tzdata):

```powershell
.venv/Scripts/python.exe -m unittest tests.unit.test_forecast_engine_protocol -v
.venv/Scripts/python.exe -m scripts.verify_forecast_engine_protocol
git diff --check
```

These E1 checks do not start the application, DB, providers/workers, training,
native inference or benchmarks. E2 native correctness checks are separate below. Fresh-session assertions are required when E2/E5
actually changes persistence; no such persistence claim exists in E1. Each failure
fixture is inspectable JSON with explicit path replacements, expected typed outcome
and code; base input remains immutable. Detailed commands/results belong to the
conversation, not an accumulating report in this document.

| Slice | Status/scope and acceptance |
| --- | --- |
| E1 | COMPLETE compatibility/protocol scope: canonical specification + frozen synthetic config/fixtures/offline checks. Real-data/runtime integration remains unverified. |
| E2 | COMPLETE internal opt-in adapter: strict typed capture/artifact admission, pinned installed native stages, separate quantile/CQR/provenance, private immutable evidence/cache and exact fresh-process replay. Local checkpoint b92d2c43cbf82e8308043f60630c9f83f65abefb; production wiring/activation disabled. |
| E3 | PARTIAL: causal per-origin A/B/C training/point/CQR harness, paired metrics and fresh-process replay VERIFIED on synthetic correctness corpus. REAL_BENCHMARK_BLOCKED / INSUFFICIENT_EVIDENCE; real accuracy not verified. |
| E4 | NOT_STARTED: common captured host operational context→forecast-only swap→Planning impact and search evidence, with historical vs counterfactual meaning explicit. |
| E5 | NOT_STARTED: integration acceptance/current authorization and fresh-session persistence/restart/replay→review evidence→explicit user promotion/config selection and rollback; no automatic promotion. |

Stop after E3; E1/E2 committed locally, E3 remains uncommitted WIP.
Rollback E3 consists of its detached benchmark contracts/harness/tooling/fixtures and
current documentation changes; retain private artifacts/evidence and operational data.
Later runtime rollback must select a retained compatible host serving identity,
keep challenger captures/artifacts/audit and never rewrite completed Planning.

TECHNICAL DEBT / observed drift: historical ADR implementation-status paragraphs
and fixtures README still mention earlier unimplemented paths/head0017, while current
wired source/head0027 has evolved. The authority intent remains unchanged; these
historical statements are not current runtime evidence. This slice reports the drift
without editing accepted ADRs or unrelated documentation to hide it.
