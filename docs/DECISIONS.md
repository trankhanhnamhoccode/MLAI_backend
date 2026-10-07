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
| ADR-013 | Future Store mapping and approval direction | ACCEPTED (future behavior) | Authorized self-approval, source/report profiles, reviewed immutable mapping versions, deterministic execution and version audit; not implemented | [ADR-013](adr/ADR-013-future-store-mapping-approval-direction.md) |
| ADR-014 | Retained internal baseline execution | ACCEPTED | Read-only snapshot capture, atomic run+JSONB input, versioned SHA-256, baseline execution/replay and explicit failure outcomes | [ADR-014](adr/ADR-014-retained-baseline-execution.md) |
| ADR-015 | Trained observed-sales forecast/evaluation/artifacts | ACCEPTED by explicit remaining-S2 implementation delegation | Provisional mechanics policies, fixed LightGBM, selection, immutable artifacts and typed retained execution metadata | [ADR-015](adr/ADR-015-trained-observed-sales-forecast.md) |

Preserve accepted ADR intent. Gather evidence and propose a linked replacement when
intent should change; do not quietly modify an accepted decision to simplify coding.

ADR-008/009 remain unchanged. See ADR-010 for missing/ambiguous source facts and incomplete inventory data.
