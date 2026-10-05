# Vertical-slice roadmap

CURRENT FACT: S0 is complete; S1 is complete with S1.1/S1.2/S1.3/S1.4 persistence schemas
implemented, with S1.5/S1.6/S1.7 operational access (acceptance in CURRENT_STATE). Future slices are PROPOSAL, not permission to
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

## S1 implementation slices

HISTORICAL INFORMATION: scope exclusions in S1.1-S1.4 rows describe those schema
slices when delivered. CURRENT FACT: S1.5 adds internal repositories for all their
tables; S1.6/S1.7 add internal operational application paths. Public APIs and engines remain future work.

| Slice | Status | Scope |
| --- | --- | --- |
| S1.1 — Identity + Store | COMPLETE; 22 targeted; historical full suite 240 passes | Only users/stores/store_memberships, storage constraints, direct Session tests and manual inspection; no APIs/repos/auth |
| S1.2 — Catalog + Recipe | COMPLETE; 51 targeted; historical full suite 240 passes, usable manual guide | Only products/ingredients/recipes/recipe_lines; scoped SKU, dated nonoverlap, yield/loss, exact unit/same-store constraints; no APIs/repos/BOM |
| S1.3 — Supplier / Operational / Constraints | COMPLETE; 80 targeted / 240 historical full passes, usable manual guide | Exactly suppliers/terms, canonical sales, received lots/movement history, registry constraints; ADR-008/009 accepted; no import/mutation/FEFO/API/repos |
| S1.3.1 -- Data Completeness & Source Semantics | COMPLETE; 9 targeted / 240 historical full passes | ADR-010; unknown receipt date nullable without default; strict supplier dates/per-pack costs unchanged; no import/readiness implementation |
| S1.4 -- Forecast / Decision persistence | COMPLETE; 58 targeted / 240 full passes | Three run tables, dated/status/quantile/state constraints, same-store FKs, versioned snapshot/package, ADR-011; no engine/API/repos |
| S1.5 -- Persistence Access Contract + Repository Layer | COMPLETE; 65 repository integration / 15 unit checks; historical full suite 320 passes | Concrete typed access for sixteen tables; explicit Store scope, caller-owned transactions, inserts/history/date queries, RUNNING-only lifecycle guards and PostgreSQL acceptance tests; no generic framework, public API or engines |
| S1.6 -- Application Contracts + Validated Read/Write Paths | COMPLETE; 38 unit / 44 application integration; 82 targeted / 402 full passes | Typed Product/Sales paths, Forecast/Decision persistence lifecycle, effective Recipe read, by-value outputs, explicit Store context/transactions/errors, atomic PostgreSQL rollback; no schema/API/engine change |
| S1.7 -- Application Coverage + Inventory Transaction Closure | COMPLETE; 106 new targeted / 188 combined targeted / 508 full passes; one final full regression | Typed Store/Ingredient/SupplierTerm create/read, atomic Recipe version+lines, received lot+RECEIPT and locked justified corrections; frozen exact money/unit/DATE/UTC/correction semantics; no schema/API/engine change |

S1.5 is authorized and implemented; see PERSISTENCE_ACCESS for its internal contract.
S1.6 adds representative contracts; S1.7 closes remaining authorized operational
boundaries. Public transports, auth and computation need separately authorized
slices; none is started automatically.

## Local verification gate

CURRENT FACT: S0 includes categorized repository test runners, guarded PostgreSQL
reset/migration, explicit no-op schema-verification seed, read-only DB inspection, a
[scaffold feature guide](features/SCAFFOLD.md) and
[fresh-environment runbook](runbooks/FULL_TEST_FLOW.md). Business seeds and e2e
scenarios are not implemented. S1.1-S1.4 implement sixteen persistence tables;
S1.5-S1.7 implement operational persistence/application paths. S1.7 final acceptance passes, and S1 is COMPLETE.

ACCEPTED DECISION: future major slices are complete only with automated tests,
relevant integration/persistence coverage, usable manual verification, deterministic
fixtures where practical, fresh-session persisted-state assertions and canonical
feature documentation. Require both application/API results and database evidence.
Keep the full test flow and testing guide current; do not mark a slice complete
while its verification instructions are unusable.

## S1 overall acceptance -- CURRENT FACT / PROPOSAL

S1.7 has implemented the authorized remaining S1 gates: Store/Ingredient/SupplierTerm
create/read, Recipe atomic version+lines, audited initial inventory receipt and
movement-backed locked corrections; exact money/unit/DATE/UTC/correction semantics.
S1.7 COMPLETE; S1 overall COMPLETE. Targeted and full regression gates pass;
no canonical S1 acceptance gate remains open. See CURRENT_STATE for counts/evidence.
The full operational chain is tested with fresh-session persistence; only Supplier
identity creation remains an explicit S1.5 repository prerequisite, as authorized.

Future budget/constraint writers, actor authorization, full Sales correction,
source conversion, engine-specific currency rounding/day cutoffs and public APIs
are deliberately outside S1.7 and are not newly invented S1 completion gates.
Next canonical phase: **S2 -- Forecast**, PROPOSAL / NOT STARTED. Freeze cutoff,
horizon, baseline/model, quantiles and provenance in a separately authorized slice.
This update authorizes no next slice or API.
