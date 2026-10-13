# Pure procurement comparison/1

Classification: CURRENT FACT unless labelled OPEN QUESTION. Authority: user's S3.5.1
task, 2026-10-08. No new ADR or business policy acceptance; ADR-018 stays PROPOSED.

## Boundary and scope

`compare_procurement(ProcurementComparisonInput(procurement=ProcurementResult))`
returns immutable `ProcurementComparisonResult`. Contracts live in
app/application/contracts/procurement_comparison.py, projection in
application/use_cases/procurement_comparison.py, independent output reconciliation in
application/procurement_comparison_validation.py. Plain domain/decision/comparison.py
contains exact aggregation/delta helpers without Pydantic/infrastructure imports.

One fully revalidated S3.4.4 result provides all context. No DB, solver, procurement
execution, simulator, HTTP or provider call. Existing serving/procurement validators
check candidate snapshot identity, scope, unit/currency, coverage, conservation,
metrics, price/fees/constraints and targets. These are structural/exact checks, not a
new policy replay or search certificate. Inputs produced via construct/copy/unsafe
nested mutation are revalidated. No silent repair, skipped malformed candidate or
partial-success comparison. Sorting valid unordered rows changes presentation only.

Output options represent only existing exact-validated candidates. Source result and
all three outcomes are retained, including readiness/constraint coverage, captured
forecast warnings/issues/blockers/assumptions/provenance and all native/search journals,
diagnostics/proof evidence. Strategy outcomes reference an option or null. Zero-purchase
is an existing valid candidate, not null. No candidate produces no invented basket or
zero metrics. BLOCKED/ERROR/INCOMPLETE can be projected with retained valid evidence;
these underlying outcomes remain visible and are never called successful business work.

Projection COMPLETE means facts/outcomes were projected, including all-empty/blocked
cases. COMPLETE_WITH_DIAGNOSTICS means valid source facts have an evaluation grouping
conflict. Both keep decision_readiness=NOT_ASSESSED. There is no winner, recommendation,
suggested/selected strategy, ranking, probability, confidence, profit/revenue/ROI,
cost-per-extra-serving or Pareto score. Customer choice is the current product direction;
future selection/API behavior remains OPEN, not implemented by these internal contracts.

## Exact metric meanings

All Product metrics are per Product and LOW/BASE/HIGH over D+1..D+7. Requested,
fulfilled and lost sum the actual daily rows. Service is exact fulfilled/requested,
null on zero requested. Fractional cups are legitimate planning quantities; no integer
rounding or weighted business-value total. Product→Ingredient contributions and lot
consumption remain separate in the retained source; no Product→lot attribution invented.

Per Ingredient/unit/path: daily_shortage_sum sums existing daily diagnostic shortage
(full requested recipe need minus usable available, floored at zero). It is not a
purchase requirement or loss assigned to Products. horizon_ending is end-D+7 stock,
never sum of seven daily endings. expired and other_waste are separate horizon sums
with existing disjoint serving semantics; no valuation. All daily Product/Ingredient
rows remain accessible, and full lot/contribution rows remain in retained source.
No g/ml normalization or cross-Ingredient unit total, no cross-currency aggregation.

Purchase outlay = captured pack_cost × integer packs, exactly. Payable fees use explicit
captured NONE/PER_OFFER/PER_SUPPLIER_ORDER activation, once per applicable component.
purchase + payable_fees = total = candidate.outlay; components retain offer/supplier ID.
The source fields do **not** classify generic payable fees as delivery fees. Hence
delivery_fees=null and PAYABLE_FEE_TYPE_NOT_CAPTURED for payable fee modes, even when
the payable amount is known. Explicit NONE gives zero and NO_PAYABLE_FEES. This is
unknown fee classification, not unknown payable amount or a budget relaxation.

Quantity uses canonical reduced numerator/denominator and Decimal50 HALF_EVEN view.
SignedQuantity extends this convention for negative deltas (no negative zero).
All arithmetic uses Fraction and existing 1000-digit guards; no binary float arithmetic,
business epsilon, serving/currency rounding or ambient Decimal context dependence.
Raw native bound/gap floats remain evidence only, unchanged in each strategy outcome.

## Group identity, evidence and ordering

Exact canonical identity includes versioned captured procurement context/configuration,
captured offer/term/basket semantics (IDs/units/quantities/counts) and every hypothetical
arrival's lot/Store/Ingredient/unit/date/expiry/quantity. Same money or display value
is insufficient. Equivalent Decimal spellings normalize to exact rational identity.
Grouping uses exact canonical serialized values, not merely hash equality. SHA256
generates a deterministic cmp1_ token; detected collisions abort, never alias facts.
Tokens are internal comparison references, not persisted/HTTP resource IDs.

Full serving evaluation identity must also agree, including dated recipes/BOM,
contributions, lot/Ingredient/Product rows and issues. Unordered metric rows are
canonicalized for identity. Compatible duplicate plans become one option with all
source strategies. Each outcome preserves its own construction rule/target/floors,
target attainment, UNKNOWN versus NO_PASS_CERTIFIED, execution, solver, proof/scope,
completeness and journal. A certified source does not certify the other sources.
INCOMPLETE/UNPROVEN does not make an exact-validated candidate hard-invalid.

Same plan but incompatible evaluation stays as separate options with an explicit
SAME_PLAN_DIFFERENT_EVALUATION diagnostic. No simulator rerun or choice of an
authoritative evaluation occurs. Differences in evidence/targets alone do not prevent
grouping; they stay separate in outcomes. Optional fee classification stays explicit.

Options sort by internal token, not cost/quality; outcomes follow captured strategy
order. Metric rows sort by path string/entity UUID/day. Every unordered option pair
appears once, from smaller token to larger token. delta(A→B)=B−A. Product fulfilled/lost
and same-unit Ingredient metrics reconcile both ends exactly; outlay delta retains
currency. A reverse-direction consumer must negate the exact value. Positive delta
means increase, not inherently improvement (lost/shortage/expiry increases are losses).

## Failure behavior and limitations

Malformed input/output raises ValidationError/ValueError; comparison returns nothing
partial. Guarded arithmetic inability raises ComparisonNumericError with original
ServingNumericError cause. Token collision aborts. Unexpected programming errors
propagate; there is no catch-all successful projection. Structurally valid but different
evaluations are preserved with diagnostics, not silently merged or discarded.

CURRENT LIMIT: this is one captured invocation comparison, not a cross-run/context
merger. Existing S3.4.4 validation rejects mismatched candidate scope/capture/currency/
units; no acceptance of extra live context. No new verification of solver journals,
global optimum, progressive allocation via replay, or forecast accuracy. Source engine
evidence is preserved, not strengthened. Presentation contracts are internal and do
not constrain the separately authorized future FE/HTTP design.

## Demo and verification

```powershell
.venv/Scripts/python.exe scripts/demo_procurement_comparison.py --output runtime/verification/procurement_comparison/demo_output.json
```

Demo reads tests/fixtures/procurement_comparison_synthetic.json, generated offline
using canonical fixed-basket evaluation; no solver/search ran for that fixture. Manual
one-vector subset per strategy is explicitly INCOMPLETE/UNPROVEN. Generator is a
separate opt-in script, never called by demo/comparison. Other tests retain original
S344 target-met/no-pass synthetic results with their native/enumeration provenance.

Hand example: six L stock, recipes .2/.4 L per cup. LOW demand10/5, BASE20/10,
HIGH30/20. One-L packs cost2, once-per-supplier payable fee1. Captured plans0/2/4 packs
cost0/5/9. Zero→2 costs+5, BASE gains5 and2.5 cups, LOW gains0. 2→4 costs+4,
HIGH gains30/7 and20/7 cups, BASE gains0. This is scenario evidence, not a winner.
The default delta orientation follows tokens, so demo may print the inverse subtraction.

Tests/evidence and exact commands: [current verification runbook](../runbooks/FULL_TEST_FLOW.md).
No full suite, DB/fresh-session/API/economic/probabilistic accuracy claims.

## OPEN questions for API/UX (not decisions)

- Which daily details and evidence should the design show initially versus drilldown?
- Fee taxonomy/capture: which captured payable components are actually delivery fees?
- How will the customer select a plan, and which acknowledgment covers INCOMPLETE,
  UNPROVEN, target misses or grouping conflicts? No cheapest-plan auto-selection.
- Which labels/units/fractional-serving displays and delta direction suit the design?
- Cross-run/context comparison, customer-choice persistence, authorization and endpoints
  require their own reviewed contract. No new targets, safety semantics or recommendation
  policy accepted here. No next slice starts automatically.
