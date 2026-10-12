# Planning configuration and readiness — S4.8

## CURRENT FACT — S4.9 follow-up

C02/C03 and an independent default-off planning worker now connect these
configuration/readiness dependencies. C01/R01 execution availability follows
actual worker liveness. See [public planning](PUBLIC_PLANNING.md) for current
runtime behavior; the S4.8 scope/evidence below remains historical.

## HISTORICAL INFORMATION — authorized S4.8 implementation, 11/10/2026

N1–N4 persist Store-scoped saved requirements and the budget ceiling. Saveability
does not require sales, recipes or an executable planning workflow. All saved
configurations are shared for authorized readers; Staff manages their original
creations, Owner manages all. Changes use current permissions, Store locking,
CAS and an atomic revision/audit/idempotency receipt. Replays reauthorize first;
an exact replay returns its original retained response. A numeric no-op preserves
the version and timestamp. Archived configurations cannot be restored or used.

R01 is a read-only snapshot evaluator. C01 projects setup and the same planning
readiness semantics. Neither GET forecasts, solves, calls an LLM or writes business
data. Authentication may refresh its own session. Sensitive selected actions
require all read permissions; a denied action denies the whole response. Missing
`planning.run` is reported only after the sensitive read checks pass.

The forecast service is internally available; the public planning workflow remains
unavailable until S4.9. `data_status=valid` can coexist with
`execution_status=unavailable`; `can_generate=false` remains accurate. Readiness
and estimated scope are prerequisite assessments, never a winner guarantee.
Results remain `NOT_ASSESSED`. Missing observations differ from observed zero;
the history watermark requires a fresh COMPLETE declaration with exact scope and
rows. Recipe coverage spans all seven Store days. Local exclusions cannot hide
unknown global fees, inbound, limits, budgets or dependency graphs.

New I06 completion readiness is retained after canonical writes in that same
transaction. Projection/storage failure rolls back the canonical writes and success
evidence. Default actions are intersected with current read permissions; omitted
actions expose names/reasons only. Historical completions retain their original
projection and are never backfilled on reads.

## Manual verification and validated examples

Use the [FULL_TEST_FLOW](../runbooks/FULL_TEST_FLOW.md) guarded local test DB and
an authenticated synthetic Store. Fixtures in
`tests/integration/test_planning_configuration_public.py` and
`test_readiness_context.py` create their own entities; no production/demo business
seed is added. JSON below is checked against the actual boundary DTOs. IDs,
versions, cookie and CSRF values must come from the current synthetic session.
Validated synthetic projections for an empty Store:
[R01 JSON](examples/s48/readiness-empty-store.json) and
[C01 JSON](examples/s48/planning-context-empty-store.json). These are DTO/application
examples, not persisted Store records or additional database evidence.

N1 `POST /api/v1/stores/{store_id}/planning-requirements`:

```json
{"name":"Base setup","requirements":{"paths":[{"path":"BASE","min_fill_rate_percent":"95","product_overrides":[]}],"budget_limit":null}}
```

Supply UUID `Idempotency-Key`, Origin and `X-CSRF-Token`; response is 201 with
Location, ETag and `SavedDetail`. Explicit null follows the current ceiling when
used; a missing ceiling can still be saved with validation unknown. Inherited
paths need the current `default_requirements_version`; fully explicit custom
paths do not depend on a stale default version.

N2 GET the Location; N3 PUT that same detail URI with its quoted ETag in
`If-Match`, a fresh UUID key and the full replacement body:

```json
{"state":"active","name":"Low setup","requirements":{"paths":[{"path":"LOW","min_fill_rate_percent":"80","product_overrides":[]}],"budget_limit":"0"}}
```

Archive uses N3, with the current ETag and a new key:

```json
{"state":"archived"}
```

N4 `PUT /api/v1/stores/{store_id}/planning-budget`:

```json
{"amount":"1000000"}
```

Create with `If-None-Match: *` (201); replace with quoted `If-Match` (200).
Never send both. Missing conditional is 428; changed version is 412. A ceiling
decrease leaves saved requirements untouched and changes their current validation.
Money uses unsigned decimal text, at most 18 integer and 18 fractional digits;
percent uses 0–100 and at most 32 fractional digits. JSON numbers, exponent,
sign, whitespace and unknown fields are rejected. Bodies exceed 64 KiB yield 413
before parsing. Invalid configuration is 422 with Vietnamese `details.field_errors`;
malformed request/headers is 400. Errors use `meta={}`.

R01 `GET /api/v1/stores/{store_id}/readiness` defaults to import/menu/inventory.
Use `?actions=forecast,planning&forecast_start_date=2026-10-10` for the seven-day
forecast/planning estimate. Other filters, duplicate actions, and a date without
forecast/planning are rejected. Source versions include exact `model_config`.
C01 `GET /api/v1/stores/{store_id}/planning-context` accepts no body/query; it
includes active Products and every active saved configuration, including invalid
ones. Suggested start is Store today and cutoff yesterday, independent of latest
sales; an unrepresentable suggestion is null.

## Explicit operator configuration and internal dependencies

ACCEPTED DECISION: the operator may explicitly select BASELINE. No missing Store
configuration is silently initialized. Absent configuration reports
`MODEL_CONFIGURATION_UNKNOWN`. No latest artifact is selected automatically.
`scripts/configure_planning.py --command-file <local JSON>` prompts for the existing
operator credential without printing it. Use the usual module invocation:
`python -m scripts.configure_planning --command-file <local JSON>`.

```json
{"store_id":"10000000-0000-0000-0000-000000000001","action":"BASELINE","expected_version":null,"evidence_reference":"Explicit operator baseline selection"}
```

For replacement, set `expected_version` to the current registry version. An
explicit `DEFAULT_BASE95` command uses the same operator/CAS/evidence mechanism
for the already accepted default. These commands were validated/tested with
synthetic operator credentials; no development Store was configured in this task.

The serving identity pins actual model/artifact, selection/fallback reason,
prepared/source digest, registry version, features/postprocessing, actual and
configured dependency versions, training window, Store, horizon and Product/unit
scope through the prepared input. Exact retained reuse verifies identity, retained
input, metadata and finite ordered quantiles. Budget, stock, recipes and retail
prices do not invalidate forecasting; sales/scope/config changes do. Operational
facts and forecast pins are captured in one fresh snapshot and compared, with an
initial attempt plus at most two re-preparations. Sessions close before artifact
work and forecast computation. Corrupt artifacts/results fail explicitly;
recognized whole-run fallback remains the existing ADR-015 policy.

The caller-owned configuration resolver and prepare/serve/capture dependencies
feed future S4.9 acceptance without writing a PlanningRun or exposing C02/C03.
S4.9 still owns worker/recovery, the operational engine adapter and public atomic
acceptance. No new forecasting/solver policy, training, live provider or FE sync
is part of S4.8. Evidence and exact verification limits:
[current verification runbook](../runbooks/FULL_TEST_FLOW.md).
