# S2.3 isolated verification and reconciliation

CURRENT FACT: trusted internal baseline execution, not a public HTTP or evaluated ML flow.
Run from backend on Windows with local Compose PostgreSQL healthy. No development reset.

```powershell
docker compose up -d --wait postgres
.\.venv\Scripts\python.exe -m pytest tests/unit/test_application_contracts.py tests/unit/test_forecast_commit_errors.py tests/unit/test_forecast_serialization.py tests/unit/test_forecast_execution.py tests/unit/test_forecast_baseline.py tests/integration/test_forecast_execution_flow.py tests/integration/test_forecast_execution_s1_regression.py tests/integration/test_database_bootstrap.py -q --tb=short
# Fixtures migrate/reset only shelfcash_test, never shelfcash:
.\.venv\Scripts\python.exe -m scripts.verify_forecast_execution
```

Manual script explicitly selects Settings.test_database_url, checks local test target
and current head, writes a synthetic Store/Product/sparse Sales fixture in shelfcash_test,
executes and persisted-replays, and asserts committed predictions/input via fresh Session.
It leaves the printed IDs visible for SQL inspection. No business seed is installed;
subsequent isolated tests own reset/cleanup. No development entities touched.

Inspect through a connection explicitly targeting shelfcash_test:

```sql
SELECT id, status, model_type, model_version, input_fingerprint, error_code
FROM forecast_runs WHERE id = '<printed run_id>'::uuid;
SELECT serialization_version, digest, prepared_json FROM forecast_run_inputs
WHERE forecast_run_id = '<printed run_id>'::uuid;
SELECT product_id, forecast_date, p25, p50, p75 FROM forecast_predictions
WHERE forecast_run_id = '<printed run_id>'::uuid ORDER BY forecast_date, product_id;
```

Expected historical_quantile_baseline/1, COMPLETED, same digest for both new UUID runs,
seven dates 2026-09-12..18, 2.5/5/7.5 and only two observed samples. READY is baseline
computability, never confidence/accuracy/freshness. History unit stability is assumed;
snapshot consistency is not knowledge-at-D after later corrections.

## Errors / manual inspection

ForecastExecutionError exposes run_id/outcome/code; original cause is chained only for
trusted diagnostics. No raw exception strings persisted. On UNKNOWN, do not blindly
fail or retry the old run: open a fresh scoped Session and inspect run/input/predictions.
COMPLETED must retain a verified digest and exact validated aggregate. FAILED/RUNNING
keep input. Missing retention or integrity failure blocks replay. A failed recording
may leave RUNNING; COMPLETED_READ_FAILED reports acknowledged completion, not failure.
Only recognized SQLAlchemy/psycopg transport/unknown-resolution commit exceptions
can reconcile into success; arbitrary commit-call/programming errors cannot. A
post-commit callback/close bug reports run ID and actual COMPLETED without failing it.
Rollback/close/invalidation errors remain secondary notes/trusted logs, preserving
the original execution cause. See FORECAST_EXECUTION for classifier/cleanup limits.

Process crash can leave abandoned RUNNING. No automatic expiry/worker exists. Explicit
manual failure uses existing ForecastUseCases.fail in an idle owned Session only after
confirming RUNNING/current state and sanitizing the reason; terminal runs are untouched.
Replay uses retained content; rerun execute captures current data. Both persisted paths
create new UUID. Never retry by rewriting an old terminal run.

## Migration / rollback

Head: 0007_forecast_input_retention. Alembic downgrade to 0006 drops only retained inputs,
leaves runs/predictions, and destroys replay ability for those runs. Export/backup input
records before real-history downgrade. Migration roundtrip is exercised by isolated tests.
Do not run development reset/downgrade for verification. Full regression once at final
gate; outcomes are recorded in S23_TASK_NOTES/CURRENT_STATE. No S3 starts automatically.
