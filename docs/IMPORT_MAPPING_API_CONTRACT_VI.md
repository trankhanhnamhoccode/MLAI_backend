<a id="import-sources"></a>
# Import — reviewed mappings and atomic canonical commit

## Authority, implemented scope and known drift

CURRENT FACT: I01-I06/M01-M04/N5/J01/H01/H02/R01 are wired with Store authorization,
immutable staging/preview/provenance, manual/approved-profile deterministic flow,
canonical nine-schema adapters and durable history/completion. Upload/review/save/
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
[inventory](features/IMPORT_SCHEMA_INVENTORY.md). Opening/actual receipt theo N6
chờ S4.6; purchase-history Import OPEN. Không map các nhóm này sang inventory_count.

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
không gửi sample cells của target rules đã biết. Off/no-key/timeout/invalid output
giữ manual flow. Tối đa hai sheet/batch, hai transport attempts/sheet; không live
provider/cost/quality claim. Trước khi bật thật phải duyệt model/dữ liệu/calls/chi phí.
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
suggestion_reason/candidate_targets, giữ indices/status/routes. Header detection
chỉ tìm trong tám dòng đầu, không vượt qua dòng đa cột để bỏ dữ liệu. Raw preamble
giữ riêng trong staging; dữ liệu không bị sửa. Scope đã khai báo có active profile
nhưng structure hoặc semantics không khớp sẽ báo PROFILE_STRUCTURE_OR_SEMANTICS_DRIFT;
không bind sai version hoặc sửa profile cũ. Numeric Excel serial chưa được convert.

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

Profile scope={store_id,source_system_key,report_type,schema_version}; schema
fingerprint có sheet/table role, headers/column types và layout declaration.

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
profiles matches với semantics khác nhau thì PROFILE_MATCH_AMBIGUOUS, cần Owner,
không chọn confidence cao nhất. New draft profile không active vì first import.

ProfileSpec REQUIRED:

```text
scope: {source_system_key, report_type, schema_version}
structure: {sheet_roles[], header_rules[], schema_signature}
field_bindings[]: {source_selector, target_field, requiredness, ignored:boolean}
identity_rules[]: {entity:product|ingredient|lot, key_fields[], bindings[]}
entity_proposals[]: {proposal_id, entity:product|ingredient, source_business_key,
  reserved_canonical_id, metadata, field_provenance, approval_revision}
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

Already approved matching version không reapproval. Replaced active version sau
preview không làm batch pin chuyển latest: nếu pinned version chỉ superseded, còn
được phép sử dụng thì commit đúng pin; **explicit retired** blocks new preview/
uncommitted commit409 MAPPING_VERSION_RETIRED. Owner retirement là chủ ý thôi dùng;
không silently migrate batch. Completed import/audit giữ version cũ dù retired.

<a id="schemas"></a>
## 6. Phạm vi dữ liệu hỗ trợ trong design

Không generic Excel writes mọi bảng. Capabilities public chỉ true khi corresponding
parser/domain-specific boundary/auth/audit/atomic commit đã wired, hiện chưa có.

| Schema/profile | Canonical intent và validation | Phần chưa được phép suy ra |
| --- | --- | --- |
| sales daily_total/disjoint_contribution | Existing Product hoặc new Product đã Owner duyệt tạo trong cùng batch, Store-local date, nonnegative quantity trong selling_unit, source/report identity; policy mục 8. | Retail price/revenue/stockout/promotion từ FE không có SalesDaily fields; không tự ghi Product.price hoặc invented history. |
| inventory lot_stock_count | Existing Ingredient + uniquely identified received lot, target on_hand≥0 exact base_unit; COUNT_CORRECTION reason/observation/version. | Không receipt/inbound, tự tạo lot từ batch_id, warehouse table hoặc source total→lot allocation. |
| recipes | Existing hoặc new Product/Ingredient được Owner duyệt tạo trong cùng batch, explicit version/from/to/yield/loss, unique lines exact base_unit, yield unit=Product.selling_unit. | Không auto-close overlap/retroedit; nhóm entire recipe atomically, không one-row-one-version. |
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

SourceContribution identity={Store,source_system_key,business_report_key,Product,date};
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
unique; full correction/source provenance writer mới là IMPLEMENTATION BACKLOG,
không gọi writer insert-only hiện tại rồi coi đã support replace/merge.

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
date_format=ISO|DMY_SLASH|MDY_SLASH, pack_cost_basis=PER_PACK|PER_SOURCE_UNIT.
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

Idempotency key scope actor+Store+method+route+phase; digest body presence/arrays,
content hashes và conditional headers; same key/request receipt/job cũ, không
latest mappings/new compute. Key khác request409. Same source business records
different key vẫn no duplicates qua source contribution/business uniqueness.
Race two imports same rows dùng expected versions/absence predicates+unique DB
keys; một commit thắng, cái còn lại409 PREVIEW_STALE, không double insertion.
Không dùng request key thay business provenance hoặc filename identity.
Proposal/approval/preview mutations CAS; retry successful receipt trước stale CAS
nhưng sau authorization recheck. Uncertain commit reconcile receipt+canonical
aggregate từ fresh session, không blind execute lại. Programming errors không
success; no generic per-row silent fallback.

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

SupplierTermSource={source_term_key:string1..1000,supplier_ref,ingredient_ref,
effective_from:date,effective_to:date|null,unit:Ingredient.base_unit,
pack_size_base_quantity:PositiveQuantity,pack_cost:MoneyText,currency,
minimum_order_packs:int1..2147483647,lead_time_days:int0..2147483647,
shelf_life_days:int0..2147483647|null,active:boolean,
maximum_order_base_quantity:Quantity|null}. Storecurrencyexact; effective_to inclusive
≥from; no datefallback fromupload. last optional maximum quantity, nếu declared
thì explicit SupplierLimit ONE_ORDER_SUPPLIER_INGREDIENT theo engine; null phải
scope_declaration EXPLICIT_NOT_CONFIGURED hoặc UNKNOWN, không “unlimited” ngầm.
Counts integer thật không string/bool; finite dates/arith overflow blockers.
Canonical internalversion SYSTEM_ASSIGNED positive sequence per supplier+ingredient,
không trust Excel version để overwrite UUID; source_term_key là external recordidentity,
không version/schema ID. Newsource cùng Supplier/Ingredient ngày hiệu lực chồng lấn block TERM_PERIOD_OVERLAP.

Pack cost là giá **một pack trọn**. Source15kg/pack,28000VND/kg→420000VND/pack chỉ
khi units/source pricingbasis+exact conversion Owner-approved, provenance giữ
inputs/operator. MOQ baseqty có thể ceil(dividepack) nếu rule explicit và khách
thấy derivation; MOQ không có không default1. Lead0 hợp lệ known same-day; missing
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

Rights: source/read fullscope including supplier.read+procurement.cost.read for
term/fee prices; importactions/mappingkeys + domainactions supplier.create fornew,
supplier.terms.create, supplier.terms.correct for amendment, supplier.fees.manage
forfees; declarations inventory.count.correct/sales.record/supplier.fees.manage
respectively plus whole domainreads, procurementcontext additionally budget.read.
Owner-only mapping approval remains; Staff granted canonical actions can commit
approvedmapping rows, no hidden escalation/automaticOwnerfactapproval.

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

### 14.2. Evaluation matrix, exclusions và orchestration

| Action | ready nghĩa gì / blockers |
| --- | --- |
| import | Upload/staging runtime available + import.create/import.upload grants; không cần có stock/sales. Existing import riêng kiểm state/rights/readset qua I04, Store ready không approvebatch. |
| menu | Scoped menu readeravailable; Menu được xác định rỗng vẫnready, data_statusvalid, warning MENU_EMPTY. No recipe không ngăn P01; P02 validity theo Catalog. |
| inventory | Warehouse readeravailable; đã biết không có lô vẫn readable ready với warning STOCK_COMPLETENESS_UNKNOWN, không claim procurementready. |
| forecast | Stable menu/sales/modelconfig, ≥1 tính được baseline Product có observations thực tế≤cutoff, preparation/execution adapteravailable; local missing history exclude affectedProduct. Empty/no computables blocked NO_COMPUTABLE_PRODUCTS; corrupt/incompatibleartifact blocker, not default fallback. |
| planning | Current readable/resolvable config+knownStorecap+requirements, ≥1 computedProduct, inventorydeclarations/datedrecipes/terms/fees/constraints in scope đã biết and valid, snapshot/preparation/forecast+planning worker compositionavailable, planning.run. Feecoverage/globalconstraintunknown blocks, not localpermission exclusion. |

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

C01 readiness giữ shape cũ: status=ready khi planningavailabilityready; not_ready
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
