# Public planning — S4.9

## ACCEPTED DECISION

[Planning contract](../PROCUREMENT_API_CONTRACT_VI.md) PLAN2–9 and P1/P2,
[Auth contract](../AUTHORIZATION_CONTRACT_VI.md), ADR015/019/020/021/022 own
semantics. This feature connects existing algorithms; it creates no purchase
order, actual receipt, selected-option persistence, training or provider call.

## CURRENT FACT

C02 `POST /api/v1/stores/{store_id}/procurement-plans` accepts default/custom/saved
requirements with a required canonical UUID `Idempotency-Key`, current Origin and
CSRF. Success contains only Run UUID/status/accepted_at, warnings and polling delay.
Queued/running returns202/Retry-After2; terminal same-intent replay200/poll0.
Location points to C03 using the same UUID. No generic job identity is added.
Missing/malformed key or JSON400; configuration/date/bounds/64KiB overflow422
`INVALID_PLANNING_CONFIGURATION` with field errors; stale inherited default409.
Same key with a different original intent409 `IDEMPOTENCY_KEY_REUSED`.

Acceptance freezes requirements, effective budget, ceiling/default/saved versions,
explicit serving registry and resource policy in the existing Run aggregate.
Current auth fences, intent/receipt/audit are atomic; replay precedes new resolution.
Money/percent remain decimal strings; omitted/null budget inherits the accepted
cap and zero is a real zero. Fully custom/saved requests do not inherit stale
defaults. Stock/recipe/history readiness is evaluated at worker capture, never
inferred from a prior GET. Worker-off acceptance is durable queued intent only.

`PlanningExecution` claims one queued Run and verifies current actor account,
credential revision, Store membership and the three sensitive run grants. Logout
closes browser access but does not delete intent; actor authorization is checked
again before capture retention and terminal publication. Reads/replays always
require a current authenticated session. Failed denied execution cannot publish
uncommitted business candidates.

The accepted serving configuration drives exact forecast preparation/reuse, even
when current registry changes after acceptance. History/scope/source pins are
compared in the same owned read-only REPEATABLE READ snapshot as operational
facts/declarations. At most two re-preparations follow the first attempt. No
observations means Product exclusion, not zero demand or a fabricated forecast
UUID. Original real observed zero remains usable. Local exclusions cannot hide
unknown fees, limits, budget conflicts or unknown dependency attribution.

Every Session/connection closes before existing BOM/serving/FEFO/procurement/2,
comparison/2 and selector/1 run. Capture is retained first, terminal result/audit
are atomic. Bounds use exact integer floors of accepted budget/positive pack cost
and captured maxima/declared supplier limits. Zero-cost offers require a finite
source maximum or actual limit; otherwise `OFFER_BOUND_UNKNOWN`. Source maximum
alone is a technical finite-domain bound, never a fabricated SupplierLimit.
Private typed retained evidence includes actual source keys/versions, source
maxima, declarations/dependency digests, fees and bound derivations. Fee bindings
honor source system identity. Supplier-order fees appear once in aggregate costs,
not duplicated in purchase lines. Generic payable fees retain delivery=null and
`DELIVERY_FEE_TAXONOMY_UNAVAILABLE`.
Multiple source aliases resolving to one canonical Supplier share one order;
all known components are summed. Unresolved components block, never become zero.
Readiness and capture share this canonical coverage check, including namespace
and Store currency.

The fixed resource policy uses engine30s/reserve2s/8 solves per strategy, disabled
enumeration and overall180s cooperative stage budget. It records actual measured
pre-publication elapsed and overrun; it does not promise hard cancellation/SLA.
An operational fee mode conflicting with the accepted policy discriminator blocks
rather than changing accepted policy. Budget/fee amount/stock/terms changes do not
invalidate forecast identity; each new Run captures new operational facts.

C03 `GET /api/v1/procurement-plans/{plan_id}` always200 for available lifecycle
records, including failed; auth/resource/integrity errors use separate HTTP codes.
It resolves owning Store, checks `planning.result.read` + `budget.read` +
`procurement.cost.read`, verifies full retained schema/digest/relationships and
returns only condensed retained facts. It never recaptures, forecasts, solves,
restarts, looks up live costs or calls an LLM. Authorized Store readers can read
other creators' Runs. Current revoke denies the entire sensitive response.

ETag is opaque response_version; no-store and full200 also for If-None-Match.
Nonterminal forecast/scope/execution/result may be null. No-computables/business
blocks have empty result arrays; no fake three-strategy evaluation. Engine results
retain ordered lean/balanced/protected sources and exact grouping/winner evidence.
Failed source strategy can retain an independently verified recommendation as
partial output; failed is never relabeled completed. Public diagnostics sanitize
private native exceptions. Quantity fractions/domain_size remain strings;
Decimal50/HALF_EVEN views and ceil milliseconds are presentation only.
Search completeness/proof and result data completeness are separate.

## TECHNICAL CHOICE — runtime and persistence

Separate `PLANNING_WORKER_ENABLED=false` by default. FastAPI lifespan registers
one local planning thread only on explicit opt-in; Import's flag grants no planning
execution. C01 capabilities and R01 execution availability follow actual thread
liveness, not route existence; GET cannot start it. One attempt owns a Run; claim
token/process incarnation fences publication. Recovery scans bounded batches and
marks only proven dead PID/birth/host owners failed/PROCESS_INTERRUPTED, with no
automatic re-execution or elapsed lease stealing. Live or UNKNOWN owners remain
protected. Graceful stop waits for in-flight cooperative computation.

No migration: head0016 remains. Optional private public evidence extends JSONB
planning_storage/1, package1; absent additions preserve historical internal
canonical serialization. Retention is indefinite. Privileged SQL can bypass
application guards; hashes check integrity, not source authenticity/tamper-proof
audit. Abandoned threads inside a live process remain running; process-only death
evidence cannot infer thread failure. No production durability/backup guarantee.

## Verification and limits

Exact commands/results/fail→fix and measurements are in
[current verification runbook](../runbooks/FULL_TEST_FLOW.md); supported local procedure in
[S49 runbook](../runbooks/FULL_TEST_FLOW.md). [Validated JSON examples](examples/planning_public/README.md)
include all request modes and actual HTTP lifecycle responses.
The50-active-Product test measured9 queries/118281 bytes/cold12.728s C03 and83.062s
worker time. TECHNICAL DEBT: deep retained validation remains expensive; no latency
SLA or simultaneous maximum lots/offers benchmark is claimed. Synthetic test observations and
BASELINE engine-path evidence do not demonstrate real-data accuracy or trained
quality. LightGBM activation/production artifacts are not required or performed.
No FE/browser acceptance, development DB change, provider call, deployment,
commit/stage/push, new handoff/ZIP or S4.10 implementation is claimed.
