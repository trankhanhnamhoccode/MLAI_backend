# Persistence access -- S1.5

## Current application composition -- CURRENT FACT (S1.7)

S1.6/S1.7 use these repositories for typed operational contracts, owned write
transactions, read no-autoflush and by-value results. S1.7 implements atomic
receipt/corrections using the existing scoped lot lock/append primitives; no new
repository extension was needed. Repository ownership and limitations stay intact.
See [APPLICATION_CONTRACTS](APPLICATION_CONTRACTS.md) and
[S17_VERIFICATION](../runbooks/S17_VERIFICATION.md). S1 completion is recorded in
CURRENT_STATE/ROADMAP. Earlier absence/status/count statements below are HISTORICAL
INFORMATION where superseded by those paths; privileged SQL still bypasses policy.

## S1.5 status -- HISTORICAL INFORMATION

Concrete synchronous SQLAlchemy repositories cover all sixteen business tables.
S1.5 is COMPLETE: targeted 80 passes (65 integration / 15 unit), full suite
320 passes. Acceptance evidence is recorded in CURRENT_STATE. The earlier
310-test insert/read baseline is historical; this review adds guarded lifecycle writes.
The implementation is an internal persistence boundary; GET /health remains the
only public operation. No Forecast/BOM/FEFO/procurement/Decision engine, inventory
mutation service, import correction or authentication/authorization exists.
Head remains 0006_forecast_decision_persist; models/migrations/dependencies unchanged.

## Application access contract -- ACCEPTED DECISION

Application composition passes the same synchronous Session to repositories that
participate in one use case. Application owns transaction begin, commit, rollback,
Session close, authorization and business validation. Repositories do not construct
engines/Sessions, commit, roll back or close them. No transaction wrapper or generic
CRUD framework is introduced. Routes call future use cases; domains receive plain
values and never import repositories, ORM or Session. Developer/migration commands
and schema-integrity tests deliberately retain direct SQL/Session access.

Methods accept explicit typed ORM entities and return ORM rows, None or lists.
These are application/persistence objects, not domain or public request/response
contracts. Future public boundaries use Pydantic. Application extracts exact values
for domain computations. There is no speculative Protocol/DTO layer or arbitrary
dictionary CRUD input; existing JSON run columns retain their S1.4 storage shape.

All Store-owned methods require store_id. Queries include it even when the Session
already holds another Store's row with the requested UUID. Wrong-store/missing
lookup returns None/[]; inserts with a mismatched row.store_id raise ValueError
before staging. Related parent integrity is checked by composite PostgreSQL FKs
on flush, including Store and exact ingredient unit. Global User identity lookup
and creation of a new Store are explicit bootstrap exceptions. Scope is data
isolation, not proof of actor permission; application must authorize the Store.

Insert methods accept only new transient rows. Persistent/pending/detached rows
cannot be reattached/merged as inserts. Duplicate business keys fail PostgreSQL;
no upsert, silent correction, additive sales or replacement. Missing facts retain
NULL where accepted; prices/dates/units are never normalized or fabricated here.

Repositories normally stage with Session.add and defer flush. Reads retain normal
SQLAlchemy autoflush, which can surface unrelated pending-write errors. Caller
chooses dependency flush points; supplied FK UUIDs alone do not establish ORM flush
ordering without relationships. Forecast aggregate insertion flushes its parent
before supplied predictions, or when a generated run ID is needed. That flush also
checks other pending Session writes; it is never a commit. Caller must roll back
the entire failed transaction before retry. The aggregate checks every supplied
prediction's Store/new-row/run identity before staging any member.

## Concrete modules -- CURRENT FACT

CURRENT FACT (S1.6): [APPLICATION_CONTRACTS](APPLICATION_CONTRACTS.md) now supplies
validated typed representative calls and returns by-value results. The S1.5 contract
below remains unchanged: repositories return internal ORM rows and never commit,
rollback or close. Application use cases own full transactions on idle clean Sessions;
composition/caller closes the Session. ForecastRepository and DecisionRepository add
only get_running_for_update, exposing existing scoped refreshed RUNNING locks for
application validation. No direct SQL queries bypass repositories in these use cases.
Repository-only horizon/full-package limitations below do not claim S1.6 lacks its
Product/date/lifecycle validation; privileged/direct persistence still bypasses it.

| Module / repository | Tables / explicit access |
| --- | --- |
| identity / IdentityRepository, StoreRepository | users, stores, store_memberships: new identity/Store/membership, exact email/UUID/pair lookups, Store member list |
| catalog / CatalogRepository | products, ingredients: insert, scoped UUID/case-sensitive SKU lookup, lists including inactive rows |
| recipe / RecipeRepository | recipes, recipe_lines: insert version/line, UUID lookup, product versions, dated recipe, lines |
| supplier / SupplierRepository | suppliers, supplier_terms: insert identity/term, UUID lookup, Store suppliers, ingredient terms/history/active terms, exact pair dated lookup |
| sales / SalesRepository | sales_daily: insert, UUID/business-key lookup, inclusive product/Store history |
| inventory / InventoryRepository | inventory_lots, inventory_movements: insert lot, scoped read/lock/list, append movement and read audit history |
| constraints / ConstraintsRepository | business_constraints: insert, UUID/history/active list, dated budget and ingredient safety-stock lookup |
| forecast / ForecastRepository | forecast_runs, forecast_predictions: insert new run with supplied predictions, scoped run/prediction/history reads |
| decision / DecisionRepository | decision_runs: insert new run, scoped UUID/Store/forecast history reads |

Forecast also exposes add_predictions, mark_completed and mark_failed; Decision
exposes complete_run and fail_run. These methods accept explicit storage fields;
no arbitrary field update or completed package replacement method exists.

Lists are deterministic: membership by user/id; catalog/suppliers by name/id;
recipe and pair term history by version/id; ingredient terms by supplier/version/id;
lines by ingredient/id; sales by date/product/id (single-product by date/id);
lots by expiry ascending NULL last/id; movements by occurred_at/id; constraints by
scope type/scope id NULL first/type/version/id; run histories by created_at descending/id;
predictions by forecast_date/product/id. No implicit active filter on history lists.
Effective rows use from<=day and (to is NULL or day<=to), plus active=true for
terms/constraints. No date/version fallback; no recipe.active column exists.
Reversed sales windows raise ValueError. At most one effective recipe/pair term/
logical constraint is enforced by existing exclusions, not supplier selection.

## Inventory and historical boundary -- ACCEPTED DECISION / CURRENT FACT

ADR-009 requires a future application to lock the lot, validate a justified change,
update its balance and append a movement in ONE caller transaction. get_lot_for_update
uses SELECT FOR UPDATE and refreshes cached values; call it before editing. Its lock
lasts until caller commit/rollback. add_lot and append_movement do not calculate or
update balances, enforce receipt/reason/actor rules or constitute a mutation service.
Expired/zero/unknown-expiry lots remain readable; ordering is not a FEFO allocation.

ADR-011 requires historical immutability and snapshot-before-computation. Forecast
accepts a new run with its supplied predictions. add_predictions only appends to a
RUNNING run. mark_completed/mark_failed and Decision complete_run/fail_run permit
only RUNNING -> COMPLETED/FAILED. Each writer uses Store-scoped SELECT FOR UPDATE
with populate_existing to refresh cached status and serialize competing writers.
Locks last until caller commit/rollback. FAILED is terminal too; retry creates a new
run. Missing/wrong-Store runs return None without staging predictions or changes.
InvalidLifecycleTransition (a ValueError) rejects terminal writes. No arbitrary
update/delete method exists for completed content or movements. JSON completion
inputs are copied before storage; repositories do not interpret business packages.
New aggregate insertion still permits already-completed storage fixtures/results;
require_new prevents reattaching an existing historical run as a new insert.

No horizon, completed-forecast-consumption, full package validation, snapshot builder,
hasher or computation is implemented. SQL checks enforce minimal storage shape,
timestamps, quantiles and FKs. Caller supplies sanitized failure text. Integrity/FK/
check/unique errors retain existing SQLAlchemy exceptions; caller rolls back.
No general database exception translation policy or hierarchy is introduced.

Lifecycle methods do not explicitly flush; their locking query uses ordinary
autoflush. Repeated writes in one Session see the prior staged terminal transition
through that flush and reject it. Callers must not directly edit run fields before
calling these methods: ORM changes would autoflush before the guard. Normal run
writes go exclusively through lifecycle methods. Read methods do not explicitly
mutate rows or commit; ordinary autoflush remains part of the Session contract.

TECHNICAL DEBT / deferred enforcement: reads return tracked mutable ORM rows; direct
Session/SQL changes can bypass immutable history and inventory audit policy. No SQL
trigger, Session-wide immutability guard or immutable read DTO is claimed. Future
authorized use cases must enforce these policies before real operational writes.
This layer never authorizes an unexplained balance overwrite or completed-run edit.

## Reproducible verification -- CURRENT FACT

With healthy local Compose PostgreSQL, from backend/:

```powershell
docker compose up -d --wait postgres
.\scripts\reset_db.ps1
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\python.exe -m pytest tests/integration/test_repositories.py -q
.\scripts\test.ps1 all
.\scripts\db_status.ps1
```

POSIX equivalent: `.venv/bin/python -m pytest tests/integration/test_repositories.py -q`
and `sh scripts/test.sh all`; Windows runtime verification is recorded in CURRENT_STATE.
The existing [FULL_TEST_FLOW](../runbooks/FULL_TEST_FLOW.md) handles fresh setup,
guarded reset/migrations/seed. Integration fixtures own only shelfcash_test. The
reset above is the explicitly authorized empty development baseline workflow;
tests themselves never reset development. Tests use fixed fixture values and
commit/close/fresh-read evidence for all tables, not engine-produced outputs.
Development status should retain sixteen empty tables and one revision row after
the existing reset baseline. Seed still writes no business entities.

Targeted tests verify Store isolation with identity-map entries, NULL/Decimal/JSON,
effective inclusive/inactive/open-ended selection, sales chronological bounds and
duplicate rejection, insertion guards, reruns and caller transaction visibility.
Inventory fixture transactions prove valid lot+movement commit and movement failure
rolls back an already flushed balance. A second Session verifies row-lock blocking
and release. These fixture transactions are persistence evidence, not a public
inventory workflow. On DB failure caller rolls back; duplicate/conflicting input
must be resolved under domain policy, never unconditional overwrite.

Lifecycle tests additionally prove RUNNING creation, prediction append, completion/
failure, terminal rejections, Store isolation, cross-repository rollback, fresh
terminal JSON/Decimal reads, lock blocking/release and stale Session refresh.

Rollback removes this slice's repository/test/docs additions; there is no migration
or schema rollback. Public APIs, full application contracts, auth and engines need
separate authorization. S1 overall remains in progress.
