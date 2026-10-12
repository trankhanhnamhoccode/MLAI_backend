# Chạy và kiểm thử ShelfCash từ đầu đến cuối

## Phạm vi và chuẩn bị

**CURRENT FACT:** một backend Python/FastAPI với các thread Import, Planning và
PDF bật độc lập. Worker là phần xử lý job nền; ba flags mặc định OFF, demo bật
chúng trong private settings. Không cần provider trả phí hoặc kích hoạt mô hình
đã huấn luyện. Startup không migrate/reset/seed/call provider.

Cài Python3.11+, Docker Desktop với Linux containers và Docker Compose. Để chạy
FE cần Node>=22.22 và repo `Shelfcash_FE_v2` nằm cạnh `backend`. Microsoft Edge
chỉ cần cho browser harness tự động. Mở Docker Desktop trước khi dùng DB.

Mọi lệnh dưới đây chạy trong PowerShell tại **backend**, trừ đoạn có Push-Location:

```powershell
Set-Location D:\hocc_bk\ai\proj\projectMLAI\backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[dev]'
```

Nếu `.venv` đã có thì dùng lại. Không cần activate; gọi thẳng python trong venv.

| Môi trường | DB | BE | FE | Dữ liệu |
| --- | --- | --- | --- | --- |
| Development | shelfcash,5432 | 8000 | tùy cấu hình | dữ liệu của developer, không reset/migrate trong test release |
| Automated tests | shelfcash_test, local | TestClient/process theo test | không cần FE | fixtures riêng, được tests reset có guard |
| Demo S4.11 | shelfcash_integration_s411,5433 | 18001 | 5173 | synthetic riêng, có marker sở hữu/Store allowlist |

Store là quán; Owner là chủ quán; Staff là nhân viên. Quyền product không bao gồm
quyền reset/seed/admin DB. Không dùng dữ liệu khách thật trong profile demo.

## 1. Thiết lập demo mới — chỉ thực hiện một lần

Nếu đã có `runtime/s411/private/settings.json` và demo data thì sang mục2.
Init sinh cấu hình/bí mật riêng trong runtime bị Git ignore; không sửa root `.env`
để cấu hình launcher. Các lệnh này chỉ migrate DB demo có đúng guard, không DB
development. Không reset môi trường đang có dữ liệu để chạy lại.

```powershell
.\.venv\Scripts\python.exe -m scripts.integration init
docker compose --env-file runtime/s411/private/compose.env -f compose.integration.yaml up -d --wait
.\.venv\Scripts\python.exe -m scripts.integration migrate
.\.venv\Scripts\python.exe -m scripts.integration status
.\.venv\Scripts\python.exe -m scripts.integration start
.\.venv\Scripts\python.exe -m scripts.integration seed
```

Đúng target: role `shelfcash_integration`, host127.0.0.1:5433,
DB `shelfcash_integration_s411`, Compose project `shelfcash-integration-s411`,
named volume `integration-s411-data`. Guard chặn provider key/model live.

Seed demo là workflow riêng: application provisioning có audit → giao credential
qua kênh holder local → N7 hoàn tất mật khẩu; Owner mời Staff → Staff đăng nhập
và nhận lời. Không tự đăng ký Owner qua FE, không SQL cấp quyền/mật khẩu chung,
không SMTP thật. Demo có5 Products,1 Ingredient theo dõi hạn dùng,5 recipes,
70 sales có zero, supplier/term/NONE-fee evidence, completeness declarations,
hai opening lots gồm stock hết hạn. BASELINE/DEFAULT_BASE95 và budget1.000.000VND
là lựa chọn fixture, không mặc định nghiệp vụ. Staff ban đầu chỉ `menu.read`;
Owner/Store thứ hai kiểm chứng isolation. Seed không phải bước startup.

Cài dependencies FE nếu chưa có; đây là cài đặt local, không sửa source FE:

```powershell
Push-Location ..\Shelfcash_FE_v2
try { npm ci --no-audit --no-fund } finally { Pop-Location }
```

## 2. Khởi động/reuse để thao tác trên browser

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/local-integration.ps1 docker
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/local-integration.ps1 status
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/local-integration.ps1 start
```

Mở **http://localhost:5173/login**. BE health là
`http://localhost:18001/health`; schema là `/openapi.json` (`/docs` và `/redoc` tắt).
Health200 chỉ chứng minh process sống. Launcher kiểm DB head/sở hữu process và
port; reuse FE/BE thuộc launcher, không đổi port hoặc kill process khác.

Private config ở `runtime/s411/private/settings.json`; tài khoản ở `accounts.json`,
dataset/Store ở `dataset.json`. Mở bằng editor riêng, không cat credentials ra
log/chat, không đưa vào VITE/localStorage/Git. Config được load bằng
`Settings(_env_file=None)`, root `.env` không tác động launcher.

FE dùng `VITE_DATA_SOURCE=api`, `VITE_API_BASE_URL=http://localhost:18001`;
không thêm `/api/v1` vào base URL vì paths đã có. FE/BE cùng dùng localhost,
Origin đúng `http://localhost:5173`, requests có credentials include. Sau login
dùng CSRF hiện hành; mutation thêm key/CAS theo từng route. Cookie local
`shelfcash_dev_session` là HttpOnly/SameSite=lax, chỉ loopback; production giữ
Secure `__Host-shelfcash_session`.

**FE đang chạy thủ công:** kiểm trang login và Network trong browser; nếu API base
URL/mode/Origin đúng thì dùng lại. Không gọi launcher `start` cho FE không có
ownership metadata: nó sẽ từ chối port5173 đang bị process khác giữ. Chỉ bật BE:

```powershell
.\.venv\Scripts\python.exe -m scripts.integration status
# Chỉ khi BE18001 chưa chạy và không có ownership conflict:
.\.venv\Scripts\python.exe -m scripts.integration start
```

Nếu FE sai mode/base URL, dừng bằng Ctrl+C tại terminal đã chạy FE của bạn rồi
khởi động lại trong repo FE với hai VITE variables trên; không kill theo port.

Import/Planning/PDF workers đã chạy trong lifespan BE demo; không chạy thêm worker
trên cùng DB. Dispatcher lời mời không cần cho demo Owner hoặc local seed.
`scripts.dispatch_invitations` là tác vụ SMTP riêng, cần cấu hình delivery/HTTPS
và operator credential; không chạy để thử mapping hay gửi thư thật trong flow này.

## 3. Test như khách hàng trên browser

1. Login bằng Owner demo → chọn đúng Store. Nếu nhiều Store, FE phải cho chọn;
   Staff chỉ xem/thao tác theo grants hiện hành. Login200 không chứng minh có
   quyền import hoặc planning.
2. Vào Import, chọn business context date và files → upload → Analyze. Chờ job
   analysis xong; kiểm file đã nhận, file rejected và acknowledgment trước seal.
   Upload không ghi Menu/Sales/Kho.
3. Review từng sheet: loại dữ liệu, headers, field options, source context và
   identity. Unknown không tự IGNORE. Sheet không hỗ trợ phải được quyết định
   rõ với reason/ack; không map receipt thành kiểm kê lô. Lần đầu cần Owner duyệt
   toàn profile. Profile reuse vẫn không thay confirmation của batch.

   CURRENT FACT trên nhánh import sau tag v1.0: Owner đọc toàn spec và mappings,
   có thể duyệt nhóm RULE đủ điều kiện bằng N5 mà không xác nhận riêng từng cột.
   M01 `include_profile_details=true`, M02 `review_only=false` cho xem đầy đủ;
   candidates/reason/header_row/preamble_samples hỗ trợ review. Cột mơ hồ, ngoài
   schema và required facts thiếu vẫn phải xử lý trước. FE chưa được sửa/kiểm chứng
   cho cách duyệt nhóm này; nếu UI vẫn buộc từng cột, dùng workflow hiện hành hoặc
   các API trên theo [Import contract](../IMPORT_MAPPING_API_CONTRACT_VI.md).

   Số items review không phải số cột nghiệp vụ bắt buộc: còn classification,
   source context, identity và conversion issues. M03 mô tả requiredness theo
   từng schema; required-nullable vẫn cần giá trị/null rõ, không tự bỏ field.
   Chỉ IGNORE cột không dùng sau khi đọc ý nghĩa/evidence; business rule chưa hỗ
   trợ không trở thành optional chỉ vì không có target.
4. Preview → xem blockers/warnings/NEW/UNCHANGED/CHANGED/CONFLICT, giá trị trước/sau
   và các nhóm cần quyền ghi. Sửa mapping/context thì preview cũ mất hiệu lực.
   Thiếu fact thì bổ sung evidence đúng nghĩa, không nhập0/ngày upload để xanh.
5. Xác nhận review → Commit → chờ job terminal → đọc completion và refetch các
   màn hình liên quan. Preview/save/HTTP202 không chứng minh dữ liệu đã commit.
   Commit atomic: có blocker hoặc thiếu quyền một nhóm thì không ghi cả batch.
6. Readiness: xem từng thiếu sót; cấu hình requirements/budget theo phiên bản.
   Chọn Planning default/custom/saved → chạy → chờ đúng run_id hoàn tất. Không
   tự train, không stock depletion hay đặt hàng sau import/planning.
7. Xem phương án, winner, chi tiết nguyên liệu/lý do. Completed không có winner
   đủ điều kiện vẫn là kết quả hợp lệ; outcome/proof/search khác status. Lịch sử
   giữ input/result đã capture, thay stock/recipe hiện tại không sửa Run cũ.
8. Nếu UI có chức năng tương ứng, xem lịch sử và xuất PDF. API hỗ trợ N9/H01/H02,
   N10 yêu cầu PDF tiếng Việt, J01 polling, N11 tải riêng tư kiểm SHA/size/quyền
   hiện hành. PDF/lịch sử Planning UI còn thiếu; không coi API pass là UI pass.
   Export/view không lưu lựa chọn khách hàng và không tạo đơn mua.

**Giới hạn kiểm chứng:** người dùng đã thử FE thật tới mapping lần đầu; chưa có
bằng chứng toàn browser flow import → Planning thành công. S4.11 vẫn PARTIAL.
Rules v1.0 chỉ canonical keys/aliases hiện hành, chưa bao phủ headers demo. Adapter
OpenRouter tùy chọn đã có; manual/profile/rules hoạt động không cần provider.

Để kiểm API/native workers và committed state qua fresh SQLAlchemy Session trên
demo owned, các lệnh sau ghi thêm dữ liệu synthetic/output; chúng không phải
browser acceptance hoặc startup, không chạy trên developer/customer DB:

```powershell
.\.venv\Scripts\python.exe -m scripts.integration e2e
.\.venv\Scripts\python.exe -m scripts.integration cases
.\.venv\Scripts\python.exe -m scripts.integration restart-check
```

`e2e` kiểm import/readiness/planning/history/PDF, `cases` kiểm quota/ACK/CAS/seal/
profile/values/replay/current rights. `restart-check` so cookie/Run/PDF trước/sau
restart thuộc ownership. Upload bytes ở PostgreSQL import_blobs; PDF bytes riêng
tư ở app runtime còn được receipts/jobs tham chiếu, không purge như cache.

## 4. Dừng đúng process

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/local-integration.ps1 stop
# Khởi động lại process thuộc launcher nếu cần:
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/local-integration.ps1 restart
```

Stop chỉ dừng FE/BE có đúng incarnation/command metadata; Docker và volume còn.
FE thủ công dùng Ctrl+C tại terminal của bạn; BE khởi động riêng dùng
`python -m scripts.integration stop` với python trong venv. Không chạy launcher
stop khi5173 thuộc FE khác. Sau crash, `recover-stopped` yêu cầu process cũ được OS
xác nhận DEAD, port free và đúng DB/Store guards; ALIVE/UNKNOWN chặn, không sửa DB.

## 5. Automated tests — khác thao tác browser và seed

Chạy từ backend. `.env` có thể được tạo từ `.env.example` nếu chưa có; chỉ
cấu hình TEST_DATABASE_URL trỏ PostgreSQL local **shelfcash_test**. Không in URL có
password. Guard từ chối DB khác. Tests chạy tuần tự, reset/migrate fixtures chỉ DB
test; không migrate/reset development. Docker development service chỉ cung cấp
PostgreSQL, không cần upgrade schema shelfcash để chạy tests:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker compose up -d --wait --wait-timeout 90 postgres
.\scripts\test.ps1 unit
.\scripts\test.ps1 api
.\scripts\test.ps1 integration
# Full suite tại mốc release/tích hợp lớn:
.\scripts\test.ps1 all
.\.venv\Scripts\python.exe -m scripts.integration_contract_snapshot
```

Chọn targeted tests cho slice nhỏ theo AGENTS; không cộng các lần chạy overlap
thành tổng test độc lập. Full suite cho release chứa thay đổi rộng schema/quyền/
transaction. Quan sát commands/results trong hội thoại, không dùng PASS lịch sử.
OpenAPI check giữ fixture original10/10 `tests/fixtures/openapi_20261010.json`,
pinned SHA/provenance ở compatibility changelog; output runtime/verification/openapi.
Baseline32 →54 operations (22 thêm,6 đổi I01-I05/M04, không bỏ) là inventory của
v1.0, không chứng minh toàn UI. DTO examples ở docs/features/examples là synthetic.

Browser harness tự động (không mocks/interception) cần demo owned đang chạy:

```powershell
npm ci --prefix scripts/browser --no-audit --no-fund
node --check scripts/integration_browser.mjs
node scripts/integration_browser.mjs
```

Manifest/lock ở scripts/browser; node_modules/reports/screenshots bị ignore.
Resume flags cần cùng dataset và prior report, không dùng sau reset.

## 6. Development mới, lỗi thường gặp và reset

Chỉ khi chủ động thiết lập DB development mới: cấu hình root `.env` theo
`.env.example`, chạy Docker như mục5, `scripts/db_status.ps1 -AllowUnmigrated`,
`alembic.exe upgrade head` trong venv, rồi `scripts/db_status.ps1`. BE chạy bằng
python venv `-m uvicorn app.main:app --host 127.0.0.1 --port 8000`. Worker flags
cần bật rõ nếu thực hiện jobs; `seed_demo` chỉ kiểm schema, không tạo dataset.
Schema source head0017/60 bảng; health không xác nhận DB. Volume development
`shelfcash-postgres-data` giữ qua restart; đổi Compose password không đổi role
password trong volume đã init. POSIX wrappers tồn tại nhưng runtime chưa certified.

| Dấu hiệu | Xử lý |
| --- | --- |
| Docker API unavailable | Mở Docker Desktop, chờ engine Linux sẵn sàng, kiểm docker ps |
| DB không đúng head | Kiểm target/config trước; chỉ upgrade target đã chủ động chọn, không reset development |
| Port/PID ownership conflict | Dùng process hiện có nếu đúng config; không kill/đổi port tùy tiện |
| CORS/login không giữ cookie | localhost cả FE/BE, đúng Origin5173, credentials include, không thêm /api/v1 vào base URL |
| Staff403 | Refresh quyền, Owner cấp đúng grants; không bypass bằng key/membership giả |
| Job queued mãi | Kiểm worker flags/private log và native lifespan; không chạy worker thứ hai trên cùng DB |
| Mapping/preview bị stale | Refresh revision, review lại thay đổi, preview lại; không reuse confirmation cũ |
| Readiness bị chặn | Xem missing/unknown/ambiguous facts và evidence, không bịa unit/date/MOQ/fee |

Reset là hành động phá dữ liệu riêng, không thuộc startup/release. Local reset
wrappers chỉ cho shelfcash/shelfcash_test, test mode chỉ shelfcash_test. Dừng
clients, backup dữ liệu muốn giữ trước; không xóa volume/kill arbitrary sessions.
S4.11 reset-disposable cần đúng marker/Store allowlist/matched server exit/no
clients; không có Store-only reset. Giữ private artifact generations, audit,
provenance, models và retained PDF theo chính sách retention đã được duyệt.

## 7. Kiểm synthetic engine không cần DB/provider

Inputs/oracles nằm trong source/fixtures, outputs ở ignored runtime/verification.
Timing native không chứng minh chất lượng forecast hay exact infeasibility:

```powershell
.\.venv\Scripts\python.exe -B -m scripts.review_planning_verification
.\.venv\Scripts\python.exe -B -m scripts.benchmark_procurement_v2
.\.venv\Scripts\python.exe -B -m scripts.verify_procurement_v2_benchmark
.\.venv\Scripts\python.exe -B -m scripts.benchmark_decision_pipeline_v2
.\.venv\Scripts\python.exe -B -m scripts.benchmark_planning_setup
```

`review_planning_verification --benchmark-directory <directory>` kiểm thêm typed
results từ planning_setup mới chạy. Không ZIP/handoff bundlers. Semantics ở
[API](../API_CONTRACT.md), [Import](../IMPORT_MAPPING_API_CONTRACT_VI.md),
[Authorization](../AUTHORIZATION_CONTRACT_VI.md), [Planning](../PROCUREMENT_API_CONTRACT_VI.md);
[CURRENT_STATE](../CURRENT_STATE.md) tách runtime facts khỏi proposals.
