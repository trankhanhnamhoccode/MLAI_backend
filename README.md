# ShelfCash Competition Edition

CURRENT FACT C4 source WIP: Today/supplier/PDF discovery và Import/Planning read
extensions đã có72 operations/66 paths, giữ head0026/catalogue43. Chưa commit hoặc
nâng cấp demo8103; [commands và giới hạn C4](docs/runbooks/FULL_TEST_FLOW.md#read-discovery-c4).

CURRENT FACT C3 local commit b1c906a: Excel hàng thực nhận đã nối shared N6 receipt writer;
không endpoint/permission/migration mới. Xem luồng kiểm và giới hạn tại
[FULL_TEST_FLOW — C3](docs/runbooks/FULL_TEST_FLOW.md#excel-actual-receipt-c3).

ShelfCash giúp quán F&B so sánh phương án mua nguyên liệu theo nhu cầu, công thức,
tồn kho, hạn dùng, điều khoản nhà cung cấp và ngân sách. Backend tính toán và đề
xuất; khách hàng quyết định. Hệ thống không tự đặt hàng.

CURRENT FACT: backend đã có đăng nhập và quyền theo Store (quán), Staff (nhân viên),
đọc Menu/Kho, import có duyệt và ghi toàn batch trong một transaction, readiness
(kiểm tra đủ dữ liệu), Planning (lập phương án), lịch sử và xuất PDF tiếng Việt.
CURRENT FACT source C1/C2 local: OpenAPI69 operations/64 paths; NF01–NF03 inbox,
PR01–PR04 yêu cầu quyền và MQ01–MQ03 queue mapping/N5 extension. Catalogue
permissions-v3/43 giữ nguyên, head `0026_collaboration_requests` (70 bảng ứng dụng).
C1 commit f85c7cdd, C2 local commit b9fe048; N13/PR/MQ producers và current target rights
đã nối. Xem [commands/limits](docs/runbooks/FULL_TEST_FLOW.md#notifications-c1).
Runtime demo8103 bên dưới vẫn0024/59 operations, chưa nâng cấp C1/C2/C3/C4.

CURRENT FACT: forecast hỗ trợ baseline (mô hình cơ sở) và trained artifacts (tệp
mô hình đã huấn luyện). Demo chọn BASELINE; chất lượng dữ liệu thật chưa đánh giá.
Người dùng đã thử FE thật tới mapping lần đầu. Toàn luồng browser import/Planning
chưa kiểm chứng; S4.11 còn PARTIAL. FE đang lỗi khi người dùng test và tạm dừng
xử lý trong scope BE này; không coi API/runtime probes là browser E2E pass.
Xem [trạng thái](docs/CURRENT_STATE.md).

HISTORICAL INFORMATION: tag `v1.0` giữ bản trước nâng cấp header/rules. CURRENT FACT
trên nhánh import: nhận diện dòng header sau tiêu đề/ghi chú đơn cột, giữ vị trí
nguồn, aliases có kiểm soát và lý do đề xuất. Owner có thể duyệt toàn profile khi
mọi đề xuất rules rõ nghĩa và đủ dữ liệu; không phải bấm xác nhận từng cột trước
quyết định duyệt. Cột mơ hồ/không hỗ trợ vẫn phải giải quyết rõ ràng. Khai báo nguồn,
định danh, unit/date và dữ liệu bắt buộc không được đoán.

Profile đã duyệt reuse trong cùng Store khi scope/cấu trúc khớp; mỗi batch vẫn
preview và xác nhận commit riêng. Drift (kể cả header reorder hoặc đổi workbook
epoch) cần review và Owner duyệt profile mới. Excel serial date cần khai báo
EXCEL_SERIAL; preview chuyển theo1900/1904 sau Owner approval, không tự tạo timestamp.
Adapter OpenRouter mặc định tắt (`IMPORT_LLM_SUGGESTIONS_ENABLED=false`), kể cả có
key. Một live probe POS demo đã nhận proposal hợp lệ cho SLX; đây không phải
kiểm chứng toàn luồng browser hay chất lượng mọi workbook. Live calls chỉ trong
phạm vi model/dữ liệu/calls/chi phí đã được duyệt.
Rules/profile/manual flow hoạt động khi provider không có. Xem
[Import contract](docs/IMPORT_MAPPING_API_CONTRACT_VI.md) và
[giới hạn parser/mapping](docs/features/IMPORT_STAGING_PREVIEW.md).

## Quick start BE local — hằng ngày sau setup một lần

Mở Docker Desktop; instance PostgreSQL hiện có phải đang chạy. Dùng PowerShell:

```powershell
Set-Location D:\hocc_bk\ai\proj\projectMLAI\backend-integrate-import-auth
.\.venv\Scripts\python.exe -m scripts.integrated_demo status
.\.venv\Scripts\python.exe -m scripts.integrated_demo start
# Khi cần dừng BE:
.\.venv\Scripts\python.exe -m scripts.integrated_demo stop
```

BE: **https://localhost:8103**. FE dự kiến: **https://localhost:5173**;
launcher này chỉ BE, không khởi động/cấu hình FE. Expected status: DB
`shelfcash_integration_demo`, head0024,65 bảng; sau start là server running và
Import/Planning/PDF alive. Không reset/migrate/seed mỗi lần chạy.

[**FULL_TEST_FLOW — hướng dẫn vận hành chính**](docs/runbooks/FULL_TEST_FLOW.md#integrated-demo-runtime)
chứa setup lần đầu, trust certificate một lần, tài khoản local private,
Origin/callback, credentials include và troubleshooting. Store demo trống cần
import/cấu hình có nguồn; không seed để che readiness. Email delivery và
OpenRouter/Qwen OFF mặc định. Gmail smoke lịch sử không phải email workflow E2E.
Các profile development/S4.11 cũ có scope riêng trong runbook, không dùng làm
startup bản tích hợp. Health chỉ liveness; OpenAPI là routes/DTO; docs/redoc tắt.

## Kiểm thử tự động

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_integrated_demo.py tests/unit/test_database_config.py tests/api/test_auth_openapi.py tests/api/test_staff_openapi.py -q --tb=short --show-capture=no
```

Integration tests của bản tích hợp chỉ sở hữu `shelfcash_integration_test`/
`shelfcash_integration_tester` theo TEST_DATABASE_URL, chạy tuần tự, cần PostgreSQL.
Demo riêng là `shelfcash_integration_demo`; không dùng tests/reset trên demo.
Đây không phải lệnh mở browser hoặc seed demo. Output kiểm thử trong runtime khác
với provenance import, audit, Runs/PDF và model artifacts; giữ các tài nguyên
nghiệp vụ đó. Targeted passing không đại diện full regression passing.

## Tài liệu có thẩm quyền

- [Quy tắc engineering và tài liệu](AGENTS.md).
- [Trạng thái hiện tại](docs/CURRENT_STATE.md) và [phần còn lại](docs/ROADMAP.md).
- [Hướng dẫn chạy và kiểm thử](docs/runbooks/FULL_TEST_FLOW.md).
- [API chung, Catalog và Inventory](docs/API_CONTRACT.md).
- [Authorization](docs/AUTHORIZATION_CONTRACT_VI.md),
  [Import](docs/IMPORT_MAPPING_API_CONTRACT_VI.md),
  [Planning](docs/PROCUREMENT_API_CONTRACT_VI.md).
- [Kiến trúc](docs/ARCHITECTURE.md), [nghiệp vụ domain](docs/DOMAIN_MODEL.md),
  [schema DB](docs/DATABASE_SCHEMA.md), [các ADR đã duyệt](docs/DECISIONS.md).
- [Tương thích và nguồn gốc baseline](docs/CONTRACT_COMPATIBILITY_CHANGELOG_VI.md).

Cập nhật trực tiếp tài liệu sở hữu chủ đề. Kế hoạch/kết quả thông thường thuộc hội
thoại; không tạo thêm task notes, báo cáo PASS hoặc ZIP.
