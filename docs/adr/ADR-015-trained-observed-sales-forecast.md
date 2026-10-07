# ADR-015 — Trained observed-sales forecast, evaluation and artifacts

Status: ACCEPTED — remaining S2 implementation explicitly delegated by user,
2026-10-07. Routine choices below are implementation decisions under that authorization,
not separately user-selected thresholds. Extends ADR-012/014 for the new trained path;
the S2.3 fixed-baseline path and S1 supplied-prediction lifecycle remain unchanged.

## Policies frozen before implementation

- One pooled model family per exact Store/Product scope; three CPU LightGBM 4.6.0
  quantile boosters, alpha .25/.50/.75, direct horizon feature 1..7. Product categorical
  codes follow captured sorted UUIDs, never current catalog. Fixed small configuration,
  seed 1729, one thread, deterministic/force_col_wise, 40 rounds, 7 leaves, learning
  rate .05, min_data_in_leaf 5. No tuning/search or additional model family.
- Features version 1: Product code, horizon, origin/target weekday, target month,
  exact-date lag 0/1/7, observed-only rolling 7/28 mean and count. Missing lag/mean
  stays missing (NaN at model boundary), zero is retained. Features use dates <= origin;
  supervised target must exist at origin+h and be <= training cutoff. No fabricated
  historical unit/catalog facts. All captured history is eligible; rolling features
  use their explicit windows. Retraining at each evaluated origin uses the same rules.
- Provisional mechanics readiness: >=28 observations per Product for training/inference,
  plus >=14 supervised training rows per Product. Baseline remains >=1. These are
  conservative operational minima, NOT empirically justified accuracy thresholds.
  Exact training scope/units/timezone, feature/policy/dependency versions must match.
  Artifact training cutoff must not exceed inference origin.
- Model float boundary rejects nonfinite/overflow values; outputs become
  Decimal(str(float)), without integer/currency rounding. Clamp negative values to 0,
  sort the three values at each key (rearrangement); record raw crossings and negative
  value counts and structured warnings. Postprocessing version 1 is identity-bearing.
- Chronological expanding-window rolling origins, seven days apart, with complete
  seven-day actual availability window inside capture. First chronological half is
  validation (minimum two origins), later half untouched holdout (minimum two).
  Selection uses equal-target aggregate mean pinball on paired observed targets in
  validation only; strict improvement selects LightGBM, ties select baseline.
  Insufficient evaluated origins/paired samples selects baseline, never superiority.
  Holdout metrics do not tune config/selection. Report missing targets, excluded
  origin/Product reason/count, horizon/Product breakdown, MAE, WAPE (null when actual
  sum zero), individual/mean pinball, interval width/coverage and crossing counts.
  No real data available: quality NOT EVALUATED; synthetic selection proves mechanics.
- Recognized absent artifact, model readiness or baseline selection may fallback for
  the whole requested scope; baseline must be ready. Persist actual model identity,
  candidate identity/reason/warnings separately from metrics_json. Corrupt/incompatible
  artifacts, inference/programming/DB errors are errors, never success via fallback.
- Immutable trusted-generated LightGBM text + strict JSON manifest, content-addressed
  SHA-256 directory identity. Includes exact prepared training snapshot/hash, features,
  configuration/seed/dependency versions, units/timezone/scope/window and evaluation.
  Atomic same-volume directory publication; no overwrite, pickle/upload loader/latest.
  Verify all bytes/manifest/compatibility before loading. Replays use exact original
  artifact plus retained input; missing artifact errors rather than fallback/retrain.
- Local FS and DB are not one atomic transaction. Publish artifact before DB start;
  failed publication creates no run. DB failure may leave an unreferenced valid artifact;
  keep artifacts, inputs and metadata for all statuses, no TTL/automatic orphan cleanup.
  Manual inspection/backup is required before removal. No transaction during model/FS
  work. New metadata table starts atomically with run+input, completion updates metadata
  atomically with predictions/status. Scoped guards prevent terminal metadata updates.
- Retained snapshot permits replay of captured corrections; chronological filtering
  is not historical point-in-time availability. No calibration/quality guarantees,
  stockout reconstruction, business API or S3 are accepted here.

References: [LightGBM 4.6 parameters](https://lightgbm.readthedocs.io/en/v4.6.0/Parameters.html),
[Booster text serialization](https://lightgbm.readthedocs.io/en/v4.6.0/pythonapi/lightgbm.Booster.html).
Exact runtime compatibility is conservative; upgrading requires producing/evaluating
a new artifact/policy version. Inference replay is distinct from bitwise cross-platform
retraining reproducibility, which is not promised.
