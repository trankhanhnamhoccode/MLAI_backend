# Planning setup resolver — S3.6.3

CURRENT FACT: `planning_resolution/1` resolves already-read typed configuration into
detached effective requirements/budget. No DB/config/saved storage, auth, HTTP,
durable acceptance, forecast orchestration or public readiness is implemented.
ACCEPTED DECISION: product semantics are the existing
[planning contract](../PROCUREMENT_API_CONTRACT_VI.md), not a new resolver policy.

## Boundary and actual entrypoints

- `app/application/contracts/planning_setup.py`: request, complete stored values,
  configuration bundle, typed field errors/warnings and reconciled resolution result.
- `app/application/use_cases/planning_setup.py::resolve_planning_setup`: JSON bytes/
  text, dictionary or typed request plus configuration → RESOLVED/INVALID outcome.
  Only deliberately identified rejection and boundary Pydantic errors become typed
  errors; unexpected programming exceptions propagate. No raw exception/input values
  appear in validation errors. No HTTP status mapping in this slice.
- `app/application/use_cases/planning_pipeline.py::prepare_planning_pipeline` and
  `execute_planning_pipeline`: resolution plus explicit internal execution declarations
  → operational_decision/2 → existing capture/pipeline /2. No reread of defaults,
  saved or ceiling; original requirements reach capture/exclusion audit.

Request permits only mode, forecast_start_date, default_requirements_version,
custom requirements and saved_requirement_id. Unknown fields reject, including
customer-supplied strategy/model/forecast ID/scope/horizon/currency. Default forbids
requirements/saved ID; custom requires requirements; saved requires saved ID and
forbids requirements. Null optional version/requirements/saved ID is invalid.
Default version is checked semantically during resolution whenever values inherit.

Wire percent/money are unsigned plain decimal strings (no exponent/leading zeros/
JSON number/float/bool/nonfinite). Percent ≤100, at most 3 integer/32 fractional
digits; money at most 18/18. UUID text canonical lower-case; date strictly YYYY-MM-DD.
Validate start−1 and start+6 without overflow. Requests ≤64KiB; duplicate JSON keys
reject. Paths 1..3 unique, overrides ≤50 unique per path, active Product scope ≤50.
The bridge caps known offers at 100. Ingredient/lot admission and loader bounds remain responsibilities of future
public operational admission; this resolver does not inspect operational rows to
claim those bounds or readiness. Native/exact numeric support remains separate.

## Config source and modes

`PlanningConfiguration` captures Store/currency/timezone, read_at, configuration
version/provenance, declared consistency, optional defaults/ceiling/selected saved,
Product catalog references and the actual ProcurementPolicyV2. Nullable records
represent absence; malformed records reject, never fabricated defaults/zero/unlimited.
The bundle is by value. `SINGLE_SNAPSHOT_DECLARED` is a source assertion;
`UNSPECIFIED` does not become a database-snapshot guarantee. Fake source proves
resolver logic only. No real configuration reader exists.

Default source explicitly declares BASE95%, overrides=[], budget=null plus version;
the resolver checks approved content whenever used. It never constructs fallback
BASE95 when absent, or derives default from construction100%. Unknown update time
stays null. Request version mismatch gives DEFAULT_REQUIREMENTS_CHANGED.

Custom uses same-path default only for omitted threshold/overrides. Omitted and
explicit null differ: threshold/overrides null reject; [] is explicit empty list.
Explicit overrides replace the whole list. LOW/HIGH lack current same-path defaults,
so those values must be explicit. Default version required only when inheriting;
full custom ignores unused stale default version and may resolve without stored
default. Approved current default corruption cannot be inherited as custom policy.

Saved uses complete resolved thresholds/overrides from the selected same-Store ID,
with revision/updated_at retained; no new threshold inheritance, mutation or implicit
Save. Default source/version is not required for saved computation. If both known
timestamps satisfy saved.updated_at < default.updated_at, warn
DEFAULT_CHANGED_SINCE_SAVED_UPDATE; missing history → DEFAULT_CHANGE_HISTORY_UNKNOWN,
without invented timestamps. Equal/later timestamp gives no change warning.
Warnings never replace required validation or silently rewrite saved values.

All modes need current known Store budget ceiling and explicit policy/config. Omitted/
null custom or null saved budget uses the supplied current ceiling; default always
uses it. Explicit zero remains zero; private > ceiling rejects, no clamp. Preserve
effective amount, currency, physical ceiling/provenance and ceiling version. Source
read time/resolution is not durable acceptance or proof values remain current later.

Overrides refer to existing active Store Products; IDs unique per path. Override
can be lower/equal/higher than common floor and replaces it for that Product/path.
No serving priority changes. Resolver never excludes active Products for missing
recipe/history: /2 captures actual operational facts, determines computed scope,
and retains excluded overrides as NOT_EVALUATED.

## Exactness, detachment and revalidation

Percentage → ratio by Decimal tuple exponent minus two, not division/scaleb under
ambient context. Example `95` → `.95`; `0.00000000000000000000000000000001`
→ `1E-34`. No rounding, epsilon or fabricated zero. Money constructs Decimal exactly.
Native solver may later report NUMERIC_UNSUPPORTED; syntactic validity is not proof
of native support or feasibility.

Nested collections are tuples of frozen typed values. Instance revalidation rebuilds
request values while preserving omitted fields through a narrowly scoped request
serializer/wrap validator. Retained JSON round-trip preserves omitted vs explicit
null budget. No caller list/dict references survive capture. The resolution retains
original request/config and rederives requirements, budget, references, warnings and
dates on output validation; forged copied output does not bypass the public bridge.

`default_reference` means threshold/override inheritance actually used; saved has
its own reference. Configuration may also retain observed default metadata used
only for revision warning, without claiming saved inherited those thresholds.
Policy and all observed configuration provenance remain in the retained bundle.

The bridge requires forecast reference, inventory/inbound attestations, snapshot
policy, offers/bounds, fee coverage/fees, capacity/supplier-limit declarations and
provenance explicitly. Missing declarations reject; UNKNOWN remains blocked by /2.
No default fees/bounds/capacity invented. Source budget conflicts continue to use
existing /2 guards. /1 and S1/S2 code/callers/lifecycle are untouched.

## Verification and benchmark (2026-10-09)

Exact commands/fail-fix history: [task notes](../runbooks/FULL_TEST_FLOW.md).
Wide targeted gate: 212 passed (84 resolver tests + 128 existing affected tests).
After final resolver-only guards/two tests, reran affected group: 86 passed.
Final known-offer bridge guard rerun: 5 passed, 82 deselected. Do not describe this
as a final 214/215-pass gate or full regression; no full suite/DB
tests were run for this no-DB slice. Existing S362 PG PASS is historical this turn.

`scripts/benchmark_planning_setup.py` declares source default BASE95 per Product,
no overrides and ceiling14 VND synthetic. Same S362 representative 5/10 Product
topology, finite domain65536, fake operational source, native solver budget10s.
No thresholds reduced to make benchmark pass. Existing raw evidence is not overwritten.

| Measurement | 5 Products | 10 Products |
| --- | ---: | ---: |
| Resolver | 0.000958s | 0.000771s |
| Bridge | 0.000417s | 0.000563s |
| Capture/preparation | 0.012213s | 0.028755s |
| BOM | 0.016266s | 0.035922s |
| Engine wall | 3.805755s | 9.692435s |
| Comparison | 2.407101s | 3.450935s |
| Selector | 2.643373s | 4.056086s |
| Final output validation | 3.530975s | 4.967127s |
| Pipeline total | 12.415770s | 22.231370s |
| External total incl. resolver/bridge | 12.420057s | 22.239769s |
| Engine reported / overrun | 3.800568s / 0 | 9.678735s / 0 |

Both: NO_ELIGIBLE_CANDIDATE, winner null, no eligible tokens; all three strategies
customer_pass=false, construction_pass=false, candidate references present,
INCOMPLETE/UNPROVEN, customer/construction feasibility UNKNOWN, no exact enumeration.
5P all terminate ENCODED_NO_CUSTOMER_INCUMBENT_NOT_PROOF. 10P LEAN terminates
SEARCH_LIMIT_NO_INCUMBENT; other two have encoded-no-customer termination.
No proof of infeasibility, global optimum, accuracy, real savings or SLA.
Full phases extend beyond engine budget; cooperative overrun can occur in other runs.
Raw resolution/pipeline and summary: `runtime/verification/planning_setup/`.
Timing was measured before the final bridge offer-count guard; both cases use eight
offers and final bridge request values match retained inputs. No numerical changes
or benchmark rerun; no claim these are newly measured final-source timings.

## Backlog

No resolver implementation blocker remains in tested internal scope. Public C01/C02/
C03, auth, consistent DB/config/saved reader/writer, migrations, durable Run/worker/
idempotency/storage/replay, forecast auto-generation/reuse and public resource admission
remain backlog. No ZIP created, commit/push or next slice started. These future tasks
require their own authorized slices; resolver success does not make capabilities true.


## Additional small-domain verification - CURRENT FACT

[Small-domain review](PROCUREMENT_V2.md): verified zero
stock-cost winner, native purchase basket(2,2) exact outlay10 against independent
9-vector oracle, and certified no-pass at budget9.90 new+resolver tests passed;
final selected-outlay assertions reran2 affected tests. No runtime correctness fix.
Historical5/10P engine UNKNOWN/UNPROVEN is preserved. Separate conservative expiry
bound on the actual captured fixtures proves P0<=60% BASE fulfillment; this new
review evidence is distinct from the old engine proof. No large domain enumeration,
requirements/budget adjustment or benchmark artifact change. No next slice.
