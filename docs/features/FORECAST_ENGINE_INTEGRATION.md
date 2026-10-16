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
accuracy VERIFIED. F4 adds only the isolated test opt-in Planning integration below;
production serving and promotion remain locked. Public DTOs/routes/permissions and
accepted ADR intent are unchanged; private versioned captures/metadata have evolved.
E4 adds an offline counterfactual host Planning benchmark; E5 remains NOT_STARTED.

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

<a id="forecast-f4"></a>
## CURRENT FACT — C0 test-only Planning integration

F3 is checkpointed at `5a8e0a853519004237d4e0900a1266d0a69caac1`:
implementation/retained semantic replay verified, benchmark PARTIAL19/24, synthetic
operations only. Its consumed batch and five missing cases are not resumed. F4 is
checkpointed locally at `8f4d90838cfe7898cf3fbbe0e0784ca136dad8cf`; technical
test-only acceptance VERIFIED, product activation NOT IMPLEMENTED, production
promotion LOCKED. F4.1 is checkpointed at `b9ec9782a398722ef1705edbd51f70d1d7c35358`;
F4.2 is checkpointed at `8537e122f28ded9b48bdc14d651cf7ecee38d1a2`.
CURRENT FACT: challenger source and shared host adapter reuse are integrated into
main local through a separate integration worktree, based on main
`b0db90cedd3962d8cb2e3f2dfe4696ec83b4e52a`. Main dev-account/shutdown docs/code
are retained; Assistant/import WIP is not merged. Only CURRENT_STATE/ROADMAP
conflicted; both accounts were reconciled. No fetch/push/deploy/demo restart or
activation occurred. Source integration does not change runtime model eligibility.

`ChallengerPlanningServing` is an explicit internal test composition; application
startup still installs host `ForecastServing`. There is no new model action, FE
choice, setting that activates production, route, permission or automatic winner.
Construction requires enabled=True, ENVIRONMENT=test, exact dedicated DB/limited
role on loopback5438 and a matching Engine; connected identity/role flags are checked.
Host BASELINE/TRAINED operator configuration remains unchanged. C1 is exploratory
endpoint sensitivity only and cannot enter this path.

C02 retains `planning_public_acceptance/2` with `ChallengerTestPin`: complete raw
canonical input, explicit observation availability and dense calendar declarations,
artifact manifest/hash, native package/source/runtime and F4 integration-code digest,
scope/units/configuration and `native_explicit_calendar_once/1`. Only existing
unpromoted `synthetic_correctness`/SYNTHETIC_ONLY artifacts are eligible here.
Research/benchmark artifacts do not acquire production eligibility. These explicit
synthetic declarations are not historical vintages or unseen-data evidence.

The worker uses the accepted pin, never the current declaration/registry/latest.
It verifies current canonical observations against it; missing/changed/foreign facts
fail closed. `PreparedForecastInput` schema3 retains raw observations with
`engine_native_reconstruction_v1` and no host demand_records: native reconstruction,
point correction and factual closure execute once. P25/P50/P75 feed the unchanged
host BOM/procurement/serving/selector; CQR stays private, separate interval evidence.
Serialization1, schema1/schema2 and capture/1 historical bytes retain their rules.
Private `ExecutionDetails` schema2 retains actual native input/output/provenance in
the existing ForecastRun metadata table. Its legacy schema1 serializer omits new
fields. Migration `f4_20261016_metadata_v2`, parent0027, only widens the metadata
version check; no new table, backfill or changes to old rows. Downgrade refuses
retained metadata2. Assistant revisions on other branches are not merged or edited.

ForecastRun completion reuses owned transactions and uncertain-commit reconciliation;
Planning acceptance/claim/retain/finalize keeps existing authority, lost-ACK, process
incarnation, terminal and stale-writer fences. Retained native quantiles and raw input
are reconciled against the acceptance pin in the durable aggregate. Existing public
C03/C08 reads require current sensitive grants/Store membership and expose actual
model/version/artifact digest, not private declarations, paths or native metadata.
F4 forecast replay is a retained read with no artifact I/O, inference, training,
procurement or live operational capture. Old host computational replay entrypoints
keep their existing semantics; the offline E2/F3 semantic verifier is a different tool.

Failures retain explicit `CHALLENGER_ARTIFACT_MISSING` or sanitized categories `CHALLENGER_DATA_BLOCKED`,
`CHALLENGER_RUNTIME_UNAVAILABLE`, `CHALLENGER_ARTIFACT_CORRUPT` or
`CHALLENGER_TECHNICAL_FAILURE`; raw native exceptions remain chained internally.
No challenger failure falls back to B. Artifact mutation after acceptance rejects
execution; mutation after completion cannot change old retained reads.

The no-training fixture rebinds only the known E2 constant synthetic artifact
`0c3c2b7539c0050bdf52fbfffa56f6ddac03c68654b3462ad1d2f2626896d936`.
Booster bytes remain identical; declared test scope/runtime/publication produce a
new artifact identity with parent provenance. It is not a relabelled research model.
The original artifact and old experiments are never overwritten. The schema3 source
change alters native adapter runtime identity: historical E2/F2/F3 source/runtime
replay must use its original committed source/environment and retained receipts,
not rewritten manifests or silent compatibility under F4 source.

Profiling is **COMPLETE for the frozen F4.1 offline subset**, with the limitations
below; end-to-end/representative performance and general F3 timeout attribution
remain unverified. HISTORICAL INFORMATION: F4's consumed batch
stopped at2.6144s with ARTIFACT_RUNTIME_MISMATCH, zero Planning/inference/fits.
The old script selected `sorted(runs/*/evidence.json)[0]`: lexical cache identity
was mistaken for runtime/purpose eligibility. Its older synthetic artifact
`d265dd9462a89495c1ca082ea1e22fcadbbdd5882d4833459aa43134c0c46416`
has adapter digest `b42639dbc702211001c77c07bcf45a4df52b14e9c95be3d24488c6c3399dd323`;
current adapter is `b7cc1b2c62bd63562dd1fdec88941a0542f93a17fc8150d2a460d0513a57a0e9`.
Original artifacts, source pins and receipt are preserved; mismatch still fails closed.

HISTORICAL INFORMATION — first F4.1 experiment: preflight used the verified no-training F4 fixture, preserving
parent `0c3c2b75...936` and all three booster byte hashes. New synthetic artifact
`4797048535f97542afa6ecc0f4881f42218ca2e92b2fc997cc5e0dffe2fb13c4`
passed typed input/scope/unit/calendar, payload, native package/source/dependency
and runtime admission before compute claim. Runtime is Python3.11.9 Windows AMD64,
non-editable snapshot0.1.0+62b94fa.e2, engine commit62b94fa4d67cb04141d32be4e57d6f9740c2a8fc;
full runtime/source/artifact identities are retained in frozen setup/preflight.
No research relabelling, training, calibration or promotion occurred.

The first F4.1 experiment is
`b6ab729e05bc00c5d960ab1adcb4c91725fc3b31c01e9db226fb367a99230cd1`.
It froze A=completed F3 June24 B_COMMON scarce_purchase (unchanged input, objective,
4s solver policy, two solves/strategy, exact certification/domain); B=first synthetic
native execution; C=identical retained cache read. Offline A and single-Product
constant B/C are different workloads. DB capture/finalize/persistence/fresh Session
were excluded in advance. No actual labels entered Planning input.

| Observed stage | Elapsed seconds | Calls / result |
| --- | ---: | --- |
| Preflight, separate from compute | 2.0398202 | 1 successful preflight; zero Planning/inference |
| Admission/artifact verification immediately before claim | 0.7703720 | 1 successful verification; zero Planning/inference |
| Claimed compute, including failed child startup | 0.1060025 | 1 batch; PARTIAL_ERROR, exit1 |
| Planning / native inference / native solves | Unmeasured | 0 / 0 / 0 reached |
| Import split, prep/admission inside child, artifact load, validation/serialization, BOM, procurement, serving/FEFO, selector, filesystem retain/read | Unmeasured | No stage instrumentation installed |
| Cold/warm cache hits/misses and repeated reconstruction/validation | Unmeasured | No observations; unavailable counts are not measured zero |
| DB persistence, capture/finalize, retained DB fresh read | N/A | Not part of frozen offline workload |

The child asserted immediate parent PID equals controller PID before its child
claim or business imports. It failed there; no child-claim/progress/timings exists.
A later **noncompute** subprocess probe reproduced different owner/immediate-parent
PIDs through the Windows venv launcher. Tooling now verifies the existing OS process
incarnation/liveness contract (host/PID/birth), rejecting missing, reused, foreign or
unverifiable owners, instead of assuming direct parenthood. The executed tooling
bytes are retained separately from this fixed WIP; frozen setup is not rewritten.
The fix passed isolated subprocess tests; the separately authorized completion
experiment below then exercised it in compute.

### CURRENT FACT — F4.1 completion profiling

The new explicit authorization has a separate group under
`runtime/challenger/f4_1/completion`; neither earlier claim was reset. Experiment
`540bb41e97f5d95092362e17fb7e91d3162c0894d2a4791a9c0010b4e12d6850`
freezes the fixed controller/process-tree helper, original instrumentation/workload,
the exact same compatible artifact/input and hashes/provenance to the failed experiment.
It ran **one attempt**, no retry, in21.5297089s of the shared120s budget: **one host
Planning execution, one native forecast inference, zero native MILP solves**. No training,
calibration, network/provider or DB business write occurred. B/C are native execution/
retained cache paths, not additional full Planning runs. Main/FE/default B remain unchanged.

The launcher is created suspended, assigned to a Windows Job Object with
KILL_ON_JOB_CLOSE before resume; timeout terminates the owned job, not only its
launcher. A noncompute probe through the same interpreter/module/owner guard
terminated four processes (launcher, child and descendant launch chain), verified
both actual Python process incarnations DEAD and job active count0. Compute also
ended with active count0. Exclusive group claim and prepared identity reject repeat
execution. The controller conservatively implements no automatic retry; the user
allowed at most one startup-only retry with shared accounting, but none was used.

| Measurement | Calls | Inclusive seconds | Exclusive observed seconds |
| --- | ---: | ---: | ---: |
| Preflight, outside compute | 1 | 0.7570131 | N/A |
| Noncompute tree probe, outside compute | 1 | 1.3728544 | N/A |
| Full setup including freeze/probe, outside compute | 1 | 2.1780951 | N/A |
| Preclaim verification, outside compute | 1 | 0.7076208 | N/A |
| Claimed compute wall | 1 | 21.5297089 | N/A |
| Launch to child entry / entry to imports complete | 1 / 1 | 0.4001412 / 1.4477047 | N/A |
| A input preparation | 1 | 0.0156134 | 0.0156134 |
| A host Planning | 1 | 16.0695954 | 0.0011004 |
| A BOM | 8 | 0.3984304 | 0.3984304 |
| A procurement orchestration | 1 | 7.2031168 | 4.8049704 |
| A exact serving application | 7 | 6.8848416 | 5.9484231 |
| A serving/FEFO domain | 7 | 0.2936612 | 0.2936612 |
| A semantic procurement revalidation | 6 | 7.8809078 | 1.2112622 |
| A semantic serving revalidation | 42 | 1.8682809 | 1.8682809 |
| A comparison / selector | 1 / 1 | 4.2733332 / 4.5396861 | 0.8985504 / 0.8002860 |
| A semantic comparison revalidation | 4 | 1.9727647 | 1.9727647 |
| A result serialization / filesystem write | 1 / 1 | 0.0081405 / 0.0008482 | same |
| A fresh filesystem read with semantic validation | 1 | 2.5727319 | 0.4445976 |
| B whole cold native execute | 1 | 0.6673141 | 0.0183139 |
| B admission (includes artifact loading) | 1 | 0.1021325 | 0.0947858 |
| B artifact load / three booster loads | 1 / 3 | 0.0073467 / 0.0242632 | same |
| B native inference | 1 | 0.4787913 | 0.4517846 |
| B forecast validation / serialization-storage | 1 / 1 | 0.0027435 / 0.0218469 | same |
| C whole warm retained-cache execute | 1 | 0.0919507 | 0.0036718 |
| C admission / artifact load | 1 / 1 | 0.0769225 / 0.0082664 | 0.0686561 / 0.0082664 |
| C retained lookup / output validation | 1 / 1 | 0.0098033 / 0.0015531 | same |
| Native solve | 0 | Not reached | N/A |
| DB persistence/capture/finalize/fresh Session | N/A | Excluded offline workload | N/A |

Full precision, preclaim elapsed, remaining stage rows and function call counts are
in `completion/summary.json` and the experiment's original `timings.json`. Inclusive
rows overlap: do not sum them. Exclusive spans subtract only observed child spans,
not all internal computation. A revalidation rows include the later retained JSON
read; they must not be treated as a partition of the16.07s Planning call.

**Confirmed cost in this instrumented workload:** `serving._quantity` is called8548
times (5.1415899s inclusive); its source constructs a new
`TypeAdapter(NonnegativeDecimal)` for each conversion. Across the profiled child,
TypeAdapter initialization is called8556 times (4.5152906s inclusive), schema generation
8594 times, Pydantic core validation26280 times (8218 primitive calls). Repeated
ProcurementResult/Comparison/WinnerSelection boundary validation also reruns exact
serving/evaluation: six procurement and42 serving checks, seven `_evaluate` calls.
Comparison and selector include those checks; their time is not solely ranking.
These are measured costs, not a decision to remove integrity checks or proof of
safe caching. No business optimization was performed.

NativeProductSearch construction ran three times (4.3375708s inclusive), including
three model builds (3.1986261s). The unchanged cooperative4s policy expires before
any native solve or finite enumeration vector; the retained procurement elapsed is
7.1986476s with3.1986476s overrun. The host pipeline also performs required checks
outside that search policy. A returns INCOMPLETE, all strategies UNPROVEN/
CERTIFICATION_DEADLINE, one unique exact basket evaluation and **no winner**. The
original retained F3 case was also INCOMPLETE but had a winner and three BALANCED
enumeration vectors. Therefore exact_winner_facts_match_original=false: this run
**does not establish output equivalence**. Observation overhead and scheduling can
change cooperative-deadline search coverage; isolated observer/cProfile overhead and
an uninstrumented counterfactual were not measured. The same source/input/policy
does not imply the same time-limited output.

Cold lookup missed once; its mandatory persisted-byte readback hit once; warm lookup
hit once. Thus low-level counters are one miss/two hits, not two warm requests.
Native demand reconstruction ran once, and warm execution loaded/verified the artifact
and checked retained output without inference. OS file cache is uncontrolled; preflight
already read payloads, and A ran before B in the same child. Constant synthetic timing
is not representative latency for trained C or DB-backed end-to-end Planning.

**Hypotheses / unverified:** repeated schema/DTO construction and semantic reconstruction
are candidates for a separately authorized optimization study. This one instrumented
fixture establishes their cost, not the cause of every F3 timeout. Native solve latency
is unmeasured because no solve was invoked. Historical F3 remains PARTIAL19/24, with
no replay/rerun/resume or new missing cases. Product activation NOT IMPLEMENTED,
production promotion LOCKED; representative performance, real quality/operational
inputs and browser/recovery gates remain before any demo activation decision.

Current commands, verification scope and limitations:
[F4 runbook](../runbooks/FULL_TEST_FLOW.md#forecast-f4). Production promotion remains
LOCKED; no accuracy/real savings claim, browser E2E or production runtime acceptance.
Rollback removes test composition and F4 caller wiring while preserving every
ForecastRun/PlanningRun, artifact and receipt. Never downgrade away retained metadata2.

<a id="forecast-f4-2"></a>
## CURRENT FACT - F4.2 static quantity validator reuse

F4.1 checkpoint is `b9ec9782a398722ef1705edbd51f70d1d7c35358`: its profiling is
complete only for its frozen offline subset, whose Planning was INCOMPLETE/null
winner. Historical timings/receipts/claims/source snapshots stay unchanged. F4.2
changes only `serving._quantity`: a module-level TypeAdapter(NonnegativeDecimal)
is reused for identical `validate_python(view)` calls. No quantity-result cache,
Store/Run state, semantic-check removal or solver/objective/policy/proof change.

The static type has only exact_decimal (rejects float/bool) and finite/nonnegative
Decimal checks; it has no context/config/Store/thread-dependent validator. Adapter
construction does not capture Decimal arithmetic context. Fraction checks and display
use existing explicit local Decimal context, Quantity construction and ValidationError/
ServingNumericError mapping stay unchanged. Differential corpus checks valid/invalid/
extreme/zero/null/NaN/infinity/negative values and error classes/codes; four-thread
mixed-precision calls match legacy outputs, with per-call TypeAdapter construction
forbidden. Serving/FEFO, dated recipes/loss, arrivals/expiry, zero-purchase, tamper,
procurement/comparison/serialization regressions pass. No bypass via model_construct.

Experiment `fe46a91810c1c8c64b902196a1228d8dc0f82cd42fb33d27c648d83c760d483c`
uses separate baseline/candidate source snapshots under ignored runtime. Baseline
comes from Git archive of the F4.1 commit; candidate copies that snapshot and changes
only serving.py to the working implementation. Child verifies every source hash and
actual serving import path before business computation. Same interpreter/dependencies,
retained forecast arrays/scarce_purchase domain5, requirements/objective/certification,
solver4s/max2solves per strategy and finite proof policy. No cProfile/observer wraps.
Every task starts a fresh process; imports/startup are excluded from the timed full
Planning call, but included in the total hard-wall resource receipt. OS cache is
uncontrolled, not an inference cold/warm experiment. No model payload is needed.

One shared180s claim completed in **109.0109421s**, six full Planning executions
(three per arm), zero native forecast inference/training/calibration/provider/network/
DB business writes and zero retries. Preflight6.1590110s is separate. Fixed-basket
business computations and all subprocess startup are included in109.01s. Owned Windows
jobs contain launcher/descendants and end with active count0. The group is consumed;
no resume/reset/extra repetition is permitted. Fixed results were compared before
full Planning; any mismatch would stop the batch.

| Pair / frozen order | Baseline full Planning seconds | Candidate full Planning seconds | Baseline / candidate vectors | Whole result |
| --- | ---: | ---: | --- | --- |
| 1, baseline then candidate | 18.8043399 | 10.6876613 | 12 / 15 | INCOMPLETE / FINISHED |
| 2, candidate then baseline | 23.0927088 | 11.3115924 | 3 / 15 | INCOMPLETE / FINISHED |
| 3, baseline then candidate | 16.7615610 | 9.7113067 | 2 / 15 | INCOMPLETE / FINISHED |
| Median | 18.8043399 | 10.6876613 | N/A | 43.16% lower median candidate wall |
| Range | 16.7615610 to 23.0927088 | 9.7113067 to 11.3115924 | N/A | Three observations per arm |

All six runs called native procurement solve three times (forecast inference zero),
all selected the same option token `cmp1_d836a7ad...7451bb1`. Within each pair the
complete selected option JSON is equal, preserving basket/arrival/outlay, exact
Product/Ingredient/daily service facts, requirements-related issues and provenance.
Baseline overrun seconds were2.5021067/3.4862805/3.0283716; candidate0/0/0. Baseline
proof is mixed in pair1 (LEAN UNPROVEN, others finite-domain certified), all UNPROVEN
in pairs2/3. Candidate has COMPLETE_EXACT_ENUMERATION for all three strategies,
15 vectors (5 each), always limited to CAPTURED_FINITE_DOMAIN_ONLY. Selector still
reports BEST_EVALUATED_CANDIDATES_ONLY. More coverage within the unchanged deadline
is a search outcome, not a semantic-rule change or global optimization certificate.
Full result bytes are not claimed equal because timings/search/proof differ.

Two single fixed-basket measurements isolate exact computation without search:
zero packs0.3211523 to 0.1228501s, three packs0.3774243 to 0.1642788s. Both complete serialized
candidate outputs have identical SHA-256 between arms, including exact services,
costs and feasibility facts. These two timings are not whole Planning latency or
statistical evidence. Dedicated non-timed tests prove no per-call adapter construction;
F4.1's cProfile4.52s figure is not reused as uninstrumented construction latency.

**Limits:** three repetitions, one machine/fixture, no statistical significance or
production SLA. OpenAPI schema generation was run concurrently with the early
benchmark/first pair and may have caused CPU contention; all pairs are reported,
including the later reversed-order pair, with no rerun. At final inspection, Python workloads from import/Assistant worktrees were also
observed; their overlap with timed runs is unknown and they were not interrupted.
Background scheduling/OS cache remain uncontrolled. The intervention and fixed hashes support the narrow
adapter-reuse improvement; they do not attribute every F3 timeout, prove all historical
Planning outputs equal, or compare challenger forecast quality with B. Revalidation
refactoring and broader runtime optimization were not performed.

207 targeted regression checks plus3 tooling/retained-challenger checks passed;
no full suite, PostgreSQL or native forecast acceptance rerun. OpenAPI73 operations
and SHA-256 `7a6d13ca1e7bafdee247504e9a0fa131c28c9796a0436691dfa309a847fbd366`
are unchanged versus the isolated baseline. No migration/API delta. Current native
adapter/integration digests do not include serving.py and remain unchanged; whole
Planning source snapshots do change, so historical F3/F4.1 replay still requires
original pinned source, never rewritten manifests/artifacts. Product activation
NOT IMPLEMENTED, promotion LOCKED; representative quality/performance, operational
readiness, browser/recovery/rollback and explicit activation authorization remain.
F4.2 source/tests/tooling/docs are checkpointed and integrated into main local;
rollback of the optimization is the shared-host reuse change plus its tooling/docs,
preserving all historical data/evidence.

## CURRENT FACT - local source integration boundary

Combined-source verification exercises host startup with optional challenger import
and distribution metadata unavailable, retained host LightGBM without the challenger
package, native synthetic ForecastRun/Planning worker/public C03/C08, current rights,
lost ACK, actual owner-process recovery/stale fences and retained reads without
artifact I/O/inference/solver/live recapture. Native/host fault tests preserve explicit
failure rather than silent fallback. Existing host computational replay keeps its
historical semantics; it is distinct from retained Planning/native public reads.

There is one Alembic head `f4_20261016_metadata_v2`, parent0027. No main divergent
migration existed; no merge revision, reparent or renumber was needed. Dedicated new
integration Compose project/volume uses the existing strict test DB/limited-role
loopback5438 guard. Fresh migration, empty synthetic roundtrip and refusal to
downgrade retained metadata2 were verified without rewriting evidence. Other DBs
and runtime8103 were not migrated/reset/restarted. Optional `--project-name` in
setup tooling permits this isolated container/volume; default provisioning behavior
and DB allowlist/privileges are unchanged. No broker/new runtime infrastructure.

OpenAPI matches the main pre-merge snapshot exactly (73 operations/66 paths,
SHA-2567a6d13ca1e7bafdee247504e9a0fa131c28c9796a0436691dfa309a847fbd366),
so FE needs no change solely for this merge. pyproject base dependencies, Settings,
model registry/operator configuration and normal startup composition are unchanged.
The native vendor wheel and pandas-based research dependencies remain explicit
optional challenger setup; the host is not required to install the research stack.
No external engine repo edits, artifact promotion, provider/SMTP calls or training.

Native acceptance inputs are copied/hash-verified into the integration runtime,
never committed. Clone native tests require the pinned synthetic parent/host model
files described in the runbook; a source clone alone cannot run all historical
research benchmarks. Historical benchmark source/runtime/artifact pins and consumed
claims/receipts are not rewritten. Whole host source identity changes after merge
are not permission to silently replay old experiments under new code.

TECHNICAL DEBT / resolved test drift: main's health route inventory predated D01,
SU01, T03 and export discovery methods. The old assertion failed identically on the
pre-merge main; combined OpenAPI bytes already matched. Updating only the expected
existing routes/methods resolves that test drift, not an API expansion. Current
commands, coverage and remaining unverified gates are in the
[runbook](../runbooks/FULL_TEST_FLOW.md#forecast-f4). Browser E2E, representative
trained-C/DB performance and real unseen/vintage/operational quality remain
unverified. Product activation NOT IMPLEMENTED; production promotion LOCKED.

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

HISTORICAL INFORMATION — original E3/1 data inventory: only the portable synthetic
generator `tests/fixtures/forecast_engine/benchmark_setup.py` was admitted for that execution.
It declares fictional calendar independently before sales generation, with missing,
zero, known-false, censored and unknown observations; two synthetic Products use cup
and piece, daily history2025-11-01..2026-06-29, explicit calendar through2026-07-06,
generated next-run availability. Origins2026-06-01/08/15/22 follow the unchanged E1
two-validation/two-holdout/window policies. Dates in E1's template are illustrative;
the execution dates were frozen before training and before actual local artifact fits.
Dataset digest is `3178e138eff2be24654400e07a03033a3df29b89e4cca3f6ce658d8ad6451b80`.
The earlier120-day host fixture lacks a sourced operating calendar and sufficient
native split evidence; the E2 tiny artifact proves inference correctness only.
At that checkpoint, the six external demo workbooks were metadata-only inventory with unverified
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
F1 changes replay to require explicit verified historical source registration; the
command above alone cannot replay an unregistered older /1 or /2 experiment.
Only the registered /3 compatibility execution below has been verified with the
current dispatcher. Earlier /1 synthetic replay results remain historical evidence.

CURRENT FACT / inputs supplied to E4: explicitly pinned per-origin C artifacts and
E2 captured inputs/forecast/quantile/CQR/diagnostic evidence, matching retained A/B
forecasts, the dataset/plan/environment/source digests and target masks. These can
support the explicitly authorized synthetic counterfactual comparison. E3 contains
no operational recipe/BOM/loss, inventory/lot/expiry/receipts, supplier/pack/price/fee,
budget/constraint/policy or search-resource capture. E4 separately freezes the same
synthetic host operational context for all arms. No historical impact/savings evidence
exists from E3 or the E4 counterfactual fixtures. E5 is not executed here.

<a id="demo-abc-v3"></a>
## CURRENT FACT — exposed-demo A/B/C protocol /3

ACCEPTED DECISION (explicit continuation request,15/10/2026): use the same six
hash-verified workbooks and original five-Product/unit/timezone/POS declarations;
allow a separate demo-only calendar assumption and justified window/origin changes
without lowering model support. A/B/admission was reviewed/tested and checkpointed
at `c4ff88a` before these changes. No main/worktree merge, raw edits, E4, DB/provider,
SMTP, tuning/repeats, deployment or promotion is part of /3.

Typed `DemoCalendarAssumption` binds raw-bundle revision
`f79b217d99a47db6133591c6d3e01cd73820ab80849447147043a2ada152b592`, calendar file
`042e97456d2293b4b37e0fad967f516da3416d215eb8d455dcea1ce497d71bb0`, normalized
row digest, Store, exact Product scope and timezone. Only valid sourced `closed`
and `holiday` rows are assumed planned/known before all feature origins. No missing
date/field is filled, and duplicate/unknown/formula/positive-sales-on-closure conflicts
reject. Weather and promotion outcomes are excluded. This is explicitly
DEMO_RETROSPECTIVE_ASSUMPTION, not historical vintage proof. Raw calendar availability
stays null; synthetic availability exists only in the detached benchmark projection
with `benchmark_assumed_calendar:<declaration digest>` provenance. Both the projection
and production-mode challenger input reject benchmark-only use. Production remains locked.

Authority is the user's explicit conversation request; actual receipt time is
2026-10-15T10:59:04.177294Z. Actor kind is USER_IN_CONVERSATION; an authenticated
actor identifier/source issuer time is unknown and stays null. These are not fabricated
historical timestamps. Input/declaration/source envelopes live in ignored
`runtime/challenger/demo-abc/inputs/57249b1b53513eb9d5ea34304d4e3197271d08ccfa77341634e01efcba0b8f3a`.

### Frozen design and native support before fits

Moving four weekly origins later under original windows cannot retain a complete
7-day observed horizon by08/07: the first origin must be≤10/06. Exact native code
gives only76 eligible dates for the least-supported Product there (77 was the old
optimistic upper bound). By17/06 the minimum is83, still below84. This rules out
the original four-origin design without inventing later POS.

Protocol /3 retains origins10/06,17/06 validation and24/06,01/07 exposed-demo holdout;
train ends O−48, point targets O−47..O−28 (20 days), calibration O−27..O (28 days).
Train/point/calibration do not overlap. Every point task originates after train fit
availability; every CQR task after point fit availability, with the original purge.
All14 holdout target dates remain quarantined from fitting in every arm, including
later origins. No rolling-origin relaxation was needed. Mature prior observations
may be inference features under the existing policy. Hyperparameters, reconstruction,
1500 native rounds,84 training dates,28 usable-history warm-up, point30 tasks/7 dates
and CQR20 samples remain unchanged. /3 additionally checks84 dates per Product.
No C metrics were available when this design was selected.

Support inspection uses the same `build_native_training_table`, raw-prefix native
adaptation/features/reconstruction and postprocess task availability/masks as fitting;
training calls are forbidden during inspection. Warm-up begins with native usable
observations; earliest eligible feature cutoffs are28/01 or29/01 by Product.

| Origin / partition | Available POS rows | Min train dates/Product old→new | Train end | Point window | CQR window | Min point tasks/dates per horizon | Min CQR tasks/dates per horizon |
| --- | ---: | ---: | --- | --- | --- | ---: | ---: |
| 10/06 validation | 805 | 76→84 | 23/04 | 24/04–13/05 | 14/05–10/06 | 68/14 | 108/22 |
| 17/06 validation | 840 | 83→91 | 30/04 | 01/05–20/05 | 21/05–17/06 | 68/14 | 109/22 |
| 24/06 holdout | 875 | 90→98 | 07/05 | 08/05–27/05 | 28/05–24/06 | 68/14 | 109/22 |
| 01/07 holdout | 910 | 97→105 | 14/05 | 15/05–03/06 | 04/06–01/07 | 68/14 | 74/15 |

Point/CQR groups pool Products by horizon as the native methods specify; these
sample counts do not establish per-Product calibration. Full support envelopes keep
per-Product eligible train dates/tasks and Product×horizon point/CQR populations,
stockout/missing exclusions,105 purged tasks per window and245 holdout-quarantined
CQR tasks at the last origin. Calendar covers every required date at every prefix;
its historical availability is assumed, not observed. All A/B/C pass this demo-only
design's admission. No operational workbook is required by the forecast consumer.

The separately frozen [manifest](../../tests/fixtures/forecast_engine/benchmark_manifest_demo_v3.json)
has digest `6adf514b662b9c0169b00e1a12291285870f265b00d28b971fd488301b3d7259`;
model configurations must equal E1's original bytes. It is not /1 or /2 evidence.
Experiment `e8fd6eea4f2528bdd9d83a95b6ffcabc84017228c04f2e347ea5a80ce1524e54`
freezes the protocol, scope, assumptions, observations/stockout-derived masks,
source/runtime and budget before fits. Its dataset digest is
`31ff9987f2f8a41a572cf9248a57d11700a6fb73975c6787b734b7d63f9c4ecb`.
Inherited /2 staging text saying C remains blocked is retained verbatim as historical
limitation; the separate /3 assumption resolves only demo admission, not production
or historical-vintage proof. No old result or declaration is rewritten.

### Actual paired results and trade-offs

A/B/C were all fitted/executed anew on /3:140 outputs each,420 total,4 origins,
28 distinct target dates,140 distinct Product/day outcomes. The shared primary mask
has138 known-false outcomes (69 per partition);2 censored lower bounds are diagnostic
only,0 missing/unknown. Horizon5 has9 primary outcomes per partition, other horizons10.
No future POS09–15/07 was supplied. No reconstruction is applied twice: A/B use host
causal_stockout_v1; C starts from raw observations and uses native reconstruction.

| Arm | Partition | MAE ly | WAPE | Bias ly | Pinball P25/P50/P75 | Quantile coverage/width ly | CQR coverage/width ly |
| --- | --- | ---: | ---: | ---: | --- | --- | --- |
| A | validation | 7.2029 | 19.1007% | −5.1159 | 2.4130/3.6014/3.2382 | 65.2174%/10.5761 | unavailable |
| B | validation | 5.0141 | 13.2965% | −0.8818 | 2.1272/2.5071/1.8669 | 43.4783%/8.4501 | unavailable |
| C | validation | 4.5849 | 12.1584% | −0.2622 | 1.8758/2.2925/2.0021 | 26.0870%/3.3607 | 34.7826%/5.5367 |
| A | holdout | 8.2174 | 23.2282% | −2.4493 | 3.8406/4.1087/2.9348 | 53.6232%/10.6377 | unavailable |
| B | holdout | 6.0417 | 17.0781% | +0.9190 | 3.2157/3.0208/2.0553 | 46.3768%/8.4740 | unavailable |
| C | holdout | 4.2723 | 12.0766% | +1.0246 | 2.0251/2.1362/1.7200 | 26.0870%/3.5796 | 55.0725%/6.4328 |

WAPE is absolute P50 error divided by sum of eligible paired actuals, null at zero
denominator. Quantile intervals are P25–P75; CQR is separately nominal50% and is
not those quantiles. Raw crossings across all tasks A0/B1/C24, final0. Primary C
crossings are11 validation/13 holdout. Validation-only aggregate mean pinball favours
C (2.0568 vsB2.1670/A3.0842), but /3 explicitly reports trade-offs and selects no
automatic winner. No holdout tuning, savings, real-accuracy or promotion claim.

| Product / unit ly | Validation MAE B→C | Validation mean pinball B→C | Holdout MAE A/B/C | Holdout WAPE A/B/C |
| --- | --- | --- | --- | --- |
| t1 Sinh tố chuối | 4.8981→4.2593 | 2.1233→1.9337 | 8.1429/4.6704/4.4627 | 24.0506/13.7943/13.1810% |
| t2 Trà sữa trân châu | 7.5205→6.1008 | 3.4487→2.8948 | 10.7143/8.1996/5.3815 | 22.8659/17.4992/11.4848% |
| t3 Cà phê sữa | 5.7795→5.5280 | 2.3366→2.4569 | 8.4286/7.6308/4.3185 | 20.4152/18.4828/10.4601% |
| t4 Nước cam | 4.0022→4.1547 | 1.6603→1.7560 | 7.7857/4.8644/3.1758 | 26.6504/16.6508/10.8705% |
| t5 Matcha latte | 2.7982→2.8512 | 1.2303→1.2211 | 5.8462/4.7511/4.0039 | 23.4568/19.0630/16.0649% |

C improves all five Product holdout MAEs on this sample, but validation regresses
on t4 MAE/pinball, t3 pinball and t5 MAE. Holdout horizon MAE B→C is
1:3.963→2.554;2:4.058→4.467;3:4.593→4.821;4:3.319→4.151;
5:5.066→5.084;6:17.843→4.843;7:3.352→4.067. Much of the aggregate gain is horizon6;
an aggregate ranking is insufficient. Narrow quantiles under-cover substantially,
and CQR validation coverage is also below nominal. The retained `summary.json`
contains full validation/holdout Product/unit/horizon/Product×horizon metrics,
all three pinballs, bias, widths/coverage and masks; no dimension is omitted there.

One hard-bounded≤300s subprocess batch consumed72.047s cooperative wall,24 boosters,
8 point/CQR fits and0 solves; no fallback, failure or partial case. Fixed one thread
and no repeats/search. A compute0.265s; B training6.812s/inference0.265s;
C training56.155s/inference6.892s (includes native preparation, not just booster fit).
These are one-run local diagnostics, not production SLA/cost. A per-process explicit
prefix cache reuses only exact observation/calendar/config prefixes; it is not a
cross-run cache or a substitute for support. Tests verify detached copies and future
label invariance. DB/provider imports, network and child launches are forbidden
after standard-library platform preflight; no forbidden attempt was recorded.

Fresh-process verification replayed all12 checkpoints/4 native artifacts with
`lightgbm.train` forbidden. Altering140 future labels left35 earlier C predictions,
captured input and fit identity identical.658 pre-task workbook/runtime files
retain their exact hashes. There is no new PostgreSQL persistence/browser/E4 claim.

CURRENT FACT — local checkpoint `a863fb5b1a85c1fba3455628853fb4f76eb0a467`
retains the executed /3 implementation as exploratory demo, not production acceptance.
F1 fixes the replay-only representation defect: typed `budget.wall_seconds` now
preserves JSON integer versus float, including non-default/fractional values. Full
schema validation and canonical-byte equality remain mandatory; the budget stays
in the identity. No other numeric field is normalized. This was a loader defect,
not an error in saved forecasts or metrics.

The generic `forecast_benchmark replay --compare-dedicated` uses an explicitly
registered historical source snapshot, verified against that Git checkpoint and
original raw source/environment hashes. Snapshot identity is
`8e999717cde0bfdac94e3348ef8cb015eae9ec685013a263101ec2695cd9dcad`.
An isolated worker executes historical inference/fit-availability validation with
the current typed plan loader; its receipt distinguishes historical execution
source from current loader/worker/dispatcher/validator hashes. It does not claim
that current source is the original source. Original plans, artifacts, receipts,
budget ledgers and manifests are read-only. New verification receipts live outside
the experiment under `runtime/challenger/f1/replays/`. Fresh-process generic replay
and the historical dedicated verifier agree on12 checkpoints/4 native artifacts;
the dedicated future-label probe still has35 identical outputs after140 changes.
Training is fail-fast forbidden, with0 fits/forbidden network attempts/original writes.
All809 files in the pre-F1 preservation inventory, including six raw workbooks,
retain exact SHA-256 bytes after verification. Focused56 tests pass; no full-suite,
PostgreSQL, API/browser or production acceptance claim is added by F1.
Absent or ambiguous historical registration rejects; no automatic source fallback.
Plan representation tests cover /1,/2,/3, but historical executable replay is verified
here only for this /3 experiment, not every older experiment/runtime. Direct current
`run_demo_abc replay`/`verify_demo_abc` are not the compatibility entrypoint.

### CURRENT FACT — independent retained-array diagnosis (F1)

Independent exact-rational arithmetic agrees with all1176 retained metric groups
(partition, arm, primary/censored masks, Product, horizon, Product×horizon and unit).
This includes MAE/WAPE/bias, three pinballs, inclusive P25–P75 coverage/width and
separate CQR coverage/width. Two censored outcomes remain excluded from primary
scoring; censored scores describe observed lower bounds, not latent demand truth.
Units are `ly`; target−origin=horizon and raw labels/masks agree. Historical replay
also verifies origin/artifact binding, source/runtime identity, causal fit availability
and strict holdout quarantine. No measurement/alignment/leakage defect was found
within these checks. This is not proof of historical source vintages.

Actual native order is residual+seasonal anchor → nonnegative quantity clip → sort
three quantities → common point offset on all three and nonnegative clip → separate
CQR interval → factual closure zeros. P50 is the middle sorted quantity plus that
offset, not necessarily the raw q50 booster output: sorting changes the median on24
of138 primary tasks. Quantity/point clips are0; point offsets preserve widths on
these arrays. Final0 crossings establish ordering only. CQR fits the corrected
P25/P75 interval using the retained per-horizon order statistic, then contains the
median; it does not overwrite quantiles. Saved inference arithmetic agrees within
1e−10; fit tables serialize10 decimal digits, so CQR parameter arithmetic is checked
within1e−8, not claimed bitwise re-fitting.

| C stage, holdout69 primary outcomes | P25–P75 coverage | Mean width ly | P50 MAE ly |
|---|---:|---:|---:|
| Raw reconstructed quantities | 17.3913% | 3.6590 | 6.6594 |
| Sorted before point correction | 17.3913% | 3.8143 | 6.6980 |
| Point corrected, before closure | 18.8406% | 3.8143 | 6.6931 |
| Official final including closure | 26.0870% | 3.5796 | 4.2723 |

Undercoverage already exists before sorting/point correction; the observed defect
is not clipping-induced width collapse. Its learning/calibration cause remains a
hypothesis requiring ablation. Validation raw/sorted coverage20.2899% becomes26.0870%
after point correction. Empirical tails use strict `y<P25`, inclusive `y≤P50`, strict
`y>P75`: validation26/69=37.6812%,33/69=47.8261%,25/69=36.2319%; holdout29/69=42.0290%,
42/69=60.8696%,22/69=31.8841%. Validation has0 endpoint/median ties; holdout has5 ties
at each quantile from closure zeros. Open-date holdout coverage is13/64=20.3125%.
These correlated tasks span only14 dates/two origins per partition; pooled-Product
point/CQR fits and CQR55.0725% do not establish quantile calibration or IID certainty.

Horizon6 targets are Tuesdays30/06 and07/07, with correct date/weekday alignment.
30/06 is explicitly closed, not a holiday; all five actuals are0. C's final closure
override zeroes five positive pre-closure forecasts; A/B have no such calendar rule.
The exact B−C absolute-error advantage totals122.0873 ly across69 holdout outcomes;
H6 contributes130.0034 ly, or106.4840% of that net advantage. Other horizons jointly
favor B by7.9161 ly. All five Products contribute to the closed-date effect.

| Saved-array sensitivity only | B MAE ly | C MAE ly |
|---|---:|---:|
| Official holdout | 6.0417 | 4.2723 |
| Omit H6 (59 outcomes) | 4.0415 | 4.1756 |
| Leave out30/06 (64 outcomes) | 4.0420 | 4.6061 |
| Leave out origin24/06 (34 outcomes) | 4.1593 | 4.5995 |
| Leave out origin01/07 (35 outcomes) | 7.8702 | 3.9545 |
| Apply the same sourced closure-zero rule to A/B | 3.7491 | 4.2723 |
| Remove only C closure override | 6.0417 | 6.6931 |

These diagnostics leave the official mask/comparators unchanged and create no trained
candidate. They prove the implemented closure override's arithmetic effect, not a
causal gain from residual learning. On open07/07 C's seasonal reference is closed30/06;
all five anchors take `FALLBACK_ROLLING_MEDIAN_7`, then positive residuals and the
shared+0.3455746641 point offset produce overprediction. B's retained H6 feature
reconstruction has no missing feature/date-shift finding. Whether a different anchor
policy improves forecasts is unproven. The official package comparison remains
reproducible, but cannot establish general C superiority or isolate learned-model gain.

Diagnostics are five hash-enveloped JSON files (`summary`, `metrics`, `stages`,
`horizon6`, `provenance`) at
`runtime/challenger/f1/diagnostics/00c733d0082cd2d4e03309627207d965a4d4fe202ebc471c93fa025746655a3a/`.
They use saved arrays/fit tables and pure feature reconstruction, with0 training or
new benchmark execution. Source/input hashes identify this diagnostic calculation.

### HISTORICAL INFORMATION — F1 bounded hypotheses

For any change informed by F1, /3 holdout is now exposed development evidence,
not an independent final holdout. These were the pre-F2 proposals; the separately
authorized F2 below executes only closure parity and one endpoint variant, without
anchor changes. No general improvement direction was proven by F1. Freeze
one hypothesis/configuration and fresh chronological validation/calibration/evaluation
scope before fitting; verify authorized POS/calendar availability and raw hashes first.
Do not silently source the following week or reopen the original batch budget.

| Hypothesis and changed component | Validation and guardrails | Compute estimate / fresh evaluation |
|---|---|---|
| Common known-at closure treatment may explain package differences: apply one explicit closure policy to all arms. | Paired MAE/WAPE/pinball plus open/closed-date and per-Product/horizon results; same masks and causal calendar availability for every arm. | First saved-array diagnostic0 fits,<5s; any new candidate evaluation needs a newly frozen budget and unseen periods containing open/closed days. |
| Interval calibration design may improve tails already poor before point correction: one predeclared endpoint recalibration variant on fixed boosters. | Three pinballs, both tails, inclusive coverage/width, median bias/MAE and Product/horizon regressions; separate CQR; no holdout-fit, width-only optimization or variant search. | Up to8 postprocess fits,0 booster fits, hard300s proposed; new disjoint point/calibration windows and unseen evaluation labels required. |
| Closed seasonal-reference fallback may contribute to07/07 overshoot: one explicit anchor/fallback variant. | Paired MAE/bias/pinball by open-after-closure vs ordinary dates; preserve84-date train minimum, holdout quarantine and all causal availability checks. | One configuration, at most24 boosters+8 postprocess fits, hard300s proposed; fresh origins with closed reference/open target, plus ordinary controls. |

Outputs remain under `runtime/challenger/benchmarks/experiments/<experiment above>`:
`demo-freeze.json`, plan/dataset/environment, resource ledgers, per-origin A/B/C
checkpoints, predictions, full summary, offline receipt and `verify-<digest>.json`.
Artifacts and fit/point/calibration tables retain separate content identities.
The scope is VERIFIED offline computation/replay, EXPLORATORY exposed demo evaluation.
Real source vintages/unseen independent demand, more origins/diverse operational
periods and later operational acceptance remain missing. Production/promotion LOCKED,
E5 NOT_STARTED; /3 checkpoint is `a863fb5`; F1 is checkpointed at
`6a50d815ba983f511a92388b2ade18d6fd6b4b93`. F2 checkpoint is
`fcb33abb9c2316d41d564d5653233f6dc4e80a5e`; F3 checkpoint is
`5a8e0a853519004237d4e0900a1266d0a69caac1`, retaining PARTIAL19/24 status.
Commands/recovery: [runbook](../runbooks/FULL_TEST_FLOW.md#challenger-demo-abc).

<a id="forecast-f2"></a>
## CURRENT FACT — F2 shared closure and one endpoint calibration variant

User-authorized offline `forecast_f2/1` is a new retained-array experiment, not a
rewrite of /3 or a production-policy change. Identity:
`ee4d7cb4de28dabb842c8900b4ebb3b9b32e8f423bd5f6611395f539323ecbc7`.
The F1 checkpoint above has exactly14 files, no runtime/workbooks/models/secrets.
F2 source/config and94 input-file hashes were frozen before fitting. Earlier
unexecuted admission drafts remain retained; only this identity consumed the one
global F2 batch marker. No source/config change or identity can reopen that budget.

### Admission, availability and retained controls

All six workbooks in runtime were read-only inventoried by sheet signature, exact
path/SHA-256 and physical headers; no suffix/mtime winner was selected. POS SHA
`23010aaa…d891dc` still covers01/01–08/07/2026; calendar SHA `042e9745…71bb0`
covers through15/07, with no POS09–15/07 or other new workbook in runtime. Existing
five-Product t1–t5 `ly` identities, Asia/Ho_Chi_Minh, source revision, scoped
retrospective POS/calendar declarations remain bound. No new known-at assumption
or unseen-label claim is introduced. The workbook inventory is retained under
`runtime/challenger/f2/preflight/workbook-inventory.json`.

Reuse is compatible at the exact four /3 origins10/06,17/06 validation and24/06,01/07
exposed evaluation, with unchanged train O−48, point O−47..O−28 and calibration
O−27..O windows. Retained C artifact/checkpoint/evidence identities and windows,
B model-file digest, raw workbook hashes and fit-table envelopes are checked.
Boosters, features, anchors, point correction, native minima and14-date holdout
quarantine are unchanged. No rebuild or native inference is needed. A/B/C package
outputs remain separate controls; raw pre-policy C is reconstructed from retained
sorted quantities+point offset, with exact open-date P50 verification. Inputs/artifacts
are read, never rewritten or published under a new historical identity.

### Frozen policies and validation-only rule

`shared_explicit_closure/1` uses the same Store/Product scope, unit, target date,
source declaration and origin cutoff for all arms. Only explicit closed facts with
source and `available_at≤next_run(origin)` zero quantiles and any existing interval.
Unknown/missing/late calendar does not become open/closed or block A/B; holidays do
not imply closure. Duplicate/conflicting calendar, wrong scope or positive sales
on a declared closure reject admission. Actual zero is never the override trigger.
C's native override is verified, then its pre-closure arrays feed the benchmark
policy once; it is not applied again to already-zeroed native values. Each variant
retains before/after arrays and policy counts. C0 is C under this common policy;
C1 uses one endpoint correction before the same policy. C0 matches C_native here.

One method only: `pooled_horizon_endpoint_residual_nearest_rank/1`. For each horizon,
pool the exact five Products in the same selling unit; require≥30 tasks,≥7 distinct
target dates and all Products represented. Compute lower correction as the empirical
.25 quantile of `(y−base_P25)`, upper correction as the empirical .75 quantile of
`(y−base_P75)`, using sorted residual rank `ceil(n*tau)`,1-indexed, no interpolation.
The objective is endpoint pinball, not maximizing coverage. No clipping cap, tuning,
variant search or CQR relabeling is used. Preserve median exactly; project lower to
`max(0,min(P50,raw_lower))` and upper to `max(P50,raw_upper)`. If any horizon lacks
support, the whole origin is NOT_FITTED and C1 equals C0; minima are not lowered.

Only retained, point-corrected calibration predictions on eligible OPEN/known-false
labels are used. Feature cutoff must follow point availability, precede target,
and match horizon; actual known-at must match the retained observation and precede
the origin forecast instant. Calibration labels are within O−27..O, outside global
holdout quarantine; evaluation starts O+1. This is disjoint from booster/point fit
windows and the same-origin scoring labels, but overlaps the parent's CQR fit labels.
Choosing this reuse preserves boosters/P50 without new inference or rebuilding CQR;
it does not provide an independent calibration split from CQR, exchangeability or
split-conformal guarantee. Predictions in saved fit tables have10-decimal precision.
Parameters, fit residual rows, support/ranks, windows and exact artifact/source bindings
are retained. All4 origins fitted,28 horizon statistics; per-group support74–138
tasks and15–28 dates, above the frozen minima.

CQR stays byte-equivalent to C0 and remains a separate interval. C1 does not inherit
a calibrated-quantile guarantee from it. Selection uses only validation OPEN primary
outcomes: strict improvement of mean endpoint pinball; each endpoint pinball and
total absolute tail deviation from .25 nonworse; no mean endpoint-pinball regression
in any Product, horizon or Product×horizon cell. Ties/failure retain C0. No ensemble,
Product switching, serving selection or exposed-evaluation optimization is allowed.

### Results and limits

All7 arrays (A/B/C native, A/B common, C0/C1) contain140 matching tasks each. Each
partition has69 primary outcomes,1 excluded censored lower-bound outcome,0 missing/
unknown,14 dates/two origins. Evaluation has64 OPEN outcomes on13 dates and5 CLOSED
outcomes on30/06; validation has69 OPEN and0 CLOSED. Censored metrics are diagnostic
observed lower bounds, not demand truth. Full1540 populated metric groups retain
partition/mask/cohort/Product/horizon/Product×horizon; absent cohorts remain absent.

| Package/policy | Validation MAE / WAPE | Exposed evaluation MAE / WAPE |
|---|---:|---:|
| A native | 7.2029 /19.1007% | 8.2174 /23.2282% |
| B native | 5.0141 /13.2965% | 6.0417 /17.0781% |
| C native | 4.5849 /12.1584% | 4.2723 /12.0766% |
| A common closure | 7.2029 /19.1007% | 5.8406 /16.5096% |
| B common closure | 5.0141 /13.2965% | 3.7491 /10.5976% |
| C0 / C1 common closure | 4.5849 /12.1584% | 4.2723 /12.0766% |

After fair closure treatment, B has better exposed point error than C0/C1; on
validation C0/C1 still have lower point error than B. C1's P50/MAE/WAPE/bias and
CQR are unchanged from C0. Their bias is−0.2622 ly validation,+1.0246 evaluation
(OPEN evaluation+1.1046); B common bias is−0.8818 and−1.3736 respectively.

| OPEN primary cohort | Pinball P25/P50/P75 | P25–P75 coverage / mean width ly | y<P25 / y≤P50 / y>P75 |
|---|---|---|---|
| B validation69 | 2.1272/2.5071/1.8669 | 43.4783% /8.4501 | 28.9855% /55.0725% /27.5362% |
| C0 validation69 | 1.8758/2.2925/2.0021 | 26.0870% /3.3607 | 37.6812% /47.8261% /36.2319% |
| C1 validation69 | 1.7537/2.2925/1.9622 | 36.2319% /5.6181 | 27.5362% /47.8261% /36.2319% |
| B evaluation64 | 1.8447/2.0210/1.5303 | 50.0000% /8.5569 | 15.6250% /42.1875% /34.3750% |
| C0 evaluation64 | 2.1833/2.3030/1.8544 | 20.3125% /3.8592 | 45.3125% /57.8125% /34.3750% |
| C1 evaluation64 | 1.9296/2.3030/1.7768 | 53.1250% /7.0407 | 28.1250% /57.8125% /18.7500% |

Coverage is inclusive; lower/upper tails are strict, median proportion inclusive.
OPEN B/C0/C1 have0 endpoint/median ties here. Five CLOSED evaluation tasks have
quantiles/CQR all0, inclusive coverage100%, width/error0 and5 ties at each quantile.
Do not count that as learned calibration. Across all69 evaluation outcomes C1
coverage56.5217%/width6.5305 versus C0 26.0870%/3.5796. C0/C1 CQR remains34.7826%/
5.5367 validation,55.0725%/6.4328 evaluation; OPEN evaluation51.5625%/6.9354.

Validation aggregate endpoint pinballs and total tail deviation improve, but the
frozen subgroup guard fails: H7 mean endpoint pinball1.1342→1.1544 and12 Product×horizon
cells regress. Full cell values are in summary/metrics. Therefore the frozen rule
retains **C0**, not C1. C1 is an exploratory aggregate improvement with unresolved
local regressions, not an accepted candidate. No additional trial followed. B's
exposed evaluation advantage does not authorize production selection either.

### Verification, resource receipts and next gate

One global consumed batch, hard300s subprocess deadline including startup/preflight;
actual parent3.844s, compute1.641s.0 booster fits,0 point/CQR fits,4 endpoint artifacts
(28 group statistics); parameters13,295 bytes, fit evidence694,010 bytes.17,038,149
bytes of existing model content were pinned/reused, no new model binaries.
Endpoint projection crossing/clamp counts0; final crossings0. Original raw crossings
A0/B1/C24 remain separately reported, not overwritten by endpoint statistics.
P50/CQR equality and full140-task paired masks are independently verified.

Fresh-process replay restores parameters and checks support/rank arithmetic and all
outputs, with booster and endpoint fitting entrypoints forbidden: F2_READONLY_REPLAY_VERIFIED,
4 origins,0 fits/forbidden IO/original writes. Original /3 generic historical replay
still matches its dedicated verifier12 checkpoints/4 artifacts and future-label probe.
An independent Decimal scorer agrees with all1540 metric groups within1e−25;
all1234 pre-F2 runtime/source-snapshot/workbook files retain SHA-256. Focused tests
cover unknown/holiday/conflict calendars, sparse/causal/quarantined fit samples,
future-label invariance, P50/unit/order, consumed batch, source/parameter/artifact/
dataset/version tamper and validation-only subgroup rejection. No API/schema/DB,
browser, full regression, impact or real unseen accuracy acceptance is claimed.

Outputs: `runtime/challenger/f2/experiments/<identity>/admission.json`,
`<origin>-parameters.json`, `<origin>-fit-evidence.json`, `predictions.json`,
`stages.json`, full `metrics.json`, `summary.json`, resource/execution/run/replay
and independent verification receipts. Source/config/input hashes bind this exact
execution; source drift rejects replay. A changed source cannot reopen the consumed
global marker. See [F2 commands](../runbooks/FULL_TEST_FLOW.md#forecast-f2).

The user subsequently authorized the separate [F3 counterfactual benchmark](#forecast-f3)
below. A real Planning impact claim still requires independently appropriate demand
and operational snapshots; the08/07 snapshot is not historical June stock. F2 stays
exploratory and cannot select C1 by later impact scores. Production/promotion LOCKED.

<a id="forecast-f3"></a>
## CURRENT FACT — F3 counterfactual host Planning impact

F2 was reviewed and locally committed as
`fcb33abb9c2316d41d564d5653233f6dc4e80a5e` (11 source/tests/docs files,16 focused
F2 tests passing). F3 is explicitly authorized offline computation only, no serving,
public API/persistence, main integration or F4 acceptance. ADR-019/020/021,
procurement/2 and existing exact BOM/serving/FEFO/comparison/selector remain authority.

Protocol `planning_f3/1`, identity
`e7aa4b531b6f7ed3fb355856fa5145bac0c7472d2df3da6bce7b7fa00afa9586`, pins the exact
F2 experiment, its implementation/input/artifact hashes and its retained B_common,
C0 and C1 forecast arrays. Primary comparison is B_COMMON vs C0_COMMON; C1_COMMON
is exploratory sensitivity, not validation-selected and never selected by impact.
Quantiles are copied exactly, with scored actual/stockout/mask fields removed before
host planning. CQR never replaces LOW/HIGH; closure is not applied again. C1 binding
retains the original base artifact plus its separate endpoint-parameter SHA-256.

### Operational admission and synthetic fixture scope

Runtime inventory still contains the six pinned workbooks. Original operational
admission/evidence remains BLOCKED: unknown unit aliases/serving/batch/yield/loss
semantics and effective historical recipe/stock/fee/supplier/constraint facts are
not repaired by F3. Mandatory safety-stock/aggregate rules remain unsupported for a
source-faithful case. No price denominator is inferred, unknown fee/loss/stock is
not zero, purchase history is not stock/receipts, and POS+recipe-derived usage is not
independent truth. The08/07 stock snapshot is not used as historical June inventory.

The frozen setup retains separate source-supported Product identities/units and
forecast/declaration provenance, existing user hash-bound POS/calendar assumptions,
source-faithful blockers, and F3_SYNTHETIC operational values. No new real Store fact
declaration is made. Fixtures are defined only from origin/Product scope/timezone/
Store and a fixture identifier, never forecast or future actual quantities. Synthetic
Ingredient identities g/ml are distinct from workbook Ingredient identities.

Two latest available F2 origins are selected chronologically before impact scores:
24/06 and01/07/2026. There are four fixtures per origin and three arms,24 runs.
All five Products retain their own `ly` identities. Common synthetic policy is
BASE95% EACH Product; LOW/BASE/HIGH100% construction remains unchanged. The base
recipe uses one g and one ml per serving, yield1/process loss0, with effectivity
and complete fictional lot/offer/fee/constraint coverage explicit in the snapshots.

| Fixture | Explicit F3_SYNTHETIC facts | Technical domain / certification |
|---|---|---|
| stock_only | 100000 g and100000 ml initially; expiry O+10; no offers; budget500 VND | 1 vector / exact≤9 |
| scarce_purchase | g0, ml100000; one400g pack at20 VND, MOQ1, upper4, lead0/shelf10; supplier fee3; budget500 | 5 vectors / exact≤9 |
| dated_shared | Shared initial500g expires O+2,500ml expires O+3; two800-unit packs at40/25 VND, upper2 each, fees3/2; g lead2/shelf4, ml lead0/shelf7; budget500 | 9 vectors / exact≤9 |
| tight_budget | Same physical setup/offers as scarce_purchase; explicit budget23 VND | 5 vectors / certification DISABLED |

Dated_shared uses dated recipes: through O+3 yield1/loss.1, from O+4 yield2 with
two g/two ml per batch and loss0. Each Ingredient has explicit gross capacity200000
in its own unit; supplier/Ingredient order limits2000 are separate from technical
pack bounds. All prices are synthetic VND/pack, not interpreted workbook prices.
Synthetic policy has no safety-stock rule and does not claim to implement all
workbook constraints. Exact rational quantities and money are never rounded to packs
or merged across g/ml. No fixture was changed after impact scores were inspected.

### Resource and evaluation contract

One global F3 batch hard300s; maximum144 native solves, maximum2 per strategy,
host cooperative invocation4s with unchanged equal-remaining-strategy deadline allocation.
Indivisible exact validation may overrun that cooperative budget; actual host
elapsed/deadline-overrun fields are retained. Only the overall300s subprocess cap
is a hard process deadline, not a per-run latency guarantee.
Domain/certification policy is identical across arms within each fixture. The host
SciPy/HiGHS default options are unchanged; there is no exposed seed parameter to
invent or tune. No search candidate/cache is carried between arms. Deterministic
origin/fixture order rotates the first arm by `(origin_index+fixture_index)%3` to
interleave B/C0/C1; single-run cold/warm/deadline effects remain diagnostic limits.
Parent preflight time is deducted from the subprocess timeout. Global consumed
marker and exclusive child claim prevent resume/retry or source-change budget reset.
Per-case outputs/resource receipts remain available after PARTIAL/timeouts.

Existing E4 `planning_request`, `plan_forecast`, `ImpactBudget`, `finite_oracle` and
`realized_evaluation` are reused; no second procurement engine or simulator exists.
The graph is forecast → dated BOM → host procurement/2 → exact serving/FEFO →
comparison/2 → selector/1. Finite enumeration proof is only CAPTURED_FINITE_DOMAIN_ONLY;
UNPROVEN/UNKNOWN, incomplete search, blocked input, technical failure and no-winner
remain separate. References never become available recommendations.

Planned results retain every strategy/options, purchase+generic payable fees,
Ingredient/unit pack quantities, Product/path requested/served/lost/service,
Ingredient/path expiry/ending stock, gaps/coverage and solver/proof/domain/timing.
Realized counterfactuals retain the winning basket, arrivals and starting fixture,
replace demand only with a complete known-false observed horizon, then run exact
serving/FEFO without procurement. On24/06 all35 outcomes are eligible; on01/07 only
34/35 are known-false, so its realized ledgers are NOT_EVALUATED with incomplete-primary
reason. No winner also means no realized recommendation ledger; no zero basket is
substituted. No cross-unit total waste or invented economic score is reported.

Hand tests verify ample-stock zero purchase,500-serving purchase requiring two400g
packs,40+3=43 VND, finite exhaustive ranking, dated recipe/loss/arrivals, exact cost/
mass balance and mask/no-winner handling. Oracle proof does not upgrade native or
production proof. Fresh replay semantically re-evaluates retained fixed baskets,
comparison/selector and eligible realized serving with all fitting/procurement-solve
entrypoints forbidden; it reports missing/noncomplete cases separately within120s.

Canonical output is `runtime/challenger/f3/experiments/<identity>/`: frozen
`setup.json`, per-case retained graph and small oracles/resource/progress/run receipts;
final aggregate publication is conditional on reaching the end of the batch.
Source/runtime/input drift rejects;
old E4/F2 artifacts/manifests/budget receipts are not overwritten. Commands:
[F3 runbook](../runbooks/FULL_TEST_FLOW.md#forecast-f3).

### Retained results — PARTIAL, not a completed benchmark population

The one batch hit its hard deadline at parent300.016s (termination/collection overhead
included), retaining19/24 COMPLETED cases and resource evidence for50 native solve
attempts (47 solver-evidence records belong to completed retained cases;3 attempts
have only budget/in-flight evidence). It was not resumed. Missing:01/07 dated_shared C0/C1 and all three01/07
tight_budget arms. The in-flight case has no completed output and cannot enter paired
impact. Six origin/fixture groups are fully paired, five have paired winners and
only three24/06 groups have paired complete realized ledgers. Three retained24/06
tight-budget cases have null winner, not a recommended zero basket.

| Origin / fixture | B_COMMON winner outlay | C0_COMMON | C1_COMMON | Fixed-basket realized status |
|---|---:|---:|---:|---|
| 24/06 stock_only | 0 | 0 | 0 | Complete, identical across arms |
| 24/06 scarce_purchase | 63 (60 purchase+3 fee),3×400g | same | same | Complete, identical across arms |
| 24/06 dated_shared | 70 (65 purchase+5 fees),800g+800ml | same | same | Complete, identical across arms |
| 24/06 tight_budget | no winner | no winner | no winner | NOT_EVALUATED: no recommendation |
| 01/07 stock_only | 0 | 0 | 0 | NOT_EVALUATED: incomplete primary truth |
| 01/07 scarce_purchase | 63,3×400g | 83,4×400g | 83,4×400g | NOT_EVALUATED: incomplete primary truth |
| 01/07 dated_shared | 135,1600g+1600ml | missing | missing | Unpaired; incomplete primary truth |
| 01/07 tight_budget | missing | missing | missing | Not executed to completion |

All outlays are fictional VND, not Store spending. On24/06 dated_shared, the same
basket produces different planned BASE service: B100% for every Product, C0/C1
97.8317–98.0232% on their respective forecast paths. Yet on the common observed
truth the exact basket/arrivals yield identical Product service across arms:

| Product | Realized service24/06 dated_shared | Lost servings, exact ly |
|---|---:|---:|
| t3 Cà phê sữa | 99.1148% | 3569/1575 |
| t1 Sinh tố chuối | 99.1679% | 332/175 |
| t4 Nước cam | 99.1579% | 2573/1575 |
| t5 Matcha latte | 99.1734% | 664/525 |
| t2 Trà sữa trân châu | 99.2869% | 3403/1575 |

Realized dated_shared expires110g and ends with110ml (g ending0, ml expired0),
reported separately by unit. Realized scarce_purchase fulfills every Product100%,
g ending66g, ml ending98866ml, no expiry; stock_only fulfills100%, ends98866g and
98866ml separately, no expiry. These are hypothetical fixture ledgers, not independently
observed store consumption/waste. No cross-unit total or savings score is formed.

On01/07 scarce_purchase, B spends20 VND less but its own planned BASE Product service
is95.5700–95.6857%, versus C0/C1 100%; B's planned g ending0 versus C0/C1 207.3677g.
The demand paths differ, so this does not prove worse actual service or economically
better overstock. That origin has no complete truth ledger. Among completed paired
winner cases, no different-basket/equal-spend example was observed. C1's wider
endpoints do not change winner baskets/outlays versus C0 in the completed pairs;
they provide no demonstrated additional realized benefit or expiry penalty here.
No fixture was added/retuned to produce a preferred effect.

Host execution is FINISHED for6 ample-stock cases and INCOMPLETE for13 others;
INCOMPLETE retained exact-valid/customer-pass incumbents can still win under the
existing selector. Across57 strategy records,18 have COMPLETE_EXACT_ENUMERATION
(domain1 ample-stock) and39 are UNPROVEN. Tight-budget feasibility is UNKNOWN,
not a market/global infeasibility certificate. Both independent oracle checks
passed captured domains1 and5 without upgrading any native proof. Native solver
seconds, cooperative deadline overruns, run order and per-case elapsed time remain
in the cases;50 solve attempts and the hard stop constrain comparison. Metrics do
not establish that C should replace B; they also do not certify B as a production winner.

Fresh-process dedicated verifier `scripts.verify_planning_f3` follows the existing
E4 verification pattern to avoid repeated graph reconstruction: full schema validators
re-evaluate retained candidate/journal baskets, then comparison/selector and fixed
winning-basket actual serving are checked. No weakened schema/model construction or
new vector search is used. It verifies all19 retained cases,9 realized ledgers and
explicitly lists5 missing cases in53.5s under its separate hard120s limit,0 solves/
fits/forbidden IO/original writes. Its SHA-256 is recorded separately from the
unchanged frozen F3 execution source. This is semantic re-evaluation, not “no calculation”.

Because the batch was killed before final aggregate publication, its canonical
per-case/resource/oracle files and PARTIAL run receipt remain authoritative.
Verified read-only metrics and replay receipt are separately retained under
`runtime/challenger/f3/verifications/88b89d8dd839b44927156335658e54bc1203ae28e2b243029f9173c889108199/`
(`metrics.json`, `replay.json`), not fabricated as a completed batch report or
written over original cases.15 focused F3 tests passed; all1261 pre-F3 runtime/artifact/
source-snapshot/workbook files,85 frozen computation-source files and102 upstream
input pins retain SHA-256. No full-suite, DB/browser, independent unseen
accuracy, real impact or production acceptance claim is added.

PROPOSAL — F4 remains NOT_STARTED/unauthorized. Any acceptance/integration requires
explicit forecast/source/policy review, appropriate unseen/vintage and operational
completeness, current-rights capture, retained persistence/restart/replay/error/rollback
acceptance and explicit promotion selection. Completing missing F3 cases needs a
separately authorized experiment/budget, not reset/resume of this batch. No F4,
main/FE/Assistant/runtime8103 change or promotion was performed.

<a id="demo-baseline-ab"></a>
## CURRENT FACT — baseline demo A/B after main readiness merge

E4/admission WIP was checkpointed at `eaf40b9`; merge `1c48162` contains local main
`869eaec914aa6905d6b935889afebe7d973004ae`. Only CURRENT_STATE/ROADMAP conflicted;
both challenger and readiness accounts were preserved. Merged host eligibility,
recognized-only fallback, contextual resolver/admission/capture, offer omission,
finite proof scope and retained version/provenance remain main's implementations.
Offline C admission stays separate. No host fallback or supplier omission can certify C.
No DB, migration, public API, FE, assistant or production serving change is made.

ACCEPTED DECISION (this explicit request and dataset-specific reply): benchmark only
five single items t1–t5, retain literal units `ly` and every Menu status, timezone
Asia/Ho_Chi_Minh, and assume current-revision POS labels available at next-day start
for retrospective demo A/B. This is not recovered historical availability. Declarations
are bound to raw-bundle revision
`f79b217d99a47db6133591c6d3e01cd73820ab80849447147043a2ada152b592`.
Another bundle needs its own approval/evidence. Combo absence is not zero demand.

The entire runtime contains one complementary six-workbook baseline pack, all under
`runtime/uploads`; there is no next-week POS/CSV or competing variant. Selection is
by sheet signatures/content/hash, never suffix, mtime or filename recency.

| File | Bytes | SHA-256 prefix | Sheets |
| --- | ---: | --- | --- |
| 01_POS_BASELINE_to_2026-07-08.xlsx | 41529 | 23010aaa9a8a88e0 | README; POS_T7_2026 |
| 02_USAGE_BASELINE_to_2026-07-08.xlsx | 21008 | e47eefcb233dce82 | NL_thực_dùng |
| 03_INVENTORY_PURCHASE_BASELINE_snapshot_2026-07-08.xlsx | 14468 | ab3c5764c9fe230d | KiemKe_08-07; PNK tháng 7; Vendor rules |
| 04_RECIPES_BUSINESS_RULES.xlsx | 14104 | a4370e477ffc4cfe | Định lượng món; Điều kiện vận hành |
| 05_CONTEXT_HISTORY_and_W1_FORECAST_2026-01-01_to_2026-07-15.xlsx | 12317 | 042e97456d2293b4 | Calendar + Weather |
| 06_MENU.xlsx | 14885 | 6864dc86b9cbcca1 | 06_Menu |

Full paths/SHA-256/sheet dimensions, physical row counts, headers/notes, date coverage,
formulas/cache metadata are retained in ignored
`runtime/challenger/dataset-admission/inventories/6b174139bcd304ca869e9220cfb37bffc6afd22a6f773b1f2541b3b21b6b192c/inventory.json`.
No formula/macro/external link is executed, cached formula value promoted, or workbook
saved. Content supersedes stale README counts and descriptive combo pause claims:
945 Product/day rows over189 dates,01/01–08/07,5 Products,23 explicit zeros,
18 stockout=true and927 false; no duplicate/conflicting keys, blank quantities,
unknown stockout or missing Product/day. Calendar covers196 dates01/01–15/07.
This is a demo/test pack with synthetic operational stock and POS-derived usage;
POS generation is not independently verified. It is exposed demo evidence.

Manifest `causal_benchmark/2` explicitly selects A/B, preserving E1 model settings,
two validation/two holdout origins, seven-day spacing/horizon, O−56/point/CQR windows
and all-holdout-label quarantine. Its source/host hashes participate in experiment
and fit identities. E3/E4 /1 bytes/results remain frozen and are not pooled with /2.
Old experiments require their original source/runtime; merged-source replay must fail
closed rather than overwrite old receipts. Admission does not require six files:
sales+Menu can support A/B; optional calendar issues block only C.

| Arm/action | Status on supplied pack | Reason / comparison scope |
| --- | --- | --- |
| A host baseline | VERIFIED outputs/replay; EXPLORATORY | 4 origins,140 predictions, fixed causal baseline,0 fallback |
| B trained host | VERIFIED outputs/artifacts/replay; EXPLORATORY | 4 origins,12 quantile booster fits,140 predictions,0 fallback |
| C challenger | BLOCKED,0 fits | Historical known-at calendar/revision evidence absent; first native split has at most77 eligible distinct target dates after28-day prefix, below84. Complete current calendar is not historical vintage proof. |
| E4 supplied pack | BLOCKED,0 solves | Historical operational population/basis, exact price/MOQ/fees/loss/completeness/requirements and applicable unsupported safety constraints remain unresolved. Old E4 remains COUNTERFACTUAL_SYNTHETIC / INCOMPLETE. |

Origins are10/06,17/06 (validation),24/06,01/07 (exposed demo holdout). The common
mask covers140 distinct Product/day outcomes across28 dates;138 known-false are
primary (69 per partition),2 censored lower bounds are excluded from primary scores.
Missing/unknown counts are0. No09–15/07 outcomes were supplied, so no next-week
accuracy claim is made. Training/selection never uses the14 holdout target dates;
mature past observations may remain inference features under the existing policy.

| Arm | Partition | MAE ly | WAPE | Bias ly | Pinball P25/P50/P75 | P25–P75 coverage / width ly |
| --- | --- | ---: | ---: | ---: | --- | --- |
| A | validation | 7.2029 | 19.1007% | −5.1159 | 2.4130 / 3.6014 / 3.2382 | 65.2174% /10.5761 |
| B | validation | 5.0141 | 13.2965% | −0.8818 | 2.1272 / 2.5071 / 1.8669 | 43.4783% /8.4501 |
| A | holdout | 8.2174 | 23.2282% | −2.4493 | 3.8406 / 4.1087 / 2.9348 | 53.6232% /10.6377 |
| B | holdout | 6.0417 | 17.0781% | +0.9190 | 3.2157 / 3.0208 / 2.0553 | 46.3768% /8.4740 |

WAPE denominator is sum of primary paired observed quantities, null if zero.
Validation-only equal-task mean pinball selects B (2.1670 vs3.0842); no deployment
selection is performed. Raw quantile crossings A0/B1, final0; CQR absent, never
labelled as the P25–P75 interval. Per-Product/unit/horizon/partition/mask metrics,
model bytes and exact training keys live in retained outputs. Mathematical scores
are not business value/savings or proof of calibrated demand under stockouts.

One hard-bounded subprocess batch ran in about7.4s, below300s, with12 boosters,
0 postprocess fits/0 solves, no trials/repeats. Retained compute times: A0.172s,
B training5.063s/inference0.171s. The runner denies DB/provider imports, socket/DNS
and subprocess launches before benchmark imports; Windows standard-library platform
metadata is primed first. Run/replay receipts contain zero forbidden attempts.
Fresh-process replay verifies all8 checkpoints without fitting. The post-run repair
only scopes malformed optional calendar findings to C; the new admission has exactly
the same dataset/plan identities, replays the same run, and is not a new benchmark.

Current admission/selection:
`runtime/challenger/dataset-admission/datasets/571fb650d4a867e7e8e51e485fc83b960dc5c1dd4aa52ab260d9a924c67ad21d`.
Original batch admission is retained at `7fda37d4bd872adb6de42d60a854ee55c196bce8772c70211e52622feec7d9c6`.
Experiment/output directory:
`runtime/challenger/benchmarks/experiments/efb23096f8613c8e77238d72daaac0a54c9d78bab577a89e675499807d171a1c`.
Dataset digest is `eb34bc5d8b8e94ed79efb0642cfa4ed89d4ac71ccdc81bfc5b0f6080a1459fd1`.
Promotion remains INSUFFICIENT_EVIDENCE / LOCKED; E5 NOT_STARTED.

Remaining E4 evidence is localized in admission findings: `Vendor rules` price
denominator/currency/MOQ and dated deliveries, payable fees/effectivity/known-at;
`Định lượng món` loss/basis/version availability (not usage Hao hụt); `KiemKe_08-07`
completeness/expiry-tracking and operational temporal basis; `Điều kiện vận hành`
weekly budget versus order cap, capacity units, Product/path requirements and
unsupported safety-stock semantics. Explicit `shelf_life_days` is retained, not
reported absent. A July08 stock snapshot cannot represent earlier rolling origins
or realized stock from a simulated basket. Receipt date remains unknown/warning,
not inferred from lot codes. Declarations alone cannot implement unsupported policy.
See [reproduction/recovery](../runbooks/FULL_TEST_FLOW.md#challenger-demo-ab).

## E4 counterfactual Planning impact

ACCEPTED DECISION (explicit E4 task): preserve dated BOM/reciprocal loss, exact
progressive Product serving/FEFO, procurement/2 construction/customer requirements,
fallback/winner and resource/proof semantics. E4 composes existing `expand_bom`,
`execute_procurement_v2`, comparison/2 and selector/1 from a typed detached snapshot.
This is the host computation boundary, not public operational capture/persistence
acceptance. No new-engine optimizer, training, LLM, FE or production activation.

CURRENT FACT: `tests/fixtures/forecast_engine/planning_impact_setup.py` defines fixed
synthetic facts from scope/origin only. No actual or forecast quantity enters stock,
recipes, budget, requirements, capacity, supplier limits or search-bound generation.
Sixteen templates cover four E3 origins and four fixtures: ample stock/no purchase,
shared Ingredient purchases, dated recipe/loss plus arrivals/expiry, and a36-vector
bounded domain with certification disabled. Two Products retain cup/piece; Ingredients
retain g/ml. Known-at provenance is an explicit fictional declaration at the captured
next-run decision instant, not recovered historical inventory. E3 native artifacts
were actually fitted/published later; this remains a post-hoc counterfactual study.

The shared frozen policy explicitly requests BASE95% each Product, LOW/BASE/HIGH100%
construction, integer packs/MOQ, generic per-supplier payable fees, capacities,
one-order supplier limits and budgets25 (14 for bounded_unproven), all synthetic.
Search resources are identical across A/B/C within every fixture:2 seconds per host
invocation,4 solves per strategy, optional exact certification limited to16 vectors.
Three tiny fixtures have domains1/6/6; the36-vector fixture remains UNPROVEN.
The complete manifest declares48 runs, maximum576 native solves and300 seconds
cooperative cumulative computation budget, one fixed A→B→C repetition per origin/
fixture. Actual overruns at an indivisible host/validation boundary are retained;
there is no hard process deadline or latency guarantee. Smoke runs one fixture on
the first origin; full execution reuses its exact checkpoints. Budget is not reset
on resume. No tuning or extra repetition is performed to improve observed results.

Input admission loads actual E3 dataset/plan/checkpoint envelopes, verifies experiment/
runtime/source identities, retained fit checkpoints and native artifact byte hashes,
and replays E3 outputs before initial freeze. Model labels/artifact/output identities
remain A/B/C. E4 snapshot, planning input, computation source and forecast-only output
digests own planning cache identity. Actual targets never enter that input/digest.
Canonical aware instants compare as typed values, including equivalent timezone
representations. Private immutable checkpoints retain exact candidates, customer/
construction gaps, winner/null, reference-only candidates, costs, raw native evidence,
termination, proof scope and timings. No-winner is not a zero-basket recommendation.

Planning requirement pass means pass on that arm's forecast design paths only.
Realized evaluation is separate: keep the selected basket/arrivals and operational
facts fixed, put eligible observed truth into a new evaluation input and run only
host exact serving/FEFO. It never calls procurement or changes budget/recipes. A full
primary observed ledger requires every Product/day to be present and known-false;
unknown/censored/missing cannot become zero. Otherwise retain target/mask identity and
mark realized unavailable, even when a forecast-path winner exists. Null winner also
makes realized recommendation evaluation unavailable. Separate hand-oracle complete
truth is test-only, explicitly identified, and never fills E3 observed-target gaps.

Metrics preserve per-Product/unit requested/served/lost sales and exact service,
per-Ingredient/unit consumed/expired/ending stock, and purchase+payable fee outlay.
No mixed-unit service/waste totals, profit/savings or confidence intervals treating
overlapping forecast tasks as independent. Reports retain every attempted arm,
paired completed/winner/realized availability and exclusions; they never condition
comparison on C having a winner. Lower spend without service context is not success.

Verification uses literal hand arithmetic for zero-purchase, integer packs/MOQ/fees,
budget/no-winner, shared bottlenecks, dated yield/reciprocal loss, arrivals/expiry,
underbuy/overbuy and incomplete actuals. On the first origin's tiny domains, a separate
exhaustive fixed-basket oracle checks feasibility and host ranking without native
solves. That proof belongs only to the captured finite domain, not to MILP. Native
search and exact validation remain unchanged; timing/search-limit noise and a single
run order constrain generalization. Real impact remains REAL_IMPACT_BLOCKED.

Commands in the isolated venv (no database/server/provider/worker startup):

```powershell
.venv/Scripts/python.exe -m scripts.planning_impact --enable freeze --e3-experiment 1bd73d0fbceca55fd5285924cdc8626e1ffe7b9a39052df663c97865b77a5727
.venv/Scripts/python.exe -m scripts.planning_impact --enable smoke --experiment <printed-E4-identity>
.venv/Scripts/python.exe -m scripts.planning_impact --enable run --experiment <printed-E4-identity>
.venv/Scripts/python.exe -m scripts.verify_planning_impact --experiment <printed-E4-identity>
.venv/Scripts/python.exe -m pytest tests/unit/test_planning_impact.py -q
```

Owned ignored `runtime/challenger/planning-impact` contains the frozen plan, imported
dataset, source/environment hashes, resource receipts, planning-only checkpoints,
separate realized ledgers and reports. `verify_planning_impact` starts a fresh process,
recomputes fixed baskets/comparison/selector and realized serving for every retained
completed case with zero procurement solves and a120-second verification budget.
It reports missing/noncomplete cases explicitly; successful replay of a subset is
not completion of the manifest. Built-in `planning_impact replay` requires all48.
No model/operational data, runtime result or private row is committed to Git.

Real E3/E4 evidence still requires authorized unseen daily demand/stockout/calendar
vintages plus historical recipe versions, balances/receipts/expiry, supplier terms,
payable fees, customer requirements/budgets and resource/policy captures actually
available at each decision. Synthetic operational definitions provide no such proof.
E3 remains PARTIAL / REAL_BENCHMARK_BLOCKED; production LOCKED, E5 NOT_STARTED.

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
| E4 | PARTIAL / COUNTERFACTUAL_SYNTHETIC: common frozen operational fixtures, host forecast-only planning, separate fixed-basket observed realized evaluation, hand/finite oracles and retained checkpoints. Bounded manifest INCOMPLETE at wall budget; REAL_IMPACT_BLOCKED, no savings/promotion claim. |
| E5 | Production activation/promotion NOT_STARTED. F4 separately covers isolated synthetic test integration/current auth/fresh-session/process retention; it does not authorize production selection, activation or automatic promotion. |

E1–E4/admission are checkpointed locally; the main-readiness merge and separate
A/B demo execution above do not open E5. Changes after checkpoint/merge remain WIP.
E3 checkpoint: `c2544c1025815bd0ccef9acb524f6f265dd03c45`.
Rollback E4 consists of its detached impact contracts/harness/tooling/fixtures and
current documentation changes; retain private artifacts/evidence and operational data.
Later runtime rollback must select a retained compatible host serving identity,
keep challenger captures/artifacts/audit and never rewrite completed Planning.

TECHNICAL DEBT / observed drift: historical ADR implementation-status paragraphs
and fixtures README still mention earlier unimplemented paths/head0017, while current
wired source/head0027 has evolved. The authority intent remains unchanged; these
historical statements are not current runtime evidence. This slice reports the drift
without editing accepted ADRs or unrelated documentation to hide it.
