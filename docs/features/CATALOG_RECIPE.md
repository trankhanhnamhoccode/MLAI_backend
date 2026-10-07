# Catalog + Recipe persistence and boundaries -- S1.2 / S1.7

## Ingredient and Recipe writes -- CURRENT FACT (S1.7)

IngredientUseCases.create/get validates Store and returns copied typed values;
nullable scoped SKU conflicts map to CONFLICT. RecipeUseCases.create_version
validates scoped Product/Ingredients, exact line units, unique ingredient lines,
positive yield and explicit loss in [0,1). Header and all supplied lines persist
atomically; a downstream failure after header/line flush leaves neither behind.
Required lines may explicitly be empty under existing storage semantics; no BOM
readiness is claimed. get_active keeps inclusive date selection and typed lines.
Corrections create explicit new versions/periods; uniqueness/period exclusions map
to CONFLICT without auto-closing or overwriting old rows. Writes own transactions;
reads do not flush/commit caller work. No schema/API/unit conversion/BOM change.
Fresh-session, atomic rollback, commit-failure, unit and ownership tests are in
new test_operational_paths.py. See
[APPLICATION_CONTRACTS](APPLICATION_CONTRACTS.md) and
[S17_VERIFICATION](../runbooks/S17_VERIFICATION.md).

## Original schema slice -- HISTORICAL INFORMATION

The following S1.2/S1.5/S1.6 implementation-status statements describe earlier
delivery. S1.7 above supersedes Ingredient/Recipe writer absence claims; the
storage constraints and future engine/public API limitations remain applicable.

CURRENT FACT (S1.6): typed Product create/scoped read and effective Recipe+lines
read now exist; see [APPLICATION_CONTRACTS](APPLICATION_CONTRACTS.md) and its
application integration tests. The schema-slice absence statements below are
HISTORICAL INFORMATION where superseded by S1.5/S1.6. Recipe/Ingredient writers,
BOM and public business APIs remain unimplemented.

CURRENT FACT (S1.5): internal repository access is now implemented; see
[PERSISTENCE_ACCESS](PERSISTENCE_ACCESS.md). Statements below about repository
absence describe the HISTORICAL INFORMATION of this schema slice. Its direct
Session tests remain schema evidence; operational services/APIs/engines and
application lifecycle/audit enforcement remain unimplemented.

## Status and purpose

CURRENT FACT: Catalog/Recipe persistence exists. Catalog/Recipe public API does
NOT exist. BOM computation does NOT exist. Store-owned menu items, canonical
ingredients and dated recipe definitions are stored for later deterministic BOM.
ACCEPTED DECISION: storage contract is in [DATABASE_SCHEMA](../DATABASE_SCHEMA.md),
under ADR-002 and ADR-007. No new architecture framework or API contract is introduced.

## Tables, relationships and business invariants

Reads/writes through direct SQLAlchemy Session: products, ingredients, recipes,
recipe_lines; stores is read/referenced. Migration writes alembic_version.
Store -> Product/Ingredient; Product -> Recipe -> RecipeLine -> Ingredient.
UUID PKs, TIMESTAMPTZ defaults and UTC sessions follow the existing baseline.
Definitions/catalog are mutable; no snapshot immutability or authorization exists.

- Product and Ingredient SKUs are nullable, case-sensitive, unique per store;
  different stores can share a SKU and multiple NULLs are allowed. Names nonunique.
- Optional price is finite >=0 in store currency. Units/name nonblank.
  Ingredient expiry_tracking defaults false; active defaults true for catalog rows.
- Recipe version >0 and unique per product. Inclusive dates; end >=start or NULL.
  NULL end is unbounded. At D: start<=D AND (end IS NULL OR D<=end).
- PostgreSQL GiST exclusion with btree_gist rejects product-period overlap on
  insert/update, including concurrent writers. Shared end/start day is an overlap;
  next-day transition is valid. Resolution yields zero/one row, not a fallback version.
- yield_quantity >0 in Product.selling_unit; line quantity >0 for the entire yield.
  NUMERIC/Decimal avoids binary float/fixed-scale rounding; values must be finite.
- Recipe-level loss defaults 0, is in [0,1). Future BOM uses theoretical/(1-loss),
  e.g. 800 ml / 10 cups / 0.95 ~84.21 ml per cup. This is a future computation rule.
- Ingredient appears once per Recipe. Line.unit exactly equals Ingredient.base_unit.
  RecipeLine.store_id is a deliberate FK integrity witness. Composite FKs reject
  wrong product/store, wrong ingredient/store and wrong unit even in direct SQL.
  Parent updates/deletes cannot invalidate existing graph references.

See DATABASE_SCHEMA for every column/constraint/index and why support unique indexes
exist. No unit conversion, implicit normalization, rounding or permission engine.

## Automated tests and required fixtures

`tests/integration/test_catalog_recipe_schema.py` owns only shelfcash_test via
guarded fixtures; fixed dates (2026-01-01 through 2026-03-31, next version 2026-04-01),
COFFEE/MILK, 10 cups yield, 800.125 ml line quantity, price 25000, loss default zero.
Tests commit/close/reload all four models and compare exact Decimal/reference/default
values. Tests also exercise raw SQL constraints, SKU/null semantics, invalid numeric
values, version/date overlap and inclusive/open-ended resolution, missing parents,
cross-store/unit rejection, parent mutations and downgrade/re-upgrade. Future tables
must not exist. S1.1 tests and metadata comparison remain regression checks.
No demo records are seeded; seed_demo verifies head/schema and writes no rows.

## Manual verification and expected database state

From backend/ with Docker running; stop backend/DB clients before development reset:

```powershell
docker compose up -d postgres
docker compose up -d --wait --wait-timeout 90 postgres
.\scripts\reset_db.ps1
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\alembic.exe current
.\.venv\Scripts\python.exe -m pytest tests/integration/test_catalog_recipe_schema.py -q
.\scripts\test.ps1 all
.\scripts\db_status.ps1
```

Expected: postgres healthy; head `0006_forecast_decision_persist`; targeted/full tests pass.
Status: reachable true, database shelfcash, at_head true, alembic_version count 1;
users, stores, store_memberships, products, ingredients, recipes, recipe_lines and `suppliers`, `supplier_terms`, `sales_daily`, `inventory_lots`,
`inventory_movements`, `business_constraints`, `forecast_runs`, `forecast_predictions`, `decision_runs` all
count 0 after reset/tests. Tests write only shelfcash_test, not development state.

Inspect columns and actual DB constraint definitions without GUI/host psql:

```powershell
.\.venv\Scripts\python.exe -c "from app.config import Settings; from app.infrastructure.database.engine import create_database_engine; from sqlalchemy import text; e=create_database_engine(Settings()); c=e.connect(); print(c.execute(text('SELECT table_name,column_name,data_type,is_nullable FROM information_schema.columns WHERE table_schema=:schema ORDER BY table_name,ordinal_position'), {'schema':'public'}).all()); print(c.execute(text('SELECT c.relname,con.conname,pg_get_constraintdef(con.oid) FROM pg_constraint con JOIN pg_class c ON c.oid=con.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=:schema ORDER BY c.relname,con.conname'), {'schema':'public'}).all()); c.close(); e.dispose()"
```

Expected: UUID PK/FK columns, NUMERIC quantities/price/loss, DATE effective bounds,
aware timestamps; unique SKU/version/recipe-ingredient constraints, positive/range
checks, exclusion `ex_recipes_product_period`, and same-store/unit composite FKs.
To reproduce actual persisted values run targeted tests: each verifies database
state through a new session, not the writer object. No HTTP upload/CRUD scenario exists.
POSIX equivalent uses `.venv/bin/python`, `.venv/bin/alembic` and existing `.sh`
wrappers; syntax-only/platform runtime status is recorded in TESTING/CURRENT_STATE.

## Failure paths, reset/retry and known limitations

Invalid writes fail with PostgreSQL integrity errors; malformed reversed date ranges
may raise a range data error before CHECK evaluation. Roll back the failed transaction
before retry. [DATABASE_RESET](../runbooks/DATABASE_RESET.md) documents guards.
Downgrade to 0002 drops only these four tables/data; re-upgrade recreates them.
btree_gist is retained on downgrade because it may be preexisting/shared. Reset public
recreates its extension objects through migration; local Compose role has permission.
Alembic metadata comparison is not a complete exclusion-constraint oracle; targeted
tests inspect pg_constraint and exercise actual rejection behavior.
No repositories, application services, CRUD, BOM or auth. S1.3 persistence is
documented separately; Forecast/Decision run storage is documented separately; Import/Order/What-if tables remain absent.
Future API is PROPOSAL; no public payload/endpoint contracts are frozen here.
