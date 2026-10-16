# ShelfCash runtime architecture

CURRENT FACT self-service: T03 dùng Auth User/session fence hiện hành, concrete
StoreCreationRepository và same transaction cho Store/Owner/audit/receipt. Không
service mới, broker hoặc operator endpoint. Một email worker hiện có xử lý thêm
invitation queue qua existing durable dispatcher; không second delivery process.
Customer local launcher owns `.venv`/TLS/storage/config của checkout chính; test DB
và runtime/migration roles tách riêng, không phụ thuộc sibling worktrees.

## ACCEPTED DECISION ? authority and boundaries

[Accepted ADRs](DECISIONS.md) own architectural intent. This document describes
current composition separately from future behavior; source/tests own runtime
facts. The backend owns forecast, BOM, inventory/FEFO, procurement, constraints,
feasibility, simulation, comparison and recommendation. LLM may only assist
approved ambiguous Excel semantics or authorized wording; it cannot create facts,
choose plans, alter calculations or bypass permissions. Core decisions work with
provider unavailable (ADR-001/004).

One native FastAPI modular monolith, local storage and PostgreSQL17 via synchronous
SQLAlchemy2/psycopg Sessions and explicit Alembic migrations (ADR-002/007). Compose
uses named volumes. No MongoDB, microservices, broker, Celery, Kafka, generic agents,
CQRS/event sourcing or speculative infrastructure. Reset is guarded development/
test tooling, not normal startup or a product permission.

## CURRENT FACT ? dependency direction

Assistant L3 AS03 wires AssistantChat to PublicPlanning retained consistency reads,
bounded structured context, question-specific obligations, typed assertion proposals,
independent deterministic surface/slot checks and optional conversational provider.
Versioned intent composition combines common instructions, scoped facts/context,
evidence availability and bounded non-authoritative placeholder examples. Historical
context/validator implementations stay pinned for immutable replay. No model judge.
One semantic regeneration shares deadline/cost bounds; independent optional trimming
and unique exact numeric-slot repair require final revalidation. Legacy grammar
remains pinned for old receipts and a supported complex-assertion subset. No solver/worker/live catalog
dependency. Existing deterministic receipts remain immutable/readable; additive
chat_generations owns accepted/running/completed/failed claim fencing and pins
request/profile/evidence/selection/prompt/schema/validator. Current authority repeats
before projection/acceptance, after metadata preflight immediately before completion,
and at publication/delivery/replay. Provider/preflight waits hold no Session/connection;
brief authority transactions close before network. No generic LLM framework/queue.
The L2 optional summary provider remains separate; its configured empty route now
means explicitly permitted default OpenRouter routing with fallback disabled.

```text
API / Pydantic DTO boundary
  -> application use cases and typed captured values
  -> pure domain computations
  -> concrete persistence/provider/storage adapters at composition boundaries
```

Domain has no FastAPI/ORM/HTTP/LLM/filesystem dependency or imports from app.api/
app.models/infrastructure. Pydantic lives at typed boundaries; declarative models
stay in persistence. Concrete repositories own explicit data access and never
commit/rollback; application paths own transactions. No generic base service,
service locator, implicit global mutable business state or default async domain.

`app/main.py` wires Auth/Staff, public reads/stock/calendar, Import, configuration/
readiness, forecast serving, durable public Planning, history, private PDF and
Notifications/permission requests/mapping submissions. Concrete collaboration and
notification repositories own queries; application owns the same authority fences,
atomic business/audit/receipt/intent transitions and explicit commit. Permission union
and request-state computation remain plain Python domain functions.
Each Import/Planning/PDF/account-email/notification flag independently opts into one bounded local
lifespan thread in the same backend process. Default flags are OFF.

## CURRENT FACT ? computation and transaction boundaries

- Public reads/mutations use current User/session/Store/membership/grant fences.
  Trusted internal S1/S2/S3 commands are separate entrypoints, not permission APIs.
- B1 signup accepts account/token/encrypted email intent atomically. A shared local
  dispatcher serves invitation and verification queues; SMTP runs outside Sessions.
  User/account/token fences serialize verification with proof/credential changes;
  successful verification gives no session or Store authority. B2 reuses this
  dispatch loop with RESET credential tokens and a separate FK-bound encrypted
  intent table; N7 owns atomic password transition/session revocation.
- B3 reuses the Staff recipient User/session/Store/invitation fences and existing
  append-only invitation-event/idempotency storage for a decline terminal. It
  does not write membership/grants or dispatch new email; sorted locks serialize
  it with accept/revoke, and current proof/issuer authority precede receipt replay.
- B4 synchronizes the Product-approved permissions-v3 catalogue and persisted
  grants CHECK. It adds no domain workflow or automatic Staff grants; HTTP/PG
  acceptance links the existing Auth/Staff boundaries with fake delivery.
- Import stores original blobs/profiles/preview/audit in PostgreSQL; reviewed
  mappings execute deterministically. Canonical batch commit and its receipt/
  audit are atomic. Upload, mapping approval and preview are not canonical writes.
- Forecast captures detached Store-scoped sparse observed sales; baseline/trained
  execution closes Sessions before model/filesystem work. Inputs, actual model
  identity, warnings and metrics stay retained. Immutable local model artifacts
  are published before DB start; filesystem/DB are not a single transaction.
- Planning acceptance retains original intent/resolved versions; worker retains
  captured input before compute. Detached operational/2 composes BOM, exact FEFO,
  native MILP candidates and exact validation/comparison/selector outside DB locks.
  /1 historical callers and S1 DecisionRun semantics are preserved.
- Durable claims fence publication. Only uncertain commit with verified fresh
  retained aggregate may reconcile as success. Only OS-proven dead owner process
  incarnations recover as failed; no elapsed-time guess or automatic recompute.
- Assistant evidence reads verify snapshots/digests/current rights using retained
  equation/relationship checks without engine/provider calls. Existing default
  C03/PDF cold validators still replay exact BOM/serving/selector checks: explicit
  technical debt, not a no-recomputation guarantee for those old callers.
  Summary uses synchronous durable acceptance/claim, closes Sessions before
  optional bounded provider presentation, then rechecks rights/versions and fences
  immutable publication; GET reads do no generation/recovery. PDF has its own durable export aggregate, local private bytes, verified
  SHA/size and rights at acceptance/materialization/publication/download.

## ACCEPTED DECISION ? historical and hypothetical meaning

Capture values before calculation; never reconstruct historical output from live
rows. Completed content is historical; rerun creates a new run. Versioned packages
start at1. Fingerprint/hash integrity is not source authenticity or tamper-proof
security. What-if is deterministic/hypothetical and nonpersistent by default.
P25/P50/P75 are demand quantiles, not strategies. Recommendations do not place orders.

## TECHNICAL DEBT / PROPOSAL

Internal ORM/privileged SQL may bypass guards; public fences do not retrofit all
trusted writers. Cold retained validation remains slow. Real-data quality,
operational purge, one-time approvals, what-if/copilot/order/selection workflows
need explicit acceptance. ADR-013 permits authorized self-approval; the current
product contract restricts reusable-profile approval/activation to Owner without
requiring separate creator and approver. Its original unimplemented status is
historical; [CURRENT_STATE](CURRENT_STATE.md) records implemented workflows.

Detail: [domain](DOMAIN_MODEL.md), [schema](DATABASE_SCHEMA.md),
[API](API_CONTRACT.md), [Import](IMPORT_MAPPING_API_CONTRACT_VI.md),
[Planning](PROCUREMENT_API_CONTRACT_VI.md), [Authorization](AUTHORIZATION_CONTRACT_VI.md).
