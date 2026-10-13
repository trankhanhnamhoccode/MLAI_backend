# ADR-020 — Product requirements and internal procurement selector

Status: ACCEPTED by the explicit S3.6.1 implementation task, 2026-10-09.
Authority: user task and the accepted policy v1 in PROCUREMENT_API_CONTRACT_VI.md.
This is limited supersession, not acceptance of new HTTP/persistence/default policies.

## ACCEPTED DECISION

For new procurement/2 only, supersede ADR-019's common-unit aggregate construction
and max-total-service fallback/no-selector scope, and ADR-017's fixed BASE-pass
recommendation gate. Preserve the historical procurement/1 and DecisionPolicy v1
contracts/evidence, serving allocation, FEFO and S1 DecisionRun lifecycle. Do not
reinterpret old runs or change their completed/recommended-strategy constraint.

Construction is LOW/BASE/HIGH 100% EACH Product for LEAN/BALANCED/PROTECTED.
Customer effective requirements are supplied explicitly: selected paths, common
minimum per Product, Product/path replacement overrides and provenance. No implicit
BASE95 default in computation. Service is exact fulfilled/requested over the seven
days for each Product/path. Zero requested is nonbinding and has undefined ratio;
different selling units are never summed to form service objectives.

Generation and exact validation both enforce customer requirements. Within that
domain, construction-pass minimizes purchase plus declared payable fees. Otherwise
rank construction-path minimum Product fulfillment, equal-weight mean fulfillment,
outlay, canonical basket, lexicographically. Omit zero-request Products from min/mean;
with none, omit service objectives. Customer-fail is reference only, not best_available.

Winner among evaluated strategy candidates requires exact hard validity, no related
blocker and customer pass. Rank outlay, minimum Product HIGH/BASE/LOW fulfillment,
canonical basket. Zero-demand path is neutral. No eligible candidate gives null.
Incomplete/unproven incumbents can be recommended; technical failure stays ERROR.
Search timeout is not automatically execution failure or proof of infeasibility.
Grouping retains context/arrivals/fees/provenance and separate source-strategy evidence.

Float MILP is a candidate generator. Exact rational serving and validation remain
authority. Exclude only rejected integer vectors; bounded re-search and shared
cooperative deadline/cache remain. Only complete optional enumeration certifies the
captured finite technical domain; native OPTIMAL/infeasible does not. No extrapolation
outside bounds, forecast accuracy or calibrated probabilistic claim.

## CURRENT FACT / routine implementation choices

Separate procurement/2, procurement_comparison/2 and procurement_selector/1 entrypoints.
PreparedDecisionInput.capture_version defaults to historical 1; explicit 2 admits
per-Product mixed selling units. snapshot_schema_version remains 1 (unchanged snapshot
fields apart from the admission marker). Old DecisionPackageV1 refuses capture 2;
operational capture/pipeline still produces/uses version 1. There is no persisted
Decision snapshot format upgrade here. Old comparison/1 identity serialization elides
the new implicit capture_version=1 to preserve historical tokens; explicit 2 is covered.

Fallback's three native stages freeze EXACT incumbent min/mean lower bounds. Float
projection can miss candidates; finite exact enumeration rescues small domains.
Large-domain ranking remains UNPROVEN. A candidate is best among exact evaluated
facts, even when native search stops without proof. Customer-fail references are
first observed, expressly NOT ranked. Stable ordering uses sorted term UUID/packs
and captured arrival identity; this resolves technical ties, not business priority.

construction_feasibility describes the JOINT customer + construction domain;
customer_feasibility describes customer requirements alone. These are separate from
execution, candidate validity, construction attainment and proof scope. FINISHED
means a search procedure finished, not a global exact certificate.

Deadline includes engine admission/build/search/exact checks/result validation;
cooperative Python/native boundaries may overrun, recorded explicitly. Subsequent
comparison/selector revalidation is outside that invocation deadline and separately
timed in the benchmark. No hard cancellation or universal latency guarantee.

## OPEN / not implemented

HTTP C01/C02, default/custom/saved resolution and revision warning, auth, mixed-unit
operational capture configuration, retention/replay/DecisionRun persistence, customer
confirmation/ordering, fee taxonomy/loaders, real-data evaluation and Optuna.
Unknown payable fees/budget remain blocking; configured unsupported safety remains
blocking. Generic payable fees are not relabelled delivery. API budget null inheritance
must be resolved BEFORE this internal input; explicit unconstrained is a separate
internal declaration and does not authorize unknown API cap as unlimited.

References: [policy](../PROCUREMENT_API_CONTRACT_VI.md),
[feature](../features/PROCUREMENT_V2.md), [task notes](../runbooks/FULL_TEST_FLOW.md),
[ADR-019](ADR-019-internal-procurement-engine.md),
[ADR-017](ADR-017-serving-fefo-provisional-direction.md).
