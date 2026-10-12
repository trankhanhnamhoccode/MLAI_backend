# S3.2 -- Pure dated BOM

Classification: CURRENT FACT; user-authorized S3.2 arithmetic choices. ADR-016
accepted intent unchanged. No Decision policy/serving/budget choice is made here.

## Entry point and result

```python
expand_bom(prepared: PreparedDecisionInput) -> BOMExpansionResult
```

`app/application/use_cases/bom.py` revalidates every public call, including copied /
constructed models. It copies and canonicalizes the complete captured snapshot into
`result.prepared`; retains forecast model/input identities, source references,
assumptions, captured warnings and original Decision issues. All nested collections
are immutable tuples / frozen contracts. Source object and caller containers remain
unchanged. No filesystem, provider, live data query or Session is used.
Plain frozen domain values and arithmetic live in `app/domain/demand/`;
Pydantic remains exclusively at the application boundary.

`BOMExpansionResult` (schema_version=1, bom_version=dated_bom/1) contains:
- `paths`: ProductDemandPath LOW/BASE/HIGH, from captured P25/P50/P75.
- `contributions`: path/Product/day/recipe/Ingredient/exact unit/quantity.
- `totals`: IngredientDemandTotal per path/day/Ingredient/unit.
- `issues`: original issues plus BOMIssue with optional day/path and affected IDs.
- `status`: COMPLETE, DATA_BLOCKED or ARITHMETIC_BLOCKED (BOM only).
- `decision_readiness`: DATA_BLOCKED if any known DATA_BLOCKER, else NOT_ASSESSED.

COMPLETE means full BOM calculation, **never whole-Decision readiness**. A missing
expiry blocker may coexist with complete BOM math. No blocker disappears. Blocked
BOM returns no paths/contributions/totals, so consumers cannot treat a dropped
Product or a partial numeric result as success. The result is an internal use-case
contract, not a new API, DecisionRun package validator or persistence adapter.

## Dated semantics and ordering

Input boundary requires exact captured Product scope and D+1..D+7 forecast coverage,
finite nonnegative ordered quantiles, same Store, valid units and recipe graph.
Recipe chosen per Product/day with both effective bounds inclusive; no overlap
resolution/fallback. Missing/empty recipes require S3.1's existing object-specific
MISSING_RECIPE DATA_BLOCKER to admit the snapshot; otherwise validation rejects it.
Admitted gaps create MISSING_RECIPE / EMPTY_RECIPE diagnostics for every affected
Product/date and block the entire BOM, including when Product demand is zero.
Invalid copied scope/unit/overlap still raises ValidationError at entry.

Contribution = demand * RecipeLine.quantity / (yield_quantity * (1-loss)).
Lines describe the entire recipe yield. Exact unit labels are preserved without
kg/g conversion or normalization. No inventory, safety stock, packs, MOQ, serving
allocation, candidate strategy or budget participates. Unused captured Ingredients
do not produce demand; used recipe lines at zero demand do produce explicit zero.

Paths are ordered LOW/BASE/HIGH; within each path Product demands follow the snapshot
validator's date/Product ordering. Contributions sort path/day/Product/Ingredient;
totals sort path/day/Ingredient/unit. Issues sort deterministically by dated context
and contents. Source collections are canonicalized without losing evidence.
These are **design demand totals**, not calibrated Ingredient quantiles and not
probabilities. Strategy construction LEAN/BALANCED/PROTECTED is a separate future use.

## Arithmetic version dated_bom/1

Exact rational coefficient q*line/(yield*(1-loss)), with quantity powers of ten
carried separately, avoids intermediate Decimal rounding. Each contribution crosses
one Decimal division boundary: precision=50 significant digits, ROUND_HALF_EVEN,
Emax=decimal.MAX_EMAX, Emin=decimal.MIN_EMIN (on supported Python: +/-999999999999999999).
No arbitrary epsilon or clipping. No serving/integer or currency settlement rounding.
Repeating division is rounded once; tie cases are tested independently.

Totals are the **exact sum of exported, already rounded contributions**, not a new
rounding of the sum of unrounded rational terms. Owned aggregate context increases
precision to cover max adjusted exponent minus min stored exponent, carry digits
and a safety digit, at least 50. Inexact is trapped. Thus a 51-digit total is valid
and reconciles exactly to the published rows; aggregate precision is not capped at
50. Ambient precision, rounding, traps and exponent settings do not control math.

Underflow that loses precision is trapped; exact nonzero subnormals are allowed
down to Emin-49 for contribution division. Positive quantities never become
fabricated zero. Overflow / invalid / nonfinite cannot return successful quantities.
Technical capacity limits: 10000 normalized source coefficient digits; loss decimal
scale <=10000; aggregate working precision <=10000. Exceeding these limits returns
BOM_NUMERIC_CAPACITY, not approximate arithmetic. These resource limits are not
business thresholds or model-readiness policy. Huge quantity exponents are kept
separate and need not expand into huge integer buffers.

The existing S3.1/shared Pydantic NonnegativeDecimal boundary rejects some finite
large Decimals (e.g. 1E+2000000, also as a Decimal instance) with finite_number on
this installed version. S3.2 does not relax that shared boundary. Invalid inputs
remain ValidationError. If valid inputs produce a finite result outside that
output range (e.g. 1E+300 * 1E+300), it becomes BOM_NUMERIC_BOUNDARY with dated affected
IDs; no partial success. Domain exponent-range tests are distinct from public
contract tests. Only this known numeric validation error is classified; unexpected
validation/programming errors still propagate rather than becoming business success.

Other controlled codes: BOM_NUMERIC_OVERFLOW, BOM_NUMERIC_UNDERFLOW,
BOM_NUMERIC_INVALID. ARITHMETIC_BLOCKED retains the full captured provenance and
issues; computation stops at the first deterministic arithmetic blocker.

## Examples and verified scope

- 40cups, yield10, line1000ml, loss.2 => 5000ml per day/path.
- G01 8cups, yield10, line100g, loss.2 => 100g/day, 700g BASE week.
- Recipe switches on D+4: BASE3 * line1 => 3g days1-3;
  BASE3 * line2 => 6g days4-7, with the actual dated recipe IDs.
- G13 two Products (0,5,10), each line1g/yield1/loss0 => totals 0/10/20g.
- Exported contributions 1 and repeating 1/3 => total 1.333... (50 threes),
  exactly their sum, 51 significant digits. Missing recipe days4-7 => no outputs.

Executable tests: `tests/unit/test_bom.py`. G01/G09/G12/G13 and captured-only G14
have BOM assertions; their procurement/FEFO/selection/persisted-replay expectations
remain specifications. No simulator tests, forecast accuracy or DB integration
are claimed. Commands/results/rollback: [current verification runbook](../runbooks/FULL_TEST_FLOW.md).

HISTORICAL S3.2: serving/budget/no-winner questions were OPEN. CURRENT FACT S3.3:
ADR-017 approves serving and future procurement/no-winner direction; pure serving/FEFO
implemented in [SERVING_FEFO](SERVING_FEFO.md). Exact future search/ranking and
policy-v2/schema wiring remain pending. BOM source/contracts/arithmetic unchanged.
