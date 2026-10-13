# S4.3 — Menu, công thức và Kho public reads

CURRENT FACT S4.4 prerequisite: all cursor callers now reuse the same private-key
CursorSigner primitive. T01/Staff's old signing noted below is historical S4.3
completion state, fixed and verified in [current verification runbook](../runbooks/FULL_TEST_FLOW.md).
S4.3 snapshot/DTO/business semantics remain unchanged.

CURRENT FACT — source hiện hành triển khai P01/P02/V01–V04 dưới `/api/v1`.
Authority: [handoff v1](../API_CONTRACT.md),
[Catalog](../API_CONTRACT.md#catalog-semantics),
[Inventory](../API_CONTRACT.md#inventory-semantics),
[AUTH v1](../AUTHORIZATION_CONTRACT_VI.md#auth-v1).
Các ghi chú “DESIGN ONLY/chưa HTTP” trong bản contract là evidence lịch sử lúc
thiết kế; không thay đổi wire contract. Evidence thực chạy và giới hạn được ghi
riêng trong [current verification runbook](../runbooks/FULL_TEST_FLOW.md).

## FE gọi gì

GET đều dùng secure session cookie S4.1, không body hoặc CSRF mutation header.
Response là typed `data/meta/error`, `Cache-Control: private, no-store`.

| ID | Route sau `/api/v1/stores/{store_id}` | Query |
| --- | --- | --- |
| P01 | `/products` | q, status active/paused, sort name/-name/selling_price/-selling_price, limit/cursor |
| P02 | `/products/{product_id}` | Không query |
| V01 | `/inventory` | q, repeated ingredient_id, status enum phân cách dấu phẩy, sort name/-name/nearest_expiry, limit/cursor |
| V02 | `/inventory/{ingredient_id}` | snapshot_id?, lot_limit |
| V03 | `/inventory/{ingredient_id}/lots` | snapshot_id?, limit/cursor, sort=expiry_date,batch_code |
| V04 | `/inventory/{ingredient_id}/movements` | snapshot_id?, limit/cursor, sort=-occurred_at |

Limit mặc định50, tối đa100; UUID canonical; q trim1..200. Query lạ/lặp không
được hỗ trợ bị422. Summary là toàn Store; pagination.total_count là filtered
result, không dùng số dòng trang thay tổng. Price null khác0, paused vẫn đọc được.
Search tiếng Việt bỏ dấu/case; Product search chỉ name, Inventory name hoặc SKU.
Name/price/expiry ties dùng UUID tăng dần, nullable sort keys ở cuối.

P01 cần menu.read; count chỉ có khi đủ recipe.read + ingredient.read, nếu thiếu
quyền là null/forbidden và không có recipe warnings. P02 cần cả ba quyền và chặn
toàn response khi thiếu. Công thức chọn tại ngày hôm nay theo timezone Store,
bounds inclusive, không chọn latest version để lấp gap. Missing recipe khác
recipe rỗng. Quantity line cho toàn yield; loss giữ nguyên, không tính BOM tại GET.

V01–V04 cần inventory.read + ingredient.read. Cost lot chỉ được query khi có
procurement.cost.read; thiếu quyền trả required cost object forbidden/null.
Không sort/filter/valuation theo cost. Không grant thêm quyền qua menu.read.
Membership/grants hiện hành được kiểm trước và sau snapshot; Store/resource
ngoài scope trả404, thiếu action trong Store có quyền truy cập trả403.

## Facts Kho và giới hạn hiện hành

Physical là SUM balance đã ghi nhận, giữ cả expired; usable là phần dương được
dùng trong ngày đọc; expiry ngày X dùng được ngày X, X+1 hết hạn. Near expiry
0..7 ngày inclusive, loại expired/null expiry. Received date null có warning;
future receipt bị loại và usable toàn Ingredient unknown. Tracked lot dương
thiếu expiry cũng unknown, vẫn trả usable_known_quantity cho phần xác định.
Nontracked expiry null được dùng kèm warning. Unit exact, không g↔kg.

Chưa có adapter declaration completeness hoặc Owner threshold: **mọi Ingredient
trả stock_completeness UNKNOWN**, low_stock_assessment unknown/null. Không có
lô vẫn recorded0/UNKNOWN, không xác nhận empty. Summary low count null khi có
Ingredient chưa đánh giá được, empty catalog count0. Primary status hiện có thể
near_expiry hoặc watch; đây là kết quả facts thiếu completeness/threshold, không
placeholder hay tự gán threshold. S4.6 mới có trách nhiệm sources/editor.

Lot location unsupported/null. Old writers không có provenance đủ chứng minh
OPENING_STOCK/ACTUAL_RECEIPT nên origin UNKNOWN. Movement actor null/origin UNKNOWN;
reason/reference giữ nguồn thật. recorded_at lấy created_at, không giả bằng
occurred_at. Signed six canonical movement kinds; trang history không dựng lại
balance lịch sử. GET không tạo movements hoặc giảm expired balance.

## Snapshot, numeric và capacity — TECHNICAL CHOICE

Migration0012 thêm metadata-only public_read_revisions: menu/recipe/inventory
counters theo Store. Triggers INSERT/UPDATE/DELETE tăng revision **trong cùng
transaction nguồn**, kể cả ABA/delete, không dựa max(updated_at). Counter mới
cho Stores cũ không backfill facts nghiệp vụ. Store DELETE cascade metadata;
schema/lifecycle/business writers S1/S2/S3 giữ nguyên semantics.

Mỗi request có owned READ ONLY REPEATABLE READ cấu hình trước SQL đầu tiên.
Auth bookkeeping dùng short Session riêng. Projection detach trước serialization;
không giữ connection/transaction giữa requests. Snapshot/version opaque HMAC
bound actor/session/Store/date/timezone/currency/authorization/source revisions.
Khóa ký private do PublicReads instance sở hữu, không dùng riêng session token
mà client nắm giữ làm signing key; không persist/log/expose khóa. Một backend
process giữ cùng instance giữa requests. Restart thay khóa: cursor cũ422
INVALID_CURSOR, explicit snapshot_id cũ409; FE refresh từ trang đầu. Không hứa
retained paging xuyên restart. Các cursor auth/Staff S4.1/S4.2 hiện vẫn dùng
cơ chế ký cũ theo session token, không được sửa trong S4.3; private-key hardening
ở đây chỉ áp dụng sáu reads mới, không phải chứng nhận security cả auth surface.
Menu-only token và updated_at không chứa recipe revision/timestamp bị cấm đọc.
Inventory token gồm catalog + inventory; hiện chưa có threshold storage revision.

Keyset cursor thêm filters/order/limit/resource. Tamper/cross-filter/scope422;
source change/date rollover409 LIST_VERSION_CHANGED hoặc SNAPSHOT_NOT_AVAILABLE.
FE refresh cả set khi409. V02 initial lot page và summary cùng snapshot; cursor
trang lô dùng tiếp V03 với cùng limit và snapshot_id. Không retained historical
read service; request cũ có thể trả snapshot vừa hết current do concurrent commit,
nhưng response không trộn facts và trang kế tiếp bị409.

Decimal plain string giữ exact giá trị/scale; không arithmetic Python ambient
context, epsilon, fixed rounding hoặc đổi unit. Money tối đa18 integer/18 fraction
digits theo contract; quantities không lấy money bounds. NaN/Infinity/invalid
unit/overlap/source graph fail503, không bỏ dòng hoặc trả empty giả. Negative zero
signed wire được bỏ dấu. Không forecast/solver/LLM trong path đọc.

Capacity kỹ thuật: tối đa1MiB serialized UTF-8 response; oversize Catalog trả
CATALOG_REPRESENTATION_UNAVAILABLE503, Inventory SERVICE_UNAVAILABLE503. Detail
recipe đọc tối đa10486 lines và fail nếu >10485; không truncate success. Đây là
conservative resource bound, không policy recipe. Page SQL LIMIT limit+1;
Store-wide counts/stock sums là SQL aggregates, không materialize toàn Store.

Chưa có production SLA, browser/FE acceptance hoặc security certification.
Aggregate queries vẫn phải đọc phạm vi nguồn; revision row có thể serialize các
writes cùng Store. Privileged maintenance TRUNCATE/disable triggers/restore không
thuộc writer contract; phải invalidate/reinitialize versions trước public serving.
Không deploy/migrate development DB trong S4.3. Rollback source và test-only
migration downgrade không được diễn giải thành quyền xóa metadata/history thật.

## Source map và manual check

`app/api/public_reads.py` — query/OpenAPI transport; application contracts và
use_cases/public_reads.py — typed projection/authority/cursors;
repositories/public_reads.py — scoped bounded SQL;
infrastructure/database/public_read_session.py — MVCC ownership;
domain/inventory/read_rules.py — exact formatting/lot rules;
alembic/versions/0012_public_read_revisions.py — transactional invalidation.

Sau login S4.1 trong test environment, đọc P01 → P02 → lấy ingredient_ids → V01
→ V02 và tiếp V03/V04 bằng snapshot/cursor. Không cần Origin/CSRF cho GET.
Ví dụ request path `/api/v1/stores/<uuid>/products?limit=5&q=tra`;
`/api/v1/stores/<uuid>/inventory?ingredient_id=<uuid>&limit=5`.
Không copy session/token thật vào docs hoặc logs. Không dùng manual check này
để truy cập development DB trong lượt S4.3.
