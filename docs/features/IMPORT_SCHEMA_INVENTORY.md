# Inventory schemas Import hiện hành — khảo sát field-by-field

CURRENT FACT: inventory xuất từ mười lăm typed SOURCE_MODELS, gồm opening_stock và bốn miền history-only A2, không registry legacy. Đây là bảng inventory của **mọi schema**, không riêng nghiệp vụ kho. Schema/row validation là authority; descriptors không tạo capability writer. ACCEPTED DECISION: sáu workbook demo là bộ kiểm thử, không định nghĩa schema hệ thống. Đối chiếu nghiệp vụ dựa trên [legacy handoff](../../IMPORT_SCHEMA_LEGACY_HANDOFF_VI.md); implementation/consumer của legacy là HISTORICAL INFORMATION, không authority cho bản mới.

## Cách đọc và nguồn giá trị

- `required`/`required-nullable` nói về row đã normalize; nullable không nghĩa có thể bỏ field. Business fields required (một số nhận null), ngoại trừ optional-warning sales.is_stockout; discriminator `domain` có system default. Điều kiện bổ sung xem từng schema/nested model.
- Cột Excel có thể chứa tên/mã nguồn thay UUID: approved IdentityRule/alias/reservation resolve sang canonical UUID; lot count phải existing và duy nhất, opening_stock giữ reserved lot ID đến commit. Không yêu cầu người dùng biết UUID.
- CURRENT FACT: explicit scalar sources theo allowlist đã triển khai. `build_spec` nhận column/shared rule; missing IMPORT_VALUE vẫn blocked. Required row value không buộc cột vật lý. Generic arbitrary JSON/nested/context injection vẫn chưa có; không hạ validation/bịa defaults. Xem [feature](IMPORT_FIELD_VALUE_BINDINGS.md) và [allowlist/evidence](../runbooks/FULL_TEST_FLOW.md).
- Store/actor/import/file/row IDs, package/profile versions, clock/currency comparison đến từ server/session/context/binding, không business columns bắt buộc của Excel. Bảng metadata context ở dưới tách chúng khỏi row schemas.
- Mười lăm schemas có retained preview/canonical writer; opening_stock dùng InventoryUseCases và InventoryReceiptRecord của N6, inventory_count chỉ existing lots. Mixed batch atomic, dependencies toàn batch gồm master/reservation rows. C3 inventory_receipts dùng cùng InventoryReceipts/N6 ledger và có typed effects/completion; purchase_history A2 chỉ record-only. Chi tiết [setup/opening contract](../IMPORT_MAPPING_API_CONTRACT_VI.md#setup-identity-excel-opening-stock-và-lot-count--current-fact).

## Bảng toàn bộ fields

### A2 — recorded support schemas (CURRENT FACT, history-only)

Authority: `contracts/import_history.py`, projected by SOURCE_MODELS/descriptors.
All fields below are required, nullable only when stated; `domain` alone has the
system discriminator default. Common `source_record_key` is a nonblank stable
source row/event key (column only), `evidence_reference` is nonblank reviewed
evidence (column or IMPORT_VALUE). Neither filename nor name creates identity.
Store/source/report/profile/file/row/actor provenance is server/approved context.
Persistence is append-only ImportHistoryRecord; correction confirmation and domain
grants are owned by [Import](../IMPORT_MAPPING_API_CONTRACT_VI.md).

| Schema / field | Meaning / validation | Shared sources besides column |
| --- | --- | --- |
| calendar_events.event_name | Declared event name; no inferred effects | None |
| calendar_events.effective_from / effective_to | Inclusive ordered ISO date period; future declared event allowed | IMPORT_VALUE |
| calendar_events.declared_at | Aware known declaration instant ≤ now | IMPORT_VALUE |
| calendar_events.is_closed / is_holiday | Strict bool or explicit null; false ≠ unknown | IMPORT_VALUE |
| promotion_observations.product_id | Same-Store reviewed Product binding/reservation | None |
| promotion_observations.sales_date | Observed ISO Store day ≤ today | IMPORT_VALUE |
| promotion_observations.promotion_name | Nonblank name or explicit null; no name→bool | IMPORT_VALUE |
| promotion_observations.promotion_applied | Strict true/false/null observation | IMPORT_VALUE |
| usage_history.ingredient_id | Same-Store reviewed Ingredient binding/reservation | None |
| usage_history.usage_date | Actual consumption ISO Store day ≤ today | IMPORT_VALUE |
| usage_history.observed_at | Aware actual observation instant or explicit null; known instant's Store day equals usage_date and ≤now | IMPORT_VALUE |
| usage_history.quantity | Exact decimal text ≥0; actual recorded, not BOM/waste; null/missing blocked | None |
| usage_history.unit | Exact Ingredient.base_unit after reviewed physical scaling | PROFILE_CONSTANT / IMPORT_VALUE |
| purchase_history.ingredient_id | Same-Store reviewed Ingredient binding/reservation | None |
| purchase_history.supplier_id | Same-Store reviewed Supplier binding or explicit null | IMPORT_VALUE |
| purchase_history.quantity | Exact recorded physical quantity ≥0; no inbound or stock effect | None |
| purchase_history.unit | Exact Ingredient.base_unit after reviewed scaling | PROFILE_CONSTANT / IMPORT_VALUE |
| purchase_history.order_date / received_date | Separate historical ISO dates or explicit null; known receipt ≥ known order | IMPORT_VALUE |
| purchase_history.report_date | Explicit report ISO date ≤today and ≥known order/receipt; never upload fallback | IMPORT_VALUE |
| purchase_history.price | Exact Money18/18 or null only for UNKNOWN; zero meaningful | IMPORT_VALUE |
| purchase_history.price_basis | PER_QUANTITY / LINE_TOTAL / UNKNOWN; no default | PROFILE_CONSTANT / IMPORT_VALUE |
| purchase_history.price_quantity | Positive denominator for PER_QUANTITY; null otherwise; scale with price_unit, never price amount | IMPORT_VALUE |
| purchase_history.price_unit | Physical price denominator label; null outside PER_QUANTITY | PROFILE_CONSTANT / IMPORT_VALUE |
| purchase_history.currency | Explicit exact Store ISO currency; no FX | PROFILE_CONSTANT / IMPORT_VALUE |

Recorded history consumers: H01/H02 discovery categories calendar/usage/purchase,
promotion=sales; I04 retained preview and I06 immutable history_record payload,
canonical_version, locations, provenance, audit link. Preview uses latest revision
for exact reimport/correction; prior completion remains historical. No history
query replaces canonical SalesDaily, recipe/BOM, inventory or SupplierTerm. Readiness
does not mark setup complete from these records. No forecast calendar/weather/promo
features, accuracy claim, waste reconciliation, recipe adjustment, actual goods
receipts or historical-price promotion is implemented.

| Existing constraint/configuration | Real consumer / status |
| --- | --- |
| ProcurementDeclaration.capacities | planning_capture.declarations_for → captured operational/2 → evaluate_procurement_basket gross capacity check per day/path at POST_RECEIPT_PRE_EXPIRY_PRE_CONSUMPTION; ENFORCED |
| ProcurementDeclaration.supplier_limits | captured operational/2 → exact basket_violations ONE_ORDER_SUPPLIER_INGREDIENT quantity; ENFORCED |
| SupplierTerm MOQ/maximum and payable_fees | Exact pack/MOQ/offer bounds/outlay validation; unsupported formulas block; ENFORCED for supported kinds |
| Current Planning budget and customer requirements | Existing Planning configuration/request resolver → hard budget versus target satisfaction/selector; A2 does not import a generic budget row or change fairness/objective |
| MIN_SAFETY_STOCK | Storage exists but computation semantics unsupported; procurement preflight blocks, R01 now MIN_SAFETY_STOCK_UNSUPPORTED for computed Ingredient/horizon, including zero |
| Open PO / priority / arbitrary rule / weather / uplift / discount inference | Unsupported; explicit resolution/IGNORE required, never silent ready/default |

Legacy source traced read-only in IMPORT_QWEN_REPRO_20261012.zip:
`app/services/business_persistence.py::_persist_usage_history` (line344) sums same
Ingredient/day and writes current usage; `_persist_purchase_history` (line388)
falls back received_date→purchase_date and stores receipts without inventory;
`_persist_calendar_features` (line547) bool-defaults fields. A2 keeps record-only
boundaries, but deliberately requires declared grain/source key, append revisions,
separate date semantics, exact price denominator and strict nullable booleans.
The [legacy handoff](../../IMPORT_SCHEMA_LEGACY_HANDOFF_VI.md) §2.6–2.8/3.3 remains
HISTORICAL INFORMATION; old weather known_at is not causal feature evidence.

### `sales` — Doanh số

CURRENT FACT A1 (migration/targeted DB acceptance verified): optional-warning
`sales.is_stockout` strict boolean/null, column hoặc IMPORT_VALUE, không
PROFILE_CONSTANT. Source/quantity-only/not-provided declarations, exact value
aliases và multi-contribution grouping do [Import contract](../IMPORT_MAPPING_API_CONTRACT_VI.md)
sở hữu. Canonical `sales_daily.is_stockout` cần additive migration; forecast consumer
đã nối ở source theo [ADR-A1](../adr/ADR-A1-observed-stockout-demand-policy.md).
Unknown không false, sales0 không infer stockout. Duplicate guard của slice cũ
ở mô tả dưới là historical; A1 collapse exact same contribution và block conflicts.

Nguồn: `app/application/contracts/import_domains.py:18` (SalesSource); metadata kế thừa `app/application/contracts/import_scalars.py`. Validation row + preview: Product hiện có hoặc reservation đã duyệt đúng Store; exact selling_unit; ngày bán không tương lai; same-key exact duplicates collapse; conflicting contributions block; independent aggregation requires confirmation; daily_total khác disjoint_contribution, correction phải xác nhận.

CURRENT FACT A1: SalesUseCases record/replace giữ transaction-owned; group Product/day giữ source/report contributions và nullable stockout. Migration0019/persistence/consumer acceptance verified trên DB Import riêng; confirmation/fences giữ nguyên, không generic upsert.

| Field / nhãn | Requiredness / conditional | Nguồn hiện có | Validation typed (cộng rules ở trên) | Writer / dữ liệu đích  Shared scopes được phép |
| --- | --- | --- | --- | ---  --- |
| `domain` — Loại dữ liệu (backend) | optional (system default) | SYSTEM_ASSIGNED: discriminator từ approved sheet schema | type=string; const=sales | discriminator; không business DB column  Không shared; column/binding hiện hành |
| `product_id` — Món bán (tên/mã đã nối) | required | Cột tên/mã/UUID → binding approved | type=string; format=uuid | resolve canonical ref; FK/Store validation trước writer tương ứng  Không shared; column/binding hiện hành |
| `sales_date` — Ngày bán | required | Cột Excel đã map; không context auto-fill | type=string; format=date | sales_daily.sales_date  Không shared; column/binding hiện hành |
| `quantity` — Số lượng | required | Cột Excel đã map; không context auto-fill | type=string; pattern=^(0&#124;[1-9][0-9]*)(\.[0-9]+)?$; maxLength=200 | sales_daily.quantity  Không shared; column/binding hiện hành |
| `unit` — Đơn vị | required | Cột Excel hoặc explicit shared value; không fallback ô trống | type=string | kiểm Product.selling_unit; không column sales_daily.unit  PROFILE_CONSTANT / IMPORT_VALUE |
| `business_report_key` — Mã báo cáo nghiệp vụ | required | Cột Excel hoặc explicit shared value; không fallback ô trống | type=string; minLength=1; maxLength=1000 | source identity/evidence/provenance; không tự là DB column  IMPORT_VALUE |
| `is_stockout` — Observed product stockout | optional-warning; nullable, không default false | Cột đã map hoặc IMPORT_VALUE; exact aliases đã review | strict boolean/null | sales_daily.is_stockout; migration0019 và fresh-session acceptance verified. Không PROFILE_CONSTANT |

### `inventory_count` — Kiểm kê lô

Nguồn: `app/application/contracts/import_domains.py:27` (CountSource); metadata kế thừa `app/application/contracts/import_scalars.py`. Validation row + preview: Ingredient/lô hiện có đúng Store, lô thuộc Ingredient; exact base_unit; thời điểm aware không tương lai/không trước cập nhật lô; duplicate lô bị reject; chỉ NO_OP/COUNT_CORRECTION, không tạo lô.

Đích canonical S4.6: inventory_lots.on_hand_quantity + inventory_movements COUNT_CORRECTION delta; observed_at/reason audit. Writer: InventoryUseCases.adjust_in_transaction trong frozen atomic Import plan; actor/count audit cùng transaction. **CURRENT FACT: S4.6 có atomic canonical adapter**; xem [feature](IMPORT_INVENTORY_SUPPLIER.md).

| Field / nhãn | Requiredness / conditional | Nguồn hiện có | Validation typed (cộng rules ở trên) | Writer / dữ liệu đích  Shared scopes được phép |
| --- | --- | --- | --- | ---  --- |
| `domain` — Loại dữ liệu (backend) | optional (system default) | SYSTEM_ASSIGNED: discriminator từ approved sheet schema | type=string; const=inventory_count | discriminator; không business DB column  Không shared; column/binding hiện hành |
| `ingredient_id` — Nguyên liệu (tên/mã đã nối) | required | Cột tên/mã/UUID → binding approved | type=string; format=uuid | resolve canonical ref; FK/Store validation trước writer tương ứng  Không shared; column/binding hiện hành |
| `lot_id` — Lô hiện có (mã đã định danh) | required; conditional: Phải resolve duy nhất lô hiện có trong Store; không tạo lô, opening stock hoặc receipt từ kiểm kê. | Cột tên/mã/UUID → binding approved | type=string; format=uuid | resolve canonical ref; FK/Store validation trước writer tương ứng  Không shared; column/binding hiện hành |
| `on_hand` — Tồn kiểm kê | required | Cột Excel đã map; không context auto-fill | type=string; pattern=^(0&#124;[1-9][0-9]*)(\.[0-9]+)?$; maxLength=200 | inventory_lots.on_hand_quantity + delta COUNT_CORRECTION  Không shared; column/binding hiện hành |
| `unit` — Đơn vị | required | Cột Excel hoặc explicit shared value; không fallback ô trống | type=string | lot/Ingredient unit validation  PROFILE_CONSTANT / IMPORT_VALUE |
| `observed_at` — Thời điểm kiểm kê | required | Cột Excel hoặc explicit shared value; không fallback ô trống | type=string; format=date-time | inventory_movements.occurred_at; observation/version fence  IMPORT_VALUE |
| `reason` — Lý do | required | Cột Excel hoặc explicit shared value; không fallback ô trống | type=string; minLength=1; maxLength=1000 | source identity/evidence/provenance; không tự là DB column  IMPORT_VALUE |

### `opening_stock` — Tồn đầu kỳ Excel

Nguồn: `OpeningSource`; canonical after `OpeningValue` thêm system-reserved lot_id.
Writer: InventoryUseCases.receive_in_transaction(opening=True) và cùng source identity
InventoryReceiptRecord với N6; lot + COUNT_CORRECTION + actor/source audit atomic.
Không tạo receipt lịch sử; current observation/stale/lot conflicts theo N6.
Không suy completeness từ có lot; ScopeDeclarationRecord và operational/2 dùng scope
đã xác nhận. Semantics/FE projection do [Import contract](../IMPORT_MAPPING_API_CONTRACT_VI.md#setup-identity-excel-opening-stock-và-lot-count--current-fact) sở hữu.

| Field | Requiredness / validation | Source / shared scope | Canonical meaning |
| --- | --- | --- | --- |
| `domain` | system default opening_stock | approved schema | source discriminator |
| `source_record_id` | required nonblank1..128 | row column | Store + approved namespace + external source lot identity |
| `ingredient_id` | required scoped binding | name/code/UUID column | Ingredient base unit/expiry policy |
| `supplier_id` | required-nullable scoped binding | column hoặc IMPORT_VALUE | known Supplier hoặc explicit null |
| `lot_code` | required-nullable nonblank1..128 | row column | physical label; không bind identity theo label |
| `quantity` | required decimal text>0, max200 | row column | balance lúc opening; không lượng đã mua |
| `unit` | required exact canonical label hoặc reviewed physical conversion | column / PROFILE_CONSTANT / IMPORT_VALUE | InventoryLot.unit |
| `received_date` | required-nullable date, known≤today | column / IMPORT_VALUE | actual received date; unknown giữnull |
| `expiry_date` | required-nullable date; tracked Ingredient requires value | column / IMPORT_VALUE | known expiry≥known received date |
| `unit_cost` | required-nullable Money18/18 | column / IMPORT_VALUE | giá đơn vị vật lý; conversion dùng inverse factor |
| `currency` | required ISO currency exact Store | column / PROFILE_CONSTANT / IMPORT_VALUE | không FX |
| `observed_at` | required aware timestamp≤now, current stock evidence | column / IMPORT_VALUE | opening as-of khác received date/upload date |
| `reason` | required nonblank1..1000 | column / IMPORT_VALUE | justified opening movement |

### `inventory_receipts` — Hàng thực nhận C3

CURRENT FACT: `ActualReceiptSource` → `ActualReceiptValue` → shared
`InventoryReceipts`/N6 writer, atomic cùng toàn import. SourceContext/ProfileSpec
khai actual_receipt; source namespace và source_record_id là business identity.
`domain`, origin ACTUAL_RECEIPT và receipt_identity được system ghép từ schema,
reviewed namespace và source row; không nhận origin giả opening.
Không có facts mặc định; keys nullable vẫn bắt buộc có null explicit.

| Source field | Validation / meaning | Shared scope |
| --- | --- | --- |
| source_record_id | Nonblank1..128, stable external receipt line identity | None |
| ingredient_id | Scoped Ingredient binding; base-unit/expiry policy live | None |
| supplier_id | Scoped Supplier hoặc null | IMPORT_VALUE |
| lot_code | Nonblank1..128 hoặc null; label không phải identity | None |
| quantity | Exact decimal text >0; không suy từ count/history | None |
| unit | Exact Ingredient base unit hoặc supported physical conversion có evidence | PROFILE_CONSTANT / IMPORT_VALUE |
| received_date | Known date≤Store today hoặc null; không upload fallback | IMPORT_VALUE |
| expiry_date | Date hoặc null; mandatory khi Ingredient tracked, ≥known received_date | IMPORT_VALUE |
| unit_cost | Money text hoặc null; known0 hợp lệ; inverse quantity conversion | IMPORT_VALUE |
| currency | Exact Store currency, không FX | PROFILE_CONSTANT / IMPORT_VALUE |
| observed_at | Explicit aware ISO timestamp≤now; không numeric/serial/date-only | IMPORT_VALUE |
| reason | Nonblank1..1000; source fact của receipt | IMPORT_VALUE |

Typed preview `receipt_effect` giữ stable planned IDs; completion có
`receipt_reference` và committed effect. Same identity/payload reuse, different
payload conflict, batch duplicates coalesce giữ mọi location/provenance; absent
file không delete. Positive replay quantity là historical movement, không ghi mới.
Chi tiết permissions/late receipt/current fences do
[Import §16](../IMPORT_MAPPING_API_CONTRACT_VI.md#excel-actual-receipt) sở hữu.

### `recipes` — Công thức

Nguồn: `app/application/contracts/import_domains.py::RecipeSource`; metadata kế thừa `app/application/contracts/import_scalars.py`. Validation row + preview: explicit quantity_basis PER_SERVING/WHOLE_BATCH, yield>0, line quantity>0, 0<=loss<1; effective_to>=from inclusive; exact yield/Ingredient units; group Product/version, không duplicate Ingredient hoặc overlap version. PER_SERVING × yield tạo canonical whole-batch; loss giữ nguyên cho BOM. Không auto-default hoặc density conversion. [Semantics/examples/FE delta](../IMPORT_MAPPING_API_CONTRACT_VI.md#recipe-source-basis-và-canonical-whole-yield).

Đích canonical S4.6: recipes + recipe_lines; yield_unit kiểm với Product.selling_unit, không cột recipes.yield_unit. Writer: RecipeUseCases transaction-owned create; S4.5 atomic Import adapter đã có; timeline → S4.7. **CURRENT FACT: preview + canonical commit không-overlap**.

| Field / nhãn | Requiredness / conditional | Nguồn hiện có | Validation typed (cộng rules ở trên) | Writer / dữ liệu đích  Shared scopes được phép |
| --- | --- | --- | --- | ---  --- |
| `domain` — Loại dữ liệu (backend) | optional (system default) | SYSTEM_ASSIGNED: discriminator từ approved sheet schema | type=string; const=recipes | discriminator; không business DB column  Không shared; column/binding hiện hành |
| `quantity_basis` — Cơ sở định lượng | required | Cột nguồn hoặc Owner-reviewed shared declaration | enum PER_SERVING / WHOLE_BATCH; không default | source-only/provenance; deterministic whole-batch normalization; PROFILE_CONSTANT / IMPORT_VALUE |
| `product_id` — Món bán (tên/mã đã nối) | required | Cột tên/mã/UUID → binding approved | type=string; format=uuid | resolve canonical ref; FK/Store validation trước writer tương ứng  Không shared; column/binding hiện hành |
| `version` — Phiên bản | required | Cột Excel hoặc explicit shared value; không fallback ô trống | type=integer; minimum=1; maximum=2147483647 | recipes.version  IMPORT_VALUE |
| `effective_from` — Ngày bắt đầu hiệu lực | required | Cột Excel hoặc explicit shared value; không fallback ô trống | type=string; format=date | recipes.effective_from  IMPORT_VALUE |
| `effective_to` — Ngày kết thúc hiệu lực | required-nullable; conditional: Giá trị row bắt buộc, nhận null rõ ràng; không buộc cột Excel. Non-null >= effective_from, inclusive. | Cột Excel hoặc explicit shared value; không fallback ô trống | type=string; format=date; type=null | recipes.effective_to  IMPORT_VALUE |
| `yield_quantity` — Sản lượng toàn mẻ | required | Cột Excel hoặc explicit shared value; không fallback ô trống | type=string; pattern=^(0&#124;[1-9][0-9]*)(\.[0-9]+)?$; maxLength=200 | recipes.yield_quantity  PROFILE_CONSTANT / IMPORT_VALUE |
| `yield_unit` — Đơn vị sản lượng | required | Cột Excel hoặc explicit shared value; không fallback ô trống | type=string | kiểm Product.selling_unit; không recipes.yield_unit  PROFILE_CONSTANT / IMPORT_VALUE |
| `process_loss_rate` — Tỷ lệ hao hụt | required | Cột Excel hoặc explicit shared value; không fallback ô trống | type=string; pattern=^(0&#124;[1-9][0-9]*)(\.[0-9]+)?$; maxLength=200 | recipes.process_loss_rate  PROFILE_CONSTANT / IMPORT_VALUE |
| `ingredient_id` — Nguyên liệu (tên/mã đã nối) | required | Cột tên/mã/UUID → binding approved | type=string; format=uuid | resolve canonical ref; FK/Store validation trước writer tương ứng  Không shared; column/binding hiện hành |
| `quantity` — Số lượng | required | Cột Excel đã map; không context auto-fill | type=string; pattern=^(0&#124;[1-9][0-9]*)(\.[0-9]+)?$; maxLength=200 | recipe_lines.quantity  Không shared; column/binding hiện hành |
| `unit` — Đơn vị | required | Cột Excel hoặc explicit shared value; không fallback ô trống | type=string | recipe_lines.unit  PROFILE_CONSTANT / IMPORT_VALUE |

### `products` — Món bán

Nguồn: `app/application/contracts/import_domains.py:87` (ProductSource); metadata kế thừa `app/application/contracts/import_scalars.py`. Validation row + preview: Metadata strict; source key phải nối existing/reserved identity đã duyệt; mismatch metadata bị conflict, không fuzzy create.

Đích canonical S4.6: products; source_business_key thuộc identity/provenance, không Product column. Writer: ProductUseCases transaction-owned create; approved reservation/Import adapter S4.5 đã có. **CURRENT FACT: preview + canonical create/NO_OP; metadata conflict blocked**.

| Field / nhãn | Requiredness / conditional | Nguồn hiện có | Validation typed (cộng rules ở trên) | Writer / dữ liệu đích  Shared scopes được phép |
| --- | --- | --- | --- | ---  --- |
| `name` — Tên | required | Cột Excel đã map; không context auto-fill | type=string; minLength=1; maxLength=200 | products.name (adapter S4.5, atomic canonical)  Không shared; column/binding hiện hành |
| `selling_unit` — Đơn vị bán | required | Cột Excel hoặc explicit shared value; không fallback ô trống | type=string; minLength=1; maxLength=32 | products.selling_unit (adapter S4.5, atomic canonical)  PROFILE_CONSTANT / IMPORT_VALUE |
| `sku` — SKU | required-nullable | Cột Excel đã map; không context auto-fill | type=string; minLength=1; maxLength=64; type=null | products.sku (adapter S4.5, atomic canonical)  Không shared; column/binding hiện hành |
| `price` — Giá bán | required-nullable | Cột Excel đã map; không context auto-fill | type=string; pattern=^(0&#124;[1-9][0-9]*)(\.[0-9]+)?$; maxLength=200; type=null | products.price (adapter S4.5, atomic canonical)  Không shared; column/binding hiện hành |
| `active` — Đang hoạt động | required | Cột Excel hoặc explicit shared value; không fallback ô trống | type=boolean | products.active (adapter S4.5, atomic canonical)  PROFILE_CONSTANT / IMPORT_VALUE |
| `domain` — Loại dữ liệu (backend) | optional (system default) | SYSTEM_ASSIGNED: discriminator từ approved sheet schema | type=string; const=products | discriminator; không business DB column  Không shared; column/binding hiện hành |
| `source_business_key` — Mã thực thể ở nguồn | required | Cột Excel đã map; không context auto-fill | type=string; minLength=1; maxLength=1000 | source identity/evidence/provenance; không tự là DB column  Không shared; column/binding hiện hành |

### `ingredients` — Nguyên liệu

Nguồn: `app/application/contracts/import_domains.py:92` (IngredientSource); metadata kế thừa `app/application/contracts/import_scalars.py`. Validation row + preview: Metadata strict; source key phải nối existing/reserved identity đã duyệt; exact base_unit, expiry_tracking không tự suy.

Đích canonical S4.6: ingredients; source_business_key thuộc identity/provenance. Writer: IngredientUseCases transaction-owned create; approved reservation/Import adapter S4.5 đã có. **CURRENT FACT: preview + canonical create/NO_OP; không stock movement**.

| Field / nhãn | Requiredness / conditional | Nguồn hiện có | Validation typed (cộng rules ở trên) | Writer / dữ liệu đích  Shared scopes được phép |
| --- | --- | --- | --- | ---  --- |
| `name` — Tên | required | Cột Excel đã map; không context auto-fill | type=string; minLength=1; maxLength=200 | ingredients.name (adapter S4.5, atomic canonical)  Không shared; column/binding hiện hành |
| `base_unit` — Đơn vị cơ sở | required | Cột Excel hoặc explicit shared value; không fallback ô trống | type=string; minLength=1; maxLength=32 | ingredients.base_unit (adapter S4.5, atomic canonical)  PROFILE_CONSTANT / IMPORT_VALUE |
| `sku` — SKU | required-nullable | Cột Excel đã map; không context auto-fill | type=string; minLength=1; maxLength=64; type=null | ingredients.sku (adapter S4.5, atomic canonical)  Không shared; column/binding hiện hành |
| `expiry_tracking` — Theo dõi hạn dùng | required | Cột Excel hoặc explicit shared value; không fallback ô trống | type=boolean | ingredients.expiry_tracking (adapter S4.5, atomic canonical)  PROFILE_CONSTANT / IMPORT_VALUE |
| `active` — Đang hoạt động | required | Cột Excel hoặc explicit shared value; không fallback ô trống | type=boolean | ingredients.active (adapter S4.5, atomic canonical)  PROFILE_CONSTANT / IMPORT_VALUE |
| `domain` — Loại dữ liệu (backend) | optional (system default) | SYSTEM_ASSIGNED: discriminator từ approved sheet schema | type=string; const=ingredients | discriminator; không business DB column  Không shared; column/binding hiện hành |
| `source_business_key` — Mã thực thể ở nguồn | required | Cột Excel đã map; không context auto-fill | type=string; minLength=1; maxLength=1000 | source identity/evidence/provenance; không tự là DB column  Không shared; column/binding hiện hành |

### `suppliers` — Nhà cung cấp

Nguồn: `app/application/contracts/import_domains.py:97` (SupplierSource); metadata kế thừa `app/application/contracts/import_scalars.py`. Validation row + preview: Metadata strict; source key/Owner entity reservation và identity không mơ hồ; không đồng nghĩa supplier terms.

Đích canonical S4.6: suppliers; source_supplier_key thuộc identity/provenance. Writer: OperationalConfiguration.supplier + immutable Store source registry; explicit Owner-approved bind/create. **CURRENT FACT: S4.6 có atomic canonical adapter**; xem [feature](IMPORT_INVENTORY_SUPPLIER.md).

| Field / nhãn | Requiredness / conditional | Nguồn hiện có | Validation typed (cộng rules ở trên) | Writer / dữ liệu đích  Shared scopes được phép |
| --- | --- | --- | --- | ---  --- |
| `name` — Tên | required | Cột Excel đã map; không context auto-fill | type=string; minLength=1; maxLength=200 | suppliers.name (adapter S4.5, atomic canonical)  Không shared; column/binding hiện hành |
| `active` — Đang hoạt động | required | Cột Excel hoặc explicit shared value; không fallback ô trống | type=boolean | suppliers.active (adapter S4.5, atomic canonical)  PROFILE_CONSTANT / IMPORT_VALUE |
| `domain` — Loại dữ liệu (backend) | optional (system default) | SYSTEM_ASSIGNED: discriminator từ approved sheet schema | type=string; const=suppliers | discriminator; không business DB column  Không shared; column/binding hiện hành |
| `source_supplier_key` — Mã nhà cung cấp ở nguồn | required | Cột Excel đã map; không context auto-fill | type=string; minLength=1; maxLength=1000 | source identity/evidence/provenance; không tự là DB column  Không shared; column/binding hiện hành |

### `supplier_terms` — Điều khoản mua

Nguồn: `app/application/contracts/import_domains.py` (TermImportSource; TermSource/TermValue là canonical/retained). Validation row + preview: pack_size>0; explicit price/MOQ basis, denominator>0, source MOQ>0; exact canonical price và integer MOQ ceil>=1; lead_time>=0; known end>=start; exact Ingredient unit/Store currency; active period không overlap; thiếu max order cảnh báo SUPPLIER_LIMIT_SCOPE_REQUIRES_DECLARATION; tracked expiry thiếu shelf-life/arrival rule cảnh báo REQUIRED_ARRIVAL_EXPIRY_UNKNOWN. Không unlimited/default0; decision readiness vẫn boundary khác.

Đích canonical S4.6: supplier_terms các fields canonical; currency kiểm Store, source_term_key provenance; maximum_order_base_quantity được giữ trong typed term_source_records.payload; null không unlimited. Writer: SupplierTermUseCases.create_in_transaction + OperationalConfiguration.term và typed immutable source registry. **CURRENT FACT: S4.6 có atomic canonical adapter**; xem [feature](IMPORT_INVENTORY_SUPPLIER.md).

| Field / nhãn | Requiredness / conditional | Nguồn hiện có | Validation typed (cộng rules ở trên) | Writer / dữ liệu đích  Shared scopes được phép |
| --- | --- | --- | --- | ---  --- |
| `domain` — Loại dữ liệu (backend) | optional (system default) | SYSTEM_ASSIGNED: discriminator từ approved sheet schema | type=string; const=supplier_terms | discriminator; không business DB column  Không shared; column/binding hiện hành |
| `source_term_key` — Mã điều khoản ở nguồn | required | Cột Excel đã map; không context auto-fill | type=string; minLength=1; maxLength=1000 | source identity/evidence/provenance; không tự là DB column  Không shared; column/binding hiện hành |
| `supplier_id` — Nhà cung cấp (tên/mã đã nối) | required | Cột tên/mã/UUID → binding approved | type=string; format=uuid | resolve canonical ref; FK/Store validation trước writer tương ứng  Không shared; column/binding hiện hành |
| `ingredient_id` — Nguyên liệu (tên/mã đã nối) | required | Cột tên/mã/UUID → binding approved | type=string; format=uuid | resolve canonical ref; FK/Store validation trước writer tương ứng  Không shared; column/binding hiện hành |
| `effective_from` — Ngày bắt đầu hiệu lực | required | Cột Excel hoặc explicit shared value; không fallback ô trống | type=string; format=date | supplier_terms.effective_from  IMPORT_VALUE |
| `effective_to` — Ngày kết thúc hiệu lực | required-nullable; conditional: Giá trị row bắt buộc, nhận null rõ ràng; không buộc cột Excel. Non-null >= effective_from, inclusive. | Cột Excel hoặc explicit shared value; không fallback ô trống | type=string; format=date; type=null | supplier_terms.effective_to  IMPORT_VALUE |
| `unit` — Đơn vị | required | Cột Excel hoặc explicit shared value; không fallback ô trống | type=string | supplier_terms.unit  PROFILE_CONSTANT / IMPORT_VALUE |
| `pack_size_base_quantity` — Lượng trong pack theo unit nguồn | required | Cột hoặc explicit shared value | Quantity text>0 | reviewed exact conversion → supplier_terms.pack_size_base_quantity; IMPORT_VALUE |
| `pack_cost` — Giá nguồn theo price_basis | required | Cột hoặc explicit shared value | Money decimal text18 integer/18 fraction digits, finite>=0 | exact normalization → supplier_terms.pack_cost; IMPORT_VALUE |
| `currency` — Tiền tệ | required | Cột Excel hoặc explicit shared value; không fallback ô trống | type=string | kiểm Store.currency; không supplier_terms.currency  PROFILE_CONSTANT / IMPORT_VALUE |
| `minimum_order_quantity` — MOQ nguồn | required | Cột hoặc explicit shared value | Quantity text>0; PACKS phải nguyên, PHYSICAL_QUANTITY cần moq_unit | exact ceil → supplier_terms.minimum_order_packs; IMPORT_VALUE |
| `lead_time_days` — Số ngày giao | required | Cột Excel hoặc explicit shared value; không fallback ô trống | type=integer; minimum=0; maximum=2147483647 | supplier_terms.lead_time_days  IMPORT_VALUE |
| `shelf_life_days` — Số ngày hạn dùng | required-nullable; conditional: Null là chưa biết hạn dùng; preview cảnh báo REQUIRED_ARRIVAL_EXPIRY_UNKNOWN khi Ingredient theo dõi expiry thiếu shelf life hoặc approved arrival-expiry rule. Không tự điền hạn dùng. | Cột Excel hoặc explicit shared value; không fallback ô trống | type=integer; minimum=0; maximum=2147483647; type=null | supplier_terms.shelf_life_days  IMPORT_VALUE |
| `active` — Đang hoạt động | required | Cột Excel hoặc explicit shared value; không fallback ô trống | type=boolean | supplier_terms.active  PROFILE_CONSTANT / IMPORT_VALUE |
| `maximum_order_base_quantity` — Lượng mua tối đa | required-nullable | Cột Excel hoặc explicit shared value; không fallback ô trống | type=string; pattern=^(0&#124;[1-9][0-9]*)(\.[0-9]+)?$; maxLength=200; type=null | chưa canonical column; preview/declared limit, S4.6  IMPORT_VALUE |
| `price_basis` — Cơ sở giá | required | Cột hoặc reviewed shared | PER_PACK/PER_QUANTITY | source semantics; PROFILE_CONSTANT / IMPORT_VALUE |
| `price_quantity` — Lượng mẫu số giá | required-nullable | Cột hoặc explicit shared/null | >0 cho PER_QUANTITY; null cho PER_PACK | source semantics; PROFILE_CONSTANT / IMPORT_VALUE |
| `price_unit` — Đơn vị mẫu số giá | required-nullable | Cột hoặc explicit shared/null | physical compatible + reviewed exact conversion; null cho PER_PACK | source semantics; PROFILE_CONSTANT / IMPORT_VALUE |
| `moq_basis` — Cơ sở MOQ | required | Cột hoặc reviewed shared | PACKS/PHYSICAL_QUANTITY | source semantics; PROFILE_CONSTANT / IMPORT_VALUE |
| `moq_unit` — Đơn vị lượng MOQ | required-nullable | Cột hoặc explicit shared/null | physical compatible cho PHYSICAL_QUANTITY; null cho PACKS | source semantics; PROFILE_CONSTANT / IMPORT_VALUE |
| `pack_label` — Nhãn bao/thùng | optional-nullable | Cột hoặc reviewed shared, không suy từ unit | nonblank Text nếu có; không physical conversion | provenance; PROFILE_CONSTANT / IMPORT_VALUE |

### `payable_fees` — Phí phải trả

Nguồn: `app/application/contracts/import_domains.py:150` (FeeSource); metadata kế thừa `app/application/contracts/import_scalars.py`. Validation row + preview: Known end>=start; NONE cần components rỗng + COMPLETE; components basis khớp mode, keys unique; refs đúng offer/supplier; exact Store currency. Không tax/tier/free-over formula.

Đích canonical S4.6: retained preview FeeSource; PayableFeeRecord/ScopeDeclarationRecord immutable typed source revisions. Writer: OperationalConfiguration transaction-owned writer. **CURRENT FACT: S4.6 có atomic canonical adapter**; xem [feature](IMPORT_INVENTORY_SUPPLIER.md).

| Field / nhãn | Requiredness / conditional | Nguồn hiện có | Validation typed (cộng rules ở trên) | Writer / dữ liệu đích  Shared scopes được phép |
| --- | --- | --- | --- | ---  --- |
| `domain` — Loại dữ liệu (backend) | optional (system default) | SYSTEM_ASSIGNED: discriminator từ approved sheet schema | type=string; const=payable_fees | discriminator; không business DB column  Không shared; column/binding hiện hành |
| `source_fee_key` — Mã khai báo phí | required | Cột Excel hoặc explicit shared value; không fallback ô trống | type=string; minLength=1; maxLength=1000 | source identity/evidence/provenance; không tự là DB column  IMPORT_VALUE |
| `scope` — Phạm vi | required | Cột Excel hoặc explicit shared value; không fallback ô trống | type=string; const=STORE_PROCUREMENT | retained preview FeeSource; chưa canonical fee/completeness tables  PROFILE_CONSTANT / IMPORT_VALUE |
| `effective_from` — Ngày bắt đầu hiệu lực | required | Cột Excel hoặc explicit shared value; không fallback ô trống | type=string; format=date | retained preview FeeSource; chưa canonical fee/completeness tables  IMPORT_VALUE |
| `effective_to` — Ngày kết thúc hiệu lực | required-nullable; conditional: Giá trị row bắt buộc, nhận null rõ ràng; không buộc cột Excel. Non-null >= effective_from, inclusive. | Cột Excel hoặc explicit shared value; không fallback ô trống | type=string; format=date; type=null | retained preview FeeSource; chưa canonical fee/completeness tables  IMPORT_VALUE |
| `mode` — Cơ chế phí | required | Cột Excel hoặc explicit shared value; không fallback ô trống | type=string; enum=['NONE', 'PER_OFFER', 'PER_SUPPLIER_ORDER'] | retained preview FeeSource; chưa canonical fee/completeness tables  PROFILE_CONSTANT / IMPORT_VALUE |
| `coverage` — Mức khai báo đầy đủ | required | Cột Excel hoặc explicit shared value; không fallback ô trống | type=string; enum=['COMPLETE', 'UNKNOWN'] | retained preview FeeSource; chưa canonical fee/completeness tables  PROFILE_CONSTANT / IMPORT_VALUE |
| `currency` — Tiền tệ | required | Cột Excel hoặc explicit shared value; không fallback ô trống | type=string | retained preview FeeSource; chưa canonical fee/completeness tables  PROFILE_CONSTANT / IMPORT_VALUE |
| `components` — Các thành phần phí | required; conditional: NONE requires empty components and COMPLETE; other components must match mode and exact scoped refs. | Cột Excel đã map; không context auto-fill | type=array; items: FeeComponent | retained preview FeeSource; chưa canonical fee/completeness tables  Không shared; column/binding hiện hành |
| `components[].component_key` — Mã thành phần phí | required | JSON trong cột cha; refs canonical đã explicit | type=string; minLength=1; maxLength=1000 | retained preview FeeSource; chưa canonical fee/completeness tables  Không shared; column/binding hiện hành |
| `components[].label` — Tên thành phần phí | required | JSON trong cột cha; refs canonical đã explicit | type=string; minLength=1; maxLength=1000 | retained preview FeeSource; chưa canonical fee/completeness tables  Không shared; column/binding hiện hành |
| `components[].basis` — Cơ sở tính phí | required | JSON trong cột cha; refs canonical đã explicit | type=string; enum=['PER_OFFER', 'PER_SUPPLIER_ORDER'] | retained preview FeeSource; chưa canonical fee/completeness tables  Không shared; column/binding hiện hành |
| `components[].source_term_key` — Mã điều khoản nguồn | required-nullable | JSON trong cột cha; refs canonical đã explicit | type=string; type=null | retained preview FeeSource; chưa canonical fee/completeness tables  Không shared; column/binding hiện hành |
| `components[].source_supplier_key` — Mã nhà cung cấp nguồn | required-nullable | JSON trong cột cha; refs canonical đã explicit | type=string; type=null | retained preview FeeSource; chưa canonical fee/completeness tables  Không shared; column/binding hiện hành |
| `components[].amount` — Số tiền | required | JSON trong cột cha; refs canonical đã explicit | type=string; pattern=^(0&#124;[1-9][0-9]*)(\.[0-9]+)?$; maxLength=200 | retained preview FeeSource; chưa canonical fee/completeness tables  Không shared; column/binding hiện hành |
| `components[].condition` — Điều kiện thu phí | required | JSON trong cột cha; refs canonical đã explicit | type=string; const=WHEN_ORDERED | retained preview FeeSource; chưa canonical fee/completeness tables  Không shared; column/binding hiện hành |
| `covered_source_term_keys` — Điều khoản trong phạm vi | required | Cột Excel đã map; không context auto-fill | type=array; items: type=string | retained preview FeeSource; chưa canonical fee/completeness tables  Không shared; column/binding hiện hành |
| `covered_source_supplier_keys` — Nhà cung cấp trong phạm vi | required | Cột Excel đã map; không context auto-fill | type=array; items: type=string | retained preview FeeSource; chưa canonical fee/completeness tables  Không shared; column/binding hiện hành |
| `evidence_reference` — Bằng chứng khai báo | required | Cột Excel hoặc explicit shared value; không fallback ô trống | type=string; minLength=1; maxLength=1000 | source identity/evidence/provenance; không tự là DB column  IMPORT_VALUE |
| `reason` — Lý do | required | Cột Excel hoặc explicit shared value; không fallback ô trống | type=string; minLength=1; maxLength=1000 | source identity/evidence/provenance; không tự là DB column  IMPORT_VALUE |

### `scope_declarations` — Khai báo phạm vi

Nguồn: `app/application/contracts/import_domains.py:256` (DeclarationSource); metadata kế thừa `app/application/contracts/import_scalars.py`. Validation row + preview: kind discriminated; Inventory aware/unique lots; Sales unique Products, ngày và coverage phải hợp lệ ở preview; Procurement bounds/state-list consistency/capacity checkpoint exact. UNKNOWN không thành complete.

Đích canonical: ScopeDeclarationRecord immutable typed payload/dependency/provenance. OperationalConfiguration transaction-owned writer; readiness và operational/2 planning capture dùng current scoped evidence. EMPTY/complete/UNKNOWN khác nhau; xem [feature](IMPORT_INVENTORY_SUPPLIER.md).

| Field / nhãn | Requiredness / conditional | Nguồn hiện có | Validation typed (cộng rules ở trên) | Writer / dữ liệu đích  Shared scopes được phép |
| --- | --- | --- | --- | ---  --- |
| `domain` — Loại dữ liệu (backend) | optional (system default) | SYSTEM_ASSIGNED: discriminator từ approved sheet schema | type=string; const=scope_declarations | discriminator; không business DB column  Không shared; column/binding hiện hành |
| `source_declaration_key` — Mã khai báo | required | Cột Excel hoặc explicit shared value; không fallback ô trống | type=string; minLength=1; maxLength=1000 | source identity/evidence/provenance; không tự là DB column  IMPORT_VALUE |
| `declaration` — Nội dung khai báo | required; conditional: Required fields depend on kind INVENTORY/SALES_COVERAGE/PROCUREMENT_CONTEXT; nested source validation remains authoritative. | Cột Excel đã map; không context auto-fill | kind: InventoryDeclaration, SalesDeclaration, ProcurementDeclaration | ScopeDeclarationRecord.payload / current dependency evidence  Không shared; column/binding hiện hành |
| `declaration.InventoryDeclaration.kind` — Loại khai báo | required | JSON trong cột cha; refs canonical đã explicit | type=string; const=INVENTORY | ScopeDeclarationRecord.payload / current dependency evidence  Không shared; column/binding hiện hành |
| `declaration.InventoryDeclaration.ingredient_id` — Nguyên liệu đã nối | required | JSON trong cột cha; refs canonical đã explicit | type=string; format=uuid | ScopeDeclarationRecord.payload / current dependency evidence  Không shared; column/binding hiện hành |
| `declaration.InventoryDeclaration.state` — Trạng thái khai báo | required | JSON trong cột cha; refs canonical đã explicit | type=string; enum=['COMPLETE_CURRENT_LOTS', 'CONFIRMED_EMPTY', 'UNKNOWN'] | ScopeDeclarationRecord.payload / current dependency evidence  Không shared; column/binding hiện hành |
| `declaration.InventoryDeclaration.observed_at` — Thời điểm quan sát | required | JSON trong cột cha; refs canonical đã explicit | type=string; format=date-time | ScopeDeclarationRecord.payload / current dependency evidence  Không shared; column/binding hiện hành |
| `declaration.InventoryDeclaration.covered_lot_ids` — Các lô thuộc khai báo | required | JSON trong cột cha; refs canonical đã explicit | type=array; items: type=string; format=uuid | ScopeDeclarationRecord.payload / current dependency evidence  Không shared; column/binding hiện hành |
| `declaration.InventoryDeclaration.evidence_reference` — Bằng chứng | required | JSON trong cột cha; refs canonical đã explicit | type=string; minLength=1; maxLength=1000 | ScopeDeclarationRecord.payload / current dependency evidence  Không shared; column/binding hiện hành |
| `declaration.SalesDeclaration.kind` — Loại khai báo | required | JSON trong cột cha; refs canonical đã explicit | type=string; const=SALES_COVERAGE | ScopeDeclarationRecord.payload / current dependency evidence  Không shared; column/binding hiện hành |
| `declaration.SalesDeclaration.product_ids` — Các món thuộc phạm vi | required | JSON trong cột cha; refs canonical đã explicit | type=array; items: type=string; format=uuid | ScopeDeclarationRecord.payload / current dependency evidence  Không shared; column/binding hiện hành |
| `declaration.SalesDeclaration.from_date` — Ngày bắt đầu | required | JSON trong cột cha; refs canonical đã explicit | type=string; format=date | ScopeDeclarationRecord.payload / current dependency evidence  Không shared; column/binding hiện hành |
| `declaration.SalesDeclaration.to_date` — Ngày kết thúc | required | JSON trong cột cha; refs canonical đã explicit | type=string; format=date | ScopeDeclarationRecord.payload / current dependency evidence  Không shared; column/binding hiện hành |
| `declaration.SalesDeclaration.state` — Trạng thái khai báo | required | JSON trong cột cha; refs canonical đã explicit | type=string; enum=['COMPLETE', 'PARTIAL', 'UNKNOWN'] | ScopeDeclarationRecord.payload / current dependency evidence  Không shared; column/binding hiện hành |
| `declaration.SalesDeclaration.evidence_reference` — Bằng chứng | required | JSON trong cột cha; refs canonical đã explicit | type=string; minLength=1; maxLength=1000 | ScopeDeclarationRecord.payload / current dependency evidence  Không shared; column/binding hiện hành |
| `declaration.ProcurementDeclaration.kind` — Loại khai báo | required | JSON trong cột cha; refs canonical đã explicit | type=string; const=PROCUREMENT_CONTEXT | ScopeDeclarationRecord.payload / current dependency evidence  Không shared; column/binding hiện hành |
| `declaration.ProcurementDeclaration.effective_from` — Ngày bắt đầu hiệu lực | required | JSON trong cột cha; refs canonical đã explicit | type=string; format=date | ScopeDeclarationRecord.payload / current dependency evidence  Không shared; column/binding hiện hành |
| `declaration.ProcurementDeclaration.effective_to` — Ngày kết thúc hiệu lực | required-nullable | JSON trong cột cha; refs canonical đã explicit | type=string; format=date; type=null | ScopeDeclarationRecord.payload / current dependency evidence  Không shared; column/binding hiện hành |
| `declaration.ProcurementDeclaration.committed_inbound_state` — Hàng đang về đã cam kết | required | JSON trong cột cha; refs canonical đã explicit | type=string; enum=['CONFIRMED_NONE', 'PRESENT_UNSUPPORTED', 'UNKNOWN'] | ScopeDeclarationRecord.payload / current dependency evidence  Không shared; column/binding hiện hành |
| `declaration.ProcurementDeclaration.no_additional_orders_state` — Lệnh mua bổ sung | required | JSON trong cột cha; refs canonical đã explicit | type=string; enum=['CONFIRMED_NONE', 'UNKNOWN'] | ScopeDeclarationRecord.payload / current dependency evidence  Không shared; column/binding hiện hành |
| `declaration.ProcurementDeclaration.capacity_state` — Trạng thái sức chứa | required | JSON trong cột cha; refs canonical đã explicit | type=string; enum=['DECLARED', 'EXPLICIT_NOT_CONFIGURED', 'UNKNOWN'] | ScopeDeclarationRecord.payload / current dependency evidence  Không shared; column/binding hiện hành |
| `declaration.ProcurementDeclaration.capacities` — Sức chứa theo nguyên liệu | required | JSON trong cột cha; refs canonical đã explicit | type=array; items: Capacity | ScopeDeclarationRecord.payload / current dependency evidence  Không shared; column/binding hiện hành |
| `declaration.ProcurementDeclaration.capacities[].ingredient_id` — Nguyên liệu đã nối | required | JSON trong cột cha; refs canonical đã explicit | type=string; format=uuid | ScopeDeclarationRecord.payload / current dependency evidence  Không shared; column/binding hiện hành |
| `declaration.ProcurementDeclaration.capacities[].unit` — Đơn vị exact | required | JSON trong cột cha; refs canonical đã explicit | type=string | ScopeDeclarationRecord.payload / current dependency evidence  Không shared; column/binding hiện hành |
| `declaration.ProcurementDeclaration.capacities[].maximum_quantity` — Số lượng tối đa | required | JSON trong cột cha; refs canonical đã explicit | type=string; pattern=^(0&#124;[1-9][0-9]*)(\.[0-9]+)?$; maxLength=200 | ScopeDeclarationRecord.payload / current dependency evidence  Không shared; column/binding hiện hành |
| `declaration.ProcurementDeclaration.capacities[].checkpoint` — Thời điểm kiểm sức chứa | required | JSON trong cột cha; refs canonical đã explicit | type=string; const=POST_RECEIPT_PRE_EXPIRY_PRE_CONSUMPTION | ScopeDeclarationRecord.payload / current dependency evidence  Không shared; column/binding hiện hành |
| `declaration.ProcurementDeclaration.supplier_limit_state` — Trạng thái trần nhà cung cấp | required | JSON trong cột cha; refs canonical đã explicit | type=string; enum=['DECLARED', 'EXPLICIT_NOT_CONFIGURED', 'UNKNOWN'] | ScopeDeclarationRecord.payload / current dependency evidence  Không shared; column/binding hiện hành |
| `declaration.ProcurementDeclaration.supplier_limits` — Trần theo nhà cung cấp/nguyên liệu | required | JSON trong cột cha; refs canonical đã explicit | type=array; items: SupplierLimit | ScopeDeclarationRecord.payload / current dependency evidence  Không shared; column/binding hiện hành |
| `declaration.ProcurementDeclaration.supplier_limits[].supplier_id` — Nhà cung cấp đã nối | required | JSON trong cột cha; refs canonical đã explicit | type=string; format=uuid | ScopeDeclarationRecord.payload / current dependency evidence  Không shared; column/binding hiện hành |
| `declaration.ProcurementDeclaration.supplier_limits[].ingredient_id` — Nguyên liệu đã nối | required | JSON trong cột cha; refs canonical đã explicit | type=string; format=uuid | ScopeDeclarationRecord.payload / current dependency evidence  Không shared; column/binding hiện hành |
| `declaration.ProcurementDeclaration.supplier_limits[].unit` — Đơn vị exact | required | JSON trong cột cha; refs canonical đã explicit | type=string | ScopeDeclarationRecord.payload / current dependency evidence  Không shared; column/binding hiện hành |
| `declaration.ProcurementDeclaration.supplier_limits[].maximum_quantity` — Số lượng tối đa | required | JSON trong cột cha; refs canonical đã explicit | type=string; pattern=^(0&#124;[1-9][0-9]*)(\.[0-9]+)?$; maxLength=200 | ScopeDeclarationRecord.payload / current dependency evidence  Không shared; column/binding hiện hành |
| `declaration.ProcurementDeclaration.supplier_limits[].scope` — Phạm vi giới hạn | required | JSON trong cột cha; refs canonical đã explicit | type=string; const=ONE_ORDER_SUPPLIER_INGREDIENT | ScopeDeclarationRecord.payload / current dependency evidence  Không shared; column/binding hiện hành |
| `declaration.ProcurementDeclaration.evidence_reference` — Bằng chứng | required | JSON trong cột cha; refs canonical đã explicit | type=string; minLength=1; maxLength=1000 | ScopeDeclarationRecord.payload / current dependency evidence  Không shared; column/binding hiện hành |

## Metadata ngoài cột Excel

| Giá trị | Nguồn / validation / đích |
| --- | --- |
| Store, actor, grants | Trusted session + current Store membership; server-owned, không tin file/payload ownership. |
| file/sheet/source row/index/digest | Parser/staging assigns; giữ physical provenance, không model tạo. |
| source_system_key/report_type | M04 SourceContext USER_DECLARED ổn định Store; Owner duyệt profile; không suy filename. |
| sales_semantics/inventory_semantics | SourceContext approved: daily_total/disjoint_contribution, lot_stock_count; không đổi thành receipt. |
| decimal_locale/date_format; supplier basis declarations | Approved parsing/normalization context; không tự đoán locale/unit price basis. |
| profile/version/identity/conversion | Immutable approved profile pins; IDs/version backend; exact rational conversion cần evidence, không tự kg↔g. |
| Store timezone/currency/now | Authorized detached read-set/server context cho validation; không tự thay missing row currency/date. |
| preview/review confirmation | Backend retained IDs/digests/revisions/audit, không mutable confirmed flag tùy ý. |

Bảng gồm fields, discriminator, nested structured values và context metadata. Declaration/fee nhận JSON trong cột cha; declaration typed reference paths đã có explicit reviewed token binding, chưa flatten-column UI hoặc arbitrary nested inference.

## Đối chiếu legacy và nhu cầu đã duyệt

| Legacy / nhu cầu | Phân loại | Capability hiện hành / gap / dependency |
| --- | --- | --- |
| sales_history | CURRENT FACT: canonical chain hiện có | SalesSource → approved Product binding/unit/source semantics → preview → SalesUseCases → sales_daily → forecast capture; coverage/readiness vẫn kiểm riêng. Không copy legacy cộng dồn/correction/defaults. |
| recipes | CURRENT FACT: serving/batch source normalization đã nối canonical chain | Explicit quantity_basis/shared declaration → exact normalization/whole-yield preview grouping → RecipeUseCases → recipes/recipe_lines → dated BOM → readiness recipe_dependencies. Giữ source values/basis trong line provenance; không lấy alias làm chứng cứ đủ. |
| menu | Một phần nhãn; phần khác mới/chưa duyệt | products metadata hiện có; combo/item_type/variant rules legacy không tự port. |
| supplier_constraints | CURRENT FACT: source basis đã nối canonical chain | TermImportSource + explicit price denominator/MOQ basis + reviewed conversion → canonical validation → SupplierTerm/TermSourceRecord → planning_capture offers → exact procurement pack/MOQ/cost và fee readiness. Không đồng nghĩa lịch sử mua. |
| business_constraints | Một phần contract, không parity registry | chỉ scope_declarations tagged kinds đã hỗ trợ; không generic arbitrary constraint engine. Persistence S4.6; kinds khác OPEN. |
| inventory snapshot của legacy | CURRENT FACT: count và opening tách semantics | inventory_count chỉ target existing lot; opening_stock dedicated intake dùng approved identity/units, không legacy auto-create theo spelling/batch label. |
| Opening stock | CURRENT FACT: Excel intake nối writer/consumer | opening_stock → reviewed Ingredient/Supplier + physical lot facts → preview/frozen effects → InventoryUseCases + receipt identity/audit → lot/count movement → scoped completeness → readiness/operational2 planning. |
| Actual goods receipts | IMPLEMENTED C3 inventory_receipts trong pipeline hiện có | N6 và Excel cùng identity/ledger/InventoryReceipts; ACTUAL_RECEIPT tạo lot + RECEIPT, preview không ghi kho, không map inventory_count. |
| purchase_history | CURRENT FACT A2: history-only | Typed exact price basis + quantity/unit + separate dates → preview/correction → immutable history revisions → I06 payload/version and H01/H02 category purchase. No inventory/term/inbound effects. |
| usage_history | CURRENT FACT A2: history-only | Typed recorded quantity/unit/day/time → immutable history revisions → I06 and H01/H02 category usage. Not movement USAGE/BOM/waste reconciliation. |
| calendar_features | CURRENT FACT A2: calendar_events and promotion_observations, history-only | Declared Store event period/known timestamp differs from observed Product/day promotion. Read I06 and history categories; no model features/weather/uplift/discount inference. |
| sales stockout observation | CURRENT FACT A1 complete | Nullable SalesDaily observation → causal schema2 demand capture/training/serving/readiness/retained replay; schema1 unchanged. Legacy remains historical source evidence, not the current policy. |
| unknown | Unsupported/review | Không source schema mới; manual choose supported type hoặc acknowledged ignore. Không zero-row fake success. |

Nguồn đối chiếu: [legacy handoff](../../IMPORT_SCHEMA_LEGACY_HANDOFF_VI.md), mục2.3 (Sales/stockout), 2.4–2.8 (recipe/inventory/supplier/usage/calendar/constraints), 3.3 (consumer), 4.4 (readiness) và 6 (gaps). N6 thuộc [API contract](../API_CONTRACT.md); lot_stock_count thuộc [Import contract](../IMPORT_MAPPING_API_CONTRACT_VI.md). Legacy source/ZIP chỉ evidence, không authority.

## Gaps có kế hoạch / OPEN

- CURRENT FACT: `import_commit.py::SUPPORTED` và `write_rows` đã orchestrate cả mười lăm schemas, gồm opening_stock và A2. S4.5/S4.6 không còn là gaps persistence chung. Bounded scalar sources, immutable approved profiles, atomic commit và read-set/current-rights revalidation hiện có; API2xx/import completed vẫn không đủ chứng minh planning ready.
- ACCEPTED DECISION: ưu tiên đóng chuỗi nghiệp vụ cốt lõi, giữ exact semantics, Owner approval/profile reuse và không port defaults/permissive conversions hoặc constraints chỉ lưu. Schema mới phải có validation, writer, consumer được enforce và readiness tương ứng trước khi gọi là hoàn thiện.
- CURRENT FACT: Recipe serving/batch và Supplier price/MOQ source basis đã nối các canonical chains hiện có. Supplier physical MOQ dùng ceil điều kiện pack nguyên, giữ source MOQ; giá không làm tròn. Các limits/unsupported cases và FE projection thuộc [Import §13.2](../IMPORT_MAPPING_API_CONTRACT_VI.md#supplier-source-basis-và-fe-projection). Không tự đặt yield/loss/version/lead time hoặc suy phí miễn phí; không bắt đầu lát tiếp khi chưa được duyệt.
- PROPOSAL — acceptance cho từng lát: inputs tổng hợp ngoài sáu workbook; ambiguous/missing/zero/null/invalid units và exact arithmetic; profile approve/reuse/drift; preview/commit cùng validators; fresh-session canonical state; consumer BOM/FEFO/procurement thực sự dùng giá trị; readiness block thiếu/stale evidence và phân biệt confirmed empty với UNKNOWN. Tests hiện có là điểm bắt đầu, không phải kết quả vừa chạy.
- CURRENT FACT: Excel opening_stock đã nối lifecycle N6. Missing/partial inventory giữ UNKNOWN; explicit zero declaration và complete exact lots scope nối readiness/capture operational/2. Actual receipt Excel C3 đã implemented, cùng N6 identity/writer; count chỉ existing lots, received_date không derive từ as-of/upload.
- CURRENT FACT: fee/declaration writers đã có; `planning_capture.py::declarations_for` đưa fee coverage, supplier limits và capacities vào captured inputs. Kind constraint mới còn OPEN cho tới khi có enforcement/capability/readiness, không generic free-text constraint importer. Budget/config dùng contract Planning hiện có; thiếu và zero không được gộp.
- ACCEPTED DECISION: A1 stockout đã được mở riêng. CURRENT FACT: schema/mapping/preview, migration/persistence, demand consumer và readiness đã có targeted acceptance trên DB Import riêng; [ADR-A1](../adr/ADR-A1-observed-stockout-demand-policy.md) sở hữu policy/compatibility; A2 recorded support domains được duyệt riêng.
- CURRENT FACT A2: purchase/usage/calendar/promotion có record-only writer và retained read consumer. OPEN: waste/reconciliation, calendar/weather forecast features, actual revenue, combo/mixed-table workflows. Nested bindings/flatten JSON UI ngoài allowlist chưa có runtime.
- Unsupported M03: tax_percent/free_over_threshold/tiers/payment_terms không writer/source schema; không silently ignore thành readiness.

Trace current chain: `app/application/contracts/import_domains.py`, `import_analysis.py::build_spec`, `import_preview.py::normalize/make_preview`, `import_commit.py::write_rows`, `use_cases/operational_configuration.py`, `app/domain/demand/bom.py::expand_dated_bom`, `app/domain/decision/procurement.py`, `app/infrastructure/database/planning_capture.py::declarations_for`, `app/application/readiness_evaluation.py::recipe_dependencies/watermark`. Source/tests mô tả implementation; không thay thế acceptance trên môi trường đang chạy.

Trace stockout legacy đã kiểm source: `app/services/business_persistence.py::_persist_sales_history` ghi nullable is_stockout; `app/repositories/forecast_data.py::sales_history` đọc sang frame; `shelfcash_core/data/demand_reconstruction.py::reconstruct_demand` xác định censored/reference/unknown; `shelfcash_core/features/historical.py::add_historical_features` tạo rolling counts/rates. `shelfcash_core/pipeline/{training_pipeline,inference_pipeline}.py` gọi reconstruction và historical features. Đây là consumer thật theo static source, chưa phải runtime test lại legacy.
