# S3.3 - Pure progressive serving and dated FEFO

Classification: CURRENT FACT for implementation; ACCEPTED DECISION for user-approved
provisional serving semantics (ADR-017). Future procurement/selection is separate.

## Pure entry point and scope

```python
simulate_serving(request: ServingSimulationInput) -> ServingSimulationResult
```

Input contains revalidated immutable PreparedDecisionInput plus explicit typed
HypotheticalArrival records. Captured Store/Ingredient/unit, unique noncolliding
lot IDs, horizon dates, expiry order and exact Decimal quantities are checked.
Copied/constructed models cannot bypass revalidation. The unchanged S3.2 expand_bom
validates full Product/date coverage and inclusive recipe graph first. Result retains
its BOM output and complete canonical snapshot, identities, warnings and assumptions.
No live facts, DB, files or providers are read by computation. Domain is plain Python.

ServingSimulationResult version serving_fefo/1 contains typed ProductServingDay,
FulfilledContribution, IngredientServingDay and LotServingDay tuples. COMPLETE means
this foundation computed, not full Decision readiness; readiness is NOT_ASSESSED.
Any known captured/new DATA_BLOCKER yields DATA_BLOCKED with no serving rows; BOM
may still be COMPLETE. Numeric failure => ARITHMETIC_BLOCKED, no partial rows, preserved
input/BOM/issues. Unexpected programming errors propagate, not business success.
Quantity views are not physical integer serving or settlement amounts.

## Allocation and conservation

Per path/day, exact demand and dated recipe intensity = line/(yield*(1-loss)).
Start fulfilled=0. Active positive-demand Products all increase by the same fraction
of original requested amounts. For each Ingredient compute active demand-rate;
step=min(remaining common request fraction, remaining capacity/rate). Freeze the
union of active Products using any simultaneously saturated Ingredient. Continue
unaffected Products; zero-capacity bottlenecks freeze affected Products immediately.
Zero requests remain fulfilled/lost zero. No menu-wide min ratio, priority, profit,
integer rounding, safety/pack/MOQ/budget changes. This is proportional fairness,
not proof of maximum total servings or revenue.

Requested=fulfilled+lost per Product. Consumption is exact dated BOM of fulfilled
amounts, attributed by Product/recipe/Ingredient and separately by consumed lots.
Ingredient shortage=max(full requested BOM-available before serving,0) is a distinct
diagnostic, not added across Ingredients into lost servings. Complementarity may
leave some Ingredient unused despite unmet Product demand.

## Dated stock/FEFO foundation

Each LOW/BASE/HIGH has independent local balances. Daily order:
explicit arrivals -> pre-service expired removal -> serving -> FEFO -> close.
Expiry X usable in X; remaining quantity disposed once at close X. Already expired
captured lots disposed before first service. Expired and other waste are separate;
other_waste is always zero in this foundation (no other disposal policy implemented).
Ending usable stock is not waste. Process loss is already included in gross recipe
consumption through 1/(1-loss); it is not added again to other_waste.

FEFO sorts known expiry ascending, unknown expiry last (allowed only nontracked
usable positive stock), then known received_date ascending, unknown receipt last,
stable UUID. Unknown dates remain unknown in provenance. Required missing-expiry
blockers and receipt/cost warnings follow unchanged S3.1 rules. No cost valuation
or inferred age. Even unrelated captured blockers stop serving computation.

Actual captured lot received_date > Store-local capture day is excluded throughout
the horizon and emits FUTURE_RECEIPT_NOT_INBOUND. It never turns into scheduled
stock. Unknown receipt is usable as captured current balance with its warning.
Hypothetical arrivals are explicit, same-scope in-window quantities; expiry is
explicit, not inferred from supplier terms. Positive tracked arrivals with missing
expiry add MISSING_ARRIVAL_EXPIRY blocker. No supplier/order/cost policy is implied;
these are hypothetical inputs, no DB movements. Arrival lot rows exist throughout
the horizon, with zero balance before arrival. Excluded actual lots have no flow rows
but remain in captured provenance.

Lot daily invariant: opening+arrivals=pre_service_expired+consumed+close_expired+
other_waste+ending. Ingredient consumption equals Product contributions and summed
lot consumption. No negative balances/overconsumption; stock carried exactly to
the next date. All captured Ingredients have state rows, including unused stock;
unused Ingredients have zero requested/consumed, not synthetic demand.

## Numeric contract serving_fefo/1

Exact Fraction state throughout allocation, intensity, consumption and balances.
Output Quantity has canonical nonnegative numerator / positive denominator **strings**
and decimal_view. The ratio is the authoritative business quantity; Decimal is a
one-way display at precision50/ROUND_HALF_EVEN, MAX_EMAX/MIN_EMIN, with owned traps
and context. Display never drives subtraction or saturation. Signed display residual
is exactly Fraction(numerator,denominator)-Fraction(decimal_view); no epsilon or
unreported balancing adjustment. For 1/3 served *3g, consumption is exactly 1g even
when display shows fifty threes. Independent display sums need not reconcile;
consumers must use ratios for exact checks. Do not multiply rounded serving views
by rounded BOM rows and claim exact conservation.

S3.2 dated_bom/1 outputs stay unchanged: rational contributions rounded once and
exact aggregates of exported Decimal rows. Serving computes exact fulfilled-BOM
state from the same captured recipe semantics, not those rounded demand totals.
Both versions retained explicitly; their finite displays can differ by rounding.

Technical limits: maximum 1000 digits in exact numerator/denominator; Decimal source
coefficient and absolute exponent checked before rational expansion. A larger
intermediate exact intensity/state can block even if a later expression would cancel.
Capacity, nonfinite/underflow/overflow, or existing Pydantic finite-number display
range failure yields SERVING_NUMERIC_BOUNDARY and no partial output. Not a demand
quality threshold or silently fabricated zero. Public input nonfinite/float/bool
errors are validation errors. Numeric issue covers the captured Product scope;
this version does not diagnose the exact failed path/day, a diagnostic limitation.

## Manual verification and evidence

From backend/, with the existing environment:

```powershell
./.venv/Scripts/python.exe -m scripts.demo_serving_fefo
```

SYNTHETIC example: 6L milk, A20*.2L, B10*.4L => BASE day1 A15, B7.5; lost5/2.5.
Output includes exact 15/1 and 15/2 and semantics version; no DB needed. The same
input can be changed locally and revalidated; no live facts are loaded. Other hand
assertions: S20/E0 => A0/B10; S15/E5 => A5/B10; FEFO G04 consumes6/expires4;
1g stock with 1/3g intensity carries ending2/3,1/3,0 over three days.
See tests/unit/test_serving.py and [task notes](../runbooks/FULL_TEST_FLOW.md).

## S3.3.1 - CURRENT FACT: independent output validation

Same fields and serving_fefo/1 version; policy unchanged. Row validators enforce
exact Product requested=fulfilled+lost, Lot conservation/zero other_waste and
Ingredient shortage/capacity. Aggregate validation in
`app/application/serving_validation.py` checks:
- Complete unique Product/contribution/eligible lot/Ingredient path/day grids,
  including explicit zero rows; captured identities, units, dates and recipe IDs.
- Requested matches the captured path quantile; contributions equal exact fulfilled
  times dated whole-yield/loss recipe intensity, not rounded BOM totals.
- Initial operational openings, explicit arrivals, pre-arrival zeros, path-local
  day continuity, pre-service expiry, expiry-X close disposal once and usable ending.
- Product contribution totals equal Ingredient and lot consumption; requested BOM,
  available, expired, other_waste, ending and shortage reconcile independently.
- Direct FEFO attribution: no later lot consumption while an earlier usable lot has
  remaining stock before close. No second allocator or simulation is run.
- Input/BOM retained snapshots agree; captured and BOM issues preserved, excluded
  future-lot warning and required arrival-expiry blocker retained. COMPLETE has no
  blockers/full rows; blocked output cannot contain partial serving rows. Numeric
  status requires numeric evidence; invariant violations are validation errors,
  never repaired into zero/COMPLETE or reclassified as numeric computation success.

`ServingSimulationResult.model_validate(...)` / `model_validate_json(...)` revalidate
nested copied/constructed models. As with existing Pydantic contracts, model_copy /
model_construct alone deliberately bypass validation; consumers must revalidate
before trusting such objects. The producer constructs validated result automatically.
No shape change; output JSON schemas equal the previous S3.3 bundle.

All business checks use bounded canonical ratios via unchanged exact()/checked(),
never decimal_view/float/epsilon. Canonical source aggregation order avoids changing
capacity behavior when rows are permuted. Existing 1000-digit technical limit is
unchanged; valid 1000-digit denominator and 1E+300 outputs pass. No new numeric
intermediate rejection found in exercised valid cases; arbitrary untested extremes
are not guaranteed. Invalid output is refused, not rewritten.

Limits: does not prove progressive fairness, global optimality, source authenticity
or DB persistence/full Decision readiness. Input and retained BOM snapshot agreement
is coherence, not a cryptographic/authorized-capture proof; matching edits to both
snapshots cannot be authenticated by this validator. It does not recompute or fully
validate standalone S3.2 BOM output arithmetic. Pure computation/algorithm tests
remain necessary. A conserving A10/B10 allocation for the milk input is deliberately
accepted here, while the actual simulator still produces the policy's A15/B7.5.
Exact equality of Ingredient/Product quantities does not infer lost servings by
adding shortages across Ingredients.

Tests: tests/unit/test_serving_output_validation.py, plus unchanged producer/BOM/S3.1
regressions. [S3.3.1 task notes](../runbooks/FULL_TEST_FLOW.md) record commands/results,
rollback and packaging; no full suite or PostgreSQL result claimed.

## Future accepted directions and limits

ADR-017 approves future LOW/BASE/HIGH strategy construction, discrete basket marginal
heuristic with joint activations and supplier-basket evaluation, and completed
evaluation without recommendation when no BASE pass. None is implemented here.
Prepared policy v1 / package-v1 validator / S1 lifecycle remain historical boundaries;
future policy-v2 and no-winner migration/wiring must not reinterpret them.
Pending: heuristic search/tie rules, best_available ranking, safety-floor treatment,
policy-v2 API/contract, no-winner persistence details, capture/retention/replay, cost
valuation and full recommendation. No full Decision-ready or global optimality claim.
