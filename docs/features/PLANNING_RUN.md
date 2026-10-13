# Internal durable planning — S3.6.4

CURRENT FACT: COMPLETE within internal scope, PostgreSQL acceptance PASS. See
historical scope notes (retired) for actual commands/results and failure/fix history; no full-suite,
public availability, model accuracy or deployment claim.
ACCEPTED DECISION is limited to the user's S3.6.4 intent, recorded in ADR-022.

## Entrypoints and retained values

`PlanningRunUseCases(engine)` requires an actual SQLAlchemy Engine and owns every
Session; rejects caller Connection/Session so outer transactions cannot masquerade
as durable acceptance or fresh reconciliation.
`accept(actor_id,store_id,key,request,resolution=None)` returns the retained record;
existing-key retries do not require resolution and return its current status.
Optional trusted resolution(Session) provider runs only for a new key, inside the
short acceptance transaction; future configuration adapters may use it with their
own consistency/version guards. There is no config/saved persistence adapter now.
The provider must preserve the owned transaction and leave no pending ORM writes;
commit/rollback/replaced transaction is a programming error, never acceptance.
Trusted raw SQL/provider side effects are not a sandbox or authorization guarantee.

`claim` returns a token/generation/process identity. `retain` durably captures exact
operational source/prepared inputs, menu/computed scope/exclusions/temporal basis,
forecast provenance, declarations, effective policy and requirements. `finalize`
requires the same claim and validated pipeline graph with the same retained input.
Identical terminal result is idempotent; different payload or stale token rejects.
`fail` records a fixed sanitized technical error without inventing empty output.
`recover_interrupted` checks real OS incarnation death while holding the row lock;
alive/unknown does not transition. No lease, clock cutoff, TTL or auto rerun.

`execute` is synchronous one-shot composition: claim → owned snapshot capture →
retain commit → pure `execute_captured_pipeline_v2` → finalize → fresh read.
No background service. Operational source must honor its owned snapshot/closed
resource contract; PostgreSQL adapter does. There is no post-compute fact query.
Pipeline timing includes measured capture preparation and pure computation/checks;
acceptance/retention/finalization persistence is not claimed as pipeline compute time.
`read(expected_store,run_id)` runs one planning-row SELECT, detaches and verifies
versions/digests/schema/business relationships. It does not query live operational
facts, invoke solver or rebuild history. Pure exact BOM/serving/evidence validation
can run, and elapsed validation+load+cleanup time is reported. Internal counters
remain exact Python integers; public C03 counter-string projection is still backlog.

## Serialization and identity

`planning_serialization.py` canonical sorted-key compact UTF-8 JSON preserves array
order, omission/null/zero/[] and all original accepted fields. Request identity
normalizes only typed Money/Percent wire values:95 and95.0 equivalent, field presence
still different. UUID/date canonical strings; aware event instants round-trip;
Decimal coefficient/exponent strings preserve exact values without ambient context
rounding or exponent expansion; signed zero canonical0. Fraction numerator/
denominator strings remain exact; decimal_view is display, never eligibility input.
Finite binary floats appear only in existing diagnostic timing contracts, not money,
quantity or requirement values. These diagnostics are retained and hashed too.

Role/domain-separated SHA-256 covers idempotency request, scoped key, retained
capture, retained result and full aggregate. Accepted configuration/metadata/model
facts are covered by aggregate and capture. Model/search identity is not added to
the original customer request identity. Numeric equivalence is never inferred by
rounding display. Read canonical round-trip equality rejects noncanonical content.
Digests are integrity checks, not authentic signatures. SQL/DB privileged access can
alter rows and recompute hashes; schema/semantic checks detect inconsistent graphs,
not a coordinated malicious rewrite. No metrics_json provenance dumping.

## Outcomes and error/commit semantics

Completed: recommendation_available, no_eligible_candidate, no_computable_products,
computation_blocked. Failed: execution_error, including interrupted owner. ERROR
pipeline may keep a verified recommendation in its partial result. INCOMPLETE/
UNPROVEN incumbents can complete; no-winner does not claim global infeasibility.
Completed always requires a real validated pipeline result. Queued/running never
publish a fabricated result. Known technical failure may have no result.

Planning reuses S2.3's conservative SQLAlchemy/psycopg classifier without changing it:
only OperationalError/InterfaceError wrapping the corresponding psycopg family;
SQLSTATE08000/08003/08006/08007/40003, or no SQLSTATE plus dialect-confirmed disconnect.
Server known rollback (e.g.40001), integrity/data/programming exceptions, generic
DBAPIError/RuntimeError/ValueError are not uncertain. Only an exception from the
commit call qualifies; flush/query/close errors do not. Unsupported transport
families conservatively remain execution errors, not reconciled success.

Fresh reconciliation uses a different Session after cleanup. Success requires the
verified acceptance identity/config/receipt or exact mutation aggregate; concurrent
later lifecycle progress can conservatively produce verification conflict for a
mutation. Unknown reconciliation returns run_id and unverified state, no invented
FAILED. Programming error after durable completion reports an execution error with
COMPLETED state and never changes it to FAILED. Rollback/close secondary failures
are logged in trusted diagnostics and attached as classification notes to primary.
Exception details are not stored; engine's existing typed diagnostics remain retained.
Fault injection demonstrates classifier/reconciliation control flow; it does not
prove a real network drop or all server/driver failure modes.

## Scope and compatibility

New PlanningRun has one UUID, no selected_option/orders. Actor parameter and FK
identity/Store scoping do not implement permissions, session/auth or money exposure.
Readers are internal and must be wrapped by future authorization before exposure.
No shared S1 writer/lifecycle changed; old package/schema remains independently read.
No default/baseline/search/serving/ranking policy change. No development migration,
full benchmark, HTTP, worker, saved/config CRUD, automatic forecast or new slice.
