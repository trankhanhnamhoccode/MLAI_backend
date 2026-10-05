# S1.3.1 task notes

Classification: ACCEPTED DECISION / scoped implementation plan.

Current contract: thirteen PostgreSQL business tables at 0004, synchronous Session,
health-only API. ADR-007/008/009 govern persistence, correction and audited inventory.
Existing uncommitted S1.3 work must remain intact. User examples are source-semantic
review inputs; no external dataset or import implementation is claimed.

Freeze ADR-010 before implementation. Keep per-pack SupplierTerm price and strict
effective_from/lead-time canonical inputs. Make only InventoryLot.received_date
nullable, without a default; expiry ordering applies when both dates are known.
Create 0005, preserving 0004 and accepted ADR-008/009 unchanged.

Acceptance: actual isolated PostgreSQL fresh-session NULL receipt persistence,
no date fallback, known-date order, strict supplier inputs and exact pack cost,
fresh migration and downgrade/re-upgrade, full regressions, unchanged OpenAPI/live
health. Rollback refuses unknown receipt dates instead of inventing facts; reset or
resolve them using confirmed source facts before restoring NOT NULL.

Affected: backend persistence and local manual verification/docs. No frontend/API,
ML, import, repository or demo business seeding changes. S1.4 is unauthorized.
