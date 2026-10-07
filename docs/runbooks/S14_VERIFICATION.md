# S1.4 local persistence verification

CURRENT FACT: persistence only, not a running Forecast/Decision pipeline. Run from
backend with native venv/local Docker per FULL_TEST_FLOW. Reset intentionally destroys
development data. Tests exclusively own shelfcash_test; do not run concurrent clients.

```powershell
docker compose up -d --wait postgres
.\scripts\reset_db.ps1
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\alembic.exe current
.\.venv\Scripts\python.exe -m pytest tests/integration/test_forecast_decision_persistence.py -q
.\scripts\test.ps1 all
.\scripts\seed_demo.ps1
.\scripts\db_status.ps1
```

Expected: healthy PostgreSQL, head 0006_forecast_decision_persist, 58 targeted / 240 full tests
pass. Sixteen empty business tables plus one Alembic version row; seed writes no data.
No import/order/what-if/strategy-result/procurement-line tables or business APIs added.

Inspect actual PostgreSQL using Python, without GUI/host psql:

```powershell
@'
from app.config import Settings
from app.infrastructure.database.engine import create_database_engine
from sqlalchemy import text
queries = [
    "SELECT version_num FROM alembic_version",
    "SELECT table_name,column_name,data_type,is_nullable FROM information_schema.columns WHERE table_schema='public' AND table_name IN ('forecast_runs','forecast_predictions','decision_runs') ORDER BY table_name,ordinal_position",
    "SELECT c.relname,con.conname,pg_get_constraintdef(con.oid) FROM pg_constraint con JOIN pg_class c ON c.oid=con.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relname IN ('forecast_runs','forecast_predictions','decision_runs') ORDER BY c.relname,con.conname",
    "SELECT tablename,indexname,indexdef FROM pg_indexes WHERE schemaname='public' AND tablename IN ('forecast_runs','forecast_predictions','decision_runs') ORDER BY tablename,indexname",
    "SELECT id,store_id,status,training_start_date,training_end_date,forecast_start_date,forecast_end_date,model_type,model_version,artifact_key,metrics_json,input_fingerprint FROM forecast_runs ORDER BY id",
    "SELECT forecast_run_id,store_id,product_id,forecast_date,p25,p50,p75 FROM forecast_predictions ORDER BY forecast_run_id,product_id,forecast_date",
    "SELECT id,store_id,status,forecast_run_id,planning_start_date,planning_end_date,package_schema_version,input_fingerprint,input_snapshot_json,decision_package_json,recommended_strategy,completed_at FROM decision_runs ORDER BY id",
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

Expected revision [('0006_forecast_decision_persist',)]. UUID/DATE/TIMESTAMPTZ,
NUMERIC and object JSONB columns match DATABASE_SCHEMA; same-store composite FKs,
prediction business key and status/window/quantile/state checks exist. Three row
queries return [] after reset. Tests insert deterministic fixtures, commit/close and
verify exact Decimal/JSON values in fresh sessions before test-only reset cleanup.

Targeted migration test executes 0006->0005->head, checking only these three tables
disappear/reappear. Destructive downgrade is isolated to shelfcash_test. Manual
development downgrade loses historical runs; preserve wanted data first. No immutability
trigger or cross-table horizon check exists. See FORECAST/DECISION_RUN for future service
responsibilities and fixture limitations; live unchanged health/OpenAPI checks are in
FULL_TEST_FLOW. No engine/LLM output is used as a test oracle.

POSIX equivalents: existing scripts/*.sh with .venv/bin/python/alembic. Windows
PowerShell runtime verification is recorded in CURRENT_STATE; POSIX wrappers retain
historical syntax-only verification, no native POSIX runtime claim for this slice.
