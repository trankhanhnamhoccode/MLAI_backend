# S4.4 — Import staging/mapping/preview

CURRENT FACT C4: M01/M02 counters đếm mapping issues theo AND filters, giữ legacy
Progress; I04 source_effect dùng cached pinned source/effect và R05 raw/logical
aggregates độc lập page size, không double-count grouped/multi-location actions.
Canonical definitions/examples do [Import §17](../IMPORT_MAPPING_API_CONTRACT_VI.md#mapping-projections)
sở hữu; [FULL_TEST_FLOW](../runbooks/FULL_TEST_FLOW.md#read-discovery-c4) giữ commands/limits.

CURRENT FACT C3: actual receipt schema, typed effect/completion and shared N6
identity/writer implemented. [Import §16](../IMPORT_MAPPING_API_CONTRACT_VI.md#excel-actual-receipt)
owns semantics; [schema inventory](IMPORT_SCHEMA_INVENTORY.md) owns source fields;
[runbook](../runbooks/FULL_TEST_FLOW.md#excel-actual-receipt-c3) owns commands/results.
C2 MQ/N5 review is reused; approval does not commit inventory. C4 read projections are implemented in local source; no canonical writer policy change.

CURRENT FACT C2: MQ01–MQ03 provide explicit pinned full-spec submissions and Store
queue/detail; N5 resolves the live submission and supports request_changes.
Content/lifecycle drift fences review, while approved history retains its pins.
Approval activates a profile; preview/confirm/commit remain separate. MQ03 exposes
bounded source evidence under current sensitive reads. C4 reuses its SourceEvidenceCell/bounds and adds I04/M01/M02 projections. Canonical workflow is in
[mapping queue contract](../IMPORT_MAPPING_API_CONTRACT_VI.md#mapping-queue);
[FULL_TEST_FLOW](../runbooks/FULL_TEST_FLOW.md#collaboration-c2) owns commands/limits.

HISTORICAL INFORMATION — S4.6 had nine schemas. CURRENT FACT C3: fifteen schemas have atomic writers, including inventory_receipts sharing the N6 receipt boundary; N8 stays separate. See [S4.6 feature](IMPORT_INVENTORY_SUPPLIER.md) and [evidence](../runbooks/FULL_TEST_FLOW.md). Four-schema/unsupported statements below describe the S4.5/S4.4 historical slice boundary.

## CURRENT FACT — consumer S4.5

Staging/field-value foundation giữ nguyên. Nay [S4.5 canonical commit](IMPORT_CANONICAL_COMMIT.md)
đã dùng retained data/explicit declarations cho products/ingredients/sales/recipes;
I05 commit202/J01/I06, current fences/retry/atomicity. confirm_review vẫn staging-only.
Các câu “commit409/can_commit=false/no S4.5” bên dưới là HISTORICAL INFORMATION
của S4.4 extension, không mô tả current consumer; unsupported schemas vẫn S4.6.

## CURRENT FACT — batch accounting/quota projection, 10/10/2026

S4.4 additive I04 `data.quota`: accepted_file_count,accepted_total_bytes,
remaining_file_slots,remaining_bytes (integer, whole batch, not page). Counts only
uploaded logical file records, including parse-failed records and duplicated bytes
under different client IDs; rejected do not count. Actual raw server file sizes,
not client declarations/expanded XLSX. Derive N/B from all files used for file_count/
source_set, remaining20−N/104857600−B; coherent refreshed batch metadata after current
authorization lock order, no source/canonical writes or parser/LLM/job execution in GET.

ACCEPTED CONTRACT: multiple pre-seal I02 calls; ordered partial per-file admission;
request guards/whole transaction rollback retained. Same bytes/new client ID counts
again while blob dedup remains. file_set_version revisions include file receipt
changes, new-key rejected/client-ID replay; same-key frozen receipt replay adds no
version/quota, even after seal (refresh I04). I03 acceptance commits seal before
worker; failed analyze never opens upload. Explicit same-source retry only; new
source after seal requires draft. No remove/replace/quota release; ignore keeps file
quota.200 upload may be mixed;422 UPLOAD_REJECTED has committed receipts distinct
from request-validation errors. I03 full accepted IDs/full rejected ack/current CAS.

Authoritative details [Import contract9.1a](../IMPORT_MAPPING_API_CONTRACT_VI.md#import-batch-mechanics),
[FE scenarios](../IMPORT_MAPPING_API_CONTRACT_VI.md),
[commands/evidence](../runbooks/FULL_TEST_FLOW.md).
Targeted verification is recorded there, not a full suite, real-provider or SLA claim.
No migration/new path/DELETE/canonical commit/S4.5/S4.6. Earlier sections are slice-time
evidence; no longer treat old quota/parser absence as current capability.


## CURRENT FACT — explicit scalar field-value sources

Required rows no longer need every required field as a physical Excel column:
bounded reviewed PROFILE_CONSTANT/import-only IMPORT_VALUE sources are implemented.
[Feature/FE flow](IMPORT_FIELD_VALUE_BINDINGS.md),
[allowlist/verification](../runbooks/FULL_TEST_FLOW.md).
Build-spec, reuse, normalize/provenance and content-bound review include sources;
Owner approval remains distinct from per-import values/review. Missing batch value
blocks reused preview; no Qwen constants or hidden canonical lookup. No writers,
new schemas or migrations; generic/nested injections still absent.

CURRENT FACT — Recipe source basis: M03 có required `recipes.quantity_basis`
(`PER_SERVING`/`WHOLE_BATCH`), M04 nhận column mapping hoặc shared_value cùng Owner
review. Normalize chuyển per-serving × yield thành whole-batch bằng exact fractions,
giữ loss để BOM áp một lần. Preview/committed references bổ sung source_value ở field
provenance và quantity_basis ở line_provenance. Không thay Recipe DB/BOM/readiness
policy, không migration/new endpoint. Old profiles thiếu basis cần Owner review;
IMPORT_VALUE không giữ facts của batch trước. Workflow/examples/limits nằm tại
[Recipe contract](../IMPORT_MAPPING_API_CONTRACT_VI.md#recipe-source-basis-và-canonical-whole-yield).
FE cần selector basis và hiển thị nguồn → canonical quantity/unit/yield/loss cùng
declaration evidence; version/dates là import-only. Output conversion và mass-volume
Recipe conversion chưa hỗ trợ. Initial historical recipe được phép khi explicit và
không conflict; không đóng kỳ đang mở hoặc sửa nội dung version đã tồn tại.

### HISTORICAL INFORMATION — descriptor follow-up before field-value extension

CURRENT FACT / schema inventory follow-up: see
[complete field inventory and gaps](IMPORT_SCHEMA_INVENTORY.md).
M03 now exposes nullable/input_sources/input_help: row requiredness is separate
from physical source; existing identity bindings accept names/codes, not only UUIDs.
Runtime still lacks generic context-to-row constants. Opening, actual goods receipts
and purchase history are not aliases for inventory_count. No extra source schemas.

## CURRENT FACT — classification/review extension (2026-10-10)

User-authorized sheet/column review task completed in staging scope. Evidence and
before-edit gap/freeze/rollback: [task notes](../runbooks/FULL_TEST_FLOW.md).
Existing S4.4 results below are historical evidence for the foundation, not a
claim these new behaviors were covered by the earlier61-test gate. No S4.5 writes.

### One descriptor authority, suggestions and corrections

`application/import_descriptors.py` projects existing SOURCE_MODELS, not legacy
schemas. Nine supported schema IDs, Vietnamese labels, requiredness including
required nullable columns, explicit nested fee/declaration constraints, aliases,
exact unit/reference/date semantics and value_role. canonical_candidate means
candidate normalized value, not a guarantee that this field is a DB column or
that a canonical writer is available. M03 and Qwen use the same descriptors;
source DTO validation and preview's business checks remain authoritative.

Order: unique compatible active approved Store profile → deterministic REUSED;
otherwise rule type/mapping by indexed headers + required coverage, sheet-name
hint only; unresolved/ambiguous/incomplete coverage → optional Qwen. A sheet-name
alone never determines type. Structural ties remain ambiguous; high confidence
never bypasses required columns, duplicates, context conflicts or Owner approval.
Physical sheet name may be empty; canonical entity names still cannot be empty.

CURRENT FACT: discovery tìm header trong tối đa tám dòng đầu sau các dòng trống/
đơn cột (title/ghi chú), chỉ nhận candidate có ít nhất ba ô text không formula.
Không vượt qua dòng đa cột; không ghép nhiều dòng thành header. SheetInfo hiển thị
header_row/preamble_rows/preamble_samples (≤1000 ký tự/dòng, review cùng source file),
raw preamble và header giữ trong staging; body giữ số dòng
vật lý/cached formula/lexical cells. Styled empty trailing cells không tạo cột giả;
ô dữ liệu có nội dung ngoài header vẫn tạo cột không nhãn cần review.

Aliases normalize Unicode/case/diacritics/spacing/punctuation chỉ cho header hints,
không đổi values/units/identities. M02 suggestion_reason/candidate_targets giải thích
exact key, controlled alias, duplicate hoặc semantic review. Generic unit/name/
currency không đủ phân loại workflow; headers consumption/receipt/calendar/tabular
business rules được nhận diện ngoài schema hiện hành, không auto-IGNORE hay ép sang
sales/count. `SLX`, `MOQ`, giá mua theo đơn vị, lượng mỗi serving, version `v1.2`
và ngày kiểm kê không timezone phải review; không tạo loss/fee/unit/source identity.
Numeric Excel dates có target vẫn có DATE_CONVENTION_REVIEW: cần M04 khai báo
EXCEL_SERIAL, workbook epoch và Owner duyệt normalization. Raw numeric giữ nguyên;
preview chuyển date-only theo1900/1904, giữ provenance. Fictitious serial60/1900,
fractional time và overflow block; không tạo observed_at hoặc receipt timestamp.

M01 exposes selected_type/suggested_type/classification_origin/confidence/ignored/
ignore_reason. M02 review_only=false exposes all indexed column mappings, including
successful reused pairs and explicit ignored fields. RULE confidence is required-
field coverage heuristic; QWEN confidence self-score. MANUAL/REUSED confidence=null,
not fake1. Null target is UNRESOLVED until an explicit ignore resolution is retained.
Duplicate headers remain separate indices; duplicate targets are rejected.

N5 Owner có thể duyệt whole displayed spec khi RULE classification/target duy nhất,
không có pending ambiguity/missing fields/identity/conversion/schema blockers.
Các đề xuất này vẫn needs_confirmation trước N5; complete proposal không can_preview.
N5 thành công mới đánh dấu approved profile và bind version. Unknown/ignored cần
explicit M04/reason; QWEN cần review riêng. Full profile + review_only=false vẫn cho
Owner đọc toàn mappings trước quyết định. Staff không activate, preview/commit và
per-import confirmation giữ permissions/atomic semantics hiện hành.

M04 classification issue: select sheet_type or explicitly ignore whole sheet with
acknowledgment/reason. Type change removes invalid targets and incompatible derived
identity/conversion issues; same type retains compatible corrections/issues/IGNORE.
This forks proposal/pins and invalidates usage, not immutable approved versions or
preview evidence. Direct edits to reused columns are also allowed: fork proposal,
preserve approved source context/rules, require fresh Owner approval before preview.
Required columns cannot be ignored into readiness; known unsupported business-rule
columns remain blockers, rather than pretending an unhandled fee/tax rule disappeared.
Whole-sheet acknowledged ignores are retained in preview evidence and warnings.

Profile reuse remains Store + declared stable source/report + schema/structure,
not filename inference or unapproved learning. Ambiguous/context-conflicting profiles
do not auto-select. New structure is review-required, not a new auto-activated version.
Unchanged approved parsing/conversion rules and manual/IGNORE origin are retained.
Khi M04 khai báo scope có active profile nhưng cấu trúc/semantics không khớp,
PROFILE_STRUCTURE_OR_SEMANTICS_DRIFT hiện warning; không auto-bind version. Scope
khác/cross-Store không được dùng làm memory. Signature có raw headers, observed
column kinds, physical header row và XLSX epoch; đổi layout/type/header/epoch cần
review lại. Header reorder cũng là drift, không tự remap indices. Profile XLSX từ
bản chưa có epoch phải review lại một lần; immutable version cũ không bị sửa.

### Provider payload and failure boundary

OPENROUTER_MAPPING_MODEL fixed qwen/qwen3.5-9b; backend Settings SecretStr API key.
IMPORT_LLM_SUGGESTIONS_ENABLED mặc định false; key không tự bật provider. Live
gateway probe POS demo đã chạy trong approved model/data/calls/cost scope. Adapter xử lý
phần chưa gán, kể cả semantic ambiguity có candidates; output thay RULE type/targets bị từ chối, duplicate ambiguity giữ
review. Known unsupported sheets không gọi model. Hai eligible sheet/batch tối đa,
mỗi sheet hai transport attempts; vượt cap có LLM_CALL_LIMIT và manual fallback.
temperature0, reasoning.enabled=false, strict response_format JSON Schema,
provider.require_parameters=true. Không fallback model/API endpoint hay schema
weakening. OPENROUTER_MAPPING_PROVIDERS mặc định rỗng dùng upstream routing;
nếu khai báo allowlist thì provider.only + allow_fallbacks=false.
Official [structured output docs](https://openrouter.ai/docs/guides/features/structured-outputs),
[model page](https://openrouter.ai/qwen/qwen3.5-9b) and
[reasoning docs](https://github.com/OpenRouterTeam/docs/blob/main/guides/best-practices/reasoning-tokens.mdx)
were checked; this is documentation evidence, not a live provider test.

Payload sheet_profile/1: display filename/sheet name≤200 chars (hints only), stable
source-column indices, lexical kind hints, at most8 evenly sampled rows with first/
last where available, each cell≤200 chars, chỉ samples của columns chưa có RULE
target, current descriptors và rule suggestion. Có header_row/row_count/epoch,
rule candidates/reasons, missing required fields và tối đa4 related sheets cùng
authorized batch (type/hint, tối đa16 headers mỗi sheet). Headers/indices vẫn giữ đầy đủ
để validate whole output, known target samples không gửi.
Optional selected type limits adapter targets; no separate remap/provider endpoint
was added. Source facts are never normalized/imputed by the model. No raw workbook,
catalog, actor/session/token, Settings contents or operational read-set is sent.
Provider authorization header carries only its required configured API key, never logs.

Max32 columns for optional provider (parser/manual still support256); input96KB,
response64KB. Settings cho sample limit1..8, output128..1800 tokens, socket timeout
>0..30s, deadline>0..60s; defaults8/1800/30/60. At most2 attempts within the
monotonic acceptance/retry deadline. Chunk reads reset socket timeout to remaining
budget and late results are rejected. DNS/OS scheduling are not hard-real-time SLA;
no performance/live slow-network assertion. No retry on invalid output or ordinary
4xx; transient429/502/503/504 and transport errors may retry within deadline.

sheet_suggestion/1 has type, indexed targets|null, confidence, warnings, optional
bounded candidates (≤4) và reason (≤200 chars) mỗi cột;
source/status/approval are backend controlled. Every source index exactly once,
allowed schema targets, unique targets, finite strict numeric scores; extra fields,
truncation, bad JSON/schema reject entire suggestion. No partial accepted output.
No-key/outage/timeout/invalid output leaves durable analysis for manual review,
with typed notice; does not discard uploaded batch. Sessions are released before
provider calls. Provider notices are advisory, never canonical facts or status.
Safe SheetInfo diagnostics expose model/prompt/schema versions/input digest/attempts/
usage/status và controlled failure stage/code, never raw output or credentials.
GET/polling và same analyze receipt không gọi lại provider. Publication kiểm active
claim/file set và captured mapping revision: kết quả muộn sau mapping edit không
được ghi đè. HTTP/DB tests dùng mock provider. Một live POS probe qua
DeepInfra/bf16 nhận structured output hợp lệ, 1 completion POST không retry,
2.777 input +370 output tokens, provider-reported cost $0,0003332; không phải
giá cố định hoặc SLA. Proposal giữ hai RULE targets, SLX → sales.quantity cần review;
đơn giá/doanh thu/stockout/CTKM null vì schema Sales chưa hỗ trợ. Tên món là
identity token cần explicit Store binding, không canonical UUID do model tạo.
Đối chiếu local 1.155/1.155 dòng có SLX × đơn giá = doanh thu hỗ trợ semantics,
không tự phục hồi lost demand từ stockout hoặc biến promotion thành business rule.
Probe giữ file gốc, không profile activation/canonical writes/browser acceptance.
Isolated transport dùng price filter + pinned endpoint + no fallback, phí request0,
output≤1.800; trần token-cost bảo thủ cho3 attempts dưới $0,10. Đây là guard của
probe, không phải budget USD setting có sẵn trong application adapter.

### Per-import confirmation — preparation for S4.5, no commit

I05 phase=confirm_review with exact preview_id/digest/mapping_revision, confirm=true
(strict boolean), reason, If-Match import revision, session/Origin/CSRF/key →HTTP200.
Preview keeps HTTP202. Current import.commit + every required_action from complete
preview is required, including corrections/declaration-specific rights. Profile
approval and review confirmation are distinct. Staff with full scope can confirm;
it does not activate a profile or confer a right.

import_review/1 records exact source/file set, reviewed import/mapping revisions,
binding digest, immutable preview ID/digest/read-set, actor/aware time/reason/hash.
Retained preview digest additionally covers reviewed sheets/mappings/explicit ignores.
Staging pointer, append-only audit and scoped retry receipt commit atomically, using
existing0013 storage; no second profile cache, table or migration. Failure after
flush leaves no confirmation/audit; shared HTTP error sanitization returns503.

I04 review_confirmation + confirmation_usable validate identity/integrity, current
rights/pins/revisions and fresh operational read-set. Stale preview, retired binding,
edit or newly generated preview invalidates usage; new preview explicitly requires
review again. Source/preview/audit evidence stays immutable. Same-key retry returns
the historical receipt after reauthorization, not a promise it is usable now.
Each new import, including REUSED, starts without confirmation. Review does not
replace future row-specific sales/supplier resolution confirmations.

There remains a possible operational change after verification; S4.5 must recheck
current permissions/read-set and consume exact confirmation at atomic commit.
canonical_commit_supported/can_commit remain false; phase=commit still409. No
completion/history/readiness/canonical writers added in this task.

### Synthetic walkthrough (executable test, not customer/provider accuracy)

1. Store A uploads sales CSV with `POS custom quantity`, row105/cup/Product UUID.
   Unknown header remains review-required (manual fallback if no provider).
2. M04 assigns indexed column to sales.quantity; source_context POS-A/daily-sales,
   user selects sales and reviews all fields. MANUAL correction has confidence=null.
3. N5 Owner approves whole immutable version; I05 preview returns NEW sales105,
   no canonical SalesDaily inserted. I05 confirm_review stores actor/source/pins/hash.
4. New import same Store/source/structure: deterministic REUSED/version, no Qwen or
   reconnecting columns. Preview again105, review_confirmation=null until this import
   is explicitly confirmed. Old confirmation cannot satisfy new import.
5. Fresh Sessions assert one profile version, two distinct review audits and zero
   canonical sales. Test: test_manual_correction_owner_profile_then_reuse_still_needs_own_confirmation.

Verification is targeted PostgreSQL/HTTP + offline provider/parser/preview/schema/
OpenAPI tests, not full suite or security/model-quality certification. Live
OpenRouter, FE/browser UX, production load, provider accuracy and canonical commit
remain unverified/unimplemented as appropriate; no development DB accessed.

## CURRENT FACT — implementation hiện hành (2026-10-10)

I01–I04, M01–M04, N5, I05 phase=preview và J01 đã được wired. Evidence/trạng
thái verification trong [historical scope notes (retired)](../runbooks/FULL_TEST_FLOW.md) và
[CURRENT_STATE](../CURRENT_STATE.md). Không canonical import writes, I05 commit,
I06 completion, H01/H02 history hoặc R01 readiness; can_commit=false và
completion_available=false. Foundation report bên dưới là HISTORICAL INFORMATION.

### FE flow

1. I01 POST /api/v1/stores/{store_id}/imports với data_date required →201 draft.
2. I02 multipart files[]/client_file_ids[], Origin/CSRF/session/UUID key →200 file
   receipts. Toàn rejected →422 UPLOAD_REJECTED với per-item structured errors và
   revision/source-set details; outcome retained để retry không tạo file trùng.
3. I03 If-Match import revision + exact source-set/all accepted IDs/explicit
   rejected acknowledgments →202 job; source set sealed, sửa bytes cần draft mới.
4. Poll J01; failed GET vẫn200/status failed/result null/sanitized location error.
   GET không chạy parser/provider/normalization/preview.
5. M01 summary + include_profile_details/full proposal/approved context catalogue;
   M02 issue samples≤5×200; M03 typed options/unavailable duplicate targets;
   M04 chỉ proposal. N5 current Owner quyết định whole version với CAS/key/audit.
6. I05 phase=preview + import/mapping revisions →202 job; I04 include_preview=true
   đọc retained immutable rows/summary. include=configurations,preview sử dụng
   cùng preview ID/digest/classification/page; không trả rows ngoài trang.
7. Config-only không tự kèm preview object. Trước preview, basis=analysis với
   paged retained raw cells/proposed targets và normalization_status=NOT_PREVIEWED;
   không giả rằng empty normalized collections là empty operational config. Sau
   preview basis=preview, typed normalized staged revisions/blocked_row_ids/stale.

### Source context và profiles

CURRENT FACT: allowed_actions/can_preview còn bị giới hạn bởi current grants/state,
không chỉ mapping validation. Reader-only không có mutation hints; empty draft
không analyze hint; retired binding không preview hint. Hints không freeze quyền:
mutations và finalize luôn reauthorize hiện hành.

ACCEPTED DECISION: người dùng duyệt M04 resolution.kind=source_context; trusted
Store/actor, stable source_system_key/report_type regex
[A-Za-z0-9][A-Za-z0-9._:-]*,1..128; meaningful evidence1..1000. Provenance
verification=USER_DECLARED, Owner review không độc lập xác minh hệ thống nguồn.
Không suy codes từ tên file/header similarity. CURRENT FACT: analyze giữ source
unresolved, signature chỉ structural candidate. M04 source declaration hợp lệ và
unique compatible approved match trong Store/source/report →reuse immutable version
không reapproval; signature không còn tự skip optional provider proposals. Nhiều match →
PROFILE_MATCH_AMBIGUOUS, chọn explicit approved context, không tự chọn. Mâu thuẫn
với explicit metadata columns source_context.source_system_key/report_type →
SOURCE_CONTEXT_CONFLICT; columns này vẫn cần resolution/ignore, không verified fact.

TECHNICAL CHOICE: optional context fields Owner review cùng mapping:
sales_semantics daily_total/disjoint_contribution; inventory_semantics lot_stock_count;
decimal_locale dot/comma; date_format ISO/DMY_SLASH/MDY_SLASH;
Supplier price/MOQ dùng explicit columns/shared declarations theo
[Import §13.2](../IMPORT_MAPPING_API_CONTRACT_VI.md#supplier-source-basis-và-fe-projection).
pack_cost_basis cũ chỉ retained readability; proposal mới cần basis/denominator/MOQ
fields, không implicit đơn giá theo 1 source unit. Không đoán locale/unit/date/pricing.
Omitted/null formats không khai báo rule mới; approved selection giữ approved rules.
Khai báo semantics/rule khác phải proposal/reapproval. Scope khác fork profile family.
Context edits invalidate binding/revision/preview usage, không sửa active spec hoặc
retained preview. Unknown identity/conversion/reservation là exception không fuzzy.

Supplier-only optional fields: planned_arrival_expiry_rule với basis
ARRIVAL_PLUS_DECLARED_SHELF_LIFE_DAYS/evidence; term_period_amendments[] gồm
supplier_term_id, expected_version (captured row xmin), effective_to, reason.
Đây là typed representation của contract13 đã duyệt; không policy mới. Mapping
approval vẫn không commit file, grant rights hoặc xác nhận mua hàng.

### Storage, transaction và executor

TECHNICAL CHOICE: migration0013 thêm10 staging tables: batches, scoped byte blobs,
files, profiles, immutable versions, approved contexts, jobs, previews, scoped
receipts/audit. Bounded bytes lưu local PostgreSQL bytea atomically cùng metadata,
không client filepath/external storage/DB dumps. Existing filesystem ML/artifacts
giữ nguyên. Dedup chỉ trong Store. Không TTL/purge/backup/DR policy mới.
DB guards bảo vệ immutable evidence/source seal/captured raw rows; chỉ file parse
status và retirement flag được đổi có kiểm soát. Proposal/bindings là mutable CAS
metadata; approved versions/previews verify content digest khi load.

READ ONLY REPEATABLE READ trước first SQL; detached exact Decimal/date/UUID JSON,
deterministic ordering/digest + xmin để detect ABA. Relevant schema tables only;
declaration subtype có permission/read-set scope riêng. Session/connection đóng
trước parser/normalization/provider. Finalize current actor/session/Store/grants
recheck + claim/source/mapping fence. Preview hash gồm source file IDs/hashes,
mapping pins/digests, policy/read-set/rows/summary, excludes only summary.digest.
GET chỉ check integrity/current revisions/stale, không recompute/change latest.

Durable acceptance→claim UUID/process incarnation→atomic completed/failed + audit.
Recovery chỉ proven DEAD local OS process; ALIVE/UNKNOWN giữ, không TTL hoặc silent
retry bằng config mới. Explicit analyze retry tạo attempt mới. Fresh failure
recording không thay primary error; durable COMPLETED giữ khi post-commit programming
bug, exception vẫn propagate. Không blanket reconcile mọi commit error thành success.
API persistence errors là error; retry cùng key/current authority đọc durable receipt.
Transport injection sau real PG commit không phải live network-outage proof.

Default IMPORT_WORKER_ENABLED=false giữ app import/startup/health không connect DB.
Enable explicit private config để một local thread drain bounded jobs; không broker.
Shutdown đợi bounded attempt, chưa production SLA. Disposable-only CLI, không migrate/
reset/seed và guard exact local shelfcash_test/no query overrides/current_database:

```powershell
.venv/Scripts/python.exe scripts/run_import_jobs.py --test-database --max-jobs 20 --recover
```

HTTP202 không có nghĩa đã computation; FE cần worker enabled hoặc explicit test
executor. Development worker/migration không chạy trong verification này.

### Preview semantics và giới hạn

- Sales zero khác missing, duplicate Product/date reject;100→105 daily replacement
  delta5, disjoint contribution205 có explicit confirmation intent. Existing source
  contribution registry UNKNOWN, không giả implemented provenance.
- Count existing lot only, aware nonstale observation/exact scope/units;12→10 delta−2,
  12.0→12 NO_OP. Không receipt/stock bootstrap/new lot.
- Recipes grouped whole version/lines/yield/loss/effectivity; line unit theo
  Ingredient, yield unit theo Product. Duplicate/overlap reject/no autoclose.
- Explicit Owner-reviewed Product/Ingredient/Supplier reservations tạo typed
  CREATE/dependency preview, không canonical entities/movements.
- Supplier15×28000/source-unit→420000/pack trước declared conversion; rational
  terminating exact arithmetic independent ambient Decimal; nonterminating block.
- Future term overlap cần explicit pinned amendment close previous at newfrom−1,
  before/after/expected_version/supplier.terms.correct/confirmation_required.
  Historical/stale/conflicting amendment blocked; không update actual term. Source
  key của old canonical term null là UNKNOWN, không fabricated identity.
- Tracked arrival expiry thiếu rule/shelf life giữ warning, không readiness success.
  Rule hypothetical arrival không ghi expiry lot thật. NONE fees cần explicit
  COMPLETE/evidence/coverage; UNKNOWN khác0; unsupported mixed/%/tier blocked.
  Existing term source coverage chưa verified block, chưa có source-key registry.
- Typed inventory/sales/procurement declarations validate scope/units; missing không
  synthesize0; UNKNOWN/unsupported inbound giữ issues, không planning-ready claim.
  Any blocker giữ atomic can_commit=false; permission/validation/commit là riêng.

CSV UTF8/BOM lexical delimiter, multiline logical+physical locations. XLSX cached
formulas only, không execute/cache-freshness claim; unsafe ZIP paths/DTD/entities/
macro/external relationships/encryption/malformed coordinates rejected.20MiB/file,
100MiB accepted batch/20files,200MiB expanded XLSX/batch,100sheets/100k data rows,
256columns/4096ZIP entries per file. Native booleans handled. Date text ISO hoặc
declared slash hoặc explicit EXCEL_SERIAL theo workbook epoch đã duyệt; styles
không tự chọn date semantics. Near-limit CPU/memory/latency chưa benchmark.

Optional OpenRouter theo provider boundary phía trên: default OFF, bounded indexed
semantic samples, không raw workbook/catalog/operational snapshot/credentials.
Allowlisted unapproved suggestions only; missing config/outage LLM_UNAVAILABLE,
manual/reuse hoạt động. Các giới hạn20headers/1000tokens/15s là HISTORICAL INFORMATION
của adapter nền tảng trước classification extension, không cấu hình hiện hành.
Offline provider tests không live model proof. Không browser FE/load/SLA/security
certification/production recovery/backup. Không S4.5/canonical histories/configuration
commit/readiness/forecast/DecisionRun trong slice này.

## HISTORICAL INFORMATION — foundation report trước source_context approval

**CURRENT FACT: PARTIAL — contract clarification pending.** No I01–I05/M01–M04/
N5/J01 HTTP, staging tables, immutable upload receipt, profile approval/reuse,
retained preview or job executor is wired yet. No capability advertises these as
available. S4.5 canonical commit is not implemented or started.

Authority: [Import contract](../IMPORT_MAPPING_API_CONTRACT_VI.md), especially
sections5/9.1–9.2; [AUTH v1](../AUTHORIZATION_CONTRACT_VI.md#auth-v1).
[current verification runbook](../runbooks/FULL_TEST_FLOW.md) record exact scope/evidence/rollback.

## Contract clarification required

Profile scope requires declared source_system_key/report_type/schema_version.
I01 body currently contains data_date; I03 seals file_set_version and file IDs.
The listed M04 resolutions cover columns, identity/conversion/ignore/new entities,
not source context. Source and report identity cannot be inferred from filename,
header resemblance or a generated business identity.

PROPOSAL pending user decision: add M04 resolution kind=source_context, with
source_system_key/report_type/evidence_reference, for source-level issue; Owner
still approves full profile version. Alternative: accept source context only from
explicit source file declarations and block missing context. No variant/public
field or new decision has been silently accepted/added.

## Implemented independent foundations

`app/application/contracts/import_source.py`: frozen detached SourceCell/SourceRow/
ParsedSheet/ParsedFile, tuples, lexical values and physical locations. No canonical
entity or approved identity is constructed. Numeric raw strings preserve exact
workbook values; missing/empty is distinct from0. No floats, date/locale/unit guesses.

`app/infrastructure/import_parser.py`: bytes-only UTF-8/BOM CSV and XLSX XML/ZIP
reader. CSV logical record and physical line start/end preserve quoted multiline.
XLSX keeps cell column indexes/physical row numbers and cached formula values;
never evaluates formula, macro, external link or client filepath/URL. Uncached
formula blocks FORMULA_VALUE_UNAVAILABLE with source location; cache freshness
is not proven/recalculated. This module is **not an upload/analyze API**.

Limits:20MiB file,200MiB expanded XLSX,100 sheets,100k data rows,256 columns;
additional4096 ZIP-entry bound prevents directory explosion. Reject duplicate/
unsafe ZIP paths, encrypted/macro workbook, XML DTD/entities (including UTF-16),
external workbook relationships, invalid row/cell coordinates and corrupt archive.
No file extraction. Parsers fail without truncating success; byte output remains
immutable and caller inputs are not retained as mutable containers.

TECHNICAL DEBT / not verified: no whole-batch20 files/100MiB/100 sheets/100k row
budget yet; no application source-set sealing/idempotency/integrity retention or
upload MIME sniff integration. The parsed result is in memory: declared bounds
are not a production memory/latency guarantee, and near-limit load was not tested.
No schema discovery, normalized numeric/date conversion, profile matching,
canonical validation, completeness, supplier/fee promotion or provider calls.
No local worker/dispatcher command for Import can be given yet.

## Cursor prerequisite fixed

Real PostgreSQL negative tests reproduced T01/Staff accepting modified offsets
signed with client-held session token. Scope authorization still ran independently;
this is cursor integrity, not evidence of cross-Store access. Now one shared
CursorSigner primitive uses private owned process keys and domain/session binding.
T01/Staff share Auth-owned signer; S4.3 uses its own signer instance with same
primitive. No route, DTO, business permission or lifecycle change.

Valid paging remains; client-forged MAC rejected422, different session/filter/limit
invalidates, foreign Store still404. Process/service restart invalidates old opaque
cursors, requiring refresh. Keys are not persisted/exposed/logged. No second crypto
framework/provider or schema migration. Historical S43 note about old signing is
superseded by this verified prerequisite fix, not rewritten as past verification.

Tests: guarded real shelfcash_test paging/current revoke/HTTP, plus14 pure parser
cases; exact commands/results in S44 notes. No live LLM, browser/FE, filesystem/DB
staging consistency, durable job/crash/preview acceptance, full regression or
production security certification. Development DB and prior18 ZIPs untouched.
