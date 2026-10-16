# Procurement golden specifications and scratch evidence

HISTORICAL INFORMATION: this research/specification predates the accepted engine.
Scratch observations below are historical; current implementation and runnable
verification are in [PROCUREMENT_ENGINE](PROCUREMENT_ENGINE.md) and
[the runbook](../runbooks/FULL_TEST_FLOW.md). Retired evidence is not a current gate.

Classification: HISTORICAL INFORMATION for executed scratch experiments; their
original PROPOSAL status is not authority for current production policy.
The original `runtime/s341/procurement_experiments.py` and `results.json` were local
scratch artifacts, not tracked inputs supplied by a clean clone. Retain existing
private evidence where present; this document does not claim those files can be
recreated from Git. Current implementation is described in
[PROCUREMENT_ENGINE](PROCUREMENT_ENGINE.md) and [PROCUREMENT_V2](PROCUREMENT_V2.md);
reusable checks include [Planning small-domain oracles](../../tests/unit/test_planning_small_domain.py)
and [procurement/2 checks](../../tests/unit/test_procurement_v2.py).

## Executed finite domains

All inputs are small SYNTHETIC captured snapshots, no DB/current facts. Horizon
always seven days; unspecified daily demand is zero. Captured quantiles are equal
in these toys, so each basket is evaluated on all three identical paths. They do
not exercise distinct construction-path strategy selection. Units are identical
within each Ingredient; recipe yield1/loss0 unless stated. Fees explicitly NONE,
prices synthetic, no cost accuracy inference. All reported servings are exact
rational values from current simulate_serving and validated output contracts.

Scratch ranking: among construction-target passers, minimum outlay, then number
of active offers, then selected offer-ID/pack signature. If none pass: maximum
served, then those cost/tie criteria. This is a proposed toy objective, not a newly
accepted business selector. Grid count includes invalid MOQ/budget/capacity vectors;
hard-valid count includes service failures. Counts vector follows script offer order.

| Case | Independent expected result | Grid / hard-valid / target-pass | Actual selected counts; outlay; served/requested |
| --- | --- | --- | --- |
| Complementarity | Product10 needs X1 and Y1; each pack5 costs5, U=2, budget10. Either alone serves0; one of each serves5; full10 needs20 and cannot fit budget. | 9 / 6 / 0 | (1,1);10;5/10 |
| Shared Ingredient | Two Products demand10 each, each uses1 of common stock5. Fairly serve2.5 each, total5, not10. | 1 / 1 / 0 | ();0;5/20 |
| Cheap unit cost / large MOQ | Demand5. Cheap pack10 costs1 but MOQ5 packs; small pack5 costs3 with MOQ1. Cheapest full-service outlay is3, despite higher unit price; cheap activation costs5. U=(5,1), budget10. | 12 / 4 / 3 | (0,1);3;5/5 |
| Quantity MOQ not divisible by pack | Legacy quantityMOQ5 with pack2 implies ceil(5/2)=3 packs. Scratch supplies canonical minpacks3 explicitly; costs2/pack, U3,budget6, demand5. Quantity6 purchased,1 ending. No production conversion implied. | 4 / 2 / 1 | (3);6;5/5 |
| Late arrival / inclusive expiry | Demand2/day for7 days; pack2 costs2, lead1 relative D+1, shelf0, U7,budget14. ArrivesD+2, usableD+2 only; one pack serves2, more packs expire without extra service. | 8 / 8 / 0 | (1);2;2/14 |
| Receipt capacity before expiry | Captured initial5 already expired; receipt3 onD+1 would make8>cap7 before expiry/removal/service, even though subsequent ending could be0. Reject receipt; zero purchase expires5 and serves0. U1. | 2 / 1 / 0 | (0);0;0/3 |
| Stock sufficient / budget zero | Initial14, demand2/day. Budget0 rejects paid pack. Zero purchase serves14 with no expiry. | 2 / 1 / 1 | (0);0;14/14 |
| Greedy trap and no target basket | A5 needsX, X pack5 costs3. B8 needsY, Y pack8 costs5. Each U1,budget5. Greedy gain/cost choosesA5 (5/3>8/5), leaving2; enumeration choosesB8. Cannot serve all13 in domain. | 4 / 3 / 0 | (0,1);5;8/13 |
| Equal objectives / supplier tie | Demand1, offers A/B each pack1,cost1,U1,budget1. Both single baskets are primary-optimal. Proposed selected-ID tie picksA. This is not a native MILP tie guarantee. | 4 / 3 / 2 | (1,0);1;1/1 |
| Split suppliers | Demand1 onD+1 and2 onD+2. Early supplier pack1 costs2, later supplier pack2 costs1 arrivesD+2, eachU1,budget3. Split basket servesall3. | 4 / 4 / 1 | (1,1);3;3/3 |
| One supplier restriction | Same inputs; forbid split perIngredient. Late-only serves2 for1, early-only serves1 for2. Full3 no longer reachable. | 4 / 3 / 0 | (0,1);1;2/3 |
| Surrogate allocation mismatch / bounded repair | A20 uses.2L, B10 uses.4L, stock7.4L. Offer.2L costs1,U3,budget3. Target.95=28.5 servings. Fair fraction7.4/8=.925 gives27.75. One pack raises stock7.6 and fraction.95, gives28.5. | 4 / 4 / 3 | (1);1;28.5/30 |

Total: **12 cases,58 grid vectors**. Counts do not include every separate evaluator
call for comparator and solver checks. Assertions compute expected values from
hand arithmetic, not by duplicating an optimizer. They exercise the current pure
evaluator; capacity/offer eligibility/ranking are explicit scratch guards and not
production behavior newly verified by these cases.

The actual single-move greedy comparator runs both complementarity and trap:
served0 versus exhaustive5, and served5 versus exhaustive8 respectively. It only
activates one MOQ or adds one pack at a time; it is **not** an implementation or
benchmark of ADR-017's unimplemented joint-activation heuristic. Two counterexamples
justify not choosing a single-move algorithm without broader evidence; they do
not prove every heuristic inferior to every MILP on real workloads.

## Actual solver experiment and status evidence

Actual SciPy1.17.1 milp solves the milk toy with integer x in[0,3], continuous
served A/B and constraints .2*A+.4*B<=7.4+.2*x, A+B>=28.5, min x. This permits
allocations differing from progressive fairness. First call status0/OPTIMAL, x0,
predicted28.5, exact evaluator27.75, target fails. Exclude x0 by lowerbound1 in
this single-variable case; second call status0, x1, evaluator28.5, target passes.
Dual bounds0 and1 respectively, both MIP gaps0. Enumeration certifies minimal
evaluated outlay1 only within this finite toy domain. General no-good cuts,
progressive MILP and deadline coordinator are design, not script implementations.

Actual separate call with time_limit=0 and presolve=False returns status1 with
no incumbent, HiGHS message time limit reached. It tests one observed native
termination only. The two results.json synthetic_status_examples describe future
handling of time-limit with a valid incumbent versus none; they are **illustrative
records**, not executed production classifiers or an observed incumbent timeout.

Future executable acceptance must fault-inject all solver statuses and separately
observe feasible-incumbent termination on a suitable model. Assert:

- Valid incumbent survives timeout, target attainment is separately labelled,
  bounds/gap preserved, no optimal label.
- No incumbent and no previous validated basket yields INCOMPLETE, not infeasible.
- Invalid incumbent is rejected by exact pack/budget/date/capacity/evaluator checks.
- One shared deadline includes every construction/search/probe/final validation.
- INFEASIBLE proof applies only to documented assumptions/domain; solver bugs and
  UNBOUNDED cannot become business success.

## Additional specifications not yet executed

Fee activation: two Ingredient offers of one supplier, each packcost2, one
supplier-order fee3, budget7: buying one each costs7, not10. With per-offer fee3,
same basket costs10 and violates7. Unknown fee capture blocks a definitive cost
claim. Current contracts cannot represent these choices; no end-to-end fee test
claimed. Quantity bounds with zero-cost offers require proven dominance/business
limits; technical cutoffs must not masquerade as business infeasibility.

Distinct strategies: LOW/BASE/HIGH construction may yield identical baskets;
evaluate each on all paths, mark equivalence. Construction-target pass alone
does not imply final BASE.95/HIGH.90 eligibility. With no BASE-pass, no winner;
best_available remains separately labelled and its ranking awaits acceptance.
No selector or no-winner persistence test is implemented in this slice.

Numeric cases: nonintegral near-integer incumbent, extreme coefficient scaling,
shared-fee budget boundary, exact target boundary, complementary recipes with
multiple simultaneous saturation events and multi-day FEFO parity. Decimal/rational
truth must reject any business overrun rather than hide it behind solver tolerances.
Policy-faithful unrolled MILP must match actual Product/day/Ingredient/lot totals
over exhaustive small fixtures, not just horizon servings or mincost.

Economic missingness: absent Product selling price and lot cost means dish profit,
expiry value and ending value UNKNOWN. A shortage reference price is not lost
profit. No probability assigned to these deterministic design paths, no calibration
claim, no monetary sum of cash outlay plus duplicated purchased-consumption cost.

## Commands and limits

HISTORICAL INFORMATION — original command recorded at the scratch checkpoint,
executed twice (second run added the actual greedy comparator). The referenced
test filename is not present in current Git; this is provenance, not a runnable
clean-clone instruction:

```
.venv/Scripts/python.exe -B -m pytest tests/unit/test_procurement_small_domain.py -q
```

Both runs passed all assertions; final results reports4.756902400000399 seconds,
Python3.11.9/SciPy1.17.1. Earlier run4.242949899999985 seconds is historical and
superseded for current script. No pytest/full regression, legacy test execution,
DB access, benchmark-size workload, production procurement or forecast accuracy
verification was performed. Task notes record document/archive checks separately.

Current reusable checks can be selected separately (not executed by this documentation task):

```powershell
.venv/Scripts/python.exe -B -m pytest tests/unit/test_procurement_v2.py tests/unit/test_planning_small_domain.py -q
```

The historical timings/results above do not apply to this current selection.
