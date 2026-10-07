# ADR-012 — Observed-sales forecast execution contract

## Status

ACCEPTED — explicitly authorized by the S2.1 task, 2026-10-07.
Classification: ACCEPTED DECISION. Related ADR-001/002/004/007/008/010/011 remain
unchanged. This accepts execution semantics, not a model or public API.

## Context

S1 lifecycle stores caller-supplied predictions, allows empty completion and does
not retain requested Product scope. That contract remains valid as low-level
persistence. Execution needs a distinct boundary with complete output and no
invented observations, without porting legacy reconstruction/filesystem pipelines.

## Decision

- Target observed daily sales by Product in its exact captured selling_unit;
  no stockout reconstruction, weather or fabricated stockout/closure facts.
- Cutoff D is a Store-local business date through the end of that day. Forecast
  exactly D+1..D+7. Do not synthesize a 23:59:59 timestamp.
- Request explicit nonempty unique Product IDs and inclusive history start <= D.
  No unrestricted horizon or silent catalog filtering.
- Prepare schema version 1 by-value Store/timezone, Product identities/units,
  inclusive history through D, canonical sales and seven forecast dates. Compute
  from those captured values; an engine does not look up mutable DB rows itself.
- Missing observations stay absent/unknown. Explicit Decimal zero remains valid.
  Reject duplicate Product/date, wrong Store/Product/unit, outside-window or
  negative/nonfinite quantities. Do not aggregate/filter malformed prepared data;
  source aggregation belongs to approved import rules.
- Engine results carry finite ordered nonnegative Decimal P25/P50/P75, actual
  model_type/model_version, optional immutable artifact identity and structured
  warnings. No rounding to integer, strategy/procurement fields, required CQR
  intervals or fabricated inference metrics. Baselines may have no artifact.
- Before future persistence, actual output keys must equal requested Products x
  all seven dates exactly. Reject empty, duplicate, missing and unexpected keys.
  Canonicalize ordering where it has no business meaning.
- Future execution must check model-specific readiness for every requested Product
  before computation; NOT_READY blocks execution rather than omitting a Product.
  Contract validity alone is not readiness; no numeric minimum history is accepted.

## Historical limits

Querying sales_date <= D bounds business dates; it cannot recover what the system
knew at D after subsequent corrections. Replay requires retained captured input.
True point-in-time backtesting needs availability/version history in a later slice.
This decision does not claim such retention/history is implemented.

## Implementation boundary / consequences

CURRENT FACT (S2.1): typed contracts and pure semantic validation only. S1 lifecycle,
Session ownership, schema, accepted ADR-010/011 and public API stay unchanged.
No engine Protocol/service/registry is introduced without concrete use.

DEFERRED: baseline/quantile algorithm and readiness policy, train/retrain/fallback,
artifact/input retention, canonical hashing, evaluation schema, actual-model metadata
publication timing relative to S1 start, failure recovery and execution orchestration.
Do not use metrics_json as generic provenance storage. Future execution must resolve
these choices explicitly before integration; no automatic next slice authorization.

## Affected areas / rollback

BE internal execution values/validation; ML/Data interface; FE/public API unchanged;
demo still has no executable forecast end-to-end. Revert only S2.1 modules/tests/docs;
no DB downgrade or change to S1 lifecycle.
