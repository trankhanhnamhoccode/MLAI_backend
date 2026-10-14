# Phản hồi BE cho FE010 — source tích hợp Import A1–A3 / Auth B1–B4


## CURRENT FACT — Đợt2 C5 backend VERIFIED; browser E2E PENDING

C4 checkpoint eabab333; source artifact hiện72 operations/66 paths, single head0026.
Runtime upgrade PREPARED trên committed main; status/matrix/commands ở
[FULL_TEST_FLOW](../runbooks/FULL_TEST_FLOW.md#linked-acceptance-c5), là runbook canonical.
Không coi C5 tổng thể COMPLETE khi browser checklist Nam/Nguyên chưa chạy.
API base `https://localhost:8103`, exact Origin `https://localhost:5173`;
credentials include, secure cookie và current CSRF như contract. Setup/reset callback
`/credentials/complete`; invitation private route `/invitations/{invitationId}`;
verification và SMTP invitation landing vẫn cần FE xác nhận, không tự gửi mail.
Credentials chỉ mở accounts.json bằng editor local trong serving worktree, không đưa FE/Git.
Import/Planning/PDF/notification cùng owned BE; email/Qwen mặc định OFF.


## Tóm tắt cho chủ dự án

CURRENT FACT C4 source local `backend-notifications-foundation`:72 operations/66
paths, permissions-v3/43, head0026. C3 checkpoint b1c906a0ea65a3b20a46d161166668d26701f0a9;
C4 WIP để review, không push/merge. D01/SU01/EX01 và M01/M02/I04/N9 extensions đã
implement; [FULL_TEST_FLOW](../runbooks/FULL_TEST_FLOW.md#read-discovery-c4) sở hữu
commands, verification và limits. Demo8103/main vẫn bản trước C1–C4; browser C4
chưa chạy. Artifacts JSON G59/55 bên dưới là historical baseline, không generated
contract C4; regenerate từ source/OpenAPI sau review, không cộng artifacts cũ.

HISTORICAL INFORMATION G: đã ghép hai commit nghiệm thu trong worktree riêng `backend-integrate-import-auth`, branch `feat/integrate-import-auth`, giữ nguyên lịch sử nguồn và WIP của hai phiên. Source thống nhất có **59 operations/55 paths**, catalogue **permissions-v3/43 keys**, migration head **0024_integrate_import_auth**. FE dùng [openapi.json](openapi.json), không cộng hai artifacts WIP cũ thành một contract.

Backend/fake-delivery và PostgreSQL là phạm vi verification; kết quả gate cuối nằm trong [runbook](../runbooks/FULL_TEST_FLOW.md#integrated-acceptance). Tại snapshot G ban đầu chưa có server; runtime demo8103 được chuẩn bị sau đó vẫn giữ source trước C1–C4, không verify C4 từ URL đó. Browser E2E và email workflow thật vẫn pending. Gmail smoke đã nhận inbox chỉ chứng minh email smoke đó. Forecast có consumers/mechanics, **real-data accuracy NOT EVALUATED**.

R05/R09 đã IMPLEMENTED trong local source C4, theo Product acceptance được giữ ở contracts. Recipe split-report đa file/sheet deferred; các guards và single-sheet hợp lệ vẫn hoạt động. Những capabilities Đợt2 còn thiếu bên dưới không trở thành runtime chỉ vì đã có prose contract.

## R00–R13

G = source tích hợp từ Import `126b0f210c898ba7510039b46f10ce3a42b4e0c0` (I) và Auth `0fbb979490eca5f8334284b6a1f7193591fe26a0` (B), common base `b1ede89a3919230ce9526337537d7a19ca182f15`. Git commit chứa tài liệu/artifact là snapshot bàn giao. Branch evidence lịch sử thuộc I/B, không suy từ file test tồn tại; gate G được ghi riêng trong runbook.

| Yêu cầu | Contract status | Runtime status | Branch/snapshot | Evidence / source kiểm tra | FE cần làm | BE cần làm | Slice phụ trách |
| --- | --- | --- | --- | --- | --- | --- | --- |
| R00 contract/API delta | OpenAPI source structural authority | C4 local72/66, gi?69 C3 locators; G59/55 l? historical artifact | C4 checkpoint eabab333; C3 checkpoint b1c906a; G provenance retained | [Diff JSON](openapi_diff_fe54.json), `app.main.create_app`, API tests | Regenerate DTO/adapters t? source C4 sau review; artifact G ch? baseline | Kh?ng n?ng c?p demo8103 trong C4; live runtime/browser c?n pending | Integration hiện tại |
| R01 signup/verify/resend/reset | ACCEPTED; AUTH self-service | A02/A05/A06/A07 và N7 implemented; no automatic Store/grants/session from verification | B1/B2/B4 tại B; G composition | [Auth routes](../../app/api/auth.py), `EmailVerification.request/complete`, `PasswordReset.request`, `AuthUseCases.complete`; fake delivery/fresh reads B4 | A02→check_email→A05→login; A07→N7→login | Browser/real workflow-email acceptance còn thiếu | B1/B2/B4 backend COMPLETE |
| R02 invitation decline | ACCEPTED; IN01 riêng; N19 true-only | Decline terminal/event/receipt, no membership/grants/access; new invitation identity for reinvite | B3/B4 tại B; G | [Staff DTO](../../app/application/contracts/staff.py), `StaffUseCases.decline/accept`, API const:true và transition tests | POST decline riêng; không dùng accept:false; refresh current context after acceptance | FE/browser terminal-state flow | B3/B4 backend COMPLETE |
| R03 mapping scoped counters | IMPLEMENTED C4 | M01/M02 batch/filtered issue counters và pinned revision; legacy Progress giữ nguyên | C4 checkpoint eabab333 | `ImportStaging.mappings/_progress`; [Import contract](../IMPORT_MAPPING_API_CONTRACT_VI.md) | Dùng counter_scope/counters, không page length hoặc completed_fields làm auto count | Current sensitive reads, snapshot/cursor và exact AND filters đã có | Import read projections C4 |
| R04 raw-cell/source-effect preview | IMPLEMENTED C4 | I04 source_effect reuse SourceEvidenceCell/C2 bounds, cached formula values và typed effects | C4 checkpoint eabab333 | `import_preview.make_preview`, `PreviewRow`, `ProvenanceValue`; [preview DTO](../../app/application/contracts/import_mapping.py) | Hiển thị partial/unavailable/truncated, không coi null là0; Recipe ID chưa reserved được báo rõ | Pinned source/read permissions, no GET parse/recanonicalization | Import read projections C4 |
| R05 file/sheet preview aggregates | IMPLEMENTED C4 / Product accepted | I04 aggregates batch/selected/files/sheets, raw records riêng logical actions; totals không theo page | C4 checkpoint eabab333 | [§17.1](../IMPORT_MAPPING_API_CONTRACT_VI.md#preview-aggregates) | Không cộng overlapping scopes; classification áp sau grouping | Retained preview/digest, distinct actions và source-record counts | Import read projections C4 |
| R06 supplier picker | IMPLEMENTED C4 | SU01 canonical supplier ID/name/active/version, search/order/paging/snapshot | C4 checkpoint eabab333 | `Supplier`, `StockWrites.receive`; [API](../API_CONTRACT.md#today-operations) | Picker chỉ locator, nullable supplier và N6 inactive policy giữ nguyên | Current supplier.read/Store scope, no terms/cost/contact | Operational discovery C4 |
| R07 creator/created-date Run search | IMPLEMENTED C4 | N9 creator/local accepted-date filters, applied_filters/timezone và snapshot | C4 checkpoint eabab333 | `PublicPlanning.history`, [history DTO](../../app/application/contracts/history.py) | Tôi dùng A03; creator lạ empty, Staff không cần N12 | Retained filter/Store timezone/current finance rights | Planning discovery C4 |
| R08 PDF locator discovery | IMPLEMENTED C4 | EX01 retained exports/job locators và verified artifact availability; GET không render | C4 checkpoint eabab333 | `PlanningExports.accept/download`, [export router](../../app/api/planning_exports.py) | Phân biệt execution status với missing/corrupt bytes; poll/download/request-new theo allowed_actions | Current export/result/finance rights và integrity; N11 rechecks | PDF discovery C4; browser S4.11 vẫn PARTIAL |
| R09 captured budget RunSummary | IMPLEMENTED C4 / Product accepted | N9 captured_budget available/unavailable từ retained acceptance, không current cap | C4 checkpoint eabab333 | [Planning §17](../PROCUREMENT_API_CONTRACT_VI.md#history-captured-budget) | Limit/currency là acceptance effective limit, không spend/remaining/null→0 | Cùng list snapshot/current financial rights; no C03 HTTP loop | Planning discovery C4 |
| R10 source-before-reuse / recipe grain | Guards ACCEPTED; split-report DEFERRED | Explicit source proof trước reuse; recipe scope ambiguity blocks; valid single-sheet assembly có | Base b1ede89 + I A3 + G | `import_analysis.discover`, `ImportStaging.resolve/_bindings`, `import_preview.make_preview`; A3 source/conflict acceptance | M02→M04 declaration→review/pin→preview; hiển thị blocker | Giữ guards; split identity/completeness deferred, không Product blocker | Lát3/A3 guards; split-report ngoài đợt |
| R11 Staff permission requests | IMPLEMENTED C2 | PR01–PR04 request/union decisions/current grants và atomic notifications | C2 local commit b9fe048 | [staff routes](../../app/api/staff.py), `StaffUseCases.replace`; [AUTH](../AUTHORIZATION_CONTRACT_VI.md#permission-requests) | Dùng PR lifecycle; approval không giả hai calls hoặc tự grant | Backend implemented; browser chưa verified | Collaboration C2 |
| R12 inbox/count/read | IMPLEMENTED C1/C2 | NF01–NF03 recipient projection/count/read; N13/PR/MQ producers và bounded dispatcher | C1/C2 local commits | [Notification](../NOTIFICATION_API_CONTRACT_VI.md#notification-v1), composition | Refetch pinned badge/list và current target rights; không dùng SMTP intent làm inbox | Backend implemented; worker default OFF/browser pending | Notifications C1/C2 |
| R13 Excel actual receipts | IMPLEMENTED C3 | Excel inventory_receipts và N6 cùng receipt identity/ledger/writer, atomic Import | C3 local commit b1c906a | `StockWrites.receive`, `InventoryEffect`, [Import](../IMPORT_MAPPING_API_CONTRACT_VI.md) | Receipt-only facts, replay/conflict và typed effects/completion; không dùng opening/count/history thay receipt | Backend implemented; C4 thêm read projection, không writer mới | Actual receipts C3 |

## Quyết định Product còn cần duyệt

Không còn câu hỏi Product chặn bàn giao trong R00–R13 hiện tại. R05/R09/R10 đã được duyệt theo nghĩa ở canonical contracts. Việc chọn thứ tự/ủy quyền triển khai các slices Đợt2 còn lại thuộc roadmap hiện hành, không phải yêu cầu đổi policy đã chốt hay duyệt cấu trúc JSON thường.

R05: logical action nhiều locations đếm một lần trong scope; totals file/sheet có thể overlap và không cộng thành batch total. Raw retained source rows là count khác. Totals/page dùng cùng preview/digest, không page length; tận dụng I04.

R09: captured effective limit/currency của Run tại acceptance, không Store cap hiện tại hoặc spend/remaining. Old Run thiếu evidence trả availability/nullable fields rõ, không zero giả; giữ quyền đọc tài chính và list snapshot/paging.

R10: không auto-union/last-file-wins hoặc bypass RECIPE_SOURCE_SCOPE_AMBIGUOUS; valid single-sheet assembly giữ nguyên. Split-report identity/completeness là deferred scope, không câu hỏi Product đang mở.

## FE nối ngay và runtime cần chờ

FE có thể làm DTO/adapters theo G cho public auth, N7, invitation offer/accept/decline, current Store context/grants và Import A1/A2 fields. FE cũng có thể chuẩn bị browser flows; chưa có base URL của server tích hợp đang chạy để certify live connectivity. R03–R09 và R11–R13 đã có trong local source C1–C4 như bảng; chưa có trên demo8103 và chưa browser-verified. D01 Today cũng thuộc C4, xem canonical API contract; không enable bằng stale capability fixture/prose.

Các URL lịch sử/demo riêng: Gmail Auth demo `https://localhost:8102` với Origin `https://localhost:5173`, DB5434 còn schema B2; demo S4.11 `http://localhost:18001`, DB5433 là profile cũ. **Không URL nào được chứng nhận là release tích hợp này.** Lượt tích hợp không start/restart/migrate demo hoặc sửa FE/config FE.

- Mọi API dưới `/api/v1`; browser dùng `credentials: include`, exact `AUTH_ALLOWED_ORIGINS` (JSON array), cookie HttpOnly. HTTPS dùng `__Host-shelfcash_session`; local insecure dev profile chỉ dùng khi cấu hình explicit đúng AUTH contract.
- A01/A02/A05/A06/A07/N7: exact Origin, public session/CSRF exemptions; verification/reset completion không cấp session. Authenticated invitation/grants mutations cần current session, Origin, X-CSRF-Token, Idempotency-Key và If-Match theo OpenAPI.
- N19 body chỉ `accept:true`; false/string/number bị422, không decline. IN01 có token/reason riêng. Offer proof không cấp authority; acceptance tạo exact grants, replay không khôi phục quyền đã thu hồi.
- Callback FE dùng AUTH_VERIFICATION_FRONTEND_URL, AUTH_PASSWORD_RESET_FRONTEND_URL, AUTH_INVITATION_FRONTEND_URL/AUTH_FRONTEND_URL theo [Auth feature](../features/AUTH_SESSION.md). URL base cần thuộc allowed Origin, không query/fragment/userinfo. Page lấy token từ fragment vào memory, xóa fragment ngay, no-referrer; không log/persist token. A05 consume verification, N7 consume SETUP/RESET, invitation proof không đổi purpose.
- Import/Planning/PDF worker flags độc lập default OFF; chỉ bật worker tương ứng khi cần process jobs và đã cấu hình runtime. AUTH_EMAIL_DELIVERY_ENABLED default OFF; backend/fake-delivery tests inject adapters, không SMTP. Provider/LLM OFF. Public mail endpoints503 EMAIL_DELIVERY_UNAVAILABLE khi capability không available; completion vẫn dùng existing valid token theo contract.
- Private errors phân biệt401 UNAUTHENTICATED,403 permission/CSRF,404 foreign resource,409 state/catalogue/idempotency,412 stale CAS,428 missing precondition. Không nới FE validator để che drift; refresh catalogue/version/context đúng error.

Lệnh kiểm trong worktree tích hợp, không secrets:

```powershell
.\.venv\Scripts\python.exe -m scripts.dev status --test-database
.\.venv\Scripts\python.exe -m alembic heads
.\.venv\Scripts\python.exe -m pytest tests/integration/test_integrated_migrations.py -q
.\.venv\Scripts\python.exe -m pytest tests/integration/test_auth_combined_acceptance.py tests/integration/test_import_planning_a3.py tests/integration/test_import_history_a2.py -q
```

DB test phải đúng shelfcash_integration_test / shelfcash_integration_tester; tests reset tuần tự riêng DB đó. Commands chạy server/worker/demo thuộc [FULL_TEST_FLOW](../runbooks/FULL_TEST_FLOW.md), là hướng dẫn, không evidence server đã chạy trong lượt này.

## Artifacts và provenance

| Artifact | Nội dung / giới hạn |
| --- | --- |
| [openapi.json](openapi.json) | Source C1–C4 đo72 operations/66 paths; provenance ghi C4 checkpoint/source manifest, head/time và previous BE59 artifact hash/ref; Git giữ bytes cũ |
| [openapi_diff_fe54.json](openapi_diff_fe54.json) | Diff với FE thực54/50 và nested previous_delivered_be59/55; SHA256, locators và structural JSON pointers |
| [examples.json](examples.json) | Giữ examples/provenance cũ; c5_read_discovery thêm DTO-validated fragments và query examples, không live response hoặc secrets |
| Tài liệu này | Trả lời R00–R13 và hướng dẫn nối FE; canonical contracts vẫn sở hữu policy |

Baseline FE thực đọc: `Shelfcash_FE_v2/api-contract-v2/generated/openapi.json`, SHA256 `6336bc0cdbe5f260389838934ba946cd51887af1b551c763b5beb4437e5e7e1f`,54 operations/50 paths. Yêu cầu010 trước ghi hash `f160bf4a46453404f103a32431da5dc722382fb02494612e61e2000e57533961`; đó là bytes snapshot khác, không được thay thành “cùng bản”. Baseline ngày10/10 trong tests/fixtures là32 operations, được giữ nguyên và không giả làm FE54.

Delta chính: +A02/A05/A06/A07/IN01, không removed operations; N19 schema const:true; terminal declined/can_decline; public mail envelopes; catalogue v3/max43; stockout policies/contributions; bốn support-history domains/typed corrections/projections; source-value/recipe/supplier basis/opening provenance và parser/mapping metadata. Xem diff structural đầy đủ và source DTO, không suy typed source input nào cũng là public HTTP request.

Source-only generation dùng process riêng, Settings không đọc .env, mọi workers/provider OFF, DB/network connect bị chặn; chỉ app.openapi(), không lifespan/server. Examples là synthetic và được model_validate; không deploy/API response captures. Artifact từng nhánh trong backend tổng `docs/handoff/010_openapi_{main,import-wip,auth-wip}.json` là lịch sử audit13/10 lúc18:07, không release I/B/G; provenance của chúng giữ nguyên ở backend tổng, không overwrite/copy làm artifact hiện hành.

Còn thiếu: browser checklist, FE callback verification/SMTP invitation và real workflow-email receipts. Runtime current status thuộc phần C5/runbook. Không tuyên bố toàn roadmap COMPLETE, forecast accuracy hay deployment pass.
