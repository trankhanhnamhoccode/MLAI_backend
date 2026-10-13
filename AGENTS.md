# ShelfCash Competition Edition engineering rules

These instructions apply to all work under `backend/`. This is a greenfield modular
monolith. Do not port legacy ShelfCash APIs, schemas, compatibility layers or service
structure without an explicit request. This file establishes ACCEPTED DECISION rules.

## Authority order

Before changing code, read in order:
1. `docs/CURRENT_STATE.md`
2. `docs/DECISIONS.md` and relevant `docs/adr/` files
3. `docs/ARCHITECTURE.md`
4. `docs/API_CONTRACT.md`
5. `docs/DOMAIN_MODEL.md`
6. `docs/DATABASE_SCHEMA.md`
7. `docs/ROADMAP.md`
8. Current code and tests for implementation reality

Report drift when code/tests disagree with documented runtime behavior. Do not
silently rewrite documentation to hide drift. Only ACCEPTED ADRs are architectural
authority; proposals in architecture or roadmap documents are not accepted decisions.

For authorization, permissions, Store membership, one-time approval, audit or
permission-sensitive data exposure, read `docs/AUTHORIZATION_CONTRACT_VI.md`.
This user-designated contract records approved product rules and separates them
from PROPOSAL/OPEN details and CURRENT FACT. Do not treat proposed permissions/routes
as approved or stored membership as implemented authorization.

## Classification

Make every architectural statement/change distinguishable as CURRENT FACT,
ACCEPTED DECISION, TECHNICAL DEBT, PROPOSAL or HISTORICAL INFORMATION. Runtime facts
must be supported by code/tests. Keep future behavior separate from current behavior.

## Before implementing

Identify the current contract, relevant ADRs, acceptance tests, rollback scope,
affected BE / FE / ML/Data / demo behavior, and unrelated WIP that must be preserved.
Record these in the conversation work plan before editing. Observe existing work first.

## Documentation ownership and generated output

ACCEPTED DECISION: update the existing canonical document when adding, clarifying
or correcting an existing topic. Edit its current account; do not append a task
history or create a supplement, response, final/v2/latest document or ZIP merely
to add information to it. Retain important decisions with their reason and status;
Git owns source history. Link to the responsible document rather than duplicate it.

Keep API_CONTRACT for shared conventions and Catalog/Inventory semantics, plus
the three independent Authorization, Import and Planning contracts. OpenAPI and
source DTOs own request/response structure; prose owns workflow, meaning, states,
errors, permissions and confirmation conditions. Keep proposals separate from
implemented behavior and report drift instead of changing approved intent.

Create a separate document only for a distinct purpose, audience or lifecycle,
substantial independently useful content, and no duplicate ownership. Default
plans, progress, commands, results and limits belong in the conversation, not new
task notes, evidence, PASS reports or handoff packages. Create reports/ZIPs only
when explicitly requested or needed by a concrete consumer. Temporary outputs
belong under ignored runtime; reusable acceptance inputs belong in tests/fixtures.

Cleanup must preserve uncommitted source, migrations, tests, fixtures, secrets,
model artifacts and operational/audit/provenance data. Back up files lacking a
reliable recovery copy outside the repository before editing/removing them.
Generated development evidence is not application audit. Never delete by Git
untracked/ignored status or purge all runtime. Retire obsolete tool callers before
deleting their input, and retain original API baseline provenance for comparisons.

## Implementation policy

Use: observe → freeze contract → test → implement one small vertical slice → verify
→ document → continue. Stay inside the authorized slice.

Never perform a big-bang rewrite; silently change API contracts or business semantics;
let LLM own business truth; redesign unrelated modules; introduce infrastructure
without an actual use case; remove compatibility behavior without explicit evidence
and decision; or invent architecture because it looks cleaner. This greenfield scaffold
has no legacy compatibility behavior to preserve or recreate.

Use typed, explicit, small Python modules. Pydantic belongs at public boundaries;
SQLAlchemy declarative models belong only to persistence. Domain computation must
remain plain Python without FastAPI, ORM, HTTP, LLM or filesystem dependencies.
No domain imports from `app.api`, `app.models` or infrastructure. No business rules
in routes or ORM models. Wire dependencies at application composition boundaries.
Use synchronous SQLAlchemy Session; do not make domain/application code async by
default. Avoid generic base services, excessive inheritance, service locators,
implicit global mutable state, arbitrary dictionary API contracts, unused wrappers,
and speculative abstractions. Empty domain packages are preferable to fake services.

Keep PostgreSQL via SQLAlchemy 2.x synchronous Session/psycopg (ADR-007), local
storage and one backend process. Local PostgreSQL runs through Docker Compose with
a named volume. Do not add MongoDB, microservices, Kubernetes, Kafka, Celery,
brokers, generic agent frameworks,
enterprise IAM, event sourcing, CQRS or unnecessary repository abstractions.
Add ML, spreadsheet or provider dependencies only for an authorized vertical slice.

Backend owns forecast, BOM, demand, inventory/FEFO, procurement, feasibility, risks,
constraints, cost, simulation, recommendation and strategy/scenario selection.
LLM may only assist approved ambiguous Excel semantics or authorized summary/copilot
wording. LLM must not create canonical fields, business facts or bypass authorization.
Core decisions must function with the provider completely unavailable.
P25/P50/P75 are demand quantiles; LEAN/BALANCED/PROTECTED are the three strategies.
DecisionRun packages start at `package_schema_version = 1`. What-if is deterministic,
hypothetical and does not silently persist as real business state.

## After each slice

Default to tests directly related to the change plus regressions for affected
boundaries/callers. For each slice, briefly explain the selected coverage and its
limits. After a small fix, rerun affected tests or the tests that failed; do not
repeat the full suite without a new reason.

Run the full suite at important integration milestones (such as completed S3
end-to-end/API), or for broad shared-contract, schema/migration, transaction-lifecycle
or infrastructure changes when targeted coverage is insufficient. Record the
reason for broadening verification. A full suite is not required after every slice.
Documentation-only changes need relevant documentation checks, not full pytest.
Add tests for important behavior, invariants and failure cases, not to increase
counts. Do not skip necessary verification to save time. Report exact commands,
results and unverified areas; targeted passing is not full regression passing.
This user-authorized verification policy supersedes earlier per-slice full-gate
instructions; historical test results remain historical evidence.

Run an OpenAPI diff/check when public APIs change. Update `docs/CURRENT_STATE.md` and
`docs/ROADMAP.md`. Update ADRs only if architectural intent actually changes;
update `docs/API_CONTRACT.md` only for an explicitly accepted contract change.
Do not modify an accepted ADR to ease implementation. If it appears wrong, gather
evidence and propose a replacement/superseding ADR rather than silently violating it.
Do not start the next slice without authorization.

## Reproducible local verification

Major slices require automated tests, relevant integration/persistence coverage,
deterministic inputs where practical, usable manual verification and canonical
feature documentation. Assert committed state through a fresh session alongside
application/API results. HTTP 2xx alone is not persistence evidence.
Use the supported test/reset/seed/db-status scripts and FULL_TEST_FLOW runbook;
integration tests own only `shelfcash_test`, never the development database.
Reset is permitted during Competition development, guarded to local development/test
targets; explicit Alembic schema evolution remains required. Do not add speculative
business seed entities, and do not depend on hosted notebooks for local workflows.
