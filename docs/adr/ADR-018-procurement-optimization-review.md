# ADR-018 - Procurement optimization review and proposed engine selection gate

Status: PROPOSED, 2026-10-07. Not ACCEPTED; does not supersede an ADR yet.

CURRENT FACT: the user's S3.4.1 task explicitly reopens ADR-017's discrete marginal
heuristic as a closed engine choice. ADR-017's serving/FEFO, strategy construction
and no-winner directions stay in force. No serving or historical policy is changed.
User authority permits analysis/replacement proposals, not acceptance of MILP.

## PROPOSAL

Select a procurement engine only after policy-faithful formulation/benchmark review:
minimum outlay under explicit supported service requirements; exact progressive
serving/FEFO evaluation and hard post-validation; best valid incumbent retained on
deadline, with honest scope/quality evidence. Evaluate unrolled policy-faithful MILP,
finite-domain exact enumeration/branch search and surrogate MILP with exhaustive
candidate exclusions/repair. Greedy remains a comparator, not a chosen engine.

No solver status alone proves actual evaluator service, global business optimality
or procurement readiness. No manufactured probabilities, economic data or capacity.
Missing fees/capacity/economics need explicit contract/completeness decisions.

Proposed supersession scope if approved: replace only ADR-017's procurement algorithm
selection; preserve its supplier-basket evaluation, one-order scope, LOW/BASE/HIGH
construction, progressive allocation, no-winner and historical version intent.
Objective hierarchy, supplier splitting, construction target, captured extensions,
search bounds/deadline and exact solver formulation require approval before wiring.

References: [design](../features/PROCUREMENT_DESIGN.md),
[formulation](../features/PROCUREMENT_FORMULATION.md),
[goldens](../features/PROCUREMENT_GOLDEN_CASES.md), [notes](../runbooks/FULL_TEST_FLOW.md).
