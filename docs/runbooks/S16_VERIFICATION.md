# S1.6 local application verification

Classification: CURRENT FACT for implemented commands/assertions; execution results
are recorded in CURRENT_STATE. From backend/ on Windows with Docker running:

```powershell
docker compose up -d --wait --wait-timeout 90 postgres
# Stop backend/DB clients first. This is the authorized empty development baseline.
.\scripts\reset_db.ps1
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\alembic.exe current
.\.venv\Scripts\python.exe -m pytest tests/unit/test_application_contracts.py tests/integration/test_application_paths.py -q
.\scripts\test.ps1 all
.\scripts\db_status.ps1
.\.venv\Scripts\alembic.exe check
.\.venv\Scripts\python.exe -m pip check
```

Expected: healthy PostgreSQL, unchanged head 0006_forecast_decision_persist,
No new upgrade operations detected, no broken requirements, green targeted/full
suites. Development status: shelfcash, at_head=true, sixteen empty business tables
and one revision row. Tests own only shelfcash_test and never reset development.
There is no business seed, HTTP CRUD or engine calculation to demonstrate.

For reviewable individual flows, execute these fixed integration examples:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/integration/test_application_paths.py::test_product_commit_close_fresh_scoped_read tests/integration/test_application_paths.py::test_sales_commit_duplicate_no_correction_and_ordered_range -v
.\.venv\Scripts\python.exe -m pytest tests/integration/test_application_paths.py::test_forecast_complete_fresh_prediction_metadata_and_rerun tests/integration/test_application_paths.py::test_decision_complete_copied_input_output_and_fresh_snapshot -v
.\.venv\Scripts\python.exe -m pytest tests/integration/test_application_paths.py::test_forecast_downstream_db_failure_rolls_back_flushed_prediction tests/integration/test_application_paths.py::test_decision_downstream_failure_after_flush_rolls_back_all_fields -v
.\.venv\Scripts\python.exe -m pytest tests/integration/test_application_paths.py::test_recipe_temporal_read_inclusive_open_end_typed_lines -v
```

Expected evidence inside each test (asserted before fixture cleanup):

| Flow | Fresh-session persisted state |
| --- | --- |
| Product create -> scoped read | Tea, cup, TEA, exact price 25000.125, matching Store; other Store NOT_FOUND |
| Sales insert/history | Quantities 0 / 10.125 / 12.125 on fixed chronological dates; changed duplicate is CONFLICT and old 0 remains |
| Forecast start/complete | COMPLETED, fingerprint fixture-input, metrics MAE 2.125, one prediction 80 / 100.125 / 130; rerun new UUID |
| Forecast downstream check failure | A valid prediction is flushed first, then completion fails; RUNNING and zero predictions after rollback |
| Decision complete | Stored quantity string 20.125, version 1, supplied three fixture evaluations, BALANCED, fingerprint and terminal time; DTO/input mutation cannot change DB |
| Decision downstream OperationalError | Output flushes then error propagates; fresh RUNNING row has no snapshot/package/fingerprint/version/recommendation/time |
| Recipe date lookup | Inclusive version 1, exact line 800.125 ml; next version has open end; no effective version returns None |

No manual fixture writes to shelfcash are required. Tests close writer Sessions and
reload through fresh Sessions, rather than trusting in-memory ORM or HTTP 2xx.

Use FULL_TEST_FLOW's live server/health/OpenAPI commands. GET /health remains exact
{"status":"ok","service":"shelfcash-backend"}; schema paths only /health, and
generated/live OpenAPI must equal the pre-S1.6 baseline. Stop the server afterward.
Run git diff / git status to inspect scope. API_CONTRACT, models, migrations, accepted
ADRs and dependencies must be unchanged. POSIX counterparts use .venv/bin/python,
.venv/bin/alembic and the existing sh wrappers; native POSIX execution is not claimed
by Windows verification. No public business API or next slice is started.
