# API contract — shared conventions, Catalog and Inventory

## Authority and current surface

CURRENT FACT: source OpenAPI has54 operations/50 paths (53 core plus health),
registered by `app/main.py`. `/openapi.json` and source Pydantic DTOs are the
structural reference. `GET /health` returns status=ok/service=shelfcash-backend;
it is liveness, not DB/business readiness. `/docs` and `/redoc` are disabled.

The three independent workflow contracts are
[Authorization](AUTHORIZATION_CONTRACT_VI.md),
[Import](IMPORT_MAPPING_API_CONTRACT_VI.md) and
[Planning](PROCUREMENT_API_CONTRACT_VI.md). This document owns shared conventions,
Menu/recipe calendar and Inventory. Do not duplicate complete DTO schemas across
documents. Keep accepted product rules separate from runtime, proposals and debt.

CURRENT FACT: P01/P02, V01-V04, N6/N8 and N20-N22 have HTTP/application/persistence
implementations. P02 reads today's live recipe; retained C04/C05/PDF use captured
horizon values. Recipe-calendar preview/commit are synchronous200 with current
rights, CAS, idempotency and Store-day policy. Inventory receipt/opening records
physical stock; reading a plan or exporting an option never writes inventory.

Use [the runbook](runbooks/FULL_TEST_FLOW.md) for a runnable end-to-end sequence;
[the changelog](CONTRACT_COMPATIBILITY_CHANGELOG_VI.md) owns compatibility/baseline
provenance. Route inventory can be regenerated with
`python -m scripts.integration_contract_snapshot` under ignored runtime.

## Contract/implementation discrepancies — TECHNICAL DEBT

ACCEPTED DECISION: ADR-013 authorized self-approval and the current Owner-only
reusable-profile approval/activation policy are compatible. Owner may approve a
profile they created; Staff proposal rights do not grant approval/activation.
Mapping approval is distinct from batch confirmation and canonical commit, which
recheck current permissions. No replacement ADR or two-person rule is required.
ADR-008's
replacement rule still applies to the same source dataset; Import also permits
confirmed independent-source sales merge, not generic addition/upsert. Cleanup
changes neither behavior nor accepted ADR intent.

## 6. Conventions chung và đối chiếu khác biệt

Quy ước chung nằm tại đây; các contract chuyên sâu dẫn về đây.

| Khác nhau / concept | Quy tắc handoff và scope |
| --- | --- |
| FE0 opaque example IDs vs cluster UUID | Resource IDs dùng UUID canonical lowercase. OptionId/snapshot/cursor/version opaque theo DTO, không ép UUID. Example FE0 như store_001 là fixture, không accepted production ID. |
| FE0 integer VND vs cluster exact money | MoneyText decimal string, Store.currency, không currency conversion hoặc display formatting vào API; C03 exact cost fractions giữ theo PLAN, không ép MoneyText display thành arithmetic truth. |
| Quantities/ratios/loss | QuantityText exact canonical; process_loss_rate decimal string [0,1). Fill requirement PercentText0..100 khác exact fulfilled ratio; P25/P50/P75 khác strategy. |
| Dates/timestamps | Business DATE theo timezone Store; event timestamps RFC3339 UTC, không source missing date fallback upload time; P02 hôm nay khác recipe trong từng ngày của Run. |
| Envelope | Success data/meta/error=null; failure data=null/meta/error structured code/message/details; success request_id/warnings theo clusters; 202 chỉ accepted job/Run, chưa completed. |
| Warnings khác shape | Đọc DTO và contract từng cluster. Import Notice có code/severity/message; field/entity/impact/source_location optional, không bắt buộc details. Xem [Import](IMPORT_MAPPING_API_CONTRACT_VI.md). FE giữ typed severity/provenance, không tự thêm fields mandatory. |
| Null/zero/[] | Unknown/unavailable/forbidden khác known zero/known empty. P01 count availability flags; P02 thiếu quyền whole denial; missing recipe null khác empty recipe. |
| Paging | limit50/max100/cursor ở paged reads; **C01 saved list không paging** theo reviewed contract. Summary/total filtered/all Store scopes đúng DTO, không page-length totals. |
| Product status | Canonical active boolean→active/paused adapter; không invent timed pause/lifecycle delete. Kho theo INV2: gần hạn7, ngưỡng sắp hết do Owner khai báo, watch khi unknown; không prototype risk. |
| CAS/version | Immutable profile version, proposal/import revision, saved/budget version, recipe integer version khác nhau. If-Match/If-None-Match đúng per mutation; absent428, stale412; source/preview stale409 không silent recompute. |
| Idempotency | Scope/digest per endpoint/phase trong clusters, không giả mọi mutations dùng một digest. Decimal numeric equivalence C02 như PLAN6; file bytes content hash exact. GET không mutation/LLM/solver. |
| Async | Import dùng J01/job_id; Planning C03 same run_id=plan_id polling. Không buộc FE gọi separate forecast training hay dùng J01 cho C02. |
| S364 internal serialization vs public counts | S364 giữ large Python/JSON integers exact nội bộ; PLAN public domain_size dùng UnboundedCountText string. HTTP mapper phải theo public DTO, không gửi raw retained engine JSON rồi để JavaScript Number mất precision. |
| Cache/read snapshots | Partition actor/Store/permission/resource/version; không mix Menu current/Kho current với retained Run; no-store private policy CAT giữ nguyên. |

Session/CSRF/CORS/errors đã định nghĩa AUTH v1; cookie session và current auth
fence, không bearer transport thứ hai. QuantityText của Kho/Import là decimal
string; ExactQuantity/SignedDelta của C03 là rational object, không cùng JSON type.
Các conventions đã nhất quán đủ để FE dựng DTO/adapters cho READY scope, không
enable live endpoint bởi capability fixture true.

### Quyền và errors đã thống nhất trong scope reviewed

Owner quyền trong đúng Store; Staff explicit grants; server resolves resource
Store và rechecks membership/permission từng read/retry/commit. Mapping activation
Owner-only, approval khác import write. Commit atomic toàn groups, missing rights
không drop rows. Menu.read gồm retail price, không procurement costs/budget.
C01/C02/C03 full-response denial nếu thiếu planning+budget.read+cost.read; config
writes không đòi cost.read vì không trả cost. P01 recipe count redaction có flag
khác P02/Planning/IMP whole-response denial; không toàn app tự bật redaction.

Chung:400 malformed request;401 unauthenticated;403 missing rights trong scope biết;
404 resource ngoài scope/not found;422 validation/filter;409 state/key/preview conflict;
412 stale CAS;428 required precondition;413 size limits;503 temporary unavailable/
verified integrity unavailable. Domain codes giữ chi tiết từng cluster, không
HTTP2xx fake error data hoặc500 cho failed retained Run GET hợp lệ.
One-time approval chưa allowlist/lifecycle: không automatically approval_allowed
true, không shared Owner key. Auth/catalogue/enforcement là dependency bắt buộc
trước expose; màn hình Owner grant editor cũng đã giữ trong v1.

<a id="dot2-handoff"></a>
## Bàn giao FE — Đợt 2 cộng tác và vận hành

ACCEPTED DECISION: phạm vi sản phẩm theo yêu cầu Đợt 2; technical choices được
ủy quyền trong các sections liên kết dưới đây. **DESIGN_READY không phải runtime**.
Các mô tả v1 hiện hành phía trên vẫn là CURRENT FACT; thiết kế Đợt 2 bổ sung hoặc
thay thế phần tương lai đúng scope, không sửa source/generated OpenAPI/FE gốc.

| Chủ đề canonical | Trạng thái và consumer FE |
| --- | --- |
| [Auth self-service/decline](AUTHORIZATION_CONTRACT_VI.md#auth-self-service) | DESIGN_READY: đăng ký, verify/resend, quên mật khẩu, decline. N7/N15–N19 routes IMPLEMENTED; mở rộng lifecycle/DTO chưa implement. |
| [Yêu cầu quyền](AUTHORIZATION_CONTRACT_VI.md#permission-requests) | DESIGN_READY: Staff submit/cancel; Owner review/approve/reject; refresh grants. N12–N14 IMPLEMENTED và tiếp tục là grants/audit authority. |
| [Inbox](NOTIFICATION_API_CONTRACT_VI.md#notification-v1) | DESIGN_READY: inbox/count/read; không approve qua notification. |
| [Mapping queue](IMPORT_MAPPING_API_CONTRACT_VI.md#mapping-queue) | DESIGN_READY: explicit submit, Store queue, pinned detail, request changes. N5/M01–M04 IMPLEMENTED; extensions chưa implement. |
| [Excel actual receipt](IMPORT_MAPPING_API_CONTRACT_VI.md#excel-actual-receipt) | DESIGN_READY schema/consumer trong pipeline hiện hữu; I01–I06/J01 và N6 IMPLEMENTED. |
| [Counters/preview](IMPORT_MAPPING_API_CONTRACT_VI.md#mapping-projections) | M01/M02/I04 IMPLEMENTED; counters có scope/origin mới và detailed projection DESIGN_READY. |
| [Today/supplier picker](#today-operations) | DESIGN_READY: D01/SU01; V01–V04/R01/C03/H02 reads IMPLEMENTED, không giả Today đã tồn tại. |
| [Run history/export discovery](PROCUREMENT_API_CONTRACT_VI.md#planning-discovery) | N9/N10/N11/J01 IMPLEMENTED; N9 creator/date filters và EX01 DESIGN_READY. |

Các clarification canonical để FE không nhầm approval/commit:
[source-before-reuse và entity binding](IMPORT_MAPPING_API_CONTRACT_VI.md#source-reuse),
[identity/correction theo schema](IMPORT_MAPPING_API_CONTRACT_VI.md#schema-correction),
[profile retirement](IMPORT_MAPPING_API_CONTRACT_VI.md#profile-retirement).
Policy đã duyệt không tự thành CURRENT FACT: analyze signature-only auto-bind còn
gap source proof; recipe cross-file full-report assembly còn gap phân biệt bản cùng
version. Lát3 identity/opening/count/completeness đang WIP, source có thêm opening_stock
writer; không dùng static trace để tuyên bố public acceptance hoặc đổi lịch sử release.
Clarification này không thêm route, permission, approval store hoặc operation count.
Auth service-wide disabled/unavailable dùng503 EMAIL_DELIVERY_UNAVAILABLE đồng nhất
mọi email trên A02/A06/A07 DESIGN_READY, không generic202 hứa check_email khi không
thể gửi. Profile approved inbox mở submission hiện hành rồi batch, không “đã nhập”.

Inventory bằng **static source inspection**, không khởi tạo FastAPI/OpenAPI:
54 operations/50 paths hiện có, gồm 53 core + GET /health. Thêm đúng **18 operations**
Đợt 2: NF01–NF03 (3), A02/A05–A07/IN01 (5), PR01–PR04 (4), MQ01–MQ03 (3),
D01/SU01/EX01 (3). Có16 paths mới (POST/GET permission-requests chung path;
GET exports dùng path POST N10 đã có). Surface dự kiến **72 operations/66 paths**,
gồm71 core + health; đây là inventory thiết kế, không OpenAPI runtime72.
Extension query/body/action trên route hiện có không cộng thêm operation.

Routes reused trong scope: A01/A03/A04/T01/T02/N7/N12–N19; M01–M04/N5;
I01–I06/H01/H02/J01; N6/V01–V04/N8; R01/C01/C02/C03;
N9/N10/N11. DTO hiện hữu tra source Pydantic; những JSON bên dưới ghi rõ
request, response `data` hoặc envelope, không masquerade toàn bộ DTO runtime.

DEFERRED: AI chat/copilot endpoints, What-if, public PO lifecycle, Owner-key/
one-time bypass, browser push/SMS, location/warehouse management, unified timeline,
general settings CRUD và currency/timezone mutation sau operational history.
Không cộng các mục này vào18 routes, không FE tự gọi route từ prototype cũ.
Settings duy nhất dùng lại trong Đợt 2 là threshold N8, budget N4 và requirements
N1–N3 hiện có với consumer rõ; không thêm general settings fields thiếu consumer.

<a id="dot2-common"></a>
### Quy ước bắt buộc cho DESIGN_READY operations

Tất cả paths tương đối `/api/v1`. UUID, UTC Timestamp, Store-local DATE,
MoneyText/QuantityText theo conventions hiện hành. Version opaque1..256 bytes;
unknown fields422, JSON request≤64KiB, reason1..1000 nonblank, decimal strings exact.
Typed objects liệt kê đầy đủ keys; `?` nghĩa optional query, `|null` nghĩa key
bắt buộc nullable; không tùy tiện omit nullable fields. Examples synthetic.

Success={data:<typed DTO>,meta:{request_id,...},error:null}; errors=
{data:null,meta:{request_id},error:{code,message,details:{field_errors?,reason_codes?}}}.
GET200, không body, Origin/CSRF không yêu cầu, không side effects/forecast/solver/LLM;
cookies credentials include, Cache-Control private,no-store. Sensitive reads check
User/session/Store/membership/current grants và actor scope; foreign resource404,
known accessible resource nhưng thiếu permission403. Không tin allowed_actions,
ETag, notification hoặc grants snapshot để bypass commit fence.

Paginated new reads: limit integer1..100 default50, cursor opaque≤4096;
items=[], next_cursor=null khi hết; total_count exact filtered int>=0.
meta.pagination={limit,next_cursor,total_count}, meta.snapshot_id:Version,
meta.observed_at:Timestamp. New cursor bind actor/Store/filters/sort/authorization/
source revisions và page position. Đọc nhất quán trong một short transaction;
snapshot token không hứa lưu historical copies. Đổi revision409
SNAPSHOT_NOT_AVAILABLE, FE refresh từ đầu; cursor khác filter422 INVALID_CURSOR.
Snapshot metadata không expose source revision của section forbidden.

Authenticated mutations: exact Origin + X-CSRF-Token, Idempotency-Key UUID canonical;
entity transitions thêm If-Match quoted current version, absent428/stale412.
Create không If-Match. Không browser header do FE tùy đặt thành quyền.
Key scope actor+Store resolved+method+resource/action, digest canonical body+CAS;
replay current authorization trước trả original receipt và trước stale CAS.
Same key/payload trả receipt cũ; changed409 IDEMPOTENCY_KEY_REUSED. Timeout giữ key,
body, If-Match và retry; không newkey để đoán commit. Chỉ sau409/412 và review dữ
liệu mới dùng key mới. CAS no-op giữ version. Local mutation/audit/receipt/intent
atomic, không phát mail trước commit. Commands synchronous trừ khi section ghi202.
Public self-service/token endpoints có ngoại lệ key/CSRF/retry được ghi ở Auth.

| HTTP/code chung | Hành động FE |
| --- | --- |
| 400 INVALID_REQUEST | Sửa request/header, không auto retry. |
| 401 UNAUTHENTICATED | Login rồi refetch context. |
| 403 PERMISSION_DENIED / CSRF_CHECK_FAILED | Refresh A03/T02 hoặc phiên; không dùng Owner-key. |
| 404 RESOURCE_NOT_FOUND | Hiện không truy cập được; không dò Store/actor khác. |
| 409 IDEMPOTENCY_KEY_REUSED | Không đổi payload trên key cũ; đối chiếu ý định. |
| 409 SNAPSHOT_NOT_AVAILABLE / *_STATE_CONFLICT | Refresh list/detail, review lại action. |
| 412 *_REVISION_CONFLICT / 428 PRECONDITION_REQUIRED | Đọc version mới / gửi conditional header. |
| 413 RESOURCE_LIMIT_EXCEEDED | Giảm request/scope, không truncate facts. |
| 422 VALIDATION_ERROR / INVALID_FILTER / INVALID_CURSOR | Hiện field error; reset filter/cursor phù hợp. |
| 429 RATE_LIMITED | Chờ Retry-After integer seconds, không retry tight loop. |
| 503 SERVICE_UNAVAILABLE | Backoff GET; mutation retry nguyên key/payload sau timeout. |

Không tự purge Run/input/result/idempotency hoặc audit/provenance. Technical design
không tạo infrastructure mới: local PostgreSQL, một backend process, purpose-specific
durable intents. Acceptance dưới các cụm là specifications tương lai; task này
không xác minh persistence, email delivery, HTTP hoặc whole FE acceptance.

<a id="today-operations"></a>
## Today và supplier discovery — DESIGN_READY

### D01 GET /stores/{store_id}/today

FE tải projection xuyên luồng trong một response. Không body; query section?:
comma-separated unique inventory,imports,mapping,permissions,readiness,planning
(omit=tất cả), limit:int1..20 default5 cho **từng sample list**, snapshot_id?:Version.
Chỉ cần current active membership để vào Today; mỗi section kiểm quyền riêng.
Section forbidden vẫn hiện availability="forbidden", value=null, source=null,
updated_at=null, completeness="unknown", reason_codes=["PERMISSION_DENIED"];
không counts/tasks/timing/snapshot hints riêng làm lộ dữ liệu. Requested section
không supported422 INVALID_FILTER. Response200 synchronous, không mutation/audit
business; meta={request_id,snapshot_id,observed_at,as_of_date,timezone}.

```text
Today={store_id:UUID, sections:{
 inventory: Section<InventoryAttention>, imports: Section<TaskList>,
 mapping: Section<TaskList>, permissions: Section<TaskList>,
 readiness: Section<Readiness>, planning: Section<LatestRun>
}}
Section<T>={availability:available|empty|unknown|forbidden|unavailable,
 value:T|null, updated_at:Timestamp|null, completeness:confirmed|partial|unknown,
 reason_codes:string[], source:{resource:string,version:Version}|null}
InventoryAttention={as_of_date:date,expired_lot_count:int,near_expiry_lot_count:int,
 low_stock_ingredient_count:int|null,unknown_assessment_ingredient_count:int,
 items:{ingredient_id:UUID,status:string,reason_codes:string[],
        usable_quantity:QuantityText|null,unit:string}[],has_more:boolean}
TaskList={total_count:int,items:{type:import|mapping_submission|permission_request,
 id:UUID,state:string,updated_at:Timestamp,allowed_actions:string[]}[],has_more:boolean}
LatestRun={run_id:UUID,status:queued|running|completed|failed,accepted_at:Timestamp,
 result_digest:Version|null}
```

Readiness type reuse R01 DTO, không định nghĩa lại blockers. Omitted section không
có key; các sections requested có đủ keys Section. available yêu cầu value khác
null; empty TaskList là total0/items[]/has_morefalse, latestRun empty value=null.
Unknown không dùng zero. updated_at là last relevant recorded update hoặc null,
observed_at là lúc đọc; không dùng observed_at để giả freshness data.
completeness phản ánh declaration/coverage, không suy từ tồn tại một row.

Inventory cần inventory.read+ingredient.read, dùng V01–V04 semantics: gần hạn
0..7 inclusive, expired riêng, low threshold do Owner khai báo; không total quantity
khác unit, cost hoặc valuation. imports dùng import.read + sensitive domain reads
như H02/I04; Staff chỉ own batches actionable, Owner toàn Store. mapping Owner queue
submitted eligible; Staff own submissions với mapping.read+import.read và sensitive
domain reads. permissions Owner pending queue, Staff own pending requests, active
membership không cần grant phụ. Readiness dùng nguyên action-specific authorization
R01, chỉ trả actions được phép; thiếu finance permission không trả money blockers,
scope details/counters hoặc versions nhạy cảm. planning section cần
planning.result.read+budget.read+procurement.cost.read (cùng N9); latest by
-accepted_at/UUID, không cần completed và không gửi cost trong Today.

ACCEPTED DECISION / DESIGN_READY: Today dùng readiness hiện hành của R01 theo
action/scope/date/source versions, không suy Store READY từ import completed hoặc
profile approved. `blockers` chặn đúng action/scope; `warnings` không tự chặn action
đã can_execute=true nhưng FE giữ impact/unknown/exclusions và limitations của input/
dự báo, không gọi readiness là forecast accuracy. Warning PAYABLE_FEES_NOT_ESTABLISHED
ở import preview có thể dẫn đến planning blocker PAYABLE_FEE_COVERAGE_UNKNOWN khi
R01 đánh giá đủ dependencies; không suy mọi preview warning cho planning chạy được.
Không đổi source data_status/result_assessment hoặc conceal blocker bằng notification.

Một consistent read transaction dựng projection/current permissions và snapshot;
không ghép cached readiness/planning/inventory từ thời điểm khác. Nếu revision
không thể pin trả409 SNAPSHOT_NOT_AVAILABLE; lỗi đọc section kỹ thuật trả unavailable
null/reason SERVICE_UNAVAILABLE, không silent0. Fresh authority từ API đích khi
click; Today không command route. Nguồn planned purchase trong retained Run không
được đưa vào inventory/inbound hoặc gọi “hàng thực đang về”.

Ví dụ D01 data cho actor chỉ được xem yêu cầu quyền, query section=permissions:

```json
{"store_id":"00000000-0000-0000-0000-000000000001","sections":{"permissions":{"availability":"empty","value":{"total_count":0,"items":[],"has_more":false},"updated_at":null,"completeness":"confirmed","reason_codes":[],"source":{"resource":"permission_requests","version":"requests-1"}}}}
```

### SU01 GET /stores/{store_id}/suppliers

Current membership + supplier.read; không suy từ inventory.read. Query q?:string
1..200 (trim, case/diacritic-insensitive name), active?:boolean (omit=tất cả),
limit/cursor, sort=name|-name defaultname, snapshot_id?:Version. Sort name/UUID.
Response200 data={items:SupplierPickerItem[]}, metadata paging theo quy ước chung.
SupplierPickerItem={supplier_id:UUID,name:string,active:boolean,
version:Version}. Version là opaque digest của current supplier identity/name/
active/updated_at, không giả Supplier có version column hoặc SKU hiện hữu.
Không terms/price/MOQ/fees/bank/contact private trong picker;
không thêm quyền procurement.cost.read chỉ để chọn supplier. Empty[] là known
empty trong filters. Active flag phục vụ picker và lịch sử; receipt dùng same-Store
reference validation hiện hành N6, không tự thêm business rule cấm inactive supplier.
N6/Excel consumer kiểm lại reference, stale picker không authority. Không mutation
hoặc business audit; 422 INVALID_FILTER/INVALID_CURSOR,409 snapshotchanged.

```json
{"items":[{"supplier_id":"00000000-0000-0000-0000-000000000041","name":"Nhà cung cấp A","active":true,"version":"supplier-1"}]}
```

Acceptance D01/SU01: quyền/Store isolation cả counts/versions; unknown threshold
không zero; day rollover/snapshot conflict; latest queued/failed visible đúng quyền;
GET không compute; supplier paging không leak terms; revoke sau picker chặn write.

## Catalog/Menu/Recipe

<a id="catalog-semantics"></a>
## 4. Nguyên liệu, đơn vị, sản phẩm và công thức

### 4.1. Đơn vị và identity — ACCEPTED DECISION hiện hành

Theo S1.7 trong [APPLICATION_CONTRACTS](features/APPLICATION_CONTRACTS.md), canonical
RecipeLine.unit, InventoryLot.unit và SupplierTerm.unit phải bằng Ingredient.base_unit
chính xác. Product.selling_unit là đơn vị đầu ra recipe và quantity sales/forecast
của Product đó. Canonical labels có thể là `g`, `ml`, `cup` nhưng không có catalog
enum hoặc conversion engine đã accepted. Không trim/case-normalize canonical unit
hoặc SKU của existing records; không dùng UI alias làm dữ liệu canonical.

Ví dụ nguyên liệu Milk có base_unit `ml`, recipe ghi `180 ml`, stock cũng là `ml`:
đọc đúng các giá trị đó. Không tự trả stock bằng `l` hoặc cho phép recipe `l` vì
“cùng thể tích”. `g` → `kg`, `ml` → `l`, piece → cup, mass → volume đều chưa là
conversion behavior hiện hành. FE có thể đổi cách viết nhãn nhưng không nhân/chia
quantity. Source unit khác canonical cần mapping/normalization có evidence và rule
được duyệt ở import, không LLM chọn hệ số hoặc P02 chữa facts lúc đọc.

UUID xác định entity; names không unique. SKU nullable, unique/case-sensitive trong
Store khi có; Ingredient và Product có namespaces SKU riêng. Không join theo tên,
không dùng SKU/null name làm recipe identity hoặc stock lookup.

### 4.2. Status và giá — policy nền + TECHNICAL CHOICE adapter

Product.active=true → wire `status=active`; false → `status=paused`, khớp hai nhãn
FE gốc. Đây là projection boolean, không tuyên bố có lịch ngừng bán, ngày pause,
lifecycle archive hoặc writer đổi trạng thái. P01 mặc định liệt kê cả hai; filter
chỉ tác động items, summary vẫn toàn Store. P02 vẫn đọc được paused Product theo ID
và quyền hiện hành, không coi paused là resource không tồn tại.

Ingredient trả `active:boolean` là metadata của nguyên liệu, không đồng nhất với
Product.status. Existing inactive Ingredient vẫn là identity tham chiếu trong
recipe; read không bỏ line đó hoặc xóa stock. Internal capture không có chứng cứ
chặn Ingredient chỉ vì active=false; không tự đặt rule “tất cả recipes bị khóa”.
Workflow ngừng nguyên liệu và cách xử lý dependencies chưa được giao, không thêm
writer hoặc suy ra semantics mới từ cờ này.

Giá bán là giá niêm yết hiện tại cho một selling_unit, Store.currency, nullable khi
chưa biết; zero là giá zero thật. Không trả giá vốn/cost/biên lợi nhuận hoặc lấy
supplier price làm selling_price. Quyền xem Menu bao gồm giá niêm yết đã chốt ở mục 11.

### 4.3. Recipe và ngày — ACCEPTED DECISION hiện hành

Recipe.version là integer >0, unique theo Product; không phải opaque ETag.
Recipe effective_from/effective_to là DATE inclusive; null to nghĩa open-ended.
Ngày hôm nay tính theo timezone Store tại đầu request, không timezone browser.
P01/P02 dùng cùng ngày định nghĩa này; không gửi dates tùy ý hoặc fallback recipe
gần nhất nếu hôm nay không được covered. Chỉ có 0 hoặc 1 recipe đúng ngày; overlap
là integrity error, không chọn version lớn nhất.

yield_quantity >0: output của toàn mẻ trong Product.selling_unit. Quantity mỗi line
>0 là nguyên liệu cho **toàn yield**, không mặc nhiên một serving. process_loss_rate
là tỷ lệ recipe-level trong [0,1), không percent display và không per-line loss.
Định nghĩa hiện hành: nhu cầu ingredient = demand_product × line_quantity /
yield_quantity / (1−process_loss_rate). Không cộng loss lần nữa vì thấy tên yield.
Ví dụ yield10 cup, milk1000 ml, loss0.2, demand40 cup → 5000 ml. Đây là minh họa
formula/test fixture, không số liệu quán hoặc forecast quality.

Recipe canonical header không có yield_unit riêng: wire yield_unit được derive
từ selling_unit của Product cùng snapshot. from/yield/loss không nullable canonical;
không áp nullable illustration FE gốc lên canonical schema. Không có recipe:
recipe=null. Có header nhưng lines=[]: known empty, count0, khác missing recipe;
không ready cho BOM, kể cả forecast demand=0. Line unit không khớp base_unit hoặc
yield không hợp lệ không được biến thành recipe=null nhằm giấu corruption.

CURRENT FACT: internal create_version chỉ thêm version với period không chồng lấn;
Recipe1 open-ended chặn Recipe2 overlap, không update/auto-close. Mục12 là workflow
public mới được giao: đổi calendar explicit có preview/confirmation/audit, giữ
content version và ngày≤hôm nay, không tự đóng khi tạo/import newversion hoặc GET.

<a id="catalog-p01"></a>
## P01 — đọc Menu và summary

`GET /stores/{store_id}/products`; không body.
Query allowlist: `q` optional 1..200 ký tự sau trim; `status=active|paused` optional;
`limit` integer default50, 1..100; `cursor` opaque; `sort=name|-name|selling_price|
-selling_price` default name. SKU không được search theo tên bằng implicit join;
q khớp product name theo Unicode case/diacritic-insensitive Vietnamese, including
Đ/đ → d, không mutate stored name. Unknown/repeated singleton query hoặc enum sai
trả422. Price null luôn last, tie-break UUID tăng dần. status filter không làm mất
summary counts paused/active.

Pagination keyset có snapshot/data_version trong cursor, gắn Store/filters/sort;
catalog/version đổi giữa các pages trả409 LIST_VERSION_CHANGED, FE bắt đầu lại.
Không trả các pages khác version như một list nhất quán. total_count là số toàn
bộ filtered result của read snapshot; summary counts toàn Store, nonnegative.
Không tính total từ items.length. Empty Store count0/items=[] khác filtered empty.

data REQUIRED `summary:{product_count,active_count,paused_count}` và `items:ProductRow[]`.
ProductRow keys: product_id, sku:string|null, name, selling_unit, selling_price:
MoneyText|null, currency, status, ingredient_count:integer|null,
ingredient_count_availability:available|missing_recipe|forbidden.
Ingredient count = số Ingredient distinct trong recipe effective hôm nay; uniqueness
lines khiến bằng line count. Có empty recipe count0/available; không recipe null/
missing_recipe. Không có recipe/ingredient read permissions: null/forbidden, không
lộ số lượng qua sorting/search/summary. Giá bán vẫn đọc được với menu.read theo mục 11.

Ví dụ **SYNTHETIC TARGET DESIGN**, không runtime response:

```json
{
  "data": {
    "summary": {"product_count": 1, "active_count": 1, "paused_count": 0},
    "items": [{
      "product_id": "00000000-0000-4000-8000-000000000010",
      "sku": "MATCHA-01", "name": "Matcha Latte", "selling_unit": "cup",
      "selling_price": "49000", "currency": "VND", "status": "active",
      "ingredient_count": 1, "ingredient_count_availability": "available"
    }]
  },
  "meta": {
    "request_id": "req-menu-demo", "observed_at": "2026-10-09T03:00:00Z",
    "as_of_date": "2026-10-09", "timezone": "Asia/Ho_Chi_Minh",
    "updated_at": "2026-10-08T02:00:00Z", "data_version": "catalog-demo-1",
    "pagination": {"limit": 50, "next_cursor": null, "total_count": 1}, "warnings": []
  }, "error": null
}
```

P01 không trả recipe nội dung, lots, sales histories, stock forecast, stock-derived
status, margin/cost hoặc ingredient name search. Product.active không bị suy ra từ
có bán hôm qua/stock=0/thiếu recipe; paused không tự mất khỏi summary.

<a id="catalog-p02"></a>
## P02 — sản phẩm và công thức hiện hành

`GET /stores/{store_id}/products/{product_id}`; không body/query. P02 là full read
product + recipe, cần đầy đủ quyền mục 8; thiếu quyền thì chặn response, không
trả recipe=null để giả không có recipe. Không thêm query history/as_of/edit/new
recipe chỉ vì repository có method. P01 vẫn usable cho actor chỉ có menu.read.

data REQUIRED product_id, sku, name, selling_unit, selling_price, currency, status,
recipe:Recipe|null. Product shape và price/status semantics như P01, không suy ra
ingredient count từ phiên P01 khác version.

Recipe REQUIRED recipe_id, version:positive integer, effective_from:DATE,
effective_to:DATE|null, yield_quantity:PositiveQuantityText, yield_unit:string,
process_loss_rate:LossRateText, ingredients:RecipeIngredient[]. Không field
effective_date alias trùng; FE chuyển effective_from sang label cũ. Version chọn
theo ngày, không latest/highest recipe version.

RecipeIngredient REQUIRED recipe_line_id, ingredient_id, ingredient_name,
ingredient_sku:string|null, ingredient_active:boolean, expiry_tracking:boolean,
base_unit:string, quantity:PositiveQuantityText, unit:string. unit=base_unit exact;
không trả Ingredient costs. Order ingredient_id UUID tăng dần, ổn định; không
duplicate ingredients. Các flags là current metadata trong cùng read snapshot,
không facts lịch sử tại effective_from.

Ví dụ **SYNTHETIC TARGET DESIGN**:

```json
{
  "data": {
    "product_id": "00000000-0000-4000-8000-000000000010",
    "sku": "MATCHA-01", "name": "Matcha Latte", "selling_unit": "cup",
    "selling_price": "49000", "currency": "VND", "status": "active",
    "recipe": {
      "recipe_id": "00000000-0000-4000-8000-000000000020", "version": 1,
      "effective_from": "2026-10-01", "effective_to": null,
      "yield_quantity": "1", "yield_unit": "cup", "process_loss_rate": "0",
      "ingredients": [{
        "recipe_line_id": "00000000-0000-4000-8000-000000000030",
        "ingredient_id": "00000000-0000-4000-8000-000000000040",
        "ingredient_name": "Sữa tươi", "ingredient_sku": "MILK-01",
        "ingredient_active": true, "expiry_tracking": true, "base_unit": "ml",
        "quantity": "180", "unit": "ml"
      }]
    }
  },
  "meta": {
    "request_id": "req-product-demo", "observed_at": "2026-10-09T03:00:00Z",
    "as_of_date": "2026-10-09", "timezone": "Asia/Ho_Chi_Minh",
    "updated_at": "2026-10-08T02:00:00Z", "data_version": "catalog-demo-1", "warnings": []
  }, "error": null
}
```

Không có version effective hôm nay:200 recipe=null, warning RECIPE_NOT_AVAILABLE
với impact “Không có công thức hiệu lực tại ngày đọc”; không 404 cho Product có thật.
Có header với ingredients=[]:200 Recipe đầy đủ, warning EMPTY_RECIPE. Không lấy
recipe tương lai hoặc quá khứ lấp chỗ trống. P01 count và P02 recipe phải reconcile
trong cùng version/ngày/quyền; nếu version khác FE refresh trước đối chiếu.

“Xem tồn kho nguyên liệu” lấy IDs từ ingredients, gọi đúng V01/repeated ingredient_id
qua FE route adapter. Missing ingredients trong stock result nhận qua
missing_ingredient_ids; không fake quantity0 hoặc tạo stock lot. Recipe missing/empty
không có IDs để điều hướng. Thiếu inventory.read thì chặn Kho, không tự grant vì
đã đọc được recipe; không đưa lots/cost vào P02 để bypass quyền.

<a id="catalog-permissions"></a>
## Catalog permissions, validation và errors

**ACCEPTED DECISION:** Owner/Staff theo Store, quyền read/write riêng, deny-by-default,
recheck session/Store/membership mỗi request; resource ngoài scope không leak.
Không Owner key/one-time approval tự động. CURRENT FACT: các grant names dưới đây nằm trong catalogue và runtime enforcement:

| Read responsibility | Quyền boundary |
| --- | --- |
| P01 product fields/summary/retail selling_price | menu.read |
| P01 ingredient_count | recipe.read + ingredient.read, ngoài menu.read; nếu thiếu count=null/forbidden |
| P02 product + full recipe + Ingredient metadata | menu.read + recipe.read + ingredient.read; thiếu bất kỳ quyền nào 403 toàn response |
| P02 → Kho/V01 | inventory.read theo contract Kho, không tự cấp từ menu/recipe |
| Write import | Quyền ghi Product/Ingredient/Recipe của batch theo auth/import, không được suy ra từ menu.read |

Không budget.read hoặc procurement.cost.read chỉ để xem giá bán niêm yết. P2
Planning không bị nới: actor vẫn cần toàn bộ quyền tiền/planning tương ứng ở C01–C03.
P01 giới hạn redaction ở count scalar với availability rõ; không trả recipe IDs,
dates/yield/ingredient names hoặc derived counts cho actor thiếu quyền. P02 dùng
whole-response denial để không có partial recipe làm FE hiểu là thiếu dữ liệu.

GET không Idempotency-Key/If-Match bắt buộc, không write/retry side effects. Một
request đọc Product/recipe/Ingredient/summary nhất quán trong read snapshot, đóng
Session trước serialize/return; không solver/LLM/filesystem generation trong read.
Không claim ORM FK là actor authorization hoặc code list hiện tại là paging API.

| HTTP / code | Điều kiện và xử lý |
| --- | --- |
| 400 INVALID_REQUEST | GET JSON body không được nhận; request syntax hỏng. |
| 401 UNAUTHENTICATED | Session không hợp lệ. |
| 403 PERMISSION_DENIED | Thiếu quyền trong Store được phép biết; approval_request_allowed=false cho reads này đến khi allowlist được duyệt. |
| 404 RESOURCE_NOT_FOUND | Store/Product không tồn tại hoặc ngoài authorized scope; same shape/message, không lộ ownership. |
| 409 LIST_VERSION_CHANGED | Cursor snapshot/version không còn current; reset pagination, không ghép trang. |
| 422 INVALID_FILTER / INVALID_CURSOR / INVALID_RESOURCE_ID | Query/type/enum/sort/cursor signature hay scope sai; UUID sai canonical. |
| 503 CATALOG_READ_UNAVAILABLE | Loader/snapshot không khả dụng; không trả Store empty giả. |
| 503 CATALOG_INTEGRITY_UNAVAILABLE | Overlap/foreign graph/missing referenced Ingredient/unit mismatch/invalid canonical value; không bịa recipe hoặc bỏ line lỗi. |
| 503 CATALOG_REPRESENTATION_UNAVAILABLE | Canonical facts vượt representation/response capacity, không round/truncate để success. |

Errors không raw SQL/trace/cross-Store entity. No recipe/nullable price không phải
503. Warning thiếu recipe/empty chỉ gửi khi actor có quyền biết facts đó.
Error shape ví dụ, **không phải lỗi runtime vừa quan sát**:

```json
{
  "data": null, "meta": {},
  "error": {
    "code": "PERMISSION_DENIED", "message": "Bạn chưa có quyền xem công thức.",
    "details": {"approval_request_allowed": false}
  }
}
```

<a id="catalog-effects"></a>
## 9. Nhất quán với sales, kho, forecast và Run đã lưu

| Dữ liệu / thay đổi | Policy đã có / boundary của cụm |
| --- | --- |
| Recipe dated switch trong horizon7 | Pipeline chọn từng ngày inclusive; P02 chỉ recipe hôm nay, không dùng một recipe P02 cho cả 7 ngày. C02 không nhận recipe facts do FE gửi. |
| Product đang paused | P01/P02 vẫn đọc identity; Planning capture active menu theo contract đã chốt. Không xóa SalesDaily/ForecastRun/DecisionRun vì Product không trong scope mới. |
| Active Product thiếu recipe/empty/recipe gap | Read vẫn giải thích được missing/empty; Planning exclusions/computed scope theo contract hiện hành. Menu read thành công không phải can_generate=true. |
| Ingredient inactive | Read giữ line/identity/metadata; không xóa tồn kho hoặc tự đổi BOM/serving. Workflow deactivate dependencies không nằm trong public surface này. |
| Đổi tên/giá niêm yết qua workflow được giao sau | Read projection là current facts; không suy ra historical selling price/revenue/margin từ Product.price hiện tại. SalesDaily hiện chỉ canonical quantity/date/Product, không price history. |
| Đổi base_unit/selling_unit | Cụm này không có writer cho thao tác này. Không đổi nghĩa quantity cũ qua read adapter; SalesDaily không lưu selling_unit riêng nên đặc biệt không suy ra có thể sửa Product.selling_unit an toàn. Migration/conversion/correction có hệ quả phải có task/decision riêng nếu mở workflow. |
| Bật expiry_tracking với stock cũ | Đây chỉ là metadata read. Không phát minh expiry cho old lots hoặc chuyển missing expiry thành known; không có toggle writer được duyệt ở cụm này. |
| Recipe correction có ngày quá khứ | Writer nội bộ chỉ new version không overlap; không overwrite/auto-close. Không retroactively ghi tiêu hao kho hoặc sửa SalesDaily; correction workflow riêng chưa tồn tại. |
| Forecast và recipe/price | Recipe/stock/supplier/budget changes không tự đổi forecast identity theo Planning; forecast quantity dùng exact captured selling_unit. Không thêm training/reuse mutation trong P01/P02. |
| Run đã nhận/lưu | ADR-011 và Planning: dùng retained config/input/result; không re-query current P02 để viết lại recipe/yield/units/cost của Run. Tên/labels hiện tại của Menu không thay retained facts của Run. |

Không dùng P02 current recipe để khẳng định recipe thực tế mà nhân viên đã dùng
ở ngày bán quá khứ. Calendar effective date không là availability/knowledge history.
BOM lý thuyết không phải actual inventory depletion; không gọi GET rồi trừ tồn kho.
Menu data_version khác Run snapshot identity; FE không mix current stock với capture
của Run. Existing immutable Run policy không phải “toàn bộ mutable catalog rows đã
có DB immutability enforcement”.

<a id="catalog-decisions"></a>
## 11. Quyết định nghiệp vụ đã hỏi và kết quả

CURRENT FACT: Staff có menu.read được thấy giá bán niêm yết trong P01/P02.
Quyền này không bao gồm giá nhập/giá vốn; không cần separate retail-price grant.

**ACCEPTED DECISION — sản phẩm, 09/10/2026:** người dùng trả lời trực tiếp
“Xem Menu được thấy giá bán niêm yết”. Áp P01/P02 tại mục 6–8; không tạo grant
procurement.cost.read/budget.read hoặc nới P2 Planning.

Không còn vấn đề sản phẩm cần duyệt trong public read scope này; **0 vấn đề quan
trọng bị để lại chưa hỏi**. Unit exact, dated nonoverlap/no autoclose, Run snapshot
và không tác động kho/sales đã có authority, không hỏi lại. Workflow đổi hiệu lực được giao sau lượt chỉ đọc và đã review tại mục12. Các luồng
conversion/deactivate/correction hồi tố khác chưa được duyệt, không tự coi là policy
đã chốt cho tương lai. Nếu scope mới cần chúng, tình huống/hệ
quả/authority được review riêng trong chính tài liệu này trước design implementation.

<a id="recipe-effectivity"></a>
## 12. Workflow đổi hiệu lực công thức — v1, chỉ tương lai

**ĐÃ CHỐT / ACCEPTED DECISION sản phẩm 09/10/2026:** người dùng chọn “Từ ngày
Store kế tiếp; chưa sửa lịch sử”. T=Store-local hôm nay ở mỗi mutation. Workflow
chỉ thay việc áp dụng từ T+1; không đổi toàn ngày T sau khi đã bán từ sáng, không
intraday timestamps hoặc apply hồi tố. Future scheduling không có worker activate:
lookup ngày theo calendar đã commit. Content cũ/yield/loss/lines không overwrite.

**CURRENT FACT**: RecipeUseCases.create_version/get_active, contracts Recipe và
RecipeLine, repositories/recipe.py; models/recipe.py có uniqueProductVersion,
inclusive daterange exclusion; tests/integration/test_operational_paths.py và
supplier_operational_constraints kiểm graph/date/nonoverlap. Chưa public calendar
reader/change/preview/audit/cancel applicability. [ADR011](adr/ADR-011-historical-run-immutability-snapshot-policy.md)
giữ Run snapshot. Source/tests chỉ được đọc, không tests vừa chạy hoặc WIP verified.
**TECHNICAL CHOICE** operations/calendar revisions bên dưới, không sửa acceptedADR.

### 12.1. Luồng và semantics

Khách mở món → xem timeline current/future/history → chọn ngày từ T+1 → soạn
nội dung version mới hoặc đổi lịch version tương lai → preview BEFORE/AFTER đầy
đủ dates, yield/loss/Ingredient quantities, warnings → khách xác nhận **các thay
đổi cụ thể** → commit atomic → refresh P01/P02/timeline/C01/R01. P02 hôm nay vẫn
công thức hôm nay; từ ngày mới lookup version đúng ngày, không chọn max version.

Ví dụ hôm nay09/10: v1 từ01/10 đếnnull; khách muốn v2 từ10/10. Request phải có
explicit v1 effective_to=09/10 và v2 effective_from=10/10. Client gửi mỗi v2 mà
không sửa period v1 thì preview blocker RECIPE_PERIOD_OVERLAP; server không tự đóng.
Tại ngày10/10 chỉ v2, ngày09/10 vẫn v1. Phiên bản nội dung và version calendar là
hai identity khác nhau; kỳ inclusive không dùng to exclusive gây lệch một ngày.

Mỗi Recipe content version immutable; sửa yield/loss/lines dù version chỉ ở tương
lai cũng tạo version mới/UUID mới. Đổi lịch là applicability, không thay content.
Có thể dời ngày future version, rút version chưa hiệu lực khỏi lịch, hoặc đóng/
mở lại phần **tương lai** của period cũ bằng operations explicit. Nội dung và audit
version rút vẫn đọc được, không DELETE. Không tái dùng UUID đã rút để overwrite
nội dung mới, không recycle số version. Version cũ có period bắt đầu quá khứ được
đổi effective_to nếu mọi ngày≤T vẫn cùng recipe identity/content/availability.

Rút future version không tự kéo dài version trước hoặc chọn version sau để lấp
khoảng trống. Nếu khách muốn tiếp tục công thức cũ thì phải gửi SET_PERIOD tương
ứng và xác nhận. Gaps được preview hiển thị RECIPE_GAP_WARNING/affected_dates,
khách phải acknowledge rõ; Planning xử lý missingrecipe/exclusions theo policy
đã chốt, không auto-pause Product hoặc fabricate recipe. Empty/invalid new recipe
không trở thành publishable nhờ acknowledgement.

### 12.2. Route đối chiếu và types

Không FE0 endpoint nào nhận sửa lịch: P02 read hôm nay; I05 import tạo data theo
approved mapping, không có editor/explicit period-change flow. Giữ P01/P02/I05;
ba routes mới chỉ phục vụ timeline/change, không CRUD từng RecipeLine.

| Nhãn / method / route | Responsibility |
| --- | --- |
| N20 GET /stores/{store_id}/products/{product_id}/recipe-schedule | Đọc timeline/current/future/unassigned contents và version để chỉnh lịch. |
| N21 POST /stores/{store_id}/products/{product_id}/recipe-schedule/changes | phase preview hoặc commit; preview immutable, atomic explicit calendar+newversion changes. |
| N22 GET /stores/{store_id}/products/{product_id}/recipe-schedule/changes/{change_id} | Mở lại preview, blockers/diff hoặc committed receipt/audit của change, không compute lại. |

ResourceId/Version/Timestamp/envelope theo Planning; QuantityText/PositiveQuantityText/
LossRateText theo mục5; Dates theo timezone Store. JSON unknown fields422. Idempotency
key UUID cho mỗi N21 phase; If-Match schedule_version cần cả preview/commit.
Content={recipe_id:UUID,version:positiveint,yield_quantity:PositiveQuantityText,
yield_unit:Product.selling_unit,process_loss_rate:LossRateText,
ingredients:array {recipe_line_id:UUID,ingredient_id,quantity:PositiveQuantityText,
unit:Ingredient.base_unit}}. Name/active metadata reads cùng catalog snapshot như
P02; content facts không gồm price/stock. Existing empty content vẫn đọc được;
newversion cần1..100 distinct Ingredient lines, exact known units, finitepositive
qty/yield và0≤loss<1. Inactive Ingredient warning INGREDIENT_INACTIVE, không tự
thay Ingredient hoặc khác policy readers/engine. Không convert unit trong editor.

ScheduleItem={content:Content,assignment:{effective_from:date,effective_to:date|null}|null,
state:past|in_effect|scheduled|unassigned}. state derive date/assignment; unassigned
là content giữ nhưng không thuộc active calendar. Reader engine chỉ materialize
assigned ranges, cùng contract Recipe với known dates; P02 canonical dates không
bị đổi thànhnull. HISTORICAL INFORMATION trước S4.7: headers chưa hỗ trợ unassigned/canceled.
CURRENT FACT S4.7: migration0015 dùng recipes.assigned và partial inclusive exclusion;
withdraw giữ content/known stored dates, projection assignment=null. Domain capture
chỉ lấy assigned ranges; retained change/audit/receipts riêng. Layout đã freeze
trong historical scope notes (retired), không đổi accepted ADR. Nonoverlap của **calendar đang áp dụng**,
uniqueness identity/version và graph integrity vẫn giữ; không pretend schema hiện
có đã hỗ trợ việc rút version. Không chốt DB layout hoặc lén sửa accepted ADR.

N20 query status=past,in_effect,scheduled,unassigned defaultin_effect,scheduled;
limit50/max100,cursor,sort=effective_from,version (null assignments cuối, UUIDtie),
optional from_date/to_date ordered filterperiodintersect. Response
{store_id,product_id,as_of_date,schedule_version,catalog_version,
items:ScheduleItem[],minimum_change_date:T+1}; ETag schedule_version,
meta pagination exacttotalcount/null nếu chưa đủ và request_id. MissingProduct/
crossStore404; paused Product vẫn có timeline, không auto-activate menu. Pages
pin calendar+catalog versions/actor/filter, đổi dữ liệu409 LIST_VERSION_CHANGED,
không silently mix pages. Read past/unassigned để audit không grant sửa lịch sử.

### 12.3. N21 preview request/response

Preview body {phase:"preview",new_recipes:NewRecipe[],operations:ScheduleOperation[],
reason:string1..1000}. NewRecipe={client_reference:string1..64 unique,
yield_quantity,yield_unit,process_loss_rate,ingredients:[{ingredient_id,quantity,unit}]};
không recipe_id/version/namePrice. Ops union:

- {kind:"SET_PERIOD",recipe_ref:{recipe_id:UUID}|{new_recipe_reference:string},
  effective_from:date,effective_to:date|null};
- {kind:"WITHDRAW_FUTURE",recipe_ref:{recipe_id:UUID}}.

Mỗi recipe ref tối đa một operation; mọi NewRecipe phải được SET_PERIOD, không
create content orphan.≤20newversions/100ops, request≤64KiB; toàn outcome calendar
có≤1000futureassignments để preview bounded. Overflow/resource limits block,
không truncate. RecipeIDs cùng Product/Store, no rename/unit/Product activation.

Preview transaction chỉ giữ staging/reserved UUIDs+versions/digest, không canonical
calendar/content writes. Max+1 nội dungversion được **đề xuất** trong preview,
commit CAS/uniqueness giữ chỗ; concurrent allocation làm PREVIEW_STALE, không dùng
client gửi version hoặc đổi UUID/values trong commit lặng lẽ. Sorted operations/
lines canonical hóa numeric value exact, không display rounding.

DateRange={from_date:date,to_date:date|null}, inclusive, null là không có ngày kết thúc.
RecipeSchedulePreview=Response200 {change_id,status:"preview_ready"|"blocked",preview_digest:Version,
store_id,product_id,evaluated_at,as_of_date,minimum_change_date,schedule_version,
catalog_version,before:ScheduleItem[],after:ScheduleItem[],changed_ranges:DateRange[],
new_contents:Content[],required_permissions:string[],blockers:Notification[],
warnings:Notification[],required_warning_acknowledgements:string[],can_commit:boolean}.
Only diff domain relevant dates/content rows; full affectedtimeline đủ thấy overlaps/
gaps, không chỉ mộtnewrow. Canonical blockers vẫn trả previewblocked200 để FE sửa,
syntax/type/foreignIDs theo generalerrors; no fake successcommit. Preview retained
không default expires tự commit; validity bởi day/CAS/inputrights, không hiddenTTL.

Example preview request, synthetic Storedate09/10, oldrecipe01/10→null:

```json
{"phase":"preview","new_recipes":[{"client_reference":"recipe-next","yield_quantity":"1","yield_unit":"cup","process_loss_rate":"0","ingredients":[{"ingredient_id":"00000000-0000-0000-0000-000000000003","quantity":"180","unit":"ml"}]}],"operations":[{"kind":"SET_PERIOD","recipe_ref":{"recipe_id":"00000000-0000-4000-8000-000000000020"},"effective_from":"2026-10-01","effective_to":"2026-10-09"},{"kind":"SET_PERIOD","recipe_ref":{"new_recipe_reference":"recipe-next"},"effective_from":"2026-10-10","effective_to":null}],"reason":"Thay công thức từ ca kinh doanh ngày mai"}
```

### 12.4. Validation và commit

Validate outcome calendar inclusive/nonoverlap theo Product, positiveversion,
knownforeignrefs/units, effective_to≥from, dates/UTC overflow; loại affected
interval ngày≤T thì **before/after recipe identity/content/availability phải giống**.
Newversion/newassignment từT+1; currentassignment bắt đầu quá khứ giữ from,
closing current atT được vì ngàyT vẫn sameRecipe; không chỉ validate “mọi from≥T+1”
rồi chặn closure hợp lệ. WITHDRAW_FUTURE chỉ assignment có from>T, không rút
recipe đã từng áp dụng. Existing futureperiod có thể dời/withdraw, nhưng không
được chèn vào≤T. Entirepast recipes không mutate dưới guise futureoperation.

Commit body {phase:"commit",change_id,preview_digest,confirm:true,
acknowledged_warning_codes:string[]}; không operations/content/reason mới (đổi
reason thì preview mới). If-Match scheduleversion gốc; Idempotency-Key khác phase
preview. Warning acknowledgement exact computed list, không unblock overlap,
auth/history/units/negativeqty. Warning gap hiển thị periods kết quả, không
estimate lostsales/costrisk hay solver proof bằng preview.

RecipeScheduleReceipt=Response200 {change_id,status:"committed",preview_digest,store_id,product_id,
committed_at,schedule_version_before,schedule_version_after,
created_recipe_ids:UUID[],affected_recipe_ids:UUID[],audit_reference:UUID,
updated_resources:{menu:true,recipes:true,inventory:false,sales:false,forecast:false,
retained_runs:false},warnings:Notification[]}. No-op toàn timeline/content giữ
scheduleversion, changed=false/arrays[],updated menu/recipesfalse; receipt mới
vẫn recorded. Response có changed:boolean required cả changed/no-op.

Trong transaction commit: recheck actor/membership/actions+Storedate, catalogunits/
Product/versionreadset → lock Productcalendar/versionreservation → verify pinned
diff ngày≤today không đổi + fullfuture nonoverlap → create immutable newcontent,
apply explicit applicabilityoperations → increment calendar/version → append
before/after/reason/actor/preview/sourceaudit+idempotencyreceipt → commit. Anyfailure
rollback whole, không oldclosed+newmissing. Snapshotdate đổi làm operation ảnh
hưởng ngày hôm nay:409 RECIPE_DATE_POLICY_CHANGED, yêu cầu re-preview; không rebase
ngày hoặc silent partialapply. Nếu Storedate đổi nhưng can prove lịch vẫn future,
v1 vẫn yêu cầu re-preview cho mọi dayrollover để khách review minimumdate rõ ràng.

Content hoặc rawcanonicalvalidity khác giữa preview/commit409 PREVIEW_STALE;
If-Match khác412 RECIPE_SCHEDULE_REVISION_CONFLICT, absent428. Retry receiptlookup
sau currentauthorization trước staleCAS/daychecks, samekey/payload giữreceipt,
không activate again; keydifferentpayload409 IDEMPOTENCY_KEY_REUSED. Uncertain
commit đọc receipt+committedcalendar qua freshSession trong verification sau này,
không mù create version. N22 trả200 {change_id,status:"preview_ready"|"blocked"|
"committed",preview:RecipeSchedulePreview,receipt:RecipeScheduleReceipt|null,
audit:RecipeScheduleAudit|null}. Receipt/audit chỉ có khi committed; preview là
bản đã giữ, không tái tính bằng current DB. Quyền đọc hiện hành theo Store/action;
đọc past change không thay schedule.

### 12.5. Quyền, audit, effects và acceptance

N20/N22 require menu.read+recipe.read+ingredient.read. N21 require cả readset này
và recipe.manage_effectivity; thêm recipe.create_version nếu request tạo newcontent.
Owner có quyền đúng Store; Staff phải được Owner cấp từng action. Không suy
create_version cho phép thay calendar cũ. Unknown/foreign read/receipt deny như
P02, no one-timeapprovalbypass cho đến approved allowlist. Price/budget không
trong response, không buộc procurement.cost.read. Quyền mới đã vào AUTH catalogue
permissions-v2 và Owner invitation có thể chọn nếu descriptorcurrent.

RecipeScheduleAudit immutable {change_id,actor_user_id,store_id,product_id,reason,occurred_at,
preview_digest,calendar_before_version,calendar_after_version,before,after,
new_content_ids,operations,acknowledged_warnings,request_id}; no delete oldfacts.
N22 là retained change/audit viewer, không tạo endpoint auditglobal theo DBtable.

Không ghi sales/USAGE/stock hoặc recomputeforecast/planning. Recipe/yield/loss đổi
thay Ingredient demand của **Run mới** theo datedBOM; forecast Productquantities
không tự đổi identity. Run đã capture/input/result giữ nguyên, kể cả futurewindow
có ngày vừa đổi. Queued Run chưa capture giữ accepted config nhưng operational
capture theo thời điểm thực như PLAN7; có thể đọc lịch mới nếu commit trước capture,
không nói accepted đã freeze mọi operational fact. C01/R01 refetchfuture recipes;
Save yêu cầu vẫn độc lập readiness, requirements/winner không đổi. Imported new
version vẫn không autoclose: I05 không được hiểu missing closure là instruction.
Không ghép recipecalendarchange vào import canonicalbatch trong v1 contract này;
khách đóng/điều chỉnh calendar qua preview explicit hoặc tạo content qua editor,
không dùng hai transaction rời để giả atomic recipe switch.

Errors thêm409 RECIPE_PERIOD_OVERLAP/PREVIEW_BLOCKED/PREVIEW_STALE/
RECIPE_DATE_POLICY_CHANGED/RECIPE_CHANGE_NOT_READY;412 RECIPE_SCHEDULE_REVISION_CONFLICT;
422 HISTORY_CHANGE_NOT_ALLOWED/INVALID_RECIPE_REFERENCE/INVALID_UNIT/
INVALID_RECIPE_CONTENT/INVALID_DATE_RANGE/INVALID_WARNING_ACKNOWLEDGEMENT;
413 RESOURCE_LIMIT_EXCEEDED; general401/403/404/422/428/503 như mục8. Sourcecorrupt
503 CATALOG_INTEGRITY_UNAVAILABLE, không auto chọn maxversion hoặc skipinvalidrow.

Acceptance specifications (design đã duyệt; kết quả thực chạy S4.7 xem task notes):

1. Oldfrom01/10→null, explicitclose09/10/newfrom10/10: hôm nay v1, ngàymai v2.
   Chỉnewversion gâyoverlap block, không tự closure; inclusive đúng dateboundary.
2. 10giờ đổi hôm nay/quá khứ blocked HISTORY_CHANGE_NOT_ALLOWED; Storemidnight
   invalidpreview, không rebase. Nội dung cũ/pastdates/Run snapshots giữ nguyên.
3. Futuremove/withdraw explicit, content retained; no autofill/reopen; gap cần
   acknowledgement và Planning exclusions theo policy, không auto-pause Product.
4. Sửa futurecontent tạo newUUID/version; concurrentpublication một thắng/stale,
   fault rollback oldcalendar+newcontent+audit/receipt, no orphan hoặc timelinegap.
5. Differentunits/foreignrefs/emptynewcontent/negativeyield/lossinvalid blocked;
   no syntheticconversion, preview không solver/LLM/tồn kho write.
6. Grant create_version thôi không editcalendar, Staff manage+reads mới allowed;
   revoked before fence chặn, retry không permissionbypass hoặc duplicateversion.
7. N20 pages pin version; N22 retaineddiff/history; P02 currenttoday không đổi,
   horizon từngngày/forecastreuse/configacceptance/C03/C05/PDF không reinterpret.

FE bổ sung timeline/current/future/unassigned, form newversion/đổi lịch, preview
before-after+gapwarnings, confirm/apply và changehistory/resume. Tách “xem recipe
hôm nay” và “đổi từ ngày…”; minimumdate server, không browsertimezone. Không
tạo form genericDBCRUD hoặc updateInventory từ Recipe.
### 12.6. CURRENT FACT — implementation S4.7

N20/N21/N22 đã registered đúng routes/methods/phases ở `app/api/recipe_schedule.py`;
current Store auth/rights, product-scoped calendar/catalog versions, immutable
preview/read và atomic commit. Timeline source/runtime details và JSON examples:
[feature](features/RECIPE_SCHEDULE.md), [verification](runbooks/FULL_TEST_FLOW.md).
Public planning/readiness/config persistence hiện đã có; xem Planning contract.

TECHNICAL CHOICE: request≤64KiB,20 new/100 ops/1000 future; preview data≤1MiB,
N20 data≤1MiB, retained N22≤4MiB chứa preview/audit/receipt. Vượt trả lỗi rõ,
không truncate hoặc tạo orphan. N22 không cần parser/worker/provider/current calendar
để thay thế retained before/after. No-op giữ schedule version, receipt/audit vẫn ghi.
Nguồn gốc baseline và khác biệt wire xem [compatibility changes](CONTRACT_COMPATIBILITY_CHANGELOG_VI.md).

## Inventory

<a id="inventory-semantics"></a>
## 2. Luồng khách và quantities

Import tạo/bind Ingredient trước → khách nhập lô có thật N6 → V01/V02 đọc stock →
V03 thêm lô/V04 audit → kiểm kê import chỉnh lô đã định danh. Recipe→Kho bằng
ingredient_id canonical. Không receipt từ recommendation/PO/chưa nhận hàng.

Store-local as_of_date=today, timestamp UTC Z. Quantity là QuantityText theo Catalog,
PositiveQuantity là alias PositiveQuantityText (>0), không rational object của
C03. SignedQuantity là plain decimal string signed (cho dấu trừ, không dấu cộng,
không exponent/negativezero); regex `^-?(0|[1-9][0-9]*)(\.[0-9]+)?$`, cấm âm0.
Quantity trong schemas dưới đây là alias QuantityText; mọi unit exact
Ingredient.base_unit. Không tự g↔kg. Public decimal input không áp bounds tiền
cho quantities; request≤64KiB, output giữ exact không truncate/round.

Các quantities của Ingredient:

- on_hand_quantity: tổng balance hiện hành mọi lô, kể cả hết hạn; là tồn vật lý
  **đã ghi nhận**, không chứng minh đã kiểm kê đủ kho.
- usable_quantity: tổng lô có balance dương đủ điều kiện dùng ngày as_of_date.
  expiry<as_of_date không dùng, expiry=as_of_date còn dùng. Null nếu có lô dương
  thiếu expiry bắt buộc hoặc fact/date không hợp lệ; usable_known_quantity vẫn
  trả tổng phần xác định. usable_availability là known|unknown.
- expired_quantity: tổng balance dương có expiry đã biết<as_of_date. GET không
  ghi movement EXPIRED hoặc tự giảm tồn vật lý.
- stock_completeness: CONFIRMED|UNKNOWN. Không có lô thì recorded on_hand="0",
  nhưng không tự xác nhận tồn thực tế bằng0. Planning cần declaration toàn phạm
  vi theo Import13.5; một receipt không đủ chứng minh toàn bộ stock.

received_date null có warning, không chặn usable hiện tại. Ngày nhận đã biết trong
future không biến lô thành inbound, loại khỏi usable và báo lỗi dữ liệu. Ingredient
tracked thiếu expiry thì usable unknown; nontracked null expiry được dùng với
warning EXPIRY_UNKNOWN. Không suy tuổi lô/expiry/cost. Unknown unit_cost không
ảnh hưởng tổng quantities; availability của cost riêng. Chưa có quarantine policy.

**Gần hạn đã chốt:** lô usable có balance dương và0≤expiry−as_of_date≤7 ngày;
không bao gồm expired hoặc expiry unknown. **Sắp hết đã chốt:** ngưỡng Owner theo
base unit; usable_quantity đã biết≤threshold thì low_stock. Threshold null khác0;
thiếu ngưỡng thì low_stock_assessment.status="unknown", không suy từ forecast.

Ingredient status theo thứ tự:
1. expired nếu recorded physical>0, mọi phần dương đều xác định hết hạn và phạm
   vi stock CONFIRMED;
2. empty nếu usable_quantity="0" đã biết và phạm vi CONFIRMED;
3. low_stock nếu threshold/usable đã biết, phạm vi CONFIRMED và usable≤threshold;
4. near_expiry nếu có lô usable gần hạn;
5. watch nếu completeness/usable/threshold chưa biết hoặc warning ngày;
6. stable khi mọi check biết, không có điều kiện trên.

status_reasons[] và các assessment/counters giữ được nhiều dấu hiệu đồng thời;
status chính không xóa cảnh báo khác. Lot status: empty|expired|near_expiry|watch|
stable theo balance/expiry, không dùng threshold của Ingredient.

use_first=true cho duy nhất lô dương đủ điều kiện đứng đầu FEFO: expiry tăng dần,
null cuối; received_date tăng dần/null cuối; UUID tie-break. Đây là thứ tự đọc,
không ghi USAGE/tiêu hao. location=null/location_availability=unsupported vì chưa
có location model. batch_code adapter=lot_code nullable, không unique identity.

<a id="inventory-reads"></a>
## 3. V01–V04 requests/responses và snapshots

CURRENT FACT: V01 cũng là nguồn discovery canonical Ingredient của Store cho
picker hiện hành, không chỉ các Ingredient có stock lot hoặc đã xuất hiện trong
P02. Query q/ingredient_id/status/sort/limit/cursor và metadata paging hiện hữu;
FE đọc đủ pages theo snapshot và ingredient_active, không dựng ID từ tên. Ingredient
không lot vẫn có row; completeness/unknown phải giữ, không suy confirmed zero stock
từ không có lot. N6 nhận supplier_id/unit_cost nullable; supplier search độc lập
và warehouse/location writer chưa có. Không suy quyền supplier từ inventory.read.
Source: PublicReadRepository.stock/inventory, PublicReads.inventory và N6 DTO.

Envelope/types/errors theo [Planning](PROCUREMENT_API_CONTRACT_VI.md#planning-types).
V01 query q1..200 case/diacritic-insensitive name/SKU; repeated ingredient_id UUID,
status list enum trên, limit50/max100,cursor,sort=name|-name|nearest_expiry (UUID
tiebreak). Filters AND, status values OR. Summary Store-wide unfiltered, response
filtered total_count riêng. Missing IDs chỉ explicit filter unknownwithinStore,
không tiết lộ existence Store khác. Known catalog Ingredient no lots vẫn row với
recorded totals0/completenessUNKNOWN; missing ID không fake row0. Active false giữ
stock/history, ingredient_active flag, không auto-delete.

IngredientStock={ingredient_id,name,sku:string|null,ingredient_active:boolean,
unit,on_hand_quantity,usable_quantity:Quantity|null,usable_known_quantity,
usable_availability,expired_quantity,stock_completeness,lot_count:int,
positive_lot_count:int,nearest_expiry:date|null,status,status_reasons:Notification[],
low_stock_assessment:{status:"low"|"ok"|"unknown",threshold:Quantity|null,
version:Version|null},near_expiry_lot_count:int}. Nearest expiry only eligible known
positive lot, không chọn expired. Summary={ingredient_count,positive_lot_count,
near_expiry_lot_count,near_expiry_ingredient_count,expired_lot_count,
low_stock_ingredient_count:int|null,unknown_assessment_ingredient_count:int}.
Low countnull nếu không đánh giá được toàn Store; không show0 cho missing thresholds.

V02 query snapshot_id?,lot_limit50/max100, không body; data=IngredientStock+
{lots:InventoryLot[],lots_page:{next_cursor,total_count},threshold_version:Version}.
V03 query snapshot_id?,limit,cursor,sort=expiry_date,batch_code duy nhất; data=
{ingredient_id,items:InventoryLot[]}. InventoryLot={lot_id,batch_code,quantity,unit,
supplier_id:UUID|null,received_date:date|null,expiry_date:date|null,status,
use_first:boolean,location:null,location_availability:"unsupported",updated_at,
version,origin:"OPENING_STOCK"|"ACTUAL_RECEIPT"|"UNKNOWN",cost:{availability:
"known"|"unknown"|"forbidden",unit_cost:MoneyText|null,currency}}. Cost omitted?
Không: cost object required, forbidden→null và không derived values/sortfiltercost.

V04 query snapshot_id?,limit,cursor,sort=-occurred_at; data={ingredient_id,
items:Movement[]}. Movement={movement_id,lot_id,batch_code,kind:receipt|usage|waste|
expired|count_correction|manual_adjustment,quantity_delta:SignedQuantity,unit,
occurred_at:Timestamp,recorded_at:Timestamp,actor_user_id:UUID|null,reason:string|null,
reference:{type,id}:object|null,origin:OPENING_STOCK|ACTUAL_RECEIPT|IMPORT_COUNT|
UNKNOWN}. Null old audit facts remainunknown; do not fabricate historical actor.
No money fields V04. List recent movements không reconstruct whole balance.

Meta everyread={request_id,as_of_date,updated_at:Timestamp|null,snapshot_id:Version,
data_version:Version,pagination?}. TECHNICAL CHOICE optimistic snapshot token binds
Store/date/inventory+catalog+threshold revision. Không historical copy service:
same snapshot đọc được chỉ khi versions hiện hành còn khớp; changed/date rollover409
SNAPSHOT_NOT_AVAILABLE yêu cầu refresh cả set. Cursor bind actor,filters,snapshot;
crossfilter422 INVALID_CURSOR, privileges changed recheck, versionchanged409. Join
một short consistent read transaction; initialV02 page lô cùng snapshot summary.

Ví dụ V01 (đã Owner xác nhận phạm vi, 12 L ghi nhận trong một lô nontracked):

```json
{"data":{"summary":{"ingredient_count":1,"positive_lot_count":1,"near_expiry_lot_count":0,"near_expiry_ingredient_count":0,"expired_lot_count":0,"low_stock_ingredient_count":0,"unknown_assessment_ingredient_count":0},"items":[{"ingredient_id":"00000000-0000-0000-0000-000000000003","name":"Sữa","sku":null,"ingredient_active":true,"unit":"l","on_hand_quantity":"12","usable_quantity":"12","usable_known_quantity":"12","usable_availability":"known","expired_quantity":"0","stock_completeness":"CONFIRMED","lot_count":1,"positive_lot_count":1,"nearest_expiry":"2026-10-25","status":"stable","status_reasons":[],"low_stock_assessment":{"status":"ok","threshold":"2","version":"threshold-1"},"near_expiry_lot_count":0}],"missing_ingredient_ids":[]},"meta":{"request_id":"req-stock","as_of_date":"2026-10-09","updated_at":"2026-10-09T02:00:00Z","snapshot_id":"stock-8","data_version":"stock-8","pagination":{"limit":50,"next_cursor":null,"total_count":1}},"error":null}
```

<a id="inventory-receipt"></a>
## 4. N6 — opening stock và hàng thực nhận

POST /stores/{store_id}/inventory/receipts, synchronous201; Idempotency-Key required,
body discriminated origin OPENING_STOCK|ACTUAL_RECEIPT. Common fields
{receipt_identity:{source_system_key,source_record_id},ingredient_id,supplier_id:
UUID|null,lot_code:string1..128|null,quantity:PositiveQuantity,unit,received_date:
date|null,expiry_date:date|null,unit_cost:MoneyText|null,currency,observed_at:Timestamp,
reason:string1..1000,expected_inventory_version:Version}. source keys1..128 nonblank,
unique Store+source_system_key+source_record_id; not filename/lotcode identity.
Currencyexact Store, unit_cost null do chưa biết, known0 valid. Dates knownreceipt≤today,
expiry≥knownreceipt, expiry tracking requires date; expired **opening stock** có
thể ghi để phản ánh vật lý, cảnh báo unusable. New receipt alreadyexpired warning
không che thông tin; không tự giả chất lượng/return workflow. observed_at là lúc
khách thực sự kiểm/nhận, bắt buộc known≤now; received_date unknown giữnull, không
derive từ observed_at. OPENING_STOCK phải observed current và không
intervening observation/source events của đúng Ingredient trong Store; CAS changed409 INVENTORY_VERSION_CONFLICT.

TECHNICAL CHOICE phù hợp ADR009: OPENING_STOCK quantity là **số còn hiện tại** của
một lô đã có thực, không lượng mua trước đây. Tạo lot balancequantity + positive
COUNT_CORRECTION từ baseline0 với reason và reference_type=OPENING_STOCK;
occurred_at=observed_at, recorded_at=server time. Không bịa RECEIPT lịch sử hoặc
received_date. ACTUAL_RECEIPT quantity là thực nhận lần này; lô mới + positive
RECEIPT, reference_type=ACTUAL_RECEIPT. Đây là design opening writer mới, internal
receive trước S4.6 chỉ RECEIPT; public N6 hiện hỗ trợ cả hai origin. Không thêm movement type.
Không reuse canonical lot đã tồn tại bằng lot_code; muốn countlot dùng import
snapshot. Source identity trùng cùng normalized payload trả receipt cũ200, khác
payload409 RECEIPT_IDENTITY_CONFLICT; không correction hàng cũ qua newkey/newlot.
Client phải xác nhận source identity; key khác không bằng chứng lô khác.

Response {receipt_id:UUID,origin,lot:InventoryLot,movement:Movement,
inventory_version:Version,audit_reference:UUID,warnings:Notification[]}.
Idempotent replay trả retained mutation receipt sau current permissions check,
không live lot balance sau các count. Lot+movement+identity nguồn+idempotency+
audit atomic. quantity = 0 không tạo lot/movement,422; toàn bộ tồn kho known0 được
declaration qua Import readiness declarations, không fake lot0. Không tự đánh
CONFIRMED toàn Ingredient chỉ vì nhận một lô; completeness phải khai báo phạm vi.

```json
{"origin":"OPENING_STOCK","receipt_identity":{"source_system_key":"store-opening-20261009","source_record_id":"sua-lot-01"},"ingredient_id":"00000000-0000-0000-0000-000000000003","supplier_id":null,"lot_code":"LOT-01","quantity":"12","unit":"l","received_date":null,"expiry_date":"2026-10-25","unit_cost":null,"currency":"VND","observed_at":"2026-10-09T02:00:00Z","reason":"Ghi nhận số dư lô có thật khi bắt đầu dùng ShelfCash","expected_inventory_version":"stock-7"}
```

<a id="inventory-threshold"></a>
## 5. N8 — Owner khai báo ngưỡng sắp hết

PUT /stores/{store_id}/inventory/{ingredient_id}/threshold Owner-only;
If-Match + Idempotency-Key, version đọc từ V02 dù config chưa có (`unconfigured-*`).
Body {minimum_usable_quantity:Quantity|null,unit,reason:string1..1000}.
Response200 {ingredient_id,minimum_usable_quantity,unit,version,updated_at,updated_by}.
Null clearconfig→unknownassessment;0 nghĩa chỉ hết dùng mới chạm ngưỡng. Không
unit conversion, không threshold từ forecast, không thay planning safety/storage
constraints. threshold update là UI alert setting, audit+CAS atomic, storedRun giữ
nguyên. Version changed412 THRESHOLD_REVISION_CONFLICT; missing428; Owner củaStore
khác404, Staff403. Retry key semantics như mutationPlanning, no-op giữversion.

<a id="inventory-acceptance"></a>
## 6. Permissions, errors và acceptance

V01–V04 require inventory.read + ingredient.read. N6 inventory.receive+
inventory.read+ingredient.read; unit_cost nonnull thêm procurement.cost.read để
khách kiểm giá mình đang ghi (inventory.receive authority cho cost receipt);
unit_cost null do chưa biết không buộc costread. Lotcost redaction có cấu trúc known/unknown/
forbidden là **TECHNICAL CHOICE riêng Kho**, không đổi whole-denial Planning/Import.
No values/valuation/ordering leak khi thiếu costread. Threshold Owner-only.
Owner/Staff active checks theo [Auth](AUTHORIZATION_CONTRACT_VI.md#auth-session).

400 INVALID_REQUEST;401 UNAUTHENTICATED;403 PERMISSION_DENIED/CSRF_CHECK_FAILED;
404 RESOURCE_NOT_FOUND scope-safe;422 VALIDATION_ERROR/INVALID_UNIT/
REQUIRED_EXPIRY_MISSING/INVALID_FILTER/INVALID_CURSOR;428 PRECONDITION_REQUIRED;
412 THRESHOLD_REVISION_CONFLICT;409 SNAPSHOT_NOT_AVAILABLE/INVENTORY_VERSION_CONFLICT/
RECEIPT_IDENTITY_CONFLICT/IDEMPOTENCY_KEY_REUSED/STALE_STOCK_OBSERVATION;503
SERVICE_UNAVAILABLE. Errors details field_errors/blockers, không SQL/secrets.

Acceptance specifications; kết quả targeted và giới hạn xem [current verification runbook](runbooks/FULL_TEST_FLOW.md):
1. Expiredphysical retained, usable0; expiryday dùng được, read không movement.
2. Nontracked missingdate warn; tracked nhưng thiếu expiry unknown, không fake dates;
   no lots recorded0/completenessunknown không whole-stock0.
3. Near-expiry7 inclusive, excludes expired; low threshold null unknown/zeroexact;
   flags/counters phân biệt lotcount và ingredientcount, summary unfiltered.
4. V02 firstpage/V03/V04 pinned snapshot; stockchange409 refresh, cursor không
   ghép filters/Store; no reconstruction from recent page.
5. Opening12 tạo COUNT_CORRECTION+12, actualreceipt5 tạo RECEIPT+5; count12→10
   là -2 trên lô đã định danh; không initialreceipt giả/unknownlot từ count.
6. Same source/key retry một lot/movement; changedsource409; fault rollback mọi
   writes, committed receipt đọc freshsession khi implementation verification.
7. Cost forbidden null không metricleak; ngưỡng Owner cập nhật auditedCAS,
   Staffdeny/crossStore404; revoke trước commit fence không writes.

CURRENT FACT S4.6: read projections/snapshots/counters, threshold storage,
receipt identity/actor audit/idempotency, declaration loader, cost masking/current
auth và N6/N8 HTTP/OpenAPI đã implement. Inventory seam compose whole-import.
Targeted verification không phải full-suite/production acceptance; xem S46 task notes.

PROPOSAL/OPEN: purchase-history workflow. Readiness, recipe timeline, public planning
worker và config hiện đã có. Không tự forecast, USAGE hoặc nhận hàng từ kế hoạch.


## N6 temporal clarification đã duyệt — CA-019, 11/10/2026

OPENING_STOCK current physical observation không dùng minute TTL. Fresh CAS không
chứng minh observation còn hiệu lực. Dưới cùng canonical fence/transaction, kiểm
movement occurred_at và recorded_at, lot updated_at, count observations (kể cả
NO_OP) của đúng Ingredient/Store; sự kiện mới hơn trả409 STALE_STOCK_OBSERVATION.
Thiếu movement/balance evidence nhất quán trả409 STOCK_OBSERVATION_UNVERIFIABLE,
khách quan sát/đối chiếu lại. Không block do nguyên liệu khác; không rebaseline lượng
đã thuộc lô hiện có. Label trùng hoặc thiếu evidence phân biệt lô khi còn tồn trả409
OPENING_STOCK_ALREADY_RECORDED, dùng kiểm kê lô đã định danh; label không dùng bind
identity. Client phải xác nhận lô vật lý riêng theo contract, new source key không
phải bằng chứng đủ để ghi lại lượng cũ.

ACTUAL_RECEIPT cho phép real event gửi muộn với source identity mới, current CAS và
invariants hợp lệ; không chặn chỉ vì movement sau observation. Giữ occurred_at
khác recorded_at, received_date unknown vẫn null. Khi business date receipt/observation
trước ngày Store hiện tại cảnh báo LATE_RECEIPT_RECORDED. Không sửa historical Run,
không mở correction/reversal/purchase history. Replay current authorization trước
CAS/freshness, giữ retained receipt; không ghi stock hai lần.
