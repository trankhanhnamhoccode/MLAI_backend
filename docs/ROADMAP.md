# Vertical-slice roadmap

CURRENT FACT: only S0 is implemented. Future slices are PROPOSAL, not permission to
implement them or an accepted public contract. Every slice must freeze precise
contracts, acceptance tests, rollback scope and affected BE/FE/ML/Data/demo behavior
before implementation. Preserve unrelated WIP; no batches of backend layers.

| Slice | End-to-end behavior | Acceptance gate before implementation |
| --- | --- | --- |
| S0 — Scaffold + architecture freeze | App/settings → health/OpenAPI → PostgreSQL migration bootstrap → canonical docs | Includes S0.2 persistence correction: healthy Compose, named volume, isolated real PostgreSQL tests, guarded reset/status/seed, migration head and unchanged API. Completion evidence/status is recorded in CURRENT_STATE. |
| S1 — Domain Model + Database Schema v1 / Operational truth | Store → Product → Ingredient → Recipe → Sales → Inventory Lot → Supplier Term | Split into small create/read/validate/persist vertical paths. Define Pydantic contracts, store boundaries, units/money/date rules and corrections. Assert validated persistence/retrieval, same-store relations, rejected invalid data and reproducible clean DB migrations. |
| S2 — Forecast | Sales → model/baseline → ForecastRun → P25/P50/P75 | Freeze cutoff, horizon, baseline/model, quantile semantics and data contract. Assert future dates, ordered nonnegative quantiles, reproducible controlled-input output, input/model provenance and no LLM dependence. |
| S3 — Decision MVP | Forecast → BOM → ingredient demand → inventory/FEFO → three candidates → exact simulation → comparison → recommendation → DecisionRun | Freeze units, simulator granularity, objective/tie break, infeasibility and package schema. Assert demand/pack/MOQ/expiry/arrival invariants, exactly three evaluated strategies, deterministic selection, preserved schema-versioned snapshot, all golden scenarios and provider-outage operation. |
| S4 — Explanation + What-if | Authorized facts → wording; baseline + mutation → recomputation → comparison | Freeze allowed tools/mutations and permissions. Assert fact fidelity, deterministic recomputation, authorized facts only, no real-state mutation, simulation vs mutation distinction and useful provider-unavailable behavior. |
| S5 — Excel semantic mapping / Store Mapping Profile | Known approved profile or rules → validated mapping → ambiguity suggestion → approval if required | Freeze canonical schema, confidence and approval rules. Assert known profiles never need LLM, confident rules are deterministic, ambiguous suggestions are validated, no invented fields, profile versions/store scope and safe human fallback on outage. |
| S6 — Authorization/human approval hardening where required | OWNER/STAFF + delegated permissions → authorized use case → auditable human approval | Freeze action permission matrix and approval triggers. Assert unauthorized reads/mutations rejected, simulation permission does not imply mutation permission, tools cannot bypass checks, store isolation and approval evidence. |

S6 hardens authorization; it is not permission to postpone minimum access enforcement
needed by any earlier slice. No unprotected real business data exposure is implied.

Next phase — PROPOSAL: S1 — Domain Model + Database Schema v1. Next smallest
implementation slice: Store create/read only, after its contract and minimum
isolation/bootstrap are agreed. Do not implement the full S1 chain at once.

## Local verification gate

CURRENT FACT: S0 includes categorized repository test runners, guarded PostgreSQL
reset/migration, explicit empty-baseline seed, read-only DB inspection, a
[scaffold feature guide](features/SCAFFOLD.md) and
[fresh-environment runbook](runbooks/FULL_TEST_FLOW.md). Business seeds and e2e
scenarios are not implemented. This tooling slice does not start or complete S1.

ACCEPTED DECISION: future major slices are complete only with automated tests,
relevant integration/persistence coverage, usable manual verification, deterministic
fixtures where practical, fresh-session persisted-state assertions and canonical
feature documentation. Require both application/API results and database evidence.
Keep the full test flow and testing guide current; do not mark a slice complete
while its verification instructions are unusable.
