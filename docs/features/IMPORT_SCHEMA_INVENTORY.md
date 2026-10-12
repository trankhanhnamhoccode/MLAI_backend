# Inventory schemas Import hiện hành — khảo sát field-by-field

CURRENT FACT (2026-10-10): xuất từ chín typed SOURCE_MODELS, không registry legacy. Đây là bảng inventory của **mọi schema**, không riêng nghiệp vụ kho. Schema/row validation là authority; descriptors không tạo capability writer.

## Cách đọc và nguồn giá trị

- `required`/`required-nullable` nói về row đã normalize; nullable không nghĩa có thể bỏ field. Hiện các business fields đều required (một số nhận null); chỉ discriminator `domain` có system default. Điều kiện bổ sung xem từng schema/nested model.
- Cột Excel có thể chứa tên/mã nguồn thay UUID: approved IdentityRule/alias/reservation resolve sang canonical UUID; lot phải existing và duy nhất. Không yêu cầu người dùng biết UUID.
- CURRENT FACT: explicit scalar sources theo allowlist đã triển khai. `build_spec` nhận column/shared rule; missing IMPORT_VALUE vẫn blocked. Required row value không buộc cột vật lý. Generic arbitrary JSON/nested/context injection vẫn chưa có; không hạ validation/bịa defaults. Xem [feature](IMPORT_FIELD_VALUE_BINDINGS.md) và [allowlist/evidence](../runbooks/FULL_TEST_FLOW.md).
- Store/actor/import/file/row IDs, package/profile versions, clock/currency comparison đến từ server/session/context/binding, không business columns bắt buộc của Excel. Bảng metadata context ở dưới tách chúng khỏi row schemas.
- Cả chín schemas có retained preview; **S4.5 canonical commit** hỗ trợ products/ingredients/sales/recipes. S4.6 đã bổ sung commit cho năm schemas còn lại; mixed batch vẫn atomic toàn bộ. Chi tiết [feature](IMPORT_CANONICAL_COMMIT.md). N6 opening/receipt có public writer riêng; chưa có dedicated Excel intake schema, purchase-history OPEN.

## Bảng toàn bộ fields

### `sales` — Doanh số

Nguồn: `app/application/contracts/import_domains.py:18` (SalesSource); metadata kế thừa `app/application/contracts/import_scalars.py`. Validation row + preview: Product hiện có hoặc reservation đã duyệt đúng Store; exact selling_unit; ngày bán không tương lai; reject duplicate Product/day; daily_total khác disjoint_contribution, correction phải xác nhận.

CURRENT FACT S4.5: sales_daily.quantity/sales_date/product_id; unit kiểm; versioned source report provenance immutable audit0013. SalesUseCases record/replace transaction-owned; explicit correction/merge + full confirmation/fences. Không generic upsert.

| Field / nhãn | Requiredness / conditional | Nguồn hiện có | Validation typed (cộng rules ở trên) | Writer / dữ liệu đích  Shared scopes được phép |
| --- | --- | --- | --- | ---  --- |
| `domain` — Loại dữ liệu (backend) | optional (system default) | SYSTEM_ASSIGNED: discriminator từ approved sheet schema | type=string; const=sales | discriminator; không business DB column  Không shared; column/binding hiện hành |
| `product_id` — Món bán (tên/mã đã nối) | required | Cột tên/mã/UUID → binding approved | type=string; format=uuid | resolve canonical ref; FK/Store validation trước writer tương ứng  Không shared; column/binding hiện hành |
| `sales_date` — Ngày bán | required | Cột Excel đã map; không context auto-fill | type=string; format=date | sales_daily.sales_date  Không shared; column/binding hiện hành |
| `quantity` — Số lượng | required | Cột Excel đã map; không context auto-fill | type=string; pattern=^(0&#124;[1-9][0-9]*)(\.[0-9]+)?$; maxLength=200 | sales_daily.quantity  Không shared; column/binding hiện hành |
| `unit` — Đơn vị | required | Cột Excel hoặc explicit shared value; không fallback ô trống | type=string | kiểm Product.selling_unit; không column sales_daily.unit  PROFILE_CONSTANT / IMPORT_VALUE |
| `business_report_key` — Mã báo cáo nghiệp vụ | required | Cột Excel hoặc explicit shared value; không fallback ô trống | type=string; minLength=1; maxLength=1000 | source identity/evidence/provenance; không tự là DB column  IMPORT_VALUE |

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

### `recipes` — Công thức

Nguồn: `app/application/contracts/import_domains.py:43` (RecipeSource); metadata kế thừa `app/application/contracts/import_scalars.py`. Validation row + preview: yield>0, line quantity>0, loss<1; effective_to>=from inclusive; exact yield/Ingredient units; group Product/version, không duplicate Ingredient hoặc overlap version.

Đích canonical S4.6: recipes + recipe_lines; yield_unit kiểm với Product.selling_unit, không cột recipes.yield_unit. Writer: RecipeUseCases transaction-owned create; S4.5 atomic Import adapter đã có; timeline → S4.7. **CURRENT FACT: preview + canonical commit không-overlap**.

| Field / nhãn | Requiredness / conditional | Nguồn hiện có | Validation typed (cộng rules ở trên) | Writer / dữ liệu đích  Shared scopes được phép |
| --- | --- | --- | --- | ---  --- |
| `domain` — Loại dữ liệu (backend) | optional (system default) | SYSTEM_ASSIGNED: discriminator từ approved sheet schema | type=string; const=recipes | discriminator; không business DB column  Không shared; column/binding hiện hành |
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

Nguồn: `app/application/contracts/import_domains.py:102` (TermSource); metadata kế thừa `app/application/contracts/import_scalars.py`. Validation row + preview: pack_size>0; MOQ>=1; lead_time>=0; known end>=start; exact Ingredient unit/Store currency; active period không overlap; thiếu max order cảnh báo SUPPLIER_LIMIT_SCOPE_REQUIRES_DECLARATION; tracked expiry thiếu shelf-life/arrival rule cảnh báo REQUIRED_ARRIVAL_EXPIRY_UNKNOWN (không source-row reject). Không unlimited/default0; decision readiness vẫn boundary khác.

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
| `pack_size_base_quantity` — Số lượng cơ sở mỗi pack | required | Cột Excel hoặc explicit shared value; không fallback ô trống | type=string; pattern=^(0&#124;[1-9][0-9]*)(\.[0-9]+)?$; maxLength=200 | supplier_terms.pack_size_base_quantity  IMPORT_VALUE |
| `pack_cost` — Giá mỗi pack | required | Cột Excel hoặc explicit shared value; không fallback ô trống | type=string; pattern=^(0&#124;[1-9][0-9]*)(\.[0-9]+)?$; maxLength=200 | supplier_terms.pack_cost  IMPORT_VALUE |
| `currency` — Tiền tệ | required | Cột Excel hoặc explicit shared value; không fallback ô trống | type=string | kiểm Store.currency; không supplier_terms.currency  PROFILE_CONSTANT / IMPORT_VALUE |
| `minimum_order_packs` — Số pack tối thiểu | required | Cột Excel hoặc explicit shared value; không fallback ô trống | type=integer; minimum=1; maximum=2147483647 | supplier_terms.minimum_order_packs  IMPORT_VALUE |
| `lead_time_days` — Số ngày giao | required | Cột Excel hoặc explicit shared value; không fallback ô trống | type=integer; minimum=0; maximum=2147483647 | supplier_terms.lead_time_days  IMPORT_VALUE |
| `shelf_life_days` — Số ngày hạn dùng | required-nullable; conditional: Null là chưa biết hạn dùng; preview cảnh báo REQUIRED_ARRIVAL_EXPIRY_UNKNOWN khi Ingredient theo dõi expiry thiếu shelf life hoặc approved arrival-expiry rule. Không tự điền hạn dùng. | Cột Excel hoặc explicit shared value; không fallback ô trống | type=integer; minimum=0; maximum=2147483647; type=null | supplier_terms.shelf_life_days  IMPORT_VALUE |
| `active` — Đang hoạt động | required | Cột Excel hoặc explicit shared value; không fallback ô trống | type=boolean | supplier_terms.active  PROFILE_CONSTANT / IMPORT_VALUE |
| `maximum_order_base_quantity` — Lượng mua tối đa | required-nullable | Cột Excel hoặc explicit shared value; không fallback ô trống | type=string; pattern=^(0&#124;[1-9][0-9]*)(\.[0-9]+)?$; maxLength=200; type=null | chưa canonical column; preview/declared limit, S4.6  IMPORT_VALUE |

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

Đích canonical S4.6: retained preview DeclarationSource; chưa canonical completeness/capacity/limit tables. Writer: OperationalConfiguration transaction-owned writer; readiness consumer S4.8 chưa có. **CURRENT FACT: S4.6 có atomic canonical adapter**; xem [feature](IMPORT_INVENTORY_SUPPLIER.md).

| Field / nhãn | Requiredness / conditional | Nguồn hiện có | Validation typed (cộng rules ở trên) | Writer / dữ liệu đích  Shared scopes được phép |
| --- | --- | --- | --- | ---  --- |
| `domain` — Loại dữ liệu (backend) | optional (system default) | SYSTEM_ASSIGNED: discriminator từ approved sheet schema | type=string; const=scope_declarations | discriminator; không business DB column  Không shared; column/binding hiện hành |
| `source_declaration_key` — Mã khai báo | required | Cột Excel hoặc explicit shared value; không fallback ô trống | type=string; minLength=1; maxLength=1000 | source identity/evidence/provenance; không tự là DB column  IMPORT_VALUE |
| `declaration` — Nội dung khai báo | required; conditional: Required fields depend on kind INVENTORY/SALES_COVERAGE/PROCUREMENT_CONTEXT; nested source validation remains authoritative. | Cột Excel đã map; không context auto-fill | kind: InventoryDeclaration, SalesDeclaration, ProcurementDeclaration | retained preview DeclarationSource; chưa canonical completeness/capacity/limit tables  Không shared; column/binding hiện hành |
| `declaration.InventoryDeclaration.kind` — Loại khai báo | required | JSON trong cột cha; refs canonical đã explicit | type=string; const=INVENTORY | retained preview DeclarationSource; chưa canonical completeness/capacity/limit tables  Không shared; column/binding hiện hành |
| `declaration.InventoryDeclaration.ingredient_id` — Nguyên liệu đã nối | required | JSON trong cột cha; refs canonical đã explicit | type=string; format=uuid | retained preview DeclarationSource; chưa canonical completeness/capacity/limit tables  Không shared; column/binding hiện hành |
| `declaration.InventoryDeclaration.state` — Trạng thái khai báo | required | JSON trong cột cha; refs canonical đã explicit | type=string; enum=['COMPLETE_CURRENT_LOTS', 'CONFIRMED_EMPTY', 'UNKNOWN'] | retained preview DeclarationSource; chưa canonical completeness/capacity/limit tables  Không shared; column/binding hiện hành |
| `declaration.InventoryDeclaration.observed_at` — Thời điểm quan sát | required | JSON trong cột cha; refs canonical đã explicit | type=string; format=date-time | retained preview DeclarationSource; chưa canonical completeness/capacity/limit tables  Không shared; column/binding hiện hành |
| `declaration.InventoryDeclaration.covered_lot_ids` — Các lô thuộc khai báo | required | JSON trong cột cha; refs canonical đã explicit | type=array; items: type=string; format=uuid | retained preview DeclarationSource; chưa canonical completeness/capacity/limit tables  Không shared; column/binding hiện hành |
| `declaration.InventoryDeclaration.evidence_reference` — Bằng chứng | required | JSON trong cột cha; refs canonical đã explicit | type=string; minLength=1; maxLength=1000 | retained preview DeclarationSource; chưa canonical completeness/capacity/limit tables  Không shared; column/binding hiện hành |
| `declaration.SalesDeclaration.kind` — Loại khai báo | required | JSON trong cột cha; refs canonical đã explicit | type=string; const=SALES_COVERAGE | retained preview DeclarationSource; chưa canonical completeness/capacity/limit tables  Không shared; column/binding hiện hành |
| `declaration.SalesDeclaration.product_ids` — Các món thuộc phạm vi | required | JSON trong cột cha; refs canonical đã explicit | type=array; items: type=string; format=uuid | retained preview DeclarationSource; chưa canonical completeness/capacity/limit tables  Không shared; column/binding hiện hành |
| `declaration.SalesDeclaration.from_date` — Ngày bắt đầu | required | JSON trong cột cha; refs canonical đã explicit | type=string; format=date | retained preview DeclarationSource; chưa canonical completeness/capacity/limit tables  Không shared; column/binding hiện hành |
| `declaration.SalesDeclaration.to_date` — Ngày kết thúc | required | JSON trong cột cha; refs canonical đã explicit | type=string; format=date | retained preview DeclarationSource; chưa canonical completeness/capacity/limit tables  Không shared; column/binding hiện hành |
| `declaration.SalesDeclaration.state` — Trạng thái khai báo | required | JSON trong cột cha; refs canonical đã explicit | type=string; enum=['COMPLETE', 'PARTIAL', 'UNKNOWN'] | retained preview DeclarationSource; chưa canonical completeness/capacity/limit tables  Không shared; column/binding hiện hành |
| `declaration.SalesDeclaration.evidence_reference` — Bằng chứng | required | JSON trong cột cha; refs canonical đã explicit | type=string; minLength=1; maxLength=1000 | retained preview DeclarationSource; chưa canonical completeness/capacity/limit tables  Không shared; column/binding hiện hành |
| `declaration.ProcurementDeclaration.kind` — Loại khai báo | required | JSON trong cột cha; refs canonical đã explicit | type=string; const=PROCUREMENT_CONTEXT | retained preview DeclarationSource; chưa canonical completeness/capacity/limit tables  Không shared; column/binding hiện hành |
| `declaration.ProcurementDeclaration.effective_from` — Ngày bắt đầu hiệu lực | required | JSON trong cột cha; refs canonical đã explicit | type=string; format=date | retained preview DeclarationSource; chưa canonical completeness/capacity/limit tables  Không shared; column/binding hiện hành |
| `declaration.ProcurementDeclaration.effective_to` — Ngày kết thúc hiệu lực | required-nullable | JSON trong cột cha; refs canonical đã explicit | type=string; format=date; type=null | retained preview DeclarationSource; chưa canonical completeness/capacity/limit tables  Không shared; column/binding hiện hành |
| `declaration.ProcurementDeclaration.committed_inbound_state` — Hàng đang về đã cam kết | required | JSON trong cột cha; refs canonical đã explicit | type=string; enum=['CONFIRMED_NONE', 'PRESENT_UNSUPPORTED', 'UNKNOWN'] | retained preview DeclarationSource; chưa canonical completeness/capacity/limit tables  Không shared; column/binding hiện hành |
| `declaration.ProcurementDeclaration.no_additional_orders_state` — Lệnh mua bổ sung | required | JSON trong cột cha; refs canonical đã explicit | type=string; enum=['CONFIRMED_NONE', 'UNKNOWN'] | retained preview DeclarationSource; chưa canonical completeness/capacity/limit tables  Không shared; column/binding hiện hành |
| `declaration.ProcurementDeclaration.capacity_state` — Trạng thái sức chứa | required | JSON trong cột cha; refs canonical đã explicit | type=string; enum=['DECLARED', 'EXPLICIT_NOT_CONFIGURED', 'UNKNOWN'] | retained preview DeclarationSource; chưa canonical completeness/capacity/limit tables  Không shared; column/binding hiện hành |
| `declaration.ProcurementDeclaration.capacities` — Sức chứa theo nguyên liệu | required | JSON trong cột cha; refs canonical đã explicit | type=array; items: Capacity | retained preview DeclarationSource; chưa canonical completeness/capacity/limit tables  Không shared; column/binding hiện hành |
| `declaration.ProcurementDeclaration.capacities[].ingredient_id` — Nguyên liệu đã nối | required | JSON trong cột cha; refs canonical đã explicit | type=string; format=uuid | retained preview DeclarationSource; chưa canonical completeness/capacity/limit tables  Không shared; column/binding hiện hành |
| `declaration.ProcurementDeclaration.capacities[].unit` — Đơn vị exact | required | JSON trong cột cha; refs canonical đã explicit | type=string | retained preview DeclarationSource; chưa canonical completeness/capacity/limit tables  Không shared; column/binding hiện hành |
| `declaration.ProcurementDeclaration.capacities[].maximum_quantity` — Số lượng tối đa | required | JSON trong cột cha; refs canonical đã explicit | type=string; pattern=^(0&#124;[1-9][0-9]*)(\.[0-9]+)?$; maxLength=200 | retained preview DeclarationSource; chưa canonical completeness/capacity/limit tables  Không shared; column/binding hiện hành |
| `declaration.ProcurementDeclaration.capacities[].checkpoint` — Thời điểm kiểm sức chứa | required | JSON trong cột cha; refs canonical đã explicit | type=string; const=POST_RECEIPT_PRE_EXPIRY_PRE_CONSUMPTION | retained preview DeclarationSource; chưa canonical completeness/capacity/limit tables  Không shared; column/binding hiện hành |
| `declaration.ProcurementDeclaration.supplier_limit_state` — Trạng thái trần nhà cung cấp | required | JSON trong cột cha; refs canonical đã explicit | type=string; enum=['DECLARED', 'EXPLICIT_NOT_CONFIGURED', 'UNKNOWN'] | retained preview DeclarationSource; chưa canonical completeness/capacity/limit tables  Không shared; column/binding hiện hành |
| `declaration.ProcurementDeclaration.supplier_limits` — Trần theo nhà cung cấp/nguyên liệu | required | JSON trong cột cha; refs canonical đã explicit | type=array; items: SupplierLimit | retained preview DeclarationSource; chưa canonical completeness/capacity/limit tables  Không shared; column/binding hiện hành |
| `declaration.ProcurementDeclaration.supplier_limits[].supplier_id` — Nhà cung cấp đã nối | required | JSON trong cột cha; refs canonical đã explicit | type=string; format=uuid | retained preview DeclarationSource; chưa canonical completeness/capacity/limit tables  Không shared; column/binding hiện hành |
| `declaration.ProcurementDeclaration.supplier_limits[].ingredient_id` — Nguyên liệu đã nối | required | JSON trong cột cha; refs canonical đã explicit | type=string; format=uuid | retained preview DeclarationSource; chưa canonical completeness/capacity/limit tables  Không shared; column/binding hiện hành |
| `declaration.ProcurementDeclaration.supplier_limits[].unit` — Đơn vị exact | required | JSON trong cột cha; refs canonical đã explicit | type=string | retained preview DeclarationSource; chưa canonical completeness/capacity/limit tables  Không shared; column/binding hiện hành |
| `declaration.ProcurementDeclaration.supplier_limits[].maximum_quantity` — Số lượng tối đa | required | JSON trong cột cha; refs canonical đã explicit | type=string; pattern=^(0&#124;[1-9][0-9]*)(\.[0-9]+)?$; maxLength=200 | retained preview DeclarationSource; chưa canonical completeness/capacity/limit tables  Không shared; column/binding hiện hành |
| `declaration.ProcurementDeclaration.supplier_limits[].scope` — Phạm vi giới hạn | required | JSON trong cột cha; refs canonical đã explicit | type=string; const=ONE_ORDER_SUPPLIER_INGREDIENT | retained preview DeclarationSource; chưa canonical completeness/capacity/limit tables  Không shared; column/binding hiện hành |
| `declaration.ProcurementDeclaration.evidence_reference` — Bằng chứng | required | JSON trong cột cha; refs canonical đã explicit | type=string; minLength=1; maxLength=1000 | retained preview DeclarationSource; chưa canonical completeness/capacity/limit tables  Không shared; column/binding hiện hành |

## Metadata ngoài cột Excel

| Giá trị | Nguồn / validation / đích |
| --- | --- |
| Store, actor, grants | Trusted session + current Store membership; server-owned, không tin file/payload ownership. |
| file/sheet/source row/index/digest | Parser/staging assigns; giữ physical provenance, không model tạo. |
| source_system_key/report_type | M04 SourceContext USER_DECLARED ổn định Store; Owner duyệt profile; không suy filename. |
| sales_semantics/inventory_semantics | SourceContext approved: daily_total/disjoint_contribution, lot_stock_count; không đổi thành receipt. |
| decimal_locale/date_format/pack_cost_basis | Approved parsing/normalization context; không tự đoán locale/unit price basis. |
| profile/version/identity/conversion | Immutable approved profile pins; IDs/version backend; exact rational conversion cần evidence, không tự kg↔g. |
| Store timezone/currency/now | Authorized detached read-set/server context cho validation; không tự thay missing row currency/date. |
| preview/review confirmation | Backend retained IDs/digests/revisions/audit, không mutable confirmed flag tùy ý. |

Tổng 111 dòng field (bao gồm discriminator và nested structured values). Nested declaration/fee hiện nhận JSON trong cột cha, chưa flatten-column UI hoặc automatic nested token binding.

## Đối chiếu legacy và nhu cầu đã duyệt

| Legacy / nhu cầu | Phân loại | Capability hiện hành / gap / dependency |
| --- | --- | --- |
| sales_history | Chỉ nhãn/descriptors/mapping | sales observed Product/day, không copy legacy cộng dồn/correction/defaults. Canonical adapter S4.5. |
| recipes | Chỉ nhãn/descriptors/mapping | dated recipes yield/loss/exact units; grouping có preview; canonical adapter S4.5, timeline S4.7. |
| menu | Một phần nhãn; phần khác mới/chưa duyệt | products metadata hiện có; combo/item_type/variant rules legacy không tự port. |
| supplier_constraints | Một phần nhãn; gap persistence đã có contract | supplier_terms + approved pack-cost/conversion; capacity/limits tagged declaration preview; writers S4.6. Không đồng nghĩa lịch sử mua. |
| business_constraints | Một phần contract, không parity registry | chỉ scope_declarations tagged kinds đã hỗ trợ; không generic arbitrary constraint engine. Persistence S4.6; kinds khác OPEN. |
| inventory snapshot của legacy | Không tương đương đầy đủ | inventory_count chỉ count **lô existing**, không legacy tạo opening lot từ snapshot/batch_id. |
| Opening stock | N6 public writer đã có, chưa dedicated Import schema | N6 OPENING_STOCK tạo lot số còn hiện tại + COUNT_CORRECTION từ0; date unknown giữnull. S4.6; nếu cần Excel intake, freeze dedicated schema/mapping nối N6 ở S4.6, không thêm trong lát này. |
| Actual goods receipts | N6 public lifecycle đã có; chưa dedicated Import schema | N6 ACTUAL_RECEIPT: lô thực nhận + RECEIPT. N6 có identity/actor/CAS/HTTP; internal receive giữ standalone ownership. S4.6; optional Excel intake cần thiết kế riêng đã freeze, không map inventory_count. |
| purchase_history | Capability mới/chưa duyệt | Legacy có purchase_receipts, không thay đổi kho. Hiện không source model/table/writer/contract tương ứng; OPEN authorization trước khi định slice. Không dùng supplier_terms/receipt/count thay thế. |
| usage_history | Capability Import mới/chưa duyệt | Internal movement USAGE có storage sign, không usage importer. Không port waste/usage auto facts. |
| calendar_features | Capability Import mới/chưa duyệt | Forecast temporal features không là source calendar importer; không thêm schema vì parity. |
| unknown | Unsupported/review | Không source schema mới; manual choose supported type hoặc acknowledged ignore. Không zero-row fake success. |

Nguồn evidence: `LEGACY_IMPORT_MAPPING_REPORT.md:43` registry, `:303` opening và `:304` purchase separation; approved `docs/INVENTORY_API_CONTRACT_VI.md:152` N6; `docs/IMPORT_MAPPING_API_CONTRACT_VI.md:343` lot_stock_count. Legacy ZIP chỉ evidence, không authority.

## Gaps có kế hoạch / OPEN

- S4.5: atomic catalog/sales/recipe adapters, source identity/provenance, corrections, retained review/read-set revalidation; không claim writers hiện đã được orchestrate. Bounded scalar shared bindings đã có trong staging; canonical adapter phải dùng exact retained declarations/rules + cùng typed row authority. Generic/nested binding chưa triển khai.
- S4.6: N6 opening/actual receipt lifecycle + source identity/CAS/current actor/idempotent audit; count public mutations/threshold, supplier core/fee/declaration canonical storage. Intake Excel opening/receipt nếu được yêu cầu phải dedicated semantics, không inventory_count aliases.
- OPEN: purchase-history import, usage/calendar/combo/mixed-table schemas; không tự ACCEPT parity. Nested bindings/flatten JSON UI và arbitrary row context constants ngoài allowlist chưa có runtime; đề xuất nhỏ riêng trước consumer có nhu cầu.
- Unsupported M03: tax_percent/free_over_threshold/tiers/payment_terms không writer/source schema; không silently ignore thành readiness.

Không migrate/test development DB; không thay S1/S2/S3, lượt khảo sát/descriptors lịch sử không implement S4.5/S4.6; current consumers xem feature S4.6.
