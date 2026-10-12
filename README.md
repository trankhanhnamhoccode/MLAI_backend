# ShelfCash Competition Edition — v1.0

ShelfCash giúp quán F&B so sánh phương án mua nguyên liệu theo nhu cầu, công thức,
tồn kho, hạn dùng, điều khoản nhà cung cấp và ngân sách. Backend tính toán và đề
xuất; khách hàng quyết định. Hệ thống không tự đặt hàng.

CURRENT FACT: backend đã có đăng nhập và quyền theo Store (quán), Staff (nhân viên),
đọc Menu/Kho, import có duyệt và ghi toàn batch trong một transaction, readiness
(kiểm tra đủ dữ liệu), Planning (lập phương án), lịch sử và xuất PDF tiếng Việt.
OpenAPI có 53 operations nghiệp vụ và health. Alembic head là
`0017_planning_exports` (60 bảng ứng dụng, cộng bảng Alembic).

CURRENT FACT: forecast hỗ trợ baseline (mô hình cơ sở) và trained artifacts (tệp
mô hình đã huấn luyện). Demo chọn BASELINE; chất lượng dữ liệu thật chưa đánh giá.
Người dùng đã thử FE thật tới mapping lần đầu. Toàn luồng browser import/Planning
chưa kiểm chứng; S4.11 còn PARTIAL, UI lịch sử Planning/PDF chưa hoàn thiện.
Xem [trạng thái](docs/CURRENT_STATE.md).

Giới hạn v1.0: rules gợi ý canonical key/alias trong descriptors nhưng chưa bao
phủ headers demo; lần đầu vẫn cần review, khai báo nguồn và nối định danh. Owner
duyệt profile riêng với xác nhận commit. Profile đã duyệt có thể reuse khi cấu
trúc khớp; từng batch vẫn cần preview và xác nhận riêng. Có adapter OpenRouter
tùy chọn; không gọi lúc startup. Rules/profile/manual flow không cần LLM; task
release không gọi provider thật.

## Cài đặt development

Cần Python 3.11+, Docker Desktop chạy Linux containers/Compose. Windows là nền
tảng đã dùng kiểm chứng. Chạy PowerShell từ `backend/`. Đây là cài đặt development
mới; hướng dẫn thao tác trên browser ở runbook bên dưới. Không migrate/reset DB
development hiện có như một bước test release.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[dev]'
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker compose up -d --wait --wait-timeout 90 postgres
.\scripts\db_status.ps1 -AllowUnmigrated
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Development dùng PostgreSQL5432 và volume `shelfcash-postgres-data`; BE8000. Không
seed dữ liệu nghiệp vụ. Health chỉ chứng minh process sống; `/openapi.json` mô tả
routes/DTO, `/docs` và `/redoc` tắt. Import/Planning/PDF có flags riêng, mặc định
OFF; không cần provider trả phí. POSIX dùng `.venv/bin/python` và
`.venv/bin/alembic`; chưa kiểm chứng runtime POSIX.

## Chạy và thử trên browser

[FULL_TEST_FLOW](docs/runbooks/FULL_TEST_FLOW.md) hướng dẫn đầy đủ cài đặt FE,
khởi động/reuse, tài khoản/Store, import → Planning, lỗi và cách dừng. Demo S4.11
tách khỏi development/tests: FE `http://localhost:5173`, BE18001, DB5433. Launcher
đọc private settings, không root `.env`; startup không reset/seed lại.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/local-integration.ps1 docker
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/local-integration.ps1 status
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/local-integration.ps1 start
```

Chỉ dùng các lệnh này sau khi đã thiết lập demo theo runbook. Mở `/login` trên FE,
đọc tài khoản riêng tư trong editor; không đưa credentials vào Git/logs.

## Kiểm thử tự động

```powershell
.\scripts\test.ps1 unit
.\scripts\test.ps1 api
.\scripts\test.ps1 integration
.\.venv\Scripts\python.exe -m scripts.integration_contract_snapshot
```

Integration tests chỉ sở hữu `shelfcash_test`, chạy tuần tự, cần PostgreSQL local.
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
