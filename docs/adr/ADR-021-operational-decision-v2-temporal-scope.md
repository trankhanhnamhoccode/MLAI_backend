# ADR-021 — Explicit operational /2 temporal basis and computed scope

Status: ACCEPTED only for intent explicitly authorized by the S3.6.2 task,
2026-10-09. This is not approval of HTTP/auth/storage or a new business policy.

## ACCEPTED DECISION

Add opt-in operational_decision/2, operational_capture/2 and operational_pipeline/2
entrypoints. They compose captured operational values with existing procurement/2,
comparison/2 and procurement_selector/1. Keep operational /1 callers and guards,
historical evidence, S1/S2 lifecycle and exact serving/ranking unchanged.

Execute the user-approved planning P1 with an explicit operational_basis/1 on
capture_version=2. Actual capture timestamp/local date remains distinct from the
planning order instant. Same-day uses CURRENT_CAPTURE; other dates use
HYPOTHETICAL_CURRENT_CAPTURE with NONCURRENT_PLANNING_CURRENT_FACTS warning.
Never relabel current balances as historical inventory or predict intervening
stock evolution. Preserve original receipt/expiry/effective dates. No PO/movement writes.

Capture the active menu and preserve original effective requirements/declarations.
Project only known computable Products and dependencies. Retain exclusions/reasons,
dates, raw facts, source times, budget/policy/fee provenance and override NOT_EVALUATED
audit. Unknown attribution blocks the whole capture; invalid override is an input
error. Remaining relevant blockers cannot disappear to make a recommendation.

One owned read-only REPEATABLE READ source closes all resources before computation.
No post-compute operational query, auth assumption, current-input rebuild or persistence.
Unknown budget/fees/constraints never become unlimited/zero/unconfigured defaults.
Preserve numeric unsupported, unproven search, technical error and no-eligible meanings.

## TECHNICAL CHOICES / implementation details

PreparedDecisionInput has optional operational_basis accepted only for explicit
capture2. Without it, all old day-start/as-of assumptions remain mandatory. Old
implicit comparison identities elide the absent new field; explicit basis participates
in new identities. Snapshot schema number remains 1; this opt-in metadata is covered
by capture2 and basis/1, not a persisted DecisionRun format upgrade. S1 package rejects capture2.

Separate /2 PostgreSQL source reuses the existing scoped repositories and owned
session cleanup. It retains scoped Ingredient/term identities when invalid row values
are localized, avoiding invented fallback values or losing dependency attribution.
The duplicated repository-read orchestration is limited technical debt; do not refactor
or move /1 callers merely to deduplicate this slice.

The explicit budget selection captures both effective limit and Store ceiling, with
budget version/provenance. A lower effective limit tightens the unchanged captured
physical ceiling; it does not overwrite that constraint. This executes the already
accepted planning budget semantics. Unknown/greater limits or a ceiling mismatch
block. Historical /1 and /2 envelopes without operational basis keep equality guards.

For a past scenario, a lot's current captured balance becomes eligible on its original
receipt date if that date falls after planning start. The adapter represents this as
a hypothetical activation in serving lot arrivals; it is not a real historical receipt
quantity or committed inbound. Same-day/future-start balances begin at planning start
if already received at capture; future-dated operational lots remain excluded throughout.
Physical values/dates are never rewritten. Original expiry still disposes the balance.
Native generation and independent exact serving validation use the same date admission,
without changing progressive allocation or FEFO ordering.

Full /2 result boundary reconciles BOM values with retained snapshot as well as nested
engine/comparison/selection evidence. Timings are wall diagnostics; final business graph
revalidation is measured, then only freshly validated diagnostic timing is installed.
No model_construct/model_copy bypass of business validation; forged nested returns reject.

## CURRENT FACT / limits

Pure/unit verification and synthetic timing are recorded in S362_TASK_NOTES and
DECISION_OPERATIONAL_V2. Historical initial /2 acceptance was BLOCKED by Docker;
on 2026-10-09 it passed on guarded shelfcash_test: six /2 tests plus six /1 capture
regressions, 12 passed in 21.00s. [Acceptance report](../features/PROCUREMENT_V2.md)
records exact assertions and limits. Accepted intent above is unchanged.
S3.6.2 is COMPLETE within its internal scope. No durable acceptance, retention,
replay storage, background worker, resolver, forecast auto-generation/reuse,
HTTP or public capability exists. No development DB access or schema change.

References: [ADR-020](ADR-020-product-requirements-procurement-selector.md),
[planning contract](../PROCUREMENT_API_CONTRACT_VI.md),
[feature](../features/DECISION_OPERATIONAL_V2.md), [task notes](../runbooks/FULL_TEST_FLOW.md).
