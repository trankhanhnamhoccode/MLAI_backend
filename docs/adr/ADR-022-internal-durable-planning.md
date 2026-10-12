# ADR-022 — Internal durable planning aggregate

Status: ACCEPTED only for the intent explicitly authorized in user task S3.6.4,
2026-10-09. Concrete storage/process choices below are delegated TECHNICAL CHOICES,
not approval of HTTP/auth/config policies, a worker service or new business rules.

## ACCEPTED DECISION

Persist atomic C02 acceptance with original presence-sensitive request, resolved
configuration, receipt, actor/Store/operation-scoped idempotency; queued/running/
completed/failed lifecycle; captured input/provenance before computation; verified
result/partial facts; fresh scoped reads. Indefinite retention, no expiry/purge.
Keep no-winner completion and execution-error partial recommendation distinct.
Search incomplete/unproven is not a technical failure or infeasibility certificate.
No orders/customer selection. Trusted internal identity is not authorization.

Short owned transactions, fenced claim, resources closed before solver. Only
recognized uncertain commit can reconcile to success through fresh aggregate
verification. Programming errors remain errors, including after durable completion.
Cleanup preserves primary failure. Recovery needs evidence the owner process exited,
not startup of another process, elapsed time or a new UUID.

## TECHNICAL CHOICES

Add `planning_runs`, a separate resource, rather than altering S1 DecisionRun/package
v1 or forcing no-winner/failed partial output into its winner-required writer.
One public run UUID; no job UUID. Planning storage/1 and positive package version1
are distinct from operational capture2. Old S1/S2 schemas/readers remain unchanged.
ADR-005's auditable aggregate intent is preserved; this new resource carries that
responsibility for planning. No historical package reinterpretation/supersession.

One JSONB aggregate holds request/config/receipt and optional capture/result; typed
schema, role-separated SHA-256 request/input/result/aggregate digests and identity
columns verify it. A unique actor+Store+C02+key-digest constraint serializes acceptance.
Core PostgreSQL ON CONFLICT waits for the conflicting acceptance transaction.
Own row locks only for claim/retain/finalize/recovery, never during computation.
No arbitrary snapshot/delete writer; privileged SQL remains able to bypass guards.

OS PID plus process creation identity and host identify the actual incarnation.
Windows uses OpenProcess/GetProcessTimes and a zero-wait process-handle signal
check (exited processes can retain handles); Linux uses /proc boot id/start ticks.
Alive owner is protected; access-denied/foreign host/unsupported OS is UNKNOWN.
PID reuse proves that the recorded incarnation exited. Dead owners become
failed/PROCESS_INTERRUPTED without recomputation. Thread-only abandonment in a
living process cannot be inferred and remains running pending future worker design.

Acceptance accepts typed detached resolved input, or a trusted provider invoked
inside its transaction. The latter is an integration seam for a future consistent
DB configuration adapter, not its implementation or an isolation/auth guarantee.
Retries inspect retained original request before touching any new source.

## Rollback and limits

Migration0009 adds only planning_runs/FKs to Store and User; no backfill or old table
change. Downgrade drops only new history and is destructive to it; it is not a
deployment rollback for retained real data without export. Only disposable test DB
migrations are authorized here. New FK identity does not enforce membership/auth.
Pure exact schema checks on read have measurable cost; no latency SLA.
Hash integrity is not source authenticity or tamper-proof audit. Replay is retained
read, not automatic rerun; computation implementation availability is not promised.
HTTP/worker/auth/config/saved adapters/forecast orchestration remain backlog.
