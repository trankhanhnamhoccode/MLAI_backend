# S3.1 — Hand-calculated golden specifications

Classification: PROVISIONAL POLICY / PROPOSAL, future engine acceptance fixtures.
These fourteen cases are **not executed simulator tests**. HISTORICAL INFORMATION:
S3.1 verified only contracts/validation. CURRENT FACT S3.2 tests actual pure BOM:
G01 yield/loss, G09 missing recipe, G12 zero demand, G13 shared design-path totals,
and the captured-only calculation portion of G14. See `tests/unit/test_bom.py` and
[BOM](BOM.md). Procurement/FEFO/serving/ranking/persisted replay portions of those
cases and all other simulator specifications remain unverified. Arithmetic
below is hand-derived. CURRENT FACT S3.3: G04 quantitative FEFO and G07 progressive
serving are executable in tests/unit/test_serving.py, plus captured-serving portions
of G01/G05/G09/G12/G14. Supplier/procurement/valuation/selector/persisted replay
portions remain unverified. ADR-017 supersedes old OPEN serving/no-winner directions. Where allocation is OPEN QUESTION, show alternatives rather
than treating one as accepted. No fake engine outputs prove these cases.

Common context unless overridden: one Store, VND, selling unit cup; Ingredient
base units explicit; D=2026-10-07 local, day1=Oct08 through day7=Oct14; decision
before day1 trading; one order only; absent budget explicitly unconstrained; no
configured safety floor. Shelf/expiry dates are stated facts or explicit known
supplier shelf derivations; no made-up source data. Paths are design demand paths,
not scenario probabilities. Each valid future package carries all strategies and
all three path evaluations, even when baskets identical. Fractions below are exact
mathematical expectations; serialized ratios use policy precision50/HALF_EVEN.

## G01 — Normal week, whole-yield recipe and loss

Input one tea Product; each day P25=P50=P75=8 cups. Recipe yield10 cups, line100g
tea, loss=.20; current stock0; pack100g/cost100VND/MOQ1/lead0, nontracked stock.
Theoretical per day=8*100/10=80g; gross=80/(1-.20)=100g, week700g.
Expected seven packs/700g/outlay700, arrivalday1; serves56cups, lost0, service1,
consumes700g, waste0, ending0. All strategies identical, record equivalence.
Incorrect shortcuts line100g per cup or apply loss twice must fail future BOM tests.

## G02 — Enough inventory and zero order vs MOQ

Demand2cups/day, each1g; stock20g, expiryday10, unit_cost2VND/g; supplier pack10g,
MOQ3packs. Weekneed14g; order0packs/0g/outlay0, MOQ not violated. Serves14, lost0,
ending6g/value12VND; not waste. All strategies' zero orders equivalent. Explicit
zero purchase is not a missing supplier quantity and does not require activating MOQ.

## G03 — Pack rounding and activation

No stock; required usable need83g, pack10g/cost20/MOQ2 ⇒ ceil83/10=9packs,
90g/outlay180, excess7g. Separate need5g ⇒ ceil=.5→1pack but MOQ2 ⇒20g/outlay40,
excess15g. Need0 ⇒0packs, not20g. Orders never contain .5packs. Excess is inventory
or eventual expiry outcome, not counted as consumed demand. Known budget39 cannot
fund MOQ2; must return within-budget zero order/unmet demand rather than 1pack.

## G04 — FEFO, expiry X inclusive and one-time disposal

Stock A=4g expiryday1, B=6g expiryday3; 1g/cup. Day1 demand3, day2 demand3,
later0. No order. Day1 consume A3; A remainder1 expired at end-day1. Day2 consume
B3; B remainder3 survives through day3 service (zero demand), expires end-day3.
Totals requested6/fulfilled6/lost0, consumed6g, expired4g, otherwaste0, ending0.
10=6+4. A is never usedday2; expiry waste not counted again at day2 opening.
If both lot costs2, combined wastevalue8. Unknown affected cost ⇒ UNKNOWN, not0.

## G05 — Lead time and early shortage

Demand2cups/day,1g/cup; stock0, pack1g/cost1/MOQ1/lead1, expiry beyondhorizon.
Order at day1, arrivalday2. A 12g basket serves six remaining days, fulfills12
of14, loses2 on day1, service6/7≈.8571428571. No quantity can serve day1 before
arrival; ordering14 would leave2g unused, not repair early shortage. Lead0 would
arrive day1 and permit14/14. No imaginary order at end-D or replenishment later.

## G06 — Short shelf life under one order

Demand2cups/day,1g/cup; stock0, pack1g/cost1/MOQ1/lead0, known shelf_life_days1.
Arrivalday1 expiryday2 inclusive. A sensible bounded basket4g serves4cups in days1–2,
lost10 in days3–7, service2/7, ending0. A14g aggregate-week purchase consumes4g,
expires10g at end-day2: do not purchase that certain unused total as “protected”.
No hidden day3 replacement. If pack/MOQ forces5g, report unavoidable1g expiry,
not manufactured fifth serving. Confirm bounded candidate rule before procurement.

## G07 — Shared Ingredient and exclusive shortage

One day A requests10cups, each S1+E1; B requests10cups, S1only. S20,E0.
Global proportional r=min(20/20,0/10)=0 ⇒ serves A0,B0, lost20 despite B service
capacity10. This counterexample rejects a global menu ratio; ADR-017 approves progressive filling.
ACCEPTED provisional ADR-017 / VERIFIED S3.3 progressive proportional: freeze A at0 because E empty, serve B10;
consumedS10,E0, endingS10, lostA10/B0, overall service10/20=.5. Physical Ingredient
shortage is E10/S0: S has20 available against20 requested. S10 unconsumed design
demand reflects E blocking, not S shortage. Never add cross-Ingredient diagnostic
gaps to fabricate20 lost cups.
Second input S15,E5: progressive fill A5,B5 first, freeze A; use remainingS5 forB
⇒A5,B10, consumedS15,E5, lost5, service15/20=.75. Fractional outputs are planning
amounts. This verifies the accepted equal-priority fairness rule; no max-cups/revenue optimality claim.

## G08 — Low budget and complementary MOQ activations

Two Products: A demand10cups uses X1+Y1, B demand6cups uses Z1. No stock.
Each Ingredient pack5units/cost5/MOQ2; activation=10units/cost10. Budget20.
X alone or Y alone yields0cups. Joint X+Y costs20 and serves A10, B0 ⇒10/16=.625.
Z alone costs10 serves B6; residualbudget10 cannot activate X+Y together ⇒6/16=.375,
unusedbudget10. Both are hard-valid, only their service differs. Arbitrary UUID-order
admission can buy X then Z, serve6, leave X10unproductive.
Reviewer alternatives: whole-MOQ dish basket admission vs marginal heuristic with
explicit joint recipe moves (DECISION_DESIGN). Singleton-only “marginal benefit”
misses complementarity. Do not claim greedy global optimality or silently accept
one allocator. Budget21 does not license 1pack of X under MOQ2.

## G09 — Missing facts vs physical shortage

Requested A10cups, missing dated recipe: retain A scope and MISSING_RECIPE blocker
affected ProductA, DATA_BLOCKED, no computed plans/recommendation/lost-sale numbers.
Recipe present but tracked lot5g/expiryunknown: MISSING_EXPIRY blocker, not “stock0”.
Lot5g/knownexpiry/receiptunknown/costunknown: stock remains5g, receipt/age and cost
warnings with affected lot/action; can quantify fulfillment with knownrecipe, but
positive ending/waste value UNKNOWN/null/reason. Missing price does not meanfree.
Missing optional Product retailprice has no impact on the v1 quantity/outlay metric.
For tracked positive purchase, supplier shelf unknown blocks it; if actual stock
suffices, zero purchase can remain valid. Distinguish conditional need from blanket
blocking all canonical records. Zero stock captured completely is a true shortage.

## G10 — Identical baskets after rounding

One planning window aggregate P50=8cups, P75=9cups,1g/cup; stock0, pack10g/cost20,
MOQ1/lead0/nontracked. LEAN construction8g, BALANCED8.5g, PROTECTED9g ⇒ all1pack,
10g/outlay20. Evaluate these same baskets on LOW/BASE/HIGH; retain all three names,
record pairwise equivalence, no forced differences. If all targets met and comparable
waste/outlay equal, provisional stable tie picksLEAN, not automaticBALANCED.
P25 need may differ, but does not define a fourth procurement strategy.

## G11 — All candidates miss targets but remain hard-valid

Each day all paths10cups,1g/cup; stock0, pack1g/cost1/MOQ1/lead0, budget30,
noexpiry. Within-budget candidate30g can fulfill30 of70, loses40, service3/7≈.42857.
All strategies may collapse to that same30g; preserve equivalence. Neither .95 BASE
nor .90 HIGH met ⇒ TARGETS_NOT_MET/degraded evidence, never target-feasible or default
BALANCED. ADR-017 requires no recommended_strategy when no BASE-pass; best_available is a
separate alternative only if hard-valid and fully evaluated, ranking still pending. HARD_INFEASIBLE reserved for constraint violations, DATA_BLOCKED for
missing facts. A basket31g violates budget and cannot be selected.

Group priority subcase (same unit): candidateA BASE.96/HIGH.85/outlay100 vs
candidateB BASE.97/HIGH.89/outlay120, no both-pass candidate ⇒ BASE_ONLY group,
provisional cheaperA; high miss still explicit. A candidateC BASE.95/HIGH.90/outlay130
belongs to both-pass group and outranksA/B despite greater outlay. No hidden weights.

## G12 — Zero demand and denominator

All Product/date/path demands0, stock0, no safetyfloor ⇒ zero orders, fulfilled0,
lost0, consumption0, waste0, ending0, outlay0. Service UNDEFINED/null/reason “zero
demand”, not fake0 or1. Targets vacuously satisfied; with identical zero baskets
provisional stable tie picksLEAN. Nonzero captured stock may remain positive ending
inventory even in this case; it does not become waste because demandzero.
Mixed units cup and portion cannot be added into a policyv1 service denominator;
explicit normalization/new policy must precede such an aggregate.

## G13 — BOM demand paths are not calibrated quantiles

A and B each P25=0/P50=5/P75=10cups for one day, each uses1g S (e.g. marginal
empirical histories A=[0,0,10,10], B=[10,10,0,0] yield those interpolated quantiles).
LOW=0g, BASE=10g,
HIGH=20g after sum. A perfectly complementary joint pattern (A10,B0 or A0,B10)
always totals10g; its true Ingredient high quantile10, not sum20. Conversely a
co-moving pattern can yield a different distribution. Marginal Product quantiles
alone cannot establish joint Ingredient probabilities/calibration. Use labels
LOW/BASE/HIGH design paths; no expected risk or CVaR from three equally weighted
numbers. S2 metrics/predictive quality evidence remain a separate evaluation.

## G14 — Captured policy/history stable after live corrections

Captured forecastP50=8/P75=9, recipe1g/cup/version1, lot0, term pack10/cost20/version1,
demo policy balancedalpha.5. Construction8/8.5/9g, same10g baskets/outlay20 asG10.
After capture live recipe2g/cup/version2, termcost999/version2, forecast999 and future
policyalpha.75 do not change the original typed snapshot or expected old result.
Historical interpretation/replay must use old copied values/policy/model/input
identities, no live join. New capture changes input digest; same old canonical
input replay keeps digest but new persisted run gets a newUUID. No retrofit of new
coefficients under policyversion1. S3.1 only proves nested immutability/typed JSON
roundtrip/policy consistency; hashing, replay execution and persisted package still
require future implementation and fresh-session tests.

## Future executable gates

Before corresponding engines: turn the applicable specs into deterministic fixtures
and tests against **real implementations**. Verify lot-level conservation/FEFO,
daily fulfillment vs BOM, no early consumption, fixed one-order basket across paths,
budget/MOQ, distinct missing vs shortage, supported value attribution, reproducible
selection and provider-outage operation. Persisted replay requires actual snapshot/
hash verification and fresh-session aggregate assertions. S3.1 does not claim these
future gates passed. See [design](DECISION_DESIGN.md) and
[task notes](../runbooks/FULL_TEST_FLOW.md).
