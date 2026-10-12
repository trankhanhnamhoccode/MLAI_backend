# Procurement/2 + comparison/2 + selector/1

CURRENT FACT — S3.6.1 internal snapshot-only slice. Authority:
[ADR-020](../adr/ADR-020-product-requirements-procurement-selector.md) and accepted
API policy v1. Not an implemented HTTP C01/C02 or persisted DecisionRun feature.

## Typed entrypoints and versions

```python
execute_procurement_v2(request: ProcurementInputV2, search_factory) -> ProcurementResultV2
evaluate_basket_v2(request: ProcurementInputV2, counts: tuple[int, ...])
compare_procurement_v2(source: ProcurementResultV2) -> ComparisonV2
select_winner(comparison: ComparisonV2) -> WinnerSelection
```

Inputs carry detached PreparedDecisionInput with explicit capture_version=2,
ProcurementPolicyV2 and EffectiveRequirements(paths, provenance). Each path has
minimum ratio and Product replacement overrides. Paths must be nonempty/unique,
overrides unique/in-scope; float/bool/nonfinite/negative/>1 are rejected. Ratios
use 0..1, not API percentages. Rules declare the three 100% construction targets.
No customer defaults or saved lookup are hidden in the engine. Public boundaries
revalidate copied/constructed instances and all nested containers are tuples/frozen
types. Captured forecasts/recipes/stock/terms are the only business inputs.

Original procurement/1/common-unit aggregate/DecisionPolicy v1 remain separate.
capture_version=1 retains its single selling-unit restriction; capture_version=2
uses independent Product denominators and exact units. Old operational pipeline
still uses /1; there is no automatic routing of old capture to this new engine.
Old DecisionPackageV1 rejects capture 2; old identity tokens remain compatible.

## Exact business ranking

For each Product/path, requested and fulfilled are exact sums over D+1..D+7.
Customer condition is fulfilled >= requested × effective minimum, where an
override replaces that path's common minimum. Requested zero is nonbinding;
ratio is None, not 1. Do not add cup and piece to build service ratio.

LEAN constructs LOW100% each Product; BALANCED BASE100%; PROTECTED HIGH100%.
Within customer-pass candidates, prefer construction-pass, minimizing exact
purchase + explicitly declared payable fees. If construction cannot be attained
among evaluated facts, fallback maximizes minimum Product construction-path ratio,
then equal-weight mean, then minimizes money, then stable basket. Zero-demand
Products are omitted; no positive demand skips service objectives.

All candidates still obey integer packs/MOQ, budget, captured arrival/expiry,
one-order supplier constraints and gross post-receipt/pre-expiry/pre-consumption
capacity at exact units. FEFO and progressive serving have not been changed.
Unknown configured fees/budget and captured blockers prevent computation.

StrategyResultV2 separates execution, selection_kind, customer/construction pass
and per-Product gaps, feasibility, proof/search completeness, solver and journal.
construction_feasibility is JOINT customer+construction. Customer-fail references
are REFERENCE_NOT_RANKED: no best_available claim. A technical error preserves
previous exact candidate/evidence and ERROR status. A search limit is INCOMPLETE,
not NO_PASS_CERTIFIED. FINISHED can still be UNPROVEN.

Selector ranks only exact/hard-valid, customer-pass, blocker-free candidates:
money first, then minimum Product HIGH, BASE, LOW ratios, then stable basket.
Zero-demand paths are neutral. Null winner means no eligible evaluated option;
it alone does not certify infeasibility. Winner is recommendation, not customer
confirmation, PO or purchase mutation. Exact candidate can remain eligible despite
source ERROR/INCOMPLETE; source errors are retained, never converted to success.

Comparison groups equivalent captured plans AND complete exact evaluations. Each
strategy binding and source result retain termination/proof/error separately.
Different suppliers/arrivals/fees/context/provenance must not collapse. Comparison
retains Product/Ingredient facts, signed deltas and generic fee breakdown; delivery
fees stay None unless captured taxonomy supports them. API delivery taxonomy is OPEN.

## Native formulation, numeric limits and proof

Reuse the existing progressive-serving/FEFO physical MILP equations. Every stage
includes customer Product/path rows. TARGET adds construction 100% rows and money
objective. FALLBACK_MIN uses z <= served/requested for each positive-demand Product;
FALLBACK_MEAN maximizes equal-weight normalized mean; FALLBACK_COST minimizes money.
Freeze EXACT incumbent minimum/mean lower bounds, not floating surrogate levels.
Exact reject is journaled and excludes only its integer vector. Construction miss
in TARGET must remain available to fallback. No surrogate total-servings objective.

Canonical evaluator uses exact Fraction facts; Quantity stores numerator/denominator
and a deterministic Decimal view under existing numeric bounds. Customer target
Decimal remains exact, including digits beyond display precision. No epsilon turns
a shortfall into pass. Numeric admission/projection failure is NUMERIC_UNSUPPORTED;
native OPTIMAL/infeasible and floating gap are never exact certificates.

Optional bounded exact enumeration checks every captured pack vector, including
hard-invalid vectors, ranks independently of native status, and certifies ONLY that
finite domain. Partial enumeration stays UNPROVEN. No large unbounded enumeration.
Large-domain native ranking is best among observed exact candidates, not guaranteed
global optimum. Re-search iteration cap and deadline are explicit; no-pass within
search limits remains UNKNOWN. Unproved min/mean stages do not gain certificates
by moving to later native stages.

One engine cooperative deadline covers build/search/cache/exact/result validation.
Remaining time divided equally among remaining strategies; completed cache entries
shared. Validation/native/model building cannot always be preempted; elapsed and
overrun are measured after result reconciliation. Comparison/selector then revalidate
outside engine deadline. Large source outputs can be costly: benchmark measures
the additional time; hard wall-clock cancellation is not implemented.

## Hand examples / executable evidence

- Demand Products [2,8], two packs total, unit costs1: fallback [1,1] has minimum
  1/8, beating [2,0] minimum0 even though the latter's mean is higher.
- Add third Product with demand1 and no purchasable Ingredient: minimum pinned0;
  fallback [2,0] maximizes equal mean1/3 before the cheaper [1,0] mean1/6.
- BASE requested1, pack0.1, requirement0.300000000000000000000000000001:
  packs3 fails exactly; native re-search returns packs4, no tolerance pass.
- Demand [2cup,4piece], budget3, BASE common1 with second override.25 and HIGH.25:
  basket [2,1] customer-pass but BASE construction-miss; still eligible.
- Zero demand/budget0 gives packs0, service None, all three sources grouped, valid
  winner. Separate forced native search limit without incumbent yields UNKNOWN.

Tests use hand outputs and an independently authored itertools search/ranking oracle,
while sharing the canonical exact fixed-basket serving evaluator (not an independent
simulator). Fault-injection cases isolate error/timeout/selector behavior; those are
explicitly not evidence of real native timeout or real-data quality. See task notes
for exact commands and benchmark report for actual measurements.

## Limits / next work remains PROPOSAL

No HTTP/wire parser/default/saved resolver, DB capture upgrade, retained DecisionRun,
schema/migration, auth, customer choice/ordering, Optuna or real-data assessment.
No profit objective, stochastic path probabilities, changed serving priorities or
hidden requirement relaxation. Safety-stock semantics remain unsupported/blocking.
Any next integration/persistence/API slice requires separate authorization and must
resolve S1 no-winner lifecycle, fee taxonomy and effective-policy capture explicitly.
