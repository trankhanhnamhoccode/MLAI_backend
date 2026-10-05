# Forecast persistence — S1.4

CURRENT FACT (S1.5): internal repository access is now implemented; see
[PERSISTENCE_ACCESS](PERSISTENCE_ACCESS.md). Statements below about repository
absence describe the HISTORICAL INFORMATION of this schema slice. Its direct
Session tests remain schema evidence; operational services/APIs/engines and
operational inventory audit enforcement remains unimplemented. CURRENT FACT:
S1.5 repository writers now guard RUNNING-only terminal transitions; Forecast also
guards prediction append. Direct ORM/SQL changes can still bypass these guards.

## Status / purpose

CURRENT FACT: ForecastRun and ForecastPrediction storage exists. Forecast computation
NOT IMPLEMENTED. No baseline algorithm, LightGBM, training, feature engineering,
repository, artifact service, public API or fallback policy exists. ADR-001/004/007/
010/011 govern backend facts, PostgreSQL, completeness and historical policy.

## Entities and business invariants

forecast_runs records one Store's execution: explicit RUNNING/COMPLETED/FAILED,
ordered inclusive training dates and forecast horizon, actual model_type/model_version,
optional artifact_key/object metrics_json, canonical input_fingerprint, explicit aware
started_at/terminal completed_at, sanitized error_code/summary and metadata timestamps.
There is no requirement that forecast immediately follows training. Every state records
requested windows/model metadata; future fallback must record the model actually used.
Completed fingerprint is required; fingerprints are nonunique audit/debug metadata.
Future canonical serialization/hash uses a stable digest such as SHA-256, never hash().

RUNNING has no terminal time/errors. COMPLETED has terminal time and fingerprint,
no errors. FAILED has terminal time and nonblank sanitized error code/summary; it may
retain captured fingerprint/metrics. DB requires completed_at >= started_at, but cannot
sanitize an error summary. Never persist secret dumps/stack traces as business errors.

forecast_predictions stores one run + Product + forecast_date. Composite FKs enforce
the same Store for run/Product; unique key rejects duplicates. Finite NUMERIC quantities
obey 0 <= p25 <= p50 <= p75 in Product.selling_unit. P25/P50/P75 express forecast
uncertainty, not procurement strategies: P25/P50/P75 != LEAN/BALANCED/PROTECTED;
LEAN=P25, BALANCED=P50, PROTECTED=P75 is not an accepted mapping.

Metrics (e.g. MAE/WAPE/pinball loss) assess forecast/model quality; they are not strategy,
recommendation or business risk scores. Actual binary artifact belongs on filesystem;
DB stores only nullable logical key. No binary storage or artifact retention service.

## Historical policy / enforcement limits

ADR-011: completed runs and predictions are historical, rerun creates a new run.
S1.5 repository writers reject terminal transitions and prediction appends unless
the Store-scoped run is RUNNING. Future services enforce full immutable boundaries, horizon
membership (start <= prediction date <= end), completed-run consumption, sanitation,
authorization and input retention. No immutability triggers exist. SQL can still
alter completed content or write an out-of-horizon prediction; the test explicitly
demonstrates this limit. Input fingerprint is not retained training data or a replay
guarantee. Actual input content/artifact retention must be specified by the engine slice.
ADR-010: insufficient history cannot be filled with invented/random/default facts.
Future engine fails clearly or uses an explicitly accepted deterministic fallback;
no fallback is selected here.

## Tables / automated tests / fixtures

Writes: forecast_runs, forecast_predictions. References read: stores/products.
test_forecast_decision_persistence.py owns shelfcash_test. Commit/close/fresh-session
reload checks all statuses, UTC time, artifact key/object metrics, exact Decimal
80/100.125/130 and zero/equal quantiles. Tests reject status/window/state failures,
nonfinite/unordered quantiles, duplicate predictions, missing/cross-store references,
JSON null/scalars and parent deletion. Fresh upgrade and downgrade/re-upgrade check
exact tables and absence of business triggers. All values are persistence fixtures,
not computed production forecasts. No LLM test oracle or hosted notebook is involved.

## Manual verification / DB inspection / reset

Use [S14_VERIFICATION](../runbooks/S14_VERIFICATION.md) for executable setup/tests
and read-only SQL, including columns/constraints/indexes and:

```sql
SELECT id,store_id,status,training_start_date,training_end_date,
       forecast_start_date,forecast_end_date,model_type,model_version,
       artifact_key,metrics_json,input_fingerprint FROM forecast_runs ORDER BY id;
SELECT forecast_run_id,store_id,product_id,forecast_date,p25,p50,p75
FROM forecast_predictions ORDER BY forecast_run_id,product_id,forecast_date;
```

After guarded reset: both tables empty; head 0006_forecast_decision_persist, sixteen
business tables. Tests verify fixture values independently before isolated cleanup.
Invalid writes fail PostgreSQL; rollback before retry. Downgrade 0006->0005 drops all
three run tables/history. Seed verifies schema and writes no business rows. No Forecast
HTTP operation exists; future public payloads remain unspecified.
