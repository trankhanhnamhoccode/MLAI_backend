# S1.2 task contract

ACCEPTED DECISION for this authorized slice: persist only Product, Ingredient,
Recipe and RecipeLine. PostgreSQL remains governed by ADR-007; the old SQLite
instruction is superseded. Before editing, the working tree was clean. S1.1 uses
0002_identity_store and only three business tables. Public API remains /health.

Freeze: nullable, case-sensitive SKU unique per store (multiple NULLs allowed);
nonunique names; nullable nonnegative finite price in store currency; exact,
nonblank units; active defaults true and expiry_tracking defaults false.
Quantities use finite Decimal/NUMERIC without implicit rounding. Version is a
positive integer. Yield is in Product.selling_unit. Recipe dates are inclusive,
NULL end is unbounded, and overlapping versions of one product are forbidden.
Loss defaults zero, is recipe-level, and is in [0,1). No BOM computation exists.

Use PostgreSQL btree_gist plus a product/date-range exclusion constraint, including
concurrent SQL writes. Retain the extension on downgrade: it may be shared.
Composite foreign keys enforce recipe/product store agreement. RecipeLine adds
required store_id as an integrity witness: recipe/store and ingredient/store/unit
foreign keys enforce both tenancy and exact Ingredient.base_unit. Parent updates
and deletes cannot invalidate existing references. Supporting composite unique
constraints are required FK targets, not speculative indexes.

Test first, then models/migration, isolated shelfcash_test; verify fresh sessions,
constraints, fresh migration, downgrade/re-upgrade, existing tests and unchanged
OpenAPI. Rollback scope: downgrade only 0003, dropping its four tables (data lost).
Backend persistence and local inspection change; FE/API/ML behavior does not.
No repositories, services, business endpoints, auth or S1.3 implementation.
Documentation and manual inspection must reflect actual verified results.

## Verification — CURRENT FACT

2026-10-05, Windows/Python 3.11.9: first schema test failed against the old 0002
baseline before implementation. Final targeted run: 51 passed. Canonical PowerShell
full runner: 93 passed (14 unit, 77 integration, 2 API), one existing upstream warning.
Fresh isolated migration and downgrade 0003->0002->head pass; existing bootstrap
downgrade to scaffold/base and re-upgrade also pass. Metadata comparison passes;
exclusion is independently verified by catalog query and actual overlapping SQL.

Compose config/up/wait/ps succeed, PostgreSQL 17.11 healthy. Development reset,
upgrade/current, seed/status and feature SQL inspection pass at 0003_catalog_recipe,
with seven empty business tables and one revision row. App/model/domain imports
with DB connections forbidden succeed. Live health and generated/live OpenAPI
match the saved pre-S1.1 baseline; verification server stopped. pip check passes.
Diff/status/whitespace/scope reviewed. API_CONTRACT and API/domain/repository code,
dependencies and accepted ADRs unchanged; no commit. POSIX wrappers unchanged,
prior syntax validation only; no POSIX runtime verification claimed here.
