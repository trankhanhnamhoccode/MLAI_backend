# Bàn giao hệ thống import ShelfCash cũ cho ShelfCash mới

Audit tĩnh source ngày 2026-10-13. Chỉ đọc code và tạo tài liệu này; không chạy ứng dụng, tests, model, migration, truy cập DB, cài dependencies hay tạo ZIP. “Có implementation” dưới đây là kết luận từ đường gọi trong source, không phải chứng nhận dữ liệu thực tế hoặc kết quả chạy. Các đường dẫn tính từ root repository. Bản mới cần thiết kế contract theo nhu cầu nghiệp vụ, không coi canonical registry cũ là chuẩn bắt buộc.

## 1. Bảng tổng quan nhóm dữ liệu và mức hỗ trợ

Registry thực sự: `app/core/canonical_schemas.py::CANONICAL_SCHEMAS`, gồm 9 loại có dữ liệu và `unknown`. `app/schemas/llm.py::SheetType` dùng cùng danh sách; `app/schemas/canonical.py::CanonicalResult` chỉ chứa các list `dict[str, Any]`, không phải typed row schema đầy đủ.

Trong bảng, “Qwen: có” nghĩa là loại/fields nằm trong toàn bộ registry được gửi **nếu model được gọi**, không có nghĩa mọi upload đều gọi Qwen. API catalog không tự trở thành schema import.

| Nhóm / type thật | Qwen | Bảng/model ghi chính (`app/models/business.py`) | Consumer và mức hỗ trợ |
|---|---|---|---|
| Menu/Product: `menu` | Có | `products` / `ProductModel`, `product_bundle_lines` / `ProductBundleLineModel` | Menu/UI, identity sales/recipe; giá product được Decision dùng cho shortage economics. **Dùng một phần**: singles có consumer thật, combo có graph/UI và usage reconstruction, nhưng BOM planning không tự expand graph combo. |
| Ingredient master | Không có type riêng | `ingredients` / `IngredientModel` tạo gián tiếp; `ingredient_aliases` dùng qua API catalog | BOM, tồn kho, supplier, UI. **Dùng một phần**: không có sheet ingredient/alias/SKU master; identity và base unit phụ thuộc file tạo trước hoặc API. |
| Sales: `sales_history` | Có | `sales_daily` / `SalesDailyModel` | Forecast sản phẩm, usage reconstruction, UI history. **Dùng một phần**: lượng/ngày/stockout thật; unit nguồn và revenue không persist; tên promotion bị rút thành bool. |
| Recipe/yield/effectivity: `recipes` | Có; không có loss fields | `recipe_versions`, `recipe_lines` | Core BOM, operational planning, UI. **Dùng một phần**: quantity/yield/version/effectivity có consumer; import không nhận process loss/waste allowance. |
| Inventory/lot/kiểm kê: `inventory` | Có | `inventory_lots`, `inventory_movements` | Balance, FEFO simulation, procurement, UI. **Dùng thực sự** đối với snapshot/lot; không phải ledger giao dịch đầy đủ; còn giới hạn metadata, unknown dates/expiry. |
| Purchase: `purchase_history` | Có | `purchase_receipts` / `PurchaseReceiptModel` | UI history. **Chỉ lưu nghiệp vụ** (`inventory_effect=record_only`), không tạo lot/movement, không làm inbound và không học supplier price/lead time từ lịch sử. |
| Supplier terms: `supplier_constraints` | Có | `suppliers`, `supplier_ingredient_terms` | Operational planner và Core Decision offers: pack/MOQ/price/lead/schedule/expiry. **Dùng một phần**, giá không đổi theo unit và không có phí giao hàng. |
| Usage: `usage_history` | Có | `usage_daily` / `UsageDailyModel` | UI history; observed usage được bảo vệ khi reconcile từ sales. **Chỉ lưu** đối với forecast/BOM/procurement: không làm target forecast nguyên liệu, không trừ inventory. |
| Stockout | Chỉ `sales_history.is_stockout` | `sales_daily.is_stockout` nullable | Forecast censor/reconstruction/rolling features. **Dùng một phần**: không có stockout event sheet hoặc thời lượng/lost sales. Stockout inventory/UI và projected stockout là giá trị tính, không phải cùng observation. |
| Calendar/promotion: `calendar_features` | Có | `calendar_features` / `CalendarFeatureModel` | Forecast dùng holiday/closed/weather/ngày; UI dùng promotion. **Dùng một phần**: promotion không nằm trong model features hiện tại. |
| Business constraints: `business_constraints` | Có fields chung, không gửi registry từng constraint type | `inventory_constraints` / `InventoryConstraintModel` | Operational planner dùng nhiều loại; Core Decision chỉ truyền một phần. **Dùng một phần**, chi tiết ở mục 2.8/3.3. |
| Budget/config | Gián tiếp qua `business_constraints`; không có type riêng | `store_settings`; `budget` vào `inventory_constraints`; không import `budget_periods` | BudgetResolver, settings/bootstrap/UI; monthly setting là fallback. **Dùng một phần**: `default_strategy` không đi được qua normalizer numeric; request horizon khác settings horizon. |
| Delivery fees / business notes tự do | Không có fees/free-note type | `note` chỉ lưu trên inventory constraint có cấu trúc | **Chưa hỗ trợ** fees và free-form business notes; note không có consumer planner/LLM import hiểu thành điều kiện. |

Phân biệt hai consumer planning đang có trong repository:

- **Operational procurement**: `app/services/decision/operational_procurement_lifecycle.py::OperationalProcurementLifecycle.generate` gọi `ProcurementPlanningService.build` (`app/services/procurement_planning_service.py`).
- **Decision Core**: `app/services/decision_planning_service.py::DecisionPlanningService.generate_decision` gọi `CoreProcurementAdapter.optimize` (`app/services/decision/adapters/procurement_adapter.py`), rồi `shelfcash_core/optimization/optimizer.py::optimize_procurement`.
- Ingredient Demand hiện dùng `app/services/decision/ingredient_demand_lifecycle.py::IngredientDemandLifecycle.generate` → `CoreBomAdapter.expand`; không được suy rằng class `RecipeBomService` là đường duy nhất đang chạy.

## 2. Field dictionary theo nhóm

### 2.1. Quy ước required, missing, null, zero và đơn vị

`R` = nằm trong `core_fields`, bị `app/core/validator.py::validate_records` kiểm tra khác `None`/`""`. `B` = persistence còn yêu cầu thêm dù registry không đánh dấu required. `O` = tùy chọn. Với mỗi field, kiểu là kiểu thực tế sau normalize hoặc tại nơi persist, không phải một schema JSON typed mà Qwen được cung cấp.

Nguồn quy tắc chung: `app/core/normalizer.py::{normalize_rows,normalize_value,normalize_number,normalize_date}`, `app/core/validator.py::validate_records`, `app/services/business_persistence.py::ImportBusinessPersistenceService.{_decimal,_date}`.

| Trường hợp | Hành vi thực tế |
|---|---|
| Cột không được mapping | Key field không được tạo trong normalized row. Cột source vẫn có trong parsed rows lưu ở profile. |
| Cột được mapping nhưng ô trống | Reader đổi NA/NaN thành `None`; normalized row có key với `None`. Hầu hết persistence dùng `.get()` nên missing và null bị gộp. Không giữ riêng “người dùng muốn xóa”. |
| Ô số/ngày/bool không parse được | Thường thành `None`, không giữ raw value gốc trong canonical. Nếu optional, có thể bị lưu null/default mà không báo lỗi field. Menu enum/unit/status và packaging có đường ném exception; recipe_version cố giữ giá trị sai để báo row issue. |
| `0` | Core validator không xem là missing. `_decimal` nhận 0 trừ field `positive=True`. Nhưng `yield_quantity or 1`, `component_quantity or 1` đổi 0 thành 1. Giá menu yêu cầu >0; giá sales/term/receipt cho phép 0. |
| Numeric | `int/float` ở normalize, chuyển `Decimal` ở persistence; số tiền nhiều nơi `int(...)` nên cắt phần thập phân. `1,234` được đoán là 1234 vì nhóm sau có 3 chữ số; không có locale contract. `_decimal` chung không chủ động kiểm tra finite; business constraint validator riêng có kiểm tra finite. |
| Ngày | Normalize thành ISO date, dùng day-first cho chuỗi không ISO. Giờ bị bỏ. `end_date` **không** nằm trong `DATE_FIELDS`, dù xuất hiện registry; persistence mới parse ISO date. |
| Bool import | true: `true/1/yes/y/co/có/dung/đúng`; false: `false/0/no/n/khong/không/sai`; còn lại null. Alias value `x` có ở adapter forecast nhưng không có ở import normalizer, nên `x` trong file có thể mất trước khi forecast nhận. |
| Physical unit | Normalizer có thể tạo `kilogram/gram/liter/milliliter/piece`; `app/core/units.py::normalize_unit` chuyển về DB `kg/g/lít/ml/cái`. Chỉ convert trong cùng mass/volume/count. Không suy kg↔lít theo density. |
| Thiếu physical unit | Ingredient mới bị chặn; ingredient đã có có thể qua bước lookup. `units.py::validate_compatible` bỏ qua missing dimension, `convert_quantity` trả nguyên số nếu một unit là `None`: không đảm bảo validation chặt. |
| Unit bán / đóng gói | `selling_unit` dùng menu contract `ly/phần/chai/cái/combo`; `order_unit` dùng packaging contract (case/bag/pack/box/crate/bundle hoặc literal). Không phải physical base unit. `unit` sales không cập nhật `selling_unit`. |

### 2.2. Menu/Product và Ingredient

Schema import Menu: `canonical_schemas.py::CANONICAL_SCHEMAS['menu']`; normalize enum ở `app/core/menu.py::{normalize_item_type,normalize_menu_status,normalize_product_unit}`; ghi ở `business_persistence.py::_persist_menu`; UI derive ở `app/services/menu_service.py::MenuService.serialize`.

| Field | Ý nghĩa, kiểu/unit | Required/default và đường ghi |
|---|---|---|
| `product_sku` | String mã món, trim/uppercase | R; identity `(Store, sku)`. SKU khác tên đã gắn → conflict; item_type không được đổi. |
| `item_type` | Enum `single/combo`; aliases values `món lẻ/retail`, `bundle` | R; ô trống được map sẽ lỗi normalize. Product tạo gián tiếp mặc định single. |
| `product_name` | String tên hiển thị, NFC/trim/coalesce spaces, key casefold | R; không có alias table riêng cho product. Menu có logic upgrade legacy product không SKU khi identity duy nhất. |
| `selling_unit` | Enum đơn vị bán `ly/phần/chai/cái/combo` | O theo registry; ô mapped trống lỗi. Single unmapped có thể lưu null; combo B phải `combo`. |
| `selling_price` | Giá một đơn vị bán; numeric → positive Decimal → int, UI currency VND | R và >0; vào `ProductModel.price`. Không có currency field riêng trong Menu. |
| `status` | `active/inactive` (`đang bán/ngừng bán`, enabled/disabled) | O; không mapping → persistence mặc định active; mapped blank/null → normalize ném lỗi, không tới default. |
| `combo_components` | String dạng `2 x Tên món + 1 x Tên khác`; parser tối đa 20 segments | O cho single (phải rỗng); B cho combo nếu không có explicit component. Graph ghi `ProductBundleLineModel`; cấm self, trùng component, component inactive/combo hoặc mơ hồ variant. |
| `component_product_id` | String ID component cùng Store | O; explicit resolution ưu tiên ID. Không tìm thấy bị chặn, không tự tạo component. |
| `component_sku` | String SKU component, uppercase | O; dùng nếu không có ID. |
| `component_product_name` | String tên component | O; dùng nếu không có ID/SKU, lookup exact/base name; tên nhiều variant → lỗi. |
| `component_variant` | String metadata variant gắn vào tên để lookup | O; không có cột riêng trong bundle line. |
| `component_quantity` | Số component trong combo → int | O; missing/null/**0** → 1 (`parse_explicit_component`), fractional bị `int` cắt; giá trị sau đó phải >0. Nhiều dòng cùng SKU có thể gom explicit components nếu header nhất quán. |
| `list_price` | Tổng giá các component; numeric tiền | O; không persist giá nguồn; combo tính lại từ graph. Single serializer dùng giá product. |
| `discount_rate` | Tỷ lệ giảm dạng fraction, numeric | O; combo tính savings/list price; sai lệch >0.005 cảnh báo. Không tự đổi percent string. |
| `savings_amount` | Tiền tiết kiệm, numeric | O; combo tính `max(list_price-price,0)`; chỉ đối chiếu/cảnh báo nguồn. |

Aliases Menu dùng **`MENU_HEADER_MAP` riêng**, không dùng toàn bộ generic aliases: `Mã món→product_sku`, `Loại→item_type`, `Tên món/Combo→product_name`, `Thành phần combo→combo_components`, `ĐVT→selling_unit`, `Tổng giá lẻ→list_price`, `Mức giảm→discount_rate`, `Giá bán→selling_price`, `Tiết kiệm→savings_amount`, `Trạng thái→status` và các explicit component headers. Map này không tự thêm canonical headers: ví dụ `product_sku`, `selling_price`, hoặc header `Tên món` đơn thuần không được rule Menu map như generic mapper; cần Qwen/manual. Xem `app/core/rule_mapper.py::{MENU_HEADER_MAP,menu_mapping_details}`. Manual Menu đòi tất cả cột có target hợp lệ; `null/ignore/__unmapped__` là unresolved, khác các sheet thông thường.

Ingredient không có sheet riêng. Các field gián tiếp là `ingredient_name`, `unit` (inventory/usage/purchase), `ingredient_unit` (recipe), `package_base_unit` (term), `expiry_tracking_mode`. `_ingredient` dùng tên/alias có sẵn hoặc tạo ingredient mới với unit của dòng đầu tiên làm `base_unit`, active/version theo model default. `sku`, `active`, đổi base unit và aliases không được import gián tiếp.

Contract API bổ sung, **không gửi Qwen**: `app/schemas/catalog.py::{IngredientCreate,IngredientPatch,AliasBulkUpsert,AliasUpsertItem}`; `IngredientCreate` yêu cầu `ingredient`, `base_unit`, tùy chọn `sku`, `active=True`, `expiry_tracking_mode=None`; `AliasUpsertItem` yêu cầu `source_name/canonical_name`, `ingredient_id` optional. Ghi/resolve qua `app/services/catalog_service.py::CatalogService` và `app/repositories/business.py::CatalogRepository`.

### 2.3. Sales history và stockout

Nguồn: `CANONICAL_SCHEMAS['sales_history']`, `business_persistence.py::_persist_sales_history`, `models/business.py::SalesDailyModel`, `app/repositories/forecast_data.py::ForecastDataRepository.sales_history`.

| Field | Ý nghĩa, kiểu/unit | Required/default, persistence/consumer |
|---|---|---|
| `date` | Ngày bán, ISO date | R; không tự bù ngày vào DB. |
| `product_name` | String món bán | R; resolve/tạo product không SKU; nhiều products cùng tên → chặn. `product_sku` **không có** trong sales registry. |
| `quantity_sold` | Numeric lượng bán, Decimal ≥0; semantic số đơn vị bán | R; cộng dòng cùng `(date, product, promotion)` trong một sheet, ghi `quantity`. Chấp nhận số lẻ, không validate bằng selling_unit. |
| `unit` | String/normalized unit nguồn | O; canonical giữ, **bảng sales bỏ**. Forecast lấy `ProductModel.selling_unit`, không lấy unit từ file sales. |
| `selling_price` | Numeric giá đơn vị bán → int ≥0 | O, null giữ null; ghi `unit_price`. Cùng aggregate khác price (kể cả null so với có giá) bị chặn; không suy từ revenue, không cập nhật giá Menu. |
| `revenue` | Numeric doanh thu nguồn | O; normalize và lưu result JSON, **không có cột business tương ứng**. Forecast repository dựng lại `quantity * unit_price`, không giữ actual revenue/discount của nguồn. Không đối chiếu ba giá trị. |
| `is_stockout` | Nullable bool quan sát hết hàng | O; all missing/null → DB null; known values → `any` (true thắng false). Mixed unknown+false thành false, mất mức độ unknown. Core forecast dùng censor/reconstruction và rolling stockout counts/rates. |
| `promotion_name` | String tên promotion | O; truthy → `promotion=True`; DB không giữ tên. Forecast trả literal `"promotion"` hoặc null. Hai chương trình khác nhau đều thành cùng key bool. |

Aliases tiêu biểu (`rule_mapper.py::ALIASES`, normalize bỏ dấu/lowercase/underscore): `ngày/ngày gd→date`, `tên món/món bán/sản phẩm→product_name`, `số lượng bán/sl bán/slx→quantity_sold`, `giá bán→selling_price`, `doanh thu→revenue`, `ĐVT/đơn vị→unit`. `is_stockout` và `promotion_name` **không có entry** trong `ALIASES`; ngay cả canonical header của hai field này không được generic `_alias_map` thêm tự động. Cần Qwen/manual cho cột đó. Không có standalone stockout type.

Forecast không dùng price/revenue/promotion làm numeric model features hiện tại: `shelfcash_core/features/specification.py::{NUMERIC_FEATURES,MODEL_FEATURES}`. `selling_price/revenue` đi qua adapter/data contract nhưng không chứng minh tác động model. Stockout có tác động thật: `shelfcash_core/data/demand_reconstruction.py::reconstruct_demand` dùng ngày trước của cùng Store/product, ưu tiên cùng weekday, kiểm tra support/recency/dispersion; estimate ≥ observed sales, chỉ chấp nhận confidence high/medium. Censored không đủ hỗ trợ bị loại khỏi train và lag state. Null stockout dùng observed sales với quality/warning unknown; false khác null.

### 2.4. Recipe, serving/batch, yield, loss, effectivity

Nguồn: `CANONICAL_SCHEMAS['recipes']`, `business_persistence.py::_persist_recipes`, `app/services/recipe_service.py::RecipeVersionService.create_version`, `app/core/recipe_versions.py::normalize_recipe_version`, `app/services/decision/adapters/bom_adapter.py::CoreBomAdapter.recipe_frame`, `shelfcash_core/bom/engine.py::{ingredient_adjustment_factor,propagate_ingredient_demand}`.

| Field | Ý nghĩa, kiểu/unit | Required/default và hạn chế |
|---|---|---|
| `product_sku` | String SKU product | O; SKU + tên phải nhất quán; không tồn tại có thể tạo product. |
| `product_name` | String product | R; nếu thiếu SKU và tên trùng variant thì chặn. |
| `ingredient_name` | String ingredient | R; resolve/create; ingredient mới cần ingredient_unit. |
| `ingredient_quantity` | Numeric >0 lượng nguyên liệu cho **toàn bộ yield của recipe** | R; convert từ ingredient_unit sang base_unit, ghi recipe_lines.quantity; không phải luôn lượng/serving. |
| `ingredient_unit` | Physical unit nguyên liệu | O registry, B cho ingredient mới; missing ở ingredient cũ có thể đi qua convert không đổi số. |
| `yield_quantity` | Numeric số đơn vị thành phẩm recipe tạo ra | O; `row.get(...) or 1`: missing/null/**0** thành 1. Sau fallback phải >0. Ghi version. |
| `yield_unit` | String đơn vị đầu ra, có unit normalization chung | O; lưu nullable, không validate tương thích lúc import. Core adapter dùng `yield_unit or 'unit'`, forecast unit được adapter cố định `None`; engine giữ nguyên forecast numbers và dùng yield unit làm working unit, báo PRODUCT_UNIT_MISSING, không xác nhận conversion đơn vị bán. |
| `recipe_version` | Positive integer, có thể input `v1`... | O; blank/null → code cấp next sequential version; requested phải bằng next, trừ content đã có được trả về trước bước check requested_version. |
| `effective_date` | ISO date bắt đầu recipe | O; suy từ `job.forecast_date`, nếu thiếu thì `job.created_at.date()` (không chuyển Store timezone). Group theo product/effective. |
| `process_loss_rate` | Model/API recipe có Decimal rate [0,1), default 0 | **Không có trong import registry**, normalizer không nhận như target, importer không truyền → 0. Consumer BOM có đọc nếu được tạo ngoài import. |
| `waste_allowance_rate` | Core BOM rate ≥0 | **Không có import field/model recipe tương ứng**; CoreBomAdapter luôn truyền 0. Không dùng `usage_history.waste_quantity` làm rate này. |
| `effective_to` | Model date kết thúc version | **Không có import target**; service đóng version trước ở ngày trước effective mới. |

Aliases: `định lượng/lượng 1 sp→ingredient_quantity`, `đơn vị nguyên liệu→ingredient_unit`, `sản lượng/yield→yield_quantity`, `đơn vị sp→yield_unit`, `phiên bản công thức→recipe_version`, `ngày hiệu lực/bắt đầu/áp dụng từ→effective_date`, `mã món→product_sku`. Key `recipe_version` bị khai báo hai lần trong ALIASES; entry sau ghi đè, alias `ver` của entry trước không còn tác dụng.

Các line cùng product/effective phải đồng ý yield/unit/version; ingredient trùng trong recipe bị chặn, không cộng line. Version theo content hash, cấm overlap/backdate, đóng effective_to trước. Import không truyền `source_import_id/source_profile_id` vào `RecipeVersionService`, dù model có hai cột này: provenance recipe không đầy đủ như term/receipt.

Semantics BOM là `forecast_count * ingredient_quantity / yield_quantity * (1+process_loss_rate) * (1+waste_allowance_rate)`. Đây là allowance multiplier của code, không mặc định là công thức hao hụt vật lý `1/(1-loss)`. Usage reconstruction cũ dùng `sales_quantity * recipe_line.quantity`, **không chia yield, không nhân loss**, nên không được lấy observed/derived usage lẫn lộn làm chứng cứ BOM đúng.

### 2.5. Inventory, lot và ngày kiểm kê

Nguồn: `CANONICAL_SCHEMAS['inventory']`, `business_persistence.py::_persist_inventory`, `app/core/business_time.py::{local_business_date,snapshot_eod_boundary}`, `InventoryRepository.calculate_lot_balance`.

| Field | Ý nghĩa, kiểu/unit | Required/default và ghi |
|---|---|---|
| `snapshot_date` | Ngày kiểm kê cuối ngày theo Store | R; ghi lot.snapshot_date và boundary EOD cho movement; ngày tương lai bị chặn. Không dùng thay received_date. |
| `ingredient_name` | String nguyên liệu | R; identity theo Store + tên/alias. |
| `batch_id` | String batch code, strip, giữ case | R; identity lot Store/ingredient/batch, không có unique DB đúng bộ này, importer truy vấn và chặn ambiguity. Trùng batch/date trong sheet hoặc sau alias resolution bị chặn. |
| `on_hand` | Numeric ≥0 lượng **đếm được**, theo unit nguồn | R; convert về base unit; tạo opening_balance hoặc delta so với balance hiện tại, không cộng nguyên lượng như receipt. |
| `unit` | Physical unit | R; base unit ingredient mới theo dòng đầu. Metadata unit của lot đã có được so sánh bất biến, không chỉ kiểm tra compatible. |
| `received_date` | Ngày thực nhận hàng, ISO date | O; missing/null → null với `received_date_status='unknown'`, có giá trị → declared. Không suy từ snapshot/ngày upload. |
| `expiry_date` | Hạn dùng, ISO date | O; null không có nghĩa not_required; DB check expiry ≥ received nếu cả hai có. Không chặn mọi missing expiry ở import, có recompute/warnings. |
| `expiry_tracking_mode` | String `required/not_required/unknown` | O; **ghi Ingredient metadata**, không lot. Missing không declare; recompute có thể infer. |
| `supplier_name` | String nhà cung cấp | O; có thì resolve/create supplier, ghi supplier_id trên lot; thiếu → null. Reimport null so với supplier hiện hữu có thể conflict. |
| `warehouse_name` | String vị trí/kho | O; ghi lot.warehouse_name; metadata kiểm tra conflict. FEFO/planning không phân bổ capacity theo warehouse này. |

Aliases: `ngày kiểm kê→snapshot_date`, `ngày nhập kho/ngày nhận hàng/ngày về kho/receipt date→received_date`, `tồn kho/sl cuối ngày/số lượng tồn→on_hand`, `mã lô/batch/lot code→batch_id`, `HSD/hạn dùng→expiry_date`, `vị trí/warehouse/location→warehouse_name`.

Snapshot cũ hơn movement của ingredient ở business date sau snapshot bị chặn; movement cùng ngày tương thích EOD. Snapshot khác import cùng batch/date bị chặn khi đã có snapshot movement ngày đó. Khi count không tạo delta, không có movement marker mới: không nên hứa chống trùng mọi snapshot tuyệt đối. Quantity 0 là kiểm kê thật, có thể tạo lot nhưng không opening movement. Existing lot metadata gồm supplier/received/expiry/warehouse/unit phải khớp, không coi missing là “giữ nguyên”. Lot mới lưu unit base; snapshot sau dùng compatible unit khác base vẫn có thể conflict do so metadata (ví dụ lot kg nhưng gửi g).

`app/services/ingredient_expiry.py::IngredientExpiryClassificationService.recompute`: evidence lot expiry hoặc active term shelf_life → infer required; tên vật liệu bao bì trong allowlist và tỷ lệ không-expiry ≤0.5 → có thể infer not_required; còn lại unknown. Declaration được giữ. Purchase receipt expiry không được recompute đọc như evidence. Unknown expiry không phải tự có ngày hết hạn; Core Decision dùng policy `unknown_expiry='warn_and_place_last'`.

### 2.6. Purchase history

Nguồn: `CANONICAL_SCHEMAS['purchase_history']`, `business_persistence.py::_persist_purchase_history`, `app/core/provenance.py::purchase_receipt_identity`, `PurchaseReceiptModel`.

| Field | Ý nghĩa, kiểu/unit | Required/default và ghi |
|---|---|---|
| `purchase_date` | Ngày mua/hóa đơn, ISO date | O riêng lẻ; B phải có purchase_date hoặc received_date. Chỉ làm fallback receipt_date, **không lưu riêng ngày mua**. |
| `received_date` | Ngày nhận thực tế, ISO date | O riêng lẻ; ưu tiên ghi receipt_date, không đối chiếu purchase_date. |
| `ingredient_name` | String ingredient | R; resolve/create. |
| `quantity_received` | Numeric ≥0 lượng nhận theo unit | R; convert sang ingredient.base_unit; không tạo inventory movement. |
| `unit` | Physical quantity unit | O registry, B cho ingredient mới; null với existing có conversion permissive. Không nhận pack như physical unit. |
| `unit_price` | Numeric giá đơn vị → int ≥0, ghi unit_cost | O → null; giữ nguyên số khi quantity/unit được convert. Không biết giá theo pack/quantity nguồn; không tự chia pack, không rescale kg/g. |
| `total_cost` | Numeric tiền tổng → Decimal ≥0 | O → null; lưu riêng, không validate `quantity * unit_cost`, không tham gia duplicate hash. |
| `supplier_name` | String supplier | O → supplier_id null nếu thiếu; có thì tạo supplier, không tạo term. |
| `expiry_date` | ISO date | O → null; DB check ≥ receipt_date; không tăng tồn hay infer expiry ingredient bằng receipt evidence. |
| `expiry_tracking_mode` | Enum string | O; `_ingredient` declare ở ingredient, không phải receipt classification riêng. |
| `batch_id` | String batch code | O → null; lưu receipt.batch_code; không liên kết tự động với lot cùng tên. |
| `purchase_order_id` | String tham chiếu PO nguồn | O; lưu text, không resolve/apply PO, khác `po_id/po_line_id` ở operational receipt. |
| `source` | Enum `supplier_invoice/manual/integration` | O → `supplier_invoice`; model source nghiệp vụ, không phải chỉ nhãn provenance `import`. |
| `external_record_id` | String ID ngoài, trim, giữ case | O; dùng identity `(Store, source, external_record_id)` khi có. Không tự tách invoice thành line IDs. |

Aliases: `ngày nhập/nct→purchase_date` (có nguy cơ ngày nhập thực nhận bị gọi là ngày mua); `ngày nhận hàng/ngày nhập kho→received_date`; `số lượng nhập/sl nhập/sln→quantity_received`; `đơn giá/giá mua→unit_price`; `thành tiền→total_cost`; `nhà cung cấp/vendor→supplier_name`; `mã hóa đơn/số hóa đơn/invoice id→external_record_id`; `nguồn nghiệp vụ→source`. `purchase_order_id` không có generic alias entry, cần Qwen/manual.

Không được port việc một `invoice id` được dùng làm identity cho toàn receipt: nhiều nguyên liệu cùng hóa đơn và cùng source sẽ bị skip sau dòng đầu. Import có external ID trùng nhưng nội dung khác cũng skip, không báo conflict. Fallback business hash gồm receipt day, ingredient/supplier, quantity/unit/cost, expiry/batch, **không gồm source, total_cost, purchase_order_id**; giao dịch thật giống hệt có thể bị gộp, sửa cost/quantity thành bản ghi mới thay vì sửa.

### 2.7. Supplier terms, pack, MOQ, lead time, expiry, phí

Nguồn: `CANONICAL_SCHEMAS['supplier_constraints']`, `business_persistence.py::{_persist_supplier_constraints,normalize_delivery_days}`, `app/core/packaging_units.py`, `SupplierIngredientTermModel`.

| Field | Ý nghĩa, kiểu/unit | Required/default và ghi |
|---|---|---|
| `supplier_name` | String supplier | R; resolve/create, không có supplier alias table. |
| `ingredient_name` | String ingredient | R; resolve/create với package_base_unit. |
| `minimum_order_quantity` | Decimal >0 **số pack/order_unit** ở file | R; ghi `moq = minimum_packages * converted_package_size`, tức physical base quantity. Không yêu cầu integer pack count. |
| `order_unit` | String packaging, aliases thùng→case, bao→bag, gói→pack, hộp→box, két→crate, bó→bundle | R; literal không biết vẫn giữ normalized và warning. Không dùng làm physical conversion. |
| `package_size` | Decimal >0 lượng physical **trong một pack** | R; convert về base_unit, ghi pack_size. |
| `package_base_unit` | Physical unit cho package_size | R; phải compatible ingredient.base_unit; chủ động chặn missing ở term. |
| `unit_price` | Numeric ≥0 → int → unit_cost | O registry nhưng **B**; planner tính `order_quantity_in_term_unit * unit_cost`. Vì vậy semantics consumer là giá/physical term.unit, không phải giá/pack; importer không convert giá. |
| `lead_time_days` | Numeric ≥0 → int số ngày | O registry nhưng **B**; fractional bị cắt, không validate integer trước int. Zero cho giao cùng ngày. |
| `shelf_life_days` | Non-negative integer ngày hạn dùng | O; missing/null → null, zero được giữ. Không normalize numeric generic (parse ở persist); Core inbound expiry resolver đọc, không tự lấy expiry từ lịch sử mua. |
| `expiry_tracking_mode` | Enum string | O; declare Ingredient. Hash term không chứa mode này; declaration vẫn có thể thay đổi khi term content skip. |
| `available_delivery_days` | List hoặc chuỗi phân cách dấu phẩy/chấm phẩy; ngày 0..6, Mon=0 | O; null/blank → không hạn chế lịch; explicit list `[]` → không giao được. Parse English/Vietnamese thứ 2..CN, dedup/sort, lưu JSON text. |
| Delivery fee/minimum order value/tax/discount tier | Không có target | **Chưa hỗ trợ import/persistence/offer adapter**. Không suy fee=0 là đã hỗ trợ. |

Aliases: `MOQ/số lượng đặt tối thiểu`, `order uom/đơn vị đặt hàng`, `pack size/quy cách đóng gói`, `base uom/đơn vị cơ sở`, `thời gian giao/lead time`, `số ngày hạn sử dụng`, `lịch giao/delivery schedule`. Unknown packaging chỉ warning, còn physical unit không hỗ trợ bị lỗi.

Term content hash gồm cost/moq/pack/lead/shelf_life/unit/order_unit/schedule. Cùng content latest → skip; khác → inactive bản trước, tạo version kế tiếp. Không có effective date term trong import: planner chỉ lấy active terms hiện tại, không reconstruct terms lịch sử theo cutoff. Cần tách giá/pack với giá/base unit ở bản mới và convert giá nghịch chiều quantity khi đổi unit.

### 2.8. Usage, calendar và business constraints/config

Usage: `CANONICAL_SCHEMAS['usage_history']`, `_persist_usage_history`, `UsageDailyModel`.

| Field | Ý nghĩa, kiểu/unit | Required/default và đường ghi |
|---|---|---|
| `date` | ISO ngày tiêu thụ | R; không bù ngày thiếu. |
| `ingredient_name` | String ingredient | R; resolve/create. |
| `quantity_used` | Numeric ≥0 lượng dùng theo unit nguồn | R; convert base, cộng trong sheet theo ngày/ingredient, overwrite natural key hiện hữu. |
| `unit` | Physical unit | O registry, B cho ingredient mới; permissive missing với existing. |
| `source` | String nguồn sử dụng nghiệp vụ | O; gom các string khác nhau bằng dấu phẩy vào usage_source; model.source luôn `import`. |
| `waste_quantity` | Numeric ≥0 lượng waste theo cùng unit | O; missing/null → **0** qua defaultdict; cộng/convert; không kiểm tra waste ≤ quantity_used, không trừ inventory. |

Aliases: `lượng dùng/lượng thực dùng/số lượng sử dụng→quantity_used`, `hao hụt→waste_quantity`, `nguồn nghiệp vụ→source`. Không có recipe loss rate sheet. UI đọc bằng `app/services/operational_service.py::OperationalService.history('usage',...)`; forecast production chỉ tải sales/calendar, planner đọc demand BOM, không query usage làm nhu cầu.

Calendar: `CANONICAL_SCHEMAS['calendar_features']`, `_persist_calendar_features`, `CalendarFeatureModel`, `ForecastDataRepository.calendar_features`.

| Field | Ý nghĩa, kiểu/unit | Required/default và consumer |
|---|---|---|
| `date` | ISO ngày lịch | R; natural key Store/date. |
| `is_weekend` | Bool weekend nguồn | O; normalize nhưng **bỏ giá trị nguồn**, ghi `day.weekday()>=5`; forecast cũng derive weekend từ target_date. |
| `is_holiday` | Bool ngày lễ | O; missing/null/invalid bool → false qua bool(); forecast future feature/UI đọc. |
| `is_store_closed` | Bool đóng cửa | O; missing/null → false; ảnh hưởng missing sales/training/future target. |
| `is_promotion` | Bool promotion ngày | O; missing/null → false; **không tự bật từ promotion_name**, khác sales. Lưu/UI đọc, không model feature hiện tại. |
| `promotion_name` | String tên promotion | O → null; ghi DB, UI trả promotion_note khi is_promotion true. Không có generic mapping alias entry. |
| `temperature` | Numeric nhiệt độ | O → null; ghi Numeric(10,3), forecast future feature đọc; không quy định/validate °C hay °F ở import. |
| `rainfall` | Numeric lượng mưa | O → null; ghi Numeric(12,3), forecast feature đọc; không quy định/validate mm hoặc khoảng giá trị ở import. |

Aliases: `ngày→date`, `cuối tuần→is_weekend`, `ngày lễ→is_holiday`, `đóng cửa→is_store_closed`, `promo/khuyến mãi→is_promotion`, `nhiệt độ→temperature`, `lượng mưa→rainfall`. Missing calendar dates được forecast xử lý mặc định, không persist zero sales. `known_at` mà forecast repository xuất là `CalendarFeatureModel.created_at`; reimport đổi row không đổi created_at, nên không phải thời điểm biết từng feature version. Ngoài ra `shelfcash_core/data/adapter.py::adapt_calendar` không giữ known_at trong frame returned. Không được cam kết point-in-time safety của future weather chỉ vì có known_at ở repository.

Business constraints envelope: `CANONICAL_SCHEMAS['business_constraints']`, `app/core/business_constraints.py::{CONSTRAINT_DEFINITIONS,validate_and_normalize_business_constraint}`, `_persist_business_constraints`.

| Field | Ý nghĩa, kiểu/unit | Required/default và ghi |
|---|---|---|
| `constraint_type` | String normalize aliases thành canonical kind | R; không chấp nhận free text tùy ý; unsupported kind lỗi persistence. `store_closed_date` bị process chặn riêng, hướng sang calendar. |
| `ingredient_name` | String ingredient target | O envelope, B tùy kind; chỉ resolve existing tên/alias, **không tạo ingredient**. Store-scoped kind không dùng tên này để đổi scope. |
| `value` | Numeric → Decimal ≥0; ratio/duration có validator riêng | R; normalizer luôn numeric, kể cả kind có ý định value string. |
| `unit` | String unit quantity/capacity/duration/ratio/currency | O envelope, B tùy kind; physical normalized, duration day, ratio/percent → ratio, currency VND. Giá trị quantity giữ unit nguồn compatible, resolver mới convert khi đọc. |
| `currency` | String currency | O; fallback khi unit falsy, persist currency cho currency dimension. Generic ALIASES không có entry currency. Unit ưu tiên trước currency. |
| `effective_date` | ISO ngày hiệu lực | O registry nhưng B cho inventory constraint; không tự default ở handler. |
| `end_date` | ISO ngày kết thúc | O → null; end ≥ effective; không qua normalize_date, non-ISO nguồn có thể lỗi persist. |
| `note` | String ghi chú | O → null; ghi InventoryConstraintModel.note (String(500)); hash/version có tính note, không interpret thành rule. |

Aliases envelope: `loại ràng buộc/loại điều kiện/business rule→constraint_type`, `giá trị→value`, `áp dụng cho NL→ingredient_name`, `ngày hiệu lực/áp dụng từ→effective_date`, `ngày kết thúc/áp dụng đến→end_date`, `ghi chú/description→note`. Normalizer unit và constraint unit validator khác nhau; phải trace tới validator kind mới biết unit được chấp nhận.

| `constraint_type` thật và aliases chính | Scope / value / unit | Consumer thực tế |
|---|---|---|
| `safety_stock` (`safety stock`) | Ingredient; ≥0 compatible physical unit | Operational: target ending, thiếu → 0 với warning; **Core Decision không truyền**. |
| `maximum_stock` (`max_stock`) | Ingredient; ≥0 physical | Operational cap nhu cầu trước rounding; Core Decision capacity_quantity ở checkpoint sau receipt/trước expiry/consumption. |
| `minimum_stock` (`min_stock`) | Ingredient; ≥0 physical | Operational target `max(safety,minimum)`; Core Decision không truyền. |
| `reorder_point` (`reorder point`) | Ingredient; ≥0 physical | Operational trigger/reasons/required-by date, không tự tạo lượng nếu raw need=0; Core Decision không truyền. |
| `shelf_life_target` (`shelf_life`) | Ingredient; positive integer day | Operational window/overbuy adjustment; khác exact supplier shelf_life_days; Core Decision không truyền target này. |
| `service_level_target` (`service_level`) | Store hoặc ingredient; [0,1] ratio, percent chia 100 | Operational so achieved fill rate với target (ingredient ưu tiên Store); Core Decision không truyền configured target. |
| `maximum_storage_volume` (`max_storage_volume`) | Store; ≥0 volume lít/ml | Resolver ưu tiên 1; Operational đánh giá nếu dimensions compatible; Core Decision lưu context **not_evaluated** vì thiếu storage volume metadata. |
| `storage_capacity` | Store; ≥0 physical | Resolver ưu tiên 2; cùng giới hạn storage như trên. |
| `warehouse_capacity` | Store; ≥0 physical | Resolver ưu tiên 3; không target warehouse_name cụ thể; cùng giới hạn storage. |
| `budget` (`store_budget`) | Store; ≥0 VND; planner yêu cầu integer | BudgetResolver đọc cả hai đường; explicit 0 là cap 0. |
| `monthly_budget` | Store setting int ≥0 tiền | Handler special case, ghi store_settings; không ghi constraint hay budget_period. Zero settings được BudgetResolver coi không cấu hình, khác budget constraint 0. |
| `forecast_horizon` | Store setting int 1..90 ngày | Handler special case; int cắt số lẻ. UI/settings/bootstrap đọc; request forecast/import có horizon riêng. |
| `default_strategy` | Ý định string economy/balanced/safe | Handler có nhánh nhưng value đã bị normalize_number đổi string thành null và core validation lỗi. **Không import được theo luồng chuẩn**. Settings mới vẫn default balanced nếu tạo qua monthly_budget/horizon. |

`CONSTRAINT_DEFINITIONS` còn ghi planner_support="configured_only" cho minimum/reorder/shelf-life/service/capacity/budget, nhưng Operational code có đọc chúng. Không dùng flag registry thay cho trace consumer. `LegacySupplierInventoryValueModel` (`legacy_supplier_inventory_values`) lưu safety_stock/capacity chỉ là archive migration, không phải operational source.

## 3. Đường đi mapping → normalize → validate → persist → consumer

### 3.1. Upload, đề xuất và phê duyệt

`app/api/imports.py::{create_import,confirm_import,process_import}` → `app/services/import_service.py::ImportService`:

1. `create_import`: Store phải tồn tại (`StoreRepository.get_required`); hash upload/request và Idempotency-Key nếu có. `app/core/excel_reader.py::read_workbook` nhận xlsx/xls/xlsm/csv, bỏ hàng toàn NA, dò header Excel trong 15 hàng đầu bằng heuristic; CSV dùng header đầu, UTF-8 BOM. Kiểm limits files/size/sheets/rows. Xlsx/xlsm thiếu cached formula value bị từ chối, không evaluate formula.
2. Lưu file upload, `import_jobs`, `import_files`, `import_sheet_profiles` (columns/dtypes/sample_rows và **toàn parsed_rows**), `import_mappings` (suggestion, confirmed=False), `import_issues`. Có sync `imports` legacy payload qua `NormalizedImportRepository.sync_legacy`. Chưa ghi business rows.
3. `IngestionPipeline.suggest` rule-first: `map_sheet_rules` dùng tên sheet keyword để chọn type, chỉ exact normalized header aliases trong schema đó. Confidence `0.55*keyword_score + 0.45*matched_column_ratio`; default threshold 0.82. Chỉ confidence dưới threshold mới gọi LLM khi provider available; requires_review/error/missing core một mình không tự trigger LLM.
4. Người dùng/caller gửi confirm mappings theo profile/sheet. Manual finalizer chỉ chấp nhận field trong type; Menu kiểm tra chặt hơn tất cả cột/core/duplicate. `skip=True` thành unknown mapping, không có business data. Confirm không chạy model.
5. `ImportService.confirm` đặt job confirmed kể cả chỉ confirm một phần profiles. `process` normalize/validate **mọi** mapping, nhưng chỉ thêm `mapping.confirmed=True` vào business_sheets. `requires_review` không phải gate chặn process. Vì vậy canonical JSON, trạng thái completed và business write không luôn đồng nghĩa cùng toàn bộ sheet được áp dụng.

API routes có `require_api_key`; không thấy role riêng approver ở các route import. Đây là quyền gọi confirm/process của caller đã auth, không phải Qwen tự phê duyệt. Audit lưu action/source, không chứng minh four-eyes approval workflow.

### 3.2. Qwen nhận gì và output được kiểm đến đâu

Nguồn quyết định: `app/core/ingestion_pipeline.py::IngestionPipeline.suggest`, `app/llm/openrouter_qwen.py::OpenRouterLLMGateway.{map_sheet,_validate_mapping_result,task_profile,_response_schema}`, `app/api/llm.py::map_sheet`, `app/config.py::Settings`, `app/schemas/llm.py::{SheetProfile,MappingSuggestion}`.

- Model nhận payload gồm `profile.model_dump(mode='json')`, **toàn** `CANONICAL_SCHEMAS` (fields/core_fields, recipe_version field_metadata), `rule_suggestion`. Không nhận models ORM, consumer code, constraint-kind registry, catalog Store/aliases, toàn dataset hoặc những file khác trong request để liên kết entity.
- Profile có tên file/sheet, header row, row/column count, columns, dtypes, sample_rows. Mặc định lấy **8 dòng đầu** (config 8; schema max_length=8), không phải random sample, không phải thống kê toàn cột. Full parsed rows được dùng code sau confirm.
- Prompt bảo mapping mọi source column vào field hợp lệ hoặc null, không bịa source columns; phân biệt inventory snapshot_date với received_date; purchase_date với received_date. Prompt không xác định giá theo pack/base unit hay suy rule từ note.
- Config code mặc định task EXCEL_MAPPING: `qwen/qwen3.5-9b`, temperature 0, max_tokens 1800, timeout 60, reasoning false, structured_output/strict_schema/require_parameters true; gateway route siliconflow. Đây là defaults trong source, không đọc .env hoặc xác nhận model runtime.
- Output shape `sheet_type`, confidence 0..1, column_mapping, warnings/errors, source/requires_review/raw_response. `_validate_mapping_result` đòi keys mapping **đúng và đủ** columns; Pydantic kiểm literal type và targets thuộc registry. Gateway gán source llm. `finalize_mapping` thêm missing core/duplicate warning và tính requires_review bằng code.
- Finalizer dựng lại mapping theo columns, chỉ giữ semantic warnings của suggestion; errors cuối lấy fresh structural errors, không bảo toàn mọi errors model báo. Generic duplicate targets chỉ warning, không vào requires_review nếu confidence cao/core đủ; dict comprehension normalize có thể để cột sau ghi đè field. Manual cũng không nâng duplicate generic thành error. Chưa kiểm semantics unit/price/entity, full-row content, dữ liệu thực tế hay readiness.
- Không có key/provider: pipeline trả rule_fallback cần review. Gateway lỗi có thể giữ known rule suggestion và warning; unknown không có fallback thích hợp có thể báo LLMUnavailable. Pipeline finalizer sau gateway có thể tính lại requires_review, không nên coi fallback flag là approval lock độc lập.
- Mapping persistence giữ column_mapping/source/confidence/requires_review/confirmed/warnings/errors theo profile. Raw response tồn tại ở suggestion nhưng `_mapping_model/_update_mapping` không lưu riêng raw_response vào `ImportMappingModel`. Không thấy cache/template mapping theo header/checksum để áp lại sang upload mới: mỗi upload lại suggest. Replay Idempotency-Key là reuse **job cũ**, không phải học mapping.

### 3.3. Normalize, validation, transaction và các đường consumer

`IngestionPipeline.process_sheet` → `normalize_rows` → `validate_records`; provenance `_source_file/_source_sheet/_source_excel_row` được thêm. `unknown` cho rows=[]/row_count=0, không phải đầy đủ số hàng thật bị bỏ. Số dòng Excel được tính từ enumerate sau dropna(all), nên có hàng trắng bị bỏ giữa dữ liệu thì `_source_excel_row` có thể lệch hàng gốc.

`validate_records` chủ yếu kiểm core nonempty, ngày purchase có ít nhất một field, recipe_version và Menu components cơ bản; không kiểm toàn bộ DB/types/units/ranges. Chỉ trả tối đa **100 errors**, mặc dù invalid_rows ban đầu tính từ tất cả lỗi. `ImportService.process` dùng chính danh sách errors đã cắt để chọn invalid indexes và tính lại summary: partial_success có thể lọt invalid rows ngoài giới hạn; summary không đại diện mọi lỗi.

Policies:

- `atomic`: có row issue thì business data không ghi; persistence exception sau đó rollback cả transaction nghiệp vụ, job ghi failed bằng transaction khác.
- `partial_success`: chỉ lọc invalid indexes đã được row validator báo; **không** savepoint/continue cho mỗi business row. Unit/entity/conflict/unsupported constraint ở persistence vẫn làm rollback toàn business batch.
- `preview_only`: lưu result/validation JSON, không gọi business persistence, status về confirmed. Vì vậy không preview được phần lớn unit/conflict/identity/term validation; preview pass không bảo đảm process pass.
- Job completed có result và business_persisted_at được replay, không chạy business write lần nữa. Claim processing chống gọi process đồng thời cùng job. Điều này không đồng nghĩa chống race/duplicate giữa hai import jobs khác nhau.

| Nhóm | Chuỗi tới consumer thật |
|---|---|
| Menu | `_persist_menu` → products/bundle lines → MenuService.serialize, CompletionService.bootstrap; products.price → CoreProcurementAdapter → build_shortage_economics. Graph combo chỉ thấy ở UI và reconcile usage; CoreBomAdapter.recipe_frame lấy recipe trực tiếp product forecast, không đọc bundle table. Comment “combo expansion đã resolved” trong shortage economics/procurement adapter chưa đủ bằng chứng implementation. |
| Ingredient | `_ingredient` → CatalogRepository/EntityResolutionService → ingredients → CoreBomAdapter/ProcurementPlanningService/CoreProcurementAdapter; aliases do Catalog API tạo. |
| Sales | `_persist_sales_history` → sales_daily → ForecastDataRepository.sales_history → ForecastService → ExistingForecastCoreProvider → shelfcash_core train/predict pipelines. Sales update cũng gọi reconcile_usage_from_sales. |
| Recipe | `_persist_recipes` → RecipeVersionService → versions/lines → RecipeRepository.get_active theo target date → CoreBomAdapter → core BOM → ingredient demand persisted → hai đường planning. |
| Inventory | `_persist_inventory` → lot + movement → ProcurementPlanningService._lots lấy balance tới EOD cutoff → operational simulator hoặc Core InventoryLot/Exact FEFO. Received null được phép vào as-of inventory; movements mới quyết định quantity. Không dùng purchase_receipts thay movements. |
| Purchase | `_persist_purchase_history` → purchase_receipts → OperationalService.history('purchase'); operational PO receipt ngoài import (`CompletionService` receipt path) mới có inventory_effect=applied và lot/movement. Không gộp hai đường này. |
| Supplier | `_persist_supplier_constraints` → active supplier terms → `_terms`, rounding MOQ/pack và delivery schedule; Core adapter → SupplierOffer → optimizer/inbound expiry. Supplier active cũng là điều kiện lọc. |
| Usage | `_persist_usage_history` → usage_daily → history UI; source import khiến reconcile bảo vệ như observed. Không chuyển thành inventory consumption movement. |
| Calendar | `_persist_calendar_features` → calendar_features → ForecastDataRepository → forecast future/missing-sales features; OperationalService.calendar/bootstrap cho UI. Promotion name/bool không nằm trong features model. |
| Constraint | `_persist_business_constraints` → inventory_constraints → BusinessConstraintResolver/InventoryConstraintRepository.effective → operational planner hoặc Core adapter có chọn lọc. Resolver effective dùng date windows + superseded_by_constraint_id, không chỉ active flag. |
| Budget | special settings hoặc budget constraint → BudgetResolver.resolve: request override > BudgetPeriod hiện hữu còn lại > effective budget constraint > settings.monthly_budget **>0** > None/unconfigured. Import monthly_budget không sync BudgetPeriod đã có, nên thay setting có thể không đổi cap thực tế. |

Operational capacity chỉ đánh giá projections ingredients thuộc demand, cùng dimension hoặc warning dimension_unsupported; không tổng hợp toàn kho/đổi kg sang volume. Operational maximum_stock cap trước MOQ/pack rounding không bảo đảm cuối cùng không vượt max. Decision Core store-level capacity **không evaluate**; maximum_stock riêng được chuyển vào model capacity. Safety/minimum/reorder/service/shelf-life-target không được Core adapter truyền. Không port “hỗ trợ mọi constraints” chỉ dựa CONSTRAINT_DEFINITIONS.

Các unit layers chưa thống nhất: DB dùng lít/cái, Core BOM `shelfcash_core/bom/units.py::UNIT_ALIASES` không có aliases này; `UnitConverter.canonical_unit` có thể giữ literal chưa biết dimension. Core BOM đổi g→kg, ml→liter; procurement `_lots` lấy lot balance ở ingredient base_unit nhưng adapter gắn demand unit mà không convert balance. Nếu ingredient base_unit là g/ml, demand Core canonical kg/liter có nguy cơ quantity lệch scale. Đây là sai lệch suy ra từ source, chưa chạy để đo tác động.

Core adapter còn có lỗi tĩnh đáng bàn giao: trong `CoreProcurementAdapter.optimize`, nhánh `if limit is not None or shortage is not None` luôn dựng `capacity_quantity=float(limit)`. Nếu economics có shortage cost nhưng maximum_stock không cấu hình (`limit=None`), phép chuyển `float(None)` sẽ lỗi thay vì cho phép bỏ capacity. Đây là suy luận từ expression/branch trong source, không phải kết quả chạy optimizer.

## 4. Liên kết nhiều file và setup Store

### 4.1. Identity và tạo entity

`app/core/names.py::{display_name,normalize_name,normalize_lookup_name}` phân biệt identity key NFC/casefold còn dấu với lookup combo bỏ dấu/variant. Header mapper bỏ dấu không có nghĩa entity master cũng bỏ dấu. Ví dụ spelling không dấu/viết tắt nguyên liệu cần aliases xác nhận, không được Qwen tự merge.

| Entity | Identity, aliases và ai quyết định tạo |
|---|---|
| Store | Normal upload phải Store tồn tại. Backfill legacy (`ImportService._backfill_legacy`) có ngoại lệ tự tạo Store hoặc LEGACY_UNKNOWN, không phải chính sách onboarding upload mới. Store timezone/currency ở `app/models/store.py::StoreModel`, không import từ sheet. |
| Product | Menu ưu tiên SKU scoped Store; sales chỉ tên, recipes SKU/name; tên có nhiều variants bị chặn. `_product` cho phép code tạo nếu thiếu; không lấy sales price làm catalog price. Không thấy product alias model. |
| Ingredient | `_ingredient` tra tên rồi alias; EntityResolutionService nói chung tra ID/SKU/alias/name nhưng importer chỉ truyền name/unit. Tên mới + unit → tự tạo; unit đầu tiên quyết định base_unit. Không có fuzzy/LLM entity resolution. |
| Supplier | Tên normalized scoped Store, tự tạo khi có name; blank thì null cho inventory/purchase, không được blank với term. Không có supplier alias master. |
| Constraint ingredient | Phải tồn tại qua tên/alias trước; handler không tự tạo. |
| Combo component | Phải tồn tại DB hoặc trong **cùng sheet Menu** đã materialize phase 1; không tự tạo, không nested combo, phải single active, ambiguity variant bị chặn. |

Liên kết: sales.product_id → recipe_version theo product/date → recipe_line.ingredient_id → lot/movement balance và supplier terms của cùng ingredient/Store. Purchase và usage cũng link ingredient nhưng không tự trở thành tồn kho hoặc supplier offer. Người dùng xác nhận mapping/aliases qua API; các quyết định create_if_missing, unit conversion, version và write do code quyết định, không do Qwen.

### 4.2. Thứ tự import và setup một phần

`NormalizedImportRepository.mappings` (`app/repositories/normalized_imports.py`) lấy rows **không order_by**; `ImportBusinessPersistenceService.persist` chạy handler lần lượt theo list truyền vào, không topo-sort, không gom theo dependency trước. Không cam kết thứ tự sheet/file từ UI là thứ tự nghiệp vụ ổn định.

- Constraint trước khi ingredient master/recipe/inventory/term tạo ingredient có thể lỗi INGREDIENT_NOT_FOUND; setup qua các job đã completed trước tránh dependency đó, nhưng không sửa được order trong một job.
- Sales trước recipe vẫn tạo product/sales nhưng reconcile báo thiếu recipe; recipe import sau không gọi rebuild historical usage. Recipe default effective hôm upload còn có thể không cover ngày sales cũ.
- Nhiều file đơn vị compatible nhưng file tạo ingredient trước quyết định base_unit; việc này còn ảnh hưởng giá và Core adapter unit scale.
- Menu 2 phase chỉ trong `_persist_menu` cho một sheet. Component nằm ở sheet Menu khác chưa persist không được pre-materialize toàn job. Singles/Menu trước sales giúp catalog complete, nhưng importer không ép.
- Sales/usage cùng natural key nằm ở nhiều sheet/job không được cộng toàn request: mỗi handler aggregate một sheet rồi overwrite DB. Kết quả có thể phụ thuộc thứ tự xử lý. Những keys không xuất hiện trong reimport vẫn giữ nguyên, không replace cả Store dataset.

Không bắt buộc đủ mọi type mới process. Menu-only, inventory-only, terms-only... có thể completed nếu rows hợp lệ; master entities và business rows được giữ theo Store, các job sau bổ sung. Skip/unconfirmed sheet không tạo business rows, dù result có thể chứa normalized rows từ unconfirmed sheet. Không có “setup draft Store” riêng tự chặn planning vì chưa đủ schema.

### 4.3. Reimport và duplicate

| Nhóm | Semantics thực tế |
|---|---|
| Upload/job | SHA checksum là metadata/index, không cấm upload lại. Idempotency-Key + cùng request hash replay job; cùng key khác request lỗi. Không key → job mới. `_request_hash` gồm danh sách file/name/checksum, Store, forecast_date/horizon; thứ tự danh sách ảnh hưởng hash. |
| Menu | Upsert `(Store, SKU)`, không xóa products vắng mặt; combo replace toàn lines của SKU nhập. source_row_hash chứa import/profile IDs nên reupload content giống vẫn có thể tăng product.version. |
| Sales | Sum rows cùng key trong **một sheet**; overwrite quantity/price/stockout/provenance ở `(Store,date,product,promotion)`, không append quantity lên record cũ. Reimport không có price/stockout có thể xóa metadata cũ về null. |
| Usage | Sum trong một sheet; overwrite `(Store,date,ingredient)` kể cả waste/source; absent waste về 0. Import observed ghi đè derived row; reconcile chỉ sửa source reconstructed_from_sales. |
| Recipe | Content hash chống tạo version giống; nội dung đổi phải effective date sau tất cả version cũ, không update tại cùng date, không nhập ngược historical version. Hash gồm yield/loss/lines/effective, không include requested_version. |
| Inventory | Count target/delta, không cộng on_hand. Immutable metadata conflict bị chặn; same batch/date khác job có movement marker → conflict; không có delta marker có giới hạn nêu trên. |
| Purchase | Append receipt nếu identity mới; external ID hoặc fallback hash tồn tại thì skip, không update hay so nội dung conflict. Không chứng minh chống race external-ID qua DB unique ở model (cột external ID không có unique key tương ứng). |
| Supplier term | Latest content giống → skip; thay đổi → version mới + inactive trước, không effective_from. |
| Calendar | Upsert `(Store,date)`, replace fields và các default; reimport thiếu holiday/promo có thể đổi false, thiếu weather/name đổi null. |
| Constraint | Latest content giống → skip; khác phải effective date lớn hơn latest, inactive trước/đóng end_date trước ngày mới. Lưu note cũng có thể gây version change. Không thay tại cùng effective date qua importer. |
| Settings | Chỉ update kinds được nhập, version tăng khi values thay đổi. Setting mới default monthly_budget=0, horizon=7, strategy=balanced. Không sync budget_period hoặc forecast model readiness. |

`app/core/provenance.py::source_row_hash` chứa store/import/profile/sheet/source_row/type/content, là provenance của job, không content identity bền vững giữa imports. Phân biệt nó với recipe/term content hash và purchase business key.

### 4.4. Missing dates, completeness và readiness

Importer không tạo sales/usage row=0 cho ngày thiếu. Forecast `shelfcash_core/data/panel_builder.py::{build_daily_panel,resolve_missing_sales}` tạo panel ngày đầy đủ cho các series đã quan sát; ngày mở thiếu record → missing_open_day, ngày đóng → quantity NA/store_closed. **Không zero-fill**. Số 0 được nhập là observation thật. Reconcile usage có ngoại lệ đặt derived row=0 khi ingredient không còn trong totals ngày được reconcile; đó là sửa derived state, không suy lịch sales thiếu thành zero.

Không thấy một service readiness tổng thể Store. Các lớp kiểm riêng:

- Job confirmed/completed là workflow import, không đảm bảo menu/recipe/terms/inventory đủ hoặc tất cả profiles confirmed.
- `CompletionService.bootstrap/dashboard` trả master/current data/latest runs/counts; không đánh giá một completeness checklist và data_notes dashboard là list rỗng trong code.
- Forecast cần sales hợp lệ, model artifact/version, history eligibility và train target: `ForecastService`, `shelfcash_core/config.py::ForecastConfig.minimum_history_observations` mặc định 28, training/inference pipelines còn kiểm usable observations/feature support. 28 ngày lịch hoặc import completed không đủ bảo đảm forecast.
- `CompletedForecastReader.load` yêu cầu completed forecast hợp lệ; IngredientDemandLifecycle cần recipe hiệu lực tại target date, lines có nguyên liệu/unit hợp lệ. Menu combo graph không thay thế recipe cho product forecast.
- Operational procurement yêu cầu demand run completed/nonempty; thiếu inventory có thể thành danh sách rỗng (coi không có balance), thiếu supplier khi có need ra violation, safety thiếu → 0 warning, budget thiếu → no cap warning. Không có evidence riêng phân biệt “đã xác nhận tồn=0” với “chưa nhập tồn”.
- Core Decision kiểm cutoff/horizon/demand, xây offers/budget/capacity; constraint import completed không đồng nghĩa mọi constraint được áp dụng. Không xác nhận tính khả thi từ audit tĩnh này.

### 4.5. Ví dụ nhỏ theo semantics code (không phải kết quả chạy)

Giả sử Store đã tạo; Menu single SKU `CF01`, tên `Cà phê`, unit `ly`; recipe effective ngày `D` có `Sữa`, quantity **1000 g**, yield **10 ly**. Nếu ingredient Sữa đã có base_unit kg thì importer convert line thành 1 kg; BOM count 1 ly sẽ cần 1/10=0.1 kg (loss import mặc định 0). Đây là phép tính contract, không là dự báo.

Term cùng Sữa: MOQ **2 thùng**, package_size **5 kg**, package_base_unit kg → DB moq=10 kg, pack_size=5 kg, order_unit=case. `unit_price` phải được bên cung cấp xác định là giá/kg theo consumer cũ; nếu bảng ghi giá/thùng mà map vào unit_price thì code không chia 5. Purchase history nhận 5 kg chỉ tạo receipt; inventory snapshot batch `L1`, on_hand 3 kg, snapshot ngày `D` mới tạo balance kiểm kê. Missing received_date ở snapshot vẫn null, không trở thành ngày `D`.

Sales ngày `D` cho Cà phê dùng product identity tên (SKU sales không có target). Nếu recipe đã hiệu lực, reconcile cũ nhân line 1 kg với số món mà không chia yield=10, sai với BOM 0.1 kg/món. Nếu sales persist trước recipe, cảnh báo thiếu recipe và import recipe sau không tự rebuild. Ngày `D+1` không có sales row vẫn missing trong forecast panel, không suy bằng 0. Constraint safety_stock cho Sữa chỉ persist được sau khi ingredient tồn tại; Operational dùng nó, Core Decision không truyền nó sang optimizer hiện tại.

## 5. Giới hạn/sai lệch giữa registry, comment và code

| Dấu hiệu dễ hiểu sai | Kết luận có căn cứ source |
|---|---|
| Có field trong canonical registry | Chỉ cho phép mapping. `sales.unit/revenue` dừng ở canonical JSON; promotion name mất khi persist. `CanonicalResult` không enforce từng row type. |
| Qwen thấy schema nên hiểu đủ nghiệp vụ | Model chỉ thấy fields/core + profile sample. Không thấy price_basis, entity catalog, constraints registry, consumer hoặc multi-file context. Finalizer chủ yếu kiểm structure. |
| Generic aliases nhận mọi canonical header | `_alias_map` chỉ loop keys ALIASES. `is_stockout/promotion_name/currency/purchase_order_id` không có entry. Menu dùng map riêng. Key recipe_version duplicate làm mất ver. |
| Supplier core fields đủ là import hợp lệ | unit_price/lead_time không core nhưng handler bắt buộc. MOQ file là pack count; DB moq là physical quantity. Price không đổi khi quantity/unit đổi. |
| Units compatible thì dữ liệu số đúng | Missing unit có permissive conversion; base_unit phụ thuộc create order; Core BOM và inventory adapters khác canonical scale; giá không convert nghịch unit. Không có density/custom-pack conversion import. |
| Recipe quantity luôn “lượng 1 sp” do alias/comment | Yield>1 nghĩa lượng/batch yield. Alias “lượng 1 sp” có thể đánh lừa. Yield=0 bị sửa thành 1. Reconcile usage không theo công thức BOM. |
| Có process_loss_rate ở model là import hỗ trợ loss | Không có import target; service default 0, waste allowance adapter 0. API/engine support khác import support. |
| Comment combo đã expanded | CoreBomAdapter không đọc bundle graph; forecast repository không expand sales combo; chỉ reconciliation usage đọc graph. Graph/Menu support không bảo đảm planning combo. |
| Purchase history nhận hàng tăng tồn | Handler record_only, không movement/lot/PO inbound. purchase_date fallback mất phân biệt invoice/receipt day. External invoice ID không có line identity. |
| Inventory optional receipt nghĩa tự suy ngày | Hiện giữ null/status unknown; snapshot ngày riêng, timezone EOD rõ. Không port giả định “ngày nhận=ngày kiểm kê”. |
| Business registry flag configured_only nghĩa không consumer | Operational đọc nhiều loại dù flag cũ. Ngược lại Core Decision không truyền nhiều configured kinds và store storage chỉ context not_evaluated. |
| Capacity là ràng buộc kho đầy đủ | Operational chỉ cùng dimension và demand ingredients; Core thiếu volume metadata, không evaluate Store storage. warehouse_capacity không gắn warehouse_name. |
| Import budget cập nhật ngân sách dùng ngay | BudgetPeriod hiện hữu có ưu tiên cao hơn settings/constraint; importer settings không sync period. Settings zero coi unconfigured, constraint zero coi cap=0. |
| default_strategy special branch là có hỗ trợ import | Numeric normalizer cho value phá string economy/balanced/safe; core validation chặn trước handler. |
| preview/partial_success là business validation đầy đủ | Preview không gọi persist; partial chỉ lọc validator errors tối đa 100, persistence exception vẫn rollback cả batch. Menu normalization lỗi có thể xảy ra trước row report. |
| requires_review/completed là readiness/approval đủ | Process không gate requires_review; job confirmed một phần; canonical result có thể gồm unconfirmed sheet không ghi business. Không có toàn Store readiness. |
| Có note là LLM sẽ dùng điều kiện quán | Constraint note lưu/hash, không planner hoặc import Qwen diễn giải. Không có field phí/business-notes tự do và không có consumer tương ứng. |
| Có created_at/known_at là future-feature leakage được chặn | Calendar không version từng feature observation, adapt_calendar bỏ known_at; cần contract as-of riêng. |

Đây là các vấn đề thiết kế/đường gọi suy từ code. Không dùng reports/ZIP/evidence có sẵn để bịa xác nhận runtime, không khẳng định dữ liệu Store nào đã gặp lỗi. `SCHEMA_VERSION` trong business_persistence vẫn là `20260804_0018` dù source có logic snapshot mới và migrations sau đó; version string không đủ mô tả toàn contract hiện tại.

## 6. Khuyến nghị cho bản mới

### A. Cần có để quán mới chạy planning

“Cần” là đầu vào đúng nghiệp vụ cho một kế hoạch có thể tin cậy; code cũ có thể cho chạy với warning/default khi thiếu.

- Store identity/timezone/currency; product SKU và selling unit rõ; ingredient ID/base unit cùng aliases đã xác nhận. Không bắt dùng tên làm natural key.
- Demand đầu vào đủ horizon và provenance. Nếu planning đi qua forecast cũ cần sales lịch sử hợp lệ/model ready; quán mới chưa có history nên thiết kế đường nhập demand/manual plan riêng, không bịa sales để vượt 28 observations.
- Recipe theo product/version/effective range, định lượng cho serving hay batch được định nghĩa bằng output_quantity/output_unit; có policy loss/yield rõ, cùng engine BOM cho planning và derived usage. Combo phải có một cơ chế expand graph thống nhất trước BOM hoặc recipe trực tiếp có chủ đích.
- Tồn kiểm kê as-of và lot theo ingredient/unit, expiry mode và dates nullable đúng nghĩa; phải phân biệt chưa khai báo tồn với quán xác nhận tồn=0. Movement và snapshot có identity/ordering, không receipt-date guessing.
- Supplier offer cho nguyên liệu cần mua: pack quantity/base unit, integer pack MOQ hay physical MOQ xác định rõ, **price_basis**, price_unit/currency, lead time integer, delivery calendar và exact shelf life nếu có. Phí phải vào chi phí nếu nghiệp vụ tính phí.
- Budget/capacity/safety/service là policy tùy quán, nhưng cần chọn và công bố “không cấu hình” hay giá trị hiệu lực, consumer nào áp dụng. Không ghi constraint mà UI gọi đó là được enforce. Ngân sách một nguồn quyền lực theo kỳ, reserve/spend/as-of có audit.

### B. Có ích cho forecast/phân tích nhưng không bắt buộc cho planning

- Stockout observation nullable, thời gian hết hàng/lost demand nếu thu được; giữ observed sales riêng reconstructed demand, confidence và lineage. Không mặc định unknown=false.
- Calendar closed/holiday/weather, promotion history và giá/doanh thu thực tế. Muốn promotion/price tác động forecast phải thiết kế feature/point-in-time contract mới; field tồn tại chưa đủ.
- Observed usage và waste để đối chiếu BOM, cost/efficiency; purchase history để audit/phân tích price/lead time. Các dữ liệu này không cần tự làm inventory delta khi chỉ record-only.
- Warehouse/location, external refs, notes nghiệp vụ cho UI và giải thích có giới hạn. Notes không thành hard constraint nếu chưa được parse/confirm thành typed rule.

### C. Có schema/model nhưng implementation hoặc consumer chưa hoàn chỉnh

- Sales revenue/unit nguồn không có business storage đầy đủ; promotion name không roundtrip. Calendar promo chỉ storage/UI, không model feature; canonical unit/price semantics thiếu metadata.
- Ingredient/Supplier masters và aliases không có import schema độc lập; sales thiếu SKU dù product có variants; product/supplier alias không có implementation tương đương ingredient alias.
- Loss/waste fields có ở recipe model/core nhưng không import; effective_to không import; recipe import provenance không truyền đủ.
- Usage/purchase có business tables/UI nhưng chưa feed forecast nguyên liệu hoặc inventory ledger tự động. PO receipt riêng có write nghiệp vụ, không được coi purchase_history đã làm việc đó.
- Core Decision chưa dùng configured safety/minimum/reorder/service/shelf-life-target và chưa evaluate Store storage. delivery fees/free notes chưa có schema import/consumer; không xem đó là “chỉ registry”.
- default_strategy nhánh handler không đi được qua normalizer; readiness tổng thể và mapping template reuse không có. Các subtype business constraints không được gửi đầy đủ cho Qwen.

### D. Logic cũ không nên port nguyên

1. Thiết kế typed schemas theo từng nhóm và union value theo constraint_type; giữ raw + normalized + validation issues, phân biệt missing/null/zero. Không dùng `or default` cho quantity và không cắt decimal/integer silently. Reject nonfinite, ngày sai và invalid optional values có ngữ cảnh hàng/cột.
2. Unit contract duy nhất xuyên import→DB→BOM→FEFO→cost; convert quantity **và price** đúng basis. Tách physical quantity, sell count, pack count và currency; kiểm tra total/revenue bằng policy chứ không tự overwrite actual nguồn.
3. Resolve master toàn batch rồi validate dependencies trước write; thứ tự deterministic, không dựa query không order_by. Thiết kế identity theo Store/IDs, aliases được người dùng xác nhận, không tùy ý tự tạo product/ingredient/supplier chỉ từ spelling.
4. Chọn rõ replace/upsert/append cho từng dataset và phạm vi ngày/entity; gom cùng natural key toàn request hoặc chặn overlap. External invoice **line** identity, conflict detection và DB uniqueness/concurrency; provenance hash tách content identity. Không dùng “skip nội dung khác” làm idempotency.
5. Preview phải chạy cùng business validators/planned effects với commit. Partial success dùng đầy đủ issue set và transaction boundary rõ; không truncate danh sách lỗi dùng để lọc. Commit gate theo per-sheet approval và Store readiness, không chỉ job status/requires_review.
6. Version recipe/term/calendar/constraints và as-of đúng nghiệp vụ; giữ ngày mua/nhận/kiểm kê độc lập. Đưa inferred defaults vào trace để người dùng xác nhận; unknown expiry cần policy rõ, không infer not_required chỉ theo tên/tỷ lệ quán.
7. Dùng một BOM calculator cho demand và sales-derived usage, cùng quy ước yield/loss/combos; observed usage không bị lẫn với reconstructed. Usage/receipt không tự tác động tồn nếu mode record-only; nếu muốn applied cần command riêng, identity và chống ghi hai lần.
8. Contract consumer capabilities theo từng planning path, kiểm một constraint có thật được truyền/enforce không; capacity cần physical storage footprint/density metadata phù hợp. Budget không duy trì nhiều nguồn cap mâu thuẫn; fee/discount/tax có basis rõ.
9. Qwen chỉ đề xuất type/mapping/semantic ambiguity, code kiểm cấu trúc và tất cả rows, người dùng xác nhận quyết định ảnh hưởng nghiệp vụ. Model cần schema có types/units/basis/constraints đủ nghĩa; giới hạn sample và mapping confidence phải được công bố. Lưu audit mapping/raw response đã kiểm soát và template version nếu thiết kế reuse; không trao quyền tự duyệt hoặc ghi business cho LLM.

Các điểm đáng kế thừa: rule-first mapping có review, Store-scoped identity, ingredient aliases, per-sheet confirmation/skip, provenance/import issues, atomic business transaction và processing claim, recipe content/version/effectivity, separation receipt record-only với PO receipt applied, snapshot EOD và received_date unknown, nullable stockout, forecast không zero-fill ngày thiếu, deterministic unit conversion cùng dimension, FEFO và trace warning/capability. Kế thừa ý tưởng sau khi thống nhất semantics; không copy toàn bộ registry/handler thành chuẩn của ShelfCash mới.
