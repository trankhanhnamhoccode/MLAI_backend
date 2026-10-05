# S1.4 task contract

CURRENT FACT: head 0005, thirteen business tables, sync PostgreSQL Sessions,
health-only API. Preserve all prior uncommitted S1.3/S1.3.1 files and migrations.
ACCEPTED DECISION: ADR-001/004/005/006/007/008/009/010 plus new ADR-011 govern this slice.

Freeze three persistence contracts, then test actual PostgreSQL constraints/fresh-session
JSON/Decimal/time reads, independent historical values and fresh/down/up migration.
Add only three typed models and static migration 0006. No computation or public API.
Adapt existing exact head/table assertions and no-op seed expectations; keep reset guards.

Affected: BE persistence and tests; FE/ML/demo claims unchanged except inspectable schema.
Rollback drops these three run tables only; backup desired historical fixtures first.
Current API and previous models/ADRs/migrations are preserved by pre-task file hashes.

S1 overall remains IN PROGRESS: the roadmap's validated read/write/application-boundary
contract gates are not implemented by schema tests. The next persistence-access slice
will be PROPOSAL only; do not start S2 or implement it automatically.
