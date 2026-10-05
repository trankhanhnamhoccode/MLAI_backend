# DecisionRun persistence — S1.4

CURRENT FACT (S1.5): internal repository access is now implemented; see
[PERSISTENCE_ACCESS](PERSISTENCE_ACCESS.md). Statements below about repository
absence describe the HISTORICAL INFORMATION of this schema slice. Its direct
Session tests remain schema evidence; operational services/APIs/engines and
operational inventory audit enforcement remains unimplemented. CURRENT FACT:
S1.5 repository writers now guard RUNNING-only terminal transitions; Forecast also
guards prediction append. Direct ORM/SQL changes can still bypass these guards.

## Status / purpose

CURRENT FACT: DecisionRun persistence exists. Decision computation NOT IMPLEMENTED.
No repository, public API, BOM, FEFO, procurement, simulation/recommendation, what-if
or LLM explanation implementation. ADR-001/004/005/006/010/011 govern future behavior.

## Storage and historical semantics

decision_runs is the central historical input/output record for one Store. It requires
same-store forecast_run_id and ordered inclusive planning_start/end dates, status
RUNNING/COMPLETED/FAILED and explicit started_at. Future service must consume an
appropriate completed forecast; FK cannot enforce source run status.

Completed fields: positive package_schema_version (initially 1), nonblank
input_fingerprint, object input_snapshot_json, object decision_package_json,
LEAN/BALANCED/PROTECTED recommended_strategy and completed_at >= started_at.
RUNNING has no terminal output/time/errors. FAILED has terminal time and nonblank
sanitized error code/summary, no output package/recommendation. Partial states may
retain captured input/version or SQL NULL when not yet captured. SQL NULL means
absent; JSON null/array/scalar is rejected. No arbitrary strategy string is accepted.

Package version is an integer, never "latest". DB checks minimal presence/object
shape, not a full JSON schema. A future versioned application package schema must
validate identities/values, recommendation/evaluation consistency and all candidates.
Canonical inputs use exact serializations for quantities/money; fixtures use decimal
strings in JSON to avoid implying a binary float monetary contract.

Historical snapshot holds values plus identities/versions used: forecast reference/
values, recipes, ingredient-demand inputs, lot state, supplier terms and constraints.
It is not a list of live FKs requiring current-table reads. Future output package
holds ingredient demand, evaluations, procurement lines, risks, warnings and selected
recommendation. All actually considered Competition candidates LEAN/BALANCED/PROTECTED
must be simulated/evaluated before deterministic backend comparison; preserve all
evaluations, not only the winner. Full JSON business schema is not frozen by this slice.

Future flow: load inputs -> build canonical snapshot -> compute FROM THAT SNAPSHOT
-> persist package. No post-computation DB re-query may substitute different input
values. Historical interpretation uses the stored snapshot/package, never today's
inventory/costs/recipes/budget. Rerun creates a new UUID even with identical fingerprint.
Fingerprint uses future deterministic canonical serialization/digest, not Python hash(),
and is nonunique. Same inputs alone do not imply identical outputs across algorithms.
Future packages must record needed algorithm/model versions; no speculative engine_version
column/framework is added because exact engine semantics remain unresolved.

## Immutability / What-if / LLM boundaries

Completed content is immutable policy under ADR-011; S1.5 complete_run/fail_run
lock and require RUNNING, so normal repository writes reject completed/failed runs.
Future application boundaries must also enforce it. There is no trigger, immutable ORM method or SQL privilege
enforcement; privileged SQL can update completed rows. This limitation is intentional,
not an implemented immutability service. What-if remains hypothetical/non-persistent
by default, no scenario/what_if tables. LLM cannot choose/change recommendation,
evaluations, risk/quantity calculations or snapshot facts; future wording may consume
authorized facts only. Missing inputs cannot be fabricated (ADR-010).

## Tables / tests / deterministic fixtures

Writes: decision_runs. References read: forecast_runs/stores. Tests use direct Session
on shelfcash_test; no repository/service flow is claimed. Fixtures contain forecast
reference, recipe v2, inventory 20 ml, supplier version 3/cost 384000/lead 2, budget
7000000, and fixture-only LEAN/BALANCED/PROTECTED evaluations. Tests commit, close,
reload all JSON and metadata; change a Python input object and a test source row to
5 ml, verifying stored snapshot remains 20 ml. Direct source SQL is test-only evidence,
not an audited inventory mutation implementation. Same fingerprint reruns persist as
separate rows. Tests reject missing completed fields, invalid version/status/strategy,
window/time/JSON shape and cross-store forecast; partial/failed states have no fake
results. No fake test claims DB-level completed immutability or computation correctness.

## Manual verification / reset / known limits

[S14_VERIFICATION](../runbooks/S14_VERIFICATION.md) provides commands/inspection:

```sql
SELECT id,store_id,status,forecast_run_id,planning_start_date,planning_end_date,
       package_schema_version,input_fingerprint,input_snapshot_json,
       decision_package_json,recommended_strategy,completed_at FROM decision_runs
ORDER BY id;
```

Expected after guarded reset: no rows; head 0006_forecast_decision_persist, sixteen
business tables. Targeted fixtures prove values through fresh sessions before cleanup.
Rollback invalid transactions before retry; 0006 downgrade removes three run tables
and their history. No public Decision API, engine, snapshot builder/hasher, complete
JSON schema, actor/authorization/retention service or SQL-level immutability exists.
