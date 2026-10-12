# S3.1 — Decision design and internal contracts

Classification: CURRENT FACT / ACCEPTED DECISION / PROVISIONAL POLICY / OPEN QUESTION.
Authority: ADR-017 partially supersedes ADR-016/011 policy direction; other accepted ADRs unchanged.

CURRENT FACT S3.5.1: internal pure procurement comparison is implemented, with exact
per-Product/path and Ingredient/path metrics, captured purchase/payable-fee breakdown,
compatible duplicate-plan grouping, separate targets/proofs/outcomes and signed deltas.
User's current direction is customer choice; this slice has no winner/suggested/selected
strategy, score or recommendation policy. HTTP/UX contracts will be designed separately.
No new thresholds, safety semantics or ADR acceptance. See
[comparison](PROCUREMENT_COMPARISON.md). ADR-019 remains the internal procurement
direction; older “no algorithm”/comparison-absence statements below are slice history.

CURRENT FACT S3.3: pure progressive serving + dated FEFO implemented, version
serving_fefo/1, [semantics/arithmetic](SERVING_FEFO.md). Future procurement direction
is accepted (joint discrete moves, supplier/basket constraints), no algorithm yet.
Future policy-v2 construction LEAN/LOW, BALANCED/BASE, PROTECTED/HIGH supersedes the
old formula below; existing frozen policy-v1 contracts stay unchanged for history.
No BASE-pass => no recommendation, separate best_available if hard-valid fully
evaluated; ranking details pending. Completed evaluation may retain package without
winner in a future migration, not current S1. Do not reinterpret old runs.

## Current implementation and intended pipeline

CURRENT FACT: `app/application/contracts/decision_execution.py` provides policy,
request, readiness and snapshot types; `contracts/decision_package.py` provides
output types. `app/application/decision_validation.py` exposes
`validate_decision_package(prepared, package, expected_input_fingerprint=...)`.
`app/domain/decision/validation.py` contains
pure conservation/coverage/date/ratio invariants. No domain dependency on
Pydantic/ORM/HTTP/filesystem/LLM. Pydantic remains the application boundary.
`DecisionPolicy` contains actual configuration; `DecisionReadiness` validates a
caller-supplied assessment, it does not evaluate readiness itself.

CURRENT FACT: S1 `DecisionUseCases` still persists supplied opaque fixture JSON.
It is not wired to these new validators and is not an engine bypass under a public
API (none exists). A future engine must explicitly call the new boundary and must
not expose the fixture writer as a business execution endpoint. S2 unchanged:
observed-sales forecasts, retained inputs/model metadata; no proven real-data
superiority/calibration. Only `/health` remains public. S3.2 now implements pure captured dated BOM;
S3.3 adds serving/FEFO; full Decision execution remains absent. See [BOM](BOM.md) for actual status/arithmetic.

ACCEPTED DECISION intended flow: completed captured forecast → dated recipe/BOM →
Product-preserving Ingredient demand → received stock/FEFO → fixed one-order
candidates → common evaluator on three paths → backend comparison → self-contained
DecisionRun. Human approves business action; simulation does not place a real order
or mutate inventory. What-if is hypothetical, nonpersistent by default (ADR-006).
LLM/OpenRouter may later word authorized facts; neither engine nor selectors depend
on it. No stochastic/residual/N_eff mode or probabilities are authorized here.

## Time and capture contract

PROVISIONAL POLICY v1 temporal convention:

| Event | Meaning |
| --- | --- |
| Cutoff D | Completed Store-local observed-sales day; not an instant for ordering |
| Planning | Exactly D+1..D+7; same captured Product scope as forecast |
| `order_at` | Aware instant on Store-local D+1, **before that day's trading/service** |
| `inventory_as_of` | Same actual decision instant, complete scoped current balances |
| Lead 0 / 1 | Arrival before D+1 / D+2 daily service; order date + lead days |
| Actual received_date unknown | Already received stock per ADR-010; no invented date; age warning |
| Actual received_date after snapshot local date | Excluded from available opening; never treated as a scheduled incoming order |
| Expiry X | Usable during X; unusable on X+1 |
| Hypothetical arrival shelf L | Expiry=arrival+L when known; L=0 permits arrival-day service |

`DAY_START_CAPTURE` is an explicit planning assumption, not evidence that a
timestamp was before trading. The future loader must establish that condition.
DATE alone cannot establish receipt timing within a day. Current operational lots
have no received instant, so actual current on-hand at capture is authoritative
for same-day receipt; no historical intraday reconstruction is promised.
Do not offer replay of an arbitrary past as-of from today's materialized balance.
Inventory capture must happen at the actual decision instant; no hours of gaps or
re-query after computation to synthesize provenance. If this cannot be established,
block or explicitly redesign capture in its authorized slice.

ACCEPTED DECISION daily sequence: arrivals → remove stock expired before day → FEFO
serve → close day. PROVISIONAL accounting convention: unused remainder expiring on
X is recorded once at end-X as `expired`; then X+1 opening excludes it. Earlier
expired stock is removed once on capture-day opening. `waste` is other discard,
disjoint from `expired`; combined waste reporting includes both exactly once.
No same remainder may be consumed and discarded. At end-D+7, stock expiring later
remains ending usable inventory, not asserted eventual waste.

Recipes are selected for each Product/demand date (inclusive source bounds).
Capture all versions needed across the seven dates, including known future recipe
changes. Supplier terms and purchase budget are effective at order date; their
later changes do not reinterpret the placed hypothetical order. Supplier price is
per complete pack in Store currency. No delivery-weekday/holiday/cutoff calendar
exists in canonical schema: lead is calendar days only, not an invented schedule.

Future capture uses one consistent DB snapshot, copies values then closes owned
read Sessions/transactions before calculation. Reads autobegin; do not pass that
Session to S1 writers requiring idle/clean state. No transaction/row lock through
computation. This is design, not an S3.1 implemented loader/retention transaction.

## Snapshot and missing facts

`DecisionExecutionInput`: Store, forecast run, explicit Product IDs, cutoff, order_at.
`PreparedDecisionInput`: schema version, request, timezone/currency, inventory_as_of,
forecast actual quantile values/model/version/artifact/input identity/warnings,
captured Products/Ingredients/dated Recipe lines/lots/SupplierTerms/constraints,
actual `DecisionPolicy`, typed issues, assumptions and source references.
Nested collections are tuples of frozen typed models, revalidated on entry. No
arbitrary dict survives capture; mutable caller lists/dicts detach. Dates/UUIDs/
Decimal are immutable values. Python `model_construct`/`model_copy(update=...)`
can bypass construction, so the output entrypoint revalidates both arguments.

All captured rows must be same Store; requested Products and Product/date
predictions exactly cover the scope × seven days. Units match exactly; no kg↔g
or cup↔piece conversion inferred. Policy v1 rejects mixed selling-unit aggregation.
Demo 5–10 main-menu Products is a fixture goal, not an artificial min-count validator.
Captured current Ingredient set may include unused evidence; no Product is dropped
because its inputs are inconvenient. `COMPLETE_INVENTORY_SCOPE` asserts all lots
were loaded; absent lots then represent true zero stock, not a failed partial query.

| Missing fact | Contract / future computation consequence |
| --- | --- |
| Required unit | Shape/scope rejection; future preflight DATA_BLOCKER before computation |
| Dated recipe or nonempty lines | Snapshot needs object-specific MISSING_RECIPE DATA_BLOCKER for each affected Product; no computed package |
| Tracked expiry on positive usable captured lot | MISSING_EXPIRY DATA_BLOCKER; shortage cannot be computed by pretending zero stock |
| Receipt date | Preserve null; MISSING_RECEIVED_DATE WARNING; use actually received on-hand, age analysis unavailable |
| Lot unit_cost | MISSING_COST WARNING; quantities usable, affected positive value metrics UNKNOWN, never zero |
| Supplier shelf life | Positive purchase for expiry-tracked Ingredient blocks until established; no date invention. Nontracked Ingredient may use null expiry; warning only if a needed capability is lost, not merely because an unused fact is absent |
| Supplier term | No fabricated lead/pack/cost; not necessarily blocking when zero purchase works. If purchase is necessary, future preflight blocks candidate construction, not a physical shortage claim |
| Product sale price | Not used by v1 quantity/outlay objective; no profit metric or obligatory warning |
| Absent budget/safety constraint | No invented source value; explicitly no configured constraint in captured set; budget-unlimited assumption must be visible in later demo/explanation |

Issues contain code, INFO/WARNING/DATA_BLOCKER/HARD_VIOLATION, field, affected
entities/strategy, impact and suggested action. Warnings preserve business meaning,
not raw tracebacks/credentials/transport errors. API sanitization/authorization is
future work: typed free-text fields cannot prove arbitrary caller text is safe.

## Policy, paths, BOM and numeric precision

HISTORICAL POLICY / CURRENT v1 CONTRACT (construction superseded for future policy v2 by ADR-017):
`competition_demo / 1`: BASE=.95, HIGH=.90; alpha=0/.5/1
for LEAN/BALANCED/PROTECTED; construction demand=P50+alpha*(P75-P50).
Candidate intent differs; each fixed basket is evaluated on identical LOW=P25,
BASE=P50, HIGH=P75 paths. Paths have no probabilities or cross-Product correlation
model; do not compute expected value/CVaR or label Ingredient sums P25/P50/P75.

ACCEPTED yield/loss semantics: theoretical line demand=
Product quantity*line.quantity/recipe.yield_quantity; loss-adjusted demand=
theoretical/(1-process_loss_rate). Lines describe the whole yield. Keep Product,
date, recipe version and Ingredient contribution for explanation/shared-Ingredient
fulfillment; sum only equal Ingredient units. HISTORICAL INFORMATION: no expansion
in S3.1. CURRENT FACT: S3.2 implements this pure use case, independently of strategies.

PROVISIONAL arithmetic: Decimal only, 50 significant digits/ROUND_HALF_EVEN with
an owned context for division and service ratios; service validation uses Python
Decimal MAX_EMAX/MIN_EMIN exponent bounds, independent of ambient context. All future calculators must use
the same explicit policy; do not round after every term arbitrarily. Exact finite
input scale is retained; no binary float/bool accepted, no cents/integer-serving
rounding. Rational conservation/multiplication checks ignore ambient context.
CURRENT FACT S3.2: rational contributions rounded once at precision50, exact sums
of exported contributions with expanded precision and explicit numeric blockers
([BOM](BOM.md)). HISTORICAL S3.1 design required disclosing
division rounding: arbitrary rational division can repeat; “exact Decimal input”
does not promise infinite exact rational output. Currency settlement outside scope.

Safety stock: PROVISIONAL terminal floor once, demand + floor − ending usable
availability, not both per-day protection multiplier and extra hidden buffer.
Retain dated safety values through the window; use end-D+7 effective floor in this
proposal. Insufficient budget/service may miss floor with explicit outcome, not
fabricated feasibility. Reviewer must confirm within-window changes/expiry treatment.

## Serving algorithm -- ACCEPTED ADR-017, CURRENT FACT S3.3

Global same-day proportional rule r=min(1, available_i/full_requested_i) can underuse
stock: A requests 10 cups needing shared S and exclusive E (1 each); B requests
10 cups needing S only. S=20,E=0 ⇒ global r=0 ⇒ serves nothing, although B=10 is
possible. The rule is not accepted as the simulator.

ACCEPTED provisional ADR-017 and implemented S3.3: progressive proportional filling of active
Products. Start each fulfilled=0. Increase all active Products by the same fraction
of their requested quantities until one Ingredient saturates; freeze only Products
using that saturated Ingredient, continue unaffected Products with remaining stock.
Zero-capacity E freezes A immediately; B reaches10. S=15,E=5 yields A=5,B=10,
consuming S=15,E=5; no ingredient-sum double counting of lost dishes. Fractional
servings are planning quantities, not physical half-cup delivery.

Stop when all requests met or no active Product can grow; at least one Product
freezes per saturation event. Deterministic equal-saturation handling freezes all
affected Products; display order by SKU then UUID is only a tie for presentation.
Allocate each chosen Ingredient consumption to available lots by expiry ascending,
unknown expiry only when nontracked, then received_date (known first), then lot ID.
No inaccessible/expired lot. Consumption totals must match dish BOM consumption.
Tradeoff: simple max-min-style proportional fairness, not revenue optimization or
max-total-servings proof. Different recipe intensities may sacrifice total cups.
CURRENT FACT: S3.3 implements this serving/FEFO foundation. Full candidate
evaluation, valuation and recommendation are absent. Exact rational state with
Decimal views is documented in SERVING_FEFO; old rounded-view packages are not reused
as exact allocation state.

## Procurement and budget -- ACCEPTED future direction / pending specification

ADR-017 approves discrete basket marginal heuristic with joint activations and
supplier offers evaluated jointly with pack/MOQ/budget/arrival/expiry. No cheapest-
unit-cost lock before basket comparison. The historical alternatives below are
review context, not the new accepted search algorithm; exact move/tie rules pending.

One order, one chosen effective supplier term per Ingredient in v1. HISTORICAL
supplier priority proposal (superseded as a preselection rule by ADR-017): offers that can actually arrive before required service and
have established required shelf life; compare delivered unit cost pack_cost/pack
size, then earlier arrival, then Supplier SKU/name if captured, lastly stable ID.
Canonical schema has no Supplier SKU; future capture must copy a business label if
used. ID is a tie after business criteria, never an allocation-benefit priority.
No source calendar or replenishment invented. Arrival/expiry must be modeled per
day; cannot buy seven-day total when a short-lived pack can only serve two days.
Pack rounding `ceil(raw_need/pack_size)`, activate minimum packs only if raw_need>0;
zero order exempt from MOQ. Pack excess is explicit, never manufactured demand.
Three identical baskets remain three strategy candidates with `equivalent_to`.

Budget-short candidates must stay within known budget and report unmet service;
hard-invalid proposed baskets cannot be chosen. Two small allocator alternatives
were reviewed as historical alternatives, neither implemented here:

1. **Whole-MOQ admission**: compute each Ingredient's needed basket, admit complete
   required MOQ activations in descending BASE cups unlocked per activation outlay;
   then buy needed packs, stopping at target or budget. Must evaluate shared-recipe
   complementarity; simple isolated Ingredient benefits can all be zero. Cheap but
   order sensitive; no global optimum claim.
2. **Discrete basket marginal heuristic**: start with existing stock and zero order;
   admissible moves are one extra pack for an activated Ingredient or its entire
   MOQ for an inactive Ingredient. Include minimal joint recipe Ingredient activation
   when otherwise every single move has zero benefit. Re-evaluate BASE fulfilled
   Product cups over D+1..7 using the same simulator; benefit=incremental fulfilled
   cups / incremental outlay. Free improving moves first; then highest benefit,
   higher absolute added cups, lower added outlay, Ingredient business label then ID.
   Move must fit budget, shelf/arrival and remaining construction-demand bounds.
   Stop at targets, no improving affordable move, or finite needed-pack bounds.
   ZERO improvement never justifies extra stock; no unbounded zero-cost purchases.
   All strategies use the same rule but their construction paths differ.
   More evaluation work; joint move enumeration may grow with recipe size. Not a
   solver, not globally optimal, and no implementation/optimality proof.

Golden G08 makes these costs concrete. Direction is approved by ADR-017; detailed
search/termination/tie behavior still needs specification before procurement slice.

## Metrics and recommendation design

All metrics cover inclusive D+1..D+7. Purchase is the one decision-time basket cost.

| Metric | Definition / unit / missing semantics |
| --- | --- |
| Purchase outlay | Sum packs*captured pack_cost, Store currency, known for canonical order lines; not cost of goods sold |
| Requested/fulfilled/lost | Per Product/day selling quantity; lost=requested−fulfilled; common-unit overall sum only in v1 |
| Service | Sum fulfilled / sum requested per path, ratio at policy precision; zero requested ⇒ UNDEFINED/null/reason |
| Ingredient consumption | BOM for actually fulfilled Product amounts, per Ingredient base unit, lot attribution by future FEFO |
| Ingredient shortage | max(full requested BOM − available usable quantity after arrival/pre-service expiry,0), per Ingredient/day diagnostics; cross-Ingredient blocking can leave usable stock unconsumed; NEVER summed into lost Product counts |
| Expired / other waste | Disjoint daily Ingredient quantities; value via actual used lot cost when all affected attribution known, else UNKNOWN/null/reason |
| Ending usable | Post-close D+7 quantity by Ingredient; cost attribution only if established, else UNKNOWN; unexpired stock is not waste |

Service target with zero demand is vacuously satisfied, while the metric remains
undefined. Lost-sales forecast is observed-sales proxy, not reconstructed latent
demand or realized revenue/profit. Missing selling price does not enable fake profit.

PROVISIONAL selection hierarchy: exclude data-blocked/incomplete/hard-invalid
candidates first. All nine evaluations must finish. Group 1 both BASE>=.95 and
HIGH>=.90; group 2 BASE passes but HIGH misses; group 3 BASE misses regardless HIGH.
For group 1 or 2: lower outlay, then lower supported BASE-path horizon combined
expiry/other-waste value **only if both compared values known**, then LEAN/BALANCED/PROTECTED.
If a group contains any unknown waste value at tied outlay, skip waste across that
tie cohort and use stable order, avoiding non-transitive pairwise comparisons.
The BASE tie metric is a provisional design choice, not an implemented selector or
average/expected waste across the three paths. Copy it into the actual producing
policy configuration when that separately authorized selector is implemented.
No weighted hidden score; unknown cost is not “better” than known cost.

When no candidate meets both targets, group2 produces BASE_ONLY with explicit high
miss; when no BASE pass, TARGETS_NOT_MET with comparison evidence, not a default
BALANCED or feasible target claim. ACCEPTED ADR-017: no winner in group3; separate
best_available only for complete hard-valid evaluations, exact ranking pending.
CURRENT v1 contract still permits an explicitly evidenced degraded winner; it is a
historical supplied-output boundary, not the accepted future selector policy. Future
policy-v2 wiring must tighten this deliberately, not silently reinterpret v1. All hard-invalid ⇒ HARD_INFEASIBLE
with no winner. Source blocker ⇒ DATA_BLOCKED with no computed candidates. Unfinished
evaluation ⇒ EVALUATION_INCOMPLETE, no recommendation.

CURRENT FACT validation proves supplied coverage, unit/identity/quantile alignment,
quantity conservation, order pack/cost/budget/arrival, initial/connected balances,
fixed arrivals, metric totals/ratios and eligibility/service group. It does **not**
prove supplied BOM numbers equal expansion, correct FEFO lot attribution, expiry
depletion, candidate optimality, actual before-trading capture, or cost attribution.
Without lot-level cost attribution the validator conservatively requires UNKNOWN
for positive waste/ending value whenever captured usable stock has unknown cost,
even if a future engine could establish that only known-cost lots remain. This is
an explicit contract limitation to revisit with real lot-allocation evidence.
No recommendation ranking function is implemented; known zero waste from a supplied
fixture is not empirical waste evidence. Future engine tests must prove these gaps.

## Versioned identity, replay and API intent — design only

PROPOSAL serialization identity v1: canonical JSON UTF-8 sorted keys, compact,
no NaN/float; UUID lower-case hyphenated, dates ISO, aware instants normalized UTC,
Decimal exact plain string with equivalent scale/trailing-zero and signed-zero
normalization (as forecast v1). Canonical array order: Products/Ingredients/rows
by IDs, forecasts day+Product, recipes by Product/version/ID and lines Ingredient,
terms Ingredient/Supplier/version/ID, constraints kind/scope/effective/version/ID;
issues and source references by all their typed fields, assumptions sorted unique.
Duplicate business keys reject, never resolve by arbitrary order.

Input digest preimage prefix `shelfcash-decision-input:v1\n` plus canonical content:
request Store/forecast/cutoff/scope/order instant, timezone/currency/as-of, complete
forecast values and actual model/input/artifact/warnings, Products/Ingredients,
dated recipes, lots, dated terms, constraints, assumptions/source refs/issues and
actual policy values/version. Policy identity separately hashes canonical policy
under `shelfcash-decision-policy:v1\n`. Algorithm identities belong in output;
changing the forecast model changes captured forecast provenance, not procurement
algorithm identity. Exclude new DecisionRun UUID, wall-clock recording timestamps,
output and live rows. Inventory_as_of/order_at **are** business inputs, not discarded
audit timestamps. Fingerprints nonunique, never Python hash/security/dedup claims.

No hasher, JSONB retention, integrity loader or replay executor is implemented by
S3.1. `expected_input_fingerprint` is checked by equality against a trusted future
adapter; caller-supplied digest is not proof of integrity. S1 opaque snapshot remains
unchanged; future adapter persists actual typed snapshot/package in its existing
columns only after validating. Same-input rerun gets a new UUID. Future replay must
use captured values/policy/algorithm version, never current mutable operational facts.
Algorithm availability/version replay support still requires explicit acceptance.
Do not place decision provenance in ForecastRun.metrics_json.

ACCEPTED future direction ADR-017: completed evaluation may persist without winner
and keep its package. Migration/lifecycle wiring deferred; current S1 DB COMPLETED requires a
non-null recommended_strategy; FAILED forbids an output package. Typed v1 allows
no winner for DATA_BLOCKED/HARD_INFEASIBLE/TARGETS_NOT_MET/EVALUATION_INCOMPLETE.
These are internal business outcomes, not presently persistable as completed S1
runs. Do not disguise a hard/data-blocked plan as a winner to satisfy that CHECK,
or claim failure recording retains a full evaluation package when schema forbids it.
A separately authorized lifecycle/schema evolution must preserve historical runs
and separate execution status from business outcome. S3.3 implements no migration. This does not
block a pure BOM slice; it does block claiming full end-to-end DecisionRun semantics.

Future API intent, **not** accepted paths: authorized execution/read returns version,
snapshot/model/policy identities, all three fixed baskets, three-path daily Product/
Ingredient outcomes, comparable metrics/status/null reasons, warnings/blockers,
recommendation evidence and whether result is hypothetical. Public schema, error
sanitization and minimum actor authorization require a separate authorized slice.

## Verification / next scope

Unit tests validate actual contracts, not a fake simulator. Fourteen golden
specifications in DECISION_GOLDEN_CASES are hand-derived future engine acceptance.
S1 PostgreSQL lifecycle regressions provide fresh-session compatibility evidence.
Commands/results/rollback in historical scope notes (retired); historical S2 test counts not new runs.

CURRENT FACT S3.2: authorized pure dated BOM implemented and targeted verified;
[arithmetic/contract](BOM.md), [task notes](../runbooks/FULL_TEST_FLOW.md). No input loader.
BOM subsets of goldens are executable; simulator/selection specs remain unverified.
CURRENT FACT S3.3: pure serving/FEFO foundation implemented and targeted verified.
See SERVING_FEFO and historical scope notes (retired). ADR-017 accepts future procurement/no-winner
direction; detailed specification/wiring deferred. No next slice starts automatically.


CURRENT FACT S3.4.1: user reopened the earlier discrete marginal heuristic engine
choice; the algorithm discussion above is HISTORICAL direction under review, not
an engine selection gate that overrides the new task. Serving/FEFO, construction
mapping and no-winner intent are unchanged. Procurement remains unimplemented.
[Procurement design](PROCUREMENT_DESIGN.md),
[formulation](PROCUREMENT_FORMULATION.md), [goldens](PROCUREMENT_GOLDEN_CASES.md)
and PROPOSED ADR-018 compare alternatives; no new policy is ACCEPTED here.
