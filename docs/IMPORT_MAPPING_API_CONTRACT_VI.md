<a id="import-sources"></a>
# Import — reviewed mappings and atomic canonical commit

## Authority, implemented scope and known drift

CURRENT FACT: I01-I06/M01-M04/N5/J01/H01/H02/R01 are wired with Store authorization,
immutable staging/preview/provenance, manual/approved-profile deterministic flow,
canonical fifteen-schema adapters and durable history/completion. Upload/review/save/
HTTP202 are not canonical persistence. Runtime: app/api/import_staging.py,
app/application/use_cases/import_staging.py and import workers/repositories.

ACCEPTED DECISION: Owner approves/activates reusable mapping profiles; Staff may
propose and may explicitly IGNORE a whole sheet in their own uncommitted batch
under current rights/reason/ack. Mapping approval differs from import confirmation.
Atomic commit applies all requested groups or none. LLM cannot write canonical
facts, resolve identities/conversions by guessing or bypass authority; provider
absence keeps manual/approved-profile workflows available.

ACCEPTED DECISION: ADR-013 permits an authorized mapper to approve their own
mapping; the current product contract limits reusable-profile approval/activation
to Owner. These rules are compatible: Owner may create and approve/activate the
same profile, while Staff may propose under current grants. No two-person rule or
superseding ADR is implied. Confirmation/commit recheck current rights separately.
ADR-008's
same-dataset replacement prohibition is preserved; independently confirmed source
contributions may merge under the approved sales policy, not a generic sum/upsert.

Source DTO/OpenAPI owns structures. The workflow/meaning below is canonical;
[API](API_CONTRACT.md) owns shared transport/Catalog/Inventory,
[Authorization](AUTHORIZATION_CONTRACT_VI.md) owns grants,
[Planning](PROCUREMENT_API_CONTRACT_VI.md) owns retained computation.

## ĐÃ CHỐT / CURRENT FACT — explicit field-value sources (10/10/2026)

M04 thêm `{resolution:{kind:"shared_value",target_field,scope:"PROFILE_CONSTANT"|
"IMPORT_VALUE",value:<strict scalar|null>,evidence_reference,
replace_source_column_index?:integer|null,acknowledgment?:boolean}}`, same route/ID.
Value bắt buộc có mặt (null chỉ nullable). Scope field allowlist/scalar-only;
source column conflict409 nếu chưa explicit switch đúng index + acktrue. TargetRequest
chọn lại column bỏ shared rule/value, không silent precedence.
M03 FieldOption thêm allowed_shared_scopes và input_sources shared_value;
M01/I04 SheetInfo shared_field_bindings/import_values; ProfileSpec chứa constants
hoặc import-value requirements, không batch-varying values. Version field_value/1.
Preview FieldProvenance thêm value_source/index/declaration_id. Các request/status/
headers hiện hành giữ nguyên; không endpoint mới, storage JSONB0013 không migration.

Profile/rule edits giữ N5 Owner approval. Value edit dưới approved IMPORT_VALUE
rule chỉ mapping.propose/current rights + explicit review, không activate profile.
Reuse thiếu import value chặn preview MISSING_IMPORT_VALUE; mỗi import confirmation
riêng. Shared values không Qwen-generated/sent; typed rows và business checks giữ
nguyên. Contract chi tiết/example/allowlist:
[feature](features/IMPORT_FIELD_VALUE_BINDINGS.md),
[freeze/evidence](runbooks/FULL_TEST_FLOW.md).
Các absence statements về scalar context trong phần inventory bên dưới là
HISTORICAL INFORMATION trước extension này; generic/nested injection vẫn unsupported.

## ĐÃ CHỐT / CURRENT FACT — descriptors và nguồn fields

M03 FieldOption bổ sung `nullable:boolean`, `input_sources:[excel|binding]`,
`input_help:string`; giữ `requiredness:required|optional` để không đổi row contract.
`required + nullable=true` là required-nullable, không được bỏ field. Các references
hiển thị tên/mã nghiệp vụ, có thể resolve bằng identity binding đã duyệt; Excel
không cần chứa UUID. Binding hiện resolve token trong cột; không generic row constant.
Store/actor/file IDs/profile versions và semantic/parsing context không phải cột
business bắt buộc. Không tự điền date/unit/currency/zero từ context chưa hỗ trợ.
Chi tiết đủ fields, validation, writer và gaps:
[inventory](features/IMPORT_SCHEMA_INVENTORY.md). Opening_stock Excel đã nối writer N6;
Actual receipt Excel đã triển khai C3 tại mục16; A2 purchase history là record-only riêng.
Không map các nhóm này sang inventory_count.

## ACCEPTED DECISION / CURRENT FACT — A2 recorded support domains

A2 thêm `calendar_events`, `promotion_observations`, `usage_history`,
`purchase_history` vào registry typed hiện hành. Chúng **history-only**, không phải
nguồn forecast feature, recipe facts, stock movement, actual receipt, committed
inbound hoặc current supplier term. H01/H02 thêm category `calendar`, `usage`,
`purchase`; promotion thuộc `sales`. I04 preview và I06 completion đọc typed payload,
provenance và immutable revision; không thêm endpoint. H01 là lịch **upload**, không
phải business calendar. `RECORDED_HISTORY_ONLY` luôn cảnh báo giới hạn consumer;
calendar có thêm `CALENDAR_NOT_FORECAST_FEATURE`. Không tuyên bố forecast cải thiện.

Schema/OpenAPI sở hữu fields; [inventory](features/IMPORT_SCHEMA_INVENTORY.md) mô tả
dictionary. Mỗi row cần source record key ổn định và evidence; thiếu key không suy
từ filename/tên/ngày hoặc tự cộng hàng. Identity chung là Store + domain + approved
source_system_key + report_type + source_record_key. Immutable business grain:
promotion Product/day, usage Ingredient/day, purchase Ingredient/Supplier; sửa
grain bị SOURCE_IDENTITY_CONFLICT, cần đúng identity mới. Calendar giữ event source
identity và cho correction period/name có evidence. Không merge bằng tên, không
delete records vắng mặt, không áp contribution summing của sales. Duplicate cùng
identity trong batch bị DUPLICATE_HISTORY_IDENTITY, khác facts bị
CONFLICTING_HISTORY_IDENTITY; toàn batch blocked. Exact numeric spellings tương đương
không tạo correction. Reimport cùng identity/facts là NO_OP, facts đổi tạo append
revision, không UPDATE lịch sử cũ.

Correction preview là `CORRECT_HISTORY_RECORD`, confirmation_required=true và
expected_version. I05 commit cần reason và `history_corrections:[{row_id,
expected_version,reason}]` khớp đúng toàn bộ corrections; thiếu/dư/trùng bị
HISTORY_CORRECTION_UNRESOLVED, stale version/read set bị PREVIEW_STALE. Confirm review
không thay confirmation riêng này. Permission/revision pin/retirement/read-set fence,
atomic transaction/receipt/audit/retry giữ cơ chế hiện hành. Profile reusable chỉ giữ
structure/approved exact semantics; quantities/prices/dates/observations không là
PROFILE_CONSTANT. IMPORT_VALUE là fact mới của batch, không reuse value.

Calendar là Store event được khai báo: inclusive period, declared_at aware không
vượt server now, nullable strict closed/holiday, tên không suy bool/uplift/discount.
Event tương lai đã khai báo được lưu; không inject feature vào model/artifact cũ,
không đổi capture /1 hoặc /2. Promotion là observation Product/day, ngày không tương
lai, applied true/false/null độc lập với nullable name; name không tự là true.
Usage là actual recorded quantity>=0 và exact Ingredient base_unit, usage_date,
observed_at aware hoặc explicit null. Known timestamp phải đúng usage_date trong
timezone Store và không tương lai. Không suy waste/loss từ chênh BOM, không reconcile
hoặc sửa recipe tự động. Purchase có order_date/received_date nullable riêng và
report_date bắt buộc; ngày quan sát không tương lai hoặc sau report_date; known
receipt không trước known order. Không học lead time, phí, expiry hay promote term.

Purchase price cần explicit `PER_QUANTITY`, `LINE_TOTAL` hoặc `UNKNOWN`.
PER_QUANTITY cần positive denominator quantity và unit; LINE_TOTAL không denominator;
UNKNOWN buộc price/denominator/unit null. Explicit zero price khác unknown. Canonical
money exact Store currency, không FX/truncation. Reviewed physical conversion scale
purchase quantity **và price denominator**, giữ price amount/line total nguyên nghĩa;
không tự áp density hoặc chia để làm tròn unit cost. Raw source giữ trong provenance.

A2 quyền theo quyết định Owner: import.commit **và quyền ghi miền**; preview/readback
cần quyền đọc miền. Calendar dùng calendar.read/write, usage dùng
usage.history.read/write, purchase dùng purchase.history.read/write + ingredient.read
+ supplier.read; mọi response/operation có purchase history cần procurement.cost.read,
thiếu thì whole denial. Promotion dùng menu.read + sales.read và sales.record.
Corrections vẫn cần quyền ghi và reason/explicit confirmation. Catalogue
permissions-v3/43 keys do [Authorization](AUTHORIZATION_CONTRACT_VI.md) sở hữu;
không tự grant Staff, không inventory mutation, Owner profile approval không cấp
quyền commit. Current rights kiểm lại acceptance/worker/replay/retained read.

Constraints A2 tái dùng typed scope_declarations.PROCUREMENT_CONTEXT: exact supplier
limits ONE_ORDER_SUPPLIER_INGREDIENT, capacities POST_RECEIPT_PRE_EXPIRY_PRE_CONSUMPTION,
fee coverage và current Planning budget/requirements. Consumer chỉ gọi supported khi
capture và exact validator enforce. Hard limits khác customer requirements/fairness/
winner policy; A2 không đổi objective/selector. MIN_SAFETY_STOCK lưu ở business schema
nhưng semantics chưa accepted: execution blocked và R01 báo
MIN_SAFETY_STOCK_UNSUPPORTED trong computed Ingredient/horizon scope, kể cả value0.
Open PO PRESENT_UNSUPPORTED, unknown constraints/fees/budget, tax/tier/priority và
arbitrary tabular rules không silently ignore/default. Business notes/evidence là
metadata, không điều kiện solver. Unsupported sheet/column cần resolution hoặc
explicit IGNORE với acknowledgment, không fake ready.

CURRENT FACT: advisory input projection sheet_profile/2 uses compact supported field
metadata (type/required/nullability/aliases/conditions), not whole FE descriptors;
mapping_prompt/3 distinguishes four history-only types from stock/forecast facts.
Output sheet_suggestion/1,96KB request cap, ≤8 samples, finite attempts and strict
supported-target validation remain unchanged. All data stays advisory; no real
provider was called for A2 acceptance. Targeted DB acceptance verifies retained
readback and mutation boundaries; whole browser flow is not evaluated.

## ĐÃ CHỐT — bổ sung classification/review theo task ngày10/10/2026

Giữ toàn bộ routes/IDs. M04 thêm resolution `{kind:"sheet_type",sheet_type:<schema>
|null,ignored:false|true,acknowledgment:false|true,reason}` trên classification
mapping_id. Ignore whole sheet cần ignored=true, sheet_type=null, acknowledgment=true.
Unknown không tự là IGNORE. Đổi loại bỏ targets ngoài schema mới, invalidate pins/
preview/confirmation; cần Owner duyệt proposal mới, không sửa active version.
Mapping cột explicit có origin MANUAL/confidence=null; reused có REUSED/profile_ref.
M04 được sửa trực tiếp reused column: fork proposal giữ approved context/rules,
invalidate preview/confirmation, Owner phải duyệt version mới; không sửa active spec.
Rule/model confidence là heuristic/self-score, không xác suất/approval/data readiness.

M01 sheets[] thêm selected_type/suggested_type/classification_origin/confidence/
ignored/ignore_reason. M02 full indexed mapping vẫn được đọc bằng review_only=false;
thêm issue_type=classification, suggestion_origin/confidence/ignored; source-column
indices zero-based phân biệt header trùng. M03 schemas[] cùng descriptor authority
SOURCE_MODELS: nhãn, mô tả, aliases, requiredness/conditional requirements, unit và
value_role canonical_candidate/resolve_only/source_only/unsupported. Nullable value
không có nghĩa column optional. Mapping không hứa mọi field thành DB column.

I05 thêm phase=confirm_review, HTTP200 synchronous staging-only:
`{phase:"confirm_review",preview_id,preview_digest,mapping_revision,confirm:true,reason}`.
Session/Origin/CSRF/UUID Idempotency-Key/If-Match import_revision hiện hành.
Current import.commit và mọi required_actions của preview cần đủ; Owner profile
approval không thay confirmation hoặc grant quyền. Response ConfirmationResult gồm
confirmation_id, exact content-bound source/file-set/mapping/pins/preview/read-set,
actor/time/reason/digest, import_revision mới; canonical_commit_supported theo
chín schema adapters hiện hành (không phải guarantee current commit acceptance).
Retry cùng operation không yêu cầu review mới, nhưng vẫn kiểm quyền hiện hành.
Confirmation review không resolve thay sales replacement/merge/supplier confirmations
riêng trong commit body. Confirm_review vẫn không canonical writes; phase=commit
đã hỗ trợ202 trong phạm vi S4.5, unsupported schemas409 SCHEMA_BLOCKED.

I04 thêm review_confirmation|null và confirmation_usable. Mapping/type/context edits,
preview mới/stale, retired pins hoặc current required rights thiếu làm unusable.
Retained audit/receipt không bị viết lại. Mỗi import mới, kể cả reuse, phải review
và confirmation riêng; S4.5 consume/recheck current permissions/read-set trước
atomic write. Confirmation không guarantee operational facts không đổi sau read.

CURRENT FACT: Qwen adapter cố định `qwen/qwen3.5-9b`, chỉ proposals indexed type/
targets. Cần `IMPORT_LLM_SUGGESTIONS_ENABLED=true` và key; mặc định OFF. Approved
exact unique Store profile reuse không gọi provider; rule trước, phần chưa gán mới
có thể dùng model. Không thay type/target rules đã xác định hoặc duplicate ambiguity;
không gửi sample cells của target rules đã biết. Semantic ambiguity chưa có target
được đề xuất candidates/reason; duplicate ambiguity vẫn cần người xử lý.
Headers/cells/README là dữ liệu không tin cậy, không phải chỉ dẫn. Off/no-key/timeout/invalid output
giữ manual flow. Tối đa hai sheet/batch, hai transport attempts/sheet. Một live
gateway probe POS demo đã validate đề xuất SLX; không phải guarantee chất lượng
model hoặc browser end-to-end. Live calls chỉ trong approved model/data/calls/cost scope.
Không dùng filename làm source-system authority, không rows rewrite/entities/
conversions/catalog gửi LLM. Chi tiết ở [feature](features/IMPORT_STAGING_PREVIEW.md).

ACCEPTED DECISION theo phạm vi import người dùng duyệt: auto-proposal khác approval.
Owner đọc toàn spec qua M01 `include_profile_details=true`, toàn cột qua M02
`review_only=false`, rồi N5 `approve_activate` với revision/reason. Không cần M04
riêng từng cột RULE không mơ hồ khi proposal đủ required fields, source context,
classification và identity/conversion/blockers. QWEN, duplicate, unknown target,
date convention chưa rõ và missing facts vẫn cần M04; không điểm confidence nào
miễn điều kiện này. Staff có thể đề xuất theo grants nhưng N5 vẫn Owner-only.

CURRENT FACT: M01/I04 SheetInfo thêm header_row/preamble_rows/preamble_samples;
samples tối đa1000 ký tự/dòng để review cùng source file, raw đầy đủ giữ staging.
M02 MappingIssue thêm
suggestion_reason/candidate_targets/model_reason và field_category A/B/C/D,
suggested_ignore; giữ indices/status/routes. A là supported alias/target, B là
semantic/date ambiguity, C là chưa có target/workflow, D là informational README
hint. D chỉ đề xuất ignore, không tạo IGNORE; ignore cần M04 và reason.
SheetInfo có excel_date_system và safe suggestion_diagnostic (status, model,
prompt/schema version, input digest, attempts, usage nếu provider trả về,
HTTP status/failure stage/code; không key/raw response/sample). Header detection
chỉ tìm trong tám dòng đầu, không vượt qua dòng đa cột để bỏ dữ liệu. Raw preamble
giữ riêng trong staging; dữ liệu không bị sửa. Scope đã khai báo có active profile
nhưng structure hoặc semantics không khớp sẽ báo PROFILE_STRUCTURE_OR_SEMANTICS_DRIFT;
không bind sai version hoặc sửa profile cũ. Header reorder là drift: indexed mapping
không tự remap. Signature XLSX có workbook epoch; profile XLSX duyệt trước khi có
epoch cần review lại một lần, không sửa retained version.

ACCEPTED DECISION trong slice này: M04 source_context.date_format=EXCEL_SERIAL là
khai báo rõ để tạo normalization theo workbook epoch 1900/1904 rồi Owner duyệt.
Chỉ áp dụng date fields sales_date/effective_from/effective_to; không biến ngày
kiểm kê thành observed_at hay tạo receipt timestamp. CURRENT FACT: giữ numeric raw,
preview dùng exact deterministic conversion với provenance; serial60 của1900,
fractional time, giá trị ngoài phạm vi bị block. CSV thiếu workbook epoch bị
EXCEL_DATE_SYSTEM_REQUIRED. Styles không tự quyết định semantics.

<a id="flow"></a>
## 2. Policy đã chốt và luồng khách dùng

1. Khách chọn business context date, files → I01 draft → I02 nhận bytes. Upload
   không ghi Product/Ingredient/Sales/Recipe/Inventory. Chưa upload thành công không
   phải nhập thành công. FE không parse workbook để tự canonicalize.
2. I03 seal file set, discover schema → thử approved Store/source/report mapping
   và deterministic rules trước. Khớp profile thì apply đúng version, không LLM,
   không duyệt lại mapping. Unfamiliar structure/identity/conversion tạo issues.
3. M01/M02/M03 hiển thị exceptions; M04 sửa **proposal**. LLM chỉ gợi ý phần mơ hồ,
   không approval/activation/facts. Provider unavailable vẫn làm được known profile
   và manual proposal. High confidence không thay quyền Owner.
4. Owner đọc toàn proposal (structure/identities/aliases/conversions), quyết định
   approve_activate hoặc reject; activation không commit file. Active version cũ
   không bị proposal mới/file mới ghi đè. Owner cũng có thể retire active profile.
5. Product/Ingredient chưa có được đề xuất identity + metadata rõ ràng để Owner
   duyệt; preview liệt kê CREATE_PRODUCT/CREATE_INGREDIENT, không tạo từ tên lạ.
   I05 phase=preview dùng file bytes + mapping versions đã bind, normalize/validate
   với DB snapshot → I04 đọc immutable preview + blockers/warnings/before/after.
   Ordinary invalid data không tự sinh mapping version hoặc gọi LLM sửa facts.
6. Khách có toàn quyền ghi các nhóm yêu cầu, xác nhận preview và sales resolution
   nếu có → I05 phase=commit. **Atomic toàn batch**: blocker bất kỳ thì không ghi
   nhóm/dòng nào; không partial_success v1. I04/J01 đọc trạng thái; I06 chỉ durable
   completion. Không silent omit rows hoặc groups thiếu quyền.
7. FE refetch Menu/Kho/sales availability/readiness liên quan sau commit. Không tự
   forecast/train/plan/stock depletion; retained Run cũ không đổi.

Mapping reuse không bỏ preview/commit confirmation. Quyền approve mapping khác
quyền ghi dữ liệu; Staff có write vẫn không được activate; Owner approve không
grant write cho Staff. Mapping content change cần version mới, không edit active.

<a id="endpoints"></a>
## 3. Đối chiếu endpoint gốc

Tất cả route tương đối `/api/v1`. GIỮ ID/route gốc khi phù hợp; bảng là DESIGN.

| ID/route từ FE | Giữ/gộp/sửa/bỏ/thêm | Lý do |
| --- | --- | --- |
| I01 POST /stores/{store_id}/imports | GIỮ | Tạo draft ngày/business context, không business writes. |
| I02 POST /imports/{import_id}/files | GIỮ, rõ immutable bytes/hash | client_file_id retry; per-item byte acceptance khác atomic canonical commit. |
| I03 POST /imports/{import_id}/analyze | GIỮ, SỬA body seal | Explicit accepted file set/ack rejected uploads; deterministic apply rồi exceptions. |
| I04 GET /imports/{import_id} | GIỮ, GỘP read preview/proposal inspection | include_preview + preview_id/rows pagination; không thêm GET preview trùng resource. |
| M01 GET /imports/{import_id}/mapping-summary | GIỮ, SỬA | Progress + bindings/profiles/approval blockers; include_profile_details cho Owner review đầy đủ. |
| M02 GET /imports/{import_id}/mappings | GIỮ, SỬA issue types | Columns/identity/alias/conversion exceptions; successful pairs read-only. |
| M03 GET /imports/{import_id}/sheets/{sheet_id}/field-options | GIỮ, SỬA descriptors | Server schema support/requiredness; unsupported targets không advertised writable. |
| M04 PATCH /imports/{import_id}/mappings/{mapping_id} | GIỮ, SỬA semantics | Confirm proposal value, không approve/activate; CAS import revision, typed per issue. |
| I05 POST /imports/{import_id}/process | GIỮ, SỬA phase preview/commit | Một processing route cho validate/preview rồi commit explicit; không endpoint mỗi stage. |
| I06 GET /imports/{import_id}/completion | GIỮ | Committed impact, source versions/audit refs; no-op completion riêng outcome. |
| H01 GET /stores/{store_id}/imports/calendar | GIỮ | History aggregate distinct batch theo uploaded time, cùng filters H02. |
| H02 GET /stores/{store_id}/imports | GIỮ | Paginated history, không file explorer. |
| R01 GET /stores/{store_id}/readiness | GIỮ ID/route | Canonical action readiness tại mục14; không compute engine trong GET. |
| J01 GET /jobs/{job_id} | GIỮ, shared job mục14.5 | Poll import/PDF; Planning Run vẫn C03 cùng run_id. |
| Không có trong FE | THÊM POST /stores/{store_id}/mapping-profiles/{profile_id}/decisions | Owner quyết định toàn version, activation/rejection/retirement atomic; M04 từng issue không đáp ứng authority/profile lifecycle. |

Không CRUD profiles theo bảng DB. Proposal chỉ phát sinh từ analysis exceptions;
M01 cho biết profile/version đang dùng và proposal để review, không cần dashboard
profiles/list/edit mới. Không API tải/xóa file hoặc undo-import tự động. Không bỏ
endpoint gốc; chỉ **1 route mới** có workflow cụ thể.

<a id="states"></a>
## 4. Identities, versions, provenance và states

Types ResourceId/Version/MoneyText/Timestamp/BusinessDate/envelope theo Planning;
QuantityText/LossRateText theo Catalog. IDs UUID canonical lowercase; display_number
chỉ UI. Exact parsed decimals không floats/exponent suy diễn. Batch JSON≤64KiB;
GET pagination limit default50/max100; cursor bound scope/filter/version, stale409.

| Identity/version | Ý nghĩa / không được thay bằng |
| --- | --- |
| import_id/import_revision | Resource batch và CAS revision; không mapping profile version hoặc filename. |
| file_id/content_digest/client_file_id | Immutable uploaded bytes + SHA-256 verified; client retry intent; filename chỉ display. |
| file_set_version | Revision opaque của file evidence/receipt set: new-key I02 kể cả rejected/client-ID replay có thể đổi; same-key replay không đổi thêm; I03 seal không tự đổi version. Không phải count hoặc chỉ accepted-set version. |
| analysis_id | Một execution sealed source set; retry không phát minh source columns mới. |
| sheet_id/source_column_id | Physical sheet/column identity thuộc immutable file/analysis; source_column_index zero-based. CSV virtual sheet. |
| mapping_id | Issue/binding object để M04 cập nhật proposal; không active profile ID. |
| profile_id/profile_version | Store/source/report profile và immutable version đã reviewed; content digest/audit khác mutable proposal_revision. |
| proposal_revision/mapping_revision | CAS proposal và import-wide bindings revision, không profile integer version. |
| preview_id/preview_digest | Immutable intended operations + source set + mapping binds + DB expected versions + policy version; không canonical write receipt. |
| commit_id/job_id | Durable commit attempt và async execution; job ID không business identity. |

Batch status: draft→uploaded→analyzing→review_required hoặc ready_for_preview→
previewing→preview_ready/blocked→committing→completed/completed_with_warnings.
Technical execution failure=failed; retained diagnostics và nguồn vẫn đọc được.
blocked là business blockers, không giả completed. Retry job mới có attempt/job ID
mới, nguồn immutable; batch terminal committed không process thêm dữ liệu.
I04 trả allowed_actions để FE không suy actions từ status đơn lẻ.

File upload_status=uploaded/rejected; parse_status=not_started/parsed/failed;
file processing outcome không đồng nhất với upload accepted.
Job status=queued/running/completed/failed, progress=null nếu không biết; terminal
GET200 với structured job error nếu job failed. queued chỉ sau durable acceptance,
running restart interrupted phải reconcile commit receipt trước failed/retry.

Profile lifecycle: proposal→approved immutable version; active pointer riêng,
approved version có thể superseded/retired (content không sửa); reject không active.
M04 mapping_status=auto_mapped/resolved/needs_confirmation/ambiguous/unmatched;
resolved chỉ proposal resolved. Auto_mapped chỉ bindings lấy từ approved version,
không LLM confidence. Global complete khác Owner approved khác can_preview khác
can_commit; không đổi progress green thành permission grant.

<a id="mapping"></a>
## 5. Store profile, reuse và Owner approval

ACCEPTED DECISION: Profile scope={store_id,source_system_key,report_type,schema_version};
schema fingerprint có sheet/table role, headers/column types và layout declaration.
Signature chỉ chứng minh cấu trúc, không chứng minh source/semantics, entity identity
hoặc hai contributions bán hàng độc lập. Nhiều profile **khác nguồn** cùng signature
là hợp lệ; không chọn arbitrary/first/latest/confidence khi context chưa phân biệt.

ĐÃ CHỐT bổ sung S4.4: source context thuộc proposal của profile cho một cấu trúc
nguồn/sheet, không phải tên file hoặc identity từng upload. `source_system_key`
và `report_type` là mã ổn định, case-sensitive trong Store, 1..128 ký tự
`[A-Za-z0-9][A-Za-z0-9._:-]*`. Người có mapping.propose được khai báo; chỉ Owner
duyệt cùng toàn spec trước activation. Client declaration là evidence do người
dùng cung cấp, không phải nguồn đã được hệ thống xác minh. Mã đã duyệt được tái
dùng; không tự phát sinh mã từ filename/header, UUID upload hoặc LLM. Matching
approved context/profile chính xác và duy nhất thì không nhập lại/không LLM.
Nhiều profile khớp hoặc context mâu thuẫn trả PROFILE_MATCH_AMBIGUOUS hoặc
SOURCE_IDENTITY_CONFLICT; không tự chọn. Context change tạo proposal revision mới,
invalidate analysis bindings/preview usability của batch; không sửa immutable
approved version hoặc retained preview cũ.
Matching theo approved rules, không filename hoặc fuzzy name identity. Nếu nhiều
profiles matches với semantics khác nhau thì PROFILE_MATCH_AMBIGUOUS, cần người
có mapping.propose làm rõ; sửa reusable semantics vẫn cần Owner approval. New draft
profile không active vì first import. Không bắt popup xác nhận nguồn mỗi lần: dùng
lựa chọn người dùng hoặc workflow/declaration đã xác lập cho **nguồn batch này** có
provenance; profile cũ đã approved không tự chứng minh file mới cùng nguồn.

<a id="source-reuse"></a>
### 5.1. Source declaration → candidate → compatibility → row validation

| Bước/operation hiện hữu | Fields/FE và giới hạn authority |
| --- | --- |
| I01/I02/I03 | I01 chỉ data_date, I02 chỉ bytes/client_file_ids, I03 chỉ seal file set/ACK; chưa có source picker field ở ba request này. filename/client_file_id/file hash không source identity. |
| M01/M02 | M02 issue_type=source_context có mapping_id; M01 sheets/profile_proposals/approved_contexts/approved_profiles và binding_refs cho FE biết declared scope/pins. include_profile_details=true để xem full spec; M02 review_only=false đọc đủ issues, không chỉ page samples. |
| M04 PATCH /imports/{import_id}/mappings/{mapping_id} | Resolve đúng source_context issue bằng SourceContext: source_system_key, report_type, evidence_reference, semantic/parsing declarations theo DTO. Có mapping.propose/current sensitive reads; Origin/CSRF/If-Match mapping_revision/Idempotency-Key như mục9.2. Không source endpoint mới. |
| N5 | Owner approves exact reusable spec/source provenance; không xác nhận mọi file/report cùng nguồn, không command correction/commit. |
| I05/I04/I06 | Preview dùng declared context+approved pin, row identity/domain validation và captured read-set. I04 preview/current usability cho FE review; I06 chỉ báo durable commit sau completion, không profile approval success. |

Ví dụ request M04 SourceContext (không chứng nhận tự động từ header):

```json
{"resolution":{"kind":"source_context","source_system_key":"POS-A","report_type":"sales-daily","evidence_reference":"staff-declaration:POS-A:daily-export","sales_semantics":"disjoint_contribution","inventory_semantics":null,"decimal_locale":"dot","date_format":"ISO"}}
```

ACCEPTED DECISION: candidate lookup chỉ tìm tập approved active/nonretired trong
Store + declared source_system_key + report_type + compatible schema/version.
Compatibility kiểm selected schema, indexed headers/layout/epoch, declared parsing/
unit/basis/sales semantics và profile drift; unique candidate chưa đủ nếu semantic
declaration conflict. Sau compatible reuse vẫn đọc rows mới, resolve references/
reservations, validate current facts, quyền và business correction. Không reuse
commercial values, recipe facts, source report key hoặc confirmation batch cũ.
Rules/Qwen có thể đề xuất context, không attest source. Chỉ signature/context
absent/untrusted/ambiguous phải làm rõ trước bind; không search/fuzzy engine mới.

CURRENT FACT — source-before-reuse trong source tích hợp, kế thừa guards lát3 và
acceptance Import126b0f2/A3 (không chứng nhận server/release đang chạy): I03 không có attested source
context nên analyze chỉ discover/candidate, giữ source_context unresolved kể cả
chỉ một profile cùng signature. Metadata columns chỉ phát hiện conflict, không
positive source proof; không copy source evidence của version cũ vào file mới.
Signature cũng không còn là điều kiện skip provider; semantic proposals vẫn opt-in,
không attest nguồn. M04 SourceContext lưu declaration/evidence/actor của batch,
lọc Store+source_system_key+report_type+signature, kiểm compatible declarations/
recipe/supplier basis rồi bind unique active/nonretired version. Nhiều candidate
không phân biệt được trả PROFILE_MATCH_AMBIGUOUS; source chưa rõ không bind/preview.
_bindings kiểm source declaration + actor + exact scope trên pin khi preview/confirm/
commit/worker; pending artifact chỉ có signature không source proof trả
SOURCE_CONTEXT_REQUIRED. Summary báo đúng source blocker, không giả retirement.

CURRENT FACT trên routes hiện có, không operation/DTO field mới: FE dùng M02
source_context issue rồi M04 khai báo/chọn nguồn, không N5 lại nếu spec unchanged.
Classification/column review compatible trước source declaration không tự làm
đổi spec; genuine draft edits giữ approval path. Context đã resolve trong batch
không bị hỏi lại để preview/commit. I03 vẫn chưa nhận established context/provenance
trước analyze; không suy nguồn từ filename, signature hoặc client trust flag.

Trước preview/commit FE hiển thị scope nguồn/report + evidence do ai khai báo,
profile_id/version/content_digest/reuse-or-new, schema và semantics/basis đang áp,
source/report contribution identity, unresolved blockers/warnings và planned effects.
Nguồn lấy từ M01 details/SheetInfo, M02 source_context resolution và I04 preview
provenance; không suy source từ filename hay màu auto_mapped. Context/source declaration
đổi làm mapping/proposal revision đổi, remove affected binding, confirmation unusable;
preview cũ retained nhưng không commit được. Phải compatible lookup/reapproval khi
spec đổi rồi preview/confirm mới; source/dependency đổi ở commit trả PREVIEW_STALE.

### 5.2. Interpretation, entity binding và batch facts

ACCEPTED DECISION: tên món mới không tự chứng minh structural profile sai. Tách
reusable interpretation (columns/grain/conversion), Store entity binding, authorized
creation và current batch facts/effects. Canonical Product/Ingredient/Supplier UUID
đã biết và đúng Store có thể đi qua profile cũ mà không sửa spec; rows vẫn validate.
Thay quantity/price/date/source report fact ở rows không tự là mapping-spec change.
Không tự match spelling, merge gần tên hoặc tạo entity từ tên chưa xác lập.

CURRENT FACT: ProfileSpec **hiện chứa** identity_rules/aliases/entity_proposals và
reserved_canonical_id/metadata/approval_revision. Sau M04 source selection, approved
spec được pin và row identities được resolve lại. Canonical UUID đúng Store hoặc
alias/reservation đã approved dùng spec cũ; unknown token giữ identity issue và
chặn preview, không tự fork draft chỉ vì file có entity mới. M04 identity_binding/
new_entity_proposal thêm alias/binding/reservation vào spec sẽ fork draft, giữ
base_spec và source declaration/evidence của batch hiện tại; proposal/lifecycle/
mapping revisions mới cần N5 approval. Đây là spec change thực theo storage hiện
hành, không kết luận columns cũ sai. Đổi target UUID/alias/source_business_key/
metadata/unit/reservation hoặc interpretation/conversion/PROFILE_CONSTANT cũng
thực sự đổi spec. IMPORT_VALUE chỉ batch facts, không reusable constant.

Không có batch-only identity approval store thứ hai hoặc separate creation command
trong clarification này. New entity cần explicit metadata/Store binding/declarations,
Owner-reviewed reservation như mục6.1 và current product.create/ingredient.create/
supplier.create cùng domain write rights. N5 không grant quyền cho Staff, không
approve overwrite metadata existing hoặc facts tất cả rows; người nhập phải tiếp
tục preview/resolutions/confirm_review/commit. Row validation/dependencies quyết
batch effect; mapping queue không giải business data conflict thay người nhập.

ProfileSpec REQUIRED:

```text
scope: {source_system_key, report_type, schema_version}
structure: {sheet_roles[], header_rules[], schema_signature}
field_bindings[]: {source_column_index, source_header, target_field, requiredness,
  ignored:boolean, evidence_reference, origin, confidence}
identity_rules[]: {entity:product|ingredient|supplier|lot, source_token,
  canonical_id, reference_state:existing|reserved}
entity_proposals[]: {proposal_id, entity:product|ingredient|supplier, source_business_key,
  reserved_canonical_id, metadata, evidence_reference, approval_revision}
aliases[]: {entity, source_token, canonical_id}
normalizations[]: {rule_id, kind, fields[], parameters, provenance}
conversions[]: {rule_id, from_unit, to_unit, factor:{numerator,denominator}, provenance}
sales_semantics: daily_total|disjoint_contribution|null
inventory_semantics: lot_stock_count|null
source_provenance: {declared_by, evidence_references[]}
```

Parameters là tagged typed variants (decimal_locale/date_format/unit_label_alias/
exact_scale), không arbitrary script/expression/eval/Python. Source selectors stable
trong signature, không Excel formula execution. Entity bindings chỉ Store IDs.
Aliases explicit reviewed, tên gần giống chỉ proposal không identity auto match.
Owner có thể sửa qua M04 issues; M01 include_profile_details trả full spec/diff và
evidence, không chỉ vài sample rồi approve unseen rules. Completeness/bounds phải
được verify trước approval; không truncated spec trông như đầy đủ.

Technical normalization: parse declared decimal/date locale, trim source label
theo explicit rule, format adapter không đổi quantity/identity/semantics. Semantic
normalization: source unit→canonical exact factor, per-serving vs whole-yield,
daily total vs contribution, SKU/alias binding; **Owner approval bắt buộc**, không
gắn nhãn “technical” để bypass. Standard factor kg→g=1000 cũng phải khai báo scope;
không mass→volume nếu không evidence factor/meaning. Không conversion currency,
infer density/expiry/lead time hoặc unknown quantity. Loss/units/date thiếu là
blocker đến khi có source hoặc Owner-established documented fact, không giá trị
mặc định tự bịa. Conversion chỉ source promotion, không mutate old canonical units.

Decisions body union approve_activate/reject/retire, Owner-only, require reason:
approve_activate `{decision,proposal_revision,expected_active_version:Version|null,
reason}`; reject `{decision,proposal_revision,reason}`; retire `{decision,
active_version,reason}`. If-Match profile lifecycle revision + Idempotency-Key
REQUIRED; CAS active pointer/proposal toàn version trong một transaction.
Approval reply200 `{profile_id,approved_version,active_version,lifecycle_revision,
decision_id,decided_at,audit_id}`; rejected/retired active_version nullable đúng facts.
Approval không rebind batch khác hoặc commit input đang pending. Staff403 dù có
mapping.propose; không approval token/key tự bypass role. Owner scope đúng Store.

<a id="profile-retirement"></a>
### 5.3. Retirement — giữ command và guards hiện hành

ACCEPTED DECISION / CURRENT FACT: already approved compatible version không reapproval.
Replaced active pointer không tự chuyển pin latest: version cũ **chỉ superseded nhưng
chưa retired** vẫn được pending batch dùng đúng pin, nếu mọi rights/read-set/checks
còn hợp lệ. N5 retire active_version đặt chính ImportProfileVersion.retired=true và
active pointer=null. Fresh lookup chỉ active/nonretired; pending batch pin version
đó cũng bị chặn, không grandfather. _bindings rechecks exact version/digest/Store
và retired ở preview, confirm_review, _commit_preview trước acceptance **và worker
canonical commit**. Trả409 MAPPING_VERSION_RETIRED; I04 giữ preview retained nhưng
stale/confirmation_usable=false và bỏ confirm_review/commit khỏi allowed_actions.

Case: B đã preview/confirm V1; retire V1 trước canonical commit → B không được ghi,
phải dùng approved version còn hợp lệ rồi re-preview/confirm. Nếu chỉ activate V2,
V1 không retired → B không tự chuyển V2, vẫn có thể commit V1 theo guards. B đã
completed V1 → không undo dữ liệu/audit hoặc rewrite historical receipt vì retire.
Retire và canonical commit phải serialize qua current profile lifecycle/transaction
fence: trường hợp chạy race cần acceptance targeted, không tuyên bố đã kiểm race
chỉ từ code read. Durable already-committed replay không thực hiện lại mutation;
current authorization luôn kiểm trước receipt, không dùng replay để ghi lại V1.

Khái niệm A “ngừng dùng cho imports mới” khác B “profile sai, chặn pending”. Command
retire hiện hành có tác động chặn **cả fresh reuse và pending dùng version retired**;
không phải new-only switch. Không thêm revoke action, grace period hoặc hai commands
từ phân biệt khái niệm. Policy/guard hiện tại rõ nên không cần hỏi lại để sửa docs;
nếu sản phẩm muốn A-only phải được duyệt ở scope khác, không gọi technical choice.

<a id="schemas"></a>
## 6. Phạm vi dữ liệu hỗ trợ trong design

Không generic Excel writes mọi bảng. Capabilities public chỉ true khi corresponding
parser/domain-specific boundary/auth/audit/atomic commit đã wired, hiện chưa có.

| Schema/profile | Canonical intent và validation | Phần chưa được phép suy ra |
| --- | --- | --- |
| sales daily_total/disjoint_contribution | Existing Product hoặc new Product đã Owner duyệt tạo trong cùng batch, Store-local date, nonnegative quantity trong selling_unit, source/report identity; policy mục 8. | Retail price/revenue/promotion từ FE không có SalesDaily fields; không tự ghi Product.price hoặc invented history. |
| inventory lot_stock_count | Existing Ingredient + uniquely identified received lot, target on_hand≥0 exact base_unit; COUNT_CORRECTION reason/observation/version. | Không receipt/inbound, tự tạo lot từ batch_id, warehouse table hoặc source total→lot allocation. |
| recipes | Existing hoặc new Product/Ingredient được Owner duyệt tạo trong cùng batch, explicit quantity_basis/version/from/to/yield/loss, unique lines exact base_unit, yield unit=Product.selling_unit. | Không auto-close overlap/retroedit; nhóm entire recipe atomically, không one-row-one-version. |
| new Product/Ingredient identity | **ĐÃ CHỐT**, mục 6.1: Owner duyệt explicit identity/đơn vị/metadata; preview creation; executor có quyền tạo catalog toàn phạm vi. | Không tạo từ tên lạ hoặc mapping confidence, không silently map gần giống; không tạo lot hoặc đổi đơn vị entity cũ. |
| supplier / supplier_terms / payable_fees / scope_declarations | HỖ TRỢ v1 theo mục13; explicit identity/Owner review, typed engine-supported semantics. | Không generic supplier Excel hoặc tự suy fees0; unsupported business rules vẫn blocker. |
| other schemas | UNSUPPORTED_SCHEMA | Không PO/payment/budget/default/saved/forecast/model/Run writes. |

M03 trả descriptors có target key, type, requiredness, unit semantics, support:
supported/source_only/unsupported, available, reason_code. FE dropdown keys giữ
đối chiếu nhưng unsupported destinations disabled. Optional known columns chỉ
source_only/ignored khi Owner-approved spec đã nói rõ; preview hiển thị không
promote. Không silent drop unsupported business fields để claim imported đầy đủ.
Optional unresolved column cần explicit ignore binding Owner-approved hoặc vẫn
exception; missing required field là schema_blocker, không fake source column.

Sales dates và recipe effective dates phải source-known; batch.data_date chỉ
business context, không overwrite row dates hoặc fallback missing dates. Cho phép
historical sales inputs; future actual sales dates BLOCK FUTURE_SALES_NOT_OBSERVED
vì target observed sales, không import hypothetical sales như actual. Inventory
count observation phải current/nonstale: future hoặc backdated count không được
overwrite current stock nếu có intervening movements; block STALE_STOCK_OBSERVATION.
Kỳ/date/time rule phải được khai báo source/profile; ngày snapshot không receipt
date, UTC commit instant không thời điểm kiểm kê được bịa.

CSV UTF-8/BOM, delimiter explicit/detected deterministic rồi verified; XLSX values
không execute macros/external links/formulas; formula thiếu cached established
value blocker FORMULA_VALUE_UNAVAILABLE. File limits kỹ thuật:≤20 files/batch,
≤20MiB/file,≤100MiB tổng actual source bytes của accepted logical files (XLSX archive bytes/CSV bytes),≤200MiB expanded XLSX,≤100 sheets/batch,
≤100k data rows/batch,≤256 columns/sheet; vượt trả resource-limit, không truncate.
CSV virtual sheet; empty sheet báo warning EMPTY_SHEET_SKIPPED và không có canonical
rows, all empty blocked NO_DATA_ROWS. Diagnostics physical worksheet row_number
one-based gồm header rows; CSV logical record_number one-based tách physical line
start/end để quoted multiline không sai vị trí.

### Recipe source basis và canonical whole-yield

ACCEPTED DECISION: `recipes.quantity_basis` là required source semantics, nhận đúng
`PER_SERVING` hoặc `WHOLE_BATCH`. Field không tạo cột canonical mới. Cột nguồn đã map
hoặc M04 `shared_value` đều được phép; PROFILE_CONSTANT dành cho semantics ổn định
được Owner duyệt, IMPORT_VALUE dành cho facts của lần nhập. Header “lượng 1 sp” chỉ
proposal. Không có default basis/yield/loss/unit. Profile lịch sử thiếu basis vẫn
đọc được, nhưng không auto-reuse; `RECIPE_BASIS_REVIEW_REQUIRED` yêu cầu review lại.

CURRENT FACT: sau lexical/date normalization và validation, ingredient conversion
theo exact declared factor; PER_SERVING nhân lượng với yield đúng một lần để tạo
`RecipeValue.lines[].quantity` toàn mẻ. WHOLE_BATCH giữ lượng toàn mẻ. Loss là ratio
`0 <= process_loss_rate < 1`, giữ nguyên ở DB; BOM dùng
`demand * canonical_quantity / yield / (1-loss)`. Không chuyển `20%` thành `0.2`,
không rounding/epsilon. Yield/line >0; loss=0 hợp lệ khi explicit. Missing/null/zero
không thay thế nhau. Exponent không được conversion làm thành lexical hợp lệ.

Yield unit phải bằng Product.selling_unit; output conversion chưa hỗ trợ,
`UNIT_MISMATCH` chặn. Recipe conversion giữa known mass mg/g/kg và volume ml/l bị
`INCOMPATIBLE_RECIPE_UNIT_CONVERSION`; không có density authority. Supported Recipe
ingredient conversions: mg/g/kg trong mass; ml/mL/l/L trong volume; same exact label
với factor1. Factor phải bằng tỷ lệ vật lý exact, sai → `INVALID_RECIPE_UNIT_FACTOR`.
Label khác/packaging/count-label conversion → `UNSUPPORTED_RECIPE_UNIT_CONVERSION`;
chưa có typed packaging/density authority. Mọi conversion vẫn cần Owner review,
khớp Ingredient.base_unit. Không đổi đơn
vị canonical hay dated BOM policy.

I04 preview và I06 canonical references giữ `line_provenance[].quantity_basis` và
`provenance[field].source_value` (raw lexical hoặc scalar declaration trước transforms),
cùng source index/declaration ID/rule IDs. `after` giữ resolved IDs, canonical quantity/
unit, yield, loss, version/from/to; shared declarations và evidence đọc ở M01 full spec
và sheets.import_values. Loss provenance không biến thành quantity đã áp loss.
Field mới nullable/default-null chỉ để đọc retained evidence cũ; không suy basis cũ.

Ví dụ M04 trên bất kỳ mapping_id của sheet Recipe, trước N5 Owner approval:

```json
{"resolution":{"kind":"shared_value","target_field":"recipes.quantity_basis","scope":"IMPORT_VALUE","value":"PER_SERVING","evidence_reference":"Owner xác nhận mỗi 100g là định lượng của một đơn vị bán"}}
```

Khai báo tương tự yield="10", yield_unit="cup", loss="0" (PROFILE_CONSTANT hoặc
IMPORT_VALUE); version=1, effective_from="2026-01-01", effective_to=null chỉ IMPORT_VALUE
nếu không lấy từ cột. Sau N5, I05 preview → confirm_review → commit dùng existing
CAS/rights/read-set/idempotency/atomic batch. Staff không approve_activate. Preview
đã normalize được commit từ retained typed values, không chạy lại transform/provider.

100g/serving × yield10 và 1000g/WHOLE_BATCH yield10 cùng lưu line1000g, demand40 →
4000g. Batch1000ml/yield10/loss0.2 → 5000ml. Readiness chỉ hết recipe gap khi version
bao phủ đủ horizon và lines hợp lệ; sales/kho/supplier/config blockers vẫn độc lập.

Profile reuse kiểm tra từng dòng: column basis/unit mới được đọc lại, sai enum/unit
bị chặn. IMPORT_VALUE luôn yêu cầu declaration mới; PROFILE_CONSTANT đổi cần proposal
mới và Owner approval. Header reorder/header-row/epoch change là structure drift,
không tự remap. Nếu nguồn thay nghĩa mà không đổi cột/giá trị và không khai báo,
backend không thể quan sát thay đổi; dùng IMPORT_VALUE cho basis chưa ổn định.

CURRENT FACT về lịch sử: RecipeUseCases.create_in_transaction không đặt lower bound
effective_from theo ngày hiện tại. Import có thể tạo initial historical recipe từ ngày
nguồn explicit nếu chưa conflict; same version/content NO_OP, khác content hoặc overlap
bị chặn. Không thay ngày nguồn bằng hôm nay. Legacy RecipeVersionService cũng không
cấm initial historical date; nó chặn ngày <= một existing.effective_from và tự đóng
kỳ trước đang mở (ZIP `app/services/recipe_service.py:55–66`). Bản mới không auto-close;
không port policy đó. N21 calendar tương lai là workflow
riêng, không ghép import để đóng/sửa kỳ hay đổi historical Run.

### 6.1. Tạo Product/Ingredient mới qua import — ĐÃ CHỐT

Nguồn approval: người dùng ngày 09/10/2026 cho phép tạo mới “theo các điều kiện
trên”. Owner phải duyệt identity, đơn vị và metadata cụ thể trước activation;
executor cần quyền tạo tương ứng. Staff có thể đề xuất, không tự approve/activate.
Không thêm CRUD/editor endpoint; M04 nhận typed new_entity_proposal trong issue
identity hiện có, M01 trả full proposal/spec/diff để Owner quyết định qua route
profile decisions. Approval chỉ staging identity, không insert catalog.

Product metadata={name,selling_unit,sku:string|null,price:MoneyText|null,
active:boolean}; Ingredient metadata={name,base_unit,sku:string|null,
expiry_tracking:boolean,active:boolean}. Names1..200 có nội dung, units1..32 exact,
SKU null hoặc1..64 case-sensitive unique trong Store/entity namespace; không unique
name. Tất cả keys metadata hiện rõ khi Owner review. Optional SKU/price giữ null;
accepted catalog defaults active=true/expiry_tracking=false nếu được dùng phải
hiển thị với SYSTEM_ASSIGNED provenance, không giả source facts. Unit bắt buộc
established, không bịa từ tên; price source sales không tự là giá niêm yết Product.

Each proposal có source_business_key theo identity rules đã duyệt, reserved UUID
ổn định qua retries, field provenance và approval revision. UUID reserved không
chứng minh canonical row đã tồn tại. References sales/recipes trong preview được
bind tới UUID này, dependencies ghi rõ; commit insert catalog trước dependent
records **trong cùng atomic transaction**, không orphan/partial Product/Ingredient
nếu sales/recipe hoặc nhóm khác failed. Ingredient mới không tự có lot/stock0/expiry
facts hoặc SupplierTerm; inventory snapshot vẫn cần lot có thật đã định danh.

Ví dụ resolution của M04 cho unknown Ingredient (SYNTHETIC, chưa ghi canonical):

```json
{
  "resolution": {
    "kind": "new_entity_proposal",
    "entity": "ingredient",
    "source_business_key": "POS-A:ingredient:SYRUP-MANGO",
    "metadata": {
      "name": "Syrup xoài", "base_unit": "ml", "sku": "SYRUP-MANGO",
      "expiry_tracking": true, "active": true
    },
    "evidence_reference": "source-catalog:SYRUP-MANGO"
  }
}
```

Server cấp proposal_id/reserved_canonical_id/provenance đã verify, không tin client
khai approved/version/actor. Entity type quyết metadata variant, không arbitrary
dict. Proposal sửa source identity/unit/metadata làm approval cũ không usable,
phải Owner review version mới; approved generic structure rule không auto approve
unknown identities xuất hiện ở files sau.

Preview mỗi entity NEW có action CREATE_PRODUCT/CREATE_INGREDIENT, before=null,
after typed catalog fields/UUID, source refs và dependent operations. Required
actions gồm product.create/ingredient.create cho toàn entity set; thiếu quyền hoặc
entity chưa được Owner duyệt block toàn batch. Không grant create từ mapping
approval, không tự chuyển target creation sang update existing entity.

Read-set giữ absence của source identity/SKU/UUID. Concurrent import đã tạo entity
giữa preview/commit → PREVIEW_STALE rollback toàn batch, refresh/reclassify; không
allocate UUID mới rồi duplicate hoặc overwrite entity khác. Retry committed same
identity dùng accepted registry/provenance và NO_OP catalog nếu không đổi facts;
different metadata của existing identity là CONFLICT, không generic catalog upsert.
Tên gần giống/giống hệt không tự bind; Owner phải resolve identity rõ ràng.

<a id="preview"></a>
## 7. Preview, thao tác dự kiến và commit

Preview immutable, gắn source_digest/file_set_version/analysis_id/mapping_revision,
exact approved binding {profile_id,version,content_digest}/sheet và DB read-set
versions/absence predicates. Không lookup latest lúc commit. Mỗi nguồn raw cell và
normalized canonical field giữ provenance SOURCE_EXPLICIT/DETERMINISTIC_DERIVED/
SYSTEM_ASSIGNED/UNKNOWN/AMBIGUOUS và applied_rule_ids. LLM suggestion không origin
accepted canonical. Unknown không zero/false/upload date.

PreviewSummary={preview_id,digest,created_at,source_set_version,mapping_bindings[],
policy_version:"import_mapping_policy/1",mode:"atomic",validation_status:
ready/blocked/confirmation_required,can_commit,required_actions[],groups[],counts,
blockers[],warnings[],confirmed_resolutions_version:Version|null}.
Group={canonical_domain,required_write_action,row_count,planned_insert_count,
planned_update_count,no_op_count,blocked_count}. Counts toàn preview, không page.
Row={row_id,source_location,classification:NEW/UNCHANGED/CHANGED/INVALID/CONFLICT,
proposed_action:INSERT/NO_OP/REPLACE_DAILY_TOTAL/MERGE_DISJOINT_SALES/
COUNT_CORRECTION/CREATE_PRODUCT/CREATE_INGREDIENT/CREATE_RECIPE_VERSION/BLOCKED,
entity_refs,before,after,changes[],
provenance,blockers[],warnings[],confirmation_required:boolean}.
before/after là discriminated domain DTO, không arbitrary canonical dictionary.

Warnings={code,severity:"WARNING",field,entity,impact,message,details}; blocker
severity ERROR với actionable source location/code, không warning che lỗi. Empty
source values giữ raw null/empty riêng; không normalize mất meaning. INVALID khác
AMBIGUOUS classification CONFLICT. Preview flags là data validation, không quyền
ủy nhiệm; actor can_commit đòi current full permissions và confirms hợp lệ.

I05 preview mới sau mapping proposal change không modify preview cũ. Khi commit
request chứa explicit sales resolutions mới, frozen commit plan = preview + resolutions
đã validate; receipt giữ exact effective plan digest, không cập nhật preview ngầm.
DB expected before/source-membership phải vẫn đúng; resolution không bypass race.

ACCEPTED DECISION: Owner profile approval chỉ chấp nhận reusable interpretation/
bindings trong exact spec. Không xác nhận row hợp lệ, business overwrite/correction,
grant Staff write hoặc commit. Người nhập tiếp tục I05 preview → I04 kiểm tác động
+ resolutions theo schema → confirm_review → commit; required rights/facts/version
kiểm lại ở commit. M04 mapping/source/context/PROFILE_CONSTANT changes invalidate
bindings và preview/confirmation; IMPORT_VALUE/declaration change cũng phải revalidate
batch facts; canonical dependency đổi làm read-set stale. Không sửa retained preview
ngầm hoặc coi allowed_actions lúc đọc là authority lâu dài.

Batch có bất kỳ blocker thì chặn **atomic toàn scope**; không bỏ row lỗi tự động.
Explicit IGNORE khác null/empty/unresolved. Whole sheet chọn qua M04 sheet_type với
ignored=true,sheet_type=null,acknowledgment=true,reason, đúng own-uncommitted-Staff
policy CA-020; đây là batch scope choice, không retire approved profile. Optional/
source-only column dùng M04 ignored_optional_field với evidence_reference; required
target không được né bằng ignore, missing required vẫn block ở build_spec/preview.
Nếu ignore là thay reusable field_bindings thì fork spec/Owner approval; không
auto-approved từ suggestion_ignore/README/Qwen. Mọi scope/field/declaration thay đổi
đòi preview/confirmation mới và đánh giá lại completeness **phạm vi còn lại**;
không xóa row thực tế khỏi kho hoặc gọi ignored scope là toàn Store CONFIRMED.
I03 ACK rejected upload chỉ seal source set, không giải business row blocker.

Atomic transaction bao gồm canonical writes + contribution revision/audit + inventory
movements/balance + commit receipt/provenance/status. Fresh-session verified receipt
trước durable completion. Preview0 write và all UNCHANGED commit kết thúc
outcome=no_changes, counts0 updated=false; không tạo correction movement delta0.
Không gọi existing per-row UseCases.commit nhiều lần rồi gọi toàn batch atomic;
transaction orchestration/refactoring là backlog slice riêng.

<a id="business"></a>
## 8. Duplicate, sales và snapshot tồn kho — policy sản phẩm

### 8.1. Đã chốt chống trùng

Tên file không identity. Exact same Store/content bytes cảnh báo DUPLICATE_CONTENT,
reuse stored bytes/provenance; không tự viết lần hai. Content hash chỉ chứng minh
bytes giống, không chứng minh cùng business dataset hoặc độc lập. Profile/source
identity/semantics/version khác không tự no-op toàn file; phải classify lại. Business
record UNCHANGED no write, NEW validated insert; absent file rows không delete.
Same Product/date nhiều dòng không được auto sum: approved report grain phải nói
daily-total (duplicates conflict) hay distinct transactions/contributions có stable
business keys và approved aggregation. Không fuzzy matching hoặc filenames as keys.

### 8.2. Sales — ĐÃ CHỐT câu trả lời người dùng ngày 09/10/2026

“hai bản hoàn toàn khác ... xác nhận gộp ... 205 ... quản lí hoặc nhân viên được
cấp quyền”; “100 cái cũ 5 cái mới ... upsert lên105”. **Không thêm Manager role**:
Owner hoặc Staff có delegated sales action, theo authorization contract.

Hai semantics phải explicit trong reviewed profile, không chọn bằng giá trị:

- **daily_total / updated dataset:** existing total100, replacement105 chứa100 cũ
  +5 mới → preview before100/after105, REPLACE_DAILY_TOTAL. Quyền sales.correct,
  explicit confirmation/reason, source revision/audit; không100+105. Same source
  business key phiên bản mới thay contribution cũ, không create independent source.
- **disjoint_contribution:** canonical before100; source report105 xác nhận là tập
  độc lập → preview after205, MERGE_DISJOINT_SALES. Quyền sales.merge + reason và
  explicit disjoint assertion. Warn SALES_DISJOINTNESS_REQUIRES_CONFIRMATION;
  không pretend backend đã chứng minh independence nếu chỉ human declaration.
- Source scope chưa rõ/overlap hoặc không có stable report/transaction identity:
  CONFLICT, không tự suy “hai file khác”=205. Khách phải khai báo evidence và report
  business reference đủ trace trước resolve; không approve LLM classification.

SourceContribution identity={Store,source_system_key,report_type,business_report_key,Product,date};
reviewed semantic grain yêu cầu unique report/transaction keys, không import_id/
file_id/client_file_id/filename làm business report key. Giữ immutable accepted
source revisions và resulting canonical total. Re-import cùng contribution same
value NO_OP; report đã gộp105 cập nhật110 → tổng trước205 thành210, không315.
Nếu canonical base100 không có retained contribution provenance (legacy/internal
writer), không giả đã biết sources: cần authorized explicit baseline/source
declaration gắn captured row/version/100 trước merge, audit rõ human assertion.
Không tự tạo independent baseline hoặc đếm overlapping source thêm lần nữa.

Daily-total covering toàn ngày và partial contributions không được cộng chung
trừ khi covered-set đã declared/reconciled; conflict phải giữ. Same key/new bytes
update không làm mất old versions. Canonical daily identity Store/Product/date giữ
unique. CURRENT FACT: import_sales_sources.classify_sales và write_plan sales branch
đã classify/replace/merge, append ImportSalesSource revisions và audit trong transaction;
không còn mô tả cả correction writer là insert-only backlog. Source-before-reuse và
multi-file/grain acceptance vẫn là gap riêng, không vì writer có mặt mà đủ proof nguồn.

Evidence tối thiểu: source_system_key/report_type có declaration/provenance của
nguồn hiện tại; business_report_key ổn định định danh đúng **phần report/contribution**,
Product/date/selling unit/grain đã xác lập; biết phiên bản incoming thay phần nào.
Để merge phải khai coverage/phần độc lập, reason/evidence reference đủ trace và
commit SalesResolution={row_id,action:"confirm_disjoint_merge",report_business_key,
evidence_reference,disjoint_assertion:true,reason}. Đây là human assertion có audit, không algorithm
chứng minh disjoint từ source_system_key khác nhau. Correction cùng phần dùng
action:"replace_daily_total",disjoint_assertion:false; report key trùng đúng preview.
Nếu overlap không xác định, retained sources không còn giải thích canonical base,
hoặc chuyển daily_total↔contribution chưa reconcile thì SALES_OVERLAP_UNRESOLVED.
Không đổi namespace/source key để biến bản sửa thành phần mới hoặc lách conflict.

| Trường hợp có evidence hợp lệ | Preview/effect đã chốt |
| --- | --- |
| Cùng phần report100 sửa105 | Replace phần100 bằng105; canonical105, không205. |
| A100 và B105 thực sự độc lập, explicit confirm | Canonical205, MERGE_DISJOINT_SALES. |
| B đã105 sửa110, A vẫn100 | Replace source contribution B, canonical210; giữ A và source revisions cũ. |
| B110 upload lại giống | UNCHANGED/NO_OP, canonical210; không thêm contribution. |
| Source key khác nhưng covered-set overlap/unknown | Blocker; source namespace không disjoint proof. |
| File mới vắng phần/record cũ | Không delete, không zero record vắng, không replace-all. |

CURRENT FACT A1 (PostgreSQL acceptance verified on owned Import test DB): preview lập một effect cho
Product/day và `sales_contributions[]` giữ namespace/report type/key, source quantity,
stockout/update mode, locations và provenance. Same-key exact duplicates collapse;
conflicting values trả SALES_CONTRIBUTION_CONFLICT. Mixed full/partial reports trả
SALES_OVERLAP_UNRESOLVED. Disjoint contributions aggregate không phụ thuộc order;
MERGE_DISJOINT_SALES cần sales.merge và assertion/evidence cho toàn frozen list,
kể cả insert tổng mới. Revision cần sales.correct; không xóa phần vắng. Historical
report_type chỉ recover từ immutable pinned mapping cùng Store; thiếu proof trả
SOURCE_REPORT_IDENTITY_UNRESOLVED. Writer có mặt không chứng minh independence.
Contribution revision đổi quantity/observation vẫn là REPLACE_DAILY_TOTAL, cần
sales.correct và resolution kể cả canonical aggregate không đổi; không NO_OP để
ghi lineage correction ngoài quyền. NO_OP chỉ khi contribution facts cũng unchanged.

ACCEPTED DECISION A1: `sales.is_stockout` là observed Product/day nullable boolean:
true có bằng chứng hết món; false biết không censored; null unknown. Không suy từ
sales0/inventory/projected shortage. Alias value khác true/false cần explicit
`SourceContext.stockout_aliases[]` token/value và Owner review reusable normalization.
IMPORT_VALUE được phép; không PROFILE_CONSTANT cho stockout business fact.

Reimport thiếu observation cần `SourceContext.missing_stockout=quantity_only` giữ
observation cũ của đúng contribution hoặc `not_provided` ghi unknown. Declaration
có evidence chỉ thuộc batch, không profile/N5 nếu spec unchanged. Thiếu lựa chọn
trả STOCKOUT_UPDATE_DECLARATION_REQUIRED; quantity_only chưa có contribution trả
STOCKOUT_QUANTITY_ONLY_REQUIRES_EXISTING_CONTRIBUTION. Mapped blank là unknown, trừ
quantity_only explicit; supplied true/false luôn là fact correction. Aggregate:
true thắng; false khi mọi phần false; unknown+false vẫn unknown. Preview giữ source/
canonical observation, before/after và STOCKOUT_UNKNOWN/CENSORED_SALES_REQUIRES_DEMAND_POLICY.
Completion giữ contribution list; audit giữ revisions/evidence/provenance.
Pending sales preview cũ thiếu typed contribution plan trả SALES_PLAN_REVIEW_REQUIRED;
cần preview/confirm mới, không tự N5 lại nếu reusable spec không đổi. Completed
receipt/replay cũ vẫn đọc nguyên retained outcome, không chạy lại writer.
Migration0019 và fresh-session persistence đã verified trên DB Import riêng;
[ADR-A1](adr/ADR-A1-observed-stockout-demand-policy.md)
sở hữu consumer policy. Import completed không chứng nhận forecast-ready/accurate.

Ví dụ các effects sales đã chuẩn hóa (minh họa dữ liệu nguồn/tổng, không I05 payload):

```json
[{"business_report_key":"B","source_quantity_before":"105","source_quantity_after":"110","canonical_quantity_before":"205","canonical_quantity_after":"210","proposed_action":"REPLACE_DAILY_TOTAL","classification":"CHANGED"},{"business_report_key":"B","source_quantity_before":"110","source_quantity_after":"110","canonical_quantity_before":"210","canonical_quantity_after":"210","proposed_action":"NO_OP","classification":"UNCHANGED"}]
```

### 8.3. Inventory — ĐÃ CHỐT snapshot theo lô đã định danh

LOT-01 current12 L, observed target10 L → preview signed delta−2 L; commit movement
COUNT_CORRECTION +balance10 cùng transaction, bắt buộc reason và observation provenance.
Không “receipt10 L” hoặc overwrite12→10 không movement. Unit đúng Ingredient.base_unit.
Delta positive/negative được theo count policy, target≥0; target=current NO_OP.
Lot lookup bằng explicit canonical UUID hoặc approved external stable key bound
uniquely trong Store; lot_code/batch_id nullable/nonunique không universal identity.
Unknown lot/Ingredient totals/ambiguous mapping BLOCKED, không create/distribute lots.
Files absent lots không xóa/zero lots; count snapshot không full-stock replace-all.
Không sửa cost/received_date/expiry bằng inventory count payload. Sale/depletion
movement sau observation làm count stale, phải re-preview/new observation, không
apply captured delta vào balance đã đổi. Import count không tạo/nhận lô mới;
v1 có N6 riêng trong contract Kho cho lô ban đầu/hàng thực nhận.

<a id="schema-correction"></a>
### 8.4. Identity/correction theo schema — không generic upsert

ACCEPTED DECISION: hai bản cùng business key nhưng nội dung khác mặc định CONFLICT,
không last-write-wins theo row/file/upload order. Chỉ các schema có resolution
nghiệp vụ đã duyệt mới được correction sau preview; nếu không có resolution thì
blocker và hướng dẫn sửa nguồn hoặc tạo batch source scope hợp lệ. Explicit scope
selection không cho bỏ row lỗi tự động trong sealed batch. Preview phải giữ source
locations/normalized_source_quantity/before/after/provenance/action/blockers và
expected versions; commit rechecks read-set, lifecycle/current rights và resolution
set chính xác. Không sửa metadata/recipe/price history immutable để làm import pass.

| Schema/key, scope Store implicit | Reimport/no-op và correction/conflict | Source trace / trạng thái |
| --- | --- | --- |
| products/ingredients: source_system_key + source_business_key bound canonical UUID; SKU chỉ Store-scoped key nullable | Same established identity+same typed metadata NO_OP. Khác metadata ENTITY_METADATA_CONFLICT; unknown binding OWNER_ENTITY_APPROVAL_REQUIRED. Không tên giống=merge, không import update metadata existing. | import_preview catalog branch, write_plan Product/Ingredient insert adapters; identity_rules/entity_proposals như mục5.2/6.1. |
| suppliers: source_system_key + source_supplier_key bound canonical UUID | Same identity/name/active NO_OP; khác metadata SOURCE_IDENTITY_CONFLICT/ENTITY_METADATA_CONFLICT, không supplier name upsert hoặc tự rebind sourcekey. | import_preview supplier/catalog branch, import_configuration_preview, OperationalConfiguration.supplier; SupplierSourceRecord provenance. |
| recipes: canonical Product + integer version; lines Ingredient trong version; effectivity inclusive | Same version/header/normalized complete line set NO_OP; khác content RECIPE_VERSION_CONFLICT, không update version cũ. Version mới không overlap assigned applicability, otherwise RECIPE_PERIOD_OVERLAP; header inconsistency RECIPE_HEADER_CONFLICT, duplicate Ingredient DUPLICATE_RECIPE_INGREDIENT. Thay lịch dùng recipe-calendar commands hiện hữu với future-only guard, không import tự đóng lịch cũ. | import_preview.recipe_groups, write_plan→RecipeUseCases.create_in_transaction; recipe-source basis/whole-yield/loss policy tại mục6 giữ nguyên. |
| supplier_terms: source_system_key + source_term_key; canonical Supplier/Ingredient/version + period | Exact canonical payload/source identity NO_OP; same values nhưng thiếu source provenance có REGISTER_TERM_SOURCE audited, không overwrite commercial facts. Khác source binding SOURCE_IDENTITY_CONFLICT; same key changed phải future dated version với explicit old-period amendment/reason/CAS/confirmation khi cần. Historical backdate/overwrite HISTORICAL_TERM_CORRECTION; overlap TERM_PERIOD_OVERLAP, amendment không hợp lệ TERM_AMENDMENT_CONFLICT. | import_preview TermSource branch, OperationalConfiguration.term/close_term, write_plan REGISTER_TERM_SOURCE; details/basis/term_period_amendments ở mục13. |
| inventory_count: canonical lot_id + Ingredient/unit; observation known | Target balance=current NO_OP, vẫn giữ observation evidence; khác balance signed COUNT_CORRECTION có reason và freshness. Unknown/ambiguous lot block; không tạo lot, nhận hàng hoặc đổi expiry/cost/date. | import_preview CountSource, write_plan→adjust_in_transaction, stock_observation; temporal guards/read-set phải recheck ở commit. |
| opening_stock: source_system_key + source_record_id trong shared N6 receipt ledger | CURRENT FACT source tích hợp kế thừa A3: OpeningSource/OpeningValue, same identity+normalized payload NO_OP/retained lot; khác RECEIPT_IDENTITY_CONFLICT. Lot quantity là physical remainder; newlot + COUNT_CORRECTION baseline0, không historical RECEIPT. Duplicate identity/ambiguous physical lot block. | import_opening_stock.receipt_semantics/write_opening, import_preview opening branch; evidence nhánh thuộc Import126b0f2/A3, gate tích hợp ở FULL_TEST_FLOW, không browser/deployment claim. |
| scope_declarations: source_system_key + source_declaration_key + kind/scoped dependencies | Same payload+same dependency evidence NO_OP; changed declaration/dependencies phải explicit SET_SCOPE_DECLARATION/review, không assume complete từ receipt/count. Kind/Ingredient identity khác DECLARATION_IDENTITY_CONFLICT. | import_configuration_preview, OperationalConfiguration.declaration, post-write declaration_dependency; A3 kiểm canonical dependency digest, evidence nhánh thuộc Import126b0f2, gate tích hợp ở FULL_TEST_FLOW. |
| inventory_receipts actual receipt | IMPLEMENTED C3 mục16; shared N6 receipt identity/writer, không sửa receipt cũ từ new file. Không dùng inventory_count/opening để giả actual receipt. | Excel và form N6 cùng InventoryReceiptRecord; atomic import. |

CURRENT FACT: supplier term duplicate source key/active-period overlap được block;
configuration preview namespace=(domain,source_system_key,key) chặn duplicate trong
batch. Không có chọn winning file endpoint. Recipe assembler nhóm (Product,version),
checks header/duplicate Ingredient/DB version/period và giữ mọi source_locations.
CURRENT FACT — recipe nhiều nguồn cùng version: assembler vẫn nhóm
(Product,version), nhưng group đi qua nhiều sheet/file bị
RECIPE_SOURCE_SCOPE_AMBIGUOUS với source location của các lines và không commit.
Matching headers/source scope/version không chứng minh full report hay split parts;
không union hai full reports có ingredients khác nhau và không chọn winning file.
Single-sheet reviewed report tiếp tục assemble lines với header/duplicate Ingredient/
DB version/period checks. ACCEPTED DECISION — Product 13/10/2026: recipe split-report
assembly qua nhiều file/sheet không thuộc đợt hiện tại. Split-report identity/completeness
declaration hoặc manifest là DEFERRED scope, không là câu hỏi Product chặn bàn giao.
Giữ RECIPE_SOURCE_SCOPE_AMBIGUOUS; không auto-union, last-file-wins, suy grain từ
filename hoặc dùng reason tùy ý để bypass. Quyết định này không đổi single-sheet
assembly hợp lệ, BOM/recipe normalization hoặc các guards đã có evidence.

Supplier trace chưa thấy thiếu guard khiến source key khác payload được silently
overwrite: namespace/source/canonical equality/version/effectivity/period amendment
đã có. Trong scope clarification này cần **bổ sung targeted acceptance** cho same-key
changed payload giữa nhiều files, same-signature different-source và preview/commit
race; không căn cứ code read để yêu cầu rewrite supplier runtime. Source-before-reuse
gap ở mục5.1 là shared orchestration, cũng ảnh hưởng recipe/supplier; phải sửa guard
shared này khi implement, không cho source basis đã đúng che gap nguồn.

Coverage hiện hữu đọc tĩnh: test_import_recipe_basis.py có normalized persistence,
fresh-row reuse, invalid-line atomicity, revoke/dependency guards; test_import_supplier_basis.py
có exact MOQ/price, fresh commercial values, historical profile review, fee dependency
và future-period amendment. Chưa chạy lại và không chứng minh cross-file conflict/source
proof. Lát3 test_import_setup_identity.py/test_import_setup_stock.py đang bổ sung
whole-batch identity/dependency order, opening↔N6 no-op/count/completeness chain;
review source/tests sau khi finalized, không ghi PASS hoặc overwrite WIP hiện tại.

Acceptance cần thêm đúng boundaries: declared-source trước bind (same signature
khác nguồn, absent/multiple contexts), entity mới vs unchanged interpretation,
same-key two-file conflicts ở cả upload orders, recipe full-report conflicting line
sets, sales contribution replacement100→105/205→210/retry, IGNORE requiredness và
completeness scope, retire trước preview/confirm/worker commit. Không full-suite
rerun trong task tài liệu; future implementation chọn tests ảnh hưởng guard/consumer
và fresh-session persistence như AGENTS/FULL_TEST_FLOW.

<a id="wire"></a>
## 9. Endpoint workflow semantics — current approved contract

Các examples SYNTHETIC, không HTTP thực. Success meta={request_id,warnings}; async
thêm poll_after_ms=2000; data nullable chỉ error. POST/PATCH Idempotency-Key UUID
REQUIRED, các CAS headers theo từng trách nhiệm. Actor/Store lấy session/route,
không payload actor. JSON fields lạ422, canonical UUID/date/decimal validate strict.

### 9.1. I01/I02/I03 — draft, upload, analysis

I01 body `{data_date:BusinessDate}` REQUIRED, response201 data={import_id,
display_number,store_id,data_date,status:"draft",import_revision,created_at,
imported_at:null,file_count:0,file_set_version}. Date context không source fact.
I02 multipart `files[]` + `client_file_ids[]` paired, allowed CSV/XLSX sniff; response
200 per-item {client_file_id,file_id|null,filename,type,size_bytes,content_digest|null,
upload_status,error|null}; all rejected422. Accepted bytes immutable, imported_at
set thời điểm first accepted upload UTC, không created/data_date/completion time.
Cannot upload after analysis seal; sửa bytes/tập files tạo new draft, không replace.

I03 body {file_set_version,accepted_file_ids[],acknowledged_rejected_client_file_ids[]};
list phải bằng accepted set, không quietly omit accepted file. Nếu upload có rejected
items FE phải báo và khách acknowledge accepted set; đây là byte scope selection,
không partial canonical row commit. If-Match import_revision, response202 import_id/
analysis_id/job_id/status analyzing. Request trống kiểu FE gốc không đủ guard v1.
Jobs discover→apply approved mappings→exceptions; profile strict reused version
không LLM. Parser failed file là blocking whole accepted batch, không tự bỏ file.

<a id="import-batch-mechanics"></a>
### 9.1a. Batch mechanics và I04 quota — ACCEPTED CONTRACT, 10/10/2026

User đã chốt giữ implementation: nhiều I02 calls trong cùng batch trước seal;
quota cộng dồn **accepted logical file records**, không submitted attempts hoặc
unique blobs. Limits giữ nguyên20 files/batch,20 MiB/file,100 MiB accepted source
bytes/batch; MiB=1.048.576 bytes. Rejected không chiếm count/accepted bytes;
parse-failed nhưng upload_status=uploaded vẫn chiếm. Cùng bytes/client_file_id mới
vẫn file record mới và cộng bytes lần nữa; Store blob dedup không file/business dedup.

I02 duyệt từng entry theo thứ tự multipart, paired files[]/client_file_ids[]. Nếu
file không vừa remaining quota thì reject entry đó; file phía sau còn vừa vẫn được
nhận. Không reject toàn request chỉ vì submitted vượt remaining slots/bytes. Giữ
request guards:1..20 submitted entries/call, paired unique UUIDs, allowlisted fields,
actual multipart body cap100 MiB+128 KiB overhead, auth/current Store rights, key/
client conflicts và transaction rollback. Request-level lỗi không có committed
per-file outcomes; không đồng nhất với quota rejection trong service loop. Mỗi file
size/hash lấy từ actual server bytes; không client-declared size. CSV bao gồm BOM/
newlines/encoding gốc; XLSX là raw archive bytes. Expanded XLSX/parser limits độc lập.

Error priority per-file: size>20 MiB/count≥20/cumulative bytes>100 MiB →
RESOURCE_LIMIT_EXCEEDED, rồi INVALID_FILE_TYPE, rồi EMPTY_FILE. Vì vậy invalid file
ở cuối sau khi count20 cũng có thể báo RESOURCE_LIMIT_EXCEEDED. Sniff accepted bytes
không bảo đảm parser/schema/domain validity. I02 response200 có thể uploaded+rejected;
all returned items rejected →422 UPLOAD_REJECTED, data=null, details={items,
import_revision,file_set_version,approval_request_allowed:false}, ETag revision.
Rejected receipts/audit đã commit trong nhánh này, kể cả batch đã có accepted files.
Request-level validation422 là general error envelope, không UploadFailure receipt.

file_set_version là **file evidence/receipt-set revision**. New-key call commit có
rejected hoặc chỉ same-client replay vẫn có thể đổi file_set_version/import_revision;
same-key same ordered IDs/filename/actual length/hash replay frozen receipt không
đổi thêm quota/version/audit. Same-key payload khác hoặc same client ID đổi bytes/
normalized filename409 IDEMPOTENCY_KEY_REUSED, rollback wholecall. Rejected client
ID cũng immutable; corrected bytes cần client ID/key mới khi còn unsealed. Historical
same-key I02 receipt có thể replay sau seal sau current authorization; FE phải refresh
I04, không lấy old receipt/ETag làm current quota. New-key I02 sau seal409.

I03 acceptance transaction seal ngay khi commit202, không đợi worker claim/completion.
Cần current quoted If-Match import_revision, file_set_version, **toàn uploaded IDs**
và **toàn rejected client-ID acknowledgment** (không duplicates). Missing/extra set422,
stale revision412, missing If-Match428; không job/seal trên validation failure.
Seal không tự đổi file_set_version. Failed analysis không unseal; khi failed và chưa
analysis_json có thể I03 retry explicit cùng sealed source set/new job. Sửa/thêm bytes
sau seal cần I01 draft mới. Chưa remove/replace/physical delete/quota release;
IGNORE sheet/cột không trả quota. Upload/analyze batch lock+refresh và DB sealed guard
serialize admission; không hứa fairness/winner theo thời điểm người dùng bấm.

**I04 JSON shape cuối cùng**, additive required `data.quota`:

```json
{"quota":{"accepted_file_count":2,"accepted_total_bytes":4,"remaining_file_slots":18,"remaining_bytes":104857596}}
```

Đây là data fragment, không toàn envelope. Mọi field là integer≥0, exact bytes,
không floating MiB. N=Σ1(upload_status=uploaded), B=Σsize_bytes(uploaded) trên toàn
batch; remaining_file_slots=20−N,remaining_bytes=104.857.600−B. Quota độc lập
files_limit/files_cursor; quota.accepted_file_count=file_count=|source_set.accepted_file_ids|,
source_set.version=file_set_version. Revisions/source-set/quota cùng coherent batch
read, không ghép cached old batch metadata với file records mới. Actor/Store/grants,
page cursor/staleness vẫn hiện hành. I01/I02 không có whole-batch quota object;
quota authoritative đọc qua I04 sau outcomes/replay/conflict. GET chỉ projection/
authorization/staleness checks, không parser/worker/LLM/preview computation hoặc
canonical/import writes. `allowed_actions` khác available remaining quota.

FE: local raw-file precheck với quota snapshot → I02 render per-item outcomes
(kể cả committed422 details) → refresh I04 whole-batch quota/source-set → I03 full
IDs+ack/current If-Match seal → J01/I04 đọc trạng thái. Không cần fetch mọi file page
chỉ tính quota; vẫn fetch đủ rejected metadata để acknowledge toàn bộ. Race/retry
không optimistic double-count. Chi tiết/scenarios và evidence:
[batch mechanics](IMPORT_MAPPING_API_CONTRACT_VI.md),
[task notes](runbooks/FULL_TEST_FLOW.md).

### 9.2. M01–M04 và profile decision

M01 GET flags include_clean_sheets defaultfalse, include_profile_details defaultfalse;
required data import_id/analysis_id/mapping_revision,progress,files,sheets,binding_refs,
profile_proposals,can_preview,blockers,allowed_actions. Progress scope toàn batch:
total_fields=completed_fields+unresolved; resolved proposals counted không có nghĩa
approved. include_profile_details trả full typed specs/diff/evidence; read sensitive
rule/sample scope cần full quyền mục10. `can_process` alias FE v0 chỉ được map sang
can_preview, **không can_commit**. ETag mapping_revision.

M02 query sheet_id optional,review_only defaulttrue,status allowlist,include_details,
limit/cursor; response items/counts như FE, thêm issue_type,source_location,
resolution_origin,profile_ref. Samples≤5 values×200 chars/issue, plain text no HTML,
not whole rows. Truncation sample là display metadata, không approval full spec.
Successful global pairs sheet_id omitted, review_only=false/status=auto_mapped;
add file/sheet refs. Counts trước status filter, không page counts.
CURRENT FACT: MappingList.counts là Progress của toàn bộ issues trong batch, kể cả
khi có sheet_id/review_only/status filter; chỉ items và meta.pagination.total_count
theo filtered result. completed_fields gồm resolved và auto_mapped, không phải số
auto/approved. Có thể đọc auto items với review_only=false&status=auto_mapped;
không cộng items.length để suy totals. Per-file/per-sheet/origin/filter mapping
counters IMPLEMENTED C4 ở mục17. Preview aggregates R05
là đơn vị khác, xem mục17.1. Source: ImportStagingUseCases.mappings/_progress.

M03 query mapping_id optional; returns schema/schema_version/schema_context_id,
mapping_revision,duplicate_mapping_allowed:false,options descriptors mục6. Target
unique trong sheet schema context, cùng target independent sheets allowed;
merge multiple columns không có declared rule thì DUPLICATE_MAPPING.

M04 column issue body `{target_field}` giữ FE shape; issue_type khác dùng union
`{resolution:{kind:"identity_binding",canonical_id}}` hoặc `{resolution:{kind:
"declared_conversion",from_unit,to_unit,factor,evidence_reference}}` hoặc explicit
ignored_optional_field hoặc new_entity_proposal mục6.1. Server issue type quyết
valid variant, không arbitrary dict; proposal entity mới không canonical insert.

Variant được người dùng duyệt trong S4.4 (không thêm route): issue cấp nguồn dùng
`{"resolution":{"kind":"source_context","source_system_key":"POS-A",
"report_type":"daily-sales","evidence_reference":"Owner source declaration"}}`.
Các keys bắt buộc, evidence_reference có nội dung 1..1000 ký tự; scope Store/actor
lấy từ session/import. Source-context issue cũng dùng được để chọn scope đã duyệt
trong trường hợp matching mơ hồ; context không thay header/identity/unit validation.
TECHNICAL CHOICE S4.4: optional sales_semantics= daily_total|disjoint_contribution,
inventory_semantics=lot_stock_count, decimal_locale=dot|comma,
date_format=ISO|DMY_SLASH|MDY_SLASH|EXCEL_SERIAL. HISTORICAL INFORMATION:
pack_cost_basis=PER_PACK|PER_SOURCE_UNIT còn đọc được trong DTO cũ; proposal mới
trả USE_EXPLICIT_SUPPLIER_PRICE_BASIS. Dùng source columns/shared declarations ở §13.2.
Owner review chúng trong full spec; không đoán khi thiếu. Omitted/null optional
format không khai báo thay đổi rule; chọn approved context giữ approved rules.
Declared policy khác phải proposal/reapproval, không bị bỏ qua như simple selection.
Optional planned_arrival_expiry_rule theo mục13.2 và term_period_amendments[]
={supplier_term_id,expected_version:opaque captured revision,effective_to,reason}
là representations của reviewed rules mục13.4, không thêm route/automatic closing.
Source provenance giữ verification=USER_DECLARED/owner_reviewed, không externally
verified. Explicit source_context.* metadata columns conflicting scope block.
M01 trả context trong full proposal/scope/source_provenance để Owner review.
If-Match mapping_revision; response200 mapping_id/status resolved/new revision/
progress/file-sheet summaries/proposal_revision/approval_required:true khi thay spec.
Staff/Owner edit proposal theo quyền; existing active/successful binding không mutate
qua M04. Proposal change sau preview invalidate khả năng commit, không đổi preview cũ.

Profile decision example, **Owner-only**, route mới duy nhất ở mục3:

```json
{
  "decision": "approve_activate",
  "proposal_revision": "proposal-demo-3",
  "expected_active_version": "profile-demo-1",
  "reason": "Đã đối chiếu mã món, đơn vị và cấu trúc báo cáo POS."
}
```

Không endpoint approval Staff execute token. Profile active update không rebind
old preview; new analyses dùng version mới, rejected proposal giữ active cũ.

### 9.3. I05 preview/commit và I04 read preview

#### Current wire S4.5 — commit202 / I06

Commit.reason có thể thiếu/null cho pure inserts/NO_OP thông thường; nếu có phải nonblank1..1000. Correction/merge/count/explicit amendment bắt buộc reason theo effective preview actions, confirm
phải boolean true rõ ràng; supplier_changes optional default[] nhưng nonempty bị
422 INVALID_IMPORT_CONFIGURATION trong S4.5 (lịch sử). S4.6 nhận tập supplier_changes đúng các row terms/phí cần xác nhận; xem runtime-s46. Current If-Match + key/Origin/CSRF.
202 data={import_id,status:"committing",phase:"commit",job_id,job_status:"queued",
commit_id,preview_id,effective_plan_digest,import_revision}; ETag revision mới.
J01 operation=import_commit, stage=queued|committing|completed|failed;
completed result={resource_type:"import_completion",resource_id:import_id,commit_id}.

I04.summary.can_commit là actor/state projection (retained preview không đổi digest),
true chỉ usable current confirmation/supported whole preview và rights/fences;
resolutions vẫn required cho confirmation rows. PreviewRow thêm normalized_source_quantity
cho sales; after.quantity là target aggregate. RecipeLineProvenance giữ từng normalized
Ingredient line/source row/provenance; synthetic reservation metadata là IDENTITY_BINDING.

I06 required fields đã chốt mục11, thêm data_date và canonical_references[]:
{row_id,canonical_domain:"products"|"ingredients"|"sales"|"recipes",canonical_id,
source_location,source_locations[],provenance:{field:ProvenanceValue},line_provenance[]}
(special recipe multi-row trace). Summary thêm inserted_record_count,
changed_record_count,no_op_count logical canonical actions; files accepted uploaded,
sheets non-ignored, rows raw source rows non-ignored (recipe lines không gộp ở rows),
mapped_fields non-ignored column issues có target, không cộng shared declarations.
Classification counts toàn logical preview (synthetic creations/recipe grouped).
Updated resources S4.5 chỉ inventory(false/null),menu,sales,catalog; các impact S4.6
chưa expose. Exact DTO examples ở feature, không dùng condensed design samples
bên dưới như full executable payload.

I06 readiness giữ shape mục14 và authorized evaluated_actions/omitted_actions;
chưa có evaluator nên unknown/NOT_ASSESSED, can_execute=false/EXECUTION_UNAVAILABLE.
as_of_date ngày Store lúc completion; data_date không watermark. Không tự evaluate GET.
Missing completion409 IMPORT_NOT_COMPLETED; failed diagnostics tại I04/J01.

Sales retained source history gắn Store/source_system_key/business_report_key/Product/
ngày. Source105 + baseline100 được explicit disjoint confirmation→205; reimport
source105 NO_OP; source revision105→110 update aggregate210 với sales.correct và
replace resolution. Unknown baseline giữ warning và pin canonical ID/xmin/quantity,
evidence/reason/assertion trong immutable audit, không coi declaration là proof.
Mixed/overlap/ledger-current-total mismatch block SALES_OVERLAP_UNRESOLVED. Không
file-hash identity, không generic UPSERT. source_revision/canonical_revision append
qua immutable audit0013; không rewrite lịch sử hay stored Run. Fraction arithmetic exact.

Atomic transaction reuses validation writers qua transaction-owned seams, master
reservations→recipe/sales dependencies; batch/authority locks và fixed canonical table
SHARE ROW EXCLUSIVE fence phantoms cả internal writers. Conservatively serialize
cross-Store writers; không throughput claim. Completion/job/audit/canonical cùng commit.
Same-key receipt replay không ghi trùng; uncertain acknowledgment fresh-session
reconcile; dead-process failed retry explicit new key + usable preview/confirmation.
GET không retry/compute. terminal import không đổi source/profile binding/completion;
Owner profile activation cho future không reset completion batch cũ.


I05 phase=preview body `{phase:"preview",mapping_revision}`; If-Match import_revision;
active job conflict409; response202 job operation import_preview, bound versions.

Ví dụ receipt202 của preview (chưa canonical writes):

```json
{
  "data": {
    "import_id": "00000000-0000-4000-8000-000000000001",
    "status": "previewing", "phase": "preview",
    "job_id": "00000000-0000-4000-8000-000000000060",
    "job_status": "queued", "import_revision": "import-demo-5"
  },
  "meta": {"request_id": "req-preview-demo", "warnings": [], "poll_after_ms": 2000},
  "error": null
}
```

Commit body `{phase:"commit",preview_id,preview_digest,confirm:true,reason,
resolutions:SalesResolution[]}`; If-Match import_revision; reason required when
correction/merge/count/explicit amendment; pure insert/NO_OP thường có thể thiếu/null,
empty resolutions[] explicit. SalesResolution={row_id,
action:replace_daily_total|confirm_disjoint_merge,report_business_key,
evidence_reference,reason,disjoint_assertion:boolean|null}; replace không disjoint
flagtrue. Resolutions phải exactly unresolved confirmation scope, không arbitrary
quantity override; after dựa established normalized facts và captured before.

```json
{
  "phase": "commit",
  "preview_id": "00000000-0000-4000-8000-000000000040",
  "preview_digest": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
  "confirm": true,
  "reason": "Đã đối chiếu bảng kiểm kê LOT-01.",
  "resolutions": []
}
```

Digest example hex0 minh họa syntax, không verified integrity của nguồn thực;
runtime phải computed/verified SHA-256 hex64 của retained preview.
Before accept check policy versions/bindings/preview/db scope/full rights; job còn
recheck tại canonical transaction. 202 không durable business success.

I04 GET files_limit/files_cursor như FE; thêm include_preview defaultfalse,
preview_id optional newest nếu không gửi,rows_limit/rows_cursor,classification
filter. Response data import metadata/status/import_revision/active_job_id,
files_page,source_set,quota (mục9.1a),allowed_actions,preview:null|{summary,rows,rows_page},
completion_available. Khi preview_id chỉ định phải thuộc đúng import, không switch
latest; summary toàn preview, rows paginated. Bound preview chưa có khi requested:
409 PREVIEW_NOT_AVAILABLE, không return empty rows giả. Preview includes typed
planned ops dù chưa có quyền commit, nhưng chỉ khi có full read sensitive scope.

Ví dụ row preview minh họa kiểm kê, quantities signed delta dùng SignedDeltaText:

```json
{
  "row_id": "00000000-0000-4000-8000-000000000050",
  "source_location": {
    "file_id": "00000000-0000-4000-8000-000000000010",
    "sheet_id": "00000000-0000-4000-8000-000000000020",
    "row_number": 2, "source_column_index": 3
  },
  "classification": "CHANGED", "proposed_action": "COUNT_CORRECTION",
  "entity_refs": {"lot_id": "00000000-0000-4000-8000-000000000030"},
  "before": {"domain": "inventory_count", "on_hand": "12", "unit": "l"},
  "after": {"domain": "inventory_count", "on_hand": "10", "unit": "l"},
  "changes": [{"field": "on_hand", "before": "12", "after": "10", "delta": "-2"}],
  "provenance": {"on_hand": {"origin": "SOURCE_EXPLICIT", "applied_rule_ids": []}},
  "blockers": [], "warnings": [], "confirmation_required": true
}
```

SignedDeltaText regex `^-?(0|[1-9][0-9]*)(\.[0-9]+)?$`, finite; negative zero canonical
output0. No float epsilon. Runtime count observation is required in retained normalized
source/header, dù condensed row example không lặp whole-source profile.

<a id="security"></a>
## 10. Quyền, idempotency, audit và dữ liệu đổi giữa các bước

Action names dưới đây TECHNICAL CHOICE catalogue, không grants runtime: import.create/upload/
analyze/read/preview/commit; mapping.read/propose; Owner-only profile.decide;
sales.record/correct/merge, inventory.count.correct, recipe.create_version,
product.create/ingredient.create cho entity mới, và
domain reads. Commit phải kiểm tập quyền **toàn bộ requested canonical domains/actions**,
kể cả NO_OP domains, không silently drop unauthorized group. Owner approve mapping
không authorization import. Membership revoked chặn reads/retry/commit, đang job
chưa commit phải recheck dưới cùng authorization fence transaction; sau commit
không undo bằng cách sửa history, nhưng rights revoked không đọc result nữa.

Raw upload có thể có sensitive columns: upload permission không cấp view bytes/
samples. Analysis LLM chỉ được nhận ambiguous approved-to-view semantic samples,
không gửi values ngoài actor permission. I04/M*/preview/history/completion chứa
samples/financial/derived facts cần toàn bộ read domain scope + sensitive read
permissions; không được chặn sau khi đã gửi provider. Thiếu quyền chặn whole
requested response403, không selective dropping rows. I01/I02 metadata receipts
không return sample/cost. Menu retail price visibility giữ policy đã chốt; cost/
budget vẫn quyền riêng. No approval one-time bypass: approval_request_allowed=false
cho commit/Owner mapping decisions cho đến khi allowlist được duyệt riêng.

Idempotency key scope actor+Store+method+route+phase; digest typed validated body,
array order, content hashes và normalized conditional headers; same key/request receipt/job cũ, không
latest mappings/new compute. Key khác request409. Same source business records
different key vẫn no duplicates qua source contribution/business uniqueness.
Race two imports same rows dùng expected versions/absence predicates+unique DB
keys; một commit thắng, cái còn lại409 PREVIEW_STALE, không double insertion.
Không dùng request key thay business provenance hoặc filename identity.
Proposal/approval/preview mutations CAS; retry successful receipt trước stale CAS
nhưng sau authorization recheck. Uncertain commit reconcile receipt+canonical
aggregate từ fresh session, không blind execute lại. Programming errors không
success; no generic per-row silent fallback.

CURRENT FACT: confirm_review kiểm receipt trong cả hai transactions, kể cả continuation
sau detached read-set capture; same-key receipt đã tồn tại được replay trước completion/
CAS guard sau current authorization, preview integrity và required-action checks.
Canonical worker chỉ reconcile recognized uncertain SQLAlchemy/psycopg error tại
COMMIT với retained completion/job proof. Programming error sau durable completion
vẫn nổi lên; không đổi completed thành failed hoặc chạy canonical writes lại.
Mất key/body không có generic discovery/negative-outcome API; I04/J01/I06 và H01/H02
chỉ chứng minh state quan sát được. Empty/404/403/missing receipt không fence delayed
request và không cho phép thay bằng key mới khi outcome chưa rõ.

ACCEPTED DECISION / CURRENT FACT: riêng Commit.reason omitted và explicit null
equivalent trong current fingerprint: CommitRequest validate rồi model_dump điền
reason=None. Text reason khác null vẫn khác intent. Không suy tương đương này cho
mọi field/operation; array order và original CAS vẫn thuộc fingerprint. Không đổi
persisted digest/receipt identity. FE luôn giữ original body/presence khi replay,
không tự fill defaults, normalize null, reorder arrays hoặc lấy CAS mới.

| Thay đổi trong lúc chờ | Behavior design |
| --- | --- |
| File bytes khác | File immutable; nguồn khác tạo new draft/file, không sửa digest/source rows cũ. |
| Proposal revision/mapping bindings đổi | Preview stale; preview lại; không patch historical preview. |
| Active mapping version mới | Pin cũ còn authorized dùng thì giữ; không latest switch. Explicit retire chặn uncommitted pin. |
| Canonical before values/source contributions/existence đổi | PREVIEW_STALE rollback toàn transaction; refresh preview, không recompute delta/merge silently rồi success. |
| Rights/membership revoked | Deny read/retry; job chưa canonical commit chặn tại fence; không grant từ accepted job. |
| Commit xong mapping retired/DB đổi | I06 retained impact/version, không reinterpret; reimport phải new preview/rights hiện hành. |

Audit immutable append records: source bytes digest, analysis/revisions, rules/
aliases/conversions evidence, proposer, Owner decision/active before-after/reason,
exact bound profile versions, preview digest/read-set/before-after/row operations,
executor/rights checked/confirmations, receipt/outcome/time/error. Owner và executor
có thể khác; Staff vẫn executor, không đổi thành Owner. Full raw file/provenance
retention policy chưa được chốt; v1 design không tự purge evidence/receipts, không
backup/DR guarantee hoặc TTL approval suy ra từ mocks.

<a id="errors"></a>
## 11. Errors, completion/history và readiness

CURRENT FACT S4.5 runtime: I01–I04/M01–M04/N5/I05 preview/confirm_review/commit/J01
và I06 đã wired cho bốn schemas. History H01/H02, R01 evaluator và S4.6 vẫn future.
Implementation/evidence/limits: [Import feature](features/IMPORT_STAGING_PREVIEW.md),
[current verification runbook](runbooks/FULL_TEST_FLOW.md). Historical absence statements ở phần
đối chiếu đầu tài liệu là slice-time, không runtime inventory hiện tại.

400 INVALID_REQUEST;401 UNAUTHENTICATED;403 PERMISSION_DENIED;
404 RESOURCE_NOT_FOUND scope-safe;412 MAPPING_REVISION_CONFLICT hoặc
IMPORT_REVISION_CONFLICT/PROFILE_REVISION_CONFLICT;428 PRECONDITION_REQUIRED;
413 RESOURCE_LIMIT_EXCEEDED;415 INVALID_FILE_TYPE;422 INVALID_FILTER/INVALID_CURSOR/
INVALID_MAPPING_TARGET/INVALID_IMPORT_CONFIGURATION. 503 SERVICE_UNAVAILABLE chỉ
tạm unavailable, không permanent unsupported schema. Async errors retained trong
Job.error; failed GET vẫn200. Successful GET không pretend failed import success.

Domain409: NO_UPLOADED_FILES,IMPORT_STATE_CONFLICT,ANALYSIS_NOT_READY,
OWNER_MAPPING_APPROVAL_REQUIRED,UNRESOLVED_REQUIRED_FIELDS,SCHEMA_BLOCKED,
PREVIEW_BLOCKED,PREVIEW_STALE,PREVIEW_NOT_AVAILABLE,MAPPING_VERSION_RETIRED,
SOURCE_IDENTITY_CONFLICT,SALES_OVERLAP_UNRESOLVED,STALE_STOCK_OBSERVATION,
IDEMPOTENCY_KEY_REUSED,IMPORT_NOT_COMPLETED. Error.details={source_locations[],
blockers[],field_errors[],approval_request_allowed:false} theo applicability,
không raw provider/SQL/secret. Ordinary row invalid là preview blocker/code như
NEGATIVE_QUANTITY/MISSING_REQUIRED_VALUE, không automatically PROFILE_INVALID.

I06 required data import_id,status,outcome:committed|no_changes,mode:atomic,
completed_at,commit_id,preview_id,effective_plan_digest,mapping_bindings[],summary,
updated_resources,readiness,audit_reference. Summary include files/sheets/rows/
mapped_fields/errors/warnings/classification counts; only successful atomic commit
errors0, warnings allowed. Impact counts distinct affected entities/new/changed/
noops from committed receipt, không current Store totals; no_changes all updatedfalse.
Product/Ingredient creation chỉ được tính impact khi thực sự committed:
menu.affected_product_count gồm distinct Product mới và Product recipe affected;
catalog thêm {created_product_count,created_ingredient_count}. New Ingredient chỉ
tạo catalog không làm inventory.updated=true nếu không có stock movement; recipe
column names không tự là Product creation hoặc stock update evidence.
Completion timestamps actual commit outcome, imported_at first accepted upload.
Failure/blocked diagnostic qua I04/J01, I06 không fake metrics cho chưa committed.

H01/H02 giữ FE category/status/q AND rules: category+filename phải match cùng file,
mở batch hiển thị cả files được phép đọc. Calendar date imported_at theo Store
timezone, distinct batches; draft chưa upload excluded. Nonterminal uploaded batch
history có in_progress filter riêng; terminal completed/completed_with_warnings/
failed, blocked state display cần FE adapter. Month YYYY-MM,import_date DATE,
sort=-imported_at/UUID tie, sparse dates count0; whole filtered totals không page
length. Summary metadata không leak batch không authorized read scope.

I06 readiness là snapshot point-in-time at commit theo mục14, R01 là evaluator
currentfacts. Canonical shape/actions/projections được định nghĩa duy nhất mục14;
không old generic data/forecast/plan boolean hoặc maxsalesday=watermark. Latest
retained Run bất biến, không chứng minh inputcurrent hoặc winnereligible.

<a id="acceptance"></a>
## 12. Acceptance, implementation backlog và quyết định đã chốt

### 12.1. Acceptance specifications

1. Approved matching Store/profile direct reuse không LLM/reapproval; unknown
   fields/identity/conversion blocked; confidence cao không activate proposal.
2. Staff M04 propose được theo grants, profile approve/activate/retire403; Owner
   khác Store404; full spec/diff/evidence/hash checked, CAS concurrency đúng.
3. Owner activation không commit; preview/commit pin source+profile versions;
   supersede không latest switch, explicit retire chặn uncommitted binding.
4. Upload/analysis/preview chỉ staging; atomic failure không partial canonical
   state, không per-row commit. Missing rights/one bad row rollback toàn batch.
5. Same bytes/records/key retry no duplicates; changed source daily total100→105
   replaces after confirmation; independent105 approved merge100→205; retry still205;
   same contribution update110 yields210, not315; overlap/missing identity blocked.
6. Count lot12→10 has one−2 movement+balance10 atomically; no receipt10, unknown
   lot/aggregate stock block; zero delta no movement; concurrent/dated count stale
   không apply. Absence file lot không zero/delete; units/expiry not fabricated.
7. Recipes whole yield/loss/version/date/no overlap; no autoclose; foreign refs
   blocked; aliases/conversions exact declared, provenance preserved; no LLM facts.
8. Preview before-after/read-set unchanged tại commit; unique race conflict rollback,
   auth revoke fence, uncertain receipt/fresh-session verify trước completion.
9. Completion counts from actual commit, no-op not updated; history/date/filter
   semantics consistent; unknown readiness false; retained Run/forecast không recompute.
10. Malformed/decompression/resource limits fail không truncate; HTML/formula
    injection không execute; provider unavailable không chặn known deterministic flow.
11. New Product/Ingredient chỉ staging trước Owner approval; approved metadata/unit/
    identity xuất hiện CREATE actions và required create grants trong preview.
    Commit catalog+dependent recipe/sales atomic; failed groups không orphan entity.
12. New Ingredient không tạo lot hoặc stock0 giả; unknown lots vẫn blocked. Repeated
    source identity no duplicate catalog; concurrent creation PREVIEW_STALE; sửa
    proposal làm approval cũ không usable; existing metadata conflict không upsert.

### 12.2. CURRENT FACT and remaining scope

Parser/staging/mappings/preview/confirmation and atomic nine-schema canonical
commit are implemented; H01/H02, I06, J01 and R01 are wired. Current DTOs:
app/application/contracts/import_mapping.py and import source/domain contracts;
application: ImportStaging and operational Import; persistence: import/operational
models and repositories. Tests cover permissions, source identity, corrections,
CAS/replay/commit/readiness and fresh-session state. Test presence is not fresh PASS.
FE whole mapping continuation remains NOT_RUN. Historical data correction,
unsupported fee conditions and one-time approval need separate reviewed scope.

### 12.3. Quyết định sản phẩm đã chốt

Ba câu hỏi quan trọng đã được hỏi trong lượt này, kết quả:

- **Atomic:** người dùng “Atomic toàn batch; có lỗi chặn thì không ghi”. V1 không
  partial_success. Byte-upload per-item acceptance không thay policy canonical batch.
- **Sales:** updated total thay thế; independent sources merge sau cảnh báo/xác nhận
  bởi Owner hoặc Staff được cấp quyền, exact version/source audit; không auto-add.
- **Inventory:** người dùng “Kiểm kê snapshot theo lô đã định danh”. Không receipt
  import/unknown lot bootstrap/ingredient-total stock writes trong scope v1 này.

**Tạo Product/Ingredient mới — ACCEPTED DECISION sản phẩm, 09/10/2026:** người dùng
“Cho tạo Product/Ingredient mới qua import theo các điều kiện trên; cập nhật vào
chính contract hiện có”. Owner duyệt explicit identity/đơn vị/metadata, executor
có quyền tạo catalog, preview creation và commit atomic theo mục6.1. Không create
từ tên hoặc LLM, không new lot/stock bootstrap. Unknown identity chưa đủ approval/
metadata vẫn blocked; sau duyệt được tạo cùng dependent sales/recipes.

OPEN tạo entity của lượt trước đã được đóng; supplier/readiness mở rộng tại mục13–14.
Implementation registry/transaction/auth/parser vẫn backlog,
không behavior đã implemented hoặc lý do mở lại policy.

### 12.4. Task notes, rollback và verification

Trước viết đọc AGENTS/FE/auth/features/ADRs/source/contracts/tests relevant,
Planning/Catalog để freeze phạm vi; only new `docs/IMPORT_MAPPING_API_CONTRACT_VI.md`.
Không sửa source/tests/migrations/ADRs/status/WIP/FE, branch/reset/clean/commit/push/
ZIP. Rollback bỏ đúng tài liệu mới, không restore/reset files người khác.
Coverage documentation checks và policy consistency, không runtime evidence.

HISTORICAL INFORMATION — verification lượt tạo contract trước approval entity creation:

- Python qua `.\.venv\Scripts\python.exe -`: PASS parse4 JSON examples,12 unique
  anchors/mục lục đúng đích,10 links tài liệu tồn tại,14 route gốc khớp FE,UTF-8 và
  whitespace. Kiểm explicit OPEN Q4 và atomic/no partial v1 vẫn có trong contract.
- `git diff --check`: exit0 cho tracked worktree; file mới untracked kiểm whitespace
  riêng bằng script trên, không suy đây là kiểm thử WIP source của phiên khác.
- `git status --short -- docs/IMPORT_MAPPING_API_CONTRACT_VI.md`: file contract mới.

Không pytest/parser/solver/DB/OpenAPI runtime. Schema/transaction/auth/provider/
performance acceptance chưa verified; docs passing không full regression passing.

Verification cập nhật policy tạo entity ngày09/10/2026: chỉ sửa chính contract này,
không tạo file mới hoặc endpoint mới. Python qua `.\.venv\Scripts\python.exe -`
PASS5 JSON examples, links/mục lục, UTF-8/whitespace và kiểm OPEN creation đã đóng;
CREATE actions/create permissions/atomic dependencies/không bootstrap lot vẫn rõ.
`git diff --check` exit0; tài liệu untracked kiểm whitespace riêng. Không chạy
tests/solver/DB, không sửa source/ADRs/FE/WIP của phiên khác, không commit/push/ZIP.

<a id="supplier-v1"></a>
## 13. Supplier terms/phí và completeness — mở rộng v1 hiện hành

**ĐÃ CHỐT scope:** người dùng giữ nhập/review điều kiện nhà cung cấp và phí ở v1.
Mục này thay unsupported-supplier của bản trước; không biến parser thành generic
DB writer. **TECHNICAL CHOICE** wire/versions; **CURRENT FACT** SupplierTerm.create/get
nội bộ có typed inputs/nonoverlap, Supplier chỉ model/repository; phí là explicit
caller-supplied inputs, chưa có canonical fee/config persistence hoặc importer.
Nguồn: app/models/supplier.py,supplier_term.py; application/contracts/supplier.py,
procurement.py,decision_capture.py,decision_capture_v2.py; use_cases/supplier.py;
tests/integration/test_supplier_operational_constraints.py; ADR010/019/020/021.
Internal engine hỗ trợ fee_mode NONE|PER_OFFER|PER_SUPPLIER_ORDER, fixed payable fee
khi offer/supplier có order; không engine thuế theo phần trăm/tier/delivery service.
Quantity/PositiveQuantity trong mục13 là aliases QuantityText/PositiveQuantityText
theo Catalog, không ExactQuantity rational output của Planning C03. MoneyText theo
Planning; canonical input giữ exact parsed decimal, capture adapter đổi sang
typed engine input chứ không gửi raw source strings làm retained result.

### 13.1. Workflow và endpoints — không thêm route supplier CRUD

I01/I02 upload → I03 schemas supplier/supplier_terms/payable_fees/scope_declarations
→ M01–M04 review/bind/đề xuất entity → N5 Owner approve mapping → I05 preview
before/after → người có đủ quyền commit → I04/I06 đọc retained configuration/actions
→ R01/C01. M03 field-options bổ sung typed descriptors dưới đây; M04 giữ mutation
proposal không canonical writer; Supplier mới dùng new_entity variant SUPPLIER.
I04 include=configurations (query comma-separated allowlist thêm cùng preview),
I06 updated_resources thêm suppliers,terms,fees,declarations mỗi nhóm
{updated:boolean,created_count:int,changed_count:int}; không count settings như lot.
H01/H02 category=supplier chỉ match cùng file; mixed sheet vẫn groups explicit.

I04 configurations là retained bản vừa reviewed/committed của import, không
endpoint “current all supplier data”. Khách sửa bằng file theo cùng business
identity và revision; preview đưa canonical before để biết current version.
Không auto commit từ mapping activation hoặc fee coverage declaration.
Typed I04 configurations={suppliers:SupplierBinding[],terms:TermRevision[],
fees:FeeRevision[],declarations:DeclarationRevision[]}, phân trang bằng cursor
bound include/schema/preview; mỗi revision gồm canonical_id:UUID,version:Version,
source_identity:{source_system_key,source_record_key},state:staged|committed,
payload:typed schema mục13.2/13.3/13.5,provenance,expected_before_version:Version|null.
SupplierBinding payload giữ source_supplier_key/name/active + reserved/current
supplier_id; TermRevision thêm internal_term_version:int. payload references trả
UUID binding canonical/reserved, không tên gần giống. Version fee/declaration
không phải internal SupplierTerm integer. No preview thì configurations staged
theo analysis, không hứa committed. include=configurations với include=preview
trả cùng preview_id/digest/readset; không trộn revisions từ previews khác nhau.

### 13.2. Supplier và term identity/typed data

SupplierSource={source_supplier_key:string1..1000,name:string1..200,active:boolean}.
Identity namespace Store+source_system_key+source_supplier_key; binding tới UUID
Supplier hoặc Owner-approved new Supplier với reserved UUID+metadata. Tên nonunique,
không fuzzyidentity; không lấy Product/IngredientSKU làm SupplierID. Same identity
unchanged NO_OP, metadata conflict blocker SUPPLIER_METADATA_CONFLICT; v1 không
generic supplier rename/deactivate từ row. sourceactive của entity mới phải explicit
hoặc accepted visibledefaulttrue; existingactive không bị fileoverwrite.

CURRENT FACT: registry dùng `TermImportSource` cho nguồn; `TermSource`/`TermValue`
giữ canonical/retained contract cũ. Nguồn có source_term_key, supplier_id,
ingredient_id, effective_from/to, unit, pack_size_base_quantity, pack_cost, currency,
lead_time_days, shelf_life_days, active, maximum_order_base_quantity như trước;
`unit` ở source là đơn vị lượng trong pack, sau normalize phải đúng Ingredient.base_unit.
MOQ nguồn dùng `minimum_order_quantity` decimal text thay `minimum_order_packs`;
thêm required `price_basis`, `price_quantity`, `price_unit`, `moq_basis`, `moq_unit`.
Ba quantity/unit nullable vẫn cần cột hoặc explicit null declaration.
`pack_label` optional-nullable chỉ giữ nhãn bao/thùng, không là physical unit.
Storecurrencyexact; effective_to inclusive
≥from; no datefallback fromupload. last optional maximum quantity, nếu declared
thì explicit SupplierLimit ONE_ORDER_SUPPLIER_INGREDIENT theo engine; null phải
scope_declaration EXPLICIT_NOT_CONFIGURED hoặc UNKNOWN, không “unlimited” ngầm.
Lead/shelf days integer thật không bool/fraction/truncate; canonical MOQ integer1..2147483647.
Canonical internalversion SYSTEM_ASSIGNED positive sequence per supplier+ingredient,
không trust Excel version để overwrite UUID; source_term_key là external recordidentity,
không version/schema ID. Newsource cùng Supplier/Ingredient ngày hiệu lực chồng lấn block TERM_PERIOD_OVERLAP.

Canonical pack cost là giá **một pack trọn**, riêng với payable fees. Source15kg/pack,
28000VND cho 1kg→420000VND/pack chỉ khi inputs/conversion Owner-approved.
MOQ physical chuyển exact ceil thành điều kiện mua pack nguyên; không default1. Lead0 hợp lệ known same-day; missing
không0. Shelf life null không đủ suy expiry; planned arrival của Ingredient tracked
phải có rule expiry đã được khai báo rõ. Mapping profile có optional
planned_arrival_expiry_rule={basis:"ARRIVAL_PLUS_DECLARED_SHELF_LIFE_DAYS",
evidence_reference:string}. Owner duyệt ý nghĩa nguồn “hạn dùng = ngày nhận + N
ngày lịch”; expiry=arrival_date+shelf_life_days, N=0 là dùng ngày nhận. Không có
rule/known shelf life thì không derive; readiness REQUIRED_ARRIVAL_EXPIRY_UNKNOWN.
Đây là rule tạo **hypothetical arrival** của engine, không ghi expiry lô thực hoặc
claim nhà cung cấp bảo đảm tuổi hàng khi nguồn chưa xác nhận. Leadtime tính từ
orderdate của captured policy, actual dates/overflow được validate; không biến
plannedarrival thành inventory hay PO. Captured source references giữ ruleversion,
termversion và derivation. SupplierTerm strict input hiện có không tự lưu rule này;
registry/config adapter nằm trong backlog.

#### Supplier source basis và FE projection

ACCEPTED DECISION: Supplier slice được người dùng duyệt; không đổi procurement
objectives/constraints hoặc diễn giải lại term/Run đã lưu. CURRENT FACT:

| Source declaration | Validation và canonical derivation |
| --- | --- |
| price_basis=PER_PACK | pack_cost nguồn là giá trọn pack; price_quantity/price_unit phải explicit null |
| price_basis=PER_QUANTITY | price_quantity>0, price_unit rõ; canonical pack_cost = source price × canonical pack quantity / canonical denominator quantity |
| moq_basis=PACKS | minimum_order_quantity>0 và nguyên; moq_unit phải explicit null |
| moq_basis=PHYSICAL_QUANTITY | quantity>0, moq_unit rõ; minimum_order_packs = ceil(canonical MOQ quantity / canonical pack quantity) |

Fraction/Decimal giữ exact, độc lập ambient precision. Hỗ trợ mg/g/kg và ml/mL/l/L
cùng dimension; count labels piece/pcs/unit/each/cái chỉ giữ khi exact same label.
Đổi unit cần M04 declared_conversion tới canonical unit và đúng known physical factor;
price_unit/moq_unit cũng sinh UNIT_CONVERSION_REQUIRED, kể cả shared declarations.
Không đoán density, packaging factor, currency FX hoặc unit aliases.
Unknown units, wrong factor/mass-volume block; zero pack/denominator/MOQ block,
zero price vẫn hợp lệ nhưng readiness đòi finite offer bound. Nonterminating price
block NON_TERMINATING_CONVERSION; terminating price vượt Money18/18 block
INVALID_SOURCE_VALUE. DB NUMERIC/pack_cost DTO cần decimal, engine rational output
không là rational canonical price input; không làm tròn để vượt giới hạn này.

| Ví dụ explicit | Canonical / consumer |
| --- | --- |
| Pack1kg, base g; 100000VND/PER_PACK | 1000g,100000VND/pack; hai pack goods200000 |
| Pack1000g; 100VND/PER_QUANTITY, denominator1g | Cùng canonical trên |
| Pack2l, base ml; 60000VND/PER_QUANTITY, denominator1l | 2000ml,120000VND/pack |
| Pack1000g; MOQ2 PACKS hoặc2000g PHYSICAL_QUANTITY | Cùng minimum_order_packs2 |
| Pack1000g; MOQ1500g PHYSICAL_QUANTITY | minimum_order_packs2; giữ source minimum1500g; zero basket được phép, một pack không được |

M03/M04 giữ endpoints: source columns hoặc shared_value declaration. price_basis,
price_quantity, price_unit, moq_basis, moq_unit, pack_label cho PROFILE_CONSTANT hoặc
IMPORT_VALUE. Commercial price/MOQ/pack quantity/lead/shelf/date/maximum facts chỉ
source column hoặc IMPORT_VALUE; profile chỉ giữ requirement, không reuse giá trị.
Ví dụ phần nguồn cho pack1kg/base g (identity/dates/lead/shelf/currency/active/max-order
vẫn phải cung cấp theo contract):

```json
{"unit":"kg","pack_size_base_quantity":"1","pack_cost":"100000","price_basis":"PER_PACK","price_quantity":null,"price_unit":null,"minimum_order_quantity":"1500","moq_basis":"PHYSICAL_QUANTITY","moq_unit":"g","pack_label":"thùng"}
```

Owner duyệt kg→g factor1000/1; `after` có unit=g, pack_size_base_quantity="1000",
pack_cost="100000", minimum_order_packs=2. MOQ nguồn luôn decimal text, kể cả "2"
pack; canonical MOQ mới là integer. Không lấy phần JSON ví dụ làm defaults.
Ví dụ M04 (các nullable declarations phải khai báo riêng, không tự điền):

```json
{"resolution":{"kind":"shared_value","target_field":"supplier_terms.price_basis","scope":"PROFILE_CONSTANT","value":"PER_QUANTITY","evidence_reference":"Bảng giá này luôn báo theo lượng khai báo"}}
```

FE lấy descriptors/scopes; thêm selectors price/MOQ basis, denominator quantity/unit,
MOQ source quantity/unit và nhãn pack riêng. N5 Owner review như hiện hành; Staff
không activate. Profile cũ thiếu các bindings mới không auto-pin/execute, warning
SUPPLIER_BASIS_REVIEW_REQUIRED; Owner map lại MOQ và basis, không backfill old terms.
SourceContext.pack_cost_basis cũ không đủ denominator/MOQ authority. Header/index/
kind/header row/epoch/source changes vẫn drift; không hứa phát hiện hidden semantics.

I04 preview và I06 canonical_references thêm nullable `supplier_term_semantics`:
source_pack_quantity/unit, pack_label, source_price, price_basis, price_quantity/unit,
canonical_price_quantity, moq_basis, source_moq_quantity, moq_unit,
canonical_moq_quantity, minimum_order_packs, fee_coverage/date. `after` giữ canonical
pack quantity/unit/cost/MOQ; identities/actions/version/blockers dùng fields hiện có.
provenance giữ source_value/index hoặc declaration_id, ordered applied_rule_ids.
TermSourceRecord.payload vẫn canonical; immutable provenance giữ semantic projection
và frozen spec. fee_coverage chỉ đánh giá tại effective_from, không chứng minh toàn
horizon readiness; không unique COMPLETE evidence thì UNKNOWN và warning
PAYABLE_FEES_NOT_ESTABLISHED. Explicit NONE+COMPLETE khác missing fee. Preview read-set
có fees; fee thay đổi làm stale. Canonical term có thể commit khi fees unknown;
planning readiness/capture vẫn block PAYABLE_FEE_COVERAGE_UNKNOWN.

Commit dùng frozen validated plan và cùng canonical writer validation, recheck
read-set/revisions/rights; không reparse/rerun model. Atomic rollback/retry giữ nguyên.
Fresh-session acceptance và small fixed-basket oracle nằm ở
`tests/{unit,integration}/test_import_supplier_basis.py`; retained Planning capture
giữ giá/quantity/version tại thời điểm Run, future term change không viết lại Run.
Whole FE/browser, dữ liệu quán thật và mọi business units khác chưa được acceptance.

HISTORICAL INFORMATION: đã trace `IMPORT_QWEN_REPRO_20261012.zip`,
`backend/app/services/business_persistence.py:415–460`: legacy tách packaging label
khỏi physical conversion, MOQ nguồn là pack count rồi lưu physical quantity.
Lines489–494 cast price/lead qua int; `services/procurement_planning_service.py:111`
tính physical order quantity × unit_cost. Bản mới giữ tách packaging/physical và
Store identity/provenance, chủ động thay bằng explicit independent price/MOQ basis,
exact denominator conversion, integer-pack ceil và dated versions/Owner review.
Không port integer truncation, giá không rescale, implicit defaults hoặc auto-deactivate
term cũ. Legacy source là evidence, không architectural authority.

### 13.3. Phí/coverage — không đồng nhất phí với delivery

FeeDeclarationSource={source_fee_key,scope:"STORE_PROCUREMENT",effective_from,
effective_to:date|null,mode:"NONE"|"PER_OFFER"|"PER_SUPPLIER_ORDER",
coverage:"COMPLETE"|"UNKNOWN",currency,components:FeeComponent[],
covered_source_term_keys:string[],covered_source_supplier_keys:string[],
evidence_reference:string1..1000,reason:string1..1000}.
FeeComponent={component_key:string1..1000,label:string1..1000,
basis:"PER_OFFER"|"PER_SUPPLIER_ORDER",source_term_key:string|null,
source_supplier_key:string|null,amount:MoneyText,condition:"WHEN_ORDERED"}.

PER_OFFER component chỉ tham chiếu term; PER_SUPPLIER_ORDER chỉ tham chiếu Supplier; label là
nguồn tên phí (vận chuyển/handling/phí dịch vụ…), không engine category giả.
Số tiền fixed/nonnegative totalpayable trong Storecurrency. Same basis/entity
components cộng exact, giữ breakdown/provenance; capture sang payable_fee theo
term hoặc SupplierFee.amount. Chỉ một mode trong một cấu hình execution,
không gom phí theo Supplier thành phí theo offer rồi tính nhiều lần. Mixed bases, %tax,
minimum invoice/tier/free-over-threshold/day-distance/perpack fees, điều kiện khác
WHEN_ORDERED: preview BLOCK UNSUPPORTED_FEE_RULE; không convert/drop businessrule.
Không phí negative/credit semantics ngầm. Không khai báo COMPLETE nếu các nhóm
phí phải trả chưa được rà soát; missing component declaration không có nghĩa0.

NONE bắt buộc coverageCOMPLETE, components=[], covered scopes đủ mọi eligible
offers/suppliers và evidence explicit “không phí phải trả ngoài pack_cost”. Known
mode có missing bound amount/unknown scope→coverageUNKNOWN, lưu declaration
chưa đủ readiness nếu explicitUNKNOWN; không đổi thành miễn phí. COMPLETE với
uncovered eligibleterm blocker FEE_COVERAGE_INCOMPLETE; feecondition applicability
theo dates/scope đã capture, không từ filename/ngàyupload. Thêm term ngoài declared
coverage làm readinessunknown/block đến khi rà soát phạmvi; không tự extend coverage.
Policy engine fee_mode lấy effective declaration được pin, không choice FEpriority.

```json
{"schema":"supplier_terms","source_term_key":"milk-pack-20261009","supplier_ref":{"source_supplier_key":"SUP-01"},"ingredient_ref":{"ingredient_id":"00000000-0000-0000-0000-000000000003"},"effective_from":"2026-10-09","effective_to":null,"unit":"l","pack_size_base_quantity":"6","pack_cost":"180000","currency":"VND","minimum_order_packs":1,"lead_time_days":1,"shelf_life_days":14,"active":true,"maximum_order_base_quantity":null}
```

```json
{"source_fee_key":"fees-october","scope":"STORE_PROCUREMENT","effective_from":"2026-10-09","effective_to":null,"mode":"PER_SUPPLIER_ORDER","coverage":"COMPLETE","currency":"VND","components":[{"component_key":"handling-01","label":"Phí xử lý mỗi đơn","basis":"PER_SUPPLIER_ORDER","source_term_key":null,"source_supplier_key":"SUP-01","amount":"15000","condition":"WHEN_ORDERED"}],"covered_source_term_keys":["milk-pack-20261009"],"covered_source_supplier_keys":["SUP-01"],"evidence_reference":"Bảng điều kiện SUP-01 ký ngày 09/10","reason":"Đã review toàn bộ phí phải trả của nguồn này"}
```

### 13.4. Correction/versioning/preview

Versions/provenance/audit immutable, không overwrite retained Run/term captures.
Same identity nguồn+normalizedvalues→NO_OP; changed→preview CHANGED with fullbefore/
after, revision kỳ vọng, reason and explicit xác nhận correction. SupplierTerm
numericfacts chưa có automatic writer sửa cũ: future change dùng version kế tiếp,
effective_from nguồn explicit. Nếu kỳ hiệu lực trước đang mở overlaps: preview phải có
**explicit reviewed period amendment** close previous at newfrom−1 với before/after,
reason, immutable revision trước retained; không tự đóng từ row mới. Amendment được
executor có supplier.terms.correct xác nhận, không mapping approval thay commit.
Ngày from≤effective_from của kỳ trước hoặc sửa giá hồi tố đã có: blocker HISTORICAL_TERM_CORRECTION
v1; workflow correction hồi tố ngoài scope, không tự viết lại lịch sử. Fee samefuture
version+đóng kỳ hiệu lực explicit rule, no retroactive rewrite. Accepted supplier DB exclusion
vẫn giữ; versioned audit của amendment là implementation mới, không pretend có.
Recipe periods vẫn không tự đóng kỳ theo contract Catalog, không áp supplier amendment
ngầm vào Recipe. Sourcefile có enddate explicit không thể silently sửa canonical
term khác, vẫn preview before/after+rights/CAS+confirmation.

PreviewAction thêm CREATE_SUPPLIER,CREATE_SUPPLIER_TERM,AMEND_TERM_PERIOD,
CREATE_FEE_DECLARATION,AMEND_FEE_PERIOD,SET_SCOPE_DECLARATION; standard fields
action_id,source_locations[],target_reserved_or_existing_id,before,after,
required_permissions[],expected_version,blockers[],warnings[],provenance.
I05 commit confirmations thêm supplier_changes:[{action_id,reason}], binds preview
digest, không client arbitrary targetafter. I04 actionpagination giữ rawvalues+
canonicalunit/pricingbasis; promoted rows có canonicalvalidity, executionreadiness
riêng. ScopeUNKNOWN validrecord không thành successplanning claim.
Sourceversion retired/currentDBchanged/rightsrevoked xử lý đúng mục10: pin,
PREVIEW_STALE hoặc deny, atomic wholebatch rollback; no partial supplierwrites.

### 13.5. Completeness declarations dùng được cho capture

Schema scope_declarations, explicit sourcefacts/manual-reviewed source sheet,
không “mặc định không có” trong code. Typed discriminated variants:
- INVENTORY: {ingredient_ref,state:COMPLETE_CURRENT_LOTS|CONFIRMED_EMPTY|UNKNOWN,
  observed_at:Timestamp,covered_lot_ids:UUID[],evidence_reference}. Complete phải
  exact toàn bộ lot IDs hiện hành; EMPTY chỉ khi nobalance/nolots positive và có xác nhận
  không còn stock thực chưa ghi. Bind expected inventoryrevision. Newreceipt/count
  hoặc relevantcatalogchange invalidate declaration đến khi reconcile/newreview;
  không stale “empty” sau receipt. Kho projection CONFIRMED cho hai knownstates.
- SALES_COVERAGE: {product_refs:[],from_date,to_date,state:COMPLETE|PARTIAL|UNKNOWN,
  evidence_reference}; COMPLETE yêu cầu explicit rows cho mọi coveredProduct/date,
  kể cả nguồn giá trị 0 được xác nhận; thiếu rows BLOCK không synthesize0. Không yêu cầu arbitrary
  140 ngày; forecastbaseline ≥1 observedProduct như Planning mục7; khoảng thiếu giữ missing.
- PROCUREMENT_CONTEXT: {effective_from,effective_to,committed_inbound_state:
  CONFIRMED_NONE|PRESENT_UNSUPPORTED|UNKNOWN,no_additional_orders_state:
  CONFIRMED_NONE|UNKNOWN,capacity_state:DECLARED|EXPLICIT_NOT_CONFIGURED|UNKNOWN,
  capacities:[{ingredient_ref,unit,maximum_quantity,checkpoint:
  POST_RECEIPT_PRE_EXPIRY_PRE_CONSUMPTION}],supplier_limit_state:
  DECLARED|EXPLICIT_NOT_CONFIGURED|UNKNOWN,supplier_limits:[{supplier_ref,
  ingredient_ref,unit,maximum_quantity,scope:ONE_ORDER_SUPPLIER_INGREDIENT}],
  evidence_reference}. DECLARED needsnonemptyrows, otherwiseempty; knownnone explicit
  evidence. Unsupported inbound blocksplanning, neverstockfake. noadditionalorders
  explicit means one-order scope engine, not customer confirmation of buying.
All declarations retain actor/source/profileversion/expectedreadset/digest. Import
profile normalizations may bind sourcecolumns but not manufacture absencefacts.

CURRENT FACT D3 trên nhánh data-readiness: Planning new-policy capture reuse các
immutable declarations/term/fee sources này, giữ versions/effectivity và typed
source confirmation references. Actor/time/audit chỉ known nếu có unique exact
Import canonical audit match; absent/ambiguous proof giữ null, không dùng Run actor
thay source confirmer. Không đổi Import required fields, approval/reuse/current
rights/stale-preview hoặc IMPORT_VALUE/batch semantics; không promote incomplete
term thành canonical. Planning offer omission là consumer admission riêng, không
workflow ghi assumptions/defaults mới. [Policy](features/DATA_READINESS_POLICY.md)
sở hữu admission rules; public readiness/warning extensions còn D4.

Rights: source/read fullscope including supplier.read+procurement.cost.read for
term/fee prices; importactions/mappingkeys + domainactions supplier.create fornew,
supplier.terms.create, supplier.terms.correct for amendment, supplier.fees.manage
forfees; declarations inventory.count.correct/sales.record/supplier.fees.manage
respectively plus whole domainreads, procurementcontext additionally budget.read.
Owner-only mapping approval remains; Staff granted canonical actions can commit
approvedmapping rows, no hidden escalation/automaticOwnerfactapproval.

#### Setup identity, Excel opening stock và lot count — CURRENT FACT

ACCEPTED DECISION: lát import setup được người dùng duyệt, dùng writers hiện có;
không mở Excel actual receipts, stockout hoặc forecast mới. Registry thêm
`opening_stock`; `inventory_count` tiếp tục chỉ chỉnh lô existing. M03 descriptors,
M04 resolutions, Owner activation và I01–I06/J01 dùng endpoints hiện hành.

Identity binding theo Store/entity/token exact trong profile được duyệt. Các spelling
khác nhau cần binding explicit; tên trùng không tự merge. Product selling_unit và
Ingredient base_unit là metadata bắt buộc trong proposal/master. Candidate tạo cùng
canonical identity, cùng SKU cho các IDs khác nhau, metadata reservations mâu thuẫn
hoặc binding một token tới nhiều IDs đều BLOCKED với source location. Dependencies
được nối trên toàn batch, gồm master rows thực và synthetic Owner reservations;
writer dùng thứ tự dependency, current permissions/read-set fence và atomic receipt.
Batch sau dùng canonical entities đã commit; thiếu identity vẫn phải review dù
headers/profile reuse đúng. Không bắt upload mọi domain hoặc dùng UUID nội bộ trong file.

Source `opening_stock` có required fields `source_record_id`, `ingredient_id`,
`supplier_id`, `lot_code`, `quantity`, `unit`, `received_date`, `expiry_date`,
`unit_cost`, `currency`, `observed_at`, `reason`. Supplier/lot label/received date/
expiry/unit cost nullable nhưng vẫn cần source hoặc declaration rõ; expiry tracking
đòi expiry date. `source_record_id` nonblank1..128; namespace lấy từ approved
profile `scope.source_system_key`, không filename/row number/lot label. Quantity>0;
zero toàn Ingredient dùng declaration, không tạo lot0. Currency exact Store.
Owner chọn rõ schema opening; ngày nhận không derive từ as-of/upload date.
observed_at cần timezone, không tương lai; nguồn date-only phải bổ sung declaration
IMPORT_VALUE có thời điểm thực đã xác nhận, không tự EXCEL_SERIAL thành timestamp.
received_date/expiry_date date-only hỗ trợ date-format/Excel epoch đã duyệt.

unit/currency cho PROFILE_CONSTANT hoặc IMPORT_VALUE; observed_at/reason/received_date/
expiry_date/supplier_id/unit_cost chỉ IMPORT_VALUE nếu shared. Quantity, source lot key
và label là row facts. Profile không giữ as-of/giá/dates của lượt import. Physical
conversions dùng known factors của recipe/supplier: không density/FX/pack factor;
opening unit_cost theo đơn vị vật lý đổi inverse factor, quantity đổi forward factor,
exact hoặc blocked. Không đổi Ingredient canonical unit hoặc metadata lô existing.

```json
{"domain":"opening_stock","source_record_id":"MILK-LOT-1","ingredient_id":"MILK","supplier_id":null,"lot_code":"LOT-1","quantity":"12","unit":"l","received_date":null,"expiry_date":null,"unit_cost":null,"currency":"VND","observed_at":"2026-10-13T02:00:00Z","reason":"Owner xác nhận số còn thực tế của lô vật lý riêng"}
```

`MILK` phải có reviewed binding/proposal; fixture example không là facts của workbook.
Preview canonical after thêm system-reserved `lot_id`. CREATE_OPENING_STOCK nối
InventoryUseCases.receive_in_transaction(opening=True): lot balance12,
COUNT_CORRECTION +12/reference OPENING_STOCK; không RECEIPT giả. Dùng cùng
InventoryReceiptRecord/source identity với N6: same normalized payload NO_OP/replay,
khác payload RECEIPT_IDENTITY_CONFLICT. New key không đủ để rebaseline lot đã có;
duplicate source key hoặc lô không phân biệt rõ trong batch bị chặn. Opening và
count cùng Ingredient trong một batch bị STOCK_OBSERVATION_UNVERIFIABLE: tách
observations đã xác minh, không chọn thứ tự file. N6 form/actual receipt giữ semantics.

PreviewRow và CommitRowReference thêm nullable `inventory_effect`:
{origin:OPENING_STOCK|IMPORT_COUNT,lot_id,before_quantity:null|Quantity,
after_quantity:Quantity,quantity_delta:SignedDeltaText,movement_type:
COUNT_CORRECTION|null,unit,observed_at}. Opening12 có before null, after12, delta+12;
count12→10 có delta−2; NO_OP không movement. Reimport opening sau count giữ source
quantity12 trong retained source, effect phản ánh live balance10→10/delta0. Frozen
effect, IDs, raw values, source index/declaration/rule chain và binding nằm trong
preview/completion/audit; commit không parse/model/normalize lại. Receipt stock
version của import là retained import effect marker; V01/V02 refresh cấp current
session-bound inventory CAS version khi khách thực hiện N6 tiếp theo.

Count unknown lot không tạo lot. Historical observation trước lot update, movement
occurred/recorded time hoặc NO_OP count audit bị STALE_STOCK_OBSERVATION, không đổi
timestamp. Preview stale/CAS/metadata conflicts giữ blockers và whole-batch rollback;
retry không apply delta lần hai. Lô received/expiry metadata không là count targets.

Declarations JSON hiện có cho phép name/code tại các typed Ingredient/Product/lot/
Supplier reference paths; M04 tạo identity issues và Owner-reviewed bindings, giữ
raw JSON/nested refs/provenance. Không flatten arbitrary nested fields. INVENTORY
scope exact Ingredient+lot set+as-of+evidence; actor/profile/commit audit giữ provenance.
Coverage tính cả planned opening/count; CONFIRMED_EMPTY không thể che opening dương.
Chưa declaration, partial lots hoặc nonunique current scopes giữ UNKNOWN; approved
profile/import completed không đồng nghĩa completeness. EMPTY với retained lots có
balance0 là known zero và operational/2 consumer nhận đúng; historical capture /1
giữ nguyên. R01/capture cùng yêu cầu một current dependency-matching scope; R01 inventory
warning chỉ cho Ingredient chưa có scope đó. Sales coverage không zero-fill gaps.

FE cần selector opening/count riêng, source lot key, nullable received/expiry/cost
facts, timezone/as-of declaration, Owner binding/create metadata và inventory_effect
projection. Scope declaration editor giữ lot picker/reference review; chỉ gỡ missing
facts đã có bằng chứng. Store mới có thể import từng batch, khai báo completeness/
procurement/fees và budget, rồi chạy custom Planning. Không có default configuration
vẫn DEFAULT_CONFIGURATION_UNAVAILABLE ở R01; không seed để tuyên bố whole READY.
Recipe gaps/fee UNKNOWN giữ exclusions/blockers. HTTP acceptance không browser PASS.

Trace legacy: [handoff §4](../IMPORT_SCHEMA_LEGACY_HANDOFF_VI.md#4-liên-kết-nhiều-file-và-setup-store)
ghi name/alias creation và handler order dependence. Static source ZIP
`app/services/business_persistence.py:98–116` iterate handlers theo sheets;
`:145–171` có ingredient create_if_missing theo source name/unit; `:220` inventory
handler là luồng legacy riêng. Current dùng approved IDs/units
và whole-batch dependencies, không port first-file units/name auto-create/default dates.
Legacy là evidence lịch sử; N6 và ADR-008/009/010/013 là authority cho lát này.

### 13.6. Acceptance và backlog

Chưa chạy: Supplier namecollision nofuzzybind; Supplier mới Owner-reviewed+creategrant;
pack15×28000→420000 exactorblock; unknownlead/date invalid; NONE explicit0 vsUNKNOWN;
supplierfee15000 once mỗi Supplier có đặt hàng, not perpack/offer; mixedfee blocked;
term mới outsidecoverage chưa ready; futureversion explicitperiodclose, no giá hồi tố
rewrite/Runmutation; stale preview/revocation/fault rollback allgroups; duplicate
identity noop/retry; initialstock declaration coversallIDs, missingdate notzero;
salesgap không0; committedinboundunknown notnone.
CURRENT FACT: supplier terms, fee storage/source binding và canonical import writers
đã triển khai. Correction ngoài các workflow được duyệt vẫn cần review.

<a id="readiness-v1"></a>
## 14. R01 canonical — action readiness và C01/I06 projection

**TECHNICAL CHOICE design**; không aggregate runtime. Đây là nguồn canonical duy
nhất; C01 chỉ projection như bên dưới, I06 retained snapshot. Không thay winner/
requirements/forecast policy trong [Planning mục7](PROCUREMENT_API_CONTRACT_VI.md#planning-capture).

### 14.1. Request/response và permissions

R01 GET /stores/{store_id}/readiness; query actions comma-separated
import|menu|inventory|forecast|planning, defaultimport,menu,inventory; optional
forecast_start_date:date chỉ khi requestforecast/planning, defaultStoretoday.
CURRENT FACT D4: optional `planning_request` URL-encoded strict C02 PlanningRequest
JSON, UTF-8≤64KiB, chỉ khi actions chứa planning. Nếu đồng thời forecast_start_date
phải bằng ngày trong request; mismatch/invalid JSON/null/duplicate keys trả422
INVALID_FILTER, không silently evaluate default. Không query thì chỉ đánh giá
DEFAULT_CONFIGURATION; không suy hypothetical custom/saved readiness.
Permissions selectedactions: import→import.read; menu→menu.read; inventory→
inventory.read+ingredient.read; forecast→planning.context.read+sales.read;
planning→planning.context.read+budget.read+procurement.cost.read. Storecurrentchecks
bắt buộc. Thiếu permission một requestedaction403 toàn response; không gửi
unauthorized cost/exclusion reason rồi dùng “permission blocker” để che. Nếu đọc
planningready mà thiếu planning.run, statusblocked reason ACTION_NOT_GRANTED,
không lộ thêm data; actor có đủ sensitive read mới được đánh giá readiness planning.
Không tự cấp inventory/sales/menu reads từ planning nếu scopedplanningfacts được
planningcontext cấp; rawrows của chúng vẫn require respectivepermissions.

Response data={store_id,as_of_date,evaluated_at:Timestamp,data_version:Version,
evaluated_forecast_start_date:date,cutoff_date:date,actions:ActionReadiness[],
source_versions:SourceVersions,scope_estimate:ScopeEstimate|null,
history_watermark:date|null}. Meta request_id,cache no-store. SourceVersions=
{catalog,recipes,inventory,sales,suppliers,fees,declarations,planning_config,
model_config:Version|null each}; digest typed sorted version nguồn projection,
không rawartifactpath hoặc implementationDBIDs. ScopeEstimate dùng đúng C01:
menu_product_count,estimated_computable_product_count,excluded_products[] với
product_id,reason_codes,affected_dates; chỉ estimated, captureC02 authoritative.

ActionReadiness={action,availability:"ready"|"blocked"|"unknown",
can_execute:boolean,data_status:"valid"|"invalid"|"incomplete"|"unknown",
execution_status:"available"|"unavailable"|"unknown",blockers:ReadinessIssue[],
warnings:ReadinessIssue[],result_assessment:"NOT_ASSESSED"}.
ReadinessIssue={code,source:"authorization"|"catalog"|"recipe"|"sales"|"inventory"|
"supplier"|"fees"|"constraints"|"forecast"|"configuration"|"runtime",
scope:"STORE"|"PRODUCT"|"INGREDIENT",entity_id:UUID|null,
affected_dates:date[],details:object}. details typed percode, noSQL/secret/costvalues
unlessalreadyauthorized. can_execute true iff availabilityready; unknownfalse.
Knownblocker takes precedence blocked; unknown prerequisite givesunknown when
no blocker đã xác định. Validdata/unavailableworker yieldsblocked, not dữ liệu invalid.
GET only load/validate typedmetadata/facts/digests/declarations; no solver/train/
LLM/forecast execution, no thay đổi canonical or jobenqueue.

CURRENT FACT D4 — additive `planning_assessment` và `forecast_assessment` nullable
trên R01 data; C01 readiness.assessment/forecast là projections cùng evaluation.
PlanningAssessment={semantics_version:"planning_readiness/1",
input_scope:"DEFAULT_CONFIGURATION"|"SUPPLIED_REQUEST",
requirements_mode:"default"|"custom"|"saved",
configuration_status:"RESOLVED"|"INVALID"|"UNKNOWN",blockers:ReadinessIssue[],warnings:ReadinessIssue[]}.
Boolean hiện có đánh giá action+inputs/snapshot đó, không proof có winner hoặc đủ
requirements. Default thiếu là known blocker; full custom/saved không phụ thuộc
default thì không nhận blocker đó. Unknown model configuration vẫn unknown;
known worker/dependency unavailable vẫn blocked với execution_status unavailable.
ForecastAssessment theo [C01](PROCUREMENT_API_CONTRACT_VI.md#planning-context).
Issue.details dùng optional typed field/impact/entity_id/reference/version/
classification/proof_scope/suggested_action; absent fields elide. OFFER_OMITTED có
scope Ingredient, details.entity_id là term, reference/version từ D3 source;
proof chỉ CAPTURED_ELIGIBLE_OFFERS_ONLY. Remaining offers/fees/bounds dùng chính
admission của execution, shared unknown/corrupt/safety không thành warnings.
Forecast warnings reuse D2 assessment, giữ impact và computed exclusions/dates;
dedup stable theo exact issue/ref, không mất Product. NONCURRENT_PLANNING_CURRENT_FACTS
chỉ current captured facts cho ngày khác, không historical stock reconstruction.
I06 retained Issue/details schemas và semantics giữ nguyên; không backfill warnings.

### 14.2. Evaluation matrix, exclusions và orchestration

| Action | ready nghĩa gì / blockers |
| --- | --- |
| import | Upload/staging runtime available + import.create/import.upload grants; không cần có stock/sales. Existing import riêng kiểm state/rights/readset qua I04, Store ready không approvebatch. |
| menu | Scoped menu readeravailable; Menu được xác định rỗng vẫnready, data_statusvalid, warning MENU_EMPTY. No recipe không ngăn P01; P02 validity theo Catalog. |
| inventory | Warehouse readeravailable; đã biết không có lô vẫn readable ready với warning STOCK_COMPLETENESS_UNKNOWN, không claim procurementready. |
| forecast | Stable menu/sales/modelconfig, ≥1 tính được baseline Product có observations thực tế≤cutoff, preparation/execution adapteravailable; local missing history exclude affectedProduct. Empty/no computables blocked NO_COMPUTABLE_PRODUCTS; corrupt/incompatibleartifact blocker, not default fallback. |
| planning | Current readable/resolvable config+knownStorecap+requirements, ≥1 computedProduct, inventorydeclarations/datedrecipes/terms/fees/constraints in scope đã biết and valid, snapshot/preparation/forecast+planning worker compositionavailable, planning.run. Feecoverage/globalconstraintunknown blocks, not localpermission exclusion. |

CURRENT FACT D2 trong nhánh data-readiness: forecast eligibility assessment dùng
cùng choice với execution. All-censored/no usable baseline history trả existing
Product-scoped CENSORED_HISTORY_NOT_USABLE blocker (missing observations dùng
PRODUCT_HISTORY_MISSING); R01 trả assessment200 thay lỗi SERVICE_UNAVAILABLE503.
Artifact corrupt/incompatible giữ MODEL_ARTIFACT_INVALID/data invalid; recognized
dependency mismatch hoặc wrapped storage unavailable dùng EXECUTION_UNAVAILABLE/
execution unavailable, không reclassify thành history missing. Không success-fallback
cho các lỗi đó. DTO/routes giữ nguyên; internal selected method/reason/warnings
chưa thêm thành public fields. [Policy D2](features/DATA_READINESS_POLICY.md) sở hữu
chi tiết classification và [runbook](runbooks/FULL_TEST_FLOW.md#data-readiness-d2)
sở hữu commands/expected responses. Không đổi contextual Planning readiness trong D2.

công thức Product validity từng7 ngày horizon, units/loss/yield theoCatalog; localize
recipe/history/requiredinventory errors→estimated exclusions đúng Planning mục7,
không rejectwholeStore chỉ vì một Product. Supplier availability/constraints và
fee completeness đánh giá lại trên **scope computed ước lượng dependencies**, không
bảng catalog đơn thuần. Unknown dependencygraph/globalStorebudget/feecoverage
không đủ authority excludeđểcheblocker. knownnoeligibleoffer có thể dẫn đến engine
NO_ELIGIBLE_CANDIDATE; ready chỉ đủ **thực thi**, không guarantee feasibility/winner.
Availability của savedconfig không phụ thuộc recipeforecast của mỗioverride đã
review; saveable và executable tách.

Reason catalogue stable minimum: MENU_EMPTY,NO_COMPUTABLE_PRODUCTS,
PRODUCT_HISTORY_MISSING,RECIPE_MISSING,RECIPE_PERIOD_GAP,UNIT_MISMATCH,
INVENTORY_SCOPE_UNKNOWN,REQUIRED_EXPIRY_MISSING,SUPPLIER_TERM_MISSING,
PAYABLE_FEE_COVERAGE_UNKNOWN,UNSUPPORTED_FEE_RULE,LIMIT_CONFIGURATION_UNKNOWN,
COMMITTED_INBOUND_UNSUPPORTED,COMMITTED_INBOUND_UNKNOWN,BUDGET_CEILING_UNKNOWN,
REQUIREMENTS_INVALID,MODEL_CONFIGURATION_UNKNOWN,MODEL_ARTIFACT_INVALID,
ACTION_NOT_GRANTED,EXECUTION_UNAVAILABLE. Missingobservations distinct fromknown0;
history_watermark chỉ SALES_COVERAGE COMPLETE đếncutoff cho scope chính xác, không
maxsalesday. Partialhistory có thểbaseline-ready với warnings/correctmissing
semantics, không giảcomplete. Modelselection/fallback/historicaldate giữ ADR015/
Planning7; không task này chọn model mới hoặc thay algorithm.

C02 orchestration boundary: giữ cấu hình đã nhận → chuẩn bị Product scope,
observations thực, ngày/units/timezone và digest → xác minh model phục vụ cùng
artifact/features/postprocessing/dependency versions → reuse forecast đã lưu nếu
mọi identity/hash khớp và đủ7 ngày predictions finite/nonnegative → nếu không thì
thực thi forecast hiện có, ghi metadata model thực dùng → capture operational
facts nhất quán (inventory/recipe/supplier/fees/declarations/bounds) → đóng Sessions
→ chạy engine → lưu kết quả. Không reuse chỉ theo latestRun hoặc cutoff. Thay
budget/requirements/stock/giá không đổi identity forecast; Run mới vẫn capture
operational facts mới. History/scope đổi giữa prepare và capture: so digest,
chuẩn bị lại tối đa2 lần; hết lượt báo INPUT_CHANGED_DURING_CAPTURE. R01 không
bảo đảm facts giữ nguyên đến lúc C02; C02 kiểm lại. Queued receipt chỉ xác nhận
đã nhận, chưa xác nhận compute xong hoặc có winner.

Giữ readiness/fallback ADR015: trained ≥28 observations và ≥14 supervised rows
mỗi Product trong exact scope; baseline ≥1 observation. Đây là minima vận hành,
không cam kết độ chính xác. Artifact absent/not-ready hoặc baseline selection có
recognized fallback và provenance; artifact corrupt/incompatible, programming/DB
errors không thành công nhờ fallback. Cấu hình model phục vụ có version từ registry
được thiết lập có hỗ trợ; không chọn file mới nhất trong thư mục hoặc train trong GET.

Offer bound phải hữu hạn: declared SupplierLimit đủ scope cho phép floor(quantity/
pack_size). Khi không có giới hạn nghiệp vụ, known budget và pack_cost>0 cho safe
upper floor(budget/pack_cost), vì phí không âm. Adapter ghi source=TECHNICAL_SEARCH_LIMIT,
derivation gồm budget/term versions, không giả đây là giới hạn Supplier. Offer
cost0 và không có bound kinh doanh cần technical search limit có version/provenance;
thiếu thì OFFER_BOUND_UNKNOWN. Mọi chứng nhận giữ proof_scope
CAPTURED_FINITE_DOMAIN_ONLY, không gọi tối ưu toàn miền vô hạn.

### 14.3. C01 và I06 adapters

C01 readiness giữ các fields cũ và thêm assessment/forecast nêu trên: status=ready khi planningavailabilityready; not_ready
khi blocked; unknown khiunknown; can_generate=can_execute; reason_codes lấy distinct
blockingcodes, evaluated_forecast_start_date/scope_estimate/history_watermark cùng
evaluation. Context_version cover source_versions + resolver cấu hình versions, không
solveGET. C01 vẫn từ chối toàn response khi thiếu quyền P2, không genericR01 defaultactions expansion.

I06 readiness={evaluated_at,as_of_date,data_version,actions:ActionReadiness[]}, pin
versions của trạng thái sau các canonical writes **trong cùng transaction** trước
persist receipt và commit; không gap “commit rồi mới tạo receipt”. Known evaluator
unknown/runtimeunavailable không biến canonical batch hợp lệ thành lỗi dữ liệu;
receipt ghi unknown/blocked, không claimready. Unexpected write/storage failure vẫn
rollback atomic cả writes và receipt. Chỉ requested
actions actor đủ quyềnread được lưu vào projection, defaultimport/menu/inventory
intersect readpermissions; response có evaluated_actions và omitted_actions chứa
names-only lý do NOT_AUTHORIZED, không facts. Đây là explicitprojection, không
partialdrop nhóm canonical. I06 fullimportdomains readrights vẫn mục10 wholedeny.
R01 selectedactions refetchnewfacts; retainedI06 không recalc giữa retries.

```json
{"data":{"store_id":"00000000-0000-0000-0000-000000000001","as_of_date":"2026-10-09","evaluated_at":"2026-10-09T02:00:00Z","data_version":"sources-9","evaluated_forecast_start_date":"2026-10-09","cutoff_date":"2026-10-08","actions":[{"action":"planning","availability":"blocked","can_execute":false,"data_status":"incomplete","execution_status":"available","blockers":[{"code":"PAYABLE_FEE_COVERAGE_UNKNOWN","source":"fees","scope":"STORE","entity_id":null,"affected_dates":[],"details":{}}],"warnings":[],"result_assessment":"NOT_ASSESSED"}],"source_versions":{"catalog":"cat-1","recipes":"recipes-1","inventory":"stock-8","sales":"sales-2","suppliers":"terms-1","fees":null,"declarations":"decl-1","planning_config":"cfg-1","model_config":"model-1"},"scope_estimate":{"menu_product_count":1,"estimated_computable_product_count":1,"excluded_products":[]},"history_watermark":null},"meta":{"request_id":"req-ready"},"error":null}
```

### 14.4. Errors/acceptance/backlog

R01 general400/401/403/404/422 INVALID_FILTER/VALIDATION_ERROR,503 temporaryStore
sourceunavailable; thiếu business facts đã xác định returns200 blocked/unknown, not transport
500 or solver failure. ReadinessIssue không exceptionstack. Acceptance criteria:
Menu được xác định rỗng readerready/plannotready; không có lịch sử≠0; localrecipeinvalidexclusions
vsglobalfeesunknown; validdata workerunavailable; revokedread403; GET no solver/
LLM/train; C01projection samecodes/versions; I06pointintimeimmutable; afterprice
change newoperationalcapture/forecastreuseidentity unchanged; historychange breaks
reuse; no proof của winner fromreadiness. CURRENT FACT evaluator/loaders/
versionedscope declarations/executionavailability probes/forecastreuse orchestration,
I06 atomic retained projection/C01projection đã triển khai ở các public slices S4.

### 14.5. J01 shared job contract — canonical, mở rộng cho PDF

GET /jobs/{job_id}, không body/query; resolve owning Store trước authorization.
Import job đòi import.read + toàn bộ domain/sensitive reads của batch mục10;
PDF job đòi planning.export+planning.result.read+budget.read+procurement.cost.read.
Same Store/grants là authority, không chỉ biết job UUID; cross-Store404,
revoked/thiếu grants403. Không cần jobservice hoặc broker riêng; one-process
durable orchestration hiện đã wired; readiness dùng worker availability thực tế.

Job={job_id:UUID,operation:import_analyze|import_preview|import_commit|planning_pdf_export,
status:queued|running|completed|failed,stage:queued|parsing|mapping|validating|
committing|rendering|completed|failed,progress:number0..1|null,
created_at:Timestamp,started_at:Timestamp|null,completed_at:Timestamp|null,
context:ImportJobContext|ExportJobContext,result:JobResult|null,
error:{code,message,details}|null}.
ImportJobContext={store_id,import_id}; ExportJobContext={store_id,run_id,export_id}.
JobResult discriminated resource_type:

- import_analysis: {resource_type,resource_id:import_id,analysis_id};
- import_preview: {resource_type,resource_id:import_id,preview_id};
- import_completion: {resource_type,resource_id:import_id,commit_id};
- planning_pdf_export: {resource_type,resource_id:export_id,run_id,option_id,
  download_url:string relative,sha256:string64 lowercasehex,byte_count:int>0,
  media_type:"application/pdf"}.

IDs đúng UUID/OptionId theo cluster; không undefined object output thứ hai.
Queued/running result/error=null, progressnull nếu không đo được; completed có
result, errornull; failed resultnull và errorrequired, stagefailed, completed_at
là terminal timestamp kể cả failure. GET failed vẫn200 job envelope, không giả
canonical success. Meta={request_id,poll_after_ms:2000 khi nonterminal,0 khi terminal,
warnings:Notification[]}; không stage/progress mô tả proof tối ưu. Unknownjob404.
Async POSTs trả job_id trỏ aggregate này, C02/C03 không đổi sang job_id. Export
completed chỉ sau durable artifact receipt; import completed chỉ sau retained
phase result/atomic commit receipt. Acceptance: unauthorized poll deny; failed200
đúng error, no result; crash reconcile receipt trước retry; export progress không
compute lại Run. Implementation backlog jobs/auth/typedprojection như các cụm.


## Alignment đã được duyệt — 11/10/2026 (CA-002/016/020/021)

ACCEPTED CONTRACT: Staff có mapping.propose và các grants đọc cần thiết có thể
explicit IGNORE sheet trong batch của mình trước canonical commit. Cần acknowledgment
và reason/evidence file-sheet; không cần N5/Owner riêng cho exclusion này. Source
bytes/file quota không giảm. Invalidate preview/confirmation; completed batch không
đổi scope. Mapping/profile reusable vẫn cần Owner approval và immutable version.

I05 commit reason là conditional theo effective retained rows: REPLACE_DAILY_TOTAL,
MERGE_DISJOINT_SALES, COUNT_CORRECTION, AMEND_TERM_PERIOD, AMEND_FEE_PERIOD cần
nonblank reason; thiếu trả422 COMMIT_REASON_REQUIRED trước job acceptance. Pure
inserts và NO_OP thường không bắt nhập reason. Source count/fee reasons, supplier
confirmations và confirm_review.reason vẫn giữ độc lập, lưu audit/provenance.

| Loại | Prose/DTO/FE descriptor hiện hành | Domain/writer | Storage và compatibility |
| --- | --- | --- | --- |
| Source business keys (Product/Ingredient/Supplier/term/fee/declaration/component/report) | nonblank1..1000; case-sensitive; không truncate | Exact scoped identity; không fuzzy | JSONB/raw key1000 + scoped SHA-256 index nơi cần; blob identity độc lập |
| source_system_key/report_type trong profile scope | Code1..128 grammar hiện hành | Store-scoped namespace | Không mở lên1000: khác source business key |
| Money price/pack_cost/component.amount/N6.unit_cost | unsigned decimal, ≤18 integer + ≤18 fractional digits, không exponent/number | Exact Money bounds; Quantity không dùng Money bounds | NUMERIC không typmod/JSON decimal text lưu exact, không rounding; không migrate/viết lại evidence cũ |
| Quantity/yield/loss/on_hand/pack_size | unsigned plain decimal text≤200 chars, positivity/loss rules riêng | Exact Decimal/Fraction quantity | NUMERIC không fixed scale; không ép18/18 |

Compatibility: inputs Money mới vượt bounds bị validation/blocker, không nới Money
để khớp implementation cũ. Retained preview before/after đã accepted được đọc qua
explicit retained-evidence validation, output schema historic exact decimal≤200
khác input Money18/18; không sửa bytes/digest/audit; không được dùng
legacy bypass để tạo writes mới. Pending proposals/jobs có tiền vượt bounds cần
re-review/re-preview hợp lệ trước canonical writes (409 LEGACY_MONEY_REVIEW_REQUIRED
cho old preview vượt Money); không tự sửa/round evidence.
Internal legacy results vẫn đọc exact. Public catalog projection ngoài MoneyText
có thể trả503 representation/integrity error, không giả thành null/round.
Các absence/current clauses của S4.4/S4.5 bên trên là lịch sử ở thời điểm slice;
CURRENT FACT thực tế xem CURRENT_STATE/feature hiện hành, không dùng làm authority
rằng commit vẫn unsupported. Handoff ZIP cũ chưa phát hành lại.

<a id="mapping-queue"></a>
## 15. Submit và queue duyệt mapping toàn Store — IMPLEMENTED C2

ACCEPTED DECISION: Staff chuẩn bị → explicit “Gửi chủ quán duyệt” → Owner đọc pinned
proposal → N5 quyết định → Staff xem kết quả/sửa/resubmit. Draft không tự thành
queue task. CURRENT FACT: MQ01–MQ03 tại `app/api/mapping_submissions.py` và
`MappingSubmissions`; retained aggregate từ migration0026. N5 tại
`ImportStaging.decision` nhận approve_activate/reject/request_changes/retire;
live submitted được resolve/pin cả khi direct N5 không gửi submission fields.
Commands/verification ở [FULL_TEST_FLOW](runbooks/FULL_TEST_FLOW.md#collaboration-c2).
N5 approve_activate là approve và activate cùng command, không thêm approve endpoint.

TECHNICAL CHOICE: một submission là **một profile proposal đầy đủ**, có toàn bộ
column mappings/declarations/identity/normalizations/entity reservations theo
ProfileSpec hiện có. Group approval trong N5 nghĩa toàn full spec của proposal
đó, không bulk nhiều profile. Batch có nhiều profile gửi từng profile riêng; queue
không giả một quyết định atomic cross-profile. Owner tự duyệt draft trong batch
qua N5 vẫn được (ADR-013), draft đó không vào queue nếu chưa submit.

```text
MappingSubmission={submission_id:UUID,store_id:UUID,profile_id:UUID,
 import_id:UUID,sheet_id:UUID,file_id:UUID,submitted_by_user_id:UUID,
 submitted_at:Timestamp,reason:string,version:Version,
 state:submitted|changes_requested|approved|rejected|stale|withdrawn,
 proposal_revision:Version,mapping_revision:Version,import_revision:Version,
 file_set_version:Version,lifecycle_revision_at_submission:Version,
 spec_digest:Version,expected_active_version:Version|null,
 review_eligibility:{eligible:boolean,reason_codes:string[]},
 current_profile:{lifecycle_revision:Version,active_version:Version|null,
                  reviewed_version_retired:boolean},
 decision:{decision_id:UUID,decision:approve_activate|reject|request_changes,
           actor_user_id:UUID,reason:string,decided_at:Timestamp}|null,
 allowed_actions:string[]}
MappingReviewDetail={submission:MappingSubmission,
 source:{file_id:UUID,filename:string,sheet_id:UUID,sheet_name:string,
         source_system_key:string,report_type:string,schema_signature:Version,
         evidence_references:string[]},
 spec:ProfileSpec,warnings:Notice[],missing_fields:string[],
 evidence:{cells:SourceEvidenceCell[],next_cursor:string|null,total_count:int}}
```

ProfileSpec/Notice dùng current DTO (extensions receipt xem mục16); không duplicate
source schema. EvidenceCell dùng [projection mục17](#mapping-projections), không
full workbook. Submitted eligibility: analyzed/sealed immutable bytes, batch chưa
commit/active job, complete source scope+spec, mọi required semantic unresolved đã
giải quyết hoặc là deterministic candidate có evidence đầy đủ đủ Owner duyệt nhóm;
missing_fields=[]; không đòi đã active profile hay preview row-valid mới submit.
Invalid data rows vẫn do preview xử lý, không giả mapping review đã validate stock.

| ID/status | Method/path | Request → response |
| --- | --- | --- |
| MQ01 IMPLEMENTED | POST /imports/{import_id}/mapping-submissions | Staff own batch (Owner cũng được), import.read+mapping.read+mapping.propose và batch sensitive reads như M04; Origin/CSRF/Idempotency-Key/If-Match import_revision. {action:"submit",profile_id:UUID,proposal_revision:Version,mapping_revision:Version,reason:string} hoặc {action:"withdraw",submission_id:UUID,expected_submission_version:Version,reason:string} → 201 submit/200 withdraw MappingSubmission. |
| MQ02 IMPLEMENTED | GET /stores/{store_id}/mapping-submissions | Owner toàn Store, Staff own submissions; import.read+mapping.read+domain read rights theo nguồn; query state?:enum,file_id?:UUID,import_id?:UUID,limit/cursor; sort -submitted_at/UUID. → 200 {items:MappingSubmission[]}. |
| MQ03 IMPLEMENTED | GET /stores/{store_id}/mapping-submissions/{submission_id} | Same scope; query evidence_limit1..100 default20,evidence_cursor? → 200 MappingReviewDetail, ETag submission.version. |
| N5 và queue extension IMPLEMENTED | POST /stores/{store_id}/mapping-profiles/{profile_id}/decisions | Owner-only hiện hành; giữ If-Match lifecycle_revision + Idempotency-Key. Queue decision thêm submission_id:UUID,expected_submission_version:Version; union approve_activate/reject hiện có + request_changes với proposal_revision/reason. → 200 DecisionResult hiện có + submission:MappingSubmission|null,notification_delivery. |

MQ02 omitstate: Owner chỉ submitted **eligible hiện hành**, Staff tất cả own;
explicit state cho lịch sử. Mọi rows check batch-sensitive permissions trước trả
source/evidence; danh sách có scope forbidden không silent page filter/count leak:
deny whole response403 như Import hiện hành. Owner toàn catalogue vẫn đủ đọc.
MQ03 trả pinned spec/evidence của submission, current_profile để báo drift; không
thay spec bằng live proposal. Queue snapshot pin submissions/profile/batch/revisions;
GET không mutation. MQ03 evidence pagination pin spec_digest/versions/actor;
đọc captured source bất biến, chỉ dựng requested page, không reparse/provider.
Source digest/header/offset index retained cùng pins; display vượt200 ký tự trả
null + SOURCE_CELL_DISPLAY_UNAVAILABLE warning, original bytes vẫn retained.

Submit lưu immutable spec/content digest và mọi pins + audit + notification intent
atomic; một live submitted/profile, duplicate newkey409 MAPPING_ALREADY_SUBMITTED,
trả existing_submission_id trong own scope. Same key retry không tạo task/event mới.
Submit stale pins409 MAPPING_SUBMISSION_STALE, unresolved409 REVIEW_NOT_READY với
missing fields/blockers; If-Match mismatch412 IMPORT_REVISION_CONFLICT. Withdraw chỉ
submitter hoặc Owner, submitted→withdrawn; không reject profile, không notification
bắt buộc. MQ01 trả current import ETag; submit/withdraw không đổi import/mapping
content revision, chỉ đổi submission revision. Response submission.version riêng,
không nhầm hai CAS domains hoặc tự làm pins stale do submit. Không edit immutable submission.

M04/scope/analyze thay pinned content sau submit: atomically mark submitted stale
(giữ historical pinned spec), tăng affected revisions và invalidate preview như cũ.
Chỉ lifecycle active pointer đổi cũng làm eligibility stale cho approve vì
expected_active_version/lifecycle fence; không tự approve revision mới. Nếu phát
hiện drift ở read, effective state stale, không write từ GET. Owner refetch MQ03,
UI disable stale decision. Staff sửa xong explicit submit mới (new submission ID),
không auto-resubmit/auto-task từ M04. changes_requested/rejected/withdrawn/stale
terminal cho submission cũ; profile draft mới có proposal_revision mới.

N5 queue extension kiểm tất cả pins/current authority dưới profile+batch locks cùng
command hiện hành, atomically update profile lifecycle + submission + decision audit
+ notification intent + receipt. Queue callers bắt buộc hai submission fields;
direct batch N5 không cần submission fields, nhưng nếu profile có live submitted
thì decision vẫn phải resolve/pin chính submission đó, không bypass queue fence.
request_changes không activate/reject profile, giữ active version cũ, terminal
changes_requested và reason; Staff tiếp tục M04 rồi submit mới. reject giữ active
version cũ như hiện hành. approve_activate tạo immutable version từ exact pinned
spec, không commit batch. N5 retire vẫn chỉ active_version/reason và current
lifecycle ETag, không cần submission ID; đánh dấu affected live submission stale.
Approved submission vẫn approved khi version bị retire; current_profile flag true,
allowed_actions không approve lại. Retired version không dùng cho fresh reuse;
retained historical import/decision vẫn giữ facts.

N5 stale request412 PROFILE_REVISION_CONFLICT, submission stale409
MAPPING_SUBMISSION_STALE, incompatible terminal409 MAPPING_SUBMISSION_STATE_CONFLICT.
Concurrent Owner decisions một winner; replay trước stale CAS sau current rights
trả retained receipt, không tạo version/notification thứ hai. Notification failure
sau commit không undo activation; audit/notification cùng decision_id.
Queue/detail và mapping approval notification dùng wording **“Profile đã được duyệt;
mở batch để kiểm tra và tiếp tục nhập.”**, không “Dữ liệu đã nhập thành công”.
Link notification trỏ submission_id, MQ03 đọc current state/eligibility với pinned
spec/digest; stale/resubmit không thay pin của submission cũ. Read/unread hoặc mất
notification không approve/reject/withdraw và không xóa task: MQ02/MQ03 mới là task
discovery/detail authority, N5 là decision command. Row correction/conflict vẫn
do I04/I05/resolutions đúng schema, không đưa business overwrite vào queue approval.

Ví dụ MQ01 request → MappingSubmission; MQ02.items reuse cùng DTO:

```json
{"action":"submit","profile_id":"00000000-0000-0000-0000-000000000061","proposal_revision":"proposal-3","mapping_revision":"mapping-3","reason":"Đã kiểm tra nguồn và quy ước"}
```

```json
{"submission_id":"00000000-0000-0000-0000-000000000062","store_id":"00000000-0000-0000-0000-000000000001","profile_id":"00000000-0000-0000-0000-000000000061","import_id":"00000000-0000-0000-0000-000000000063","sheet_id":"00000000-0000-0000-0000-000000000064","file_id":"00000000-0000-0000-0000-000000000065","submitted_by_user_id":"00000000-0000-0000-0000-000000000002","submitted_at":"2026-10-13T02:00:00Z","reason":"Đã kiểm tra nguồn và quy ước","version":"submission-1","state":"submitted","proposal_revision":"proposal-3","mapping_revision":"mapping-3","import_revision":"import-5","file_set_version":"files-2","lifecycle_revision_at_submission":"profile-1","spec_digest":"spec-3","expected_active_version":null,"review_eligibility":{"eligible":true,"reason_codes":[]},"current_profile":{"lifecycle_revision":"profile-1","active_version":null,"reviewed_version_retired":false},"decision":null,"allowed_actions":["withdraw"]}
```

Ví dụ N5 queue approval và yêu cầu sửa (hai variants; If-Match="profile-1"):

```json
{"decision":"approve_activate","proposal_revision":"proposal-3","expected_active_version":null,"reason":"Đồng ý full spec","submission_id":"00000000-0000-0000-0000-000000000062","expected_submission_version":"submission-1"}
```

```json
{"decision":"request_changes","proposal_revision":"proposal-3","reason":"Bổ sung bằng chứng đơn vị nguồn","submission_id":"00000000-0000-0000-0000-000000000062","expected_submission_version":"submission-1"}
```

Ví dụ MQ03 phần `data.source` và `data.evidence` (response còn có submission đầy
đủ như ví dụ MQ01 và spec theo typed ProfileSpec, không phải response rút gọn runtime):

```json
{"source":{"file_id":"00000000-0000-0000-0000-000000000065","filename":"suppliers.xlsx","sheet_id":"00000000-0000-0000-0000-000000000064","sheet_name":"Suppliers","source_system_key":"supplier-a","report_type":"supplier-catalog","schema_signature":"headers-1","evidence_references":["source-catalog:SUP-A"]},"evidence":{"cells":[{"location":{"file_id":"00000000-0000-0000-0000-000000000065","sheet_id":"00000000-0000-0000-0000-000000000064","row_number":2,"source_column_index":1,"record_number":null,"line_start":null,"line_end":null},"column_label":"Mã nhà cung cấp","raw_value":"SUP-A","cell_kind":"text","formula_present":false}],"next_cursor":null,"total_count":1}}
```

Ví dụ N5 response fields hiện có (queue extension còn có submission và
notification_delivery cùng decision_id):

```json
{"profile_id":"00000000-0000-0000-0000-000000000061","approved_version":"approved-1","active_version":"approved-1","lifecycle_revision":"profile-2","decision_id":"00000000-0000-0000-0000-000000000066","decided_at":"2026-10-13T02:05:00Z","audit_id":"00000000-0000-0000-0000-000000000067"}
```

Allowed actions computed: submitted eligible Owner approve_activate/reject/
request_changes (+withdraw), submitter withdraw; terminal chỉ view (resubmit là
new submission sau sửa draft). Audit submit/withdraw/stale giữ actor/source/pins;
decisions vẫn ImportAudit, không permission grant/audit. HTTP/PostgreSQL acceptance
ở `tests/integration/test_mapping_submissions.py` và
`tests/integration/test_collaboration_boundaries.py`; typed API ở
`tests/api/test_collaboration_openapi.py`. Retained pinned evidence, stale edits,
retirement, direct N5 queue resolution, rollback/retry/dispatcher và sensitive
target denial được kiểm bằng fresh sessions. Browser continuation chưa chạy.

<a id="excel-actual-receipt"></a>
## 16. Excel hàng thực nhận — IMPLEMENTED C3

ACCEPTED DECISION: actual receipt là hàng đã thực nhận; opening stock, count,
purchase history và Planning purchases giữ nghiệp vụ riêng. CURRENT FACT: registry
có mười lăm variants, gồm `inventory_receipts`, trong `import_schema/1`.
Reusable receipt ProfileSpec yêu cầu inventory_semantics="actual_receipt".
M03 advertises source fields; mapping/preview/commit/completion dùng pipeline hiện có.
StockWrites.receive (N6), Excel actual và opening cùng `InventoryReceipts` →
`InventoryUseCases.receive_in_transaction`, cùng ledger `InventoryReceiptRecord`;
không HTTP loop, endpoint mới hoặc commit từng dòng. Caller giữ transaction,
current authorization và inventory/read-set fences.

Mapping giữ reviewed unit/currency constants, batch-only IMPORT_VALUE và raw
source/declaration/location/conversion provenance. Receipt facts không reusable
defaults. observed_at cần timestamp ISO với timezone explicit; numeric/Excel serial,
date-only và naive timestamp bị chặn, không suy timezone/date từ upload.

```text
ActualReceiptValue={origin:"ACTUAL_RECEIPT",
 receipt_identity:{source_system_key:string1..128,source_record_id:string1..128},
 ingredient_id:UUID,supplier_id:UUID|null,lot_code:string1..128|null,
 quantity:PositiveQuantityText,unit:string exact Ingredient.base_unit,
 received_date:date|null,expiry_date:date|null,unit_cost:MoneyText|null,
 currency:string exact Store.currency,observed_at:Timestamp,reason:string}
ReceiptEffect={action:CREATE_RECEIPT|REUSE_RECEIPT|BLOCKED,
 source_identity:{source_system_key:string1..128,source_record_id:string1..128},
 receipt_id:UUID|null,lot_id:UUID|null,movement_id:UUID|null,
 origin:"ACTUAL_RECEIPT",movement_kind:"receipt",
 quantity_delta:PositiveQuantityText,unit:string,
 occurred_at:Timestamp,recorded_at:Timestamp|null,
 conflict_code:string|null}
```

Nullable keys vẫn bắt buộc có null. Unknown supplier/cost không0, không bắt Supplier
Term cho receipt; cost known0 hợp lệ. Quantity>0, exact unit, currency; known received
date≤Store today, expiry≥known receipt; tracked ingredient required expiry như N6.
observed_at phải known≤server now, là event hàng thực nhận (occurred_at), không ngày
upload. Late receipt cho phép đúng CA-019 với LATE_RECEIPT_RECORDED warning; không
silently backdate recorded_at hoặc sửa Run lịch sử. Location/warehouse unsupported,
source columns chỉ source-only/explicit IGNORE reviewed, không mandatory fake values.
Không nhận opening stock bằng origin khác trong schema actual receipt.

I01–I03 bytes/seal/analyze, M01–M04 và N5 mapping review **IMPLEMENTED routes**;
schema receipt đã IMPLEMENTED C3. I05 body giữ các phases hiện hành:
preview{phase,mapping_revision}, confirm_review{phase,preview_id,preview_digest,
mapping_revision,confirm:true,reason}, commit{phase,preview_id,preview_digest,
confirm:true,reason?,resolutions:SalesResolution[],supplier_changes?:SupplierConfirmation[]}.
Receipt-only resolutions=[]; không post canonical row từ FE hoặc gọi N6 từng dòng.
I05 preview/commit202 job acceptance, confirm_review200; J01 poll2s; I04 đọc pinned
preview, I06 durable completion. Request JSON/phases xem mục9.3 và current DTO;
chỉ thêm receipt variant trong rows/effects/completion, không thêm operation.

Preview pin inventory_version/read-set dùng chung trong batch, không yêu cầu user
nhập CAS từng dòng Excel. Owner đọc source→canonical→lot/movement effect trước
confirm. New planned IDs stable trong immutable preview (reserved, không chứng
minh inserted); recorded_at=null tới commit, không giả server time tương lai.
Existing same identity+normalized payload REUSE_RECEIPT có retained IDs/recorded_at;
different payload BLOCKED RECEIPT_IDENTITY_CONFLICT, không upsert quantity/cost.
File hash/filename/row_number/lot_code không business identity. Owner phải khai
source namespace và per-receipt source_record_id ổn định, không tự tạo từ new file.
Rows trong batch trùng identity cùng payload coalesce một action, giữ mọi physical
source_locations và per-source transformation evidence trong nested_provenance
`receipt_sources[index]`; khác payload blocker toàn batch. Identity phải dùng chung N6
ledger: Excel rồi form/reverse retry cũng chỉ một receipt/lot/movement.

Commit dùng cùng receipt identity/domain writer **trong transaction toàn import**,
không HTTP loop hoặc một commit/dòng. Current auth fence và canonical locks/receipt
CAS/read-set chung; stale409 PREVIEW_STALE, FE refresh preview và confirm lại.
Receipt preview qua ngày mới theo Store timezone cũng stale ở confirm/commit để
không dùng warning expiry/late của ngày cũ. Raw supplier/cost nonblank yêu cầu
sensitive read trước capture/projection; cost "0" là nonnull, không bị bỏ guard.
Recheck import.commit+inventory.receive+inventory.read+ingredient.read; supplier_id
nonnull thêm supplier.read để đọc/bind locator; unit_cost nonnull thêm procurement.cost.read;
Import whole-response sensitive rights như mục10 vẫn áp toàn affected schema (cả
preview/history/completion), không dùng N6 lot redaction để leak mixed workbook.
Không bypass vì Owner đã approve profile; row validation/preview/write rights giữ.

Replay I05 cùng key trả retained job acceptance sau current rights; job publish
identity+lot+movement+receipt+audit+completion atomically. Crash uncertain commit
đối chiếu durable import và shared receipt ledger trước retry, không tạo new receipt
do key khác. Completion extension row reference={source_identity,receipt_id,lot_id,
movement_id,action:"CREATED"|"REUSED",audit_reference:UUID}, ở
`CommitRowReference.receipt_reference`; receipt_effect giữ planned/retained IDs và
recorded_at sau commit. REUSE_RECEIPT.quantity_delta là lượng movement đã ghi,
không phải tăng kho lần nữa; inventory.updated=false cho receipt-only replay.
Actual created effects
khác raw row count. Không receipt khácunits quantity sum, không tổngunknowncost0.
NO_OP batch duplicate vẫn có outcome riêng; không xác nhận stock completeness từ
một receipt. PlanningRun purchases/hypothetical arrival không input actual receipts.

Ví dụ canonical receipt row sau mapping (không phải I05 request):

```json
{"origin":"ACTUAL_RECEIPT","receipt_identity":{"source_system_key":"supplier-a-deliveries","source_record_id":"DN-20261013-001-L1"},"ingredient_id":"00000000-0000-0000-0000-000000000003","supplier_id":null,"lot_code":"DELIVERY-01","quantity":"5","unit":"l","received_date":"2026-10-13","expiry_date":"2026-10-20","unit_cost":null,"currency":"VND","observed_at":"2026-10-13T02:00:00Z","reason":"Nhận thực tế theo phiếu DN-001"}
```

```json
{"action":"CREATE_RECEIPT","source_identity":{"source_system_key":"supplier-a-deliveries","source_record_id":"DN-20261013-001-L1"},"receipt_id":"00000000-0000-0000-0000-000000000071","lot_id":"00000000-0000-0000-0000-000000000072","movement_id":"00000000-0000-0000-0000-000000000073","origin":"ACTUAL_RECEIPT","movement_kind":"receipt","quantity_delta":"5","unit":"l","occurred_at":"2026-10-13T02:00:00Z","recorded_at":null,"conflict_code":null}
```

Errors: N6 domain codes INVALID_UNIT/REQUIRED_EXPIRY_MISSING422,
RECEIPT_IDENTITY_CONFLICT409 hoặc preview blocker, PREVIEW_STALE409,
PERMISSION_DENIED403, RESOURCE_NOT_FOUND404 scoped; common key/CSRF/job errors
mục9–11. FE sửa declaration/source identity có evidence, không đổi key để lách
duplicate. CURRENT FACT acceptance: public HTTP → worker → PostgreSQL → fresh-session
inventory, nullable/known0/expiry/unit/late facts, Excel↔N6 replay, reversed duplicate
order, current Staff grants/MQ/N5, retirement/spec drift, rollback/lost ACK/concurrency
và retained PlanningRun được kiểm tại [runbook](runbooks/FULL_TEST_FLOW.md#excel-actual-receipt-c3).
Browser/runtime8103 chưa nâng cấp/kiểm C3; C4 projections không thuộc lát này.

<a id="mapping-projections"></a>
## 17. Counters và source→canonical→effect — IMPLEMENTED C4

CURRENT FACT: M01 có Progress/files/sheets/profile details; M02 có sheet_id,
review_only/status/include_details/limit/cursor và MappingList.counts; issue origins
tách resolution_origin APPROVED_PROFILE|USER_PROPOSAL|UNRESOLVED và suggestion_origin
RULE|QWEN|REUSED|MANUAL|NONE. I04 có include_preview/preview_id/rows_limit/rows_cursor/
classification/configurations; PreviewRow có source_location/provenance/before/after,
supplier_term_semantics và recipe provenance. C4 bổ sung counters/source projection dưới đây, không đổi nghĩa Progress hiện hành.

M01 GET extension query file_id?:UUID,sheet_id?:UUID,review_only?:boolean,
status?:MappingStatus,origin?:SuggestionOrigin; filters AND, cùng enum hiện có.
M02 GET thêm file_id/origin, giữ queries hiện hữu. `origin` lọc **suggestion_origin**,
không nhầm resolution_origin. response extension:
{mapping_revision:Version,counter_scope:{file_id:UUID|null,sheet_id:UUID|null,
review_only:boolean,status:MappingStatus|null,origin:SuggestionOrigin|null},
counters:{batch:{total:int,by_status:StatusCounts,by_origin:OriginCounts},
filtered:{total:int,by_status:StatusCounts,by_origin:OriginCounts}}}.
StatusCounts có đủ five status keys; OriginCounts đủ five origin keys, known zero0.
Counter đơn vị **mapping issues**, classification/identity/conversion issues cùng
phạm vi M02, không số rows/cells/files. review_only defaulttrue như M02; batch
unfiltered, filtered áp chính filters request, không page-length. M01 legacy
progress không đổi nghĩa. M01 counters và M02 page pin cùng mapping_revision;
M02 thêm snapshot_id? để bind, changed409 SNAPSHOT_NOT_AVAILABLE.
snapshot_id của M02 là mapping_revision từ M01, không quoted HTTP ETag. Filters
áp counters/issues; legacy M01 files/sheets là batch metadata, không totals từ page.

Ví dụ counter extension M02 (một column issue từ RULE, filter cùng revision):

```json
{"mapping_revision":"mapping-3","counter_scope":{"file_id":null,"sheet_id":null,"review_only":true,"status":"needs_confirmation","origin":"RULE"},"counters":{"batch":{"total":1,"by_status":{"auto_mapped":0,"resolved":0,"needs_confirmation":1,"ambiguous":0,"unmatched":0},"by_origin":{"RULE":1,"QWEN":0,"REUSED":0,"MANUAL":0,"NONE":0}},"filtered":{"total":1,"by_status":{"auto_mapped":0,"resolved":0,"needs_confirmation":1,"ambiguous":0,"unmatched":0},"by_origin":{"RULE":1,"QWEN":0,"REUSED":0,"MANUAL":0,"NONE":0}}}}
```

I04 GET extension preview query file_id?:UUID,sheet_id?:UUID,projection?:
summary|source_effect (defaultsummary); chỉ hợp lệ khi include_preview=true cùng
preview_id. Response rows PreviewRow current + source_cells:SourceEvidenceCell[]
và planned_effect: typed union ReceiptEffect|CatalogEffect|CountEffect|RecipeEffect|
SupplierEffect|SalesEffect|DeclarationEffect|OpeningEffect|HistoryEffect. summary không cells/effect extension;
source_effect chỉ selected rows page, không toàn workbook. SourceEffectRow giữ
PreviewRow fields và thêm source_cells/planned_effect/source_evidence_availability
(available|partial|unavailable), source_cells_truncated. Tối đa200 cells/action và
2000 cells/page; bounds không thay canonical facts hoặc aggregate totals.
PreviewPage thêm mapping_revision/read_set_digest/source_evidence_digest; full
internal read_set vẫn private. New preview pin digest cached sources và read
permissions trong immutable payload. Old preview thiếu source pin trả unavailable
evidence/raw count=null; không parse lại bytes hoặc lấy mapping mới làm evidence.
Quyền của pinned preview được kiểm cả trước projection và fresh-authority readback;
đổi mapping không hạ sensitive guard của preview cũ.
File/sheet filters chọn logical actions có location liên quan. Mỗi action vẫn giữ
toàn bộ locations và bounded evidence của chính action, kể cả location ở file scope
khác; raw aggregate count chỉ đếm intersection đang chọn. Không lấy số cells hoặc
toàn bộ locations của returned action để suy scoped raw total.

```text
SourceEvidenceCell={location:SourceLocation,column_label:string|null,
 raw_value:string|null,cell_kind:text|numeric|boolean|date|empty|error,
 formula_present:boolean}
CatalogEffect={kind:"catalog",entity:product|ingredient|supplier,id:UUID,
 action:create|reuse,expected_version:Version|null}
CountEffect={kind:"count",lot_id:UUID,before_quantity:QuantityText,
 after_quantity:QuantityText,delta:SignedQuantityText,unit:string,
 expected_version:Version}
RecipeEffect={kind:"recipe",product_id:UUID,recipe_id:UUID|null,
 identity_availability:available|not_reserved,recipe_version:int,action:create_version|reuse,
 effective_from:date,effective_to:date|null,dependency_ids:UUID[]}
SupplierEffect={kind:"supplier",entity:supplier_term|payable_fee,id:UUID,
 action:create_version|close_period|reuse,expected_version:Version|null}
SalesEffect={kind:"sales",product_id:UUID,date:date,
 action:record|replace|merge|reuse,before_quantity:QuantityText|null,
 after_quantity:QuantityText,unit:string,expected_version:Version|null}
DeclarationEffect={kind:"declaration",id:UUID,action:declare|reuse,
 dependency_ids:UUID[],expected_version:Version|null}
```

CURRENT FACT / TECHNICAL DEBT: example thiết kế RecipeEffect ban đầu dùng UUID
bắt buộc, nhưng writer hiện hành chỉ cấp recipe_id lúc commit. C4 trả null với
identity_availability=not_reserved và Product/version/date/dependencies, không bịa
reserved identity hoặc sửa writer chỉ để dựng GET. Reuse effect có action=reuse.
OpeningEffect (kind=opening_stock) giữ lot_id/quantity_delta/unit/observed_at và
action create|reuse; HistoryEffect giữ domain/id/action record|reuse/expected_version.
Đây là typed projections của nghiệp vụ đã có, không receipt/count/history mới.
`dependency_ids` là `row_id` của các planned actions phụ thuộc; canonical entity IDs
vẫn thuộc `entity_refs`/`nested_references`, không suy ra từ action IDs.

ReceiptEffect thêm kind="receipt" khi union; canonical before/after giữ typed
current CanonicalValue+ActualReceiptValue, không dictionary tùy ý. Raw null là
empty/unknown source, không unknown canonical0. Formula chỉ báo presence, raw_value
là cached visible value, không formula expression/external links. Source không
established/unsupported chỉ blocked row+Notice; planned_effect=null khi không thể
xác định action, không fabricated type/value. C4 reuse SourceEvidenceCell và bounded display builder với C2 MQ03. Source cell tối đa200 chars display,
nếu lớn trả raw_value=null kèm row warning SOURCE_CELL_DISPLAY_UNAVAILABLE, không
truncate thành evidence đầy đủ; raw bytes vẫn retained private. Header label cùng
guard. Sheet/file filters phải đúng import, foreign404, malformed422 INVALID_FILTER.

Ví dụ extension `source_cells`/`planned_effect` của một I04 preview row
(các fields PreviewRow hiện có vẫn trả đầy đủ, ReceiptEffect như mục16):

```json
{"source_cells":[{"location":{"file_id":"00000000-0000-0000-0000-000000000065","sheet_id":"00000000-0000-0000-0000-000000000064","row_number":2,"source_column_index":2,"record_number":null,"line_start":null,"line_end":null},"column_label":"Lượng thực nhận","raw_value":"5","cell_kind":"numeric","formula_present":false}],"planned_effect":{"kind":"receipt","action":"CREATE_RECEIPT","source_identity":{"source_system_key":"supplier-a-deliveries","source_record_id":"DN-20261013-001-L1"},"receipt_id":"00000000-0000-0000-0000-000000000071","lot_id":"00000000-0000-0000-0000-000000000072","movement_id":"00000000-0000-0000-0000-000000000073","origin":"ACTUAL_RECEIPT","movement_kind":"receipt","quantity_delta":"5","unit":"l","occurred_at":"2026-10-13T02:00:00Z","recorded_at":null,"conflict_code":null}}
```

Quyền M01/M02/I04 giữ current action+batch sensitive domain reads, own batch rules
nếu applicable; không whitelist riêng từng cell để hạ quyền whole response. Page
metadata pin preview_digest/mapping_revision/read_set versions, không live
recanonicalize trên GET. Different filters cursor422; data changed409 PREVIEW_STALE
hoặc snapshot unavailable; FE refresh preview, không ghép rows từ hai digests.
No new mutations/audit business, no async job từ GET. MQ03 evidence dùng cùng
SourceEvidenceCell và quyền full spec; không expose whole workbook qua queue.
Acceptance C4 và regression liên quan: counts scope/filters/status/origin/empty; matching pages;
source→exact canonical→effect provenance; finance denial; bounds không truncate
audit facts; stale snapshot và no compute. Xem [bàn giao chung](API_CONTRACT.md#dot2-handoff).

<a id="preview-aggregates"></a>
### 17.1. R05 — Preview aggregates theo file/sheet — IMPLEMENTED C4

ACCEPTED DECISION — Product 13/10/2026: bổ sung aggregates theo file/sheet trên
projection I04 hiện có, cùng preview_id và pinned preview_digest. Không thêm endpoint
chỉ trả aggregates. CURRENT FACT: PreviewSummary/PreviewGroup toàn preview đã có;
scoped aggregates implemented trong I04/PreviewAggregates, không thêm metrics route.

Hai đơn vị phải trả riêng và có nhãn rõ:

- Raw source rows: records dữ liệu nguồn retained trong scope file/sheet, trước
  grouping thành action; không dùng số lines vật lý của CSV multiline hay mapping
  issues thay count này.
- Logical planned actions: distinct actions của pinned preview liên quan scope.
  Một action có nhiều source locations trong scope chỉ đếm một lần, kể cả nhiều
  locations trong cùng file/sheet. Source locations khác file/sheet có thể khiến
  cùng action thuộc nhiều scope; vì vậy totals từng file/sheet có thể chồng lặp,
  không được cộng thành batch total. Batch total đếm distinct actions trên scope
  batch, độc lập với tổng các scope con. Logical actions không đồng nghĩa successful
  writes; classification/planned action/blocker/warning vẫn giữ nghĩa preview.

Totals và rows page áp cùng scope/filters được hỗ trợ, cùng pinned preview/digest;
không đếm từ page length, cộng các pages hoặc trộn digest để dựng totals. File/sheet
scope chọn các actions có source location liên quan; raw row count chỉ đếm records
nguồn trong scope, không lấy số locations ngoài scope của action nhiều nguồn.
Representation phải phân biệt hai counts; không tái định nghĩa row_count hiện hành
để chứa lúc raw rows, lúc logical actions. Typed DTO/wire structure được chốt khi
triển khai projection; API không tự tính lại canonical facts trên GET.

Quyền whole-response sensitive reads, preview/read-set pins, foreign scope/error và
cursor/stale handling giữ mục17 và workflow I04 hiện hành. Acceptance khi triển khai:
raw rows khác actions; multi-location dedupe; overlapping file/sheet scopes và batch
distinct total; totals/page pin/filters; empty scope; stale preview và financial denial.
CURRENT FACT C4: I04.preview.aggregates={preview_id,preview_digest,batch,selected,
files:ScopedPreviewAggregate[],sheets:ScopedPreviewAggregate[]}.
Mỗi scope có {scope:{file_id,sheet_id,classification},raw_source_rows:{availability,
count},logical_action_count,by_classification,groups,blockers,warnings}. Groups đếm
actions theo canonical_domain/proposed_action và số actions có blocker/warning;
code counts đếm action một lần/code, không số Notice trùng trong grouped action.
Classification filter áp sau canonical grouping; raw count khi có filter chỉ đếm
distinct source records đóng góp matched actions. Không filter thì raw count gồm
mọi retained data record trong scope, kể cả source không tạo action. File/sheet
filters AND trước chọn actions; hai IDs hợp lệ nhưng intersection rỗng trả known0.
Files không có sheet/action vẫn có empty aggregate nếu thuộc frozen source_files.
Totals độc lập rows_limit/cursor; files/sheets là các scopes có thể overlap.

Ví dụ hai file A/B cùng proven receipt: batch raw2/logical1; mỗi file raw1/logical1,
không cộng logical1+1 thành batch2. Nếu có master reservation, đó là action khác
và được đếm riêng dù dùng cùng physical source row. Source rows không nhân đôi.
Xem [verification/commands/limits](runbooks/FULL_TEST_FLOW.md#read-discovery-c4).

## Canonical clarification for consumers

ACCEPTED DECISION / CURRENT FACT: I04 owns cumulative quota/source-set/revision,
not I02 or a files page. Read all receipts needed for rejected-client ACK before
I03 seals uploads. Same-key replay rechecks current authority; a new key never
means duplicate facts may be created. Preview counts refer to logical actions,
not raw rows. Filtered rows/configuration projections are pages, not complete
Store configuration; collect pinned pages to satisfy exact confirmation sets.

M03 descriptors are the authority for requiredness, nullability and source roles;
required-nullable still needs a key. Unknown/unresolved semantics cannot become0.
PROFILE_CONSTANT is reviewed reusable content; IMPORT_VALUE is batch-only and
must not enter a reusable spec. Source switches require explicit acknowledgment;
active-pointer change does not silently migrate an authorized immutable old pin.

Input Money has18 integer/18 fractional digit limits. Retained historic output
may preserve wider exact decimals (read-only exception, at most200 characters);
pending oversized legacy money cannot commit (LEGACY_MONEY_REVIEW_REQUIRED).
Quantity bounds are independent; source business keys1..1000 differ from namespace
Code1..128. Never round/truncate to fit. Changes/provenance retain typed domain/path
identities; a public preview does not expose its internal full read_set object.

Import Notice has code/severity/message and optional typed field/entity/impact/
source_location, not mandatory details. H01/H02 return explicit meta.warnings=[]
when empty; reviewed staging/queued commit remain in_progress until verified I06.
History GET retries only PostgreSQL40001 as a whole fresh-authority/snapshot read,
at most five attempts with0.75s total backoff; exhaustion remains503.

Current schemas/examples are generated/validated from source, not maintained as
parallel snapshots in clarification/supplement folders. Keep only useful synthetic
examples under features/examples; schema-valid examples do not prove API acceptance.
