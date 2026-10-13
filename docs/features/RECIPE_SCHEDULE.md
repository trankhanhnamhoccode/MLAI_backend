# Lịch hiệu lực công thức — N20–N22 / S4.7

Authority: [CAT12](../API_CONTRACT.md#recipe-effectivity),
[Auth](../AUTHORIZATION_CONTRACT_VI.md), [task notes](../runbooks/FULL_TEST_FLOW.md).
Contract là authority; feature này mô tả HTTP/source hiện hành và cách kiểm tra.
Không thay policy lịch sử, requirements, forecast, winner hoặc FEFO.

## Luồng FE

1. GET N20 `/api/v1/stores/{store_id}/products/{product_id}/recipe-schedule`.
   Đọc `as_of_date`, `minimum_change_date`, `schedule_version`/ETag,
   `catalog_version`, items/content/assignment/state. Mặc định in_effect,scheduled;
   muốn audit chọn status=past,in_effect,scheduled,unassigned. Các trang phải cùng
   version;409 LIST_VERSION_CHANGED thì tải lại trang đầu, không nối trang cũ.
2. Khách khai báo rõ đóng kỳ cũ/mở kỳ mới. POST N21 cùng route `/changes`,
   `phase=preview`, If-Match ETag từ N20, UUID Idempotency-Key, Origin/CSRF/session.
   Chỉ có staging preview; recipe/lines/calendar chưa đổi. Không tự close từ Import.
3. Response200 có `status=preview_ready|blocked`, before/after/changed_ranges,
   reserved new_contents, blockers/warnings và required_warning_acknowledgements.
   Blocked là kết quả preview, không phải canonical success. Sửa đề xuất thì tạo
   preview mới; không sửa nội dung hoặc reason trong commit.
4. POST N21 `phase=commit`, key riêng, If-Match **schedule_version gốc**, exact
   change_id/preview_digest, confirm=true, exact warning codes. Gap có ranges rõ,
   không tự lấp hoặc pause Product. Commit200 synchronous; receipt có changed và
   resource flags, không poll worker.409/412 thì refresh/re-preview.
5. GET N22 `/changes/{change_id}` mở lại retained preview/receipt/audit. GET không
   re-evaluate preview, gọi provider, BOM/forecast/solver hoặc thay canonical state.
   Lost response: retry **cùng body/key/If-Match**, hoặc đọc N22. Replay vẫn kiểm
   current rights, không cho quyền đã bị thu hồi tiếp tục write/replay.

N20/N22 cần menu.read+recipe.read+ingredient.read. N21 thêm
recipe.manage_effectivity; chỉ khi tạo content mới mới thêm recipe.create_version.
Owner đúng Store hoặc Staff có grants tương ứng; create_version đơn lẻ không đổi
lịch. Giá bán/giá nhập/budget không nằm trong response này.

## JSON để kiểm tra thủ công (IDs hoàn toàn synthetic)

Ví dụ Store day11/10; v1 từ01/10 đang open-ended. Headers cho từng POST:
`Content-Type: application/json`, `If-Match: "schedule-version-from-N20"`,
`Idempotency-Key: UUID riêng mỗi phase`, Origin và X-CSRF-Token từ session hợp lệ.
Không dùng các IDs/version mẫu như dữ liệu thật.

N21 preview request:

```json
{"phase":"preview","new_recipes":[{"client_reference":"next","yield_quantity":"2","yield_unit":"cup","process_loss_rate":"0.1","ingredients":[{"ingredient_id":"00000000-0000-4000-8000-000000000003","quantity":"300","unit":"ml"}]}],"operations":[{"kind":"SET_PERIOD","recipe_ref":{"recipe_id":"00000000-0000-4000-8000-000000000020"},"effective_from":"2026-10-01","effective_to":"2026-10-11"},{"kind":"SET_PERIOD","recipe_ref":{"new_recipe_reference":"next"},"effective_from":"2026-10-12","effective_to":null}],"reason":"Thay công thức từ ngày kinh doanh kế tiếp"}
```

N21 commit request (thay IDs/digest bằng preview thực):

```json
{"phase":"commit","change_id":"00000000-0000-4000-8000-000000000030","preview_digest":"preview-digest-from-N21","confirm":true,"acknowledged_warning_codes":[]}
```

N20 success response:

```json
{"data":{"store_id":"00000000-0000-4000-8000-000000000001","product_id":"00000000-0000-4000-8000-000000000002","as_of_date":"2026-10-11","schedule_version":"schedule-version-from-N20","catalog_version":"catalog-version-from-N20","items":[{"content":{"recipe_id":"00000000-0000-4000-8000-000000000020","version":1,"yield_quantity":"1","yield_unit":"cup","process_loss_rate":"0","ingredients":[{"recipe_line_id":"00000000-0000-4000-8000-000000000021","ingredient_id":"00000000-0000-4000-8000-000000000003","quantity":"180","unit":"ml"}]},"assignment":{"effective_from":"2026-10-01","effective_to":null},"state":"in_effect"}],"minimum_change_date":"2026-10-12"},"meta":{"request_id":"synthetic-request","pagination":{"limit":50,"next_cursor":null,"total_count":1}},"error":null}
```

N21 committed receipt success:

```json
{"data":{"change_id":"00000000-0000-4000-8000-000000000030","status":"committed","preview_digest":"preview-digest-from-N21","store_id":"00000000-0000-4000-8000-000000000001","product_id":"00000000-0000-4000-8000-000000000002","committed_at":"2026-10-11T03:00:00Z","schedule_version_before":"schedule-version-from-N20","schedule_version_after":"schedule-version-after-commit","created_recipe_ids":["00000000-0000-4000-8000-000000000022"],"affected_recipe_ids":["00000000-0000-4000-8000-000000000020","00000000-0000-4000-8000-000000000022"],"audit_reference":"00000000-0000-4000-8000-000000000031","changed":true,"updated_resources":{"menu":true,"recipes":true,"inventory":false,"sales":false,"forecast":false,"retained_runs":false},"warnings":[]},"meta":{"request_id":"synthetic-commit"},"error":null}
```

No-op receipt có changed=false, arrays rỗng, menu/recipes=false và schedule version
không tăng; vẫn có retained receipt/audit. Preview/read response đầy đủ dùng schema
`Preview`/`ChangeRead` generated OpenAPI, không gửi receipt như request.

## Lịch, validity và errors

- Inclusive: đóng ngày11 và mở ngày12 thì ngày11 vẫn v1, ngày12 v2. Today/past
  phải giữ identity/content/availability. WITHDRAW_FUTURE chỉ kỳ chưa từng hiệu lực;
  content/lines/version giữ lại, assignment=null. Reassign phải từ ngày kế tiếp.
- Qua nửa đêm Store:409 RECIPE_DATE_POLICY_CHANGED cho mọi commit preview cũ,
  re-preview; không tự dời ngày. Same-key success replay vẫn trả receipt lịch sử.
- Existing empty content đọc được; content mới1..100 distinct lines, exact positive
  qty/yield và0≤loss<1, unit khớp Product/Ingredient; không conversions/defaults.
- Overlap/history violation là blocker preview200; commit409 PREVIEW_BLOCKED.
  Syntax/foreign IDs/unit errors422/404; CAS412 RECIPE_SCHEDULE_REVISION_CONFLICT;
  thiếu key/If-Match428; deps/content đổi409 PREVIEW_STALE. Invalid warning ack422.
- Unknown fields/query/body GET bị chặn. POST request cap64KiB,≤20 new/100 ops,
  ≤1000 future assignments; không truncate. Technical output caps: N20 data1MiB,
  preview1MiB (413 khi vượt), N22 retained projection4MiB để chứa cả preview/audit.
  Source quá lớn/không thể biểu diễn đầy đủ báo lỗi, không cắt recipe lines.

## Persistence và giới hạn

CURRENT FACT: migration0015 thêm `recipes.assigned=true` cho headers hiện có và hai
bảng retained changes/request receipts. Unassigned giữ dates cũ trong storage làm
evidence, nhưng API assignment=null; active/operational capture chỉ materialize
assigned rows. Partial inclusive exclusion áp dụng calendar đang assigned;
unique Product/version và Store graph giữ nguyên. Không nullable hóa dated inputs
của domain engine. Downgrade từ chối khi có editor evidence/unassigned content.

Canonical recipe periods/content + immutable proposal/audit/success receipt cùng
transaction. Ordered table fences giống Import; temporary unassignment chỉ nằm
trong transaction, không expose trạng thái giữa chừng. Reserving preview không ghi
canonical UUID/version; concurrent Import/version allocation làm preview stale,
không đổi reserved IDs/version ở commit. Retained GET không lấy current facts thay
bản trước/sau đã giữ. Fault sau SQL flush rollback toàn bộ.

Không có queue/worker cho N21, LLM, forecast/planning execution, lịch sử sửa hồi tố,
recipe CRUD, autoclose trong import hoặc S4.8 readiness. S4.7 không phát hành handoff
mới; FE ZIP trước đây vẫn là snapshot lịch sử chưa chứa validation changes mới.
