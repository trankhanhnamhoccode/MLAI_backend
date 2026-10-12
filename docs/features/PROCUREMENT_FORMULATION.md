# Procurement formulation

HISTORICAL INFORMATION: this research/specification predates the accepted engine.
Scratch observations below are historical; current implementation and runnable
verification are in [PROCUREMENT_ENGINE](PROCUREMENT_ENGINE.md) and
[the runbook](../runbooks/FULL_TEST_FLOW.md). Retired evidence is not a current gate.

Classification: PROPOSAL, except explicitly labelled CURRENT FACT or experiment.
S3.4.1 does not implement this formulation or accept an optimizer. Read
[design](PROCUREMENT_DESIGN.md), [goldens](PROCUREMENT_GOLDEN_CASES.md) and
[proposed ADR-018](../adr/ADR-018-procurement-optimization-review.md).

CURRENT FACT S3.4.2: historical scratch output (retired; current implementation is app/domain/procurement/) implements a scratch-only instance
with derived quantity normalization/bounds, shortage max linearization and actual
finite-corpus parity/oracle evidence. See [benchmark](PROCUREMENT_V2.md).
No production engine/contract or business policy is accepted. Experimental source
uses finite fixture bounds, explicit fee/capacity data and technical numeric guards.

CURRENT FACT S3.4.3: separate scratch coordinator implements the finite no-good
disjunction below and exact bounded enumeration certification; it preserves the
unchanged S342 event model. [New evidence](PROCUREMENT_V2.md)
distinguishes exact candidate, native encoded optimum and enumeration proof.
Native INFEASIBLE or gap0 never certifies the exact evaluator domain. Only a
complete traversal certifies primary/fallback; deadline/limit leaves UNCERTIFIED.
Conservative RHS projection can exclude exact-feasible baskets, so it is a
diagnostic, not a superset or production numeric fix. Old counterexample resolved
in its declared11-vector domain; broader proof/policy/adoption remain unaccepted.

## Scope, sets and captured parameters

One order decision, one fixed basket evaluated independently on three paths.
No replenishment policy, stochastic probabilities or actual purchase action.
T={D+1,...,D+7}; R={LOW,BASE,HIGH}; P=captured Products; I=captured Ingredients;
O=eligible dated offers; L=actual eligible lots plus each potential offer receipt.
Every quantity is indexed by its exact unit; no sum of kg and litres. Product
service counts may be summed only under an approved common serving-unit policy.

For each path/day/Product, d[r,t,p] is captured P25/P50/P75. The dated recipe
coefficient a[t,i,p] is line quantity / yield / (1-loss), summed over lines for
that Ingredient. These are bounded exact rational coefficients using the same
captured recipe and units as serving, not displayed/rounded BOM quantities.
Missing/overlapping/empty recipes or any relevant DATA_BLOCKER block construction.
Zero demand still requires the recipe according to existing snapshot policy.

Offer parameters: q[o]>0 pack quantity, c[o]>=0 exact pack cost, m[o]>=1 integer
minimum packs, supplier, Ingredient/unit, effective dates, arrival date and known
expiry when required. Capture currently has packs MOQ, not quantity MOQ. Importing
quantity MOQ would require explicit conversion ceil(quantity MOQ/q), provenance
and an authorized boundary; solver does not guess such a conversion.

CURRENT FACT: snapshot supplier terms have lead time and optional shelf life,
but no delivery calendar, fees, supplier capacity or explicit incoming PO capture.
Product has no selling price; storage capacity/footprint is absent from the
constraint registry. These gaps and proposed minimal evolution are in DESIGN.
The formulation below is conditional on explicit capture of each enabled policy.
No absent field means free delivery, unlimited business capacity or zero cost.
MIN_SAFETY_STOCK is captured but its procurement checkpoint/expiry semantics are
not approved here. A configured rule cannot silently disappear: future readiness
must flag unsupported required safety policy until it is explicitly formulated.
Possible terminal usable-stock floor is an alternative, not an accepted constraint.

CURRENT FACT: single order date is Store-local D+1 from captured request.order_at,
with inventory_as_of equal to that pre-trading instant
(`app/application/contracts/decision_execution.py:226`). Evaluate term validity
there, require active same-Store terms and consistent Ingredient/unit. Nominal
arrival=date(order_at)+captured lead days, so lead0/1 means D+1/D+2. This preserves
the existing convention; it cannot establish an uncaptured real calendar. With
captured shelf life L under the existing inclusive convention, expiry=arrival+L;
L=0 is usable on arrival then disposed at close. A known expiry is honored even
for non-expiry-tracked Ingredients. Unknown expiry is permitted only under the
current explicit non-tracked policy, not inferred from a missing shelf life for
tracked ingredients. Revalidate date overflow and every generated arrival.

Actual stock eligibility uses the current serving filter at inventory_as_of:
future operational receipts are not incoming orders. Additional inbound must be
explicit, hypothetical, uniquely identified and scoped; no live reads. Missing
actual receipt dates remain unknown. Opening balances and all ordering metadata
are captured, never reconstructed from current operational facts.

## Packs, activation, suppliers and money

Variables x[o] in integers [0,U[o]], y[o] binary. Constraints:

```
m[o]*y[o] <= x[o] <= U[o]*y[o]
```

Thus zero purchase is MOQ-exempt and any activated offer satisfies MOQ. Multiple
dated alternatives from the same supplier are not separate business orders unless
the capture says so. For one-supplier-per-Ingredient, introduce z[i,s] binary,
y[o]<=z[i,s(o)], sum_s z[i,s]<=1, and z[i,s]<=sum_{o in (i,s)}y[o]. For split
suppliers, remove the exclusivity bound but retain actual supplier restrictions.
Both are alternatives pending approval; the same tests must compare them.

Outlay C=sum_o c[o]*x[o] + explicit applicable delivery charges. Choose an explicit
captured fee policy: NONE, PER_OFFER f[o]*y[o], or PER_SUPPLIER_ORDER f[s]*z[s].
For grouped fees, z[s] is the OR of all that supplier's active offers; charge once,
not once per Ingredient. Do not accidentally charge both representations. A
configured nonnegative budget B imposes C<=B. An explicitly unconstrained budget
differs from an unknown budget. Optional supplier quantity/spend bounds require
captured limits, scopes and comparable units; they are not invented constraints.

Use exact Decimal-to-rational money for business checks. No implicit cents, VND
rounding, currency conversion or settlement. Currency units must agree. Fees are
part of budget, outlay and reported provenance, not buried in objective weights.

## Finite bounds: business versus admitted search domain

Business maxima apply only if captured. With c[o]>0 and a budget, floor(B/c[o])
is a safe upper bound when all fees/costs are nonnegative; tightening by a shared
fee requires the correct activation group. Zero-price offers need another bound.

Conditional dominance bound: U[o]=max(m[o],ceil(G[i]/q[o])), where G is full
HIGH-path gross horizon consumption, without subtracting stock. This preserves
an optimal representative only under nonnegative costs, no reward/requirement for
excess stock, no later-horizon obligations, no minimum supplier spend, monotone
capacity and freely removable extra packs above MOQ. Reducing larger quantities
then cannot reduce usable horizon consumption; whole-horizon gross is an upper
bound despite chronology. Include approved safety requirements if later added.
If those assumptions fail, this is not a proven safe bound. Zero demand permits
zero only under the same no-extra-obligation conditions. Setting U<m makes that
offer unusable; report it rather than silently changing MOQ.

Bounds imposed just to limit a benchmark are TECHNICAL SEARCH LIMITS, not supplier
capacity. Optimal/infeasible statements then concern only the admitted finite
domain. Record bounds, derivations and discarded alternatives. No arbitrary 1e9
big-M; any linearization M follows from captured finite quantity/fraction bounds.

## Lot balance, FEFO and physical capacity

Separate state for each path. For each lot/day, nonnegative O(open), A(arrivals),
Epre, V(usable), U(consumed), Eclose and N(ending). A potential offer contributes
q[o]*x[o] on its fixed arrival; actual lots contribute captured opening quantity;
explicit existing inbound is a separate captured constant. Future receipts do
not become opening stock. O on later days equals previous N.

```
Epre = O+A if known expiry < t, otherwise 0
V = O+A-Epre
0 <= U <= V
Eclose = V-U if known expiry == t, otherwise 0
N = V-U-Eclose
sum_l U[r,t,l of i] = sum_p a[t,i,p]*s[r,t,p]
other_waste = 0
```

Arrival on expiry day is usable; pre-expired arrivals are rejected by input policy.
Known-expired actual opening lots may be present and are removed at pre-expiry.
No fabricated shrinkage, serving rounding or optional disposal to evade constraints.

Capacity checkpoint is **after receipt, before pre-expiry removal and consumption**:
sum_{l of i}(O+A)<=K[i], if explicitly configured in that exact unit. This may
block even when ending stock is low. Shared store capacity requires captured
footprint v[i] in one capacity unit: sum_i v[i]*sum_{l of i}(O+A)<=Kstore.
No sum of raw Ingredient quantities across units. Initial expired stock still
occupies this checkpoint under the proposed convention; changing the convention
is a policy decision. Capacity is currently a scratch-only guard, not a new
serving or BusinessConstraint contract.

For fixed daily FEFO order j precedes l, introduce binary w[r,t,l]:

```
U[l] <= M[l]*w[l]
V[j]-U[j] <= M[j]*(1-w[l]) for every eligible earlier j
```

Positive consumption of a later lot therefore requires every earlier usable lot
to be exhausted before close disposal. Fixed ordering follows the actual captured
expiry/receipt/ID keys used in serving; absent receipt dates are not fabricated.
M is a safe available-quantity bound. CURRENT FACT correction (S3.4.2): the
evaluator emits Product-by-Ingredient contributions and separate lot consumption;
it does not emit a Product-to-lot edge (domain Usage/LotDay, serving contracts
FulfilledContribution/LotServingDay). Ingredient-level reconciliation cannot
establish which lot served a particular Product. Lot cost/expiry totals can be
explained at Ingredient/lot level; Product-by-lot economics would need a separately
authorized attribution contract, not inferred links. No such feature is added here.

## Encoding progressive proportional filling

CURRENT FACT: serving does not maximize arbitrary Product servings. It progresses
equal fractions of original positive demands and freezes Products using any
saturated Ingredient. A max-servings LP is a relaxation, not this policy.

PROPOSAL: unroll at most n=number of positive-demand Products events per day.
HISTORICAL INFORMATION S3.4.1: this was analytical, not solver-implemented then.
S3.4.2 now implements it in scratch and verifies a finite corpus, not general proof.
Let k=1..n, binary A[p,k] active; common fraction mu[k], increment delta[k];
Product fraction f[p,k]; v[p,k]=delta[k]*A[p,k]. Start active for every positive
demand, mu[0]=f[p,0]=0. All fractions lie in [0,1]. Linearize the product exactly
in real arithmetic using delta<=1:

```
mu[k]=mu[k-1]+delta[k] <= 1
0<=v[p,k]<=delta[k]; v[p,k]<=A[p,k]
v[p,k]>=delta[k]-(1-A[p,k])
f[p,k]=f[p,k-1]+v[p,k]
R[i,k]=Cusable[i]-sum_p a[i,p]*d[p]*f[p,k] >= 0
```

Introduce binary Z[i,k] selecting an actual saturated Ingredient, G[k] for
demand-complete, and H[k] indicating any active Product:

```
R[i,k] <= M[i]*(1-Z[i,k])
Z[i,k] <= sum_{p using i} A[p,k]
mu[k] >= G[k]
A[p,k] <= H[k]; H[k] <= sum_p A[p,k]
sum_i Z[i,k]+G[k] >= H[k]
A[p,k+1] <= A[p,k]
A[p,k+1] <= 1-G[k]
A[p,k+1] <= 1-Z[i,k] for each i used by p
A[p,k+1] >= A[p,k]-G[k]-sum_{i used by p}Z[i,k]
A[p,n+1]=0; s[p]=d[p]*f[p,n]
```

Any active event must reach a real bottleneck or full demand; it cannot stop at
an arbitrary fraction to favor another Product. At least one active Product is
removed per event. Selecting only some simultaneous saturated Ingredients leaves
other users active at the same mu, but the next delta is forced to zero until
they freeze. Compressing these zero events gives the same final Product fractions
as union freezing, rather than the identical event trace. This avoids a strict
zero-equivalence predicate or arbitrary epsilon. Proof obligations still include
multi-Ingredient simultaneous bottlenecks, variable capacities across days, zero
demand, bounded coefficient ranges and exact parity with the existing evaluator.
Do not claim demonstrated policy equivalence from this algebra alone.

This adds roughly O(paths*days*Products*Ingredients) event relations plus binary
activation and potentially quadratic lot-order relations. Benchmark formulation
size/time and parity before choosing it. It does not require a serving-policy
change. If too expensive, use the evaluator-driven alternative below, with weaker
optimality claims. Changing serving to max-servings would change fair distribution
(e.g. 6L: A20 at .2L/B10 at .4L -> fair A15/B7.5 versus LP A20/B5), and needs
separate explicit approval; it is not proposed as an implementation shortcut.

## Objective hierarchy and eligibility

Pending approval: construction target tau for each strategy. Recommended starting
benchmark is tau=1 on that strategy's construction path; alternatives are approved
per-strategy targets or joint BASE/HIGH constraints. Current final provisional
BASE>=.95 / HIGH>=.90 thresholds do not automatically define construction targets.
Proposed primary: minimize C subject to actual construction service >= tau.
If proved infeasible in the admitted domain, fallback maximize supported service,
then minimize C at that exact service optimum. Hard constraints always remain.

Horizon service=sum s / sum d requires comparable Product units; otherwise use
per-Product service constraints or an explicitly approved dimensionless weighted
aggregation. Zero-request path is vacuously satisfied only under a stated policy,
and report the zero denominator rather than fake division. Alternatives and daily
versus horizon protection are in DESIGN. No Ingredient total as a Product-service
proxy, no unapproved Product priority weights. A solver tolerance is not a service
relaxation. Exact tier fixing needs native post-check or proven staged bounds.

Economic objective is deferred until dish price and lot-cost attribution exist.
Never charge procurement cash outlay plus the same purchased consumption as COGS
in a profit metric. Missing expiry/ending cost valuation is UNKNOWN, not zero.
Holding and shortage coefficients are explicit business policy/data, not legacy
strategy weights copied from LEAN/BALANCED/PROTECTED.

Construct LEAN on LOW, BALANCED on BASE, PROTECTED on HIGH; evaluate every fixed
basket on all paths. Identical baskets are valid equivalence, not a failure to
create diversity. Final eligibility is separate from construction objective. No
BASE-pass retains TARGETS_NOT_MET/no winner; separate best_available is not a
recommendation and its ranking remains pending. Selector/persistence not implemented.

## Surrogate mismatch, repair and search termination

Alternative: relax progressive serving or FEFO to generate candidates, then run
the exact native evaluator and independent output validation. Every candidate
must first pass exact packs/MOQ/scope/fees/budget/date/capacity checks. Hard-invalid
outputs are rejected; a hard-valid target miss may be retained only as a labelled
best-available candidate. Store both predicted and actual metrics, formulation
version and reason. Never publish solver-predicted service as evaluated service.

Exclude a disproved basket and search again. With finite bounds, exact no-good
for xbar uses binary b[o,-],b[o,+] and sum_o(b[o,-]+b[o,+])>=1:

```
x[o] <= xbar[o]-1 +(U[o]+1)*(1-b[o,-])
x[o] >= xbar[o]+1 -(U[o]+1)*(1-b[o,+])
```

This excludes only that integer vector, not an unjustified neighborhood. Repair
may add a bounded pack or consider jointly activating complementary offers;
every repaired vector gets fresh exact evaluation. A single successful repair
does not prove minimal outlay. To certify evaluated minimal cost in a finite
domain, enumerate/exclude every cheaper basket (and required tie candidates), or
prove a valid lower bound from a genuine superset relaxation. A different economics
proxy, missing fees or artificial bounds do not establish that lower bound.
When the deadline/domain limits leave unresolved candidates, return search
INCOMPLETE with the best previously fully validated incumbent and scope, not an
infeasibility or optimality claim. An empty feasible set requires complete bounded
enumeration or a sound policy-faithful proof, not repeated unsuccessful repairs.

Experiment: stock7.4L, A20*.2L/B10*.4L, target28.5/30. A max-servings MILP buys
zero and predicts28.5; native progressive gives27.75. One additional .2L pack
gives28.5. Enumeration of 0..3 packs proves cost1 minimal in that toy domain.
The actual two solver calls implement this one-variable exclusion only; no generic
repair/no-good engine or policy-faithful MILP is implemented. See results/goldens.

## Numeric representation, solver states and one deadline

CURRENT FACT: installed SciPy1.17.1 milp is available in the existing environment.
Its interface converts objective/constraint data to double precision; status0
means solver-optimal, status1 an iteration/time limit, and incumbent/bound/gap may
be absent. Options include time_limit, node_limit and mip_rel_gap.
See [official SciPy milp documentation](https://docs.scipy.org/doc/scipy-1.17.0/reference/generated/scipy.optimize.milp.html).
No solver dependency added in S3.4.1; SciPy/HiGHS is a benchmark candidate, not
accepted procurement infrastructure. Record solver version/options/status/message,
objective/dual bound/gap/nodes where available and the actual domain solved.

Convert finite Decimal via exact rational first. Coefficient scaling can multiply
rows by powers of ten or bounded common denominators, but must record the map and
reject ranges that cannot be represented safely. No overflow/underflow to fabricated
zero, infinity or huge unexamined big-M. Existing evaluator bounds fractions at
1000 numerator/denominator digits; solver coefficient dynamic-range limits require
their own experiments and published guard policy. Large LCM scaling is not a
universal answer. Decimal50 display is not the authoritative conservation value.

Integer extraction tolerance is a versioned technical policy pending benchmark
(example proposal 1e-7); only near-integer solver x may become a candidate, then
exactly recheck its integer vector. This tolerance never permits budget overruns,
nonzero residual conservation errors or missing service. Float primal tolerances
and MIP gap do not certify business feasibility or exact global optimization.

| Solver evidence | Proposed interpretation after exact evaluation |
| --- | --- |
| OPTIMAL + validated incumbent | Optimal for the encoded formulation/tolerances; evaluator optimum only with parity/proof/domain qualifications |
| LIMIT + incumbent | Keep if fully hard-valid; report target attainment and gap separately; not optimal |
| LIMIT without incumbent | INCOMPLETE/unknown feasibility; retain an earlier validated candidate if any |
| INFEASIBLE | Encoded/admitted domain only; inspect bounds/data/model, no blanket business infeasibility |
| UNBOUNDED | Technical/model failure for a supposedly finite pack model; no recommendation |
| Other solver/programming failure | Explicit execution failure; prior evidence may be retained, never disguise a bug as successful optimization |

Use one absolute monotonic deadline covering model construction, all three strategy
searches, repairs, diagnostic probes and final evaluation/validation. Pass remaining
budget to each solver call, reserve final-validation time, do not start another
probe when insufficient time remains. Preserve only fully validated incumbents.
Solver time_limit is best effort and does not cover Python model building or
guarantee hard wall-clock preemption. A worker isolation/preemption mechanism would
require separate infrastructure approval; it is not implemented in this slice.
Legacy separate30s limits per solve/probe are not a shared computation deadline.

Equal-objective baskets need a proposed explicit tie sequence: fewer activated
offers then stable selected-offer-ID/pack signature. Staged exact comparisons or
exhaustive ties avoid native solver arbitrary choice; artificial tiny objective
weights can change the primary objective and are not acceptable. Tie policy awaits
approval. Replay of a fixed basket with captured input/version is deterministic;
time-limited optimization may produce different incumbents across machine/solver
versions. Capture options/versions, not a promise of identical interrupted searches.

## Verification boundary -- HISTORICAL INFORMATION S3.4.1

Executable evidence covers tiny exhaustive grids, current evaluator and a simple
max-servings surrogate. It does not cover the unrolled policy-faithful MILP, general
FEFO linearization, delivery-fee capture, native status classification, realistic
performance, API/persistence, real dish economics or probabilistic accuracy.
These are explicit benchmark/implementation gates, not completed S3.4 behavior.
S3.4.2's newer scratch evidence is reported separately above; production/real-data
and general policy-equivalence claims remain unverified. No old result is upgraded
by reading a new prototype.
