# S3.4.1 - Procurement design and optimization review

HISTORICAL INFORMATION: this research/specification predates the accepted engine.
Scratch observations below are historical; current implementation and runnable
verification are in [PROCUREMENT_ENGINE](PROCUREMENT_ENGINE.md) and
[the runbook](../runbooks/FULL_TEST_FLOW.md). Retired evidence is not a current gate.

Classification: CURRENT FACT / PROPOSAL / HISTORICAL INFORMATION. No procurement
production engine implemented; S3.4 is not COMPLETE. ADR-018 is PROPOSED only.
User explicitly reopened ADR-017's greedy direction; no automatic MILP acceptance.
Serving_fefo/1, old policy/package v1, S1 lifecycle and historical runs unchanged.

CURRENT FACT S3.4.2: scratch progressive/FEFO MILP and exact enumeration benchmark
now exist under runtime/s342. [Benchmark evidence](PROCUREMENT_V2.md)
supersedes this document's S3.4.1 prototype-absence statements for scratch only;
algorithm recommendation/approval gates remain PROPOSAL. No production engine.
Claim correction: evaluator has Product–Ingredient contributions and separate lot
consumption, no Product-to-lot attribution edge; do not infer dish-level lot costs.

CURRENT FACT S3.4.3: historical scratch output (retired; current implementation is app/domain/procurement/) adds candidate classification,
exact-vector exclusion and complete finite enumeration certification. See
[numeric/broader benchmark](PROCUREMENT_V2.md).
Proof belongs to enumeration, not MILP. Incomplete domains retain validated
incumbents without optimal/infeasible claims. Conservative projection false
negative recovered; old counterexample certified only within declared bounds.
No engine/policy ACCEPTED. Large topology remains UNCERTIFIED, with native
incumbent timeout observed; adoption recommendations below remain proposals.

## Recommendation for review, pending approval

Use a policy-faithful constrained optimization design, compare solver alternatives
against exhaustive small-domain references, then select engine on correctness,
quality and explainability evidence. The existing SciPy/HiGHS MILP is a credible
candidate, not a foregone conclusion. No commercial solver/dependency added.
Greedy may initialize an incumbent, never serves as an optimality certificate.

Primary candidate objective: minimum captured total purchase outlay subject to an
explicit construction-path service requirement. If no passing basket is proved
within the defined domain, optimize supported service first, then outlay, and
return a separate best_available evaluation without recommended_strategy if no
BASE pass. A deadline without proof is incomplete search, not infeasibility.
The meaning/aggregation of fallback service and construction target need approval.

Compare these alternatives:

| Objective | Benefits | Requirements/risks | Recommendation |
| --- | --- | --- | --- |
| Min outlay subject to service | Direct money objective, explainable target | Targets must refer to actual progressive/FEFO results, not ingredient proxies | Preferred primary proposal |
| Max supported service, then min outlay | Useful fallback without hiding shortfall | Common selling unit currently required; horizon aggregate can hide Product/day gaps | Preferred fallback proposal, pending exact hierarchy |
| Dish economic objective | Can reflect business value | Captured selling prices, acquisition/fee valuation and explicit economics absent; maximizing servings differs from accepted fairness | Defer until adequate data/policy |

Proposed construction target tau_k=1 on LOW/BASE/HIGH respectively is an explicit
review option, not a new default. Alternative: approved tau_k per strategy. Another
option jointly imposes final BASE/HIGH requirements, but can collapse all strategies
and changes construction intent. Recommend retaining independent construction and
reporting final BASE/HIGH eligibility separately. .95/.90 are provisional demo
thresholds, not an industry standard or calibrated uncertainty guarantee.

Hard feasibility (configured budget/MOQ/units/time/capacity) is separate from service
attainment, candidate quality, formulation optimality, forecast quality and human
confirmation of a purchase. No PO or real stock mutation follows computation.
No sum of unrelated units. Current common selling-unit rule permits horizon service
sum fulfilled / sum requested; zero requested remains UNDEFINED, target vacuous.
Alternatives needing review: per-Product/day floor, minimum normalized Product
service or weighted service with explicit business weights. No priority/margin
assumptions are silently introduced; allocation remains equal priority.

## Actual code and capture gaps

Evidence paths below are backend-relative with symbol/line:

| Data | CURRENT FACT | Minimum proposed evolution / treatment |
| --- | --- | --- |
| Pack/MOQ/price | `app/application/contracts/supplier.py:9` CreateSupplierTermInput: base-unit pack, integer minimum_order_packs, exact pack_cost | No quantity-MOQ conversion inside engine; if source MOQ is quantity, reviewed import must derive ceil(MOQ/pack) with provenance |
| Offers/time | Same contract: Store/Ingredient/supplier/version, effective bounds, active, lead days, optional shelf days | Nominal arrival=local D+1+lead under current convention; reject overflow/out-of-window with reason; calendars/supplier cap not captured |
| Scope/forecast/recipes | `app/application/contracts/decision_execution.py:195` PreparedDecisionInput, dated recipes/full Product grid | Keep captured exact intensity; no live price/calendar/shelf inference |
| Stock/inbound | Captured InventoryLotResult current balance; explicit ServingSimulationInput arrivals | Future operational lots not inbound; existing real inbound capture absent, cannot claim supported |
| Budget/safety | `app/application/contracts/decision_execution.py:175` registry only BUDGET_LIMIT/MIN_SAFETY_STOCK | Budget optional explicit unconstrained assumption distinct from unknown source budget; safety terminal-floor/expiry policy still pending |
| Delivery fees | No captured fee field | Typed source-explicit NONE / PER_OFFER / PER_SUPPLIER_ORDER and fee/currency/effective dates; absence not zero; otherwise report modeled pack spend only, not all-in budget feasibility |
| Capacity | No captured capacity/footprint fields | Explicit per-Ingredient dated quantity caps; store cap requires captured storage footprint/unit conversion. Missing required capacity blocks; optional unconfigured capacity remains NOT_ASSESSED |
| Economics | Captured Product has SKU/unit, no price; actual lot unit_cost optional | Capture reviewed Product selling price and goods/fee attribution before economic objective; missing costs remain UNKNOWN |
| Policy/audit | Old DecisionPolicy v1 fixed alpha formula; outputs serving_fefo/1 exact ratios | Future policy v2 must carry construction mapping/targets, supplier split/objective/bounds/deadline/tie settings. No old run reinterpretation |

SupplierTerm's pack_cost is not asserted to include freight. Proposed procurement
readiness must state the modeled monetary scope, fee evidence and constraint coverage.
Do not offer a purchase-ready budget guarantee with unknown payable charges.
New captured extensions/version require separate authorization; no schema changes here.

## Legacy review: actual code, not an architectural template

Accessible archive: `retired legacy review archive`, 561 entries; literal `(1)` filename
not found. Static selected-source inspection only; no legacy test/core/HTTP/DB run.
Evidence shorthand L = historical scratch output (retired; current implementation is app/domain/procurement/), included directly in review
ZIP. Preserve original `PROCUREMENT_TRIAL_PURCHASE_REPORT.md` unmodified.
Unqualified optimization filenames in the table are under
`L/shelfcash_core/optimization/`; adapter/economics/planning/FEFO paths are explicit.

| Learnable part | Limits/assumptions | Difference in new edition | Evidence / verification |
| --- | --- | --- | --- |
| Integer pack + activation/MOQ; alternative offers | Quantity MOQ ceil uses float tolerances; core permits supplier splits, no one-supplier constraint by default | New MOQ already integer packs and exact price; split choice pending | L `shelfcash_core/optimization/deterministic.py:43,338` _offer_upper_packs/constraints; static read |
| Offer filtering, nominal/calendar arrival, shelf-derived expiry | Adapter only creates order-at-first-day offers; unknown tracked shelf warns rather than strict complete purchase data | One decision-time order; no captured calendar; unknown required shelf blocks | L `model_data.py:93,194`, `expiry.py:8`; adapter `app/services/decision/adapters/procurement_adapter.py:132` |
| Budget + activated delivery fee in core | Fee per offer, not automatically one shared supplier fee; adapter does not set delivery_cost | Current fees absent; must capture explicit scope | L `deterministic.py:427`, adapter `procurement_adapter.py:132`; read request build :302 |
| Core supplier quantity/spend bounds | Adapter never passes supplier_constraints | No canonical supplier capacity; not end-to-end supported in either new snapshot or legacy adapter | L `deterministic.py:434`, adapter :302 |
| Lot/expiry buckets, post-receipt max-stock constraint | Solver buckets do not establish exact Product-serving/FEFO policy; store storage reported not_evaluated without volume metadata | New evaluator exact Product recipes/FEFO; current capacity absent | L `deterministic.py:382`, `inventory/simulator.py:318,474`; adapter :281 |
| Shortage economics and profiles | Ingredient proxy can double count dish economics; holding only when supplied; waste_term=0 despite waste_penalty profiles | No fake dish profit; quantity paths only, missing valuations UNKNOWN | L `app/services/shortage_economics.py:9`, `model_data.py:65`, `deterministic.py:511`, `strategies.py:4`; static |
| Three candidates + exact resimulation/critic | Critic rejects every non-OPTIMAL status; no post-failure repair; exact here uses floats/tolerances, Ingredient service, not rational Product fair-share | Preserve hard-valid incumbent if not optimal; evaluator must remain progressive | L `optimizer.py:26,68`, `critic.py:104,123`; no execution claimed |
| Status/probe diagnostics | Native 30s per solve; up to three new 30s probes, no shared deadline; no supplier-basket tie policy | Shared total computation budget and staged evidence needed | L `deterministic.py:478,550`, `infeasibility.py:39`; static |
| No-winner package retained | Legacy stores completed_with_no_feasible_recommendation; new S1 schema still requires winner at COMPLETED | Borrow separation intent, not old schema/API; migration deferred | L `app/services/decision_planning_service.py:204,212`; new S1 unchanged, no persistence run |

Drift found relative to report/comment: adapter docstring :36 says residuals never
optimize, but actual :234 sets optimizer_scenarios=risk_scenarios for stochastic mode
when available. Therefore report's blanket optimizer-input statement is not reliable;
actual branch must be reviewed with scenario selector to determine resulting set.
Core `model_data.py:225` gives equal candidate weights to unweighted design scenarios;
do not import them as probabilities/expected business metrics. New paths never have
probabilities. Legacy `inventory/fefo.py:17` treats not_required as never expired,
whereas new code honors any known expiry; do not port that behavior. Capacity at
receipt and no-winner storage are useful evidence, not permission to port APIs.

## Serving/solver mismatch and engine alternatives

Existing authority: `app/domain/decision/serving.py:85` allocate, :117 simulate;
`app/application/use_cases/serving.py:35`; independent invariants in
`app/application/serving_validation.py:58` do not themselves prove fairness.

1. Policy-faithful MILP: unroll at most N progressive saturation events per day,
   linearize binary-active times common fraction, require a real saturated Ingredient
   or full service each stage; exact FEFO implication constraints. Formulation below
   defines the details. Model may be large (days/paths/Products/Ingredients/lots/
   events), degeneracy/Big-M/scaling needs benchmark. Not implemented or certified.
2. Bounded exact enumeration/branch search with canonical evaluator: trustworthy
   finite-domain reference and feasible small deployments; combinatorial explosion,
   no general scale promise. Proof only when the whole admitted domain is exhausted.
3. Surrogate MILP + evaluator-constrained search: cheaper candidate generator;
   reject falsely predicted target passes, exclude exact rejected integer basket,
   repair/search within the same admitted domain/deadline. Not just resimulation.

Detailed mismatch protocol:
- Canonicalize integer basket once; exact validate prices/MOQ/scope/fee/date/capacity.
- Evaluate fixed arrivals with the same captured progressive/FEFO evaluator on all
  three paths and revalidate output; record solver predictions vs observed exact
  service and lot/capacity/expiry diagnostics.
- Hard-invalid => reject. Prediction passes but evaluator misses => not eligible;
  keep hard-valid output as possible best_available, with mismatch evidence.
- Exclude that exact basket using finite-domain no-good constraint and solve again,
  or evaluate an explicitly bounded neighborhood/joint recipe move/supplier swap.
  Repair provenance includes original vector, changed offers, spend and before/after
  service; it is a new candidate, not edited solver evidence or automatic acceptance.
- Only corrected, fully exact-validated candidates enter comparison. If no passing
  candidate before deadline, return no winner / incomplete search as appropriate;
  never announce global infeasible based on a surrogate optimum or failed repairs.
- For min-cost target search, exhausting all baskets cheaper than incumbent plus
  necessary equal-cost tie checks can certify optimality under the admitted evaluator
  domain; otherwise bound/gap is surrogate-only. A heuristic neighborhood cannot.

Toy evidence: 7.4L, A20*.2L+B10*.4L. Surrogate supplies28.5 and zero cost; actual
progressive serves27.75 (<.95*30). Excluding zero basket and buying one .2L pack
cost1 yields28.5. Full tiny enumeration finds that minimum. At 6L, max-servings LP
can serve A20/B5=25, while approved progressive is A15/B7.5=22.5. Changing policy
could improve total cups but changes fairness and Product outcomes; not proposed
as an implicit fix, would need new ADR/version/fixtures and historical handling.

## Strategies, valuation and audit

Accepted direction LEAN/LOW, BALANCED/BASE, PROTECTED/HIGH remains. Each independently
optimizes against an approved construction target; fixed baskets evaluate all paths.
No forced basket differences; record equivalence by exact offer vector and dates.
Final eligibility is BASE .95 (and HIGH .90 for both-target group), not the LOW
construction status or solver objective. No BASE pass => no recommended_strategy;
best_available requires hard validity/full evaluation, ranking still pending approval.
Selector/persistence not implemented; S1 completed-winner rule still enforced.

Expiry/ending cost unknown => UNKNOWN with affected lots, no fabricated zero.
Purchase outlay is cash spend, not COGS. Possible future economic objective:
revenue(served) - consumed attributed goods cost - expiry write-off - explicit holding
expense; classify delivery as either capitalized lot cost or period expense, once.
Do not subtract purchase outlay again if those goods are already expensed through
COGS/write-off. Ending inventory is an asset, not automatically waste. Alternative
cashflow objective and initial-stock opportunity costs need explicit accounting
policy; observed-sales proxy is not latent-demand/revenue accuracy proof.

Future typed audit fields (PROPOSAL): model/policy/formulation/solver versions,
snapshot hash, construction path/target, exact offers/pack vector/arrivals/outlay,
fee/constraint coverage and exclusions, configured/admitted bounds and proof scope,
all three evaluations and target gaps, cost UNKNOWN reasons, equivalence, recommended
and separate best_available, raw solver status/incumbent/bound/gap/nodes/options,
deadline/termination, mismatch/repair/no-good trail, exact validation status. Do not
put audit in ForecastRun.metrics_json or invent current JSON adapters.

## Approval gates / proposed S3.4.2 scope

Review before implementation: objective hierarchy/service aggregation/construction
targets; supplier splitting; fee/capacity/shelf completeness; dominance bounds vs
technical limits; exact unrolled policy model versus bounded evaluator search;
best_available ranking; tie rules, computation budget and solver extraction tolerance.

PROPOSAL S3.4.2: separate scratch policy-faithful progressive/FEFO MILP prototype and
benchmark corpus with exhaustive oracle, including full 7-day/path interactions,
fee/capacity data gaps and timeout-quality curves. No production search/selector/DB
until these gates resolve. If reviewer instead approves an explicit tiny bounded
production search, its contract and maximum domain must be frozen first. No slice
starts automatically; no MILP or heuristic engine is ACCEPTED by this document.

[Formulation](PROCUREMENT_FORMULATION.md), [goldens](PROCUREMENT_GOLDEN_CASES.md),
[evidence/rollback](../runbooks/FULL_TEST_FLOW.md).
