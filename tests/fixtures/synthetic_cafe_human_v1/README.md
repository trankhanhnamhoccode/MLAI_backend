# Demo quán cafe — dữ liệu giả, bố cục dành cho người nhập

Đây là bản trình bày tiếng Việt của `../synthetic_cafe_v1`, không phải dữ liệu
trích từ sáu workbook gốc tháng07. Không tạo lại sales hoặc chỉnh ngân sách/forecast.
Mọi SKU, giá, ngày nhận, MOQ, yield1, loss0, version1 và trạng thái là facts giả
được khai báo tường minh trong bộ chuẩn. Mã nguồn riêng với SKU. Giữ đủ tên
“Sinh tố dâu size S/L”, “Cà phê sữa nóng/lạnh”. Không fuzzy merge.

Mốc dữ liệu: **17/10/2026 23:59:59+07:00**, Asia/Ho_Chi_Minh. Lịch sử182 ngày
19/04–17/10. Nguồn ổn định `SYNTHETIC_CAFE_V1`, loại báo cáo `CAFE_INPUT_V1`;
sales tổng theo món/ngày, key `CAFE_V1_DAILY_TOTAL`. Đổi tên file không đổi nguồn.
Các quan sát kho là cuối ngày do tác giả bộ giả khai báo, không timestamp forecast.
Protocol oracle giữ10 validation origins30/05–01/08 và10 internal holdout origins
08/08–10/10; tuần18–24/10 tách ngoài cả hai. Lát này không train/chọn model lại.

## File nào nhập?

| File | Phạm vi / thứ tự |
| --- | --- |
|01_danh_muc.xlsx|Menu4 món,5 nguyên liệu,1 NCC,4 công thức/16 dòng và5 quy cách mua.|
|02_ban_hang.xlsx|728 quan sát món/ngày; SL bán là tổng ngày, không contribution độc lập.|
|03_lich_su.xlsx|597 dòng mua và910 dòng thực dùng. Chỉ lịch sử, không ghi tăng/giảm kho.|
|04_ton_kho.xlsx|11 lô còn tồn thực tế ở cutoff, khai báo mở sổ; không receipt mới.|
|08_khai_bao_phi.csv|Khai báo phí đầy đủ: giá pack đã gồm phí, không phí phát sinh; không phải missing fee=0.|
|09_pham_vi_ca_chinh.csv|Nhập sau khi các lô đã commit:5 phạm vi kho, sales coverage và procurement context.|
|05_ca_du_ton.xlsx|Ca phụ trên **Store mới riêng**: thay04 và thay sheet Mua hàng trong03; giữ Thực dùng03.16 lô,602 dòng mua.|
|10_pham_vi_du_ton.csv|Thay09 cho ca đủ tồn, nhập sau commit lô.|
|06_tuan_kiem_chung.xlsx|**Không upload** vào Store đầu vào.28 actuals18–24/10, khóa riêng đến khi dự báo đã frozen.|
|07_doi_soat.xlsx|**Không import**. Đối soát bảo toàn tồn/ngày/lô; nhập lại sẽ làm sai nghiệp vụ.|

Có thể upload01,02,03,04,08 cùng batch để Owner review rồi commit atomic.
Sau đó nhập09 riêng. Nếu nhập lần lượt, giữ thứ tự catalog trước, stock trước
phạm vi; mỗi batch vẫn cần review/preview/confirmation riêng. Không import cả04
và05. Ca đủ tồn explicitly IGNORE sheet Mua hàng03, có lý do/ack; không bỏ rows
âm thầm. Ca ngân sách thiếu dùng đúng đầu vào ca chính, budget1VND.

## Hoàn thành trên backend hiện có

1. Tạo/chọn Store; auth bootstrap của test chỉ tạo account/Store, không seed facts.
2. Upload và analyze. Discovery không gọi model. Đọc M01/M02/M03 để kiểm sheet,
   target proposals/candidates và blockers riêng từng loại.
3. Chọn workflow đúng cho từng sheet: products, ingredients, suppliers, recipes,
   supplier_terms, sales, purchase_history, usage_history, opening_stock, payable_fees.
   `manifest.json` ghi nhãn→target để hỗ trợ người review, không là BE rule.
4. M04 source_context: nguồn/report ở trên; Excel dùng EXCEL_SERIAL, CSV dùng ISO,
   sales_semantics=daily_total. Khai báo nguồn trước khi dùng approved-profile reuse.
5. Giữ các alias đủ điều kiện để Owner xem full spec. `SL bán` cần explicit target
   `sales.quantity` theo current build_spec policy; không mở whitelist giảm clicks.
   Cột chưa nhận diện nối tay theo manifest. Không tự IGNORE target=null.
6. Đối chiếu full name, khai báo new entity metadata đúng nguồn, review reserved IDs;
   nối rows phụ thuộc vào Product/Ingredient/Supplier đó. Khi nhập phạm vi, nối mã
   lô nguồn đúng lot ID vừa commit trong Store. Không lấy UUID từ benchmark/Store khác.
7. Owner approve_activate full spec/evidence qua N5. Staff chỉ prepare/submit theo
   grants hiện hành; approval không cấp thêm quyền ghi miền.
8. Preview → đọc warnings/conflicts → confirm_review → atomic commit → poll job/
   completion. Approval, preview, confirmation và commit là các thao tác riêng.
9. Nhập declaration phạm vi09/10, Owner review các covered lots và capacities,
   xác nhận không inbound/đơn bổ sung đã biết ở cutoff. Không suy từ thiếu rows.

Phí/phạm vi có cấu trúc nested; contract hiện chỉ đọc qua cột nguồn, không có
form M04 generic nested declaration. Vì vậy CSV08–10 là **declarations giả đi kèm**,
không nhét JSON/UUID vào Excel. Nội dung dùng token nghiệp vụ, được nối thủ công
và Owner duyệt. Đây là giới hạn ergonomics hiện có; không thêm API/DDL cho demo.
Enum nghiệp vụ trong bảng (PER_SERVING, PER_PACK, PACKS) dùng đúng giá trị contract;
null là ô trống, boolean là ô Excel true/false. Đơn vị ml/g/piece/cup giữ nguyên;
không ngầm đổi kg/lít/ly. Loss0 là explicit fact giả, không SYSTEM_DEFAULT.

## Planning và reuse

Serving **BASELINE** phải được cấu hình qua operator hiện có; dataset không tự
kích hoạt model. Không train lại/activate LightGBM trong lát này. Budget Owner
khai báo5.000.000VND; custom requirement BASE100% cho từng món; forecast18–24/10.
C02 → worker → C03; kiểm BOM, packs/MOQ, lead1ngày, HSD14ngày thực phẩm, capacities,
phí và chi phí. Kỳ vọng oracle: ca chính mua3.620.000; ca đủ tồn mua0; budget1
không winner. Selector khuyến nghị, người dùng quyết định chọn cuối; không đặt hàng
hoặc ghi stock từ Planning. Search incomplete không chứng minh tối ưu toàn cục.

Re-export đổi tên, cùng Store/source/profile: khai báo source_context rồi reuse
binding/version còn hợp lệ; không N5 lại khi spec không đổi. Preview/confirm/commit
riêng, NO_OP cho facts giống nhau, không cộng stock/sales. Bộ này lấy values từ
cột nguồn nên không có IMPORT_VALUE requirement. Nếu đổi rule sang IMPORT_VALUE,
phải khai báo lại mỗi import theo contract, không dùng values cũ.

FE chưa được sửa/kiểm browser trong lát này. Các thao tác M04 source/identity,
explicit column, N5 full spec và structured CSV declaration cần được UI/adapters
biểu diễn; API acceptance không chứng minh toàn bộ UI hiện tại làm được. Qwen
tùy chọn chỉ sau source context cho sheet eligible; không cần để chạy demo này,
không được resolve facts/identity thay người review. Real provider calls=0.

## Tái lập và kiểm tra

Generator `scripts/generate_synthetic_cafe_human.mjs` đọc oracle bất biến, không random
facts (seed kế thừa bộ chuẩn). Dùng Node/artifact-tool theo skill Spreadsheets.
Chạy từng tên XLSX ở manifest bằng process Node riêng rồi `--metadata` để xuất
CSV/manifest/hashes; không sửa oracle. `manifest.json` ánh xạ từng cột và toàn bộ
rows một-một sang oracle; `hashes.json` pin bytes đầu vào. Binaries XLSX có thể có
metadata export khác giữa runtime; tests kiểm cả hash đã pin và exact cell values.

Tests: `tests/unit/test_synthetic_cafe_human.py` kiểm toàn bộ ô/oracle/hashes/cutoff;
`tests/unit/test_import_human_rules.py` kiểm aliases/đổi thứ tự/header-row/negative;
`tests/integration/test_synthetic_cafe_human.py` chạy public Import/Owner/worker,
fresh-session facts, renamed re-export và3 ca Planning, không seed business facts.
Logs/JUnit/redacted API requests/source digest nằm trong ignored runtime theo runner.
Chạy DB test owned shelfcash_test qua harness; không dùng .env/development/demo DB.
Snapshot có cutoff cố định; DB system timestamps thực tế sau cutoff có thể làm
freshness guard chặn. Không nới guard/đổi oracle để lách; phải báo rõ điều kiện thời gian.
