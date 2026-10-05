# ADR-011 — Historical Run Immutability and Snapshot Policy

## Status

ACCEPTED — authorized S1.4, 2026-10-05.

## Context

ADR-001/004 reserve business truth for the deterministic backend. ADR-005 requires
versioned, self-contained decisions; ADR-006 keeps what-if hypothetical. ADR-008/009
govern corrections/current inventory; ADR-010 forbids invented input facts. Mutable
operational rows cannot redefine the meaning of a completed historical run.

## Decision

- COMPLETED ForecastRun and its predictions, and COMPLETED DecisionRun, are historical
  records. Future writers prohibit silent modification/deletion of completed content.
  Reruns create new UUID runs, including when canonical input fingerprints match.
- Historical decisions are interpreted using their stored snapshot/package, never
  current inventory, supplier terms, recipes or constraints. Preserve identities,
  versions and the actual used values, not only references to mutable rows.
- Future flow: load authorized business inputs -> build canonical input snapshot ->
  compute FROM THAT SNAPSHOT -> persist result package. Do not compute from DB then
  re-query potentially changed rows to manufacture an input snapshot afterward.
- Decision packages have positive integer package_schema_version, starting at 1.
  Snapshot/package contents retain enough model/business algorithm version metadata
  to explain historical output. Full JSON schemas and algorithm identifier semantics
  will be frozen by engine slices; no speculative engine_version column is added now.
- Fingerprints are nonunique audit/debug identifiers of canonical input, not security
  or deduplication guarantees. Future hashing uses deterministic canonical serialization
  and a stable digest such as SHA-256, never Python hash(). No hasher is implemented now.
- P25/P50/P75 are demand quantiles in Product.selling_unit, not strategies. Never map
  them to LEAN/BALANCED/PROTECTED. Quantiles are finite, ordered and nonnegative.
  Model metadata records the model actually used, including any future accepted fallback.
  Model metrics evaluate forecasts, not procurement/recommendation/business risk scores.
- Model binaries belong on local filesystem; PostgreSQL stores artifact_key metadata
  only. Baselines may have no artifact. A fingerprint alone is not retained forecast
  training content; input content/artifact retention must be resolved in the Forecast
  Engine slice, not claimed by this schema.
- A completed Decision package must retain evaluations of all actually considered
  Competition candidates LEAN/BALANCED/PROTECTED, with simulator evaluation before
  deterministic comparison selects recommendation. LLM cannot choose recommendation,
  alter predictions, quantities, risk calculations, evaluations or snapshot facts.
- What-if remains non-persistent by default under ADR-006; no what-if tables are added.

## S1.4 storage contract and enforcement

Only forecast_runs, forecast_predictions and decision_runs are added. UUIDs,
TIMESTAMPTZ, DATE, NUMERIC and object JSONB follow existing PostgreSQL conventions.
Statuses are RUNNING/COMPLETED/FAILED. Windows are required/ordered for every run;
no rule requires forecast immediately after training. started_at is explicit, terminal
completed_at >= started_at records completion/failure time. RUNNING has no terminal
time/errors; COMPLETED has no errors; FAILED requires sanitized error_code/summary.
DB checks presence/shape, not sanitization. Actual-model metadata is required for
ForecastRun; no engine/fallback algorithm is selected by this ADR.

Completed ForecastRun requires input_fingerprint and terminal time. Completed
DecisionRun requires forecast reference, planning window, positive package version,
nonblank fingerprint, object input snapshot/package, constrained recommendation and
terminal time. RUNNING/FAILED decisions have no output package/recommendation;
captured inputs/version may remain. A package requires its positive version.
JSON SQL NULL denotes absent values; JSON null/array/scalar is not an object package.

DB enforces run statuses, local date/time ordering, quantile integrity, prediction
business key and same-store FKs. FK deletion is RESTRICT. There are no immutability
triggers, generic immutable-record framework, snapshot builder or repositories.
Privileged SQL can still edit completed rows. Future services must enforce immutability,
legal transitions, completed forecast consumption, horizon membership, package version/
shape/evaluation consistency, exact input capture, sanitization and authorization.
Do not claim these application invariants as implemented by S1.4.

## Consequences / deferred choices

Schema-only fixtures demonstrate durable storage and independent snapshot values,
not working Forecast/Decision Engines. Migration downgrade drops only these three
tables/history; guarded development reset remains permitted. No dependency, business
API, queue, artifact service, repository, algorithm or S2 implementation is introduced.
Full run lifecycle/retention, canonical hashing/input retention, model/engine versions
and versioned package validation remain explicit future slice requirements.
