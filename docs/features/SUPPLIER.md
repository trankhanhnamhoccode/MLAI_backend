# Supplier persistence and terms boundary -- S1.3 / S1.7

## SupplierTerm application path -- CURRENT FACT (S1.7)

SupplierTermUseCases.create/get uses typed by-value contracts and explicit Store
scope. Supplier identity remains a repository prerequisite. Required procurement
facts are not defaulted: version, effective_from, pack size, minimum packs, per-pack
cost and lead time. Same-store Supplier/Ingredient and exact base unit are validated.
Decimal pack_cost is whole-pack cost in Store.currency: 15000 g at confirmed
28 VND/g means 420000 VND/pack, supplied explicitly. No conversion/import engine.
New terms create a new explicit version; named unique/active-period exclusions map
to CONFLICT and leave previous terms untouched. No overwrite or auto-close.
Inclusive adjacent nonoverlapping periods pass; active overlaps fail; inactive
term overlap remains accepted. Writes own begin/flush/commit/rollback; scoped reads
never commit/autoflush. Fresh-session, rollback, ownership and commit-failure tests
are in test_operational_paths.py. See
[APPLICATION_CONTRACTS](APPLICATION_CONTRACTS.md) and
[S17_VERIFICATION](../runbooks/S17_VERIFICATION.md).

## Original schema slice -- HISTORICAL INFORMATION

The following S1.3/S1.3.1 absence claims describe that delivery; S1.5 repositories
and S1.7 term boundaries supersede them. Procurement, identity API, source mapping
and conversion remain future work; canonical storage rules are unchanged.

CURRENT FACT (S1.5): internal repository access is now implemented; see
[PERSISTENCE_ACCESS](PERSISTENCE_ACCESS.md). Statements below about repository
absence describe the HISTORICAL INFORMATION of this schema slice. Its direct
Session tests remain schema evidence; operational services/APIs/engines and
application lifecycle/audit enforcement remain unimplemented.

## S1.3.1 review — ACCEPTED DECISION / CURRENT FACT

ADR-010 governs completeness. Price schema UNCHANGED: pack_cost is cost of one
complete pack in Store.currency. Known source 15 kg/pack and 28,000 VND/kg means
420,000 VND/pack (15,000 g if base_unit=g), never pack_cost=28,000. Existing
representation is unambiguous, so no supplier-price migration is necessary.
Future mapping may derive this only from proven units; no conversion/import exists.

effective_from UNCHANGED: required, no default. It is a business fact, not backend
metadata. Unknown source date cannot be promoted to canonical SupplierTerm and must
never become upload date. Internal version is system-managed metadata; version 1
may be assigned by a future canonical writer. Strict term inputs, including pack
cost/quantity, minimum packs and lead time, must be known before canonical promotion.
Supplier identity may exist independently of unresolved term data. Unknown lead time
cannot become zero to force delivery feasibility. No application promotion flow exists.

Regression tests: test_data_semantics_correction.py checks NULL effective_from,
lead_time_days and pack_cost rejection, no defaults, and exact 420,000 per-pack
Decimal fresh-session reload. These test canonical storage, not import normalization.

## Status and purpose

CURRENT FACT: Supplier/SupplierTerm persistence exists; no supplier API, repository,
procurement or conversion computation. ADR-007 governs PostgreSQL; ADR-008 governs
future source/correction behavior. Exact columns/constraints are in DATABASE_SCHEMA.

## Business invariants and persistence

Tables written/read directly in tests: suppliers, supplier_terms; references read
stores and ingredients. Supplier belongs to one Store; names nonblank, nonunique.
Supplier ↔ Ingredient is many-to-many through versioned terms in the same Store.
Positive integer version unique per pair across active/inactive rows. Date endpoints
inclusive, NULL end unbounded; end >=start. At D choose active and start<=D and
(end IS NULL or D<=end), yielding 0/1. GiST exclusion blocks active overlap, including
shared boundary day and activation of overlapping inactive drafts.

Pack size is finite >0 in Ingredient.base_unit; retained unit is a composite-FK
witness protecting store/unit and future base-unit edits. Minimum whole packs >=1,
finite pack cost >=0 in Store currency, integer lead time >=0, optional shelf life >=0.
12 x 1L milk pack is normalized externally to 12000 ml; 2 packs at 360000 VND each
means 720000 VND. This is an input example, not implemented procurement behavior.
Changed terms should create a next version with explicit periods; direct SQL remains
editable. No immutable history service or currency conversion exists.

## Automated tests and fixtures

`tests/integration/test_supplier_operational_constraints.py` uses shelfcash_test.
Fixed two stores, nonunique supplier names, Milk ml/Coffee g, dates Jan 1–Mar 31
2026 and adjacent Apr 1 open end, 12000 ml/pack, minimum 2, cost 360000, lead 3,
shelf life 10. Tests commit/close/new-session reload, many suppliers/ingredients,
unique version, inclusive/open-ended selection, overlap/activation, invalid numbers,
missing/cross-store references and wrong units. Zero cost/durations and minimum 1 pass.

## Manual verification, inspection and expected state

Use [S13_VERIFICATION](../runbooks/S13_VERIFICATION.md): start healthy PostgreSQL,
reset/migrate, run targeted/full tests, inspect actual schema/rows. Expected head
0006_forecast_decision_persist, suppliers and supplier_terms count 0 after reset;
tests do not mutate development data. The shared runbook executes these queries:

```sql
SELECT id, store_id, name, active FROM suppliers ORDER BY id;
SELECT supplier_id, ingredient_id, version, unit, pack_size_base_quantity,
       minimum_order_packs, pack_cost, effective_from, effective_to, active
FROM supplier_terms ORDER BY supplier_id, ingredient_id, version;
```

After reset both return no rows; targeted fixture assertions verify the exact values
above through new sessions. Schema inspection must show pair/version unique,
same-store/unit FKs, numeric checks and ex_supplier_terms_pair_period WHERE active.

## Failure paths, reset and limitations

Duplicate versions, invalid values/references/units or overlap fail in PostgreSQL;
invalid reversed ranges can raise a data error before CHECK evaluation. Roll back
before retry. reset_db safely recreates head; downgrade 0004->0003 drops six new
tables/data (not only supplier tables). Seed remains no-op, no demo data.
No procurement, application validation/mutation, auth or public contracts. Future API
and history correction workflow remain PROPOSAL.
