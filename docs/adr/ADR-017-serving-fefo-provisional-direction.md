# ADR-017 - Serving/FEFO and revised provisional decision direction

Status: ACCEPTED by explicit user continuation task, 2026-10-07; provisional and
reviewable after evaluation. Acceptance of future direction is not implementation.

Partially supersedes ADR-016 serving/budget/no-winner OPEN intent and construction
formula, and ADR-011's prohibition on mapping quantiles to strategy construction.
Old policy v1 and runs are not reinterpreted; existing contracts remain unchanged.

## ACCEPTED DECISION - current slice

Equal-priority Products; progressive proportional filling of requested quantities;
freeze all active users of every saturated Ingredient; unaffected Products continue.
Fractional servings are planning quantities, not physical sales or profit estimates.
Captured facts, dated yield/loss and exact units only. Expiry usable through X,
close-X remainder expires once. FEFO known expiry, known receipt, stable lot UUID;
unknown receipt stays unknown. Positive tracked stock with unknown expiry blocks.
Operational lots received after capture are not hypothetical scheduled inbound.
Version serving/FEFO semantics; later changes cannot reinterpret historical runs.

## ACCEPTED DECISION - future direction, not implemented in S3.3

- LEAN/BALANCED/PROTECTED construct on LOW/BASE/HIGH respectively; every fixed basket
  evaluated on all three paths. Strategies and paths remain distinct, no probabilities.
  This supersedes ADR-016's P50+alpha*(P75-P50) construction under a future policy v2;
  the existing frozen policy v1 boundary is retained for historical compatibility.
- Discrete basket marginal heuristic using the same serving/FEFO evaluator, including
  joint Ingredient activations for recipe complementarity. No global optimality claim.
  Supplier offers evaluated jointly with pack/MOQ, budget, arrival and expiry;
  never lock the lowest unit-cost offer before basket evaluation.
- If no candidate meets BASE target: TARGETS_NOT_MET, no recommended_strategy;
  separate best_available only for fully evaluated hard-valid candidates. Exact
  best_available ranking and candidate-search termination remain pending specification.
- Execution completion and business outcome are separate: completed evaluation may
  retain package without winner. Migration/lifecycle/public contracts implemented
  in a later authorized slice; unchanged S1 still requires winner at completion.
- Failure to find a passing candidate is not proof of global infeasibility.

## PENDING SPECIFICATION

Heuristic move enumeration/termination/tie rules, exact best_available ranking,
safety-floor treatment, supplier-search tie policy, policy-v2 contract wiring,
no-winner schema/lifecycle, auth/API and retained Decision capture/replay. None is
invented by the serving foundation. No procurement/recommendation code in S3.3.

References: [serving](../features/SERVING_FEFO.md),
[task notes](../runbooks/FULL_TEST_FLOW.md), [ADR-016](ADR-016-decision-contracts-provisional-demo-policy.md).
