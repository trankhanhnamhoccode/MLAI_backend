# S1.3 local persistence verification

CURRENT FACT: schema-only verification, no HTTP business flow. From backend/ with
Python venv/Docker configured per FULL_TEST_FLOW. Stop DB clients before resetting
development state. Tests own only shelfcash_test; do not run suites concurrently.

```powershell
docker compose up -d --wait postgres
.\scripts\reset_db.ps1
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\alembic.exe current
.\.venv\Scripts\python.exe -m pytest tests/integration/test_supplier_operational_constraints.py -q
.\scripts\test.ps1 all
.\scripts\seed_demo.ps1
.\scripts\db_status.ps1
```

Expected: healthy PostgreSQL; head 0006_forecast_decision_persist; targeted/full suite
pass. Seed reports no business seed data and writes nothing. Status reachable true,
database shelfcash, at_head true, alembic_version count 1 and all sixteen business
tables count 0: users, stores, store_memberships, products, ingredients, recipes,
recipe_lines, suppliers, supplier_terms, sales_daily, inventory_lots,
inventory_movements, business_constraints, forecast_runs, forecast_predictions, decision_runs. No Import/Order/What-if tables.

Inspect actual schema and each domain's persisted rows, no GUI/host psql:

```powershell
@'
from app.config import Settings
from app.infrastructure.database.engine import create_database_engine
from sqlalchemy import text
queries = [
    "SELECT version_num FROM alembic_version",
    "SELECT table_name,column_name,data_type,is_nullable FROM information_schema.columns WHERE table_schema='public' ORDER BY table_name,ordinal_position",
    "SELECT c.relname,con.conname,pg_get_constraintdef(con.oid) FROM pg_constraint con JOIN pg_class c ON c.oid=con.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' ORDER BY c.relname,con.conname",
    "SELECT id,store_id,name,active FROM suppliers ORDER BY id",
    "SELECT supplier_id,ingredient_id,version,unit,pack_size_base_quantity,minimum_order_packs,pack_cost,effective_from,effective_to,active FROM supplier_terms ORDER BY supplier_id,ingredient_id,version",
    "SELECT store_id,product_id,sales_date,quantity FROM sales_daily ORDER BY store_id,product_id,sales_date",
    "SELECT id,store_id,ingredient_id,received_date,expiry_date,on_hand_quantity,unit FROM inventory_lots ORDER BY id",
    "SELECT lot_id,store_id,ingredient_id,movement_type,quantity_delta,occurred_at,reference_type,reference_id FROM inventory_movements ORDER BY lot_id,occurred_at,id",
    "SELECT store_id,scope_type,scope_id,constraint_type,numeric_value,unit,version,effective_from,effective_to,active FROM business_constraints ORDER BY store_id,scope_type,scope_id,constraint_type,version",
]
engine = create_database_engine(Settings())
try:
    with engine.connect() as connection, connection.begin():
        connection.execute(text("SET TRANSACTION READ ONLY"))
        for query in queries:
            print(query)
            print(connection.execute(text(query)).all())
finally:
    engine.dispose()
'@ | .\.venv\Scripts\python.exe -
```

Expected revision [('0006_forecast_decision_persist',)], documented UUID/NUMERIC/
DATE/TIMESTAMPTZ columns, named constraints matching DATABASE_SCHEMA; six domain
row queries return []. In particular exclusion constraints are partial WHERE active,
business constraint version uniqueness is NULLS NOT DISTINCT, same-store/unit/lot
FKs exist and numeric/range/type checks are installed. Automated fixtures commit,
close and verify records using a new session before isolated reset; see feature docs
for exact fixture values. Database state, not HTTP 2xx, proves persistence.

Targeted test verifies fresh migration and descent from head through 0006/0005/0004
to 0003. The 0006 step removes three run tables; 0004->0003 removes the six S1.3
tables. Re-upgrade recreates all; original identity/catalog migrations remain intact.
Failed transaction requires rollback; reset retry/guards in DATABASE_RESET. No seed
records fabricated. Existing .sh wrappers share the Python implementation; use
.venv/bin/python/alembic on POSIX. This Windows slice does not claim POSIX runtime
verification. Health/OpenAPI/pip checks and fresh setup remain in FULL_TEST_FLOW.
