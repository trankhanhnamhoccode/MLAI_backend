# Forecast execution contract and historical quantile baseline — S2.1 / S2.2

Classification: CURRENT FACT for the modules/tests described here; ACCEPTED DECISION
for user-approved semantics in [ADR-012](../adr/ADR-012-observed-sales-forecast-execution-contract.md)
and the explicit S2.2 task specification below. CURRENT FACT: baseline-specific
readiness and pure historical quantile computation exist. S2.3 internal persisted execution is described below; no public
business API exists. S2.4-S2.7 now add trained LightGBM/evaluation/artifact execution:
see [FORECAST_TRAINED](FORECAST_TRAINED.md). Baseline-only absence/deferred statements
below describe their original slice boundaries. Real-data evaluation remains pending. [FORECAST](FORECAST.md) covers S1 persistence.

## Internal boundary and input example

`app/application/contracts/forecast_execution.py` defines frozen typed Pydantic
values; `app/domain/forecasting/validation.py` validates ordinary Python values
without Pydantic/FastAPI/ORM/HTTP/filesystem/LLM dependencies. Existing Contract,
Decimal/unit/metadata boundary conventions are reused. Engine Protocol and production
frameworks are absent. S2.2 uses small concrete functions, not an engine registry.

Executable example from `backend/`, using only synthetic observations/predictions:

```powershell
@'
from datetime import date
from uuid import UUID
from app.application.contracts.forecast_execution import (
    ForecastExecutionInput, PreparedForecastInput, ForecastEngineResult, validate_engine_result,
)
from app.domain.forecasting.validation import forecast_dates
store, a, b = UUID(int=100), UUID(int=101), UUID(int=102)
request = ForecastExecutionInput(store_id=store, product_ids=[a, b],
    cutoff_date=date(2026, 9, 11), history_start_date=date(2026, 9, 1))
prepared = PreparedForecastInput(schema_version=1, request=request,
    timezone='Asia/Ho_Chi_Minh',
    products=[{'product_id': a, 'selling_unit': 'cup'},
              {'product_id': b, 'selling_unit': 'piece'}],
    observations=[{'store_id': store, 'product_id': a,
                   'sales_date': date(2026, 9, 11), 'quantity': '0', 'selling_unit': 'cup'}],
    forecast_dates=forecast_dates(request.cutoff_date))
result = ForecastEngineResult(model_type='synthetic-fixture', model_version='v1',
    predictions=[{'product_id': p, 'forecast_date': d,
                  'p25': '0.125', 'p50': '1.375', 'p75': '2.625'}
                 for p in request.product_ids for d in prepared.forecast_dates])
validated = validate_engine_result(prepared, result)
assert len(validated.predictions) == 14
assert len(prepared.observations) == 1
assert validated.artifact_identity is None
print('14 keys: 2026-09-12 through 2026-09-18; sparse zero preserved')
'@ | .\.venv\Scripts\python.exe -
```

Quantiles illustrate shape only, never measured forecast accuracy or a baseline
algorithm. Product A's absent history days and Product B's absent observations stay
unknown. These supplied predictions prove validation, not model readiness or execution.

## Capture and semantics

Request contains Store ID, explicit nonempty unique Product IDs, D and history start.
Prepared input embeds that request (including Store/history window); timezone is a
required resolvable IANA name, with no default. Seven explicit forecast dates must
equal D+1..D+7. No arbitrary horizon option. Boundary rejects dates whose seven-day
horizon overflows Python DATE. It does not invent event timestamps.

Products retain exact selling_unit strings; observations retain Store ID, Product ID,
sales_date, quantity and selling_unit. Captured Product IDs must equal request scope.
Membership in the captured Store is asserted by the future authorized loader, not
proven by consulting a DB in this validator. Observation Store/scope/unit identity
is checked against the capture. Engine units derive from captured Product values.
No unit conversion, catalog auto-filtering, default stockout=false/closure=false,
weather or reconstructed target exists. Extra fields are forbidden.

History is inclusive [history_start_date, D]. Prepared canonical duplicate keys are
rejected, never aggregated. Explicit zero is valid; missing days stay absent. Decimal,
decimal strings and integers are accepted; floats/bools, negatives and nonfinite
values are rejected using S1's exact Decimal policy. No quantity rounding.

Frozen nested contracts and tuples retain values despite caller list/dict mutation.
Model revalidation recaptures nested instances, including at result validation.
Products/request IDs sort by UUID; observations/predictions by date then UUID;
dates ascending; warnings by all their fields (optional Product ID last). Ordering
has no business meaning and does not remove duplicate records.

## Engine return and mandatory coverage gate

Engine result fields: required actual model_type/model_version, optional nonblank
opaque immutable artifact_identity, typed predictions and structured warnings.
At the S2.1 value boundary artifact identity is metadata only. S2.3/ADR-014 maps
fixed baseline metadata to runs; S2.7/ADR-015 adds verified artifact lookup/identity
mapping in the concrete trained path, separate from this pure validator. Baselines may return no artifact and
must identify themselves accurately; no assumed LightGBM identity. Warnings require
code, severity (INFO/WARNING/ERROR), field, entity and impact, with optional Product ID.
No inference metrics or procurement/strategy fields are accepted.

Constructing ForecastEngineResult validates shape/quantiles and canonical order;
it does **not** establish complete coverage. Always call
`validate_engine_result(prepared, result)` before future persistence. This revalidates
both values and requires exactly requested Products x seven dates. It returns the
validated canonical result or rejects it; there is no persistence side effect.

| Rejection | Internal behavior |
| --- | --- |
| Invalid request, prepared scope/window/unit/timezone, shape or Decimal | Pydantic ValidationError; pure semantic checks originate in ForecastSemanticError |
| Empty engine output | ForecastSemanticError code EMPTY_OUTPUT |
| Duplicate Product/date prediction keys | ForecastSemanticError code DUPLICATE_OUTPUT |
| Missing/unexpected Product or date, including cutoff-day prediction | ForecastSemanticError code OUTPUT_COVERAGE, counts of missing/unexpected keys |
| Nonfinite/negative/unordered quantiles | Boundary ValidationError; pure validator code INVALID_QUANTILES |

Codes are internal, not accepted HTTP error mappings. Reject malformed prepared
input rather than silently filtering it. Future raw queries must select authorized
scoped sales with sales_date <= D and the chosen inclusive start; such query execution
is absent in S2.1 and is distinct from prepared-contract rejection.

## Baseline-specific readiness — ACCEPTED DECISION / CURRENT FACT (S2.2)

The user explicitly froze this policy in S2.2; it is not general Forecast or LightGBM
readiness. No accepted ADR is changed: ADR-012 records the historical S2.1 deferral,
while this section records the later authorized concrete algorithm specification.
No architecture-significant replacement/interface/framework decision is introduced.

`assess_baseline_readiness(prepared)` in
`app/application/use_cases/forecast_baseline.py` revalidates the complete capture
through S2.1 PreparedForecastInput, then returns a tuple of frozen plain Python
BaselineProductReadiness values in ascending Product UUID order. Each contains
product_id, status, observed_count, first_observed_date and last_observed_date.

| Actual observed count per requested Product | Status | First / last dates |
| --- | --- | --- |
| 0 | NOT_READY_NO_HISTORY | Both None |
| >=1 | READY | Earliest / latest real observation date |

Explicit zero counts as a real observation. Missing dates contribute no observation.
The entire scope is assessed independently; a history-rich Product cannot make an
empty-history Product ready. Reports do not mutate capture or fabricate facts.
Contract validation alone is not readiness. One observation is intentionally enough
for this weak reference baseline; it says nothing about confidence/accuracy or the
history requirements of a future model. No 7/14/28/90-day threshold or fallback exists.

## Historical Quantile Baseline — ACCEPTED DECISION / CURRENT FACT (S2.2)

`run_historical_quantile_baseline(prepared)` is the safe internal execution entrypoint:

1. Revalidate PreparedForecastInput (including canonical pure validate_prepared_input).
2. Assess every requested Product.
3. If any Product has no history, raise domain BaselineNotReadyError **before any
   prediction quantile computation**, with code BASELINE_NOT_READY, deterministic
   product_ids of all no-history Products and the complete readiness tuple. No partial
   result, DB write or HTTP mapping.
4. For each ready Product, take every captured observed quantity in the requested
   history window, including zero/repeated values; sort a new tuple ascending.
5. Compute empirical P25/P50/P75 by Decimal linear interpolation and use the same
   triple for each of the seven forecast dates. Publish truthful metadata
   model_type=historical_quantile_baseline, model_version=1 (strings), artifact_identity=None,
   No trained artifact, fake training metadata or metrics. CURRENT FACT: warnings=();
   this is an implementation choice, not an accepted confidence/quality warning policy.
6. Call canonical validate_engine_result and return only the validated result.

For sorted x[0..n-1] and q=.25/.50/.75, position=(n-1)*q, lower=floor(position),
fraction=position-lower. At an integer position use x[lower]; otherwise use
`x[lower] + (x[lower+1] - x[lower]) * fraction`.
All arithmetic uses Decimal, never float or integer forecast rounding. The plain
domain helper in `app/domain/forecasting/baseline.py` validates quantities using the
existing canonical quantile rule and selects sufficient local precision/digit range
for exact interpolation, independent of caller Decimal precision/rounding/exponent
limits. It restores caller context. Samples/dates are never sorted in place.

Known mathematical examples (not measured accuracy): [12.5] -> 12.5/12.5/12.5;
[10,20] -> 12.5/15/17.5; [0,10] -> 2.5/5/7.5; [0,0,10,20] -> 0/5/12.5.
Monday=10, Tuesday=missing, Wednesday=0 uses **two** samples, [10,0], not [10,0,0].
No imputation, clipping, weights, trend, weekday/seasonal/calendar/weather feature,
stockout correction, reconstruction or arbitrary uncertainty percentage exists.

Output retains S2.1 canonical order **forecast_date then Product UUID**. A two-Product
request returns exactly 14 rows. Same capture yields the same readiness, predictions,
ordering and model identity; no random/current-time/hash-based output is generated.
This transparent baseline is a reference for future model comparison, not a claim of
production suitability or high confidence. HISTORICAL INFORMATION (S2.2): no persistence/ForecastRun completion in that slice;
S2.3 now adds the internal orchestration described below.

Executable in-memory baseline verification from backend/:

```powershell
@'
from datetime import date
from uuid import UUID
from app.application.contracts.forecast_execution import PreparedForecastInput
from app.application.use_cases.forecast_baseline import assess_baseline_readiness, run_historical_quantile_baseline
from app.domain.forecasting.validation import forecast_dates
store, product = UUID(int=100), UUID(int=101)
prepared = PreparedForecastInput(
    request={'store_id': store, 'product_ids': [product], 'cutoff_date': date(2026, 9, 11),
             'history_start_date': date(2026, 9, 7)}, timezone='Asia/Ho_Chi_Minh',
    products=[{'product_id': product, 'selling_unit': 'cup'}],
    observations=[{'store_id': store, 'product_id': product, 'sales_date': day,
                   'quantity': quantity, 'selling_unit': 'cup'}
                  for day, quantity in [(date(2026, 9, 7), '10'), (date(2026, 9, 9), '0')]],
    forecast_dates=forecast_dates(date(2026, 9, 11)))
report = assess_baseline_readiness(prepared)
result = run_historical_quantile_baseline(prepared)
assert report[0].status == 'READY' and report[0].observed_count == 2
assert len(prepared.observations) == 2 and len(result.predictions) == 7
print(report[0])
print(result.model_type, result.model_version, result.artifact_identity)
print([(p.forecast_date.isoformat(), str(p.p25), str(p.p50), str(p.p75)) for p in result.predictions])
'@ | .\.venv\Scripts\python.exe -
```

Expected: READY/count=2; historical_quantile_baseline/1/None; seven rows for
2026-09-12..2026-09-18, each 2.5/5/7.5 numerically. Decimal trailing zero representation
may retain interpolation scale; no rounding or confidence/accuracy assertion.

## Historical limits — ACCEPTED DECISION / CURRENT FACT

Cutoff D is through the end of Store-local business day D; forecast starts D+1.
Filtering sales_date <= D cannot recover data the system knew at D if correction
happened later. Replay must use retained captured input; by-value in-memory capture
does not implement durable retention. True point-in-time backtesting requires future
availability/version history. Legacy target-date splits do not prove a model existed
at each prediction origin. No such historical guarantee is claimed here.

## S1 compatibility, deferred choices and verification

S1 start/complete/fail/get is unchanged: completion persists supplied predictions,
including empty output; scoped ownership/horizon/lifecycle checks remain. S1 windows
need not be adjacent or seven days; model/artifact metadata is still supplied at start.
Writers require idle clean synchronous Session; reads may autobegin. Full S2 coverage
applies only to the new execution gate, never retroactively to S1.

PROPOSAL / DEFERRED: future model estimator/quantiles/readiness, CQR/reconstruction/weather,
train/retrain/fallback/model selection, trained artifact lifecycle,
evaluation schema and trained-model metadata/recovery policies. S2.3 freezes concrete
baseline publication and failure behavior below. Do not put arbitrary provenance in
metrics_json. No ML dependency/public API/auth/import or trained model service is added;
S2.3 adds retention schema and internal execution. [ADR-013](../adr/ADR-013-future-store-mapping-approval-direction.md) records
accepted future import direction separately; mapping S5 and hardening S6 stay ordered.

S2.2 targeted/manual commands (PowerShell, repository-local venv; S2.1's historical
command/results remain in its task notes):

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_forecast_execution.py tests/unit/test_forecast_baseline.py tests/integration/test_forecast_execution_s1_regression.py tests/integration/test_application_paths.py tests/integration/test_repositories.py -q
# Full regression only at final gate after targeted green:
.\scripts\test.ps1 all
```

Pure tests use synthetic values with no DB/model/provider. PostgreSQL tests own only
shelfcash_test and verify unchanged S1 empty completion using committed fresh-session
reads and terminal guards; they are not fake execution E2E tests. No development
reset needed. S2.2 tests assert baseline math/readiness/context independence, all-or-
nothing scope before math, exact ordering/metadata, caller mutation and mandatory
canonical rejection of malformed output. See [S2.1 notes](../runbooks/S21_TASK_NOTES.md),
[S2.2 notes](../runbooks/S22_TASK_NOTES.md) and CURRENT_STATE for exact results/OpenAPI
evidence. S2.2 rollback only its new modules/tests and precise docs changes; preserve
S2.1 and S1 WIP. No DB downgrade. Stop after S2.2; S2.3+ needs separate authorization.

## Internal retained execution ? CURRENT FACT / ACCEPTED DECISION (S2.3)

[ADR-014](../adr/ADR-014-retained-baseline-execution.md) records explicit user authorization.
`ForecastExecutionUseCases(engine)` in app/application/use_cases/forecast_execution.py
owns all synchronous Sessions; it never receives or cleans a caller Session.
`capture(request)` loads every requested Product and all in-window canonical Sales
in one read-only REPEATABLE READ snapshot. Inactive Products are not silently omitted.
Store timezone/current selling units are captured. Unit stability within history is
an accepted assumption, not historical unit reconstruction or point-in-time data recovery.
Store IDs do not prove actor permissions: these are trusted internal calls only.

`execute(request)` captures -> validates/preflights -> serializes/hashes -> atomically
starts RUNNING plus retained JSONB -> closes Session -> runs unchanged baseline ->
validates exact coverage/identity -> atomically completes -> reads/verifies through a
fresh Session. Training window fields store requested history, not actual training.
No transaction or row lock spans computation. Identity is shared constants
historical_quantile_baseline / 1 / None, metrics_json=None. Any nonempty engine warnings
are rejected by this concrete persistence adapter, which has no warning-storage policy.

Table forecast_run_inputs retains one record per run: same-Store FK, object JSONB,
positive serialization_version, lowercase 64-hex digest, created_at. Old S1 runs have
no retention requirement. Input stays for RUNNING/FAILED/COMPLETED; insert/read only.
Serialization v1 uses prefix `shelfcash.forecast-input.v1\n`, compact sorted-key UTF-8
JSON, S2.1 canonical array order, UUID/ISO dates and exact Decimal strings. 10/10.0/10.00
share identity, signed zero is 0. Hash excludes run ID/timestamps/model/results.
JSONB text is not hashed. No fingerprint uniqueness/dedup, artifact or metrics overload.

`get(RunReferenceInput)` returns the unchanged S1 typed run result in an owned read
Session. `load_retained(reference)` validates payload/version/hash/run consistency;
`replay(reference)` computes without operational data lookups. `replay_persisted(reference)`
creates a new run/input record, checking current Store/Product existence only. Re-running
`execute` captures current operational values. Missing retention (including old S1 runs),
corruption, unsupported version and identity mismatch reject explicitly with
RetainedInputError codes. Pure replay can still compute if operational Product identities
are gone; persisted replay cannot recreate them. New UUID even if fingerprint matches.

Preflight no history creates no run. Start failure rolls back run and input together.
After durable start, exceptions preserve the original cause and expose run_id through
ForecastExecutionError. FAILED summaries contain fixed sanitized text, not raw secrets.
Completion rollback leaves no partial predictions. Failure recording uses a new
transaction. Recognized uncertain commit errors reconcile with fresh state; only
matching verified COMPLETED content can return success. Programming errors inside
commit/callbacks or cleanup never qualify for reconciled success on their own.
Durable COMPLETED remains COMPLETED but execution reports error with run ID.
Failure recording errors report actual known state; unreadable state reports UNKNOWN.
Acknowledged completion followed by read failure reports COMPLETED_READ_FAILED and
COMPLETED, never attempts to fail the run. Crashes may leave RUNNING: manual inspection,
no timeout/worker/automatic retries. Failed and completed content is not rewritten.

CURRENT FACT — corrective commit/cleanup semantics (2026-10-07):

- Supported stack: SQLAlchemy 2.1.3 / psycopg 3.3.6. Only SQLAlchemy OperationalError
  or InterfaceError wrapping psycopg OperationalError/InterfaceError can qualify.
  SQLSTATE 08000/08003/08006/08007 (connection/unknown resolution) and 40003
  (statement completion unknown) qualify during the commit call. With no SQLSTATE,
  connection_invalidated=True is required, using dialect disconnect evidence.
- A present SQLSTATE takes precedence over invalidation. Other states, including
  40001 serialization failure, 40P01 deadlock, 08001 connection establishment failure,
  integrity/data/programming failures, are not uncertain-success candidates.
  Generic DBAPIError, unwrapped driver errors, generic OperationalError without
  disconnect evidence and arbitrary Python exceptions also do not qualify.
- This conservative allowlist is not proof that COMMIT reached the server. Fresh
  state and full retained-input/result verification still decide success. Unsupported
  errors are reported, not inferred to be known rollbacks: a fresh read may reveal
  COMPLETED (error, no FAILED rewrite), RUNNING (record failure), missing start
  (NOT_STARTED), or unreadable state (UNKNOWN). No error-message matching.
- The private infrastructure owned-Session context, composed by application, preserves
  the primary exception through rollback,
  close and invalidation failures. Secondary failures are exception notes (type/phase)
  plus trusted diagnostic logs; raw errors never enter persisted business summaries.
  Failed cleanup attempts invalidation before fresh-Session reconciliation; it never
  reuses the failed Session. If close alone fails after commit, it is an execution
  error. Cleanup secondary to genuine uncertain commit is logged/noted without
  replacing that primary error. Reads/recovery/failure recording use this same guard.
- Failure-recording or verification failures remain secondary to the original execution
  cause; their actual state is reported only after fresh read. If rollback, close and
  invalidation all fail, resource release cannot be guaranteed; this is recorded in
  diagnostics, and state verification can still fail to UNKNOWN. No automatic retry.

Reference semantics: [SQLAlchemy exceptions](https://docs.sqlalchemy.org/en/20/core/exceptions.html),
[psycopg exceptions](https://www.psycopg.org/psycopg3/docs/api/errors.html),
[PostgreSQL SQLSTATEs](https://www.postgresql.org/docs/current/errcodes-appendix.html).
Typed transport fault injections verify orchestration, not a real network lost-ack
incident. PostgreSQL tests additionally exercise actual after_commit callback errors
and server-reported 40001; no concurrent serialization-conflict reproduction claimed.

Retention has no purge/TTL. No evaluated predictive calibration or performance claim.
DB snapshot consistency is not historical data availability at cutoff. Domain remains
I/O-free; application performs persistence. S1 empty completion remains allowed.
Migration 0007 adds retention only; downgrade loses inputs but leaves runs/predictions:
export/backup first if history matters. Public OpenAPI unchanged; S2 remains IN PROGRESS.
Runnable isolated verification: [S23_VERIFICATION](../runbooks/S23_VERIFICATION.md).
