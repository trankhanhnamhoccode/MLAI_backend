# Notification — inbox cộng tác ShelfCash

<a id="notification-v1"></a>
## 1. Phạm vi và authority

ACCEPTED DECISION — Đợt 2: inbox trong ứng dụng cho account đang đăng nhập;
không browser push/SMS. Toàn bộ operations NF01–NF03 dưới đây là **DESIGN_READY**,
chưa có route/DTO/storage trong source. Quy ước wire, retry và bảng lỗi dùng
[bàn giao chung](API_CONTRACT.md#dot2-common). Không đổi authority của
[permissions](AUTHORIZATION_CONTRACT_VI.md#permission-requests) hoặc
[mapping](IMPORT_MAPPING_API_CONTRACT_VI.md#mapping-queue).

TECHNICAL CHOICE theo ủy quyền: recipient do backend resolve, không client chọn.
Một Notification thuộc một User, có Store nullable. Người dùng chỉ đọc/sửa read
state của chính mình. Sự kiện có Store chỉ hiện khi User/Store/membership đang
active; mất membership thì ẩn cả row/count/Store name. Membership phục hồi không
chứng minh quyền đọc object; quyền object luôn kiểm riêng. Không notification
permission mới và không grant qua notification.

## 2. DTO và bảo mật

```text
Notification = {
 notification_id: UUID, recipient_user_id: UUID,
 store: {store_id: UUID, name: string} | null,
 event_id: UUID, decision_id: UUID|null, event_type: string,
 occurred_at: Timestamp, created_at: Timestamp, read_at: Timestamp|null,
 title: string(1..200), body: string(1..1000),
 object: {type: permission_request|mapping_submission|membership,
          id: UUID, revision: Version|null},
 link: {path: string, availability: available|forbidden|unavailable} | null,
 version: Version
}
```

title/body là plain text template server, không HTML/LLM, không email của người
khác, workbook cells, tên món/nguyên liệu nhạy cảm, giá/budget hoặc grants nhạy cảm.
Thông báo đổi grants chỉ nói “Quyền tại quán đã thay đổi”; danh sách quyền lấy từ
T02 hiện hành. `object` chỉ chứa locator; `link.path` là FE relative path đã
allowlist theo type, không URL provider/storage. Thiếu quyền object trả link=null;
không thông báo chi tiết sự kiện gây lộ object. Read receipt không trả delivery
intent, errors provider hoặc secrets. Mọi deep link gọi API authority hiện hành;
không dùng event/decision/revision cũ để approve hoặc cấp quyền.

read_at=null nghĩa chưa đọc; có thời điểm nghĩa đã đọc. [] là không có thông báo
**hiện được phép hiển thị**. Count0 không chứng minh không có delivery đang chờ.
Unknown event_type mới: FE dùng title/body an toàn, chỉ link khi type được hỗ trợ.
ACCEPTED DECISION: read/unread không approve/reject/withdraw. Inbox là projection
của sự kiện, không task store: notification không hiện/mất/đã đọc không xóa pending
submission/request. FE khôi phục việc cần làm từ queue/detail qua current rights,
không từ notification count. Không thêm delete/dismiss endpoint để quản lý task.

## 3. Operations — DESIGN_READY

| ID | Method/path | FE và typed request | Response |
| --- | --- | --- | --- |
| NF01 | GET /notifications | Inbox; query store_id?:UUID, unread?:boolean, limit/cursor; không body. Bỏ store_id lấy toàn bộ Store accessible + account-scope; có store_id chỉ Store đó, không account-scope. | 200 data={items:Notification[]}; meta pagination + snapshot_id + observed_at. |
| NF02 | GET /notifications/unread-count | Badge; query store_id?:UUID, snapshot_id?:Version; scope giống NF01, không unread filter/body. | 200 data={unread_count:int>=0,scope:"accessible"|"store",store_id:UUID|null}; meta snapshot_id/observed_at. |
| NF03 | PATCH /notifications/{notification_id} | Body {read:boolean}; Origin/CSRF + If-Match + Idempotency-Key. true mark read; false đặt unread. | 200 data={notification_id,read_at:Timestamp|null,version:Version}; ETag version. |

Sort NF01 cố định -created_at/UUID. Snapshot pin visible membership set,
notification content/read revisions và authorization_version; count và list
cùng snapshot nếu cần nhất quán. Store không accessible404; đổi snapshot409
SNAPSHOT_NOT_AVAILABLE, FE refresh list/count. Badge phải refetch sau PATCH;
không cộng trừ từ page length. NF03 không bulk/dismiss/delete; không approve,
reject hoặc ghi quyết định nghiệp vụ. No-op read giữ timestamp/version, có receipt
retry; mark unread rồi read lại tạo read_at mới. Row recipient khác404, stale
ETag412 NOTIFICATION_REVISION_CONFLICT. GET chỉ đọc, không tạo notification.

Ví dụ NF01 data (meta/envelope theo quy ước chung):

```json
{"items":[{"notification_id":"00000000-0000-0000-0000-000000000031","recipient_user_id":"00000000-0000-0000-0000-000000000002","store":{"store_id":"00000000-0000-0000-0000-000000000001","name":"Quán A"},"event_id":"00000000-0000-0000-0000-000000000032","decision_id":null,"event_type":"permission_request.submitted","occurred_at":"2026-10-13T02:00:00Z","created_at":"2026-10-13T02:00:01Z","read_at":null,"title":"Có yêu cầu quyền mới","body":"Một nhân viên gửi yêu cầu quyền tại quán.","object":{"type":"permission_request","id":"00000000-0000-0000-0000-000000000033","revision":"request-1"},"link":{"path":"/stores/00000000-0000-0000-0000-000000000001/permission-requests/00000000-0000-0000-0000-000000000033","availability":"available"},"version":"notification-1"}]}
```

Ví dụ NF02 data và NF03 request → response data:

```json
{"unread_count":1,"scope":"store","store_id":"00000000-0000-0000-0000-000000000001"}
```

```json
{"read":true}
```

```json
{"notification_id":"00000000-0000-0000-0000-000000000031","read_at":"2026-10-13T02:01:00Z","version":"notification-2"}
```

## 4. Events, delivery và recovery — DESIGN_READY

| Event type v1 | Recipient và object |
| --- | --- |
| permission_request.submitted | Current active Owner(s) đúng Store; permission_request. |
| permission_request.approved / permission_request.rejected | Requester; permission_request và cùng decision_id với audit. |
| mapping_submission.submitted | Current active Owner(s) đúng Store; mapping_submission. |
| mapping_submission.approved / mapping_submission.rejected / mapping_submission.changes_requested | Submitter; mapping_submission và N5 decision_id. |
| membership.grants_changed | Staff bị đổi grants; membership và PermissionEvent ID làm event_id. |

Mapping events luôn trỏ `object.type="mapping_submission"` và **submission_id**,
không trỏ profile revision latest thay thế bản đã submit. Deep link mở MQ03 theo
Store/submission rồi lấy current state/review_eligibility/current_profile; pinned
proposal_revision/mapping_revision/spec_digest giữ immutable. Nếu proposal đổi sau
submit thì detail stale và Staff explicit resubmit ID mới; notification cũ không
duyệt nhầm revision mới. N5 vẫn command authority approve_activate/reject/retire
(request_changes là extension DESIGN_READY), queue không resolve sales/recipe/
supplier/inventory business conflict thay preview/resolutions.

Template mapping_submission.approved bắt buộc body:
**“Profile đã được duyệt; mở batch để kiểm tra và tiếp tục nhập.”**
title="Profile đã được duyệt"; không “Dữ liệu đã nhập thành công” hoặc giả batch
completed từ N5. Từ MQ03 detail người có quyền mở I04/M01 batch rồi preview/
resolutions/confirm_review/commit. Approved submission terminal chỉ ghi decision
lịch sử, không chứng minh approved version còn active/nonretired, không grant Staff
write, không tự commit. Các events reject/changes_requested chỉ nói kết quả review,
lý do đầy đủ đọc từ authorized detail, không đưa workbook/finance vào inbox.

Ví dụ NF01.items item mapping approval (decision/profile approval **chưa nhập dữ liệu**):

```json
{"notification_id":"00000000-0000-0000-0000-000000000091","recipient_user_id":"00000000-0000-0000-0000-000000000002","store":{"store_id":"00000000-0000-0000-0000-000000000001","name":"Quán A"},"event_id":"00000000-0000-0000-0000-000000000092","decision_id":"00000000-0000-0000-0000-000000000066","event_type":"mapping_submission.approved","occurred_at":"2026-10-13T02:05:00Z","created_at":"2026-10-13T02:05:01Z","read_at":null,"title":"Profile đã được duyệt","body":"Profile đã được duyệt; mở batch để kiểm tra và tiếp tục nhập.","object":{"type":"mapping_submission","id":"00000000-0000-0000-0000-000000000062","revision":"submission-2"},"link":{"path":"/stores/00000000-0000-0000-0000-000000000001/mapping-submissions/00000000-0000-0000-0000-000000000062","availability":"available"},"version":"notification-1"}
```

Request cancellation/satisfied/invalidated, mapping stale/withdrawn/retired có
trạng thái ở detail; không bắt buộc sinh thêm event v1. Nếu thêm loại sau này,
dùng cùng inbox operations. `import.completed`, `import.failed`, `incident.*` là
**DEFERRED**, extension vocabulary, chưa đăng ký producer v1.

Business decision + audit + durable notification intent cùng transaction local
PostgreSQL trong một backend process. Không gọi external delivery trong business
transaction. Nếu không lưu được intent thì rollback decision; nếu decision đã
commit, lỗi materialize inbox không undo decision. Intent có state
`pending|delivered|failed`, attempt:int, next_attempt_at nullable, safe error_code;
internal-only, không public endpoint mỗi event. Dedupe unique
(event_id,recipient_user_id,event_type), event_id ổn định từ audit/submit receipt;
delivery retry không tạo business decision hoặc notification mới.

Materialize trong transaction: recheck recipient hiện hành → insert-on-identity
và verify payload → mark delivered. Recipient không còn accessible: kết thúc
delivered với outcome suppressed; không chờ phục hồi để tiết lộ sự kiện cũ.
Transient DB failure giữ pending, backoff 1/5/30/60 giây rồi tối đa mỗi 5 phút;
invalid payload failed, giữ intent/audit để operator sửa dispatcher và retry cùng
event ID. Restart tiếp tục pending; uncertain commit đọc identity trước retry.
Không broker, không generic event framework, không email notification v1. Receipt
quyết định trả notification_delivery={status:"pending",event_id}; đây là durable
intent acceptance, không bảo đảm đã có inbox row hoặc SLA. FE dùng decision/detail
làm kết quả, refresh inbox định kỳ khi màn hình active (30 giây, kỹ thuật polling).

## 5. Errors, audit và acceptance

NF01–NF03 kế thừa lỗi chung; NF03 thêm412 NOTIFICATION_REVISION_CONFLICT.
NF01/NF02 invalid cursor/filter422, snapshot409;503 retry GET có backoff.
401 yêu cầu login;404 không tự tìm recipient/Store khác. Mutation receipt/read
state ghi actor/time/request ID, không trộn vào PermissionEvent/InvitationEvent;
không unified activity timeline. Delivery audit không chứa token/finance/provider
raw error. No-store và current authorization áp cả idempotent replay.

Acceptance khi implement: recipient isolation; revoke trước read/count/materialize;
finance-safe template/deep-link denial; count/list snapshot; read/unread CAS/no-op;
concurrent delivery/restart chỉ một row; decision committed + deliveryfail giữ
decision; missing intent rollback; failed payload recovery không tạo event mới;
notification read/hidden/missing không mất pending task; mapping approved wording
không báo canonical completion; old link đọc current stale/retired state, không
approve revision mới hoặc vượt current authority.
Đây là specifications, chưa chạy tests hoặc delivery thực tế.
