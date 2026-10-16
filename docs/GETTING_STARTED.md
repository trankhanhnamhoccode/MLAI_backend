# Bắt đầu với ShelfCash backend

Trang này là nguồn chính cho setup và chạy local trên Windows/PowerShell.
Các lệnh dưới đây chạy từ **repo root**, dùng `.venv` của chính checkout này.
Đây là hướng dẫn theo tooling hiện có, không phải chứng nhận fresh-clone hoặc
browser E2E đã chạy trên source hiện tại. [CURRENT_STATE](CURRENT_STATE.md) phân
biệt source, deployment và các kết quả kiểm chứng có phạm vi riêng.

<a id="first-time-setup"></a>
## A. Prerequisites và clone sạch

Cần Git, Python 3.11+ tương thích dependencies trong [pyproject.toml](../pyproject.toml),
Docker Desktop với Linux engine đang hoạt động và PowerShell. Các gói ML/native
cũng được cài theo pyproject; lỗi wheel/dependency phải được xử lý trước khi setup
DB. `tzdata` đã được khai báo cho IANA timezone trên Windows.

Trong thư mục cha do bạn chọn, chỉ clone khi thư mục đích chưa tồn tại:

```powershell
git clone --branch main https://github.com/trankhanhnamhoccode/MLAI_backend.git backend
Set-Location .\backend
```

Nếu đã có checkout, mở PowerShell tại repo root; không clone đè hoặc bỏ WIP.
Clone không mang theo `.env`, venv, DB, certificate, tài khoản hay private runtime.
Thay đổi chưa commit cũng chưa có trong bản clone từ remote; xem baseline của
[handoff FE](handoff/010_BE_CAPABILITY_RESPONSE_VI.md) trước khi đối chiếu capability.

## B. Venv và dependencies

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[dev]'
```

Dùng trực tiếp interpreter này, không cần activate hoặc mượn venv worktree khác.
Nhóm `dev` cung cấp cả `httpx` mà launcher dùng cho HTTPS probes.

<a id="configuration"></a>
## C. Cấu hình tối thiểu

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
.\.venv\Scripts\python.exe -m scripts.local_runtime secrets
notepad .env
```

`.env.example` là [nguồn tên settings và defaults](../.env.example).
`secrets` thay placeholders mật khẩu DB/Docker và tạo encryption key riêng trong
ignored `.env`; giữ giá trị thật đã có, backup file trước khi sửa và không in secrets.
Không đổi encryption key khi còn email intents cần giải mã.

| Nhóm | Cấu hình tối thiểu / điều kiện |
| --- | --- |
| DB runtime / migration / test | Giữ ba URL riêng của template: `shelfcash_local_runtime` và `shelfcash_local_migrator` dùng `shelfcash_local`; `shelfcash_local_tester` chỉ dùng `shelfcash_local_test`. Loopback `127.0.0.1`, port mặc định 5433. Password tự nhập phải URL-encode. |
| Docker admin | `POSTGRES_USER/PASSWORD/PORT`, `LOCAL_POSTGRES_CONTAINER` dành cho volume mới hoặc instance hiện hữu đã xác minh. Đổi initial password trong env không đổi password của role cũ. |
| Storage | Giữ các directory dưới `runtime/local/app` trong checkout này. Không mượn uploads/model artifacts/private files của checkout khác. |
| HTTPS và Origin | Mặc định BE `https://localhost:8103`, FE Origin chính xác `https://localhost:5173`, `AUTH_DEV_COOKIE=false`. FE dùng credentials include và chạy riêng; launcher không setup/chạy FE hoặc certificate cho FE. |
| Business workers | Template bật `IMPORT_WORKER_ENABLED`, `PLANNING_WORKER_ENABLED`, `PDF_EXPORT_WORKER_ENABLED`, `NOTIFICATION_WORKER_ENABLED` trong cùng một backend process. Application defaults vẫn OFF; tắt một worker có thể để công việc tương ứng chờ. Không chạy thêm dispatcher trùng. |
| Email | Để `AUTH_EMAIL_DELIVERY_ENABLED=false` khi chưa đủ SMTP/key/callback. Đăng ký tài khoản mới cần email capability; xem mục F. |
| LLM | Giữ Import/Summary/Chat OFF nếu chưa cần. `OPENROUTER_API_KEY` riêng tư không tự bật bất kỳ chức năng nào. |

Cấu hình nâng cao nằm tại nguồn chuyên biệt:

- [Email verification](features/AUTH_SESSION.md#b1-configuration-and-fe-flow),
  [password reset](features/AUTH_SESSION.md#b2-configuration-and-fe-flow) và
  [Authorization self-service](AUTHORIZATION_CONTRACT_VI.md#auth-self-service):
  SMTP_SSL/465, sender, key và HTTPS callback đúng purpose. Adapter không dùng STARTTLS/587.
- [Import mapping](features/IMPORT_STAGING_PREVIEW.md): `IMPORT_LLM_SUGGESTIONS_ENABLED`
  và `OPENROUTER_MAPPING_*`; model/key và bounds riêng.
- [Summary / Chat](features/DECISION_ASSISTANT.md):
  `SUMMARY_*` và `CHAT_*` độc lập; model, provider routing và bounds theo feature.
  Summary synchronous, không cần thêm worker. Đổi settings cần stop/start để nạp lại.

SMTP smoke là thao tác gửi mail riêng, không phải bước setup mặc định và không
chứng minh verification callback hoạt động. Không đặt key/password/token vào FE,
Git, chat hoặc shell history.

## D. Docker, database và TLS — chỉ setup lần đầu

Kiểm `.env` trước khi chạy. Nếu port DB đã có instance khác, chọn đúng
container/admin đã xác minh; launcher từ chối tạo Compose thứ hai tranh port.
Máy mới dùng [compose.local.yaml](../compose.local.yaml) với named volume riêng.

```powershell
.\.venv\Scripts\python.exe -m scripts.local_runtime docker
.\.venv\Scripts\python.exe -m scripts.local_runtime init-db
.\.venv\Scripts\python.exe -m scripts.local_runtime migrate
.\.venv\Scripts\python.exe -m scripts.local_runtime tls
Import-Certificate -FilePath .\runtime\local\private\localhost.cer -CertStoreLocation Cert:\CurrentUser\Root
```

`init-db` tạo hai DB local/test và các role hạn chế; không overwrite credentials
của DB/role có sẵn. DB hiện hữu thiếu ownership marker bị từ chối. `migrate`
chỉ dành cho schema chưa có Alembic; chạy tới source head, không reset/stamp/seed.
DB test được fixture quản lý riêng; xem [TESTING](TESTING.md).

`tls` tạo key/certificate của checkout này. Chỉ trust public `.cer` trên máy browser,
giữ private key riêng. Tool tạo certificate có hạn 30 ngày, không tự gia hạn/thay
certificate đã có. Incomplete/expired TLS cần recovery có kiểm soát, không bỏ verify.

Sau setup, DB phải khớp graph/metadata của source; không dùng số bảng hoặc head
của một acceptance cũ làm expected state. `status` bên dưới kiểm sự khớp này.
Setup không tạo User, Store, dữ liệu kinh doanh, không tự bật SMTP/LLM.

<a id="daily-use"></a>
## E. Chạy và dừng hằng ngày

Chạy từ repo root sau setup:

Docker engine và container DB cần đang chạy. Nếu container đã dừng sau reboot,
khởi động lại bằng `.\.venv\Scripts\python.exe -m scripts.local_runtime docker`
trước `start`; không chạy lại init/migrate hoặc tạo volume mới.

```powershell
git status --short
.\.venv\Scripts\python.exe -m scripts.local_runtime start
.\.venv\Scripts\python.exe -m scripts.local_runtime status
# Khi dùng xong:
.\.venv\Scripts\python.exe -m scripts.local_runtime stop
```

**Start yêu cầu source sạch và đã commit.** Nếu checkout đang review WIP, launcher
sẽ từ chối; giữ WIP và hoàn tất review theo quy trình của nhóm trước khi chạy.
Không discard hoặc tự commit thay người khác để vượt guard.

`status` báo DB/schema, source SHA/root, configuration match, worker observations
và từng email capability. Health chỉ liveness, không xác nhận feature/DB/browser
acceptance. FE chạy riêng tại Origin đã cấu hình. Không init/migrate/seed/reset
mỗi ngày; thay source/settings cần kiểm tra và stop/start đúng process đang sở hữu.

<details>
<summary>Source mới cần migration: upgrade có backup</summary>

Chờ công việc queued/running hoàn tất, rồi chạy:

```powershell
.\.venv\Scripts\python.exe -m scripts.local_runtime stop
.\.venv\Scripts\python.exe -m scripts.local_runtime backup
.\.venv\Scripts\python.exe -m scripts.local_runtime upgrade
.\.venv\Scripts\python.exe -m scripts.local_runtime start
```

Backup giữ DB dump, config và counts ngoài Git. Upgrade kiểm ownership, process
DEAD, không pending work và backup khớp; kiểm counts bảng cũ sau migration.
Nếu lỗi, giữ backup/evidence để điều tra; không tự downgrade/stamp/reset/restore đè.

</details>

<a id="onboarding"></a>
## F. Signup → xác minh email → login → tạo Store

**Email thật có điều kiện:** cần SMTP/sender hợp lệ, encryption key, email worker
và `AUTH_VERIFICATION_FRONTEND_URL` trỏ HTTPS page cùng allowed Origin, có consumer
gọi A05. Theo trạng thái tài liệu hiện tại, signup/EMAIL_VERIFY/create Store phía
FE chưa được xác nhận đầy đủ; template để verification URL trống. Không thay bằng
page SETUP/RESET gọi N7 vì khác purpose. Audit tĩnh không chứng minh browser flow.

Khi callback và capability đã được triển khai/cấu hình đúng, dùng luồng API sau;
payload/headers/errors theo [OpenAPI](handoff/openapi.json) và
[Authorization](AUTHORIZATION_CONTRACT_VI.md#self-service-stores):

1. Đăng ký qua `POST /api/v1/auth/register`. Accepted không cấp session hay Store.
2. Mở email, callback hoàn tất `POST /api/v1/auth/email-verifications/complete`
   bằng token và password của holder; không tự login. Hết hạn thì yêu cầu lại
   qua `POST /api/v1/auth/email-verifications/request`.
3. Login qua `POST /api/v1/auth/login`, lấy current session/CSRF và Store context.
4. Holder active, verified, credential-ready gọi `POST /api/v1/stores` với
   name/timezone/currency tự chọn; dùng current Origin/CSRF và Idempotency-Key.
   Store/Owner được tạo atomically; timeout giữ nguyên key/body để replay.
5. Store mới trống: nhập/review facts, completeness và cấu hình theo
   [Import](IMPORT_MAPPING_API_CONTRACT_VI.md), [Planning](PROCUREMENT_API_CONTRACT_VI.md).
   Có Store không đồng nghĩa đủ dữ liệu để tính. [Runbook C](runbooks/FULL_TEST_FLOW.md#c14-luồng-khách-hàng-theo-namnguyên)
   giữ checklist các luồng tiếp theo.

**Không SMTP/OpenRouter:** có thể dùng core computation và deterministic
explanation với account/dữ liệu/config đã chuẩn bị hợp lệ, nhưng không hoàn tất
onboarding email mới chỉ bằng template mặc định. Register/resend/forgot có thể trả
503 khi capability thiếu. Demo Owner/Staff là lựa chọn synthetic riêng tại
[runbook local accounts](runbooks/FULL_TEST_FLOW.md#local-test-accounts).
Các scripts seed forecast/planning đang WIP local, chưa thuộc hướng dẫn đã phát hành.
Không coi seed hoặc DB trên máy tác giả là dữ liệu clone.

<a id="troubleshooting"></a>
## G. Troubleshooting

| Dấu hiệu | Kiểm tra / recovery |
| --- | --- |
| Cài dependencies lỗi | Kiểm interpreter/platform và requirements trong pyproject; xử lý lỗi pip cụ thể, không mượn sibling venv để coi clone đã chạy. |
| Port 5433 đã dùng | Xác minh container/admin hiện hữu trong env; không tạo Compose thứ hai hoặc reset volume. |
| DB auth/marker/role lỗi | Kiểm ba URLs khác initial Docker credentials; giữ partial setup để điều tra, không sửa marker hay overwrite role/password cũ để vượt guard. |
| DB head/schema khác source | Đối chiếu checkout và migration graph; DB đã có Alembic dùng backup-aware upgrade, không first-time migrate/stamp/reset. |
| Dirty source / config mismatch | Review WIP trước khi chạy; stop/start đúng process để nạp source/config đã duyệt. Không kill mọi Python process. |
| TLS lỗi | Kiểm own cert, trust, SAN và expiry. Renew cần backup/stop/thay/trust có kiểm soát; tool không tự renew. |
| Register/resend/forgot 503 | Kiểm flag và từng `email_capabilities` từ status; callback verification còn thiếu thì SMTP smoke không lấp được gap. |
| Mail chưa tới / token hết hạn | Kiểm sender/provider/private logs/spam; dùng resend/reissue đúng workflow. Không chạy hai email dispatchers hoặc tự phát lại unknown delivery. |
| 401/403/404 | Kiểm session, Origin/CSRF, current membership/grants đúng Store; biết UUID không cấp quyền. |
| 409/412/428 | Refetch version và review theo contract; lost ACK replay cùng key/body, không đổi key để né conflict. |
| Queued / readiness blocked | Kiểm từng worker và missing facts/config/completeness; không seed ngầm hoặc coi unknown là zero. |
| Stop/status lỗi observation | Launcher retry có giới hạn khi replace `workers.tmp` → `workers.json`; status vẫn từ chối stale observations. Giữ manifest/private files, xác minh PID/birth/run_id và job state trước recovery. Forced stop không chứng minh graceful shutdown. |

Tests và reset chỉ dành cho DB test được allowlist, chạy tuần tự; đọc
[TESTING](TESTING.md) trước khi chọn profile. Manual acceptance/history có scope
riêng tại [FULL_TEST_FLOW](runbooks/FULL_TEST_FLOW.md); không dùng kết quả cũ làm
chứng nhận source/deployment hoặc forecast accuracy hiện tại.
