# Planning — configuration, computation and retained results

CURRENT FACT: C01-C05/C08, N1-N4/N9-N11 and readiness/shared PDF jobs are wired.
C06 is merged into C05; C07 polling responsibility is C03. This contract owns
approved requirements/budget/forecast/capture/strategy/result meanings and
workflow states. Source DTOs/OpenAPI own request/response structure.

ACCEPTED DECISION: a recommendation is not customer selection or an order. No
GET recomputes a forecast/solver/provider result. Current Store-sensitive rights
apply to reads/replay/workers/PDF; no permissive staging account. Known configuration
is explicit and versioned. BASELINE and DEFAULT_BASE95 are operator actions,
not automatic facts/defaults for an unknown Store. Example caps are synthetic.

See [API](API_CONTRACT.md), [Authorization](AUTHORIZATION_CONTRACT_VI.md),
[Import](IMPORT_MAPPING_API_CONTRACT_VI.md) and [runbook](runbooks/FULL_TEST_FLOW.md).
S4.11 UI remains PARTIAL; implementation registration is not fresh verification.

<a id="planning-flow"></a>
## 1. Luồng khách dùng và endpoints

C01 đọc setup → khách chọn default/custom/saved và ngày bắt đầu → C02 nhận Run →
FE đọc C03 đến terminal → xem ba kế hoạch, winner hoặc lý do không có winner.
Custom chạy mà chưa Save được; Save độc lập. Run đã nhận giữ cấu hình; chỉnh setup
chạy lại dùng key mới/UUID mới. Không selected_option, xác nhận chọn phương án,
tạo PO hoặc tự đặt hàng trong cụm. LOW/BASE/HIGH là paths, không ba kế hoạch.

| Endpoint FE gốc | Xử lý trong design | Lý do / authority |
| --- | --- | --- |
| C01 GET /stores/{store_id}/planning-context | GIỮ ID/route | ĐÃ CHỐT GET context, không computation/Save. |
| C02 POST /stores/{store_id}/procurement-plans | GIỮ ID/route | ĐÃ CHỐT ba mode và nhận Run xử lý nền. |
| C03 GET /procurement-plans/{plan_id} | TECHNICAL CHOICE: GIỮ ID/route; plan_id chính là run_id | Một UUID public; không thêm job_id/plan_id thứ hai. Placeholder trong code có thể gọi run_id, URL thực không đổi. |
| C07 GET /procurement-plans/{plan_id}/strategies | TECHNICAL CHOICE: GỘP trách nhiệm vào C03 v1 | Chỉ ba sources; đọc cùng aggregate/grouping, không route trùng hoặc compute khi đổi tab. |
| C04/C05 | GIỮ, mục16 | Navigator → kiểm tra captured stock/purchases/daily balances/lý do từ retained engine. |
| C06 | GỘP vào C05, mục16 | Cùng retained daily rows đủ vẽ theo path; không endpoint chart riêng hoặc Ingredient confidence interval giả. |
| Save/budget settings | CẤU HÌNH PLANNING — mục 14 | Save/quản lý requirements và trần Store, độc lập với C02. |
| C08 GET /procurement-plans/{plan_id}/explanation | GIỮ, mục15 | Lý do/cảnh báo engine đã lưu; không LLM dependency. |
| C09 | DEFERRED | Không draft PO/order workflow trong scope hiện hành. |
| What-if | NEEDS_REVIEW | Đánh giá riêng giá trị/dependencies; chưa phê duyệt inclusion hoặc deferral. |
| C10 POST /procurement-plans/{plan_id}/regenerate | GỘP C02 | Key mới/Run mới, không sửa Run cũ. |

C03 được mở rộng theo task review cụm này, không giả đã duyệt từ lượt cũ. Không
tạo ID endpoint mới. Các route được GIỮ hiện đã registered; các route GỘP/DEFERRED không được thêm.

<a id="planning-types"></a>
## 2. Planning-specific conventions — current approved contract

Response JSON luôn có data/meta/error. Success error=null; error data=null,meta={},
error={code,message,details}. Unknown request fields trả422, không silently ignore
option cũ từ FE v0. Notification={code,message,details}; details không có thì{}.
Blocker không được đổi thành warning để nhận Run.

| Type | Quy tắc |
| --- | --- |
| ResourceId | UUID canonical chữ thường có gạch; Store/Product/Run/saved. |
| Version | Opaque string1..128 ký tự; không so theo thứ tự lexical. |
| OptionId | Token immutable trong Run, không UUID và không permission credential. |
| BusinessDate | YYYY-MM-DD, theo IANA timezone Store;0001-01-01..9999-12-31 và phép cộng/trừ không overflow. |
| Timestamp | RFC3339 offset; BE xuất UTC Z, FE hiển thị timezone Store. |
| DecimalText | Regex `^(0|[1-9][0-9]*)(\.[0-9]+)?$`; không exponent/sign/space/NaN/Infinity/%, không JSON number. |
| PercentText | DecimalText0..100;≤3 chữ số nguyên,≤32 chữ số lẻ. Không round input. |
| MoneyText | DecimalText;≤18 chữ số nguyên,≤18 chữ số lẻ; currency Store. Resource bound, không settlement rounding. |
| UnboundedCountText | Chuỗi số nguyên không âm canonical, regex `^(0|[1-9][0-9]*)$`. FE giữ string hoặc dùng BigInt; không ép sang JavaScript Number khi vượt `2^53-1`. Dùng cho domain_size và combinatorial counters public có thể vượt safe integer. Python internal giữ integer exact. Packs/count nhỏ có bounds vẫn là JSON integer. |
| ExactQuantity | {numerator:string,denominator:string,decimal_view:DecimalText}; phân số không âm tối giản,denominator>0; view precision50/HALF_EVEN chỉ display. |
| Service | null khi requested0; nếu dương {numerator,denominator,percent_view}. Fraction là ratio exact; percent_view0..100 chỉ display, không threshold. |
| SignedDelta | Numerator signed integer string/denominator positive integer string/decimal_view signed decimal string. Không cộng quantities khác unit. |

Request≤64KiB; paths1..3 unique; mỗi path≤50 overrides unique. Run≤50 Products active,
100 Ingredients cần thiết,100 offers,1000 lot rows. Biết vượt trước nhận:422
RESOURCE_LIMIT_EXCEEDED; phát hiện khi capture:computation_blocked. Không tự cắt scope.
C01 trả toàn bộ saved active được phép đọc trong Store, không phân trang/cắt danh sách;
không đọc trọn thì503. Archived đọc qua detail mục 14, không liệt kê ở C01. Tên
saved1..200 ký tự có nội dung, không bắt unique. Không tự giới hạn số saved được lưu
trong v1; Save và lifecycle quy định tại mục 14.

Admission limits KHÔNG chứng minh50 Products chạy nhanh hoặc mọi nguồn input đều
numeric-supported. Exact engine có capacity1000 digits và native numeric guards riêng.
Vượt khả năng tính: NUMERIC_UNSUPPORTED, không round/epsilon/fabricated zero.
Percent→ratio dịch Decimal exponent−2 exact, independent ambient context.

<a id="planning-policy"></a>
## 3. Policy sản phẩm giữ nguyên — ĐÃ CHỐT

- Default BASE/P50≥95% TỪNG Product trên tổng 7 ngày, overrides=[],budget=null.
  Không khôi phục setup lần trước. Không hứa từng ngày 95%, xác suất95%, accuracy
  hoặc ngưỡng tối ưu đã được real-data chứng minh.
- Custom/saved chọn≥1 LOW/BASE/HIGH; mức chung mỗi Product/path; override thay đúng
  Product/path, thấp/bằng/cao đều được. Không đổi serving priority hoặc aggregate
  servings khác unit. Requested 0 không ràng buộc, service=null, không gán100%.
- Khách chọn start; D=start−1,end=start+6,horizon7. FE không gửi scope/model/forecast
  ID/strategy/currency/stochastic options. Các paths là design paths, không xác suất.
- Trần budget cấu hình Store; chưa biết không unlimited. Default/omit/null budget
  dùng trần HIỆN HÀNH tại nhận; riêng≤trần;0 thật. Không clamp hoặc sửa saved. Cost
  intent là purchase+delivery; missing fees không 0, generic fees không relabel delivery.
- LEAN xây LOW100% từng Product; BALANCED BASE100%; PROTECTED HIGH100%. Requirements
  khách dùng trong generation lẫn exact validation, không chỉ lọc vài baskets cũ.
- Customer-pass/construction-pass min outlay. Customer-pass/construction-miss:
  max minimum Product fulfillment → max equal-weight mean → min outlay → stable
  basket, xét construction path, bỏ zero-request Products. Không demand dương bỏ
  service objectives. Customer-fail reference không gọi best_available thiếu proof.
- Winner exact/hard-valid, không blocker liên quan, customer-pass; min cost, hòa so
  minimum Product HIGH→BASE→LOW cao hơn rồi stable basket. Zero-demand path trung hòa.
  INCOMPLETE/UNPROVEN incumbent có thể recommend; errors vẫn errors. Không certified
  global optimum từ native OPTIMAL. Winner không tự đặt hàng.
- Group plan/evaluation đồng nhất, source evidence riêng; không ép3 baskets khác nhau.
- Reuse forecast không phụ thuộc requirements/budget/recipe/stock/supplier price;
  đổi input forecast/actual model/config cần bản phù hợp mới.
- Menu scope toàn Product active Store tại capture. Exclude món lỗi riêng có lý do,
  vẫn winner trên computed scope; không giả coverage toàn menu.

<a id="planning-context"></a>
## 4. C01 — response đọc setup

Không body/query. GET không tạo forecast/model/Run/solver/saved. DB facts dùng cùng
read-only snapshot, detached preflight; không giữ transaction khi verify artifact FS.
Capability true chỉ khi PUBLIC flow đã wired/enforce quyền/lưu đọc outcome; pure
selector có không tự làm public capability true.

Fields data đều REQUIRED; nullable chỉ khi nói rõ:

| Field | Type / semantics |
| --- | --- |
| store_id,currency,timezone | ResourceId,currency string,IANA timezone string. |
| observed_at,context_version | Timestamp,Version facts/config preflight; không đảm bảo live facts giữ nguyên sau GET. |
| latest_business_date | Date/null=max SalesDaily.business_date có row Store≤ngày Store hiện tại; zero row vẫn tính; KHÔNG completeness watermark. |
| defaults | {requirements_mode:"default",horizon_days:7,cutoff_date:date/null,forecast_start_date:date/null}. |
| supported_horizon_days,supported_strategies,supported_paths | [7],[lean,balanced,protected],[LOW,BASE,HIGH]. |
| default_requirements | Requirements/null; khi resolver định nghĩa, đúng default mục3. |
| default_requirements_version,default_requirements_updated_at | Version/null,Timestamp/null; chưa biết không tạo ngày giả. |
| budget_ceiling | {amount:MoneyText,currency,version:Version,updated_at:Timestamp}/null. Trong C01 thành công, null là chưa có cap row tại snapshot; amount="0" là cap zero có version. Không số ví dụ thành cap thật. |
| products | Toàn menu active {product_id,name,selling_unit}; name rồiUUID tăng dần; nguồn FE chọn override. |
| custom_requirement_fields | FieldDescriptor[]/null;null chưa định nghĩa,[] xác nhận không field. |
| requirements_modes | Đủ3 {mode:default/custom/saved,availability:available/unavailable/unknown,reason_codes:string[]}. |
| saved_requirements | Saved[]/null; toàn bộ bộ active dùng chung Store trong scope quyền; [] đọc thành công/rỗng; null chưa hỗ trợ/chưa biết; không phân trang. Invalid active vẫn hiện, archived không hiện. |
| capabilities | Boolean winner_selection,saved_requirements,include_open_purchase_orders,scenario_based_planning. Hai capability cuối false v1. |
| readiness | Readiness dưới đây, không proof có winner/model tốt. |

CURRENT FACT: C01 kiểm đủ planning.context.read, budget.read và procurement.cost.read
trước projection và recheck authority trước trả response. Thiếu quyền trả403 toàn
response, không budget_ceiling=null. Null trong200 không chứng minh budget.update;
FE kiểm current effective permissions qua T02, N4 vẫn enforce budget.read+budget.update.
Initial create dùng If-None-Match:*; concurrent create/replace trả412
CONFIGURATION_VERSION_CHANGED. Không cần enum availability mới để suy absence;
không có response thành công thì không được suy Store chưa tạo budget.
Source: ReadinessReads.read, project_context và PlanningConfigurationWrites;
acceptance: test_planning_configuration_public.py (create/CAS/zero/replay), kết quả
chạy và điều kiện bàn giao xem [TD-BE-010](../008_TechDebt.md#td-be-010--store-profilegeneral-settings-writers-và-initial-budget-absence).

FieldDescriptor={field,type,required,nullable,constraints,inheritance}. field là
JSON path template;type decimal_text/path/product_override_array; constraints mô tả
range/scale/enum/unique/max_items. Descriptors cho requirements.paths[].path,
.min_fill_rate_percent,.product_overrides và requirements.budget_limit. Không custom
construction targets v1. Required descriptor là required trong request CUSTOM trước resolve.

Saved={saved_requirement_id,name,updated_at,requirements,validation,warnings};
validation={status:valid/invalid/unknown,reason_codes:string[]}. Updated_at giảm dần,
UUID tăng khi hòa; validity check không đổi updated_at. Invalid/unknown FE block,
BE recheck Run. Budget riêng>trần: invalid, không sửa. Inactive/cross-Store override
invalid. Active nhưng thiếu forecast/recipe: giữ saved; xử lý exclusion trong Run.

Saved lưu mức/overrides đã resolve lúc Save; budget null giữ late binding. Save có thể
lưu null budget khi trần chưa cấu hình, validation unknown; C02 vẫn cần trần đã biết.
C02 không nhận saved archived. Đọc/dùng không giới hạn creator; sửa/lưu trữ theo mục 14.9. Nếu
saved.updated_at<default.updated_at:warning DEFAULT_CHANGED_SINCE_SAVED_UPDATE, không
block chỉ do cảnh báo. Thiếu history:DEFAULT_CHANGE_HISTORY_UNKNOWN, không tạo ngày giả.
Mode available là setup dùng được, không guarantee pipeline ready. Default cần config/
version;custom cần descriptors/resolver;saved cần reader và≥1 bộ valid. Saved rỗng:
unavailable/NO_SAVED_REQUIREMENTS;reader chưa wired:SAVED_REQUIREMENTS_UNAVAILABLE;
không xác minh được validity:unknown/SAVED_VALIDATION_UNKNOWN.

### Readiness và ngày gợi ý — TECHNICAL CHOICE

Readiness={status:ready/not_ready/unknown,can_generate:boolean,reason_codes:string[],
evaluated_forecast_start_date:date/null,scope_estimate:ScopeEstimate/null,
history_watermark:date/null}. ready iff can_generate=true;unknown cũng false.
Suggestion start=ngày Store hôm nay,D=hôm qua. Không lấy latest sales làm cutoff rồi
tự nhảy ngày che thiếu data. Thiếu timezone/ngày không biểu diễn được:suggestion=null.
GET không chạy forecast/solver để xác minh readiness.

Cần public flow wired,authorized Store,known budget/default/resolver và sales availability
đến D được xác nhận;≥1 món đủ recipe/horizon và baseline-ready; required inventory/
fees/constraints của computed scope known, không global blocker. Watermark là completeness
declaration có provenance từ loader hiện hành, không max sales day. Unknown
không gán missing days0. Latest observation cũ có thể warning, không tự tăng ngưỡng
baseline ≥1 observation hoặc đòi sales mỗi ngày. ScopeEstimate={menu_product_count,
estimated_computable_product_count,excluded_products:Exclusion[]}; chỉ estimate tại GET.
C02 luôn revalidate ngày/mode thực gửi, không tin can_generate=true cũ.
Reasons gồm PLANNING_WORKFLOW_UNAVAILABLE,BUDGET_CEILING_UNKNOWN,NO_ACTIVE_PRODUCTS,
NO_COMPUTABLE_PRODUCTS,HISTORY_NOT_AVAILABLE_THROUGH_CUTOFF,DEFAULT_CONFIGURATION_UNAVAILABLE,
REQUIRED_SOURCE_UNSUPPORTED,RESOURCE_LIMIT_EXCEEDED,READINESS_NOT_DETERMINED.

### Ví dụ C01 minh họa (synthetic, cấu trúc chuẩn tra OpenAPI)

```json
{
  "data": {
    "store_id": "00000000-0000-4000-8000-000000000001", "currency": "VND", "timezone": "Asia/Ho_Chi_Minh",
    "observed_at": "2026-10-09T03:00:00Z", "context_version": "ctx-demo-1", "latest_business_date": "2026-10-08",
    "defaults": {"requirements_mode": "default", "horizon_days": 7, "cutoff_date": "2026-10-08", "forecast_start_date": "2026-10-09"},
    "supported_horizon_days": [7], "supported_strategies": ["lean", "balanced", "protected"], "supported_paths": ["LOW", "BASE", "HIGH"],
    "default_requirements": {"budget_limit": null, "paths": [{"path": "BASE", "min_fill_rate_percent": "95", "product_overrides": []}]},
    "default_requirements_version": "defaults-demo-1", "default_requirements_updated_at": "2026-10-08T02:00:00Z",
    "budget_ceiling": {"amount": "1000000", "currency": "VND", "version": "budget-demo-1", "updated_at": "2026-10-08T02:00:00Z"},
    "products": [{"product_id": "00000000-0000-4000-8000-000000000010", "name": "Trà", "selling_unit": "cup"}],
    "custom_requirement_fields": [
      {"field": "requirements.paths[].path", "type": "path", "required": true, "nullable": false, "constraints": {"enum": ["LOW", "BASE", "HIGH"], "unique": true, "max_items": 3}, "inheritance": "none"},
      {"field": "requirements.paths[].min_fill_rate_percent", "type": "decimal_text", "required": false, "nullable": false, "constraints": {"minimum": "0", "maximum": "100", "max_fraction_digits": 32}, "inheritance": "same_path_default"},
      {"field": "requirements.paths[].product_overrides", "type": "product_override_array", "required": false, "nullable": false, "constraints": {"max_items": 50, "unique_product_id": true}, "inheritance": "same_path_default_replace"},
      {"field": "requirements.budget_limit", "type": "decimal_text", "required": false, "nullable": true, "constraints": {"minimum": "0", "max_integer_digits": 18, "max_fraction_digits": 18}, "inheritance": "current_store_ceiling"}
    ],
    "requirements_modes": [{"mode": "default", "availability": "available", "reason_codes": []}, {"mode": "custom", "availability": "available", "reason_codes": []}, {"mode": "saved", "availability": "unavailable", "reason_codes": ["NO_SAVED_REQUIREMENTS"]}],
    "saved_requirements": [],
    "capabilities": {"winner_selection": true, "saved_requirements": true, "include_open_purchase_orders": false, "scenario_based_planning": false},
    "readiness": {"status": "ready", "can_generate": true, "reason_codes": [], "evaluated_forecast_start_date": "2026-10-09", "scope_estimate": {"menu_product_count": 1, "estimated_computable_product_count": 1, "excluded_products": []}, "history_watermark": "2026-10-08"}
  },
  "meta": {"warnings": []}, "error": null
}
```

CURRENT FACT: public workflow và saved reader đã wired; capability/readiness
phụ thuộc dữ liệu, quyền, configuration và worker thực sự đang đăng ký.

<a id="planning-run"></a>
## 5. C02 — request/resolve/receipt

Header Idempotency-Key REQUIRED ResourceId mới cho mỗi lần chủ động Run. Store route,
actor authenticated session, không payload. requirements_mode và forecast_start_date
REQUIRED; horizon/cutoff/model/scope/strategy/currency/old advanced fields forbidden.
Custom requirements REQUIRED,saved ID forbidden; default cả hai forbidden; saved ID
REQUIRED,requirements forbidden. Default version REQUIRED mode default hoặc custom
kế thừa mức/overrides;optional full custom/saved, không check stale nếu không dùng default.

Requirements={budget_limit:MoneyText/null optional,paths:PathRequirement[] required}.
PathRequirement={path required,min_fill_rate_percent optional,product_overrides optional}.
Override={product_id,min_fill_rate_percent} cả hai required. Sau resolve đầy đủ.

| Missing/explicit | Resolve đã chốt |
| --- | --- |
| Custom min omit | Default cùng path; không có thì422 DEFAULT_VALUE_UNAVAILABLE. |
| Custom overrides omit | Default cùng path; không có thì lỗi. |
| Overrides=[] | Chủ động không ngoại lệ; không missing. |
| Overrides đã gửi | Thay TOÀN danh sách trên path, không merge default. |
| Budget omit/null | Trần Store lúc nhận; không cần default version chỉ vìbudget. |
| Budget="0" | Zero thật. |
| Saved | Mức đã resolve lúc Save, không kế thừa default mới; validate Store/active/budget lại. |

Default chỉ BASE nên HIGH/LOW custom phải gửi min/overrides tường minh. Null rate/
overrides lỗi. Paths missing/[]/trùng lỗi. Version stale khi cần default:409
DEFAULT_REQUIREMENTS_CHANGED, không nhận Run. Cap thay đổi giữa GET/POST dùng trần hiện
hành tại nhận như đã chốt; riêng>cap trả422, null/default dùng cap mới. C03 cho xem cap
thực dùng; không giả biết FE đã thấycap nào nếu request không gửi evidence tương ứng.

### Ba request hợp lệ (demo)

```json
{"requirements_mode": "default", "forecast_start_date": "2026-10-09", "default_requirements_version": "defaults-demo-1"}
```

```json
{"requirements_mode": "custom", "forecast_start_date": "2026-10-09", "requirements": {"budget_limit": null, "paths": [{"path": "HIGH", "min_fill_rate_percent": "90", "product_overrides": []}]}}
```

```json
{"requirements_mode": "saved", "forecast_start_date": "2026-10-09", "saved_requirement_id": "00000000-0000-4000-8000-000000000020"}
```

C02 kiểm quyền,syntax/setup/budget/default/saved/current active references trước nhận.
Thiếu recipe/history riêng món xử lý sau nhận bằng exclusions; không toàn Run fail vì một
món. Known no active trước nhận422 NO_ACTIVE_PRODUCTS. Receipt chỉ sau durable acceptance
được xác minh. Không full result/winner/job_id/plan_id trong receipt.

Data={run_id:ResourceId,status:queued/running/completed/failed,accepted_at:Timestamp};
meta={warnings:Notification[],poll_after_ms:integer}; queued/running202 và poll 2000ms;
retry terminal200/poll0. Location C03 URL cùng run_id;Cache-Control:no-store,
Retry-After:2 nonterminal. Warnings receipt là facts biết lúc nhận, retry giữ nguyên;
warnings computation ở C03.202 không forecast complete/có winner/đặt hàng.

```json
{"data": {"run_id": "00000000-0000-4000-8000-000000000100", "status": "queued", "accepted_at": "2026-10-09T03:01:00Z"}, "meta": {"warnings": [], "poll_after_ms": 2000}, "error": null}
```

<a id="planning-idempotency"></a>
## 6. Idempotency/version/transaction — TECHNICAL CHOICE

Key scoped actor+Store+C02. So parsed request TRƯỚC resolve: object key order bỏ qua,
array order và field presence giữ nguyên. Omit khác null/[]; Money/Percent numeric
equivalence95/95.0 giống nhau. Canonical SHA-256 idempotency_request/1; Decimal coefficient/
exponent hoặc fraction tối giản, UUID canonical,date ISO. Không Python hash hoặc so view.

Resolve default đúng version, đọc saved cùng revision và cap lúc nhận; atomically lưu
Run+key+original digest+effective config+budget cap/version+default/saved source/version/
timestamps+policy/API version+actor/Store+receipt warnings. Unique scope key chống hai
acceptance concurrent. Retry cùng request trả Run cũ, không read config mới để thay.
Khác request409 IDEMPOTENCY_KEY_REUSED. Config updates optimistic version, không silent
last-write-wins; mutations cấu hình dùng preconditions mục 14.7. Version default đổi khi semantic
content đổi, updated_at không chính là version. Saved revision giữ content update.

Uncertain acceptance commit cần fresh-session verify đủ aggregate trước success; known
integrity/programming error không success. Cleanup không che primary error. Retry vẫn
kiểm quyền; key không phải credential. Theo policy đã chốt ở mục 12, giữ Run,
input, result và liên kết key không thời hạn, không tự xóa, không áp dụng TTL.
IDEMPOTENCY_KEY_EXPIRED chỉ dành cho dữ liệu legacy đã xác minh hoặc policy tương lai
được duyệt riêng; không tự hết hạn key của v1. Lượt này không xóa dữ liệu.

<a id="planning-capture"></a>
## 7. Forecast/capture/scope/provenance

TECHNICAL CHOICE: history window toàn observations thực có≤D trong Store/scope;
history_start earliest observation trong scope. Missing≠0; baseline ≥1 mỗiProduct.
Store serving model/config cóversion explicit; không glob artifact mới nhất. Dùng
ADR-015 actual selection/fallback: absent/notready/baseline-selected cówarning;
corrupt/incompatible/programming error không success qua fallback. Không train trongGET.

Reuse cần canonical PreparedForecastInput digest và ACTUAL model/artifact/features/
postprocessing/dependencies/config identity riêng; verify retained bytes/hash, Store,
units/timezone/exact Product scope/cutoff/history window, đủ 7 ngày ordered finite
nonnegative predictions. Không chỉ cutoff/tuổiRun. Exact scope matching, không subset
scope lớn thiếu audit. Thay requirements/budget/recipe/stock/price không làm forecast
identity đổi; operational facts vẫn capture/tính mới cho Run UUID mới. Không đủ conditions
thì tạo forecast phù hợp. Actual model metadata phải từ bản đã dùng, không model mới nhất.

Training bounds lấyartifact thực dùng train window, không inference cutoff. Baseline mô tả
empirical history window, không pretend trained ML. Overlap warning FORECAST_TRAINING_OVERLAP
với intersection dates; unknown bounds FORECAST_TRAINING_BOUNDS_UNKNOWN. Không cấm do
overlap/âm thầm đổi model. Cutofffiltering không historical point-in-time availability.

Operational reads cùng owned READ ONLY REPEATABLE READ snapshot, detached/frozen; closes
Sessions/connections trước solve. Không query sau compute dựng provenance. Forecast/FS
validation ngoài transaction, referencedforecast verify trong capture. Nếu history/scope
đổi giữa forecast prepare và capture: compare digest, retry prepare tối đa 2 lần; hết retry
failed INPUT_CHANGED_DURING_CAPTURE, không mix snapshots. Effective requirements/budget
đã fixed AT ACCEPTANCE; operational capture thời điểm khác được ghi riêng, không claim tất cả
cùng một physical instant. BusinessConstraint cap conflict với accepted cap:blocked,
không bypass validator hoặc âm thầm lấycap mới.

Scope={menu_products:ProductBrief[],computed_product_ids:ResourceId[],excluded_products:
Exclusion[],menu_count,computed_count,coverage_status:full/partial/none}.
ProductBrief={product_id,name,selling_unit}; Exclusion={product_id,code,field,
affected_dates:date[],ingredient_ids:ResourceId[],message,suggested_action,
requirement_overrides:array}. Unknown/cross-store/inactive override là setup error;
ACTIVE nhưng lỗi local forecast/recipe là exclusion, không silent sửa Saved.
Override của excluded giữ audit NOT_EVALUATED, không PASS. Graph shared Ingredient blockers
propagate đúng affected Products; scope ảnh hưởng unknown thìfailed, không guess.

| Nguyên nhân | Code chuẩn v1 / hành vi |
| --- | --- |
| Không history/forecast riêng Product sai | PRODUCT_HISTORY_MISSING/FORECAST_PRODUCT_INVALID: exclude nếu localize được. |
| Recipe thiếu/rỗng/overlap/unit | RECIPE_MISSING/RECIPE_EMPTY/RECIPE_OVERLAP/RECIPE_UNIT_MISMATCH: Product/date excluded. |
| Required inventory/expiry unknown | INVENTORY_UNKNOWN/REQUIRED_EXPIRY_MISSING: exclude affected Products nếu dependencygraph đủ. |
| Scope lỗiunknown | SOURCE_FAILURE_SCOPE_UNKNOWN: failed, không giả phầncòn lại tốt. |
| Source phụ thiếureceiveddate/cost | RECEIPT_DATE_UNKNOWN/INVENTORY_COST_UNKNOWN: warning; metric null, không 0. |
| Budget/fees/requiredconstraint unknown | BUDGET_CEILING_UNKNOWN/PAYABLE_FEE_UNKNOWN/CONSTRAINT_CONFIGURATION_UNKNOWN:blocked đúng scope, không unlimited/0. |
| Forecast toàn nguồn/DB/model/programming lỗi | FORECAST_EXECUTION_FAILED/DATA_SOURCE_UNAVAILABLE/EXECUTION_ERROR:failed, không no-pass. |

Boundary revalidation trêncomputed scope còn lại, giữ exclusions audit. Không forecast
thiếu coverage rồi dùng v2 output nhưcomplete. Excluded issues ởngoài computed-ready input
nhưng retained Run audit; không drop blocker cònliênquan. Không cònmón:completed outcome
no_computable_products, options=[],winner=null, không fake đã xét3 strategies.

<a id="planning-lifecycle"></a>
## 8. Mapping public lifecycle/execution/search/proof

TECHNICAL CHOICE: lifecycle tách riêng search, validity và proof. Status không thay
thế lý do winner null; FE cần hiển thị cả status, outcome và diagnostics.

| Facts thực tế | Public status / outcome | Recommendation |
| --- | --- | --- |
| Đã nhận/chờ claim | queued/null | result=null. |
| Forecast/capture/solve/validation chạy | running/null | Không publish intermediatewinner. |
| Hết pipeline, có eligible option, không technical error | completed/recommendation_available | Có thể INCOMPLETE/UNPROVEN. |
| Hết pipeline, không eligible option, có exact facts | completed/no_eligible_candidate | null; chưa chắc là certified no-pass. |
| Không có computed Product | completed/no_computable_products | null; không tuyên bố đã đánh giá ba strategies. |
| Known blocker/numeric unsupported sau acceptance | completed/computation_blocked | null; diagnostics, không gọi là infeasibility certificate. |
| Source ERROR nhưng còn verified eligible option | failed/execution_error | Giữ recommendation đã xác minh trong partial result; không chuyển error thành success. |
| System/crash/integrity error, không candidate verified | failed/execution_error | null; chỉ giữ partial facts đã xác minh độc lập. |
| Native deadline/iteration limit | Không tự failed; completed khi finalize nếu không lỗi khác | Incumbent eligible vẫn có thể recommend, proof UNPROVEN. |
| HTTP client timeout | Chưa biết outcome; retry CÙNG key hoặc đọc C03 | Không tự tạo Run mới hoặc suy rằng server failed. |

Engine dùng cooperative budget 30s, reserve 2s, tối đa 8 solves/strategy; overall
stage budget 180s là lựa chọn resource, không phải SLA hoặc hard cancellation.
Native/build/validation có thể overrun; phải lưu elapsed/overrun. Hết overall budget
trả failed/EXECUTION_DEADLINE_EXCEEDED, có thể giữ candidate đã xác minh. Không tuyên
bố native task đã bị cancel khi còn chạy. Comparison/selector validation nằm ngoài
engine deadline, được đo riêng; không giấu thời gian này.

Native OPTIMAL/infeasible/gap chỉgenerator evidence. Proof UNPROVEN hoặc
COMPLETE_EXACT_ENUMERATION trong CAPTURED_FINITE_DOMAIN_ONLY. No-pass UNKNOWN hoặc
NO_PASS_CERTIFIED chỉ trong finite bounds. Large-domain certification disabled; optional ≤256-vector
bounded exact check theo declared policy/version. Winner scope BEST_EVALUATED_CANDIDATES_ONLY.
Không tuyên bố global optimum, calibrated Ingredient quantiles, probabilities hoặc profit.

<a id="planning-result"></a>
## 9. C03 — cùng resource cho polling và đọc result

GET /procurement-plans/{plan_id}; plan_id=run_id, không body. Read đồng bộ, có
authorization, chỉ đọc persisted aggregate; không query live facts/recompute/LLM.
Trả 200 kể cả failed/nonterminal; resource/auth errors dùng HTTP riêng. Header
Cache-Control:no-store; ETag là opaque response_version (v1 trả full 200, không bắt
FE xử lý 304). poll_after_ms=2000 khi nonterminal, =0 khi terminal.
GET không restart job hoặc đặt hàng.

Data REQUIRED={run_id,store_id,status,outcome,accepted_at,started_at,finished_at,
response_version,request,configuration,operational_basis,forecast,scope,execution,result,errors}.
Started/finished là Timestamp nullable theo lifecycle; outcome null khi nonterminal,
còn terminal dùng enum mục 8.
Request là request đã nhận; configuration là cấu hình effective tại acceptance.
Operational_basis bắt buộc có key, null trước capture; sau capture có shape ở mục 12. Forecast/scope/execution có thể
null trước availability; errors luôn Notification[]. Result null khi nonterminal;terminal known business block có Result arrays rỗng;failed có Result chỉ nếu verified, nếu không null.

Configuration={requirements_mode,effective_requirements,budget:{limit:MoneyText,
currency,ceiling_at_acceptance:MoneyText,ceiling_version:Version},default_version:
Version/null,saved_reference:{id,version,updated_at}/null,policy_version:
"procurement_api_policy/1"}. Requirements giữ override excluded và scope NOT_EVALUATED.
Forecast={forecast_run_id,input_digest,model_type,model_version,artifact_identity:
string/null,start_date,end_date,history_start_date:date/null,history_end_date:date/null,training_start_date:
date/null,training_end_date:date/null,reused:boolean,quality_status:not_evaluated/evaluated,
warnings:Notification[]}. Quality theo actual evaluation provenance; synthetic tests không
thành accuracy. Training window không biết giữ null. History bounds không có trong nguồn retained
thì giữ null và cảnh báo, không suy diễn từ cutoff. Input_digest là digest đã được
xác minh trong runtime; fixture minh họa giữ fingerprint SYNTHETIC-S344 của nguồn
và không phải bằng chứng integrity của ForecastRun thật. Execution={engine_semantics_version,
comparison_version,selector_version,elapsed_ms,engine_elapsed_ms,engine_deadline_ms,
engine_overrun_ms,comparison_selector_elapsed_ms,search_complete:boolean}.
Milliseconds ceil từ actual seconds, không money arithmetic; nguồn seconds retain internally.

Result={completeness:full/partial,strategies:StrategyResult[],options:Option[],
winner_option_id:OptionId/null,winner_reason:WINNER_FOUND/NO_ELIGIBLE_CANDIDATE/
NOT_EVALUATED,warnings:Notification[]}. Khi đã chạy engine, đúng 3 strategy ordered
lean/balanced/protected;không compute thì[]/NOT_EVALUATED, không fabricated rows.
Winner phải reference eligible option; grouping không che source errors/proof.
Completeness mô tả độ đầy đủ của dữ liệu kết quả (source/scope/facts), không chứng
minh search complete: kết quả đủ facts vẫn có thể có search_complete=false và UNPROVEN.

StrategyResult={strategy,construction_path,option_id:OptionId/null,execution:
FINISHED/INCOMPLETE/ERROR/BLOCKED/NUMERIC_UNSUPPORTED,termination,customer_pass:boolean,
construction_pass:boolean,selection_kind:TARGET/CUSTOMER_PASS_FALLBACK/REFERENCE_NOT_RANKED/
NONE,customer_feasibility:PASS_EXISTS/NO_PASS_CERTIFIED/UNKNOWN,construction_feasibility:
same enum,proof:UNPROVEN/COMPLETE_EXACT_ENUMERATION,proof_scope:CAPTURED_FINITE_DOMAIN_ONLY,
domain_size:UnboundedCountText,search_complete:boolean,customer_gaps:Gap[],construction_gaps:Gap[],
diagnostic:Notification/null}. Construction feasibility là JOINT customer+construction.
Condensed diagnostics public; retained aggregate giữ full solver/journal, không massive poll payload.
Ví dụ wire: `"domain_size": "65536"`; domain lớn có thể là
`"domain_size": "9007199254740993"`, không phải JSON number. Nếu public hóa
enumerated_vectors/unique_exact_evaluations hoặc tổng search vectors ở cụm sau,
cũng dùng UnboundedCountText khi không có safe-integer bound. Không thêm fields đó
vào response hiện hành chỉ để đồng nhất hình thức. Đây là sửa design kỹ thuật
S3.6.2 được ủy quyền, không thay business policy hoặc tuyên bố endpoint đã chạy.
Gap={product_id,path,target_percent:PercentText,shortfall:ExactQuantity,unit}.

Option={option_id,source_strategies:strategy[],eligible:boolean,rejection_reasons:string[],
not_selected_reason:null/HIGHER_COST/LOWER_SERVICE_TIE/STABLE_ORDER_TIE/
CUSTOMER_REQUIREMENTS_NOT_MET/RELATED_BLOCKER,costs:Costs,purchases:Purchase[],
product_services:ProductService[],ingredient_balances:IngredientBalance[],
requirements_assessment:Assessment[],issues:Notification[]}.
Reason từ actual comparison key, không từ nhãn strategy;winner reason not_selected=null.
Costs={currency,purchase:ExactQuantity,payable_fees:ExactQuantity,delivery_fees:
ExactQuantity/null,fee_classification:DECLARED_DELIVERY/PAYABLE_FEE_TYPE_NOT_CAPTURED/NONE,
total:ExactQuantity}. NONE chỉconfirmed no fees;generic giữ payable,delivery=null,
notification DELIVERY_FEE_TAXONOMY_UNAVAILABLE. Generic fees chỉ dùng được khi nguồn xác nhận tổng payable đã bao phủ đầy đủ
mọi phí phải trả; vẫn cảnh báo thiếu taxonomy, không gọi generic fee là delivery.
Nếu coverage phí chưa biết thì không được đánh giá eligible. Public ready cần chứng minh full cost coverage,
không relabel v2 fees thành delivery hoặc unknown thành 0.
Purchase={supplier_term_id,supplier_id,ingredient_id,unit,packs:integer,quantity:
ExactQuantity,arrival_date,expiry_date:date/null,purchase_outlay:ExactQuantity,
payable_fee_components:array {basis,entity_id,amount:ExactQuantity}}. Supplier order fee
ởCosts aggregate, không nhân đôi từng line. Costs thêm fee_components cùng shape giữ basis.
ProductService={product_id,unit,path,requested:ExactQuantity,fulfilled:ExactQuantity,
lost_sales:ExactQuantity,service:Service/null}; đủ computed Products ×3paths,tổng 7 ngày.
IngredientBalance={ingredient_id,unit,path,consumed:ExactQuantity,expired:ExactQuantity,
ending_usable:ExactQuantity}. Không g+ml total. Assessment={product_id,path,target_percent,
applied_source:common/product_override,status:PASS/FAIL/NOT_EVALUATED,shortfall:
ExactQuantity/null};excluded shortfall null, không PASS.

### Ví dụ C03 running

```json
{
  "data": {
    "run_id": "00000000-0000-4000-8000-000000000100", "store_id": "00000000-0000-4000-8000-000000000001", "status": "running", "outcome": null,
    "accepted_at": "2026-10-09T03:01:00Z", "started_at": "2026-10-09T03:01:01Z", "finished_at": null, "response_version": "run-demo-2",
    "request": {"requirements_mode": "default", "forecast_start_date": "2026-10-09", "default_requirements_version": "defaults-demo-1"},
    "configuration": {"requirements_mode": "default", "effective_requirements": {"budget_limit": null, "paths": [{"path": "BASE", "min_fill_rate_percent": "95", "product_overrides": []}]}, "budget": {"limit": "1000000", "currency": "VND", "ceiling_at_acceptance": "1000000", "ceiling_version": "budget-demo-1"}, "default_version": "defaults-demo-1", "saved_reference": null, "policy_version": "procurement_api_policy/1"},
    "operational_basis": null, "forecast": null, "scope": null, "execution": null, "result": null, "errors": []
  },
  "meta": {"warnings": [], "poll_after_ms": 2000}, "error": null
}
```

Ví dụ terminal đầy đủ với recommendation eligible theo evidence nguồn được build từ S361 fixture
trong ZIP ở review_context/C03_completed_synthetic.json; không HTTP response thực.
Ví dụ queued tương receipt;terminal no_computable_products có scope excluded,forecast
null nếu chưa forecast,execution null,Result partial/strategies[]/options[]/winner null/
NOT_EVALUATED. Không dùng 0 để thay nullable metrics.

<a id="planning-errors"></a>
## 10. Errors/quyền

| Trước nhận / GET | HTTP / code |
| --- | --- |
| JSON hỏng/header key thiếu/sai |400 INVALID_REQUEST. |
| Chưa đăng nhập |401 UNAUTHENTICATED. |
| Không quyền Store được phép biết |403 PERMISSION_DENIED. |
| Resource not found/Store ngoài scope |404 RESOURCE_NOT_FOUND, không lộfacts. |
| Fields/setup/budget/date/limits sai |422 INVALID_PLANNING_CONFIGURATION,field_errors code cụ thể. |
| Default stale |409 DEFAULT_REQUIREMENTS_CHANGED. |
| Key khác request / expired verified |409 IDEMPOTENCY_KEY_REUSED / IDEMPOTENCY_KEY_EXPIRED. |
| Tạm không đọc/nhận bền vững |503 SERVICE_UNAVAILABLE, không false 202. |

error.details.field_errors=[{field,code,message}];permissions error có
approval_request_allowed:boolean theo BE policy, không default true. Allowlist approval
chưa duyệt không one-time bypass C02. Failed Run GET vẫn200 với errors data, không 500 giả GET fail.
Retained result integrity/schema không verify được:503 RESULT_INTEGRITY_UNAVAILABLE,
không success fake data. Owner/Staff/Store/deny-by-default giữauth contract;retry/GET histories
recheck quyền. Membershiprevoked chặnnew request/retry/read;mid-jobpolicy thuộc auth review,
không suyaccepted Run giữ quyền đọc mãi. Không leak cost/budget/derived facts qua warnings/LLM.
Theo P2 đã chốt ở mục 12, thiếu quyền xem budget/giá mua thì chặn toàn response;
không trả bản redacted và không tự cấp quyền cho Staff.

```json
{"data": null, "meta": {}, "error": {"code": "INVALID_PLANNING_CONFIGURATION", "message": "Ngân sách riêng vượt trần chung.", "details": {"field_errors": [{"field": "requirements.budget_limit", "code": "BUDGET_LIMIT_EXCEEDS_CEILING", "message": "Giảm ngân sách riêng hoặc chỉnh trần chung bằng quyền phù hợp."}]}}}
```

<a id="planning-backlog"></a>
## 11. CURRENT FACT — durable public orchestration

C01/C02/C03, N1-N4/R01 and retained/history/PDF routes are implemented by the
composed app. PlanningRun is a separate durable resource: atomic acceptance/
receipt/configuration, retained capture before compute, short owned Sessions,
fenced claims and verified publication/read. One default-OFF local worker; no
broker. OS-proven dead process becomes failed without recomputation. Original
S1 DecisionRun recommendation-required schema is not reinterpreted as no-winner.
Package/schema/capture/model versions are distinct. Fresh-session persistence is
an acceptance requirement; source registration alone is not verified operation.
Remaining UI/quality/latency/unsupported-condition scope is in ROADMAP.

<a id="planning-approved-policy"></a>
## 12. Các policy bổ sung — ĐÃ CHỐT ngày 09/10/2026

Nguồn authorization: người dùng trả lời trực tiếp cả ba câu hỏi trong lượt review
cụm này. Không hỏi lại. Không còn policy planning cần chốt thêm ở cụm này; thiếu
runtime nằm ở backlog, không phải OPEN.

**P1 — Ngày bắt đầu khác hôm nay.** Cho phép lập kế hoạch khi đủ history, dùng
tồn kho/giá/công thức capture hiện tại làm giả định rõ ràng. Không giả tồn kho
thực tại ngày quá khứ hoặc dự báo tồn kho tương lai. Luôn warning
NONCURRENT_PLANNING_CURRENT_FACTS khi start khác ngày Store tại capture. C03 trả
operational_basis={kind:HYPOTHETICAL_CURRENT_CAPTURE,captured_at,local_capture_date,
planning_start_date,assumptions:string[]}. Start hôm nay dùng kind=CURRENT_CAPTURE,
vẫn giữ thời điểm quan sát, không hứa chụp đúng đầu ngày/accounting close.

TECHNICAL CHOICE: giữ received/expiry/effective dates gốc, xét eligibility từng ngày;
lô nhận sau ngày mô phỏng hoặc expired không dùng. Future start giả định balance
capture làm starting balance, không tự forecast tiêu hao/nhận hàng giữa capture và
start. Không đổi current balance thành historical balance. Purchases có ngày quá khứ
là hypothetical, không ghi PO/movements thật. Cảnh báo nêu nguy cơ không phản ánh
thực tế; không historical backtest/point-in-time claim. operational_basis REQUIRED
khi đã capture, null trước capture. Ngày vẫn cần history đến cutoff, không coi sales
tương lai là zero. Adapter temporal/version2 là backlog; không sửa day-start guard
của source hiện tại trong lượt docs.

**P2 — Quyền xem tiền.** C01/C02/C03 cần quyền planning tương ứng và quyền xem
budget/giá mua; thiếu chặn cả response403, không redaction một phần. Store ngoài scope
dùng404 để không lộ tài nguyên. Không tự cấp view money cho Staff chỉ vì có planning.
TECHNICAL CHOICE action mapping: planning.context.read/planning.run/planning.result.read
kèm budget.read/procurement.cost.read; tên map vào auth catalogue, không tạo grant.
Mọi GET/retry kiểm quyền hiện hành. Supersede OPEN redaction của auth document CHỈ
cho planning; endpoints khác review riêng. One-time approval allowlist và job đang
chạy thuộc dependency auth, không tự bypass hoặc giữ quyền đọc mãi vì Run đã nhận.

**P3 — Retention không thời hạn.** Giữ Run/input/result/liên kết idempotency không
thời hạn v1; không tự expire/purge/xóa. Dung lượng tăng; chưa có backup/DR guarantee.
Same key/request nhiều ngày sau vẫn Run cũ. Không có90-day cleanup; Saved không tự
TTL xóa trong cụm. IDEMPOTENCY_KEY_EXPIRED là code dự phòng khi có expired-key history
được xác minh hoặc purge policy mới được duyệt; v1 không tự làm key hết hạn.

<a id="planning-acceptance"></a>
## 13. Acceptance specifications

Acceptance criteria; kết quả kiểm thử hiện hành báo trong hội thoại:

1. C01 chỉ đọc; trả đúng default/descriptors, capability thật, phân biệt saved=null
   và [], trả toàn bộ requirements và đúng thứ tự updated_at/UUID. C02 kiểm tra lại
   readiness; không tạo completeness watermark từ ngày sales mới nhất.
2. Custom BASE omit kế thừa đúng version; HIGH/LOW chưa có default thì báo lỗi;
   [] thay danh sách; null rate bị reject; budget null late-bind, zero là zero thật.
   Full custom không bị chặn bởi stale default không dùng. Override phải đúng scope/active.
3. Concurrent config updates không trộn version; cùng key chỉ một acceptance.
   Retry giữ Run/config/receipt warnings, kiểm quyền lại và reject cross-store.
4. Sales/model identity đổi thì không reuse forecast; chỉ requirements/budget đổi
   có thể reuse. Missing khác zero; baseline ≥1 observation không chứng minh quality.
   Corrupt artifact phải báo lỗi, không fallback thành success.
5. Năm món active, một món thiếu recipe: computed scope bốn món, có exclusion và
   override NOT_EVALUATED. Shared blockers đúng dependency graph; graph chưa biết
   thì failed. Không computed Product khác no eligible/certified no-pass. Không sửa saved.
6. Exact customer-pass nhưng construction-miss vẫn eligible. Winner so cost rồi
   min HIGH/BASE/LOW; requested zero có Service=null. Không epsilon cho tiny shortfall;
   grouping giữ source errors và proof riêng.
7. Native deadline có/không incumbent không bị gọi nhầm infeasible. Source ERROR
   với eligible option vẫn failed, giữ partial recommendation đã xác minh. HTTP timeout
   retry cùng key; ghi cooperative overrun, không hứa hard cancellation.
8. Fresh-session kiểm receipt/input/result và atomic aggregate; không publish invalid
   partial facts. Programming error, uncertain commit, rollback và restart không báo
   sai completed. C03 chỉ đọc retained facts.
9. Budget fixed tại acceptance; cap mới không sửa Run cũ. Operational cap conflict
   thì blocked. Generic fee khác delivery, unknown fee không zero; không cộng khác
   unit, không probabilities hoặc LLM business truth.
10. P1: ngày khác capture có basis/cảnh báo, giữ dates gốc và không tạo stock evolution
    giả. P2: thiếu quyền xem tiền chặn cả cụm/retry, warnings không leak. P3: không
    TTL/purge, retry muộn vẫn Run cũ.

HISTORICAL INFORMATION — verification review C01–C03 trước hợp nhất cấu hình:
chỉ kiểm docs/examples, references, policy consistency, UTF-8,
WIP và ZIP. Commands/results trong `review_context/VERIFICATION.json` của ZIP.
Không pytest/full suite/HTTP/OpenAPI runtime/DB/migration/auth. Rollback: restore
combined contract từ historical bytes và bỏ đúng additions của lượt này trong ba
docs trạng thái; không reset, sửa accepted ADR/source/FE hoặc xóa ZIP cũ.

<a id="planning-configuration"></a>
## 14. Cấu hình planning

Review và hợp nhất: 09/10/2026. Cấu hình planning/1.
**DESIGN ONLY:** policy sản phẩm mục 14.9 đã chốt; chi tiết kỹ thuật là
PROPOSAL / TECHNICAL CHOICE theo ủy quyền, không phải runtime/ADR mới ACCEPT.
Dùng conventions mục 2, custom resolve mục 5 và
[contract phân quyền](AUTHORIZATION_CONTRACT_VI.md).

<a id="planning-configuration-1"></a>
### 14.1. Bản đồ các cụm còn lại và thứ tự review

| Thứ tự | Cụm trọn vẹn | Endpoint gốc / hướng review |
| --- | --- | --- |
| 1 — mục 14 đã review | Cấu hình planning | C01 đọc saved/budget đã chốt; bổ sung mutations thật sự thiếu. T02 giữ metadata Store. |
| 2 | Chi tiết nguyên liệu và đồ thị kết quả | C04–C06: navigator → detail → series, đọc cùng retained Run/option, xác định lazy reads và nullable metrics. C07 đã gộp C03, không mở lại. |
| 3 | What-if | S01–S02: thay giả định → tính → so baseline; giữ hypothetical, không tự ghi business state. |
| 4 | Giải thích và xuất phương án | C08 + X01–X02: đọc bài đã có/yêu cầu giải thích; PDF là nhu cầu đã được cho phép, FE gốc chưa có route. C09 review riêng ý định draft PO, không tự đưa vào luồng đã chốt. C10 đang dùng C02/key mới, không thêm regenerate trùng. |
| 5 | Nhập dữ liệu đến hoàn tất và lịch sử | I01–I06, M01–M04, H01–H02: upload → mapping/review → commit → completion/history; quyền commit theo loại dữ liệu. |
| 6 | Kho | V01–V04: summary → nguyên liệu/lô → movements; không thêm stock mutation chỉ vì nội bộ có receive/adjust. |
| 7 | Menu và công thức | P01–P02: danh sách → recipe hiện hành; review đúng reads gốc, mutations chỉ nếu có nhu cầu được giao. |
| 8 | Hôm nay và readiness xuyên luồng | D01 + R01: chỉ tổng hợp facts/capabilities từ các cụm đã review, không invent cảnh báo/số liệu. |
| 9 | Đăng nhập, Store và quản lý quyền | A01–A04, T01–T02; bổ sung permissions/approval/audit nếu trách nhiệm thật sự thiếu. Nguyên tắc Owner/Staff đã chốt giữ nguyên. |

J01 là contract kỹ thuật dùng chung để đối chiếu ở các cụm có job, không ép planning
quay lại job_id riêng. Cập nhật file contract của cụm hiện có; chỉ tạo file mới khi cụm độc lập,
không tách theo endpoint hoặc lượt làm. Bảng này là đề xuất thứ tự, không ủy quyền triển khai hoặc tự chuyển sang cụm kế tiếp.
Thứ tự review sản phẩm không phải thứ tự implementation: public APIs cần auth tối
thiểu trước khi expose dữ liệu dù cụm đăng nhập chi tiết review sau.

<a id="planning-configuration-2"></a>
### 14.2. Luồng khách dùng

Khách mở Dự đoán, C01 tải default, requirements đã lưu và trần ngân sách hiện hành.
Khách chọn một bộ hoặc nhập custom; có thể chạy ngay bằng C02 mà không Save.
Nếu muốn dùng lại, khách đặt tên rồi Save. Save chỉ lưu yêu cầu phục vụ và ngân sách
riêng nếu có; không chạy forecast/solver, không tạo Run, không đổi default BASE95.
Save thành công trả bộ đã resolve để khách thấy chính xác nội dung được lưu.

Để thay một bộ, khách mở bản hiện tại, sửa rồi lưu thay thế với version đã đọc;
hoặc Save thành bộ mới. Lưu trữ chỉ ẩn bộ khỏi danh sách dùng cho Run mới, không
xóa Run/input/result cũ. Bộ dùng chung Store; Staff chỉ sửa/lưu trữ bộ mình tạo,
Owner quản lý mọi bộ trong Store, theo quyết định mục 14.9.

Owner hoặc Staff có quyền sửa budget mở trần hiện tại, nhập số mới và lưu.
FE báo rõ: trần dùng cho mỗi kế hoạch 7 ngày được nhận sau thay đổi; đây không phải
ví tiền có spent/reserved/rollover. Giảm trần có thể làm một số bộ ngân sách riêng
không còn hợp lệ; FE hiển thị chúng là invalid, không âm thầm sửa số của bộ đó.
Run đã được C02 nhận giữ nguyên budget/cap/version đã capture.

Không thiết kế màn hình mới trong lượt này. Luồng trên mô tả trách nhiệm API và
FE adapter cần có khi tích hợp, không tuyên bố prototype đã có nút/quyền tương ứng.

<a id="planning-configuration-3"></a>
### 14.3. Đối chiếu endpoint gốc

| Endpoint | Giữ/sửa/gộp/bổ sung | Giải thích |
| --- | --- | --- |
| C01 `GET /stores/{store_id}/planning-context` | GIỮ contract hiện hành | Đã trả toàn bộ saved đang sử dụng và budget; không thêm GET list active trùng, không biến GET thành Save. |
| C02/C03 | GIỮ | Chạy từ cấu hình effective tại acceptance; quản lý setup không sửa Run đã nhận. |
| C08 `GET /procurement-plans/{plan_id}/explanation` | GIỮ ngoài cụm | Saved detailed analysis là bài giải thích, không phải saved requirements. |
| T02 `GET /stores/{store_id}` | GIỮ metadata | Không nhét planning settings/money vào read Store tối thiểu. |
| Không có trong FE gốc | BỔ SUNG `POST /stores/{store_id}/planning-requirements` | Save bộ mới; không endpoint gốc nào có write responsibility này. |
| Không có trong FE gốc | BỔ SUNG `GET /stores/{store_id}/planning-requirements/{saved_requirement_id}` | Đọc version để sửa/lưu trữ; vẫn đọc được bản archived, C01 không đáp ứng trường hợp đó. |
| Không có trong FE gốc | BỔ SUNG `PUT /stores/{store_id}/planning-requirements/{saved_requirement_id}` | Thay nội dung hoặc lưu trữ cùng một resource/version, không thêm endpoint rename/archive riêng. |
| Không có trong FE gốc | BỔ SUNG `PUT /stores/{store_id}/planning-budget` | Tạo trần ban đầu hoặc thay trần hiện hành, không mở Store CRUD tổng quát. |

Tất cả route tương đối với `/api/v1`; không gán ID C11/T03 giả là ID từ FE gốc.
Không DELETE/hard purge, không mutation chọn candidate, không PO/approval tự động.
Không thêm GET budget riêng: C01 đã trả amount/currency/version/updated_at; endpoint
write budget trả lại cùng shape. Không bổ sung archive listing/restore trong v1.

<a id="planning-configuration-4"></a>
### 14.4. Types và dữ liệu trả về

**PROPOSAL — technical choice.** Types, envelope và giới hạn request dùng mục 2;
custom requirements dùng mục 5. Tên saved áp quy tắc mục 2 và trim hai đầu trước
validation. Không định nghĩa MoneyText/PercentText hoặc inheritance khác cho Save.

`SavedDetail` có tất cả keys sau:

```text
saved_requirement_id: ResourceId
store_id: ResourceId
name: string
version: Version
state: active | archived
created_at: Timestamp
updated_at: Timestamp
created_by_user_id: ResourceId
updated_by_user_id: ResourceId
requirements: StoredRequirements
default_reference: {version: Version, updated_at: Timestamp|null} | null
validation: {status: valid|invalid|unknown, reason_codes: string[]}
warnings: Notification[]
```

StoredRequirements giữ budget_limit REQUIRED nullable và paths đã resolve đầy đủ
min_fill_rate_percent/product_overrides. Chỉ các paths khách gửi được giữ; không
tự thêm LOW/HIGH. Path order LOW/BASE/HIGH; overrides UUID tăng dần. Default reference
chỉ ghi khi thực sự kế thừa; không gán provenance default cho full custom.
created/updated actor là audit facts, không thông tin quyền tự cấp.

GET detail trả `200 {data: SavedDetail, meta:{request_id,warnings:[]}, error:null}`
và `ETag: "<version>"`; version opaque, không timestamp/hash có thể tự suy ra.
validation là đánh giá hiện hành, không stored flag bảo đảm dùng được mãi.
Không sửa updated_at chỉ do revalidation/default/budget/Product thay đổi.

C01 vẫn trả shape Saved hiện hành, projection từ các bộ active trong scope đã
quyết ở mục 14.9; không thêm version/actor/state vào schema C01 trong lượt này.
Muốn sửa dùng GET detail. Invalid active vẫn xuất hiện; archived không xuất hiện.
`[]` chỉ khi đã đọc thành công và rỗng; reader không khả dụng theo contract C01.

<a id="planning-configuration-5"></a>
### 14.5. Save và quản lý requirements

#### Save bộ mới

POST body REQUIRED `name`, `requirements`; optional
`default_requirements_version`. Không gửi mode/start date/currency/strategy/model,
saved ID hoặc actor. Requirements dùng đúng custom shape và resolve rules C02.

```json
{
  "name": "Phục vụ ngày thường",
  "requirements": {
    "budget_limit": null,
    "paths": [{"path": "BASE", "min_fill_rate_percent": "95", "product_overrides": []}]
  }
}
```

Header `Idempotency-Key` REQUIRED, dạng ResourceId. Thành công `201`, data là
SavedDetail, `Location` trỏ GET detail, ETag là version mới. `state=active`, actor
từ session. Full custom không cần default version; nếu omit mức/overrides để kế
thừa thì version REQUIRED và stale trả `409 DEFAULT_REQUIREMENTS_CHANGED`.
Resolve và ghi một transaction nhất quán, không lưu missing thresholds rồi late-bind.

Save độc lập với readiness chạy: thiếu sales/recipe/forecast/fees không chặn Save.
Override phải là Product active của đúng Store; inactive/cross-Store không lưu mới.
Ngân sách riêng nonnull phải ≤ trần hiện hành và cần trần đã biết để kiểm;
`budget_limit=null` hoặc omit được lưu thành null dù trần chưa cấu hình. Khi đó
SavedDetail validation là unknown/BUDGET_CEILING_UNKNOWN và C02 vẫn không chạy
được. Đây là lưu cấu hình, không tuyên bố budget unlimited hoặc readiness=true.

#### Thay nội dung hoặc lưu trữ

PUT REQUIRE `If-Match: "<version>"` và `Idempotency-Key`. Body:

```json
{
  "state": "active",
  "name": "Phục vụ ngày thường — điều chỉnh",
  "requirements": {
    "budget_limit": "800000",
    "paths": [{"path": "BASE", "min_fill_rate_percent": "95", "product_overrides": []}]
  }
}
```

Active body là full replacement, không merge lists; default version chỉ nếu kế
thừa, cùng rules Save. `200` trả SavedDetail và ETag mới. Mỗi thay đổi thực tạo
version mới; no-op trả version/updated_at cũ. Không mutate revision đã được Run
capture. C02 saved request giữ nguyên: dùng bộ current tại acceptance, không thêm
saved version bắt buộc vào C02 đã chốt.

Lưu trữ cùng PUT bằng body duy nhất `{"state":"archived"}`; name/requirements/
default version forbidden để không ghép archive và sửa nội dung. Không đòi bộ
đang hợp lệ mới archive: ngân sách vượt trần hoặc Product inactive vẫn archive được.
GET detail còn đọc được, validation invalid/SAVED_REQUIREMENTS_ARCHIVED; Run mới
bị từ chối `422 INVALID_PLANNING_CONFIGURATION` với field error
SAVED_REQUIREMENTS_ARCHIVED. Run cũ vẫn đọc retained config. Không restore in-place
v1: nếu muốn dùng lại, đọc detail và POST bản mới qua validation hiện hành.
Archiving bản đã archived với version hiện hành là no-op thành công.

Khi budget giảm/Product ngừng bán/default đổi, không cascade sửa/archiving saved.
Budget vượt trần, inactive override là invalid; active thiếu recipe giữ saved và
xử lý exclusions trong Run theo C01–C03. Warning default đổi giữ đúng semantics
hiện hành, không tự refresh thresholds. Không giới hạn số saved mới trong contract
này; C01 phải đọc đủ, không truncation. Growth/performance là backlog, không lý do
tự thêm cap rồi biến thành business policy.

<a id="planning-configuration-6"></a>
### 14.6. Cấu hình budget Store

Budget Run giữ policy mục 3/5: cap tại acceptance, riêng ≤ cap, zero thật,
unknown không unlimited, Run cũ không đổi. Cấu hình Store không phải monthly
balance, không trừ tiền sau Run hoặc reservation.

**PROPOSAL — technical choice:** PUT body REQUIRED `amount: MoneyText`; không
currency/date/actor. Currency lấy Store; nonnull, ≥0. Zero cho phép; không DELETE
trần hoặc gửi null để bỏ giới hạn. Budget không đổi default BASE95.

```json
{"amount": "1000000"}
```

Header Idempotency-Key REQUIRED. Khi C01 budget_ceiling=null do đã xác minh chưa
có cấu hình: `If-None-Match: *`, create-only, `201`. Nếu C01 null vì không đọc được,
không suy ra resource chưa tồn tại; lỗi loader cần xử lý trước. Khi đã có cap:
`If-Match: "<ceiling_version>"`, `200`. Cấm gửi cả hai headers; thiếu precondition
trả 428. Không dùng unknown version để overwrite.

Success data=`{store_id,budget_ceiling:{amount,currency,version,updated_at}}`, envelope
và ETag; create Location trỏ C01 là nơi đọc ngân sách. Ghi amount mới + version +
audit atomically. No-op amount tương đương exact giữ version/timestamp cũ.
Không trả contents/count của saved người khác trong write response.

FE refresh C01 sau mutation; riêng cap bị giảm làm saved invalid là trạng thái được
chấp nhận, không chặn sửa cap hoặc clamp saved. C02 và mutation budget serialize
điểm acceptance để mỗi Run capture trọn một amount/version; Run nhận trước dùng
cap trước, nhận sau dùng cap sau. Không giữ lock suốt compute.

CURRENT FACT: BusinessConstraint có dated BUDGET storage; đó không tự là writer
cho Store ceiling. Backlog phải chỉ định mapping/storage evolution sao cho cap
Store và hard operational budget facts không mâu thuẫn; không tạo hai nguồn budget
rồi chọn số thuận tiện. Contract này không tự ACCEPT bảng/ADR/schema hoặc đổi
temporal constraints. Conflict nguồn vẫn là blocker theo planning contract.

<a id="planning-configuration-7"></a>
### 14.7. Quyền, concurrency, retry và errors

Áp nguyên tắc Owner/Staff, deny-by-default, scope/membership hiện hành của
contract phân quyền; saved sharing không tự cấp quyền. Không approval một lần
tự động cho writes. Action mapping dưới đây chỉ cho endpoints cấu hình,
không thay điều kiện quyền C01–C03.

**PROPOSAL — action mapping**, chờ catalogue auth, không runtime grants:

| Responsibility | Quyền đề xuất |
| --- | --- |
| GET detail | planning.requirements.read + budget.read |
| POST Save mới | planning.requirements.create + planning.requirements.read + budget.read |
| PUT sửa/archive | planning.requirements.manage + planning.requirements.read + budget.read; Staff chỉ bộ do mình tạo, Owner mọi bộ trong Store |
| PUT budget | budget.update + budget.read |

Endpoint riêng cấu hình không trả procurement costs, nên không cần quyền
procurement.cost.read chỉ để sửa setup. C01–C03 giữ nguyên P2: planning permission
tương ứng + budget.read + procurement.cost.read, thiếu chặn toàn response.
GET detail không redaction nửa bộ khi thiếu budget.read. Membership bị thu hồi
chặn đọc/write/retry; resource ngoài Store/scope trả 404 không leak contents/actor.
Staff có quyền đọc được xem/dùng bộ active người khác tạo; quyền create/manage
không tự phát sinh từ quyền đọc. Staff sửa/archive bộ người khác trả 403
PERMISSION_DENIED dù có manage; created_by_user_id lấy server, bất biến qua sửa.
Không chuyển quyền tác giả bằng payload, không thêm chuyển chủ sở hữu trong v1.

If-Match là CAS atomic, không check rồi write tách transactions. Retry sau commit
không rõ kết quả dùng đúng key/body/precondition gốc. Idempotency scope
Store + actor + method + route; digest gồm body và precondition. Cùng key/request
trả receipt/resource/version của lần thành công, kể cả current version đã đổi;
không execute lần nữa hoặc xét stale precondition lại trước verified replay.
Vẫn kiểm quyền hiện hành trước replay; receipt cũ không thay current GET detail.
Khác payload/precondition cùng key trả 409. Failed-before-commit không consume key;
uncertain commit phải reconcile, không tạo bản thứ hai. Đề xuất giữ receipts/revisions/
audit không auto TTL trong v1, không mở rộng lời hứa backup/DR.

| HTTP/code | Khi dùng |
| --- | --- |
| 400 INVALID_REQUEST | JSON hỏng; idempotency/precondition syntax không hợp lệ; cả hai conditional headers. |
| 401 UNAUTHENTICATED | Không session hợp lệ. |
| 403 PERMISSION_DENIED | Store được phép biết nhưng thiếu quyền; approval_request_allowed=false cho cụm này cho đến khi có allowlist được duyệt. |
| 404 RESOURCE_NOT_FOUND | Store/resource không tồn tại hoặc ngoài scope. Không leak Product của Store khác qua field errors. |
| 409 DEFAULT_REQUIREMENTS_CHANGED | Chỉ khi Save/update thực sự kế thừa default stale. |
| 409 IDEMPOTENCY_KEY_REUSED | Key đã nhận request khác. |
| 409 SAVED_REQUIREMENTS_ARCHIVED | Sửa active content trên bản archived; tạo bản mới nếu cần. |
| 412 CONFIGURATION_VERSION_CHANGED | If-Match stale hoặc create-only budget đã tồn tại; FE đọc lại, không overwrite tự động. |
| 413 REQUEST_TOO_LARGE | Body vượt 64 KiB; không parse hoặc persist một phần. |
| 428 PRECONDITION_REQUIRED | PUT thiếu conditional header cần thiết. |
| 422 INVALID_PLANNING_CONFIGURATION | Fields/paths/rates/limits/override/budget/name/state sai; details.field_errors cùng shape planning contract. |
| 503 SERVICE_UNAVAILABLE | Chưa thể đọc/ghi/reconcile bền vững; không báo Save thành công giả. |

Field error codes: INVALID_NAME, UNKNOWN_FIELD, DUPLICATE_PATH,
DUPLICATE_PRODUCT_OVERRIDE, PRODUCT_NOT_AVAILABLE, DEFAULT_VALUE_UNAVAILABLE,
DEFAULT_VERSION_REQUIRED, INVALID_DECIMAL_TEXT, BUDGET_LIMIT_EXCEEDS_CEILING,
BUDGET_CEILING_UNKNOWN, RESOURCE_LIMIT_EXCEEDED. Messages tiếng Việt, không raw SQL
hoặc stack trace. ResourceId canonical invalid là 422. Body limits áp trước parse.

Audit giữ Store/actor/time/action/resource, before/after version và values; archive
không xóa audit. Audit readers/routes/visibility thuộc cụm auth riêng, không tự
expose vì write đã ghi. Không secrets trong logs.

<a id="planning-configuration-8"></a>
### 14.8. Runtime, backlog và acceptance

CURRENT FACT: saved/default/budget/serving persistence and revisions/audit/CAS,
C01 projection and C02 frozen acceptance exist. Save does not compute/produce Run.
Staff creator-only edits, Owner Store-wide management and current grants apply.

Acceptance specifications:

1. Custom Save không forecast/solver/Run; omit đúng inheritance; full custom không
   check default stale; saved resolved giữ null budget, không default-refresh.
2. Paths/overrides/rates exact đúng C02; foreign/inactive Product bị chặn, thiếu
   recipe/sales không chặn Save; zero không missing, unknown cap không unlimited.
3. Two writes cùng version chỉ một thành công; create-only budget không overwrite;
   same key replay không double Save, changed payload/precondition conflict.
4. Giảm cap không sửa saved; C01 invalid/read detail đúng; C02 fixed/current cap
   và archived guard atomic. Concurrent cap/Save/Run không trộn amount/version.
5. Archive bộ invalid được, không xóa Run/revisions/audit; no-op giữ timestamp;
   role/scope/ownership/revocation và money denial kiểm cả retry. Staff đọc/dùng
   bộ người khác được khi có quyền, sửa/archive thì bị chặn; Owner quản lý mọi bộ
   trong Store; không đổi creator khi một actor khác chỉnh sửa.
6. Fresh session chứng minh committed config/version/audit/receipt, crash/uncertain
   commit không false success. C03 cũ giữ values bất kể setup đã thay.
7. OpenAPI diff và public boundaries kiểm khi triển khai; real storage coverage
   chỉ `shelfcash_test`, theo runbook hiện hành. HTTP 2xx không đủ evidence.

Phạm vi ảnh hưởng đề xuất: BE config/auth/acceptance; FE setup/settings adapter;
ML/Data không đổi thuật toán hoặc forecast input identity; demo dùng UUID/money
minh họa, không seed business data thật. ADR-001/004/010/011/020 giữ nguyên; không
đổi winner/serving/FEFO. Contract hiện hành không phải API runtime.

Task notes/rollback hợp nhất: chỉ sửa contract này và xóa file cấu hình riêng sau
kiểm tra đầy đủ; không reset/restore WIP, không code/design/FE gốc, không sửa
CURRENT_STATE/ROADMAP/API_CONTRACT hoặc trạng thái S3.6.4; không ZIP/commit/push.

<a id="planning-configuration-9"></a>
### 14.9. Quyết định sản phẩm đã chốt trong lượt review

**ACCEPTED DECISION — sản phẩm, không phải runtime/ADR mới.** Nguồn là hai trả lời
trực tiếp của người dùng ngày 09/10/2026:

1. **Phạm vi dùng saved:** “Dùng chung trong Store”. C01 visibility và C02 saved
   access không giới hạn theo creator; vẫn kiểm quyền và scope Store hiện hành.
2. **Phạm vi quản lý saved:** “owner dc toàn quyền, nhân viên chỉ được sửa của mình
   nhưng được xem và dùng của ng khác”. Owner quản lý mọi bộ trong Store; Staff
   có quyền tương ứng được đọc/dùng bộ người khác nhưng chỉ sửa bộ mình tạo.
   Lưu trữ là thao tác quản lý cùng giới hạn creator, không phải quyền xóa bộ
   của người khác. Không tự cấp read/create/manage/budget permissions cho Staff.

Không còn câu hỏi business cần quyết trong cụm này. Catalogue permission chính
xác/approval/audit readers thuộc review auth riêng; storage/CAS/HTTP/FE là backlog
implementation, không mở lại resolve/winner/budget policy C01–C03. JSON/version/
validation/errors/routes là lựa chọn kỹ thuật theo ủy quyền, không hỏi từng field.

<a id="planning-readiness-integration"></a>
## 15. Bổ sung bàn giao v1 — readiness, lịch sử, engine reasons và PDF

**ĐÃ CHỐT scope qua câu trả lời trực tiếp 09/10/2026:** giữ PDF kế hoạch, danh sách
lịch sử Run và khả năng đọc lý do/cảnh báo engine; AI diễn giải review riêng.
**CURRENT FACT**: public history, retained reads, current authorization và native
PDF worker đã triển khai. Payload chuẩn tra source DTO/OpenAPI.

### 15.1. C01 integration boundary

Canonical action readiness nằm duy nhất tại [Import mục14](IMPORT_MAPPING_API_CONTRACT_VI.md#readiness-v1).
C01 readiness giữ shape mục4; status/can_generate/reason_codes/scope_estimate/
history_watermark là projection của actionplanning, cùng versions nguồn và ngày
đánh giá. Không GET solver/LLM/train, không maxsalesday=coverage. Runtimeavailability
thiếu→not_ready EXECUTION_UNAVAILABLE, validfacts không imply worker chạy được.
Config capture AT ACCEPTANCE giữ policy; forecast prepare/reuse và operational
capture theo mục7, không S3.6.4persistence tự sinh forecast hoặc budgetconfig.

<a id="planning-history-export"></a>
### 15.2. Lịch sử Run — N9 thêm cho luồng mở lại kết quả

**GET /stores/{store_id}/procurement-plans**, query limit50/max100,cursor,
status comma-separated queued|running|completed|failed,forecast_start_from/date,
forecast_start_to/date (inclusive ordered), sort=-accepted_at duy nhất, UUIDtie.
Store-wide Run trong đúng scope Store, không chỉ actor creator; yêu cầu
planning.result.read+budget.read+procurement.cost.read và membership hiện hành, như
C03. Không grant từ việc từng tạo Run. Creator display chỉ nội bộ Store identity,
không email/othermemberships. C02 body giữ nguyên, GET cùng collection là route
method mới, FE0 không có historycandidate.

Response envelope {items:RunSummary[]}; meta.pagination {limit,next_cursor,
total_count:int|null},snapshot_id:Version. RunSummary={run_id,store_id,status,
accepted_at,started_at:Timestamp|null,completed_at:Timestamp|null,
forecast_start_date:date,forecast_end_date:date,requirements_mode:default|custom|saved,
created_by:{user_id,display_name:string|null},winner_option_id:OptionId|null,
outcome:string|null,error_code:string|null,result_schema_version:string|null,
result_digest:Version|null,record_version:Version}. Outcome/error enums lấy đúng
C03 kết quả đã lưu, không suy statuscompleted=winner. Queuedsummarynullable result.
Scope cùng filter sốtotal thật hoặcnull, không totals từ page. Pagination snapshot
token bind Store/actor/filter/listrevision; nếu concurrent newRun/statuschange làm
snapshotinvalid409 SNAPSHOT_NOT_AVAILABLE và refresh; không âm thầm skip duplicate.
No DELETE/archive retention vì policy giữ Run vô thời hạn. Clickrow dùng C03 cùng
UUID, C03 phản ánh latestlifecycle của Run, completedimmutable.

```json
{"data":{"items":[{"run_id":"00000000-0000-4000-8000-000000000100","store_id":"00000000-0000-0000-0000-000000000001","status":"queued","accepted_at":"2026-10-09T03:01:00Z","started_at":null,"completed_at":null,"forecast_start_date":"2026-10-09","forecast_end_date":"2026-10-15","requirements_mode":"default","created_by":{"user_id":"00000000-0000-0000-0000-000000000004","display_name":"Owner"},"winner_option_id":null,"outcome":null,"error_code":null,"result_schema_version":null,"result_digest":null,"record_version":"run-1"}]},"meta":{"request_id":"req-history","snapshot_id":"run-list-1","pagination":{"limit":50,"next_cursor":null,"total_count":1}},"error":null}
```

### 15.3. C08 giữ route gốc — structured engine explanation

**GET /procurement-plans/{plan_id}/explanation**, no body; optional option_id
token1..128, phải tồn tại đúng Run đã lưu (không selected_option). Permissions
giống C03. Default trả global và các optionreason đủ đã lưu. Queued/running409
RESULT_NOT_READY; completed/failed có diagnostics đã lưu đọc được, không giả
engineđãchạy nếu failedtrướccapture. Response:
{run_id,result_schema_version:string|null,result_digest:Version|null,
availability:available|partial|unavailable,outcome:string|null,
winner:{option_id:OptionId|null,reason_code:string},
exclusions:ExcludedProduct[],blockers:Notification[],warnings:Notification[],
options:OptionReason[],evidence_availability:known|unknown|not_evaluated}.
ExcludedProduct đúng C03 scope (product_id,reason_codes,affected_dates);
OptionReason={option_id,eligible:boolean,rejection_reasons:string[],
not_selected_reason:string|null,source_strategies:strategy[],evidence:StrategyResult[]}.
Evidence dùng nguyên typed StrategyResult mục9, filter theo các source của option,
giữ proof enum/execution/finite scope/searchcomplete; không generic proof object
hay evidence mới. Focus option filter không bỏ globalwarnings.
Result chưacompute→options[],availabilityunavailable,winnerreason NOT_EVALUATED;
unavailable không bị chuyển thành “không có rủi ro”. Labelmessage do FE vi catalog
codes hoặc retained enginewording, không generate LLM. Không nguyên liệu attribution
giả, không recreatecomparison từ live DB; compare với C03 digest phải cùngaggregate.

```json
{"data":{"run_id":"00000000-0000-4000-8000-000000000100","result_schema_version":null,"result_digest":null,"availability":"unavailable","outcome":null,"winner":{"option_id":null,"reason_code":"NOT_EVALUATED"},"exclusions":[],"blockers":[{"code":"INPUT_CHANGED_DURING_CAPTURE","message":"Nguồn đổi trong khi chuẩn bị capture","details":{}}],"warnings":[],"options":[],"evidence_availability":"not_evaluated"},"meta":{"request_id":"req-reasons"},"error":null}
```

### 15.4. PDF — N10/N11 thêm, không thay planning state

N10 **POST /procurement-plans/{plan_id}/exports**, Idempotency-Key required,
body {format:"pdf",option_id:OptionId|null,locale:"vi"}. Explicitnull mặc định
winner đã lưu; no winner409 WINNER_NOT_AVAILABLE, FE có thể gửi option_id cụ thể
để xuất phương án khác có candidate đã lưu. option_idunknown404 OPTION_NOT_FOUND,
source/reference option cócandidate nhưng ineligible cho phép xuất với **cảnh báo
không khuyến nghị** theo policy xuất phươngánkhác, không gọi winner. No candidate
409 OPTION_NOT_EXPORTABLE. Không request render arbitrary HTML/cost replacements,
không chọn strategy bằng label tạo optionmới. Run completed mới export, failed/nonterminal
409 RESULT_NOT_READY; typedresult unreadable409 RESULT_INTEGRITY_ERROR.

Require planning.export+planning.result.read+budget.read+procurement.cost.read;
samecurrentStore boundary. Response202 {export_id:UUID,run_id,option_id,
status:"queued",job_id:UUID,result_digest:Version,render_version:"planning-pdf/1"};
meta.poll_after_ms=2000. J01 poll theo [shared job canonical](IMPORT_MAPPING_API_CONTRACT_VI.md#readiness-v1), mục14.5 (không chuyển C02 thành job_id).
J01 result khi completed={export_id,download_url:relative routeN11,sha256,
byte_count:int,media_type:"application/pdf"}; failed gồm structurederror, không
download giả. Server-supplied relative URL không external signedpublicshare.
Workerreauthorize trước materializeartifact, source chỉ **retained result**;
không solver/forecast/LLM/live costs. POST replay sau rightscheck trả sameexport/job;
digestbind run+option+locale+renderversion, differentpayloadsamekey409. Retry failed
renderer có kiểm soát cùngexportjobattempt, không request computeRun lại.

N11 **GET /procurement-plans/{plan_id}/exports/{export_id}**, download binary PDF,
không JSON successenvelope; current samepermissions mọirequest, export belongsRun+
Store check404. Completed200 application/pdf, Content-Disposition attachment
`shelfcash-plan-{run_id}.pdf`,Content-Length,ETag=artifactsha256,Cache-Control:private,
no-store, X-Content-Type-Options:nosniff. Failed/notready409 EXPORT_NOT_READY vớiJSON
errorenvelope; artifactmissing/corrupt503 EXPORT_ARTIFACT_UNAVAILABLE, không current
DBrerender ngầm. Range không cần v1; không publicshare URL/token bypasspermissions.

PDF in từ kết quả đã lưu: Store/timezone/currency, Run UUID và các thời điểm nhận/
capture; horizon, model thực dùng/provenance và tình trạng quality; requirements,
Store ceiling và effective budget; option xuất, trạng thái winner/eligible;
mọi dòng mua (quantity, packs, term IDs, arrival/expiry, cost breakdown), mức phục
vụ từng Product/path, exclusions, warnings/blockers, proof/execution/bounds và các
giả định hypothetical P1. In đủ dòng bằng nhiều trang; không screenshot hoặc chỉ
in trang FE đang xem. Giá trị display được làm tròn phải có nhãn; phụ lục exact
values gồm numerator/denominator khi C03 giữ phân số, không biến decimal_view
thành giá trị exact. PDF là report, không hóa đơn hoặc xác nhận đặt hàng. Unknown
hiện “Chưa biết/Chưa đánh giá”, không0; không thêm stochastic risk chưa có.

Renderer embed font Unicode tiếng Việt, lặp headers bảng, đánh số trang/Run ID,
hiện cảnh báo, escape dữ liệu và không scripts. Local artifact ghi atomic cùng
hash và durable job receipt; lỗi không để download file dở. V1 không tự purge
artifact; retention Run/input/result/idempotency vẫn policy cũ. Quyền worker và
mọi lần download được kiểm lại. Không solver/forecast/LLM hoặc live facts.

```json
{"format":"pdf","option_id":null,"locale":"vi"}
```

### 15.5. Validation, acceptance và backlog riêng

List/C08 errors chung mục10 +422 INVALID_FILTER/INVALID_CURSOR,409
SNAPSHOT_NOT_AVAILABLE/RESULT_NOT_READY; PDF adds409 WINNER_NOT_AVAILABLE/
OPTION_NOT_EXPORTABLE/EXPORT_NOT_READY/RESULT_INTEGRITY_ERROR,404 OPTION_NOT_FOUND;
quotaadmission413 RESOURCE_LIMIT_EXCEEDED, temporaryrenderer503 SERVICE_UNAVAILABLE.
No one-timeapprovalbypass. Badpayload422, permissions recheck beforeidempotencyreplay.

Acceptance criteria: danh sách Run đúng Store, cursor và trạng
thái; revoke/cross-Store từ chối; completed/no-winner không có winner giả; C08 cùng
digest/codes engine C03, không LLM. PDF optionnull dùng winner đã lưu; option khác
được ghi rõ eligible/reference, không có candidate thì chặn. Thay giá/công thức/
ngưỡng sau Run không đổi facts PDF. Mọi dòng và exact-value appendix đều có, font
đọc được. Concurrent retry chỉ một job/artifact; crash không download file dở;
revoke chặn worker/download/replay; PDF không tạo PO hoặc sửa Run.

CURRENT FACT: listing/C08/PDF/local fonts/artifact integrity/durable worker đã có.
PROPOSAL/OPEN: AI wording và broader PDF editing/design.

<a id="planning-detail-v1"></a>
## 16. Chi tiết kết quả từ engine — C04/C05 v1

**Authority scope:** yêu cầu mới ưu tiên chi tiết kết quả và lý do có căn cứ. FE0
là đối chiếu ID/route, không giới hạn chức năng. **TECHNICAL CHOICE** projections
sau; không thay thuật toán, winner hoặc business policy. **CURRENT FACT** đọc
application/contracts/procurement.py: candidate giữ ServingSimulationResult;
serving.py có IngredientServingDay/LotServingDay/FulfilledContribution. S3.6.4
retained aggregate không phải public navigator/detail đã triển khai. Nguồn capture
Ingredient hiện không có name: không đọc name live rồi gọi đó là tên tại Run.

### 16.1. Luồng kiểm tra và đối chiếu

Mở Run C03 → chọn option để xem (local inspection) → C04 danh sách nguyên liệu
trong computed scope → C05 chọn nguyên liệu → xem tồn tại capture, lượng mua,
arrival/expiry, balances theo7 ngày/3 paths và issues engine → C08 lý do so sánh/
proof toàn phương án → xuất PDF cùng option. Chọn xem không xác nhận mua hoặc
mutation selected_option. Current Kho là link riêng V02, ghi rõ khác snapshot Run.

| Endpoint FE0 | Xử lý | Responsibility |
| --- | --- | --- |
| C04 GET /procurement-plans/{plan_id}/ingredients | GIỮ | Paginated navigator của computed Ingredient scope, option quantities từ retained output. |
| C05 GET /procurement-plans/{plan_id}/ingredients/{ingredient_id} | GIỮ | Chi tiết facts/đánh giá đủ để kiểm tra đề xuất; không suy nguyên nhân engine chưa chứng minh. |
| C06 GET /procurement-plans/{plan_id}/ingredients/{ingredient_id}/forecast-series | GỘP vào C05 | Chart dùng daily_balances cùng option/path/snapshot; không fetch series riêng hoặc suy confidence interval. |

### 16.2. Shared selection, types và permissions

C04/C05 no body; optional option_id:OptionId, default retained winner. Nếu Run
không có winner và chưa chỉ định option, selected_option_id=null, selection_status
=not_selected; trả captured facts khi đã có computed scope, không tự chọn “best”
hoặc reference candidate. Explicit unknown option404 OPTION_NOT_FOUND; option có
identity nhưng không candidate thì option availability=no_candidate, quantities
mô phỏng null; không đổi thành0 hoặc compute lại. Nonterminal409 RESULT_NOT_READY;
terminal chưa có prepared computed scope409 COMPUTED_SCOPE_NOT_AVAILABLE; dùng
C03/C08 để đọc failure/exclusions. Ingredient không thuộc computed scope404
INGREDIENT_NOT_IN_RUN, không fallback current catalog hoặc silently broaden scope.

Permissions giống C03: planning.result.read+budget.read+procurement.cost.read,
current Store/membership, whole-response denial. Planning quyền đọc captured
facts để kiểm tra Run, không tự cấp inventory.read hoặc ingredient.read cho dữ
liệu vận hành live. Cache-Control:no-store. Meta {request_id,run_id,result_digest:
Version|null,response_version:Version,pagination?}; digest cùng retained aggregate C03/
C08, cursor gắn actor/Store/Run/digest/option/filter. Completed aggregate immutable,
không lấy inventory snapshot hiện tại để pin các pages. Integrity không verified
503 RESULT_INTEGRITY_UNAVAILABLE. Không GET solver/forecast/LLM.

**ACCEPTED DECISION S4.10 (user clarification):** C04/C05 được trả captured facts
khi Run terminal đã có prepared computed scope nhưng chưa có retained result.
Trong trường hợp này `result_digest=null` ở data và meta; integrity của captured
facts được kiểm bằng input/snapshot digest và aggregate decoder hiện có. Không
tạo digest giả hoặc thay result digest bằng snapshot digest. Purchases, path/daily
balances và fulfilled contributions chưa được đánh giá là null, không suy diễn0.
Khi retained result tồn tại, result_digest bắt buộc non-null và được validate.
Điều chỉnh nullability có điều kiện này không thay quyền đọc hoặc engine policy.

ExactQuantity/SignedDelta/BusinessDate/OptionId/Notification theo mục2. Tất cả quantities
cùng base unit Ingredient trong capture; số theo path là BOM/simulation có căn cứ,
không gọi P25/P50/P75 của Ingredient hoặc stochastic shortage probability.

### 16.3. C04 request/response

Query option_id?,limit50/max100,cursor,sort=ingredient_id duy nhất; optional repeated
ingredient_id UUID filter AND scope. Không sort theo live name/cost hoặc q nhập
nhằng trong v1. FE0 q/name/sort prototype là đề xuất được sửa theo facts capture.
Response {run_id,result_digest,selected_option_id:OptionId|null,
selection_status:winner|explicit|not_selected,items:IngredientResultRow[]}.
IngredientResultRow={ingredient_id,unit,display_name:string|null,
name_availability:captured|not_captured,purchase_quantity:ExactQuantity|null,
purchase_line_count:int|null,path_balances:IngredientBalance[]|null,
issues:Notification[],detail_available:boolean}.
IngredientBalance dùng đúng C03 {ingredient_id,unit,path,consumed,expired,ending_usable}.
Purchase quantity tổng các retained basket lines của Ingredient; candidate known
nhưng không mua Ingredient thì exact0/count0. Chưa candidate thì null/null,
path_balancesnull. Pagination total_count đúng filtered scope, không page length.

Display metadata **TECHNICAL CHOICE mới tại capture public**: retain companion
{ingredient_id,name,sku} cùng digest aggregate, không sửa engine computation input.
Historical Run không có metadata → display_name=null/name_availability=not_captured,
FE hiện UUID và cảnh báo LABEL_NOT_CAPTURED; không query tên live bổ sung lặng lẽ.
Companion capture/retention là backlog public adapter, không fact S3.6.4 hiện có.

Ví dụ C04 khi computed scope đã capture, Run không có winner và khách chưa chọn
option để xem; quantities chưa đánh giá là null:

```json
{"data":{"run_id":"00000000-0000-4000-8000-000000000100","result_digest":"result-1","selected_option_id":null,"selection_status":"not_selected","items":[{"ingredient_id":"00000000-0000-0000-0000-000000000003","unit":"l","display_name":null,"name_availability":"not_captured","purchase_quantity":null,"purchase_line_count":null,"path_balances":null,"issues":[{"code":"LABEL_NOT_CAPTURED","message":"Run chưa giữ tên nguyên liệu","details":{}}],"detail_available":true}]},"meta":{"request_id":"req-ingredients","run_id":"00000000-0000-4000-8000-000000000100","result_digest":"result-1","response_version":"run-result-1","pagination":{"limit":50,"next_cursor":null,"total_count":1}},"error":null}
```

### 16.4. C05 request/response

Query option_id? duy nhất. Response {run_id,result_digest,ingredient_id,unit,
selected_option_id:OptionId|null,selection_status,display_name:string|null,
name_availability,captured_stock:CapturedStock,purchases:Purchase[]|null,
daily_balances:IngredientDay[]|null,related_products:ProductDependency[],
issues:Notification[],evidence_availability:known|partial|not_evaluated}.

CapturedStock={captured_at:Timestamp,lots:CapturedLot[],scope_declaration:
COMPLETE_CURRENT_LOTS|CONFIRMED_EMPTY|UNKNOWN,provenance:string|null}.
CapturedLot={lot_id,quantity:ExactQuantity,unit,received_date:date|null,
expiry_date:date|null,supplier_id:UUID|null,unit_cost:MoneyText|null,
cost_availability:known|unknown}. Đây là balance tại capture, bao gồm expired
physical khi retained source có; eligibility theo ngày trong simulation, không
xóa expired lot hoặc tự gán receipt date. Unknown old declaration/provenance không
được bịa: scope_declarationUNKNOWN, provenance nullable nếu source không giữ.

Purchase cùng typed Purchase mục9, filter Ingredient; tất cả options cùng aggregate.
Supplier-order fee ở aggregate Costs/C08, không phân bổ vào từng Ingredient để
bịa contribution cost. Candidate known không mua → purchases=[]; not evaluated
→null. IngredientDay={path:LOW|BASE|HIGH,day:BusinessDate,unit,requested:
ExactQuantity,available:ExactQuantity,shortage:ExactQuantity,consumed:ExactQuantity,
expired:ExactQuantity,other_waste:ExactQuantity,ending:ExactQuantity,incoming_quantity:ExactQuantity}.
Incoming_quantity là tổng arrivals của retained evaluation.lots cùng Ingredient/path/day,
không committed inbound hoặc receipt thật. Adapter lấy retained
candidate.evaluation.ingredients cho exact Ingredient; ba
paths ×7 ngày ordered path LOW/BASE/HIGH rồi day. Không simulation rows thì null;
không nội suy/mượn rows option khác hoặc stock live. Explain expiry-day semantics
đúng engine: usable trong ngày X, expire cuối ngày X; available/ending là checkpoint
mô phỏng được engine lưu, không actual balance hoặc inventory mutation.

ProductDependency={product_id,selling_unit,ingredient_unit,recipe_ids:UUID[],affected_dates:date[],
fulfilled_contributions:array {path,day,quantity:ExactQuantity}|null}.
Recipe dependencies lấy retained recipes/BOM, fulfilled contributions từ candidate
simulation contributions; contribution quantity theo ingredient_unit (không selling_unit).
Thiếu provenance thì unavailable/null, không inverse
shortage thành Product lost-sales hoặc gán “Ingredient này gây mất X tiền”.
Issues filter retained entity/path/Ingredient/dependentProduct scope có mapping
chứng minh; Store-level blockers giữ source scope STORE, không tự gán riêng cho
Ingredient. C08 vẫn chứa đầy đủ global warnings/proof/rejection reasons; C05 link
qua cùng run_id/option_id, không cạnh tranh definition winner.

### 16.5. Errors, acceptance và FE cần đổi

General401/403/404/422 INVALID_FILTER/INVALID_CURSOR;409 RESULT_NOT_READY/
COMPUTED_SCOPE_NOT_AVAILABLE;503 RESULT_INTEGRITY_UNAVAILABLE; error envelope theo
mục10. Backend giới hạn request/output theo resource guards mục2, không truncate
collections thành report đầy đủ. C04 pages, C05 bounded Run scope1000 capturedlots/
100offers/50Products/7days; vượt representation budget trả resource error rõ ràng.

Acceptance criteria: C04/C05/C03/C08 cùng digest/option; alternate
inspection không mutation; known zero khác unavailable; actual stock sau Run thay
đổi không đổi detail; không name live vào historical report; đầy đủ3×7 retained
rows khi simulation COMPLETE; supplier fee không nhân/chia giả; thiếu quyền toàn
response denied; thuộc Store nhưng Ingredient ngoài computed scope404; no solver/
LLM; C05 physical capturedstock khác daily hypothetical usable/ending rõ nhãn.

FE bổ sung/đổi: navigator và detail kiểm tra nguồn số; lựa chọn option chỉ local;
nhãn stock tại capture so với Kho hiện tại, predicted/simulated so với actual;
unknown/không capture metadata; link C08 và PDF theo option đang xem. Không giữ
control/chart chỉ vì FE0 từng vẽ: C06 gộp C05 vì cùng daily rows.
Chart chọn LOW/BASE/HIGH, dùng requested/ending/incoming_quantity theo checkpoint
engine. Bỏ expected_demand/demand_lower/demand_upper kiểu interval chưa có definition;
đây là ba demand paths BOM có nguồn, không khoảng tin cậy của Ingredient.
Không có simulation thì vùng chart unavailable, không zero/interpolation.
CURRENT FACT: retained projection, pagination, captured display metadata và public
C04/C05 đã triển khai; không dùng live labels thay historical facts.

<a id="planning-discovery"></a>
## 17. Planning history filters và export discovery — Đợt 2

ACCEPTED DECISION: FE tìm lại Run theo creator/ngày tạo theo timezone Store,
tìm lại PDF khi mất locator. Retention Run/input/result/idempotency không thời hạn
giữ nguyên mục12/P3; không purge hoặc chỉnh historical facts.
CURRENT FACT: `app/api/history.py` N9 chỉ limit/cursor/status/forecast_start_from/
forecast_start_to/sort=-accepted_at. DTO RunSummary đã có created_by/accepted_at,
không cần creator API thứ hai. `app/api/planning_exports.py` N10 POST nhận
ExportRequest, N11 GET binary, J01 poll export job; chưa GET export collection.
Download/job kiểm current Store rights, không token URL hoặc quyền cũ của creator.

### N9 IMPLEMENTED route, query extension DESIGN_READY

GET /stores/{store_id}/procurement-plans thêm created_by_user_id?:UUID,
created_date_from?:date,created_date_to?:date (inclusive ordered). Omit creator lấy
mọi creator trong Store như hiện hành; filter không cấp user discovery hoặc quyền
đọc Store khác. Unknown creator UUID trả items[] trong authorized Store, không404
account-existence. Có thể chọn “Tôi” bằng A03 user_id hoặc dùng creator labels từ
RunSummary đã đọc; không bắt Staff gọi N12 Owner-only.

Ngày tạo = **accepted_at** của durable Run, khác forecast_start_date. Convert
from local midnight đến midnight sau to theo timezone Store rồi UTC half-open;
thiếu một đầu là unbounded bên đó. DST boundary theo IANA, không cộng24h UTC mặc
định; FE không browser timezone. AND với status/forecast date range/creator,
giữ sort -accepted_at/UUID và RunHistory/RunSummary DTO hiện có. Meta extension
{timezone:string,applied_filters:{created_by_user_id:UUID|null,
created_date_from:date|null,created_date_to:date|null}}. Không rename accepted_at
hoặc thêm timestamp giả bằng completed_at. Empty[] known no match, nullable
result_digest/outcome như current DTO; total_count current int|null giữ nguyên.

Permissions giữ planning.result.read+budget.read+procurement.cost.read và Store
membership hiện hành. Missing whole response403; không cost aggregates trong
filter suggestions. Snapshot bind filters/Store timezone/current authorization/
Run revisions; new Run/status change409 SNAPSHOT_NOT_AVAILABLE, FE reload trang1.
Query không mutation/audit business/job; retry GET an toàn, không rerun forecast.
Malformed/date order422 INVALID_FILTER, cursor mismatch422 INVALID_CURSOR;
401/403/404/503 theo [quy ước chung](API_CONTRACT.md#dot2-common).

Ví dụ request query (không JSON body):
`?created_by_user_id=00000000-0000-0000-0000-000000000004&created_date_from=2026-10-13&created_date_to=2026-10-13&limit=50`.
Với Asia/Ho_Chi_Minh, UTC range [2026-10-12T17:00:00Z,2026-10-13T17:00:00Z).
Response data reuse ví dụ N9 mục15.2; meta extension:

```json
{"timezone":"Asia/Ho_Chi_Minh","applied_filters":{"created_by_user_id":"00000000-0000-0000-0000-000000000004","created_date_from":"2026-10-13","created_date_to":"2026-10-13"}}
```

### EX01 DESIGN_READY — GET /procurement-plans/{plan_id}/exports

FE tìm lại export/job/download locator của retained Run, không gọi POST chỉ để dò.
No body, query option_id?:OptionId,status?:queued|running|completed|failed,
limit/cursor; sort -created_at/UUID cố định. Mọi exports của đúng Run/Store accessible
cho actor có planning.result.read+planning.export+budget.read+procurement.cost.read,
giống N10/J01 PDF/N11. Không chỉ creator, không ngầm cấp planning.export từ result.read.
Foreign Run404; missing known Store action403; option lạ thuộc Run422 INVALID_OPTION.
Response200 data={items:ExportSummary[]}, meta pagination/snapshot_id/observed_at.

```text
ExportSummary={export_id:UUID,run_id:UUID,job_id:UUID,option_id:OptionId,
 created_by_user_id:UUID,created_at:Timestamp,
 status:queued|running|completed|failed,
 result_digest:Version,render_version:string,version:Version,
 artifact_availability:pending|available|missing|unverifiable|failed,
 completed_at:Timestamp|null,error_code:string|null,
 download_url:string|null,sha256:string|null,byte_count:int|null,
 media_type:"application/pdf",allowed_actions:string[]}
```

Artifact fields null khi chưa verified binary, không byte_count0 cho unknown.
Completed execution là retained terminal status; nếu bytes sau đó missing/corrupt,
artifact_availability missing/unverifiable, download_url=null, không sửa historical
job thành failed hoặc giả PDF recoverable. Local path không exposed. Available
download_url là N11 relative API locator; không public/static presigned bearer URL.
EX01 snapshot pin export revisions/authorization/result_digest, metadata availability
kiểm private binary tồn tại và size/hash evidence bằng adapter read; không render.
Race bytes mất sau discovery vẫn do N11 kiểm lại. Unknown statuses/cursors422,
snapshot409; missing retained result evidence503 RESULT_INTEGRITY_UNAVAILABLE.
EX01 không tạo job/audit business, [] known no exports match filters.

Ví dụ EX01 data khi export đang queued:

```json
{"items":[{"export_id":"00000000-0000-0000-0000-000000000081","run_id":"00000000-0000-0000-0000-000000000082","job_id":"00000000-0000-0000-0000-000000000083","option_id":"option-balanced","created_by_user_id":"00000000-0000-0000-0000-000000000004","created_at":"2026-10-13T02:00:00Z","status":"queued","result_digest":"result-1","render_version":"planning-pdf/1","version":"export-1","artifact_availability":"pending","completed_at":null,"error_code":null,"download_url":null,"sha256":null,"byte_count":null,"media_type":"application/pdf","allowed_actions":["poll"]}]}
```

### N10/N11/J01 — IMPLEMENTED, giữ authority và retries

N10 POST /procurement-plans/{plan_id}/exports: Origin/CSRF/Idempotency-Key,
không If-Match/If-None-Match. Request {format:"pdf",option_id:OptionId|null,
locale:"vi"}; null resolve winner tại acceptance, không winner409 WINNER_NOT_AVAILABLE
theo source và contract mục15.4; unknown option404 OPTION_NOT_FOUND,
known strategy không exportable409 OPTION_NOT_EXPORTABLE.
202 data ExportAccepted={export_id,run_id,option_id,status:"queued",job_id,
result_digest,render_version:"planning-pdf/1"}, meta.poll_after_ms=2000.
Key/payload cũ trả original receipt/job; timeout retry samekey, không generate
export mới. N10 không resurrect failed export; user muốn attempt mới phải chọn
explicit generate lại với key mới sau review. Không chuyển Run hoặc selected option.

```json
{"format":"pdf","option_id":null,"locale":"vi"}
```

```json
{"export_id":"00000000-0000-0000-0000-000000000081","run_id":"00000000-0000-0000-0000-000000000082","option_id":"option-balanced","status":"queued","job_id":"00000000-0000-0000-0000-000000000083","result_digest":"result-1","render_version":"planning-pdf/1"}
```

J01 GET /jobs/{job_id}: no body/query, current export permissions, returns JobView
current DTO; queued/running poll2s, completed result resource_type planning_pdf_export
+resource_id/run_id/option_id/download_url/sha256/byte_count/media_type, failed
safe error_code theo mục15.4. N11 GET /procurement-plans/{plan_id}/exports/{export_id}:
no body/query, current rights on every download/retry;200 application/pdf,
Content-Disposition/Content-Length/ETag hash/private,no-store/nosniff như source.
Không JSON success hoặc token, không HTTP2xx fake missing artifact. Runtime errors
EXPORT_NOT_READY409/EXPORT_ARTIFACT_UNAVAILABLE503/RESOURCE_NOT_FOUND404 theo current source;
không redirect storage path hoặc tự render từ GET.

Binary regenerate/cache là lựa chọn kỹ thuật **có điều kiện**, không promise
automatic recovery: chỉ khi retained input/result/render implementation/evidence
đủ và integrity verified, cùng captured Run/option/result digest. Nếu không đủ,
explicit unavailable/reason, không dùng inventory/price/name hiện tại thay facts
lịch sử. Trong Đợt 2 không thêm regenerate endpoint/recovery command; FE có thể
request N10 key mới cho cùng option sau thông báo, vẫn có thể fail vì evidence thiếu.
Giữ original export intent/proof/idempotency và historical facts, không tự purge.

Allowed actions EX01: pending [poll]; available [download]; missing/unverifiable/
failed [request_new_export] chỉ khi retained evidence đủ, nếu chưa xác định [] với
reason qua error_code; không bảo đảm success. Audit tạo/export giữ actor/Run/option/
result digest/job/time, GET discovery/download không permission changes; delivery
notification import/PDF vẫn DEFERRED, không đăng ký inbox event ngoài v1.
FE thêm creator/local-date filters, export list→resume J01→download N11 và missing
artifact UI. Acceptance tương lai: Store time boundaries, filter cursor consistency,
creator không email leak; locator recovery, grant revocation discovery/download,
missing/corrupt bytes, no implicit rendering, no retained fact rewrite.
