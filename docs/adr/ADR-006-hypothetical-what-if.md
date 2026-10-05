# ADR-006 — What-if is hypothetical and non-persistent by default

## Status
ACCEPTED

## Context
Owners/staff need to explore alternatives without silently changing inventory,
budgets or real procurement decisions. Simulation permission differs from mutation.

## Decision
What-if is deterministic recomputation: baseline DecisionRun + explicit mutation →
hypothetical decision → baseline/hypothetical comparison → optional LLM explanation.
Potential mutations include demand multiplier, supplier delay, budget, promotion or
forced strategy. Results must not silently mutate/persist as real business state.
Backend enforces OWNER/STAFF and delegated permissions; the model cannot bypass them.
Staff may be allowed to simulate a budget without being allowed to change the real one.

## Consequences
Reuse deterministic business computation and preserved baseline facts. Distinguish
hypothetical results visibly and at API/application boundaries. Any later real-state
application requires a separate explicitly authorized action and validation.

## Rejected/Deferred alternatives
REJECTED: LLM-computed scenarios, automatic persistence as real state or implied
mutation permission from what-if access.
DEFERRED: mutation contracts, hypothetical-history storage and approval flows until S4/S6.

## Revisit conditions
A concrete requirement for saved hypothetical history or an apply workflow needs
an accepted design that preserves hypothetical/real separation and permission checks.

## Affected areas
Decision application/domain, API contracts, authorization, FE labels/approval,
persistence boundaries, tests and demonstrations.
