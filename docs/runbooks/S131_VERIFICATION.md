# S1.3.1 local verification

CURRENT FACT: run from backend with local Docker/venv. Reset intentionally destroys
development data; tests own only shelfcash_test. Do not run concurrent reset/test clients.

```powershell
docker compose up -d --wait postgres
.\scripts\reset_db.ps1
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\alembic.exe current
.\.venv\Scripts\python.exe -m pytest tests/integration/test_data_semantics_correction.py -q
.\scripts\test.ps1 all
.\scripts\db_status.ps1
```

Expected: healthy PostgreSQL; head 0005_data_semantics_correction; 9 targeted and
182 full tests pass. Development has thirteen empty business tables and one revision
row. No import, readiness, Forecast or Decision tables are added. Seed remains no-op.

Inspect using Python/psycopg, without a GUI or host psql:

```powershell
@'
from app.config import Settings
from app.infrastructure.database.engine import create_database_engine
from sqlalchemy import text
engine = create_database_engine(Settings())
try:
    with engine.connect() as connection, connection.begin():
        connection.execute(text("SET TRANSACTION READ ONLY"))
        print(connection.execute(text("SELECT version_num FROM alembic_version")).all())
        print(connection.execute(text("SELECT table_name,column_name,is_nullable,column_default FROM information_schema.columns WHERE table_schema='public' AND (table_name='inventory_lots' AND column_name='received_date' OR table_name='supplier_terms' AND column_name IN ('effective_from','lead_time_days','pack_cost')) ORDER BY table_name,column_name")).all())
        print(connection.execute(text("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname='ck_inventory_lots_expiry'")).all())
        print(connection.execute(text("SELECT id,received_date,expiry_date,on_hand_quantity FROM inventory_lots ORDER BY id")).all())
finally:
    engine.dispose()
'@ | .\.venv\Scripts\python.exe -
```

Expected: revision 0005; received_date nullable YES/default None; supplier fields
nullable NO/default None. Expiry CHECK permits unknown receipt or expiry, otherwise
requires expiry >= receipt. Lot query is [] after reset. Tests create their own records,
commit/close/reload to confirm unknown receipt is None with known expiry/quantity,
then clean them up. Canonical pack fixture is 420000 VND for 15000 g, not 28000.

Targeted tests execute 0005->0004->head with known dates and prove data survives.
With NULL dates downgrade fails transactionally, preserving head/schema/data. Before
manual downgrade, resolve dates using confirmed source evidence or explicitly reset
development data; never backfill upload/snapshot/current dates. Downgrade farther than
0004 can drop business history. Full setup/live HTTP commands are in FULL_TEST_FLOW.
No public API is added; warnings/readiness are accepted future policy, unimplemented.

POSIX equivalents use existing .sh wrappers and .venv/bin/python/alembic. This Windows
slice does not claim POSIX runtime verification.
