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
| ADR-003 | SQLite persistence for Competition Edition | ACCEPTED | Synchronous SQLAlchemy 2.x/SQLite; resets acceptable; explicit Alembic evolution | [ADR-003](adr/ADR-003-sqlite-persistence.md) |
| ADR-004 | Bounded LLM responsibilities | ACCEPTED | Only ambiguous Excel semantics and authorized summary/copilot wording | [ADR-004](adr/ADR-004-bounded-llm.md) |
| ADR-005 | DecisionRun is an auditable versioned snapshot | ACCEPTED | Self-contained historical context; package_schema_version starts at 1 | [ADR-005](adr/ADR-005-decision-run-snapshot.md) |
| ADR-006 | What-if is hypothetical and non-persistent by default | ACCEPTED | Deterministic baseline-plus-mutation recomputation; no silent real-state persistence | [ADR-006](adr/ADR-006-hypothetical-what-if.md) |

Preserve accepted ADR intent. Gather evidence and propose a linked replacement when
intent should change; do not quietly modify an accepted decision to simplify coding.
