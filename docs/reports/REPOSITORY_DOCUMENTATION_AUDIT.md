# Audit trình bày repository và tài liệu ShelfCash

Ngày 17/10/2026. **Chỉ audit và đề xuất**; các thay đổi bên dưới là PROPOSAL,
không phải quyết định kiến trúc hay thay đổi contract đã được chấp nhận.

## 1. Baseline và phạm vi

**CURRENT FACT — kiểm tra tĩnh:** checkout `D:\hocc_bk\ai\proj\projectMLAI\backend`,
branch `main`, HEAD `a17d153feccfa96de34002dd536bf9381c01f219`.
`git log` và `git merge-base --is-ancestor` xác nhận Summary `48a3658`, PDF
`9a80f97` và integration PDF `1134a78` nằm trong ancestry HEAD. Source
[profile_from_settings](../../app/infrastructure/plan_summary_provider.py) chọn
`summary_profile/6`; [ExportAccepted](../../app/application/contracts/planning_export.py)
mặc định `planning-pdf/3`; renderer cũ vẫn có đường replay trong
[PlanningExports](../../app/application/use_cases/planning_exports.py).

[OpenAPI tracked](../handoff/openapi.json) chứa **76 operations/69 paths**;
đếm tĩnh decorators trong `app/api/*.py` cũng có 76 operations. Parse tĩnh
`revision/down_revision` xác nhận một source migration head
`l5_20261016_assistant_f4`, merge `0030_conversational_chat` và
`f4_20261016_metadata_v2`. Không kiểm tra schema/data của DB đang chạy.
Local ref `origin/main` là `d5cfbfb59de7c45bc08eb47129b5ba3919e05473`;
không fetch nên không kết luận HEAD trên server remote.

`git worktree list` có 21 checkout: main; Auth, readiness, Assistant, forecast,
Import, notification, PDF, Summary và các integration/snapshot liên quan.
`backend-import-curated-templates` ở `feat/import-curated-templates`/`4609a52`
không là ancestor HEAD; không đưa capability nâng cấp riêng này vào main.
`backend-import-mapping-preserved` ở `feat/import_mapping_rules`/`b1ede89`
là checkout riêng cần bảo toàn. Không thao tác worktree nào khác.

Baseline dirty gồm 7 tracked files: CURRENT_STATE, ROADMAP, Planning contract,
Assistant feature, handoff entrypoint/examples và FULL_TEST_FLOW. Có 7 untracked
files: `docs/handoff/openapi_diff_d5cfbfb.json`, hai scripts
`seed_local_forecast.py`/`seed_local_planning.py` và bốn unit/integration tests
tương ứng. **WIP không phải bytes của HEAD**; các mô tả mới trong WIP và các
seed scripts chưa tracked không được coi là đã phát hành cho clone sạch.
Không đọc nội dung `.env`, credential, private runtime hoặc model artifacts.

Đã đọc engineering rules tại [AGENTS](../../AGENTS.md), không tìm thấy AGENTS ở
các thư mục cha đã kiểm tra; đọc state/decision index, ADR-001/004/007/015/020/022,
architecture, shared API, domain/schema/roadmap và các phần liên quan của
Authorization/Import/Planning. Đối chiếu README, TESTING, runbook, handoff,
Import/forecast/engine/Assistant/PDF features, `.env.example`, launcher,
Compose, pyproject, `.gitignore`, source và acceptance assertions liên quan.
Không đọc toàn bộ logs/vendor/evidence; không chạy server, pytest, DB, migration,
provider, SMTP hay FE; không commit/push/merge. Không chứng nhận “chạy được”.

## 2. Bản đồ tài liệu và các luồng chạy

**ACCEPTED DECISION — ownership hiện có:** AGENTS và DECISIONS quy định chỉ ADR
ACCEPTED có thẩm quyền kiến trúc; OpenAPI/DTO sở hữu cấu trúc wire, các contract
sở hữu workflow/meaning/permissions. Giữ ownership này khi chỉnh presentation.

| Nhóm điều hướng | File hiện có và vai trò đề xuất |
| --- | --- |
| A. Sản phẩm | [README](../../README.md): cửa vào ngắn, giá trị/luồng/khả năng/giới hạn; không phải API inventory. |
| B. Clone sạch | [FULL_TEST_FLOW](../runbooks/FULL_TEST_FLOW.md), mục “setup khách hàng từ số0”/A: canonical setup; launcher `scripts/local_runtime.py` và `compose.local.yaml` là implementation. |
| C. Chạy/dừng | Cùng runbook, mục B: start/status/stop, upgrade có backup; không lặp init/reset mỗi ngày. |
| D. Cấu hình | [.env.example](../../.env.example): tên/default; runbook A: điền theo nhu cầu; [AUTH_SESSION](../features/AUTH_SESSION.md) và [DECISION_ASSISTANT](../features/DECISION_ASSISTANT.md): điều kiện email/provider chuyên biệt. |
| E. Tests/troubleshooting | [TESTING](../TESTING.md): policy/coverage; runbook D và các profile: thao tác và DB ownership. TESTING chưa có inbound Markdown link trong phạm vi quét. |
| F. Kiến trúc/nghiệp vụ | [ARCHITECTURE](../ARCHITECTURE.md), [DOMAIN_MODEL](../DOMAIN_MODEL.md), [DATABASE_SCHEMA](../DATABASE_SCHEMA.md), [DECISIONS](../DECISIONS.md); features giải thích implementation có version. CURRENT_STATE/ROADMAP sở hữu trạng thái/gates. |
| G. Contract/FE | [Handoff 010](../handoff/010_BE_CAPABILITY_RESPONSE_VI.md): mục lục FE; OpenAPI/examples/recovery journal đi kèm. [API_CONTRACT](../API_CONTRACT.md): shared/Catalog/Inventory; Authorization, Import, Planning là ba contract độc lập; [Notification](../NOTIFICATION_API_CONTRACT_VI.md) sở hữu workflow chuyên biệt đã có. |
| H. Lịch sử/evidence | Các section HISTORICAL trong state/runbook/features; [compatibility changelog](../CONTRACT_COMPATIBILITY_CHANGELOG_VI.md), ADR superseded/proposed, fixtures và [legacy Import audit](../../IMPORT_SCHEMA_LEGACY_HANDOFF_VI.md). Đây không phải hướng dẫn mặc định cho clone mới. |

**CURRENT FACT — mức hỗ trợ theo tài liệu/source, chưa thực thi trong audit:**

| Luồng | Hỗ trợ hiện có, prerequisites và gap |
| --- | --- |
| Clone mới, chưa env/venv/DB/cert | README + runbook A có venv, editable dev install, copy env, secrets, Docker/init/migrate/TLS/trust. Source launcher dùng interpreter hiện hành, không cần sibling venv. Cần Git, Python tương thích dependencies, Docker Linux engine, PowerShell; cần quyền trust cert. Đường dẫn `D:\...` phải thay bằng checkout thực tế. Expected schema trong runbook đã cũ; chưa có fresh-clone execution ở HEAD này. |
| Chạy lại máy đã setup | Runbook B và launcher `start/status/stop` có ownership/PID/config/source checks; cần DB/TLS/env đã chuẩn bị và Git sạch. Source mới có migration cần backup-aware upgrade, không dùng lại first-time migrate. Không suy runtime cũ đã được upgrade/restart từ main source. |
| Signup Owner → verify → Store | Runbook C bước 1–2, Authorization self-service: signup/verify không tạo Store, holder verified/credential-ready login rồi T03 tạo Store/Owner trống. Cần email capability và callback A05; callback/UI FE chưa được xác nhận theo tài liệu, audit này không kiểm FE. Store trống chưa READY; không lấy seed/account local làm prerequisite chung. |
| Không SMTP/OpenRouter | Core Import review thủ công/Planning và deterministic Assistant có đường hoạt động không provider khi đủ facts/rights/config/workers. Không có SMTP/callback thì register/resend/forgot có thể 503, không hoàn tất customer onboarding mới. Owner/Staff seed đã tracked là lựa chọn synthetic riêng, không phải production onboarding; seed forecast/planning mới là WIP local. |
| Email thật + LLM | Có SMTP_SSL/465, encryption key, sender và HTTPS callbacks; worker email bật riêng. Import, Summary, Chat có enable/model/bounds độc lập, key không tự bật. `.env.example` có cả ba nhóm; runbook A chưa hướng dẫn Summary/Chat trong bảng cấu hình. Assistant feature có hướng dẫn bù. SMTP smoke/historical Gemini acceptance không chứng minh browser/final S3 live acceptance; không tự chạy để lấp gap. |
| Developer tests DB riêng | TESTING, runbook D, `tests/conftest.py` và `scripts/dev.py` có effective TEST_DATABASE_URL/identity allowlist, reset tuần tự; local profile dùng `shelfcash_local_test`/tester riêng. Fixtures reset/migrate DB test, không DB customer. Profile đầu TESTING vẫn gắn worktree integration cũ; cần chỉ rõ local mặc định và exceptions. Chưa chạy tests, không chứng nhận full regression. |

## 3. Findings, ưu tiên cao → thấp

| Mức | Finding và bằng chứng | Hướng sửa sau audit |
| --- | --- | --- |
| Cao | **TECHNICAL DEBT — drift inventory/setup.** README đoạn CURRENT FACT ghi 73/66, head0027/72 tables; runbook “setup khách hàng từ số0” và mục A expected DB lặp lại. OpenAPI tracked là 76/69; migration graph đã tới `l5_20261016_assistant_f4`. `local_runtime.migrate` chạy graph head thực tế, không pin0027. | Bỏ số biến động khỏi giới thiệu README; cập nhật current setup expectations theo source, giữ mốc0027 trong lịch sử. Tuyệt đối không suy schema DB đang phục vụ. |
| Cao | **TECHNICAL DEBT — anchor đúng cú pháp nhưng sai đích.** README link “FULL_TEST_FLOW — canonical A–D” dùng `#customer-self-service`; anchor nằm ở dòng1511 trước “L3.1/L3.2 synthetic conversational verification”, còn setup thật bắt đầu dòng1737. Các contract/feature cũng dùng anchor này. | Đặt anchor hiện hữu ngay trước setup thật, giữ tên để inbound links tiếp tục hoạt động. Không cần đổi hàng loạt callers. |
| Cao | **TECHNICAL DEBT — clone sạch thiếu tham chiếu.** Handoff WIP dòng22 link `openapi_diff_d5cfbfb.json` chưa tracked; HEAD handoff chưa có link mới đó. `PROCUREMENT_GOLDEN_CASES` dòng10 link ignored `runtime/s341/procurement_experiments.py`, không có trong HEAD; dòng11 nhãn `results.json` lại trỏ tài liệu engine. | Handoff artifact phải được review cùng WIP trước khi phát hành; chưa tự add/commit. Golden doc đánh dấu evidence lịch sử/private và trỏ current reusable fixtures/tool đúng nghĩa, không giả script còn clone được. |
| Vừa | **TECHNICAL DEBT — “CURRENT FACT” theo lát cũ gây mâu thuẫn.** `features/SCAFFOLD.md` mục Status/API nói chưa auth/import/business APIs, OpenAPI chỉ health, head0006. `features/FORECAST.md` mục Status nói LightGBM/artifacts/fallback còn absent; `FORECAST_TRAINED`, `forecast_model.train_quantiles`, `ForecastServing` và `app/main.py` chứng minh implementation hiện có. `FORECAST_ENGINE_INTEGRATION` phần C0 còn nói Assistant không merge trong khi main đã wire Assistant. | Chỉnh current account và gắn phạm vi HISTORICAL cho slice-time claims; không sửa ADR để hợp thức hóa drift. Không gom mọi feature thành một tài liệu hoặc thay đổi thuật toán. |
| Vừa | **TECHNICAL DEBT — đường đọc cho bốn nhóm người chưa rõ.** README 73 dòng dành phần lớn cho setup/seed/benchmark; không giải thích riêng Forecast–Planning–Summary–Chat–PDF. Runbook 3538 dòng mở bằng Summary/PDF acceptance, setup nằm sâu và lẫn WIP/provenance máy. TESTING mở bằng env của sibling integration. README chưa dẫn TESTING; bảng env runbook thiếu Summary/Chat dù template có. | README làm mục lục theo người đọc; runbook đưa current A–D lên trước, đánh dấu profile/acceptance chuyên biệt; TESTING chỉ tới local/default và profile cần chọn. Link feature cho cấu hình AI. |

Đánh giá README hiện tại: hai câu mở đầu **đã nêu đúng** khách F&B, bài toán mua
nguyên liệu và khách quyết định; không cần viết lại thành lời quảng cáo. Setup lần
đầu và chạy hằng ngày **đã tách**, tests chỉ được nhắc/link, không phải tất cả đang
trộn chung. Điểm yếu là product story ngắn hơn phần vận hành và metrics/schema
implementation xuất hiện quá sớm; seed/benchmark chiếm vị trí nổi bật.

README không hứa forecast accuracy, whole browser pass hoặc tự đặt hàng; chữ
“Source” không phải claim runtime deployed. Tuy nhiên nên có một giới hạn ngắn,
rõ: chất lượng real-data chưa đánh giá, challenger chỉ test opt-in/OFF, Summary S3
chưa final-source live acceptance, FE/browser pending. Handoff WIP đã phân biệt
SOURCE_READY/NOT_DEPLOYED và Import riêng đúng; cần giữ sự phân biệt này.

Quét 89 Markdown tracked trong working tree: 697 local inline links ngoài fenced
code, không phát hiện path đích mất trên máy hoặc anchor không tồn tại theo checker
cục bộ; **hai link phụ thuộc file local/untracked** như bảng trên. Quét riêng links
đường dẫn ở HEAD: 681 links, chỉ script scratch procurement không có trong Git.
Không có Markdown link dạng `D:\...`/`file://` trong phạm vi quét, nhưng commands
trong README/runbook và TESTING có đường dẫn/worktree cá nhân. Không kiểm mạng,
external links, HTML/reference-style links hay mọi path trong code blocks; anchor
sai ngữ nghĩa phát hiện bằng đọc tay, không phải kết quả checker.

Hai root files `018_Backend_Capabilities_Service_Boundary.md` và
`019_Main_Frontend_Implementation.md` chỉ có local, được `.git/info/exclude` loại;
không phải tài liệu có sẵn cho người clone. Không dùng làm contract canonical.
Không có tracked CI workflow dưới `.github/`, logo hay ảnh PNG/SVG/JPG được tìm thấy;
không thêm badge CI/coverage, screenshot hoặc logo chưa xác minh quyền sử dụng.

## 4. Outline README đề xuất để Owner duyệt

**PROPOSAL — tiếng Việt**, giữ identifiers/API/commands tiếng Anh; phù hợp README,
contract VI và nhóm FE hiện tại. Không cần dịch toàn repository.

1. **ShelfCash là gì** — backend hỗ trợ quán F&B quyết định mua nguyên liệu; dữ
   liệu đầu vào, phương án so sánh và khách quyết định trong 2–3 câu.
2. **Luồng tổng quát** — nhập/review dữ liệu → kiểm readiness/config → forecast
   nhu cầu → BOM/tồn/FEFO → so sánh LEAN/BALANCED/PROTECTED → xem kết quả/giải
   thích/PDF. Summary/Chat là cách đọc retained evidence, không bước ra quyết định.
3. **Khả năng đã có** — bảng gọn: Import/Inventory; Forecast (demand quantiles);
   Planning (tính/so sánh); Summary (tóm tắt); Chat (hỏi theo Run); PDF (export).
4. **Bắt đầu** — hai link rõ “Clone/setup lần đầu” và “Start/status/stop”; nêu
   prerequisites ngắn và FE chạy riêng, không nhúng lệnh dài hoặc toàn env.
5. **Tìm tài liệu theo việc cần làm** — developer → runbook/TESTING; FE → handoff/
   OpenAPI/contracts; hiểu hệ thống → architecture/domain/ADRs; status → state/roadmap.
6. **Giới hạn hiện tại** — chưa real-data quality/browser certification; optional
   email/LLM cần cấu hình riêng; challenger chưa production; không tự đặt hàng.

Giữ nội dung chính khoảng 1–2 màn hình. Dùng headings và một bảng; Mermaid chỉ
nếu luồng vẫn đọc được trong khoảng 6 nút, không cần FigJam/file ảnh mới. Dùng
`<details>` cho ghi chú demo tùy chọn, ưu tiên đưa seed/benchmark về runbook/feature.
Không đưa API inventory, SHA, acceptance logs hoặc credentials vào README.

## 5. File giữ/cập nhật/gộp/lịch sử

| File/nhóm | Đề xuất và lý do |
| --- | --- |
| README.md | Cập nhật presentation theo outline; bỏ setup chi tiết và inventory, giữ links tới owner hiện có. |
| docs/runbooks/FULL_TEST_FLOW.md | Cập nhật vị trí anchor, đặt current setup/run/config/test lên đầu, sửa stale expectations; giữ profile/evidence có nhãn và provenance. |
| docs/TESTING.md | Cập nhật entrypoint/profile selector; giữ policy và coverage, không chép lại commands runbook. |
| docs/CURRENT_STATE.md, docs/ROADMAP.md | Chỉ cập nhật current account/điều hướng liên quan, sau khi review WIP với chủ phần đang sửa; không ghi audit thành PASS log. |
| docs/features/SCAFFOLD.md, FORECAST.md, FORECAST_ENGINE_INTEGRATION.md | Cập nhật phân loại current/historical tại các finding; giữ phạm vi và version của implementation cũ. |
| docs/features/PROCUREMENT_GOLDEN_CASES.md | Sửa link/nhãn evidence; giữ goldens/history hữu ích, không xóa vì cũ. |
| docs/handoff/010_BE_CAPABILITY_RESPONSE_VI.md và openapi_diff_d5cfbfb.json | Reconcile tính đầy đủ của handoff WIP trước phát hành; giữ pin/hash/source-vs-runtime và baseline provenance. |
| API/Authorization/Import/Planning/Notification contracts, OpenAPI/DTO, ADRs | Giữ ownership và semantics. Lượt presentation không tự thay contract/accepted ADR hoặc tái sinh OpenAPI. |
| ARCHITECTURE/DOMAIN_MODEL/DATABASE_SCHEMA, Assistant/PDF/current engine features | Giữ làm nguồn chuyên biệt, README link tới; chỉ sửa current-account drift có bằng chứng nếu nằm trong scope được duyệt tiếp. |
| Legacy Import audit, compatibility, design/formulation/golden history, examples/fixtures | Giữ tại chỗ. Có thể thu gọn cách hiển thị section lịch sử; chưa đề xuất di chuyển/xóa file. |

**Inbound links đã kiểm:** FULL_TEST_FLOW có 60 nguồn Markdown khác nhau (gồm
self-links), handoff 010 có 9; legacy Import audit được CURRENT_STATE, Import
contract và IMPORT_SCHEMA_INVENTORY dẫn tới. PROCUREMENT_DESIGN có inbound từ
ADR-018/DECISION_DESIGN/PROCUREMENT_FORMULATION; DECISION_DESIGN từ ADR-016 và
DECISION_GOLDEN_CASES. TESTING và SCAFFOLD không có inbound inline link trong
phạm vi quét. Vì ownership/lifecycle khác nhau, không đề xuất gộp/move các file
này. “Gộp” chỉ là bỏ đoạn hướng dẫn lặp trong README rồi link runbook; không mất
nội dung canonical và không đổi đường dẫn đang có callers.

## 6. Các thay đổi cụ thể cho lượt chỉnh sau

1. Review cùng chủ WIP để freeze source baseline/handoff artifacts; xác nhận dữ
   liệu nào đã tracked và nội dung nào vẫn preview. Không đưa Import upgrade riêng vào main docs.
2. Chỉnh README theo outline; chuyển người đọc setup tới runbook và tests tới TESTING.
3. Đưa anchor `customer-self-service` về đúng heading; sắp current A–D trước
   historical acceptance, giữ anchors cũ/callers và profile ownership.
4. Sửa stale inventory/schema expected của current sections; đối chiếu graph/source,
   không công bố deployment/DB verification chưa thực hiện.
5. Thêm chỉ dẫn Summary/Chat độc lập vào bảng cấu hình bằng links tới Assistant
   feature; giữ `.env.example` làm nguồn tên/default, không sửa config trong lát docs.
6. Sửa slice-time claims và link scratch evidence nêu ở findings; giữ provenance
   thực chất, không tạo các tài liệu “v2/latest” hoặc tám file theo nhóm A–H.
7. Verification lượt docs: diff/whitespace, links + anchor đích đúng, đối chiếu
   tracked HEAD/WIP, tên lệnh/config/route với source. Không cần pytest hay OpenAPI
   regeneration cho thay đổi presentation; fresh-clone run/deployment là scope riêng.

## 7. Quyết định thật sự cần Owner chốt

**PROPOSAL:** duyệt outline README ở mục4 và phạm vi chỉnh tài liệu ở mục5–6 là
đủ để bắt đầu lượt tiếp. Tiếng Việt và tái sử dụng runbook là mặc định đề xuất,
không cần quyết định kiến trúc mới. Nếu muốn công bố demo/browser self-service
hoạt động hoặc challenger production/forecast quality, cần scope acceptance riêng;
không biến những việc đó thành prerequisite cho việc sửa presentation.

Audit chỉ tạo báo cáo này; mọi đề xuất vẫn chưa thực hiện. Source-ready không
đồng nghĩa deployed; targeted/historical tests không đồng nghĩa full regression.
