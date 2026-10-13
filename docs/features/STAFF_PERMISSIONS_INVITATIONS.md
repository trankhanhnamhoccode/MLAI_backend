# S4.2 — quyền Staff, lời mời và audit

## CURRENT FACT — B4 catalogue and linked acceptance

Catalogue permissions-v3 contains43 keys. The six History descriptors are identical
to Import A2; all37 old descriptors remain intact. Owner grants are Store-scoped;
existing Staff does not receive new keys. N12/T02 expose v3, N13 accepts an explicit
sorted grant set up to43, and N15/N17 require the current catalogue version.
Retained v2 offers need Owner reissue/review. N19 OpenAPI now has accept const:true;
false/numeric1/string"true" still return422. No route or consent semantics changed.

CURRENT FACT: integrated0024 joins Auth0023 and Import0021. Both CHECK upgrades
retain grants and versions; integration-only downgrade repairs preserve v3 while
the companion branch still requires it and block final removal of retained keys.
Original Auth0fbb979 had an independent0023 head. Source worktrees/DBs remain
unchanged; [schema contract](../DATABASE_SCHEMA.md) owns the merged traversal.

The combined test exercises both verified and not-yet-registered invitees through
public signup, fake mail, verification, HTTP login/offer/accept, live grant updates,
multi-Store isolation, decline/new identity, and reset/relogin. It asserts committed
state through fresh SQLAlchemy sessions. Membership deactivation is verified through
the existing persistence boundary, since no public deactivation endpoint is added.
Fake delivery restart is also exercised in a separate Python process. Existing
B1/B2/B3 suites own lifecycle/fault/race coverage; rerunning overlapping cases does
not create a unique aggregate count or a full-suite claim. Browser acceptance and
real credential-email workflows remain pending; Gmail smoke inbox was user-confirmed.

## CURRENT FACT — B3 invitation decline

IN01 POST `/api/v1/staff-invitations/{invitation_id}/decline` takes `{token,reason}`
and returns200 DeclineReceipt in the existing envelope. An active verified target
session, exact Origin, X-CSRF-Token, If-Match and Idempotency-Key are required;
membership is not required. Reason is nonblank1..1000 characters, token1..512
UTF-8 bytes/write-only. N18 is an authenticated offer, not anonymous authority.

Pending→declined atomically advances version, records declined_at, consumes
mutation capability, writes InvitationEvent DECLINED and idempotency receipt,
and cancels queued delivery secrets. No membership/grants/permission events,
Store access, email or notification is created. Receipt contains invitation_id,
store_id,status,declined_at,version,event_id,next_action=return_to_stores.

Sorted User→session→Store→invitation locks serialize accept/decline/revoke and
recheck holder/proof/token, Store, current active Owner issuer, expiry and pinned
grants/catalog. IN01 wrong holder/token404; N18/N19 retain wrong-holder403.
Expired/revoked410, absent If-Match428, stale pending revision412 and incompatible
terminal409. N19 still requires accept:true; false stays422.

N16 supports declined and DECLINED events. Invitation/InvitationOffer gain nullable
declined_at; N18 gains can_decline, with both capabilities false for declined even
without membership. N17 cannot reissue/revoke declined409 INVITATION_STATE_CONFLICT.
Owner creates a new identity through N15; declined does not block its acceptance.

Replay uses the same key/body/original If-Match after current account/token/Store/
issuer proof, without requiring unused capability or membership. It never repeats
transition or authority writes. A different body/CAS with the same key gives409
IDEMPOTENCY_KEY_REUSED; lost commit acknowledgment is recovered by request replay.
Pre-commit failure rolls back transition/event/receipt/secret cancellation. The
existing30-attempt recipient/account+IP/15-minute throttle is shared with accept.

Migration0022 is additive on Auth0020. Verification uses only guarded Auth test DB
and fake delivery. The Gmail demo and FE source/config are untouched; browser UI
is an FE-owned prerequisite. Canonical product authority remains
[Authorization](../AUTHORIZATION_CONTRACT_VI.md#auth-self-service).
CURRENT FACT: B3 backend/fake-delivery acceptance is COMPLETE. Fresh-session
assertions and fault/race cases cover all accepted transition/replay/no-authority
invariants, alongside relevant invitation/B1/B2/session/schema regressions.
Commands/results are reported in the conversation; no fresh full-suite claim.

CURRENT FACT S4.4 prerequisite: cursor HMAC now uses Auth-owned server-private
CursorSigner key with domain/session binding. Client cannot re-sign modified offsets
using their session token. Authorization/Store/filter/limit/list-version checks,
routes and DTOs stay unchanged. Restart requires cursor refresh. Evidence:
[historical scope notes (retired)](../runbooks/FULL_TEST_FLOW.md).

HISTORICAL INFORMATION S4.2: source triển khai N12–N19 theo AUTH v1 mục4/6; evidence và giới hạn
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
| N18 | GET /staff-invitations/{invitation_id} | Session đúng verified account + X-Invitation-Token; offer/can_accept/can_decline/reasons + ETag; không cần membership chưa tồn tại. |
| N19 | POST /staff-invitations/{invitation_id}/accept | `{token,accept:true}`, Origin/CSRF/If-Match/Idempotency-Key; 201 mới, 200 retained replay. |

Grants phải unique/sorted trong permissions-v3; reason không blank,1..1000.
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

Create/reissue không tạo account/membership. Account chưa có có thể qua B1 signup/verification hoặc assisted
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
