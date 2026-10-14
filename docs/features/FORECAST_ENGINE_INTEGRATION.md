# Forecast engine integration — E1 compatibility and benchmark protocol

## Authority and status

ACCEPTED DECISION (explicit E1 request, 2026-10-14): current Competition BE remains
host; a separate forecast adapter admits the new engine as a challenger. Preserve
host BOM, reciprocal loss, Product serving/FEFO, procurement/2, requirements,
winner and retained Planning. E1–E5 make no LLM/OpenRouter calls. Stochastic
scenarios, new procurement, explanation/chatbot and what-if are outside this work.

CURRENT FACT: E1 supplies static boundary traces, a frozen synthetic protocol,
portable admission fixtures and small offline validators. Challenger serving,
training, accuracy, persistence and promotion have **not** run. E2 implementation
below is PROPOSAL within the approved direction, not current runtime. No public
API, schema, permission, accepted ADR or production configuration changes in E1.

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

PROPOSAL — detached input: host-owned validated prepared observations plus a new
explicit supplemental capture containing scoped calendar/closure, optional forecast
weather vintage, real inference availability instant, pinned challenger artifact
and versioned adapter configuration. The current PreparedForecastInput contains
host-derived demand_records; pass **only observations** to challenger sales_history.
Keep original host capture/digest intact and give challenger projection its own
policy identity/digest. Never relabel host demand_records as challenger estimates.

| Topic | Frozen compatibility requirement | Support/gap |
| --- | --- | --- |
| Identity/scope | One captured Store, explicit sorted UUID Products, exact selling units; per-row Store/Product checks before engine coercion. Product_name may be opaque UUID display text; names never keys. Preserve all requested Products. | Host supports; engine adapter needs strict preflight and mapping. |
| Time | Store-local DATE D inclusive; history_start…D; D+1…D+7. Known-at uses aware actual execution instant after EOD D, separately retained; no fabricated23:59:59 cutoff. At backtests state explicit next-run availability assumption. | Host dates supported; engine timestamp normalization and availability need guard. |
| Sparse/zero | Absence is missing; explicit Decimal0 remains observed. Dense model panels never write canonical rows. No fill of canonical quantities or missing forecast outputs. Native last_observed_demand uses forward fill as a separate feature; never treat it as an observation. | Supported observations; host/engine different derived panels preserved by policy. |
| Units | Output quantity is Product selling_unit, no integer rounding/unit conversion/Ingredient inference. Reject absent/wrong unit, overflow or float conversion failure. | Engine unit nullable; adapter must tighten. |
| Coverage | Exact Product×7 dates, no duplicates/unexpected keys; target horizon consistent. All requested Product readiness before execution; no partial success. | Existing host validator reusable for final result. |
| Stockout | true/false/null preserved; sales≠estimated demand. C arm reconstructs original observations exactly once using native policy. Never pass usable_histories or host demand_quantity as quantity_sold. | E2 uses native boundary; model+estimator changes expressly declared. |
| Quantiles | P25/P50/P75 are demand quantiles mapped directly to host LOW/BASE/HIGH. Preserve engine raw crossings/clipping diagnostics and frozen postprocess identity; reject final crossing/nonfinite/negative. Decimal(str(float)), no extra silent repair. | Supported after strict output validation; raw diagnostics need state capture. |
| CQR | Separate interval_lower/upper, coverage target, calibrator and point IDs/fit provenance. Never replace P25/P75; no joint path/probability guarantee. | Separate E2 diagnostic envelope required; existing host result/persistence has no CQR fields. |
| Closure | Zero only from same-Store, sourced, known-at closure facts covering dense historical panel and forecast dates. Known open/holiday false also need evidence; missing is data-blocked. Positive observed sales on declared closed date require resolution. | CalendarEvent history is not complete daily operating calendar. Host closure/weather capture currently absent. |
| Artifact | Explicit immutable content identity covering all3 boosters, config, features, category mappings, point, CQR, metadata and training manifest. Verify hashes/paths/versions/scope/units/timezone before native load. No optional checksums, schema2 implicit corrector, latest, download, train or promotion. | New pinned schema3 envelope required; native registry is weaker. |
| Temporal | Training, point-fit and calibration labels and their known-at boundaries must precede artifact fit; artifact publication/availability must precede inference; production additionally needs explicit promoted identity and production_available_at. Original exposed holdout remains inadmissible promotion evidence. | Native production gate is insufficient for these full checks. |
| Reuse/replay | Separate challenger model_type/version, host input digest, projection/policy/config/source/features/postprocess/dependency/artifact identities and supplemental capture digest. Stable ordering and canonical decimals. Cache only exact identity, partition by Store; replay exact captured input and bytes, no current lookup/retrain/fallback. | Existing serving contracts and artifact manifest use host-specific literals. Extend opt-in contracts later; cannot stuff CQR/provenance into metrics_json or reinterpret schema1. |
| Failure | UNSUPPORTED: incompatible schema/unit/scope/horizon/basis. DATA_BLOCKED: missing history/calendar, unsafe vintage/temporally ineligible/unpromoted artifact. TECHNICAL_ERROR: absent/corrupt pinned bytes, invalid native output, dependency/load/inference error. Sanitized code/detail, never broad success fallback. | E1 tooling enum illustrates outcomes; E2 needs real typed adapter errors, not string matching. |

ACCEPTED DECISION: adapter cannot query/write operational DB or authorize users.
Host owns permission checks, capture, persistence and transactions. No BOM calls,
new multiplicative loss, Ingredient service, BALANCED-first winner, scenario weights,
overrides or scenario probability. Explicit host fallback policy remains historical;
benchmark arms disable fallback so failures cannot masquerade as challenger scores.

Determinism means same captured input/config/versions/artifact produces the same
canonical predictions on the verified runtime. It does not promise bitwise
retraining across platforms. E2 must test repeated/fresh-process replay and document
any native numerical tolerance separately from exact retained byte/digest integrity.

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
| E2 | Resolvable isolated dependency pins, schema3 complete fixed artifact, scoped Products/units/timezone; closure/holiday coverage and known-at provenance; point/CQR fit binding and publication instants. | Engine assets present but research/temporal/dependency admissibility not established; host supplemental capture absent. |
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

## Offline verification and lifecycle

CURRENT FACT tooling: `scripts/forecast_benchmark_protocol.py` validates frozen
manifest policy/config digests and synthetic detached admission/output examples.
`scripts/verify_forecast_engine_protocol.py` exercises named fixtures and prints
protocol digest. `tests/unit/test_forecast_engine_protocol.py` additionally checks
temporal partitions/masks/config drift and calls the **existing pure host** stockout
projection on supported/unsupported/unknown/future-support fixtures. This is not an
adapter, native booster parser, benchmark runner or production registry validator.
Synthetic artifact strings deliberately cannot load as models.

Run from the E1 worktree (Python3.11.9, private venv; Windows needs tzdata):

```powershell
.venv/Scripts/python.exe -m unittest tests.unit.test_forecast_engine_protocol -v
.venv/Scripts/python.exe -m scripts.verify_forecast_engine_protocol
git diff --check
```

No application startup/import, DB URL, migrations/reset/seed, SMTP/OpenRouter,
workers, training, full pipeline/business suite, native inference, accuracy/impact
execution or OpenAPI changes. Fresh-session assertions are required when E2/E5
actually changes persistence; no such persistence claim exists in E1. Each failure
fixture is inspectable JSON with explicit path replacements, expected typed outcome
and code; base input remains immutable. Detailed commands/results belong to the
conversation, not an accumulating report in this document.

| Slice | Status/scope and acceptance |
| --- | --- |
| E1 | COMPLETE compatibility/protocol scope: canonical specification + frozen synthetic config/fixtures/offline checks. Real-data/runtime integration remains unverified. |
| E2 | NOT_STARTED: separate opt-in detached forecast adapter, strict captured scope/calendar/vintage/bytes admission, native fixed inference, truthful quantile/CQR/provenance envelope, replay/failure tests. Resolve compatible dependency pins locally. Preserve external source and existing serving; no automatic production activation. If durable serving contracts need extension, explicitly version/pin separate challenger metadata instead of fitting host-only artifact literals. |
| E3 | NOT_STARTED: authorized data inventory→freeze real execution manifest→causal per-origin training/point/CQR harness→paired accuracy/replay/coverage; report insufficient evidence honestly. |
| E4 | NOT_STARTED: common captured host operational context→forecast-only swap→Planning impact and search evidence, with historical vs counterfactual meaning explicit. |
| E5 | NOT_STARTED: integration acceptance/current authorization and fresh-session persistence/restart/replay→review evidence→explicit user promotion/config selection and rollback; no automatic promotion. |

Stop after E1. Rollback E1 consists only of its docs/tooling/fixtures in the isolated
worktree; preserve ignored private environment and all unrelated operational data.
Later runtime rollback must select a retained compatible host serving identity,
keep challenger captures/artifacts/audit and never rewrite completed Planning.

TECHNICAL DEBT / observed drift: historical ADR implementation-status paragraphs
and fixtures README still mention earlier unimplemented paths/head0017, while current
wired source/head0027 has evolved. The authority intent remains unchanged; these
historical statements are not current runtime evidence. This slice reports the drift
without editing accepted ADRs or unrelated documentation to hide it.
