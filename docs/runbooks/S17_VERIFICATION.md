# S1.7 local operational verification

Classification: CURRENT FACT for implemented commands/assertions. Execution results
are in CURRENT_STATE. Use backend/ on Windows with Docker running. Stop DB clients
before the explicitly authorized development reset; tests own only shelfcash_test.

```powershell
docker compose up -d --wait --wait-timeout 90 postgres
.\scripts\reset_db.ps1
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\alembic.exe current
.\.venv\Scripts\python.exe -m pytest tests/unit/test_operational_contracts.py tests/integration/test_operational_paths.py tests/unit/test_application_contracts.py tests/integration/test_application_paths.py -q
# Run once after targeted tests are green; rerun only when a failure needs a fix.
.\scripts\test.ps1 all
.\scripts\db_status.ps1
.\.venv\Scripts\alembic.exe check
.\.venv\Scripts\python.exe -m pip check
```

Expected: healthy PostgreSQL; unchanged 0006_forecast_decision_persist head; no new
upgrade operations; no broken requirements; green targeted and full suites.
Development status is shelfcash, at_head=true, sixteen empty business tables plus
one revision row. Seed remains an explicit no-op schema check, not business data.
Tests assert actual rows before cleanup; final empty development DB is not evidence
of successful business writes. No e2e/public business API or engine is claimed.

## Reviewable individual flows -- CURRENT FACT

These fixed examples are also usable manual verification commands. Each closes its
writer and reads persisted rows in a fresh Session before isolated fixture cleanup.
Supplier identity is an explicit repository prerequisite, not a new application API.

```powershell
.\.venv\Scripts\python.exe -m pytest tests/integration/test_operational_paths.py::test_s1_operational_chain_through_application_and_fresh_database -v
.\.venv\Scripts\python.exe -m pytest tests/integration/test_operational_paths.py -k 'recipe' -v
.\.venv\Scripts\python.exe -m pytest tests/integration/test_operational_paths.py -k 'receipt or negative_balance or movement_constraint' -v
.\.venv\Scripts\python.exe -m pytest tests/integration/test_operational_paths.py -k 'correction or stale_cached or commit_failure or caller_transaction or new_reads' -v
```

| Scenario | Expected fresh-session database evidence |
| --- | --- |
| S1 chain through typed application paths | Store/Product/Ingredient, versioned term and Recipe lines, Sales quantity 10; received lot 50 corrected to 45 with receipt/correction movements |
| Store/Ingredient | Typed exact defaults/metadata; scoped nullable SKU uniqueness; other Store NOT_FOUND |
| SupplierTerm | Exact pack size 15000 and pack_cost 420000; explicit dates/version; adjacent version accepted; duplicate/active overlap CONFLICT leaves old row unchanged |
| Recipe version | Header and two exact lines persist together; duplicate/overlap leaves old period unchanged; malformed shape/scoped unit rejected |
| Recipe downstream CHECK | Header and a valid line flush first; subsequent invalid line fails; no Recipe or lines remain |
| Receipt | Balance 50 plus one RECEIPT +50; unit_cost 30.125; received_date NULL; supplied +07 event preserved as UTC instant |
| Receipt downstream failure | Failure after lot flush or after movement flush leaves zero lots/movements |
| Corrections | COUNT -5 ->45, MANUAL +2.125 ->52.125, COUNT -50 ->0; old receipt retained; reason note retained; movement sum matches balance |
| Negative balance | Lot 10 minus 20 is VALIDATION_ERROR; balance 10 and only receipt remain |
| Adjustment downstream CHECK | Balance 45 already flushed; invalid movement fails; fresh balance 50 and only old receipt remain |
| Commit failure | Each of six new writers flushes then commit raises; row counts and old balance remain unchanged |
| Caller transaction/reads | Every new writer rejects existing transaction without touching pending work; all new reads leave pending rows unflushed and uncommitted |
| Stale cache | A cached balance 50 refreshes after another writer commits 45; next -7 yields 38 |
| Two concurrent corrections | PostgreSQL pg_stat_activity confirms second writer waiting on Lock; after first commits, final balance 38 and three movements sum to 38 |

Optional read-only inspection through the supported database tooling/connection:

```sql
SELECT id, store_id, product_id, version, effective_from, effective_to
FROM recipes ORDER BY store_id, product_id, version;
SELECT recipe_id, ingredient_id, quantity, unit FROM recipe_lines ORDER BY recipe_id, ingredient_id;
SELECT supplier_id, ingredient_id, version, pack_cost, effective_from, effective_to FROM supplier_terms;
SELECT id, store_id, ingredient_id, received_date, expiry_date, on_hand_quantity, unit, unit_cost FROM inventory_lots;
SELECT lot_id, movement_type, quantity_delta, occurred_at, note, reference_type, reference_id
FROM inventory_movements ORDER BY lot_id, occurred_at, id;
```

Do not run concurrent test commands: fixtures reset only their own test database.
No manual fixture writes to development are needed. HTTP 2xx is not persistence
evidence. Use FULL_TEST_FLOW for live Uvicorn health/OpenAPI checks: /health must
return {"status":"ok","service":"shelfcash-backend"}; generated/live schemas must
equal the pre-S1.7 baseline, with only /health. Stop the verifier server afterward.

Review git diff/status and baseline hashes: models, migrations, accepted ADRs,
API_CONTRACT, pyproject dependencies and all pre-existing tests stay unchanged.
Rollback only S1.7 application/domain/tests/docs; no database rollback. Trusted
internal scope is not actor authorization. No absolute inventory overwrite,
auto-close version, full Sales correction, unit/currency conversion, engine, public
business API or S2+ implementation is started. POSIX equivalents use existing sh
wrappers and .venv/bin tools; this Windows session makes no native POSIX claim.
