# S4.2 — quyền Staff, lời mời và audit

CURRENT FACT S4.4 prerequisite: cursor HMAC now uses Auth-owned server-private
CursorSigner key with domain/session binding. Client cannot re-sign modified offsets
using their session token. Authorization/Store/filter/limit/list-version checks,
routes and DTOs stay unchanged. Restart requires cursor refresh. Evidence:
[historical scope notes (retired)](../runbooks/FULL_TEST_FLOW.md).

CURRENT FACT: source triển khai N12–N19 theo AUTH v1 mục4/6; evidence và giới hạn
ở [historical scope notes (retired)](../runbooks/FULL_TEST_FLOW.md). Không thay product policy,
không self-registration, chuyển Owner, xóa/reactivate membership hoặc one-time bypass.
Catalogue mô tả 37 action keys đã chốt, không chứng minh các API tương lai đã có.

## FE gọi gì

Tất cả route dưới `/api/v1`, dùng session/cookie S4.1, `credentials:include`.
Private response `data/meta/error`, no-store/no-referrer; `meta.request_id` và
pagination cho list. Owner-only là current active ownership đúng Store; Staff403,
Store/resource ngoài phạm vi404. Các mutations đòi Origin allowlist và CSRF hiện hành.

| ID | Route | Hành vi |
| --- | --- | --- |
| N12 | GET /stores/{store_id}/memberships | STAFF, active all/true/false, limit50/max100/cursor; catalogue + grants/version. |
| N13 | PUT /stores/{store_id}/memberships/{membership_id}/permissions | Full replace `{grants,reason}`; `[]` thu toàn grants; Idempotency-Key/If-Match; 200 + ETag. |
| N14 | GET /stores/{store_id}/permission-events | Store audit, optional membership_id; paging, thời gian giảm dần rồi UUID. |
| N15 | POST /stores/{store_id}/staff-invitations | `{email,grants,permission_catalog_version,reason}`, Idempotency-Key; 201 invitation + delivery queued; không token/account_exists. |
| N16 | GET /stores/{store_id}/staff-invitations | view=invitations: status/email/sort=-issued_at; view=events: invitation_id và limit/cursor; paging. |
| N17 | POST /stores/{store_id}/staff-invitations/{invitation_id}/actions | Reissue hoặc revoke, Idempotency-Key/If-Match; 200 invitation/delivery/event_id + ETag. |
| N18 | GET /staff-invitations/{invitation_id} | Session đúng verified account + X-Invitation-Token; offer/can_accept/reasons + ETag; không cần membership chưa tồn tại. |
| N19 | POST /staff-invitations/{invitation_id}/accept | `{token,accept:true}`, Origin/CSRF/If-Match/Idempotency-Key; 201 mới, 200 retained replay. |

Grants phải unique/sorted trong permissions-v2; reason không blank,1..1000.
Không auto-add prerequisites. Owner target422, inactive Staff409, stale CAS412,
missing If-Match428. N13 no-op giữ version, changed=false,event_id=null; có receipt,
không audit change giả. Request sau dùng current grants; session account không bị
logout toàn bộ khi thay quyền của một Store.

TECHNICAL CHOICE: Idempotency-Key opaque nonblank, tối đa128 UTF-8 bytes. Strong
quoted ETag output; If-Match nhận opaque version raw hoặc quoted, không wildcard/
weak/multiple. Fingerprint gồm canonical body và CAS, secret body chỉ qua digest.
Key scope actor+Store+method+resource route+action. Receipt được đọc sau current
authority, trước stale CAS; đổi body/CAS409. Receipt là historical result, không
apply lại grants, offer hoặc membership. FE refresh current list/T02 sau retry.

Cursor HMAC-SHA256 bind session/actor/Store/current authorization/filter/limit/list
fingerprint. Tamper/filter mismatch422; list snapshot thay đổi409, không trộn pages.
Count cùng snapshot. Implementation đọc list trong bộ nhớ và Store fence; đây là
giới hạn hiệu năng cần đo ở Store lớn, chưa claim load/performance acceptance.

## Consent, account và persistence

Create/reissue không tạo account/membership. Account chưa có phải qua assisted
account setup + verified-holder credential flow S4.1. N18/N19 kiểm session active,
account proof `verified_email/verified_at/verification_reference`, đúng target email.
Possession token không cấp quyền. Unknown token/UUID404 chung; wrong account403;
missing verification reference403. Email/session identity không còn hợp lệ vẫn
bị S4.1 guard401; không làm yếu guard để giữ session có email sai.

Token CSPRNG256bit, SHA-256 digest gắn bản ghi Store/email/STAFF purpose và revision;
7×24h từ issuance. Reissue rotate token/version, đổi issuer sang Owner executor,
bắt buộc review consent lại. Revoke không tạo/remove membership. accepted terminal.
Expired tính từ server clock, GET không ghi status; create mới có thể materialize
expired pending để nhường unique(Store,email). Existing membership kể cả inactive/
Owner409; không merge/reactivate/overwrite. Issuer phải còn active Owner đúng Store
khi accept; nếu mất authority cần Owner hiện hành reissue.

Migration0011 thêm5 tables, không backfill. Acceptance atomically ghi STAFF member,
exact grants, accepted invitation, permission/invitation events và retained receipt.
Grant triggers/revision S4.1 giữ nguyên. Replay kiểm current account/Store/member;
member inactive403, không resurrect rights. Receipt giữ grants/version tại acceptance,
T02 đọc quyền hiện tại. N14 có nguồn ASSISTED_PROVISIONING cho provisioning **mới**,
OWNER_CHANGE và INVITATION_ACCEPTANCE; actor acceptor riêng với issuer. Audit/receipt
append-only được PostgreSQL triggers bảo vệ UPDATE/DELETE; không purge endpoint.
Không fabricate audit backfill cho provisioning S4.1 trước migration này.

## Fence và lỗi

Owned synchronous Session. Recipient discovery chỉ quyết định lock order: Users
(recipient/issuer) UUID tăng dần → S4.1 session → Store → invitation/memberships.
Sau lock reload token/version/time/proof/current issuer; nếu reissue đổi issuer trong
discovery thì reject, không lấy lock User mới sai thứ tự. Owner writes giữ User →
session → Store → resource, cùng fence S4.1. Không dùng caller user_id/role/Store.

Thay quyền và acceptance rollback toàn aggregate khi audit/receipt/commit lỗi.
Commit/close/rollback errors dùng auth_session giữ primary + sanitized diagnostic;
không reconcile programming/unknown commit thành success. Có thể durable nhưng
HTTP503; client retry **cùng key/body/CAS**, server fresh current authorization rồi
đọc receipt đã commit. Không tự ghi FAILED cho transition đã durable.

TECHNICAL CHOICE: invitation create/reissue/revoke10 attempts/Store/10phút; invalid
CAS/catalogue cũng count, successful receipt replay không count. Recipient resolve/
accept30 attempts/account+IP/15phút. Counter được commit riêng trước mutation để
rollback không xóa throttle; 429 có Retry-After. Không trust forwarded IP tùy ý.

## Operator delivery

HTTP commit invitation + encrypted intent + audit + receipt, trả queued. Không SMTP
trong transaction/request. Configure privately: existing operator credentials,
SMTP TLS/sender và `AUTH_INVITATION_FRONTEND_URL` HTTPS page; thêm
`AUTH_DELIVERY_ENCRYPTION_KEY` là base64 của32 random bytes, giữ ngoài Git/logs.
AES256-GCM nonce random96bit, AAD versioned `invitation-delivery/1` bind Store,
invitation/email/issuance version/attempt. Raw token chỉ trong channel delivery,
không audit/receipt/plaintext DB/Owner response. Dependency cryptography phục vụ
use case encrypted retention thực tế, không thay auth provider.

Command kiểm operator authorization trước DB work:

```powershell
.venv/Scripts/python.exe -m scripts.dispatch_invitations --operator-id YOUR_OPERATOR_ID --limit 100
```

Nhập operator key bằng prompt ẩn; command không migrate/reset. Chỉ operator tự
chạy trên deployment đã cấu hình; task này không chạy vào development DB. Dispatcher
claim trong short transaction rồi đóng Session/connection trước decrypt/SMTP;
fresh transaction ghi confirmed outcome/audit, clear ciphertext sau delivery.
Fragment link chứa invitation_id/token; FE đọc vào memory rồi xóa fragment, không
query/localStorage/log. SMTP acknowledgment không chứng minh người nhận đọc email.

Provider exception = failed/not-confirmed, không grant. Reissue/revoke/accept clear
queued ciphertext và vô hiệu queued attempt; send đang in-flight có thể gửi mail cũ,
token đã rotate không dùng được. Dispatcher không overwrite revision mới bằng
outcome attempt cũ. Concurrent dispatcher claim cùng attempt chỉ một bên gửi.
Unknown claim/send/outcome commit không bịa success, không tự retry claimed attempt;
Owner reissue token mới để phục hồi. Không đảm bảo exactly-once email. Dispatcher
quét ciphertext expired kể cả crashed claim, bounded100 mỗi lượt; **cần operator
chạy định kỳ**. Không có background worker tự chạy hoặc crypto key rotation service.
Giữ key trong khi còn intents; đổi key cần drained queue hoặc Owner reissue.

Giới hạn: SMTP thật, browser FE, bounce/inbox, provider uncertainty thực tế, load và
security certification chưa kiểm chứng. Tests dùng real PostgreSQL + callback SMTP
kiểm thử, fault injection được ghi rõ trong task notes. S4.3 chưa bắt đầu.
