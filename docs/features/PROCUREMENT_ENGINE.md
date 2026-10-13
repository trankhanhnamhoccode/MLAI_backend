# Internal procurement/1

Classification: CURRENT FACT unless labelled. Authority: user S3.4.4 task and ADR-019.
This is candidate construction for an eventual selector, not a full DecisionRun.

## Callable boundaries and layout

`ProcurementInput` / `ProcurementPolicy` in
`app/application/contracts/procurement.py` are frozen, recursively revalidated values.
`execute_procurement(input, search_factory)` in application/use_cases/procurement.py
accepts a synchronous candidate-search port. Compose with infrastructure
`NativeSearch`; the demo shows the actual wiring. No application imports SciPy or
concrete infrastructure. `evaluate_procurement_basket(input, counts)` separately
revalidates fixed-basket inputs and rejects blocked admission.
Domain `decision/procurement.py` has exact rational fees/packs/constraints and finite
odometer traversal only. Infrastructure procurement_milp.py owns float projection,
SciPy/HiGHS, progressive event equations, dated independent lot states and FEFO cuts.
Independent application/procurement_validation.py verifies final basket/input identity,
outlay, arrivals, all-path metrics, targets/gaps, enabled constraints and proof coverage.
Canonical serving output validation is also mandatory; no simulation reimplementation.

## Supported envelope

Captured PreparedDecisionInput owns Store-local cutoff, exactly seven days, explicit
Products, P25/P50/P75, dated inclusive recipes, whole-yield quantities and process loss,
exact units, lots/receipt/expiry, supplier terms, issues and source provenance. Snapshot
order is canonicalized using existing BOM rules; caller mutation/live facts do not
change values. Procurement policy is separate from the unchanged historical v1.

Every offer references a captured active/effective supplier term and a distinct future
lot UUID. Pack/cost/MOQ/lead/shelf facts are reused, not overridden. Supplied offers
must arrive within D+1..D+7; missing tracked shelf life blocks, known expiry always
applies. Explicit hypothetical arrivals are separate from current operational lots;
future operational receipts are excluded as in serving_fefo/1. No current data reads.

Bound source is TECHNICAL_SEARCH_LIMIT or CAPTURED_SUPPLIER_LIMIT with derivation and
CAPTURED_FINITE_DOMAIN_ONLY proof scope. Supplier-derived bounds need a consistent
supplied limit; technical bounds are never claimed to be real supplier availability.
Limits currently support ONE_ORDER_SUPPLIER_INGREDIENT base quantity in exact unit.
Other configured constraints must be explicitly listed as unsupported and block.
No aggregate supplier cross-unit capacity/conversion, calendars or repeated orders.

Required policy explicitly contains LEAN→LOW/BALANCED→BASE/PROTECTED→HIGH, all three
construction targets and optional per-Product horizon floors. Common selling unit
must match literally; no conversion. A zero-request scope vacuously meets targets;
its service ratio is null, not fabricated 100%. Every basket evaluates all three
independent paths. These are design scenarios, not probabilities or accuracy claims.

Fees: explicit NONE / PER_OFFER activation / PER_SUPPLIER_ORDER once per active
supplier across all its offers. In applicable fee mode, null/missing fee blocks.
NONE with a positive supplied payable fee is a contradictory boundary input and is rejected.
Budget KNOWN enforces exact all-in spend, EXPLICIT_UNCONSTRAINED declares no limit,
UNKNOWN blocks. Captured budget cannot be bypassed by envelope settings. Capacity is
optional per Ingredient, exact unit, on gross opening + receipts before expiry or
consumption for every path/day. Not-configured capacity/limits remain visible in
coverage. Configured MIN_SAFETY_STOCK always blocks; policy-v1's unused terminal-floor
wording is not interpreted by this engine. No sales price/profit or currency settlement.

## Exact authority and numerical envelope

Pack count is integer, zero or >= offer MOQ, and <= explicit finite bound. Costs,
fees, supplier quantities, budgets, capacity and service gaps use exact Fraction of
captured Decimal. No budget/target epsilon or downward target rounding. Decimal50
HALF_EVEN is only a view via existing canonical Quantity; reduced numerator/denominator
strings are authority. Pack × integer creates a terminating Decimal exactly without
ambient context. Existing serving guards limit rational numerator/denominator to
1000 digits. Numeric failures are unsupported, never manufactured zero/infeasible.

Required numeric policy specifies float coefficient/lot-scale ranges, integer maximum
(<=2^53-1) and extraction tolerance (<.5). Float projection rejects nonfinite,
underflow-to-zero and configured unsafe ranges. The MILP bounds are derived from
maximum captured/possible lot quantities and known demand, not guessed big-M stock.
Extraction tolerance is purely technical; every extracted integer basket is exact
checked. Decimal facts closer than float64 resolution can project together; exact
evaluation remains authoritative, and the finite-domain proof comes only from exact
enumeration. Guard values are SYNTHETIC config choices in demo, not general guarantees.

## Search, result quality and failures

Primary generator minimizes outlay under encoded construction requirements. Rejects
are classified before exclusions. Disjunctive bounded cuts remove exactly one vector;
target-miss cuts stay in target search only. Hard-invalid cuts also apply to fallback.
Fallback generates maximum construction service, then minimum cost under its raw
encoded service level. Exact incumbent comparison uses max exact served then min
exact outlay; floor gaps remain separate. These generation phases cannot establish
global exact objective or ties. When enabled and within explicit limit, complete
odometer traversal certifies the supplied finite domain including every invalid/MOQ
vector classification, independently of native exclusions/status. Tests' oracle uses
separately authored itertools traversal, fee/constraint/objective code, same canonical
fixed-basket evaluator; it does not independently prove simulator correctness.

Result keeps execution FINISHED/INCOMPLETE/ERROR/BLOCKED/NUMERIC_UNSUPPORTED separate
from target existence PASS_EXISTS/NO_PASS_CERTIFIED/UNKNOWN and proof UNPROVEN versus
COMPLETE_EXACT_ENUMERATION. FINISHED can mean a completed bounded generation phase
with unproven optimum; search_complete is true only for exact finite certification.
Validated target-met candidates are usable internal proposals despite unproven cost.
UNCERTIFIED is not hard invalidity. Native infeasible is encoded evidence only, never
NO_PASS_CERTIFIED without full exact traversal. A hard-valid fallback is separate;
there is no recommended_strategy/winner. Equivalent baskets across strategies are legal.
Issues/provenance/full canonical serving remain in retained typed in-memory values.

One monotonic deadline starts before public input revalidation. Each remaining
strategy gets equal remaining time, with unused time carried forward. Required reserve
is withheld from native solve time for exact validation. Cache is shared across
strategies, cuts are isolated. Only fully validated candidates are retained, including
zero purchase. Native LIMIT with validated candidate stays INCOMPLETE unless exact
certification finishes; LIMIT without candidate remains unknown. Repeated excluded
vectors, cut/model/programming failures are ERROR even if earlier evidence exists.
Numeric unsupported remains distinct. Journal is an immutable in-memory trail, not a
durable disk journal or provenance retention feature.

TECHNICAL DEBT: build, native solve and exact validation are cooperative/nonpreemptible;
actual elapsed (including final aggregate validation) and overrun are reported. A too
small reserve can leave a late raw incumbent unvalidated. Time-limited searches can
vary by machine/solver and have no exact objective/tie proof. Required reserve and
guard settings need practical tuning; no universal latency envelope is claimed.
Exclusion cuts also guard `2*maximum_packs+1` against the configured exact integer
range; representable pack bounds alone do not guarantee representable cut RHS.
The serving contract has Product→Ingredient contributions and separate lot consumption,
not direct Product→lot edges. No DB/API/auth/retention/replay/selector/final Decision
readiness is implemented. Output reconstruction is structural consistency evidence,
not replay/certification of a potentially maliciously authored search journal.

## Verification and manual use

See [task notes](../runbooks/FULL_TEST_FLOW.md) and
[current verification report](PROCUREMENT_V2.md).

```powershell
.venv/Scripts/python.exe scripts/demo_procurement.py --seconds 30
.venv/Scripts/python.exe scripts/demo_procurement.py --products 5 --seconds 15
.venv/Scripts/python.exe scripts/demo_procurement.py --products 10 --seconds 15
```

Small demo uses the saved just-above-.3 target and .3 budget, and reports a certified
miss/fallback. Larger demo uses explicit SYNTHETIC .8 targets, .5s reserve and 65,536
pack vectors with enumeration disabled. It shows suppliers/packs, exact spend,
LOW/BASE/HIGH service, native status/bound/gap and quality. No DB or operational writes.
Use `--example target-met` or `--example zero-purchase` with the one-Product demo
to inspect a passing basket or a passing zero-budget/zero-purchase baseline.
PROPOSAL: review this boundary/configuration before authorizing capture/persistence or
selector work. No next slice is started automatically.
