# Target Competition MVP architecture

## Current S2 trained extension -- CURRENT FACT

ADR-015 adds concrete infrastructure LightGBM/storage and application rolling evaluation/
trained execution. Plain domain contains only causal features/metrics/baseline/validation.
A concrete trained use case shares S2.3 capture/recovery; no engine registry. Snapshot,
start and completion Sessions close before model/artifact work. Purpose-specific
metadata stores selection/warnings; metrics_json remains evaluation only. S1 and fixed
baseline semantics are preserved. See features/FORECAST_TRAINED.md.

## Retained baseline and historical slice boundaries

CURRENT FACT (S2.3): trusted Engine-composed internal orchestration owns short read-only
REPEATABLE READ capture and atomic start/completion Sessions; domain computation runs
with no DB transaction. Prepared inputs are retained as separate PostgreSQL JSONB
records with versioned SHA-256 and replay integrity checks (ADR-014). No public API,
auth framework, model service or recovery worker. The S2.2 pure functions below remain
unchanged in semantics; their earlier lack of persistence wiring is historical.

HISTORICAL INFORMATION (S2.2 slice boundary): a small internal application boundary revalidates S2.1 captured
input, calls pure domain per-Product baseline readiness/Decimal quantiles, then
validates complete output. No Session, DB lookup/write, trained model, provider,
artifact/evaluation service or public API. See
[FORECAST_EXECUTION](features/FORECAST_EXECUTION.md). This supersedes earlier
forecast-computation absence statements only for the in-memory historical baseline;
it changes no accepted architecture/ADR or S1 lifecycle.

This document describes **target architecture**, not runtime implementation.
ACCEPTED DECISION sections derive from active ADRs 001, 002, 004–011. Layout details and future
contracts are PROPOSAL until their slice accepts them. See CURRENT_STATE for reality.

## System context — ACCEPTED DECISION

ShelfCash serves Vietnamese F&B stores. The question is:
“Trong kỳ kế hoạch tiếp theo, cửa hàng nên nhập nguyên liệu gì, bao nhiêu, khi nào
và theo chiến lược nào để cân bằng thiếu hàng, lãng phí và vốn?”
The backend supplies deterministic evidence and recommendations; the human owns
the final business decision. Forecast alone is not the product: simulation,
strategy comparison and recommendation form the Decision Intelligence layer.

```mermaid
flowchart LR
    Human[Owner / manager / authorized staff] --> UI[Future frontend]
    UI --> BE[ShelfCash FastAPI modular monolith]
    Files[Operational data / Excel] --> BE
    BE --> DB[(PostgreSQL)]
    BE --> Storage[Local uploads / model artifacts]
    BE -. optional semantic or wording tasks .-> LLM[Bounded LLM gateway]
    BE --> Human
```

## Dependency direction — ACCEPTED DECISION

```mermaid
flowchart TD
    Route[FastAPI routes / Pydantic boundaries] --> App[Application use cases]
    App --> Domain[Plain Python domain computation]
    App --> Ports[Repository / gateway contracts]
    Infra[Infrastructure implementations] -. implements .-> Ports
    Composition[Application composition] --> Infra
    Composition --> App
    Infra --> PostgreSQL[SQLAlchemy / synchronous Session / psycopg / PostgreSQL]
    Infra --> Local[Local storage]
    Infra --> Gateway[Optional bounded LLM gateway]
```

Execution flows from route to use case to domain/repository contracts and wired
infrastructure. Infrastructure implements boundaries; domain computation does not
import it. Introduce an interface only when a concrete use case needs it.

One FastAPI modular monolith, synchronous application/domain code and synchronous
SQLAlchemy Session are the baseline. An external HTTP integration may later use
async internally without converting domain/application computation to async.
No microservices, brokers, Kubernetes, distributed architecture, enterprise IAM,
event sourcing, CQRS or generic agent framework.

Routes handle transport and validated schemas. Application coordinates authorization,
transactions and use cases. Domain owns plain Python business rules. Repositories
persist/query; ORM models encode persistence, not business computation. PostgreSQL and
local storage are infrastructure. Trained ML artifacts are immutable local files, with
versions captured in decision provenance. CURRENT FACT: S1.5 concrete repositories
in app/repositories take a caller-owned synchronous Session; no generic abstraction.
See [persistence access](features/PERSISTENCE_ACCESS.md) for the accepted internal contract.

## Local persistence topology — ACCEPTED DECISION (ADR-007)

CURRENT FACT: `compose.yaml` defines PostgreSQL 17 with a `pg_isready` healthcheck,
localhost port 5432 (configurable), and a named `shelfcash-postgres-data` volume.
Native backend/venv development is supported; no backend Dockerfile exists.
Runtime verification evidence is recorded in CURRENT_STATE.

```text
Developer machine
├── backend / Python venv (FastAPI, SQLAlchemy, psycopg)
└── Docker Compose
    └── PostgreSQL
        └── shelfcash-postgres-data named volume
```

```mermaid
flowchart TD
    Client[Client / Developer] --> FastAPI
    FastAPI --> Application
    Application --> Repository[Concrete domain repository]
    Repository --> SQLAlchemy[SQLAlchemy / synchronous Session / psycopg]
    SQLAlchemy --> PostgreSQL[(PostgreSQL)]
```

CURRENT FACT: health performs no persistence operation. S1.1/S1.2/S1.3 implement
sixteen ORM tables: identity/store, catalog/recipe, supplier/terms, canonical sales,
lot/movement, controlled planning constraints and S1.4 Forecast/Decision run storage.
S1.6 internal application paths now connect explicitly through repositories;
business API paths remain future work. Migrations,
developer commands, explicitly invoked use cases and integration tests connect. PROPOSAL: a backend
container may later use Compose host `postgres`; it is not part of this slice.

ACCEPTED DECISION (S1.5): application/use case owns the transaction and supplies
one synchronous Session to all participating repositories. Repositories never
commit, roll back, close that Session or create their own Session. Internal
Forecast/Decision lifecycle writers lock a Store-scoped RUNNING row before staging
terminal fields; no computation, public API or generic state-machine framework.

## Import correction and inventory audit — ACCEPTED DECISION (ADR-008/009)

Future import uses content/business identity, not filename. UNCHANGED performs no
business write; NEW validates before insert; CHANGED follows domain correction
policy; INVALID/CONFLICT are explicit. No generic upsert/replace-all; missing source
rows are not automatically deleted. Preserve provenance and explicit import mode.
CURRENT FACT: no import/hash/parser/classification/mode/correction code exists.

Inventory uses actually received lot current state + movement history, not Event
Sourcing. Future services create movement and change materialized balance in one
protected transaction; no unexplained overwrite or expired-lot deletion. Incoming
stock is not InventoryLot; expired lots have no usable future-demand quantity.
CURRENT FACT: S1.3 stores/constraints these relationships and signs, but no mutation
service, balance trigger, immutable ledger enforcement, expiry logic or FEFO exists.
Mandatory expiry for tracked ingredients and exact budget currency matching remain
future application validation; no framework/trigger was introduced to fake them.

## Business pipeline — ACCEPTED DECISION, future behavior

```mermaid
flowchart TD
    Operational[Operational data] --> Forecast[Forecast P25 / P50 / P75]
    Forecast --> BOM[BOM / recipe expansion]
    BOM --> Demand[Ingredient demand]
    Demand --> Inventory[Inventory / FEFO]
    Inventory --> Constraints[Supplier / business constraints]
    Constraints --> Candidates[LEAN / BALANCED / PROTECTED candidates]
    Candidates --> Simulation[Deterministic exact simulator: every candidate]
    Simulation --> Comparison[Strategy comparison]
    Comparison --> Recommendation[Backend recommendation]
    Recommendation --> Package[Auditable DecisionRun: package_schema_version 1]
    Package --> Explanation[Optional explanation / deterministic what-if]
    Explanation --> Human[Human decision]
```

P25/P50/P75 express demand uncertainty; they are not procurement plans.
Exactly three procurement strategies exist: LEAN accepts more shortage risk for
lower capital/inventory; BALANCED balances purchase cost, fill rate, waste and risk;
PROTECTED prioritizes availability while accepting more inventory/cost. Every
candidate is simulated before deterministic comparison selects the recommendation.
Scoring weights, tie breaks and failure handling remain PROPOSAL.

## Authority boundaries — ACCEPTED DECISION

Backend owns forecast results, BOM, ingredient demand, inventory balances/FEFO,
procurement quantities, candidate feasibility, strategy/scenario selection, risks,
constraints, cost, simulation and recommendation. Core decisions continue to work
when all LLM providers are unavailable. No LLM dependency enters domain computation.

Allowed future LLM work is limited to genuinely ambiguous Excel semantics,
authorized overall-summary wording and Decision Copilot/explanation wording.
Mapping flow: approved known profile → deterministic mapping; otherwise rule mapper
→ confident deterministic mapping OR genuinely ambiguous LLM suggestion → backend
validation → human approval if required. LLM cannot invent canonical fields/schema.
Provider failure leaves ambiguity unresolved for human review; it does not create facts.

Copilot flow: natural language → authorized intent/tool selection → deterministic
backend computation → structured authorized facts → optional LLM wording. The model
may select an allowed tool, never replace its computation or bypass authorization.

DecisionRun captures self-contained versioned inputs/outputs, evidence, warnings,
risks, candidates, simulation and recommendation. Historical meaning cannot silently
change with today's inventory, supplier terms or constraints. Complex output may be
a versioned JSON package; important forecast quantiles stay explicitly modeled.

What-if: baseline DecisionRun + mutation → deterministic recomputation → hypothetical
decision → baseline comparison → optional explanation. Hypothetical output never
silently becomes real store state. Demand multiplier, delay, budget, promotion and
forced strategy are future mutations, not implemented APIs.

Future simple RBAC uses OWNER/STAFF plus delegated permissions, always enforced
by backend. Permission to simulate a budget differs from permission to change it.
Authorization details and public endpoints await accepted slice contracts.

## Source completeness boundary -- ACCEPTED DECISION (ADR-010)

Canonical facts must not be invented to fill missing source values. Future mapping
retains unknown/ambiguous evidence and evaluates computation readiness per use case.
Current S1.3.1 schema permits unknown lot receipt date without date defaults; strict
SupplierTerm procurement inputs remain required. No import/readiness service, public
warning API or staging table is implemented. S1.6 application inputs preserve missing
optional facts and reject missing required facts; they do not add a readiness engine.

## Historical runs -- ACCEPTED DECISION (ADR-011)

Future computation loads authorized inputs, builds a canonical snapshot, computes
from that exact snapshot and persists versioned results. Completed runs are historical;
reruns create new UUIDs. Historical interpretation uses copied values/versions, not
current mutable joins. Future services enforce immutability and package validation;
no trigger or generic immutable framework exists. CURRENT FACT: three typed models
and migrations implement persistence only. Forecast now implements captured-input hashing, baseline/trained computation and
immutable artifact/retained replay under ADR-014/015. Decision computation and public
business APIs remain NOT STARTED. Earlier schema-only statements are historical.
CURRENT FACT: S1.5 inserts new run aggregates and reads history through scoped
repositories. Minimal RUNNING -> COMPLETED/FAILED and RUNNING-only prediction
append guards now exist in repository writers. Direct tracked ORM/SQL mutation can
still bypass policy; operational services/full business validation remain future.
Algorithm metadata belongs in future versioned packages; no engine-version framework
is introduced. ADR-006 What-if and ADR-004 LLM authority boundaries are unchanged.

## Internal application contracts -- ACCEPTED DECISION / CURRENT FACT (S1.6)

API contract != Application contract. Future HTTP / Import / internal caller ->
typed application contract -> use case -> concrete repositories -> SQLAlchemy ->
PostgreSQL. Application owns transaction; repository owns persistence operations;
future engine owns deterministic business computation. No public business API exists.

Pydantic v2 inputs/outputs contain explicit schemas, exact Decimal quantities/prices,
UUID/date/aware instants, by-value results and copied typed object JSON. Shape checks
belong to Pydantic, ownership/current-state/lifecycle to application, DB constraints
remain final safety nets. Application errors are internal categories, independent of
HTTP. Wrong-store and missing references consistently report NOT_FOUND.

CURRENT FACT: Product create/scoped read, Sales canonical insert/inclusive history,
Forecast/Decision start/complete/fail/scoped read and effective Recipe+lines reads
are implemented. Forecast validates Product/horizon and atomic supplied predictions;
Decision requires a completed same-store Forecast and atomically stores supplied
snapshot/package metadata. Full package shape/evaluation/provenance remains future.

Composition supplies a synchronous Session; write methods require idle clean state,
explicitly begin/commit/rollback and leave Session close to caller. Reads suppress
autoflush and never commit. An existing caller transaction is rejected without
touching its work. Repositories still never own transaction or Session lifecycle.
No transaction decorator, generic service, UnitOfWork or engine placeholder exists.
See [APPLICATION_CONTRACTS](features/APPLICATION_CONTRACTS.md) for exact contracts,
error conventions, JSON mutability limits and manual persistence verification.

## Operational application closure -- CURRENT FACT (S1.7)

The internal boundary now also implements Store and Ingredient create/read,
SupplierTerm version create/read, atomic Recipe version+lines and atomic received
lot+RECEIPT/correcting movement paths. Writes retain idle clean synchronous Session
ownership; repositories retain caller-owned persistence only. Existing scoped lot
row locking with refresh protects corrections through commit/rollback. The minimal
exact nonnegative balance calculation lives in plain Python app/domain/inventory,
without HTTP, ORM or filesystem dependencies; other engines remain unimplemented.

Money is exact Decimal in Store.currency, with no rounding/conversion. Ingredient
units match exactly; supplied business dates stay separate from aware UTC inventory
event instants. Corrections use new Recipe/term versions and append inventory
movements; Sales canonical duplicates stay conflicts. No version auto-close,
absolute balance setter, public business API, schema/ADR/dependency or infrastructure
change. Actor/provenance authorization, source importing, full Sales correction,
HISTORICAL INFORMATION (S1.7): Forecast computation was deferred. CURRENT FACT:
S2 now implements baseline/trained Forecast and its Store-local date cutoff;
Decision computation remains future.
This section supersedes historical operational-service absence statements only for
these paths. See APPLICATION_CONTRACTS and CURRENT_STATE for verified boundaries.
