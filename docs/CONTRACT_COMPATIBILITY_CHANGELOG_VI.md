# Compatibility API — các thay đổi sau baseline10/10

## CURRENT FACT — D4 contextual readiness extension

D1–D5 đã tích hợp main local, source73 operations/66 paths/head0027.
[Handoff OpenAPI](handoff/openapi.json) và [diff FE54](handoff/openapi_diff_fe54.json)
đã đồng bộ; original baselines/hashes giữ nguyên. So clean main052cddee trước
merge: không endpoint mới/xóa; chỉ R01/C01 query và additive D4 fields dưới đây.
Runtime8103 chưa nâng cấp; không coi source artifact là live deployment.

R01/C01 thêm optional planning_request query (URL-encoded strict C02 request JSON).
Absent query giữ default-only scope; supplied request chọn context explicit.
Known missing default chuyển unknown→blocked cho đúng default flow; boolean vẫn
false. Full custom/saved không còn bị unused default chặn khi đánh giá chính request.
R01 thêm planning_assessment/forecast_assessment; C01 readiness thêm assessment/
forecast; typed ReadinessIssueDetails giữ source field/impact/offer reference/version.
C03/C08 PlanningNotificationDetails thêm optional source_reference/source_version
từ retained evidence, absent elide. Không endpoint, migration hoặc historical rewrite.
Retained Import CompletionReadinessIssue/details OpenAPI giữ nguyên. Current DTOs
và [canonical R01](IMPORT_MAPPING_API_CONTRACT_VI.md#readiness-v1)/
[C01](PROCUREMENT_API_CONTRACT_VI.md#planning-context) sở hữu semantics; FE cần dùng
assessment.input_scope và render warnings, không hiểu can_generate là winner promise.
GET không infer/solve/train hoặc pin cho Run; C02/execution vẫn revalidate.

## Original baseline provenance — immutable test input

- Fixture: [openapi_20261010.json](../tests/fixtures/openapi_20261010.json).
- Original archive: shelfcash_backend_context_handoff.zip, SHA-256
  `238959dd16307ebd691834d2a679f7f80134495bbe99c56f29f7835f39bab6fd`.
- Original entry: `shelfcash-backend-context/generated/openapi.json`.
- Exact extracted bytes: 406572; SHA-256
  `04ee429440efa23a5c74035d01c8c1f63df7d231cee54705d848856592879d63`.
- Baseline: 32 operations; current: 54; 22 additions, no removals,
  six changed existing operations I01/I02/I03/I04/I05/M04.
  Component/ref changes remain compatibility information, not an automatic pass.
- Snapshot tool refuses baseline checksum drift. Source DTOs/current OpenAPI
  describe current structure; they never overwrite this original fixture.

## Development provenance — condensed historical information

Git-backed milestones: scaffold `0e408a3`; PostgreSQL `4303f71`;
identity/catalog/operational schema `6c69010`/`afa5295`/`ea166be`;
repositories/application foundation `26d4aac`/`1019789`; S2 retained forecast
`b5ebb3b`, merged at `a4b6837`. S3 and S4 implementation present in this
worktree was not committed at cleanup start. Its milestone assignments rely on
original scope notes, feature contracts, ADRs and implementation; S4.11 is a
work milestone, not a Git commit. S3 adds pure deterministic decisions,
FEFO, procurement, temporal capture and durable planning. S4 adds Store auth,
import/mapping/atomic commit, menu/inventory, configuration/readiness,
public planning and retained history/PDF. S4.11 adds isolated local integration
tools and partial FE integration; full UI flow remains unverified.
Cleanup preserves product implementation and accepted ADR intent, consolidates
operational documentation and retires task reports/ZIP packaging.

## 11/10/2026 / S4.11 integration versus exact ZIP10/10

Baseline SHA256238959dd16307ebd691834d2a679f7f80134495bbe99c56f29f7835f39bab6fd.
Baseline OpenAPI32 operations (31 core+health) ->54 (53 core+health);22 added,
0 removed,6 existing operation definitions changed: I01/I02/I03/I04/I05/M04.
Regenerated runtime/verification/openapi/openapi_diff.json includes component/ref/name changes;
regenerate consumers against current input/output schemas, not only route counts.

| Dimension | Current accepted difference / compatibility action |
| --- | --- |
| Route/method additions | C01/C02/C03/C04/C05/C08/H01/H02/I06/N1/N2/N3/N4/N6/N8/N9/N10/N11/N20/N21/N22/R01. Design-approved routes now HTTP; not new product permission. |
| Existing transport/workflow | I01/I02/I03/I04 cumulative receipts/quota/seal/ACK/CAS; I05 preview/confirmation/atomic commit; M04 sheet selection/IGNORE/shared values. Re-read I04 rather than assuming quota from I02. |
| Request validation | CA-002 conditional commit reason; CA-016 monetary input18/18, independent Quantity and source keys1..1000 vs namespace128; finite/length/admission guards are compatibility-affecting, not route additions. |
| Retained response typing | Read-only historic Money exception; no rewrite/rounding. Current P01/P02 limits unchanged. PLAN16 C04/C05 required result_digest:string|null condition and unavailable engine fields affect generated types. |
| Authorization | CA-020 Staff own-sheet IGNORE without separate Owner approval, but no approved profile edit; retained/PDF sensitive reads check current cost/budget/planning/export rights including replay/worker. No staging reset permission. |
| Temporal meaning | N6 OPENING_STOCK observation freshness vs late ACTUAL_RECEIPT warning; N20-N22 next Store day, inclusive dates, pinned preview/read-set and atomic publication. No hidden historical correction. |
| Job/result/header unions | J01 planning_pdf_export/rendering with typed context/result; N10 explicit option_id:null; N11 authenticated PDF binary/quoted SHA ETag/bytes/private cache headers and CORS expose. |
| H01/H02 browser integration fix | HistoryMeta/ImportHistoryMeta now include warnings:Notice[] per existing common Import success contract (section9). S4.10 omission was observed drift, not approved contract change. FE accepts normalized in_progress and Notice without invented details. Empty warnings is explicit. |
| Operational addition | Isolated integration DB/CLI/runtime/sample, normal Holder/Owner/Staff provisioning and explicit BASELINE. No new public route/config engine, no production auth relaxation. |

CURRENT FACT: historical ZIP handoffs are retired. Regenerate snapshots with
`python -m scripts.integration_contract_snapshot`; full UI acceptance remains
unverified. Historical slice checkpoints below are compatibility provenance,
not current feature-status declarations.

## CURRENT FACT / ACCEPTED DECISION — 11/10/2026 S4.10 wire synchronization

| Surface | Current wire/validation | FE action for final handoff |
| --- | --- | --- |
| C04/C05 | Required result_digest in data/meta permits null only for terminal captured computed scope without retained result; snapshot integrity remains required. Result-backed reads keep valid non-null digest | Handle captured-only views and null engine-dependent values. Never display unavailable as0 or substitute snapshot digest. This is the accepted conditional PLAN16 nullability adjustment. |
| C04/C05 options/scope | Retained winner/explicit/not_selected; captured names may be missing on old Runs; exact quantities and3×7 rows only with complete simulation | Keep physical stock separate from hypothetical balances/arrivals, demand paths separate from confidence intervals; no live label fallback. Unknown scope/option and not-ready errors are explicit. |
| C08 | Structured retained warnings/blockers/exclusions/proof and option evidence; global issues survive option filtering; unavailable/NOT_EVALUATED is explicit | Render retained codes and scope. No-winner/incomplete search is not an infeasibility certificate; no AI-generated explanation. |
| N9 | Current Store-wide summaries, nullable result fields, creator user_id/display_name:null, exact counts, -accepted_at/UUID, actor/Store/auth/filter/revision-bound cursor | Reopen same Run UUID through C03; restart stale snapshot pagination. No email/creator-only restriction. |
| H01/H02 | First-upload Store-local date, sparse calendar/matched+unfiltered distinct batch counts; same-file category+filename q; statuses in_progress/completed/completed_with_warnings/failed | Preserve imported_at vs data_date/completion distinction. Only verified retained I06 means canonical success; retries/files do not add batch counts. Sensitive authority is whole-response deny. |
| N10 | Three required keys format=pdf, option_id explicit-null or real candidate, locale=vi; UUID key/CSRF/Origin;202 original queued receipt including resolved option,result_digest,render_version=planning-pdf/1 | Explicit null selects retained winner; no-winner/unknown/not-exportable/not-ready are separate errors. Replay retains original receipt, conflicting payload409. 64KiB pre-parse bound413. |
| J01 | operation planning_pdf_export, stage rendering, ExportJobContext {store_id,run_id,export_id}, ExportJobResult discriminator planning_pdf_export | Update operation/stage/context/result unions. Completed result includes resource_id/run_id/option_id/private relative download_url/SHA/byte_count/media_type. Existing Import variants remain unchanged. |
| N11 | application/pdf binary, attachment filename, Content-Length/quoted SHA ETag/private no-store/nosniff, headers exposed through CORS | Download verified bytes using current cookie and rights; no JSON success envelope or publicshare. Not-ready409 and missing/corrupt artifact503 do not trigger GET rerender. |
| OpenAPI/performance | Eight additive operations/six paths; old operations unchanged, only shared JobView expands.53core+health. C03 cold13.068s/warm1.127s in controlled50-Product fixture | Regenerate types with nullable C04/C05 digest and expanded JobView. Account for cold restart/eviction cost; no SLA/capacity claim. |

Examples: [actual validated JSON](features/examples/s410/README.md).
Evidence/limits: [current verification runbook](runbooks/FULL_TEST_FLOW.md). FE/browser synchronization
and S4.11 remain future work; no new handoff/ZIP is created in this task.

Authority: quyết định người dùng và contract cụm hiện hành. Baseline đúng:
`shelfcash_backend_context_handoff.zip`, SHA-256
238959dd16307ebd691834d2a679f7f80134495bbe99c56f29f7835f39bab6fd.
Không dùng ZIP09/10; chưa tạo handoff thay thế.

## HISTORICAL INFORMATION — 11/10/2026 S4.9 accepted wire implementation

| Surface | Current wire/validation | FE action for final handoff |
| --- | --- | --- |
| C02 | POST /stores/{store_id}/procurement-plans; canonical UUID Idempotency-Key, Origin/CSRF; default/custom/saved;202 accepted, terminal replay200; Location/Retry-After; one Run identity | Preserve original field presence and array order for same-key replay. Receipt is intent, not forecast/winner. No strategy/model/job selector. Budget is a ceiling. |
| C03 | GET /procurement-plans/{plan_id};200 queued/running/failed/completed; opaque ETag,response_version; no-store/full200 even If-None-Match; current owning-Store planning.result.read,budget.read,procurement.cost.read | Poll2000ms nonterminal/0 terminal. Separate status,outcome,search,proof,winner and completeness. Failed may retain independently verified partial recommendation. No creator-only restriction. |
| Result | Exact fraction strings and Decimal50 views; domain_size string; excluded overrides NOT_EVALUATED; supplier-order fees once in aggregate; generic delivery_fees=null with warning | Regenerate typed clients; do not coerce fractions/count strings or call unknown fees zero. Training dates are actual provenance, not accuracy proof. |
| Bounds/errors | 50 active Products/100 required Ingredients/100 offers/1000 relevant lots; C02 body64KiB;422 RESOURCE_LIMIT_EXCEEDED; no truncation | The50 limit concerns active menu, correcting earlier computed-count readiness drift. N1–N4 oversized body stays413. Late scope expansion is a whole-Run computation blocker. |
| C01/R01 | planning availability follows actual registered live worker; data valid can coexist with execution unavailable | Worker opt-in is operator/local runtime setup, not a GET action or browser model selection. Import worker flag is independent. |
| Fee readiness/capture | Shared canonical source bindings include namespace/currency. Several aliases may identify one Supplier/order; unknown component binding blocks rather than omitting charge | Readiness can now report unknown for foreign namespace or unresolved fee components previously missed. Alias count is not supplier/order count. JSON shape unchanged. |
| OpenAPI | Exactly2 added operations; old operation definitions unchanged. CustomPath/CustomRequirements split into -Input/-Output; SaveRequest/ReplaceRequest refs follow -Input. Existing readiness Exclusion becomes module-qualified due to public Exclusion name collision; ScopeEstimate ref follows it | Sync generated component names; old request/response JSON shapes remain unchanged. This component diff is explicit compatibility information, not a new product contract. |
| Retained performance |50-active-Product actual test:9 queries,118281 bytes,cold12.73s; full deep validation, no live facts | Account for cold read cost. Measurement is not an SLA or maximum lots/offers load certification. |

45 core operations + health. Validated synthetic JSON examples and exact evidence
are linked from [PUBLIC_PLANNING](features/PUBLIC_PLANNING.md) and
[current verification runbook](runbooks/FULL_TEST_FLOW.md). No FE/browser-synced claim or new handoff.

## HISTORICAL INFORMATION — 11/10/2026 S4.8 accepted wire implementation

| Surface | Current wire/validation | FE action for final handoff |
| --- | --- | --- |
| N1–N3 | Save/read/replace/archive; shared Store reads, immutable original creator; UUID idempotency key, quoted If-Match for N3; ETag/Location; active full replacement or archive-only union | Separate Save from can_generate; show unknown/invalid validation; re-read ETag after conflict; no restore UI. |
| N4 | Decimal-text cap; If-None-Match:* create201, If-Match replace200; missing428/stale412; numeric no-op preserves version/time | CORS allows If-None-Match and exposes Location; never send both conditionals. Cap changes do not rewrite saved values. |
| Configuration validation | Money18/18, percent0..100 fraction32, null/omit/0 preserved; inherited paths pin defaults, full custom ignores stale defaults; 64KiB pre-parse body cap; 422 Vietnamese field_errors, malformed400, oversized413, error meta{} | Use exact string numeric fields and field errors; do not round retained evidence or infer execution readiness from a successful Save. |
| R01/C01 | Canonical selected-action whole deny; explicit source_versions.model_config; seven-day estimated local scope, fresh declaration watermark; C01 all active saved, invalid included, archived omitted | Keep data_status separate from execution_status; NOT_ASSESSED is never winner/feasibility proof. Public planning remains unavailable. |
| I06 | New completions retain authorized post-write readiness ready/blocked/unknown; names-only omissions; old immutable unknown projections still valid | Support both historical and current projections without recalculation. Existing operation definitions are unchanged; shared CompletionActionReadiness/CompletionReadinessIssue OpenAPI components expanded. |
| Model configuration | Explicit operator BASELINE registry; no customer model selector, auto latest artifact or public forecast route | Store unknown/unavailable must remain visible; S4.9 owns public planning. |

Six operations/five paths added relative to exact ZIP10/10 audited source runtime;
43 core operations + health. No new handoff/ZIP and no FE-synced claim.

## 11/10/2026 — audit remediation + S4.7

| Audit / route | Wire/validation hiện hành | Compatibility và FE action |
| --- | --- | --- |
| CA-002 / I05 | reason optional/null cho pure insert/NO_OP; effective correction/merge/count/amend cần nonblank1..1000,422 COMMIT_REASON_REQUIRED | Clients đã gửi reason vẫn hợp lệ. Confirm_review và source/action reasons không đổi. FE không ép nhập reason cho mọi import. |
| CA-019 / N6 | Không đổi request. OPENING_STOCK kiểm same-Ingredient intervening events/evidence;409 STALE_STOCK_OBSERVATION, STOCK_OBSERVATION_UNVERIFIABLE, OPENING_STOCK_ALREADY_RECORDED | Fresh CAS không đủ; quan sát/đối chiếu lại, không đổi key để cộng lượng cũ. ACTUAL_RECEIPT gửi muộn có LATE_RECEIPT_RECORDED, không bị chặn chỉ vì newer movement. |
| CA-020 / M04 | Staff explicit whole-sheet IGNORE own batch không N5 riêng; ownership/grants/ack/reason vẫn enforce | Không activate/update approved profile; không quota release; refresh invalidated preview/confirmation. Completed scope không đổi. |
| CA-016 / source inputs | Source business keys1..1000; profile namespace Code vẫn1..128. Money mới18 integer/18 fractional, Quantity độc lập≤200 nguồn Import | Descriptors M03 phản ánh pattern/length, không dùng bounds Quantity cho tiền. New input vượt Money bị block; không round/truncate. |
| CA-016 / retained Import projections | Retained pre-alignment monetary text vẫn exact, schema **output** cho phép historic decimal≤200; schema **input** Money giữ18/18 | Legacy output exception không phải quyền ghi Money rộng. Existing evidence/digests không sửa. Old pending commit vượt Money409 LEGACY_MONEY_REVIEW_REQUIRED, review/re-preview; không tự migrate price. Public P01/P02 vẫn Money18/18 và có thể503 với legacy không thể biểu diễn. |
| CAT12 N20–N22 | Ba method/routes đã approved design, nay có HTTP typed phases/retained read | Không phải endpoint design mới. N21 synchronous200 preview/commit; key từng phase, If-Match cả hai. FE cần màn hình lịch/diff/ack/read. |
| CA-021 | Current clauses hợp nhất, phần lịch sử gắn nhãn; matrix bounds thống nhất | Không coi absence của S4.4/5 hoặc source chưa HTTP trong baseline là state hiện tại. |
| H01/H02 | Gán slice owner S4.10; chưa implement | Vẫn approved v1, không deferred và không được giả HTTP đã có. |

Các IDs CA-* gốc giữ trong [audit](API_CONTRACT.md). Đây không
claim tất cả audit findings là regression mới hay toàn bộ v1 HTTP ready.
