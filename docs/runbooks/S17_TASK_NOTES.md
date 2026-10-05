# S1.7 task notes

## Observation and frozen scope -- ACCEPTED DECISION / CURRENT FACT

S1.7 is explicitly authorized by the user. Read AGENTS, CURRENT_STATE, DECISIONS,
accepted ADRs 001/002/004-011, architecture/domain/schema/API/roadmap/testing,
APPLICATION_CONTRACTS, PERSISTENCE_ACCESS, INVENTORY, SUPPLIER, CATALOG_RECIPE,
S1.5 repositories/S1.6 contracts/use cases and related tests. Existing uncommitted
S1.6 work is present; save all-file hashes/status under ignored runtime/s17 and
preserve that work. Protected snapshots include existing tests, models/migrations,
accepted ADRs, API_CONTRACT and dependencies. No schema fault observed.

Current: sixteen tables, head 0006_forecast_decision_persist, only public GET /health.
Reuse S1.6 frozen typed contracts/by-value results/errors, idle clean synchronous
Session requirement, explicit application begin/flush/map/commit and failure rollback.
Reads suppress autoflush, never commit. Missing/wrong Store entities both NOT_FOUND.
Known named UNIQUE/exclusion conflicts map CONFLICT; unexpected DB errors rethrow.

Authorized additions: Store create/read; Ingredient create/read; SupplierTerm
version create/scoped read; Recipe version+typed lines atomic create; new Inventory
lot+RECEIPT atomic write; signed delta COUNT_CORRECTION/MANUAL_ADJUSTMENT backed by
required nonblank note and movement; scoped lot/audit read to verify results.
No other movement writer, target-quantity setter, auto-close period, update/delete,
engine, public API, auth/actor enforcement, schema or dependency change.

Defaults preserve Store Asia/Ho_Chi_Minh/VND and catalog lifecycle metadata. Store
timezone validates the current nonblank/64-character contract, currency uppercase
three-letter shape; no unaccepted IANA/ISO catalog dependency/validation. Ingredient
expiry_tracking/active reuse accepted defaults. Required term business dates/pack
price/lead time, recipe version/dates/yield/loss/lines and movement event time have
no fabricated defaults. Canonical units are exact labels, no conversion. Monetary
values are exact Decimal in Store.currency; unit_cost per base unit, pack_cost per
complete pack. Date and aware event time are supplied independently; no UTC/date
derivation, clock fallback or new future-date rule. Tracked receipt requires expiry;
unknown received_date stays NULL (document OPTIONAL_WARNING capability loss, no
general warnings framework). Lot_code is not an idempotency key.

Recipe/term corrections create new versions with caller-supplied valid inclusive
periods; no overwrite/auto-close. Sales repeats remain CONFLICT with no sum/upsert.
Inventory corrections append movement and update the locked current lot balance
together; negative resulting balance is VALIDATION_ERROR. Minimal exact Decimal
balance arithmetic belongs in a plain Python inventory domain function. Repository
lock/get primitives already exist; no new repository setter is needed if the locked
tracked lot is staged directly inside the authorized application transaction.
Movement note preserves reason; existing opaque paired source refs are retained.
Actor identity has no schema field and auth is expressly outside S1.7.

Acceptance: contract tests first, targeted domain/shape tests and local PostgreSQL
application tests per affected path; close/fresh-session committed reads, same-store
relations, overlap/canonical conflicts, no partial Recipe, receipt lot without
movement never committed, negative result unchanged, failure after real balance
flush rolls back, two concurrent corrections serialize without lost updates.
Full regression only once at final acceptance after targeted green (rerun only if
failure requires correction). Alembic/pip/import/protected-WIP/OpenAPI/live health/
status checks and usable manual guide required. Tests own only shelfcash_test.

Affected BE: internal operational use cases/domain balance only. FE: unchanged API.
ML/Data: no computation/import. Demo: isolated fixed fixtures, no business seeds.
Rollback only S1.7 contracts/use cases/domain helper/error translation/tests/docs;
no database rollback. Canonical S1 closure evaluated after acceptance; full budget
constraint writers/engine cutoffs/rounding/conversions/approval workflows remain
separate future slices, not invented by the money/date convention.

## Observed documentation limits -- CURRENT FACT

Older schema feature narratives still mention absent application inventory/writers.
Those facts were accurate for their slices; new current sections will explicitly
supersede them, without rewriting accepted ADRs or claiming DB-level audit triggers.

## Final outcome -- CURRENT FACT

S1.7 and canonical S1 are COMPLETE after 106 new targeted tests, 188 combined
S1.6/S1.7 final targeted tests and 508 full passes. Full regression ran exactly
once at the final gate, with one existing upstream warning and no skips/failures.
PostgreSQL fresh-session success/rollback/lock evidence, supported reset/upgrade/
status, Alembic/pip/import/OpenAPI/health and protected-WIP checks pass. Models,
migrations, accepted ADRs, public contract, dependencies and existing tests stay
unchanged. Final development state is sixteen empty business tables at 0006 head.
CURRENT_STATE records full evidence; S17_VERIFICATION supplies reviewable steps.
Canonical next proposal is S2 -- Forecast; it is NOT STARTED. No commit was created.
