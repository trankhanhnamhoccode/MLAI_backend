# ADR-A1 — Observed stockout and versioned demand inputs

Status: ACCEPTED under the user's explicit A1 implementation request, 2026-10-13.
Algorithm thresholds are delegated implementation choices, not accuracy claims.
Extends ADR-008/010/011; supersedes only the no-reconstruction restriction of
ADR-012/015 for new schema-2 captures. Historical schema-1 execution stays unchanged.

## Decision

Canonical sales remain observed Store/Product/local-day quantity in selling units.
Stockout is true (positive evidence), false (known uncensored), or null (unknown).
Zero sales never establishes stockout. Exact reviewed value aliases belong to
reusable interpretation; quantities, dates, report keys and missing-stockout update
declarations belong to the batch. Reimport without observation requires explicit
quantity_only (preserve that contribution's observation) or not_provided (unknown).
A mapped blank is unknown unless quantity_only is explicit. Unknown + false stays
unknown; any true wins. No duration, lost demand or projected event is inferred.

Contribution identity includes Store, source_system_key, report_type, stable
business_report_key, Product and day. Different sources do not prove independence.
Aggregate independent contributions only with disjoint confirmation covering the
complete frozen list. A revision replaces its previous contribution. Exact same-key
duplicates collapse with all locations retained; conflicting same-key values and
mixed full/partial reports block the atomic batch. Absent records stay retained.
Recover historical report_type only from immutable same-Store pinned mapping proof.

New captures use schema 2 / causal_stockout_v1. Derived records retain observed
quantity, stockout, estimated demand or null, method/version and supporting dates.
Use only strictly earlier known-false days in the preceding 42 days. Prefer same
weekday if >=3 samples exist; otherwise require >=3 uncensored days overall.
Use lower median bounded below by observed quantity. This provisional estimator
does not account for promotions/closures/calendar effects or certify true demand.
Unsupported censored days are excluded from baseline samples, trained labels and
lag/rolling state. Unknown retains observed values with a compatibility warning.

Both consumers share this projection; feature layout and quantile algorithms stay
unchanged. Censored targets are excluded from observed backtest metrics. Each
rolling-origin capture reconstructs its own prefix. Business-date filtering is not
point-in-time recovery after later corrections. Replay uses original captured
facts, policy and immutable artifact, with no current-fact lookup.

Schema-1 JSON/digests/replay remain exact. Schema-2 digests include stockout, policy
and derived evidence. Artifact demand policy must match inference; an old observed
artifact is incompatible, not a silent fallback. P25/P50/P75 are demand quantiles;
LOW/BASE/HIGH remain design paths.

## Implementation and rollback

CURRENT FACT: source/unit implementation and additive nullable Boolean migration
`0019_sales_stockout` exist, parent `0017_planning_exports`, without Auth dependency.
Migration/persistence and targeted acceptance are verified on owned
`shelfcash_import_test`, role `shelfcash_import_tester`; tests/reset are sequential
within that DB. No development/Auth/shared-test DB changes or head merge here.
Do not start on the old schema. No activation, Run rewrite or legacy backfill.
Rollback A1 source only; preserve audit,
captures and artifacts. Column downgrade refuses non-null stockout observations;
preserve/export them before an explicitly authorized destructive rollback.
No A2, Auth, notification or queue scope is opened.
