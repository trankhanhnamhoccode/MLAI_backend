# Architectural decision index

ACCEPTED DECISION: only **ACCEPTED** ADRs are architectural authority. A proposal
does not become accepted by appearing in another document. Implementation reality
belongs in CURRENT_STATE; report drift rather than hiding it by editing decisions.

| Status | Meaning |
| --- | --- |
| PROPOSED | Under consideration; not authority |
| ACCEPTED | Approved architectural intent governing applicable work |
| SUPERSEDED | Replaced by an explicitly linked accepted decision; historical record |
| REJECTED | Considered and declined; not authority |
| DEFERRED | Deliberately postponed; not authority |

| ADR ID | Title | Status | Short decision | File |
| --- | --- | --- | --- | --- |
| ADR-022 | Internal durable planning aggregate | ACCEPTED only by explicit S3.6.4 task intent; storage details delegated | Separate PlanningRun, atomic scoped acceptance, retained input/result, fencing, verified process recovery and fresh reads; preserve S1/S2, no HTTP/auth/worker policy | [ADR-022](adr/ADR-022-internal-durable-planning.md) |
| ADR-021 | Operational /2 temporal basis and computed scope | ACCEPTED only by explicit S3.6.2 task intent | Opt-in capture/pipeline2 with P1, preserved raw menu/exclusions/effective inputs; no /1/S1/S2 rewrite or HTTP/persistence approval | [ADR-021](adr/ADR-021-operational-decision-v2-temporal-scope.md) |
| ADR-020 | Product requirements and internal selector | ACCEPTED by explicit S3.6.1 task; limited supersession | New procurement/2 per-Product100% construction/customer requirements, max-min/mean/cost fallback, exact-valid winner; preserve historical /1 and S1 lifecycle | [ADR-020](adr/ADR-020-product-requirements-procurement-selector.md) |
| ADR-018 | Procurement optimization review | PROPOSED, not authority | User reopens ADR-017 heuristic choice; proposed policy-faithful formulation and benchmark gate, no engine accepted | [ADR-018](adr/ADR-018-procurement-optimization-review.md) |
| ADR-017 | Serving/FEFO and revised provisional direction | ACCEPTED by user; partial supersession ADR-016/011 | Progressive serving; future basket heuristic/joint supplier evaluation, LOW/BASE/HIGH construction, no-BASE-pass no recommendation and no-winner completed persistence direction; implementation scope pure serving/FEFO only | [ADR-017](adr/ADR-017-serving-fefo-provisional-direction.md) |
| ADR-016 | Decision contracts and provisional demo policy | ACCEPTED historical boundary; policy portions superseded by ADR-017 | Opt-in S3.1 contracts; user-authorized provisional demo v1; no computation, allocator acceptance, API or S1 fixture change | [ADR-016](adr/ADR-016-decision-contracts-provisional-demo-policy.md) |
| ADR-001 | Backend owns business authority | ACCEPTED | Deterministic backend owns facts, feasibility, risk and recommendation; LLM only approved semantics/wording | [ADR-001](adr/ADR-001-backend-business-authority.md) |
| ADR-002 | Modular Monolith for Competition MVP | ACCEPTED | One FastAPI modular monolith; no distributed infrastructure without concrete need | [ADR-002](adr/ADR-002-modular-monolith.md) |
| ADR-003 | SQLite persistence for Competition Edition | SUPERSEDED | Historical scaffold decision; superseded by ADR-007 before business schema/data | [ADR-003](adr/ADR-003-sqlite-persistence.md) |
| ADR-004 | Bounded LLM responsibilities | ACCEPTED | Only ambiguous Excel semantics and authorized summary/copilot wording | [ADR-004](adr/ADR-004-bounded-llm.md) |
| ADR-005 | DecisionRun is an auditable versioned snapshot | ACCEPTED | Self-contained historical context; package_schema_version starts at 1 | [ADR-005](adr/ADR-005-decision-run-snapshot.md) |
| ADR-006 | What-if is hypothetical and non-persistent by default | ACCEPTED | Deterministic baseline-plus-mutation recomputation; no silent real-state persistence | [ADR-006](adr/ADR-006-hypothetical-what-if.md) |
| ADR-007 | PostgreSQL Persistence Baseline | ACCEPTED | PostgreSQL/psycopg, synchronous SQLAlchemy 2.x, Alembic, local Compose named volume and guarded resets | [ADR-007](adr/ADR-007-postgresql-persistence-baseline.md) |
| ADR-008 | Import Idempotency and Correction Policy | ACCEPTED | Content/business identity, no duplicate/replace-all writes; domain-specific corrections and provenance; import remains future | [ADR-008](adr/ADR-008-import-idempotency-correction-policy.md) |
| ADR-009 | Inventory Mutation and Audit Policy | ACCEPTED | Received lot current balance + justified movement history; future atomic audited mutations, not Event Sourcing | [ADR-009](adr/ADR-009-inventory-mutation-audit-policy.md) |
| ADR-010 | Data Completeness and Missing Business Facts Policy | ACCEPTED | No invented facts; explicit completeness/origins/readiness; unknown receipt dates remain NULL | [ADR-010](adr/ADR-010-data-completeness-and-missing-business-facts.md) |
| ADR-011 | Historical Run Immutability and Snapshot Policy | ACCEPTED | Completed runs historical; rerun creates new run; compute from captured values; versioned packages, future service enforcement | [ADR-011](adr/ADR-011-historical-run-immutability-snapshot-policy.md) |
| ADR-012 | Observed-sales forecast execution contract | ACCEPTED | Store-local D cutoff, explicit Products, D+1..D+7, captured canonical sparse sales, full output coverage; no algorithm/readiness threshold | [ADR-012](adr/ADR-012-observed-sales-forecast-execution-contract.md) |
| ADR-013 | Future Store mapping and approval direction | ACCEPTED; not superseded | Authorized self-approval, source/report profiles, reviewed immutable mapping versions, deterministic execution and version audit; original implementation status is historical, current Owner-only authority is detailed in the Import/Authorization contracts | [ADR-013](adr/ADR-013-future-store-mapping-approval-direction.md) |
| ADR-014 | Retained internal baseline execution | ACCEPTED | Read-only snapshot capture, atomic run+JSONB input, versioned SHA-256, baseline execution/replay and explicit failure outcomes | [ADR-014](adr/ADR-014-retained-baseline-execution.md) |
| ADR-015 | Trained observed-sales forecast/evaluation/artifacts | ACCEPTED by explicit remaining-S2 implementation delegation | Provisional mechanics policies, fixed LightGBM, selection, immutable artifacts and typed retained execution metadata | [ADR-015](adr/ADR-015-trained-observed-sales-forecast.md) |
| ADR-A1 | Observed stockout and demand inputs | ACCEPTED under explicit A1 request | Schema-2 causal demand inputs; preserves v1 replay; targeted owned-DB persistence acceptance complete | [ADR-A1](adr/ADR-A1-observed-stockout-demand-policy.md) |

CURRENT FACT S3.4.1: the user explicitly reopened ADR-017's procurement heuristic
selection, without changing serving/FEFO or accepting MILP. Its old accepted text
is preserved as a historical decision record; that algorithm choice is under review,
not a closed constraint for new procurement work. ADR-018 proposes supersession
of that portion only if approved. No other ADR is changed by this design slice.

Preserve accepted ADR intent. Gather evidence and propose a linked replacement when
intent should change; do not quietly modify an accepted decision to simplify coding.

ADR-008/009 remain unchanged. See ADR-010 for missing/ambiguous source facts and incomplete inventory data.


## S3.4.4 — ACCEPTED DECISION / CURRENT FACT (2026-10-08)

[ADR-019](adr/ADR-019-internal-procurement-engine.md) records explicit user approval
for internal policy-faithful MILP candidate generation + exact canonical validation,
bounded exclusions and opt-in finite certification. It supersedes only ADR-017's
procurement algorithm choice. ADR-018 remains a historical PROPOSED review gate.
Procurement/1 requires business targets/configuration rather than accepting scratch
constants as defaults. No policy-v1 reinterpretation or persistence/API/selector approval.
