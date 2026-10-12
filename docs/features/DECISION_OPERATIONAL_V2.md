# Operational decision /2 — S3.6.2

Classification: CURRENT FACT for code and executed unit checks; ACCEPTED DECISION
for user-authorized /2/P1 intent; IMPLEMENTATION BACKLOG for public flow/persistence.
Status COMPLETE within the internal S3.6.2 scope: PostgreSQL acceptance PASS (2026-10-09).

## Actual entrypoints and retained values

- `app/application/contracts/decision_capture_v2.py`: explicit Store/cutoff/referenced
  forecast, effective Product/path requirements, budget + version, policy + version,
  inventory/inbound/fee/bounds/capacity declarations. No default/custom/saved resolver.
- `app/infrastructure/database/decision_capture_v2.py`: separate owned read-only
  REPEATABLE READ source, active menu plus catalog identities, dated recipes/terms,
  current lots/constraints, retained Forecast digest/units/model warnings and timestamps.
  Same snapshot as the first Store SELECT, using synchronous scoped repositories.
- `capture_decision_v2`: source returns detached values after owned resources close;
  scope projection revalidates source and explicit original input before computation.
- `execute_operational_pipeline_v2`: capture → BOM → procurement/2 → comparison/2 →
  selector/1. No persistence/write/API/LLM; no queries to reconstruct provenance afterward.
- `decision_capture_v2_validation.py`: re-derives scope, exclusions, projected input and
  provenance from retained source; forged/stale output rejects. Invalid row identities
  preserve known dependency graph, never fabricate missing numeric values.
- `decision_pipeline_v2_validation.py`: cross-phase identity and BOM quantity/coverage
  reconciliation; nested output contracts retain exact candidate/proof/eligibility checks.

## Temporal semantics

Same local date as start: CURRENT_CAPTURE, actual intraday observation; no promise of
midnight/day-start inventory. Different start: HYPOTHETICAL_CURRENT_CAPTURE with
NONCURRENT_PLANNING_CURRENT_FACTS and assumptions. Input keeps physical captured_at,
local_capture_date and planning_start_date. The hypothetical order instant is local
midnight at start; it does not replace inventory_as_of or source timestamps.

Future start assumes captured balance is the starting balance, without forecasting
intervening consumption or inbound. Expiry before start removes it. Past start does
not imply historical available inventory: a currently observed lot activates on its
original received_date and cannot be consumed earlier. `LotServingDay.arrivals` for
such /2 captured lots describes hypothetical eligibility activation of the captured
current balance, not an actual receipt/movement quantity. Purchases are hypothetical.
Future-dated lots relative to actual capture remain excluded, not hidden inbound.
Unknown receipt date remains unknown with warning, per unchanged serving semantics.

Recipe and supplier effective dates remain inclusive and unchanged. Expiry day is
usable, then discarded, under unchanged FEFO policy. Decimal/rational arithmetic and
progressive proportional serving/ranking are unchanged.

Example: seven days each request1, lot current balance3 received on day3 and expiring
day3: fulfilled [0,0,1,0,0,0,0], day3 hypothetical activation3, expired2. This is not a
reconstruction of actual historical sales/receipts; tests assert only declared assumptions.

## Scope, audit and preflight

All active menu preserved. Missing forecast/day coverage, dated/empty/overlapping recipe,
unit/reference faults and related Ingredient blockers exclude only known affected
Products. Shared Ingredient blockers propagate to all dependent Products. Unknown
attribution blocks the whole capture. Cross-Store row identities block; unknown/foreign/
inactive override raises invalid input, never becomes an exclusion.

Computed snapshot contains only eligible Product/dependency facts and full seven-day
forecast coverage. Original requirements remain in capture.request; only computed-scope
override subset enters engine. Excluded overrides get NOT_EVALUATED, not PASS. All
excluded yields NO_COMPUTABLE_PRODUCTS with no fake three strategy evaluations.
Original source issues and timestamps survive in capture/pipeline audit.

Budget and Store ceiling must both be explicit KNOWN; version and provenance retained.
Effective limit may be lower than ceiling; above ceiling blocks. A changed captured
operational ceiling conflicts with the supplied frozen ceiling and blocks, instead of
clamping/changing either. Prepared constraints retain the actual physical ceiling;
procurement/2 tightens it with the effective budget. Historical /1 and /2-without-basis
keep their equality guard. budget_version labels the caller's explicit selection bundle;
operational constraint identity/version is retained separately, not invented from it.
All original
declarations are checked before projection, including foreign offers/limits/fees and
duplicate declarations on excluded dependencies. UNKNOWN fee coverage blocks globally;
missing known fees for computed offers blocks preflight. NONE is an explicit complete
fee declaration, not inferred zero. Generic payable fee stays generic, never delivery.
Configured safety stock/committed inbound still uses existing unsupported/blocking checks.

## Outcome, errors and proof

CAPTURE_BLOCKED / NO_COMPUTABLE_PRODUCTS / COMPUTATION_BLOCKED / NUMERIC_UNSUPPORTED /
EXECUTION_ERROR / NO_ELIGIBLE_CANDIDATE / RECOMMENDATION_AVAILABLE are separate.
Capture status/readiness is not public readiness or forecast quality. Native deadline
does not automatically mean execution failure or infeasibility. Exact-valid/customer-pass
incumbent may be recommended with UNPROVEN; technical ERROR remains EXECUTION_ERROR even
when verified partial recommendation survives. No old DecisionRun COMPLETED mapping.
Unexpected source/validation/programming exceptions propagate; they do not become
business no-pass or success. This internal use case has no durable Run ID/recovery.

## Timing and verification limits

Capture/preparation, BOM, engine (build/search/exact checks), comparison, selector,
final output revalidation and total wall time are separate. Engine reported elapsed
and deadline overrun retained. Subsequent comparison/selector validation is outside
solver budget. Diagnostic timing amendment uses a newly validated PhaseTiming only;
business graph was recursively validated and BOM reconciled before returning.

Measured duplicate reconstruction was removed only inside new pipeline orchestration:
existing engine/comparison/selector boundaries still validate their inputs/outputs,
and final result constructor revalidates nested graph. Tests inject copied forged
selector/BOM returns and assert rejection. No global mutable validation cache.

See [task notes](../runbooks/FULL_TEST_FLOW.md) for exact commands/results. Synthetic
5/10 Product benchmark is not PostgreSQL evidence, an accuracy result, savings or
latency SLA. The engine deadline is cooperative and can overrun. Public C03 domain_size
is canonical integer text; internal Python counters stay exact integers.

Six PG acceptance tests in `tests/integration/test_decision_operational_v2.py` and
six /1 regressions in `tests/integration/test_decision_operational_capture.py` ran:
12 passed in 21.00s on guarded shelfcash_test, PostgreSQL 17.11. No source fix needed.
[Acceptance report](PROCUREMENT_V2.md) describes actual assertions.
New readiness, pytest log and fresh read-only post-fixture inspection are in
the original acceptance checkpoint; disposable reports are retired. Rerun current
tests against validated shelfcash_test rather than reusing historical PASS/BLOCKED output.
No development DB access/reset/migration or full suite. Historical S3.5.2 results
are unchanged; the new /2 adapter is now verified by its own PostgreSQL tests.

Resolver/default/saved/budget storage, auth, forecast orchestration/reuse, durable Run,
retention/replay/idempotency/worker/HTTP/OpenAPI/FE/Optuna remain implementation backlog.
