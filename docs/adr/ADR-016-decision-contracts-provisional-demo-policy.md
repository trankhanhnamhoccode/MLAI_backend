# ADR-016 — Decision contracts and provisional demo policy

Status: ACCEPTED — S3.1 contract boundary authorized by the user's S3.1 task,
2026-10-07. Acceptance does **not** accept the open allocation algorithms below.

## ACCEPTED DECISION — scope and authority

S3.1 adds opt-in typed request/snapshot/output validation, versioned policy and
hand-calculated golden specifications. Preserve ADR-001/004/005/010/011 and the S1
opaque DecisionRun fixture lifecycle. No DB migration, engine orchestration,
procurement/FEFO/BOM computation, recommendation selector or business HTTP API here.
S2 baseline or trained forecasts can be consumed without a claim that LightGBM
outperforms baseline. Real-data quality remains unproven.

User explicitly approved: Store-local cutoff D, D+1..D+7 Product planning scope,
one order at decision time, no replenishment, expiry X usable through X, captured
facts before computation, all three strategies evaluated on the same three paths,
backend selection, typed warnings/blockers, and package schema version 1.
Snapshot includes actual values/versions, not live references as a replay recipe.
No transaction is to span computation. Actor authorization/capture implementation
remain future; supplying a Store UUID is not authentication.

## PROVISIONAL POLICY — explicitly authorized demo v1

`competition_demo / 1`: BASE service target .95, HIGH .90. Candidate design demand
P50 + alpha*(P75-P50), alpha LEAN=0, BALANCED=.5, PROTECTED=1. LOW/BASE/HIGH paths
use captured P25/P50/P75. Strategies remain procurement protection intent, not
quantile labels or service guarantees. No probabilities, expected value or CVaR.
Aggregated BOM paths are not calibrated Ingredient quantiles.

Actual coefficients/targets and routine conventions are snapshotted. Contract v1
rejects mismatched values under that version. A reviewed policy v2 can change
configuration without rewriting a parameter-driven simulator; none exists yet.
This is neither an empirically optimized policy nor a forecast quality guarantee.

## PROVISIONAL POLICY — implementation design choices, not source facts

- Decision instant on local D+1, before trading; captured inventory as-of that same
  instant. Daily model treats lead=0 as arrival before D+1 service, lead=1 before
  D+2 service. Explicit DAY_START_CAPTURE; no intraday calendar inferred.
- Terms/budget selected at order date; recipes effective on each demand day.
  Known shelf life L gives hypothetical expiry arrival+L (L=0 usable on arrival
  day); this rule does not backfill unknown actual lot expiry under ADR-010.
- Service quantities aggregate only one exact Product selling unit; no serving
  normalization. Fractional planning servings allowed, not physical sales claims.
- Decimal division/ratios: 50 significant digits, ROUND_HALF_EVEN in owned context;
  exact conservation/pack multiplication uses rational checks. No currency or
  integer-serving rounding. Pack rounding happens only at procurement boundary.
- Safety is a terminal floor once, not a second multiplier on protected demand;
  explicit dated source constraints retained. No invented floor where absent.
- Preferred group both targets, then BASE-only, then target-not-met. Within the
  first two groups: lower purchase outlay, supported BASE-path waste value only if comparable,
  stable LEAN/BALANCED/PROTECTED. Undefined zero-demand ratios displayed as null;
  zero demand satisfies that target without manufacturing service=1.

These choices and limits are documented for review in DECISION_DESIGN. S3.1 validates
supplied identities, scope, coverage, arithmetic conservation, pack/MOQ/budget,
fixed arrivals and recommendation eligibility/group. It does not generate or rank
candidates, prove FEFO/BOM quantities, or verify hashes from retained bytes.

## OPEN QUESTION / PROPOSAL — not accepted by this ADR

- Global same-day proportional fulfillment wastes service under an exclusive
  Ingredient shortage. Review the progressive proportional alternative and its
  tradeoffs before S3.4. No allocation algorithm implemented or silently accepted.
- Budget allocation: review whole-MOQ basket admission vs discrete marginal pack
  heuristic; no optimizer/greedy implementation or optimality claim.
- Rank target-not-met candidates vs return a comparison without a winner; exact
  target-miss ranking needs approval before recommendation computation.
- Confirm safety-floor expiry treatment and handling of within-window floor changes
  before candidate generation; terminal floor is provisional, not hard feasibility.
- Public auth/API and replay persistence wiring belong to separately authorized
  slices. S3.1 defines canonical identity design, not hashing/retention execution.
- Existing S1 COMPLETED requires a recommendation, and FAILED cannot retain an
  output package. Decide how typed no-winner business outcomes are surfaced/stored
  before persistence wiring, without silently changing S1/schema in S3.1.

Rollback is code/docs/tests only; no schema or API change. Future behavior cannot
be declared implemented because these contracts can represent it.

References: [design](../features/DECISION_DESIGN.md),
[goldens](../features/DECISION_GOLDEN_CASES.md), [notes](../runbooks/FULL_TEST_FLOW.md).
