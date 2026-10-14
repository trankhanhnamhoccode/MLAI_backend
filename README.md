# ShelfCash Competition Edition

Backend giúp quán F&B so sánh phương án mua nguyên liệu từ demand, BOM, tồn kho,
hạn dùng, supplier terms và budget. Backend tính toán; khách quyết định, không tự đặt hàng.

CURRENT FACT: self-service account → verify/password → login → tạo Store/Owner →
invite Staff; Import có review/atomic commit, Inventory, Planning/History/PDF,
permission requests/mapping queue/notifications và Today. Source73 operations/66 paths,
head0027/72 tables. Không seed account/Store/business facts cho customer workflow.
Browser E2E pending; FE chưa có signup/EMAIL_VERIFY callback/create Store flow được
xác nhận. Email mặc định OFF tới khi SMTP/key/callback đúng; không giả full browser pass.

## Setup lần đầu

Checkout chính: `D:\hocc_bk\ai\proj\projectMLAI\backend`, main, `.venv` riêng.
Cần Python3.11+, Docker Desktop Linux engine, Git và PowerShell. Từ checkout sạch:

```powershell
Set-Location D:\hocc_bk\ai\proj\projectMLAI\backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[dev]'
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
.\.venv\Scripts\python.exe -m scripts.local_runtime secrets
notepad .env
.\.venv\Scripts\python.exe -m scripts.local_runtime docker
.\.venv\Scripts\python.exe -m scripts.local_runtime init-db
.\.venv\Scripts\python.exe -m scripts.local_runtime migrate
.\.venv\Scripts\python.exe -m scripts.local_runtime tls
Import-Certificate -FilePath .\runtime\local\private\localhost.cer -CertStoreLocation Cert:\CurrentUser\Root
```

Nếu port5433 đã có PostgreSQL, chọn đúng existing container/admin trong .env trước
lệnh docker; không tạo Compose thứ hai. Không overwrite .env/WIP có sẵn. Secrets
được tạo local, không in hoặc đưa Git. SMTP App Password do user tự nhập riêng.

## Chạy hằng ngày

```powershell
.\.venv\Scripts\python.exe -m scripts.local_runtime start
.\.venv\Scripts\python.exe -m scripts.local_runtime status
# Khi dùng xong:
.\.venv\Scripts\python.exe -m scripts.local_runtime stop
```

BE **https://localhost:8103**, exact FE Origin **https://localhost:5173**. FE chạy riêng;
launcher BE không sửa/chạy FE. Không migrate/reset/seed mỗi ngày; không dùng accounts.json
hoặc operator provisioning cho khách. Store mới trống cần import/config/completeness
có nguồn, không tự READY. Email/OpenRouter opt-in riêng, không gửi/call trong setup.

[**FULL_TEST_FLOW — hướng dẫn canonical A–D**](docs/runbooks/FULL_TEST_FLOW.md#customer-self-service)
chứa checkout mới, [.env.example](.env.example) từng nhóm/Gmail/callbacks,14 luồng API,
fixtures và recovery. Database `shelfcash_local` khác `shelfcash_local_test`; pytest/reset
chỉ dedicated test DB, chạy tuần tự. Không reset demo/development; không full-suite/
forecast accuracy claim từ targeted synthetic tests.

## Tài liệu và contract

- [Trạng thái](docs/CURRENT_STATE.md), [roadmap](docs/ROADMAP.md), [engineering rules](AGENTS.md).
- [Authorization/Store](docs/AUTHORIZATION_CONTRACT_VI.md#self-service-stores), [API chung](docs/API_CONTRACT.md).
- [Import](docs/IMPORT_MAPPING_API_CONTRACT_VI.md), [Planning](docs/PROCUREMENT_API_CONTRACT_VI.md), [Notifications](docs/NOTIFICATION_API_CONTRACT_VI.md).
- [Kiến trúc](docs/ARCHITECTURE.md), [domain](docs/DOMAIN_MODEL.md), [schema](docs/DATABASE_SCHEMA.md), [ADRs](docs/DECISIONS.md).
- [FE handoff/OpenAPI](docs/handoff/010_BE_CAPABILITY_RESPONSE_VI.md).
