# Operational Decision capture and internal pipeline

Classification: CURRENT FACT unless marked otherwise. S3.5.2 adds internal code,
not a public API, DecisionRun persistence, winner or purchase order. PostgreSQL
acceptance is now PASS on disposable PostgreSQL: six real tests and a targeted
cross-store follow-up. The earlier unavailable-daemon result is historical;
fake-repository tests/demo do not establish PostgreSQL isolation. ADR-018 remains PROPOSED;
ADR-007/010/014/016/017/019 accepted intent is unchanged.

## Entry points and input

`app/application/contracts/decision_capture.py:51` defines `OperationalDecisionInput`.
Explicit Store, ForecastRun, complete requested Product scope, D, day-start attestation,
inventory declarations, committed-inbound absence, one-order attestation and two
separate typed policy values are required. Store scope is not actor authorization.
`capture_decision` (`app/application/use_cases/decision_capture.py:25`) accepts a small
synchronous `DecisionSnapshotSource` port and injected aware clock.
`PostgresDecisionSnapshotSource` (`app/infrastructure/database/decision_capture.py:31`)
owns its connection/Session and reuses existing scoped repositories. No caller Session
is accepted, committed, rolled back or silently given another isolation level.

## Source mapping and scope

| Captured value | Repository / source | Selection / missing handling |
| --- | --- | --- |
| Store timezone/currency | StoreRepository | Exact requested Store; missing blocks |
| Product identities/current selling units | CatalogRepository.get_product | Every explicit requested ID, including inactive rows; cross-store unavailable |
| Forecast predictions/model/artifact/fingerprint | ForecastRepository | Explicit COMPLETED ID only; no latest selection; exact Product × D+1..D+7 coverage |
| Forecast unit provenance | ForecastInputRepository + existing restore_prepared | Version/digest verified; Store/history/cutoff/full Product scope match; unit/timezone drift blocks |
| Forecast warnings/selection diagnostics | ForecastExecutionMetadataRepository + ExecutionDetails | Preserve actual details in capture provenance and warnings in prepared forecast; required for non-baseline models |
| Recipes/lines | RecipeRepository versions/lines | All versions intersecting horizon, inclusive bounds, exact yield/loss/units; gaps/empty/overlap block, even with zero demand |
| Ingredients | CatalogRepository.list_ingredients | All Store Ingredients, including unused/inactive; exact canonical base labels and expiry-tracking flags |
| Current lots/balances | InventoryRepository.list_lots | All scoped lots, including expired, zero, unknown receipt/expiry and future receipt; no FEFO filtering in capture |
| Supplier terms/identities | SupplierRepository | Active/effective on D+1 for all captured Ingredients; same-Store Supplier required; pack/MOQ/cost/lead/shelf/version copied |
| Constraints | ConstraintsRepository.list_constraints | Active budget effective at order date; safety versions intersecting horizon retained and blocked as unsupported by procurement |
| Source dates | Existing created_at/updated_at/completed_at | Detached SourceTime metadata; not a temporal reconstruction or full audit history |

Schema has no conversion definitions, committed inbound, persisted payable fee,
capacity/supplier limit, targets or finite search bounds source. Exact labels must
match; `kg` is never implicitly converted to `g`. Full Store Ingredient scope is a
conservative routine implementation choice. Unused Ingredients do not create BOM
demand, but their captured inventory completeness must still be declared.

## Snapshot and time semantics

Infrastructure sets `isolation_level='REPEATABLE READ', postgresql_readonly=True`
on an owned connection before Session begin/first SELECT. The first Store query fixes
the PostgreSQL MVCC snapshot; the injected clock then records `captured_at`, an
observation marker rather than a database historical inventory timestamp. All reads,
retained-input decoding and typed DTO construction use that transaction. It closes
before returning facts; no ORM objects/lazy references cross the port. Application
revalidates by-value facts and the canonical prepared snapshot after release.

`captured_at`, row source timestamps, Forecast origin/history/horizon/completion,
and `inventory_as_of` have distinct meanings. Existing v1 requires `inventory_as_of`
equal decision time on local D+1; this slice uses current balances observed at capture
and requires the explicit before-trading attestation. It cannot verify no intraday
trading from current schema. An older/future D+1 is blocked; no current balance is
relabeled a historical inventory snapshot. An injected test clock proves test
determinism only, not historical data availability. REPEATABLE READ guarantees a
consistent current view, not that all rows were historically known at D.

## Explicit facts, unknowns and blockers

Inventory declaration for every captured Ingredient distinguishes complete current
lot rows, confirmed absence of all lots, and unknown. No rows with a complete-lots
declaration is `INVENTORY_BALANCE_MISSING`; explicit zero row is valid. Confirmed empty
requires no lot rows; it is a caller source assertion with provenance, not DB-inferred
zero. Negative/nonfinite/missing balance is a typed source error. No movement-ledger
reconstruction/reconciliation is performed; lot balance is canonical current state.

Expired rows stay in snapshot/audit with warning and canonical serving excludes them.
Future-received operational rows stay captured with warning, are excluded throughout
serving and never become inbound. Unknown receipt/cost preserve existing warnings;
positive tracked stock with unknown expiry blocks. Committed inbound must be explicitly
confirmed absent; PRESENT_UNSUPPORTED/UNKNOWN blocks. No committed inbound is mapped
to stock or hypothetical arrivals. The only hypothetical arrivals are created by the
existing procurement engine from each basket; baseline serving has no arrivals.

ExplicitProcurementConfiguration retains required policy/targets, selected term IDs,
bounds, fees, caller budget if no DB budget, capacity/limit values or explicit
unconfigured states, and provenance. NONE fees is an explicit policy assertion;
missing PER_OFFER/PER_SUPPLIER_ORDER amounts block. UNKNOWN limits/budget are not
unconstrained. DB budget wins only through declared authoritative source: a conflicting
caller amount/state/currency blocks, never silently overrides. Technical bounds remain
technical bounds, not supplier limits. Snapshot DecisionPolicy v1 is unchanged and
does not supply the separate procurement/1 targets. Safety stock remains unsupported.

## Computation and outcome boundaries

`execute_operational_pipeline` (`app/application/use_cases/decision_pipeline.py:19`)
captures, validates explicit envelope and preflight, then invokes existing pure serving
(which first expands/revalidates BOM), procurement, and comparison. Serving's BOM
result is reused rather than expanding it separately again. Existing candidate
evaluation boundary validation remains mandatory. No algorithm/search/objective change.

Capture outcome is separate from computation outcome. Capture failure returns
DATA_BLOCKED without solver. Configuration/envelope/preflight failure after valid
capture returns COMPUTATION_BLOCKED with pipeline problems and unchanged CAPTURED
outcome. Numeric/serving blockers stop procurement. Technical repository/transport/
programming errors propagate; procurement's existing technical ERROR evidence is
surfaced as EXECUTION_ERROR, never business infeasibility. INCOMPLETE/UNKNOWN/UNPROVEN
and exact-valid candidates survive comparison. Truly absent candidate remains absent;
it is never replaced with a fake zero-purchase plan. No winner and no decision-ready
claim: `decision_readiness='NOT_ASSESSED'` everywhere.

## Manual demo / verification / limits

```powershell
.venv/Scripts/python.exe scripts/demo_decision_pipeline.py --output runtime/verification/decision_pipeline/synthetic_pipeline.json
.venv/Scripts/python.exe -m pytest tests/unit/test_decision_capture.py tests/unit/test_decision_snapshot_adapter.py -q
.venv/Scripts/python.exe -m pytest tests/integration/test_decision_operational_capture.py -q
```

Demo uses a deterministic SYNTHETIC fake repository port and real NativeSearch;
output file creation refuses overwrite. Expected first-day demand 2 cups, BOM 2g,
operational fulfillment 1 cup from 1g stock, one 1g pack at 0.1 VND; all strategies
share one compatible comparison option. Their finite proof remains UNPROVEN; this is
mechanics evidence, not forecast calibration/profit or real business recommendations.
PostgreSQL continuation passed the six actual cases, then the strengthened six-case
group and a final cross-store-only addition. They verify MVCC concurrency, post-capture
detachment, read-only enforcement, ownership/pool release, fresh-session unchanged
state and blockers/provenance. See [acceptance report](PROCUREMENT_V2.md).
Full suite/large benchmarks and development DB access were not performed.
Exact commands/results and rollback: [current verification runbook](../runbooks/FULL_TEST_FLOW.md).

OPEN: actor authorization/HTTP, temporal inventory/committed inbound source, conversion
definitions, business configuration storage/fee taxonomy, retention/hash/replay of
Decision snapshot, no-winner persistence and selection/recommendation policy. No next
slice starts automatically. No migration/dependency change or S1/S2 logic edit.
