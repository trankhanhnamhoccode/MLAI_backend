# S4.6 — Import kho, nhà cung cấp và cấu hình có nguồn

ACCEPTED DECISION: [Import §13](../IMPORT_MAPPING_API_CONTRACT_VI.md),
[Inventory N6/N8](../API_CONTRACT.md#inventory-semantics), [Authorization](../AUTHORIZATION_CONTRACT_VI.md)
và ADR-007/008/009/010/011/013. Không thay policy đã duyệt; không port UI legacy.
CURRENT FACT: source/DTO của S4.6; kết quả kiểm chứng và giới hạn ở
[current verification runbook](../runbooks/FULL_TEST_FLOW.md). Tài liệu này không chứng minh mọi API v1 đã triển khai.

## Luồng khách và FE

1. Owner duyệt toàn bộ mapping Store, identity binding/reservation và quy đổi có evidence.
   Staff đề xuất nhưng không activate mapping. Không nối identity theo tên gần giống.
2. I01 → I02 nhiều calls → I03 seal → worker analyze → M01–M04 review, MQ01 submit khi cần và N5 Owner decision.
   Quota/source-set/seal/replay giữ semantics S4.4; không thêm route nhập theo từng bảng.
3. I05 `phase=preview` → J01 → I04 `?include=preview,configurations`.
   Preview không ghi canonical. Mười lăm source schemas hiện có writer:
   products, ingredients, sales, recipes, inventory_count, suppliers,
   supplier_terms, payable_fees, scope_declarations, opening_stock,
   calendar_events, promotion_observations, usage_history, purchase_history
   và inventory_receipts. [Schema inventory](IMPORT_SCHEMA_INVENTORY.md) sở hữu fields.
   Setup identity/Excel opening/count projection/completeness hiện hành thuộc
   [Import contract](../IMPORT_MAPPING_API_CONTRACT_VI.md#setup-identity-excel-opening-stock-và-lot-count--current-fact).
4. I05 `phase=confirm_review` xác nhận evidence của chính import; activation không thay xác nhận này.
   I05 `phase=commit` phải có If-Match hiện hành, preview_id/digest và confirm=true.
   `supplier_changes=[{action_id: PreviewRow.row_id, reason}]` phải đúng toàn bộ
   rows terms/phí có `confirmation_required=true`, gồm cả AMEND_* và CREATE_* bị CHANGED.
   Không lấy mapping approval làm quyền sửa số liệu. Sales resolutions riêng giữ nguyên S4.5.
5. I05 trả202 → J01 → I06 completion bất biến. Refresh V01–V04 sau thành công.
   I04 configurations có `state=committed`, canonical IDs/version thực từ completion;
   `internal_term_version` là phiên bản canonical theo supplier/ingredient.
   Preview digest/read-set vẫn là evidence lúc review; completion không viết lại preview.
6. Tồn đầu kỳ/hàng thực nhận dùng form N6 hoặc schema Excel riêng; C3 actual
   receipt dùng cùng InventoryReceipts/N6 writer trong atomic Import transaction. Không đưa file receipt vào inventory_count.
   Owner sửa ngưỡng cảnh báo bằng N8; ngưỡng không trở thành planning constraint.

## Nhóm ghi và provenance

CURRENT FACT: Supplier source price/MOQ semantics đã bổ sung; source schema tách
khỏi canonical payload, exact price denominator/unit conversion và physical MOQ
ceil giữ provenance qua preview/completion/TermSourceRecord. Không thêm endpoint
hoặc migration. FE fields, examples, unsupported units/pricing và readiness fee
scope thuộc [canonical Import contract](../IMPORT_MAPPING_API_CONTRACT_VI.md#supplier-source-basis-và-fe-projection).

| Nhóm | CURRENT FACT canonical writes | Giới hạn chủ ý |
| --- | --- | --- |
| inventory_count | Lô existing đúng Store/Ingredient, số tuyệt đối → delta exact COUNT_CORRECTION + actor/reason/source audit | Không tạo lô, không ghi RECEIPT; bằng số cũ là NO_OP không movement0 |
| suppliers | Supplier explicit binding/create reservation + supplier_source_records immutable namespace Store/system/key | Không đổi metadata/active qua generic upsert; không đoán identity |
| supplier_terms | Core SupplierTerm + term_source_records giữ full source/max-order/provenance; internal next version theo pair | max-order null không nghĩa unlimited; không sửa giá quá khứ |
| payable_fees | PayableFeeRecord typed immutable version, resolved canonical nested IDs và JSON-path provenance | NONE cần COMPLETE và coverage đầy đủ; UNKNOWN lưu rõ unknown; không default0/thuế%/tier |
| scope_declarations | Immutable typed INVENTORY / SALES_COVERAGE / PROCUREMENT_CONTEXT revision và dependency digest | Không tạo sales0, lô0, inbound/constraints giả; readiness consumer S4.8 chưa có |

Term source registration cho core term đã tồn tại và exact-match là
`REGISTER_TERM_SOURCE`: ghi registry/provenance cho canonical term đó, không tạo
term mới hoặc tăng internal term version. Counts completion đếm logical action;
`updated_resources.terms.created_count` gồm registration, không phải số row vật lý
mới trong supplier_terms. Supplier NO_OP có thể bind source registry đã được Owner
duyệt; canonical supplier metadata không đổi.

Thay giá/phí tương lai cần ngày > ngày Store hiện tại và > ngày đầu kỳ cũ.
Không tự đóng kỳ mở. Owner khai báo trong source_context/ProfileSpec:

```json
{"term_period_amendments":[{"supplier_term_id":"00000000-0000-0000-0000-000000000001","expected_version":"77","effective_to":"2026-10-10","reason":"Điều kiện mới từ ngày tiếp theo"}],"fee_period_amendments":[{"fee_id":"00000000-0000-0000-0000-000000000002","expected_version":"78","effective_to":"2026-10-10","reason":"Bảng phí mới từ ngày tiếp theo"}]}
```

expected_version là phiên bản before trong evidence (xmin opaque), không phải
internal term version. Term chỉ sửa effective_to của kỳ được duyệt; giữ nguyên giá.
Phí không UPDATE evidence: append bản đóng kỳ của cùng source identity, rồi append
kỳ mới. Kỳ cũ gốc giữ nguyên. Preview có before/after, quyền và row_id của mọi action;
executor xác nhận đầy đủ. Fee numeric spelling tương đương không tạo revision giả.

Nested component/covered keys resolve bằng registry Store/system đã duyệt hoặc refs
canonical được reserve trong cùng frozen batch. Không dùng latest mapping giữa
review/commit; không LLM ở commit. Mọi component có typed canonical reference,
JSON path và evidence ô nguồn, kể cả coverage UNKNOWN.

INVENTORY declaration được gắn hash dependency **sau** các writes cùng atomic batch.
V01/V02 chỉ CONFIRMED nếu revision declaration mới nhất của identity còn khớp
Ingredient/tập lô hiện tại. Thêm/đổi lô khiến evidence cũ UNKNOWN; GET không ghi.
Conflicting declarations còn hiệu lực không tự chọn một nguồn. Cost không trả hoặc
SELECT qua projection completeness nếu thiếu procurement.cost.read.
SALES_COVERAGE và PROCUREMENT_CONTEXT hiện nối readiness/capture/planning qua
scoped dependency evidence. PRESENT_UNSUPPORTED giữ blocker; không fake inbound.

## N6 — Ghi nhận lô thực tế

`POST /api/v1/stores/{store_id}/inventory/receipts`, Idempotency-Key, CSRF/Origin như auth.
Quyền inventory.receive + inventory.read + ingredient.read. Unit cost có giá trị,
kể cả "0", cần procurement.cost.read. Unit đúng base unit; currency đúng Store.
TECHNICAL CHOICE: quantity/threshold decimal text tối đa200 ký tự như Source quantity;
unit_cost Money18/18. Không precision rounding; invalid representation422 trước SQL.

```json
{"origin":"OPENING_STOCK","receipt_identity":{"source_system_key":"opening-20261011","source_record_id":"milk-lot-01"},"ingredient_id":"00000000-0000-0000-0000-000000000003","supplier_id":null,"lot_code":"LOT-01","quantity":"12","unit":"l","received_date":null,"expiry_date":null,"unit_cost":null,"currency":"VND","observed_at":"2026-10-11T02:00:00Z","reason":"Ghi nhận tồn vật lý khi bắt đầu dùng","expected_inventory_version":"stock-version-from-V01-or-V02"}
```

201 với `{receipt_id,origin,lot:LotRead,movement:MovementRead,inventory_version,
audit_reference,warnings}` trong envelope auth `{data,meta,error:null}`.
OPENING_STOCK: lô mới + COUNT_CORRECTION dương từ0, không fake receipt quá khứ.
ACTUAL_RECEIPT: lô mới + RECEIPT dương. received_date null giữ null; observed_at
aware ≤ now; date known ≤ Store day; tracked Ingredient cần expiry; expired physical
giữ lại và cảnh báo. Quantity0 không tạo lô; toàn bộ hết hàng cần declaration.

Mỗi receipt identity Store/system/record tạo đúng một lô; lot_code không là identity.
Normalized same payload/same identity trả200 retained result; khác payload409
RECEIPT_IDENTITY_CONFLICT. Same key khác request409 IDEMPOTENCY_KEY_REUSED.
Source identity replay không cộng thêm stock, không đọc lại balance hiện tại.
expected_inventory_version CAS kiểm trong cùng transaction/auth fence; stale409
INVENTORY_VERSION_CONFLICT, đúng Inventory contract hiện hành. Replay vẫn kiểm
current quyền, không bypass revocation. Future observation409 STALE_STOCK_OBSERVATION;
unit mismatch422 INVALID_UNIT; tracked missing expiry422 REQUIRED_EXPIRY_MISSING.

## N8 — Owner sửa ngưỡng tồn tối thiểu

`PUT /api/v1/stores/{store_id}/inventory/{ingredient_id}/threshold`, If-Match từ
V02.threshold_version, Idempotency-Key. Owner đúng Store; Staff không được phép.
Body `{minimum_usable_quantity:"2"|null,unit:"l",reason:"..."}`.
200 `{ingredient_id,minimum_usable_quantity,unit,version,updated_at,updated_by}`,
ETag version. Null clear → unknown;0 hợp lệ. No-op giữ version; stale412
THRESHOLD_REVISION_CONFLICT; thiếu If-Match428. Unit conversion không được suy ngầm.
V01/V02 đọc threshold/completeness và tính nhãn đúng precedence contract; summary
đếm toàn Store trước pagination/filter. Near-expiry7 ngày giữ nguyên.

## Atomicity, lỗi và persistence

TECHNICAL CHOICE: migration0014 bổ sung tám tables, composite Store FKs và immutable
evidence triggers; không backfill business facts. N6/N8 transaction-owned services;
Import sử dụng transaction-owned seams Inventory/SupplierTerm, không inner commit.
Ordered table fences + current auth locks giữ absent rows và canonical read-set;
không thêm broker hay concurrency infrastructure. Giới hạn throughput: canonical
writes cùng fenced tables được serialize kể cả giữa Store khác nhau; không claim
high-throughput. Chưa chạy load testing.

Một lỗi bất kỳ → rollback tất cả canonical mutations, success audit, completion và
job success. Preview/permissions thay đổi → PREVIEW_STALE/PERMISSION_DENIED; không
lọc bỏ nhóm rồi báo thành công. Read-only I04/I06/J01 không parser/provider/write.
Same-key replay/recovery giữ retained identity. Mất ACK chỉ báo thành công nếu có
durable receipt/completion proof sau current authorization. Không kết luận concurrency
từ mock; targeted tests dùng PostgreSQL thực, fresh session và worker fences.

CURRENT FACT sau audit remediation11/10 (CA-016): source business keys1..1000,
namespace Code1..128; price/pack_cost/component.amount Money18/18; Quantity200
độc lập. Monetary internal writers giữ exact value, bỏ insignificant trailing zeros
không rounding. Storage NUMERIC không typmod; không sửa legacy facts/evidence.
Descriptors có pattern/length; retained output có historic money exception,
new input không bypass. [Compatibility matrix](../CONTRACT_COMPATIBILITY_CHANGELOG_VI.md).
N6 temporal semantics xem [contract](../API_CONTRACT.md#inventory-receipt):
opening current observation checks same Ingredient events/evidence under fence;
actual receipt gửi muộn được lưu event/recorded times và warning, không history rewrite.

Không tự forecast/BOM/FEFO/solver/readiness hoặc tính lại Run đã lưu. Purchase history,
usage/calendar/combo và dedicated receipt Excel schemas chưa được bổ sung. Timeline recipe S4.7 đã triển khai riêng, không tự close từ Import;
readiness S4.8/public planning S4.9 chưa implement.
