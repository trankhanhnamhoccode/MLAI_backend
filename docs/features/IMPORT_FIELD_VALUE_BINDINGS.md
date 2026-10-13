CURRENT FACT11/10: consumer hiện hỗ trợ chín schemas; Money input18/18 tách
Quantity200, source business keys1000 (namespace Code128). Retained evidence không
rewrite; xem [compatibility](../CONTRACT_COMPATIBILITY_CHANGELOG_VI.md) và
[feature current](IMPORT_INVENTORY_SUPPLIER.md).
Recipe source extension thêm `recipes.quantity_basis` vào PROFILE_CONSTANT/IMPORT_VALUE;
required enum PER_SERVING/WHOLE_BATCH. Không thêm source schema hoặc canonical DB field.
Semantics, FE projection và ví dụ nằm tại [Import contract](../IMPORT_MAPPING_API_CONTRACT_VI.md#recipe-source-basis-và-canonical-whole-yield).

# Giá trị chung cho sheet — explicit field-value bindings

## HISTORICAL INFORMATION — consumer S4.5

Staging/field-value foundation giữ nguyên. Nay [S4.5 canonical commit](IMPORT_CANONICAL_COMMIT.md)
đã dùng retained data/explicit declarations cho products/ingredients/sales/recipes;
I05 commit202/J01/I06, current fences/retry/atomicity. confirm_review vẫn staging-only.
Các câu “commit409/can_commit=false/no S4.5” bên dưới là HISTORICAL INFORMATION
của S4.4 extension, không mô tả current consumer; supplier/inventory consumers đã có ở S4.6, xem CURRENT_STATE.

HISTORICAL INFORMATION (10/10/2026): mở rộng S4.4 staging/mapping/preview, không canonical
writes. Typed source rows không đổi; requiredness áp dụng normalized row, không
bắt mọi field thành cột Excel. Đây không generic context injection hoặc schema mới.

## Nguồn và scope

- SOURCE_COLUMN: cột indexed đã map, giữ source index; UUID refs có thể resolve
  từ tên/mã nguồn bằng IdentityRule/reservation hiện hành (IDENTITY_BINDING).
- PROFILE_CONSTANT: scalar ổn định, declaration ID/value/evidence được Owner duyệt
  trong immutable profile version. Reuse hiển thị giá trị, không hidden default.
- IMPORT_VALUE: scalar cho toàn rows của một sheet trong import hiện tại. Profile
  chỉ giữ requirement/rule target, **không giữ giá trị**. Lần sau phải khai báo mới.

Một field đúng một nguồn; không fill-blanks-only/fallback/sample guess. Shared null
khác thiếu declaration; chỉ nullable fields nhận null. Blank string bị reject,
không chuyển ngầm thành null trong shared declaration. Zero/false giữ nguyên.
Không live lookup selling_unit/context currency để tự điền row. Units/conversion,
requiredness, date/recipe periods, Store scope và permissions vẫn được kiểm.

Allowlist/scopes theo từng schema đã freeze trước edit tại
[task notes](../runbooks/FULL_TEST_FLOW.md); bảng mọi field:
[schema inventory](IMPORT_SCHEMA_INVENTORY.md). Scalar tối đa1000 chars, integer
signed32-bit, boolean strict hoặc null có điều kiện; float/array/object/extra fields
bị reject. Tối đa64 declarations/rules mỗi sheet/profile; thực tế allowlist nhỏ hơn.
CURRENT FACT: Supplier price_basis/price_quantity/price_unit/moq_basis/moq_unit/pack_label
cho PROFILE_CONSTANT hoặc IMPORT_VALUE. pack_cost/pack_size_base_quantity/
minimum_order_quantity/lead/shelf/effective dates/max-order chỉ IMPORT_VALUE nếu
shared; không reusable commercial defaults. Source row MOQ thay bằng decimal
minimum_order_quantity; canonical minimum_order_packs vẫn integer. Chi tiết
[Supplier source basis](../IMPORT_MAPPING_API_CONTRACT_VI.md#supplier-source-basis-và-fe-projection).

opening_stock thêm unit/currency cho cả hai scopes; observed_at/reason/received_date/
expiry_date/supplier_id/unit_cost chỉ IMPORT_VALUE. Row quantity/source record key/lot
label không reusable defaults. Nested declarations vẫn JSON column, có typed reference
binding qua M04; không shared object/array hoặc arbitrary nested injection.
Không expressions/executable transforms hoặc calendar/purchase/actual receipt intake.
Chi tiết tại [setup/opening contract](../IMPORT_MAPPING_API_CONTRACT_VI.md#setup-identity-excel-opening-stock-và-lot-count--current-fact).

## M03/M04/N5 và review

M03 thêm allowed_shared_scopes và shared_value trong input_sources; nhãn/help Việt.
M01/I04 sheets có shared_field_bindings/import_values. ProfileSpec thêm reviewed
shared_field_bindings (version field_value/1): PROFILE_CONSTANT có value/id/evidence,
IMPORT_VALUE chỉ target requirement. Storage JSONB staging0013 hiện có; không migration.

M04 giữ route, shared_value resolution có thể dùng bất kỳ mapping_id thuộc sheet;
target_field phải thuộc selected_type và allowlist. Missing sources xuất trong
ProfileProposal.missing_fields; chọn nguồn shared qua M04, không tạo cột giả.
Ví dụ request (unit chưa map):

```json
{"resolution":{"kind":"shared_value","target_field":"sales.unit","scope":"PROFILE_CONSTANT","value":"ly","evidence_reference":"POS này ghi toàn bộ số lượng theo ly"}}
```

```json
{"resolution":{"kind":"shared_value","target_field":"sales.business_report_key","scope":"IMPORT_VALUE","value":"POS-A-20261010","evidence_reference":"Mã báo cáo batch đã kiểm"}}
```

Giữ session/Origin/CSRF/Idempotency-Key/If-Match mapping_revision hiện hành. Nếu field
đã map từ cột, thiếu explicit switch →409 FIELD_SOURCE_CONFLICT. Gửi đúng
replace_source_column_index + acknowledgment=true; cột cũ thành explicit IGNORE với
evidence. Nếu khai báo replacement index không tồn tại cho field cũng409. TargetRequest
chọn lại cột rõ ràng sẽ bỏ shared rule/value tương ứng; duplicate targets vẫn reject.
Null/unmatched target không tự thành shared/ignored.

Thêm/đổi source rule/scope/PROFILE_CONSTANT: proposal mới hoặc cập nhật proposal,
invalidate pins/preview/confirmation; N5 Owner-only phải duyệt trước preview. Nhập
IMPORT_VALUE lần đầu không activate rule. Dưới **approved IMPORT_VALUE rule**, sửa
giá trị cần mapping.propose/current sensitive reads; giữ profile pin, không N5 mới,
nhưng mapping/import revisions đổi và review confirmation bị invalidate. Cùng key
retry trả receipt cũ sau reauthorization, không declaration/audit mới. Retained old
profiles/previews/audit bất biến. Đổi sheet type loại rules/values khác schema.

## Normalization/provenance và ví dụ

Capture shared declarations rồi đóng Session trước normalize/compute preview.
Shared scalar dùng grammar numeric/date/approved normalization rules như source
columns; validation type sớm, lexical/cross-field/business validation toàn row tại
preview. Vì vậy khai báo sai decimal/date hoặc unit không tạo business-valid row.
Owner approval source rule không là bằng chứng row readiness.

FieldProvenance thêm value_source, source_column_index hoặc declaration_id. Applied
normalization/conversion IDs và nguồn declaration/index cùng được giữ khi derived.
Preview digest bao reviewed_sheets/shared values/scopes + mapping/pins/rules/rows;
confirmation ràng exact source/read-set/preview/revisions và current write rights.
Edit value/profile rule hoặc preview mới khiến confirmation cũ không usable.

First import: Excel Ngày/Món/SL với10/10/2026, Trà đào L12 và Latte đá0. Approved
identity rules + DMY_SLASH, unit ly PROFILE_CONSTANT, report key IMPORT_VALUE.
Owner N5 approve → preview2 normalized rows12/0 → I05 confirm_review riêng. No writes.

Second import cùng structure: reuse unit/rules/identities, Qwen không chạy; report
key không được reuse. M01 MISSING_IMPORT_VALUE/can_preview=false, sheet vẫn hiện
để FE nhập. Khai báo key mới → preview → confirmation riêng, không Owner activate
profile mới nếu source rule không thay. Recipe thiếu yield/loss/version/effectivity
chỉ preview khi có declarations explicit; null end date chỉ khi explicit nullable,
không tự yield1/loss0/ngày hôm nay. Existing recipe checks vẫn áp dụng.

## Provider và giới hạn

Qwen chỉ đề xuất indexed columns/type; allowlist descriptors có thể gửi như metadata,
actual shared declarations/profile values không gửi vào payload. Không provider
call cần thiết cho manual declaration flow, không cho model tạo constants.
Nested JSON refs chưa có automatic token binding/flatten UI; không per-row fallback,
derived canonical-value lookup hoặc arbitrary constants. No live provider/FE/browser
validation trong slice; không security/accuracy certification. Opening/actual
receipts S4.6 và purchase-history OPEN giữ nguyên. DATA_REQUIREMENTS_VI hoãn.
