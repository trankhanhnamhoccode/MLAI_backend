# Retained inspection, history and PDF — S4.10

## CURRENT FACT — implemented scope

Authority is PLAN15–16, IMP11/14.5 and the authorization contract. The accepted
conditional PLAN16 nullability decision is recorded in
[compatibility](../CONTRACT_COMPATIBILITY_CHANGELOG_VI.md).

| Surface | Behavior |
| --- | --- |
| C04 GET `/api/v1/procurement-plans/{plan_id}/ingredients` | Computed Ingredient scope, repeated `ingredient_id`, optional `option_id`, limit1–100/default50 and private snapshot cursor. Unknown filtered IDs do not add scope. |
| C05 GET same path `/{ingredient_id}` | Captured physical lots/declaration, selected candidate purchases, retained daily balances and Product/recipe provenance. Out-of-scope Ingredient is404 `INGREDIENT_NOT_IN_RUN`. |
| C08 GET `/api/v1/procurement-plans/{plan_id}/explanation` | Retained structured engine reasons, warnings, eligibility, search/proof and winner. An option filter preserves global issues. |
| N9 GET `/api/v1/stores/{store_id}/procurement-plans` | Store-wide current authorized Run summaries; status/date filters, `-accepted_at`, UUID tie-break, limit1–100/default50 and snapshot cursor. |
| H01 GET `/api/v1/stores/{store_id}/imports/calendar` | Sparse calendar grouped by first-upload `imported_at` in Store timezone, matched/unfiltered distinct batch counts. |
| H02 GET `/api/v1/stores/{store_id}/imports` | `import_date` selects Store-local first-upload day; uploaded batch metadata, `-imported_at`, pagination and unfiltered date count. |
| N10 POST `/api/v1/procurement-plans/{plan_id}/exports` | Durable PDF intent202, original queued receipt, resolved option/result digest/render version. |
| N11 GET same exports path `/{export_id}` | Private verified PDF bytes; readiness/ownership/permission/artifact integrity fail closed. |
| J01 GET `/api/v1/jobs/{job_id}` | Existing Import variants plus `planning_pdf_export`, `rendering`, export context/result discriminator. |

C03–C05/C08/N9 require current `planning.result.read`, `budget.read` and
`procurement.cost.read`. N10/J01 export/N11 also require `planning.export`.
These are Store-wide reads; the original creator is not a read restriction.
Import history requires `import.read` and the same selected-domain sensitive
rights as I04. A denied batch denies the whole requested range before any counts;
filtering cannot hide unauthorized data. No email, membership list or live names
are added to history.

## Captured facts and result availability

Views do not invoke a provider, forecast, solver or capture. Option inspection
does not persist a selection or alter winner. New captures retain optional
Ingredient name/sku companions; old records without them remain canonical and
return `LABEL_NOT_CAPTURED`, never a live fallback. Store/creator names that were
not captured remain unavailable. Physical lots include expiry/future-date
anomalies; hypothetical arrivals and daily simulation stay separate.

LOW/BASE/HIGH are demand paths. Completed simulation has three times seven rows;
exact quantity/money fractions remain authoritative. Known zero is zero;
missing simulation/purchases remain null. Ingredient shortage is not converted
to Product lost revenue without retained attribution. Global blockers retain
their scope. Failed-before-compute has no invented proof or winner explanation.

ACCEPTED DECISION: terminal Runs with a prepared computed scope but no retained
result can return C04/C05 captured facts with required `result_digest: null` in
both data and meta. Existing snapshot/input/aggregate integrity verifies those
facts. Engine-dependent fields are unavailable/null. A retained result still
requires its real valid non-null result digest; no substitute digest is emitted.

C04 private cursors bind current actor/session/Store/authorization version,
aggregate version, option, Ingredient filter and limit. N9/H02 cursors also bind
their full filters and snapshot metadata revisions. An changed history snapshot
returns409 `SNAPSHOT_NOT_AVAILABLE`; clients restart pagination. N9 counts the
whole matching set, not the page. H01/H02 exclude drafts with no upload and count
each batch once. Category and casefold filename `q` must match the same uploaded
file. Categories are only approved sales/inventory/recipes/supplier schemas;
ignored, unclassified and other schema types are not guessed. Only verified I06
completion becomes completed/completed_with_warnings; queued commit or reviewed
staging is `in_progress`, never canonical success. Retried jobs do not add batches.

## Export lifecycle and private publication

All three JSON keys are required:

```json
{"format":"pdf","option_id":null,"locale":"vi"}
```

Use a canonical UUID `Idempotency-Key`, current CSRF token and allowed Origin.
Explicit null resolves the retained winner; absence of a winner returns409
`WINNER_NOT_AVAILABLE`. An explicit actual candidate can be exported even when
ineligible, with a clear warning. Unknown option is404; Run without a completed
result is409 `RESULT_NOT_READY`. No strategy creates a new option. Request bodies
are bounded at64KiB before parsing (413 `RESOURCE_LIMIT_EXCEEDED`).

The key binds actor/Store/Run and original request. Replay returns the original
queued receipt even after completion, after rechecking current rights. A changed
payload with the same key conflicts. Replay precedes new-intent quota/renderer
admission. The minimal `planning_exports` aggregate owns one export and one job,
accepted request/session identity, revision/digest, claim and durable completion
proof. Migration0017 adds that table and queue/history indexes, with no business
backfill. Downgrade refuses any retained export intent; empty roundtrip preserves
older Run/Import data. ImportJob's mandatory import identity is unchanged.

One default-off local PDF thread claims durable work. Current accepted actor
account/credential revision, Store membership and all four grants are checked
before materialization and before publication. Logout follows S4.9 accepted-intent
semantics; credential/account/grant changes still fence work. Rendering and private
temp preparation own no SQLAlchemy Session or authorization locks. Fenced atomic
rename publishes fsynced bytes, then hash/size proof and terminal job state commit.
Lost acknowledgment is reconciled through a fresh Session and exact expected
record/artifact proof. No successful download precedes durable completion.

ALIVE/UNKNOWN process owners are never stolen. Proven process death marks the job
failed, without automatic execution. A purpose-specific internal retry can allow
one additional attempt on transient rendering/storage/process/DB failure using
the same export/job and current authority. It is bounded to two attempts; there
is no public retry route. Permanent permission failures are not retried. A failed
DB publication can leave private orphan bytes; an authorized controlled retry
must reproduce identical bytes. No TTL, purge, public share URL or retention
guarantee is introduced.

N11 uses `application/pdf`, attachment filename `shelfcash-plan-{run_id}.pdf`,
Content-Length, quoted SHA-256 ETag, `Cache-Control: private, no-store` and
`X-Content-Type-Options: nosniff`. Missing/corrupt bytes return503
`EXPORT_ARTIFACT_UNAVAILABLE`; GET does not rerender. CORS exposes download headers.
Paths derive only from verified UUIDs under private runtime storage.
Worker, J01 and N11 also verify the parent Run's Store identity independently of
export JSON/hash. A rehashed export with a foreign Store binding fails503
`RESULT_INTEGRITY_UNAVAILABLE`; this metadata check does not read live business facts.

## Renderer, resources and performance limits

ReportLab renders retained typed facts directly, not HTML/browser screenshots.
Unmodified bundled NotoSans Regular/Bold and OFL license support Vietnamese;
fonts/assets are never fetched at runtime. The report marks hypothetical purchase
proposals, selected/ineligible status, capture time, budget/cost/fulfillment,
warnings/proof limits, unknown values, physical lots and simulation. A complete
exact-value appendix retains all typed source fields. This is not an invoice,
purchase order or receipt. Deterministic rendering preserves identical historical
bytes after live business edits.

Technical admission: twenty outstanding exports per Store,3MiB typed report,
25MiB PDF,1000 pages and120s cooperative render checks. Those are not a hard process
kill or capacity SLA. Import history rejects ranges above1000 uploaded batches
with413, without truncating calendar/counts or deleting data. C04/C05 responses
are bounded at3MiB. A local cache admits at most four verified records and16MiB
canonical raw source bytes; this is not an RSS cap. Every access rechecks current
authorization and full raw aggregate hash/identity. Cold cache misses still run
all canonical/schema/digest/semantic validation. There is no UUID-only trust.

Controlled50-Product C03 measurements: initial cold11.748s; after cold13.068s,
warm1.127s. Both after reads used9 queries/118281 bytes and preserved response
parity. TECHNICAL DEBT: deep cold validation/replay remains slow, including after
restart/eviction. A single synthetic fixture does not establish production
capacity or maximum simultaneous lots/offers throughput.

Evidence: [task notes](../runbooks/FULL_TEST_FLOW.md),
[manual flow](../runbooks/FULL_TEST_FLOW.md),
[validated actual synthetic examples](examples/s410/README.md).
S4.11 FE/browser acceptance remains outside this task.
