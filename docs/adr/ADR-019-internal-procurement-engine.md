# ADR-019 — Internal procurement candidate engine

Status: ACCEPTED by the explicit S3.4.4 user implementation task, 2026-10-08.
Acceptance is limited to the direction below, not undocumented business defaults.

## ACCEPTED DECISION

Supersede ADR-017's procurement heuristic choice only. Preserve progressive serving,
FEFO, LOW/BASE/HIGH construction mapping, one-order scope and no-winner direction.
ADR-018 remains the historical PROPOSED review gate; the S3.4.4 task now explicitly
authorizes production internal adoption after S342/S343 experiments.

Policy-faithful float64 MILP generates finite pack baskets. Exact canonical serving
and independent output validation own hard validity and target attainment. Reject
wrong candidates, journal classification before bounded exact-vector exclusion and
re-search. A validated target-met basket may be proposed with minimum outlay
UNPROVEN. Native OPTIMAL/infeasible/gap is not an exact business certificate.
Small-domain exact enumeration is opt-in, limited and separately identified.

Separate procurement/1 from historical DecisionPolicy v1; never reinterpret runs.
Required configuration declares three construction targets, optional Product floors,
common-unit horizon aggregate, min-outlay primary and max-service/min-outlay fallback,
supplier splitting, fees, budget state, finite bounds/provenance, guards, deadline,
search/certification limits and tie rule. Do not reuse BASE .95/HIGH .90 implicitly.
Configured MIN_SAFETY_STOCK remains unsupported/blocking; no terminal floor adopted.
One decision-time basket; exact-unit supplier/Ingredient limits and optional gross
capacity are checked post-receipt/pre-expiry/pre-consumption, independently per path.
Unknown budget/payable fees cannot become unlimited/zero. No invented live facts.

Independent result dimensions preserve readiness/coverage, execution, exact hard
validity, targets/floor gaps, raw solver evidence, finite proof scope and search
completeness. Best-available is separate from a winner; no strategy selector here.
Always consider zero purchase; cache only completed exact evaluations. One cooperative
invocation deadline includes build/solve/re-search/evaluation/validation/certification.
Fair scheduling must not disguise incomplete strategies as a complete comparison.
Technical failure retains validated evidence but remains an execution error.

## CURRENT FACT / routine implementation choices

Contract requires the implemented UUID-sorted pack-vector lexicographic tie rule;
this is a reviewable implementation choice, not a Store business preference default.
Remaining time is divided equally among remaining strategies, with unused time
carried forward. Each strategy has separate target and fallback cuts: target misses
must remain available to fallback. Technical numeric guards/reserve are required;
demo values are labelled SYNTHETIC. No general float-bound-to-exact proof exists.

## PROPOSAL / unimplemented

DB capture/retention/replay, persistence/schema/API/auth, real payable fee/capacity
loaders, PO/movements, full comparison/selector, profit, stochastic modes and real
forecast accuracy remain outside this authorization. Business configuration needs
Store-specific review; no universal service target accepted by this ADR.

References: [engine](../features/PROCUREMENT_ENGINE.md),
[task notes](../runbooks/FULL_TEST_FLOW.md),
[ADR-017](ADR-017-serving-fefo-provisional-direction.md),
[ADR-018](ADR-018-procurement-optimization-review.md).
