# Current state

## CURRENT FACT — D2 forecast eligibility/readiness, local WIP

Isolated `backend-data-readiness` / `feat/data-readiness` từ main052cddee, D1 committed
local `c930dfe66cfda5de5896164e16fcf8f4c7acaefe`. D2 COMPLETE trong BE scope đã giao,
source/tests/docs còn WIP để review, chưa commit/push/merge/deploy. Shared forecast
choice và typed internal assessment giữ actual method/candidate/reason/warnings,
scoped history blockers, recognized-only whole-scope fallback và exact retained
replay. R01/C01 all-censored TRAINED trước trả503, nay trả200 blocked assessment;
Today caller cùng fix. Dependency/runtime unavailable tách artifact invalid;
invalid/programming errors không success-fallback. OpenAPI/DTO/routes giữ nguyên.

[Canonical policy/matrix](features/DATA_READINESS_POLICY.md) tách main/D1 audit,
current D2 và proposals D3–D5. Sales-only/sparse0/stockout/retained/schema1 replay,
HTTP/PG/current-rights/Store isolation có focused acceptance, không full-suite hay
real-accuracy claim. Own venv/test-only PostgreSQL5435, shelfcash_readiness_test /
shelfcash_readiness_tester, head0027; provider/email/workers OFF. Commands/expected
responses tại [runbook](runbooks/FULL_TEST_FLOW.md#data-readiness-d2).
Default/custom/saved contextual readiness, offer omission và public warning fields
còn D3/D4; integrity/unknown-fee/safety guards giữ nguyên. Main8103/local DB/config/
artifacts, challenger E4/dataset WIP và sáu baseline workbooks ngoài Git được giữ
nguyên; không chạy E3/E4 benchmark hoặc training bằng workbook.

## CURRENT FACT — self-service Store/customer local

Canonical checkout `backend` trên main, own .venv/TLS/runtime/local profile. WIP9
nhánh import_mapping_rules được backup và giữ nguyên tại backend-import-mapping-preserved;
không merge WIP documents/artifacts cũ vào main. Import15/Auth0 giữ nguyên.
T03 POST /api/v1/stores: active verified credential-ready holder tự tạo Store/Owner,
atomic audit/immutable receipt, account-scoped replay/lost ACK/current authority.
Không account/Store/business seed cho customer. Source73/66, one head0027/72 tables.
New empty shelfcash_local + dedicated shelfcash_local_test/limited roles tách DB demo
cũ. Own certificate/key/storage/config, không external worktree dependency.
Single opted-in email thread handles existing verification/reset/invitation queues;
parameterized invitation callback supports confirmed FE route. No real SMTP/model
calls in setup/tests. EMAIL_VERIFY callback và signup/verify/create Store UI chưa
được FE nối/xác nhận: browser/self-service email E2E BLOCKED/PENDING, không claim PASS.
Verification, commands và14 customer flows thuộc [FULL_TEST_FLOW](runbooks/FULL_TEST_FLOW.md#customer-self-service).
Source checkpoint86fcc6795957baea9b2d7f343a8079bed44c1559; focused83/schema210 pass,
Auth149/1 assertion failure đã sửa và affected cases pass, không full-suite claim.
Own HTTPS runtime verified: OpenAPI73/66 khớp artifact, exact Origin/guards, direct
limited-role DB probes,0 accounts/Stores/business rows,4 workers alive/email OFF.
Demo cũ được backup/stop đúng ownership, head0026/data counts giữ nguyên. Process
source SHA cuối do local_runtime status cung cấp; browser/real email vẫn pending.

## HISTORICAL INFORMATION — C5 backend/runtime verification

C4 committed eabab333ee8738a0fa758b91f95a106d662edac6. Linked HTTP/PostgreSQL/
fresh-session gate3+20 passed; migration/tooling/OpenAPI gate25 passed, no full suite.
Origin main6f80735 đã nằm trong source, không conflict/engine delta; own test DB
head0026/71 tables, limited role,0 application rows sau cleanup.
Demo upgraded0024→0026 qua limited migrator sau verified custom backup (TOC/full
payload/SHA256 + private config ngoài Git); row counts mọi bảng cũ giữ nguyên.
Serving worktree committed `backend-main-integrated`, API HTTPS8103/Origin HTTPS5173,
71 tables/72 operations/66 paths, Import/Planning/PDF/notification cùng một BE.
Runtime role hạn chế, email/model OFF; TLS/Auth/current Store isolation/Today/inbox
và direct DB/queue probes pass. Existing2 terminal import jobs được giữ nguyên;
không thêm business facts, grant, account hoặc email. Cookie/login probes tạo session/
security audit thông thường. C5 tổng thể chưa COMPLETE: browser E2E PENDING.
Main đã tích hợp C1–C4/C5; source SHA/incarnation thực do launcher status báo,
remote push result thuộc bàn giao conversation (không tự ghi hash commit chứa nó).
[Commands, matrix, limits và browser checklist](runbooks/FULL_TEST_FLOW.md#linked-acceptance-c5).

## HISTORICAL INFORMATION — C4 backend acceptance checkpoint

C3 checkpoint b1c906a0ea65a3b20a46d161166668d26701f0a9; C4 checkpoint eabab333.
Source72 operations/66 paths: giữ69 locators C3, thêm GET D01/SU01/EX01;
extensions I04/M01/M02/N9. Catalogue permissions-v3/43, head0026/71 tables giữ nguyên.
Today section authorization/partial snapshots, canonical supplier picker, scoped
mapping issues, pinned raw/effect/overlap aggregates, creator/local-day/captured
budget history và retained PDF discovery đã implement. GET không tạo jobs/canonical
data hoặc render PDF. Current/pinned sensitive reads vẫn áp whole response.
Owned notifications test DB duy nhất, provider/email OFF; main/demo8103/WIP nguồn
giữ nguyên. Commands, coverage, fail→fix/query evidence và limits ở
[FULL_TEST_FLOW](runbooks/FULL_TEST_FLOW.md#read-discovery-c4). Không full-suite,
browser, runtime8103 upgrade hoặc production SLA claim. C5 current acceptance/runtime status thuộc phần đầu.
Final C4 focused24 passed; affected C1–C3/stock/history/PDF/readiness/DTO/query-boundary
regression191 passed. Own DB/role/head0026/71 tables/flags OFF đã kiểm sau cleanup.
Giữ technical limits Recipe ID not_reserved và absent-evidence budget projector;
structurally corrupt aggregates vẫn integrity error, không legacy facts giả.

## HISTORICAL INFORMATION — C3 backend acceptance

CURRENT FACT C3 COMPLETE backend acceptance: Excel `inventory_receipts` là schema thứ15, dùng cùng N6
`InventoryReceipts`/receipt ledger; không thêm endpoint, permission hoặc migration.
Source giữ69 operations/64 paths, permissions-v3/43, head0026/71 tables.
Typed receipt preview/effect/completion, exact identity replay/conflict, C2 MQ/N5
review và current grants/fences nối atomic Import. Không tự khai completeness,
supplier/cost/date hoặc thay retained PlanningRun. C3 commit local `b1c906a0ea65a3b20a46d161166668d26701f0a9`; phạm vi kiểm
chứng và command tại [FULL_TEST_FLOW](runbooks/FULL_TEST_FLOW.md#excel-actual-receipt-c3).
Main/demo8103/DB cũ giữ nguyên; browser E2E chưa chạy.
Final targeted gate105 passed; C1/C2/field/history regression196 passed/1 fixture
failure rồi affected case pass trong105; broad inventory gate51 passed/2 fixture
failures rồi affected cases pass. Không cộng trùng counts thành full-suite claim.
Own DB/role/head0026/71 tables và flags OFF đã probe sau test cleanup.

## HISTORICAL INFORMATION — C1/C2 local và C3 acceptance

Worktree `backend-notifications-foundation`, branch `feat/notifications-foundation`
from main `6f807357e107e504349a9b154c820bacdfffbe86`. C1 checkpoint commit local
`f85c7cdd7d9529404f5fd28e06f9156e97bb803e`; C2 commit `b9fe048a6c64ffb79438068076ee3e9d99d75fda`; C3 checkpoint local b1c906a; chưa merge/push.
Source NF01–NF03 + PR01–PR04/MQ01–MQ03: OpenAPI69 operations/64 paths,
permissions-v3/43 giữ nguyên. Additive single head `0026_collaboration_requests`,
70 application tables/71 với Alembic. Owned test DB
`shelfcash_notifications_test` / limited `shelfcash_notifications_tester` trên
instance Docker hiện có5433; dedicated URL/current-user guards và HBA boundary.
Demo8103 và các DB cũ vẫn head/data cũ, không migrate/reset.

Own-recipient inbox/count/read-unread, current active Store membership, account
scope, signed snapshots, CAS/idempotent read receipts và safe server templates đã
implement. Durable business enqueue + separate bounded row-lock dispatcher có
dedupe/backoff/restart/suppression và evidence retention. Producer thật: N13 đổi
grants; PermissionEvent/intent cùng Session, không thay N13 DTO/grants policy.
PR submit/approve/reject và MQ submit/N5 approve/reject/request_changes đã nối
intent cùng business transaction. PR approval union qua grants boundary hiện có,
không duplicate membership.grants_changed; retained replay không regrant. MQ pin
full spec/source/revisions, stale reconciliation cùng Import mutations; N5 resolve
live submission cả direct command. Approval không commit canonical data. Inbox
links PR/MQ kiểm lại current own/Owner và batch-sensitive domain rights; mất quyền
target thì link=null, notification không cấp quyền.
Notification worker explicit opt-in, default OFF; không thêm email/provider call.

HISTORICAL INFORMATION: final C1 targeted gate pass25 cases, cùng affected
Auth/Staff/database guards/schema regressions. C2 commands/results và giới hạn
được ghi tại runbook; acceptance dùng HTTP/PostgreSQL/fresh-session reads,
Full gate trước đợt sửa cuối:2308 passed/10 failed; đã sửa9 stale inventory
expectations và query boundary violation, rồi affected gates pass56 unit/API,
21 C2 HTTP/PG,69 regressions và2 retention cases. Không rerun/claim final full-suite
PASS, browser E2E hoặc live delivery. Runtime8103 vẫn chạy snapshot
tích hợp trước C1, OpenAPI59/head0024; các NF operations chưa có trên process đó.
Canonical scope/API/producers ở [notification contract](NOTIFICATION_API_CONTRACT_VI.md),
commands và exact verification ở [runbook](runbooks/FULL_TEST_FLOW.md#notifications-c1).
WIP backend9/Import15 giữ nguyên; C2 commit local; không push/merge hoặc đổi main/demo8103.

## HISTORICAL INFORMATION — runtime tích hợp trước C5

Branch `feat/integrate-import-auth` combines accepted Import126b0f2 and Auth0fbb979
on common base b1ede89, retaining both source histories and leaving both source
worktrees unchanged. Integrated base has59 operations/55 paths, permissions-v3/43 keys,
64 application tables (65 with Alembic), one head `0024_integrate_import_auth`.
Automated acceptance owns `shelfcash_integration_test` / `shelfcash_integration_tester`.
CURRENT FACT (2026-10-14): separate BE-only HTTPS runtime is prepared at
`https://localhost:8103`, exact Origin `https://localhost:5173`, using
`shelfcash_integration_demo` on the existing Docker PostgreSQL instance at5433.
Separate limited migrator/runtime roles, DB marker and role-specific HBA guards
protect the new target; old S4.11 data/schema/credentials are preserved. Demo has
head0024/65 tables, Import/Planning/PDF lifespan workers, provider/email OFF.
Synthetic assisted holders (two Owners/two empty Stores and one Staff) complete
credentials and Staff invitation through HTTPS/private delivery; Staff receives
only explicit `menu.read`. No operational facts/completeness/default config are seeded.
Runtime probes verify certificate TLS, OpenAPI59/55, cookie/CORS/Origin/CSRF,
login/me/Store isolation, fresh committed state, empty worker dependencies and
graceful stop/start. Browser E2E, real email and nonempty job execution on this
demo remain unverified. FE is failing in user testing and FE work is paused.
Historical private Vite helper TLS/page/config probes do not establish browser
E2E acceptance; BE launcher owns only HTTPS8103. Invitation SMTP
formatter does not match its parameterized route, so that callback stays unset.
See [runtime commands/trust/callbacks](runbooks/FULL_TEST_FLOW.md#integrated-demo-runtime).
Source worker/provider defaults remain OFF; fake delivery is the acceptance boundary.

Migration0024 joins0021 and0023. Integration-only repairs of these unreleased
revisions preserve v3 CHECK while the other branch still requires it; the final
v3 downgrade refuses retained grants. Historical v1.0 revisions are unchanged.
Traversal from0017/either branch head, both upgrade orders, retained grants and
schema parity are verified by test_integrated_migrations.py (6 cases).

Integration restores the existing exact signed quantity delta in grouped sales
preview changes; contribution grouping had dropped this projection field. Writer
totals and replace/merge semantics remain unchanged. Shared legacy tests now supply
source proof and explicit missing-stockout policy according to the accepted contract.
The scoped history max-version query now lives in the existing repository with the
same transaction-owned Session. New linked HTTP/PostgreSQL cases verify Owner grants,
Staff history imports and live revocation for calendar/usage/purchase permissions;
replayed acceptance does not restore revoked grants. These three cases pass with
fake invitation delivery and fresh-session persistence reads.
Gate completion/limitations are recorded in the integrated runbook; interrupted
full invocations are not reported as full-suite passes.

[FE010 response and artifacts](handoff/010_BE_CAPABILITY_RESPONSE_VI.md) distinguish
implemented integrated source from DESIGN_READY backlog. R05 scoped preview
aggregates and R09 captured budget summary are IMPLEMENTED C4 in local source; demo8103 remains the older snapshot.
R10 recipe split-report is deferred; source-proof/scope guards stay enforced.
Historical branch acceptance below belongs to its named commit, not a deployment.

## HISTORICAL INFORMATION — Import126b0f2 A3 acceptance, 2026-10-13

Public Import/configuration boundaries and real Import/Planning workers are verified
on a newly provisioned synthetic Store without seeded operational facts, using only
`shelfcash_import_test` / `shelfcash_import_tester`, provider OFF. Complementary master,
recipe, sales, term, opening and fee files work in both upload orders; declarations,
identity/unit review, Owner reusable-spec approval, preview/confirmation, atomic commit
and fresh reads lead to custom Planning and retained results. Default readiness remains
unknown when no default configuration exists; import completion is not Store-wide READY.

The explicit fixture oracle reconciles BASE14 cups /14 litres with opening12: one
pack4 at10, total10/fees0, fulfilled14/lost0, consumed14/expired0/ending2. Confirmed
zero stock instead needs four packs/total40/ending2. Planning creates no real stock
movements; opening/count0 retain one receipt and three justified movements. Subsequent
sales correction2→3 and budget100→80 preserve the original full retained aggregate
and both public Run responses, including input/config/capture/result/provenance.

Staff obtain exact permissions-v3 grants through public invitation/acceptance, reuse
an approved declared source and commit with no model call. Unknown tokens block;
an explicit alias changes the reusable spec, Staff cannot approve and Owner approval
is needed. Recipe conflicts remain blocked in both upload orders; ambiguous source
requires explicit selection. Mixed durable lost ACK reconciles and same-key retry
returns the same receipt/job without duplicate writes. Safety-floor value0 blocks
only computed Ingredients in the applicable horizon, not unrelated/future scopes or
forecast. Targeted verification covers11 unique PostgreSQL cases across selected runs;
existing A1/A2 rights/stockout/history/rollback/migration evidence is inherited, not
claimed rerun. Test-only repairs read mapping pages, remove the fixture's100-step
ceiling and submit sorted grants. No runtime/API/catalogue/migration delta in A3.

Limits: no full suite, browser/FE E2E, demo workbook compatibility rerun, real provider
or real forecast accuracy claim. No Auth worktree/DB, head merge, commit/push/deployment
or next feature slice. Repeatable selectors, expected outcomes and recovery are in
[FULL_TEST_FLOW](runbooks/FULL_TEST_FLOW.md); task commands/results remain in conversation.

## HISTORICAL INFORMATION — Import126b0f2 A2 acceptance

Four typed support schemas are mapped/reviewed/previewed/atomically committed into
append-only history revisions: declared calendar events, observed promotions,
recorded ingredient usage and purchase history. Read consumers are retained I04/I06
payload/provenance/version and H01/H02 category discovery. They are explicitly
history-only; no inventory movements/receipt/inbound/term, recipe reconciliation or
forecast feature/model/artifact changes. Unsupported safety stock blocks readiness
in computed scope as well as procurement execution. Existing capacity/supplier
limits/fees/budget/requirements consumers remain authoritative.

Owner's A2 permission decision adds six domain read/write keys to permissions-v3
(43 keys); Staff need explicit grants plus import.commit, current readback rights and
procurement.cost.read for purchase. Corrections require reason and explicit retained
version confirmation. Migration0021_import_support_history parents0019_sales_stockout,
expands the CHECK without granting rights and refuses destructive downgrade of
retained history/new grants. Auth0018/0020 remain independent. Targeted acceptance
uses only shelfcash_import_test as shelfcash_import_tester, provider OFF. OpenAPI
keeps54 operations/50 paths; H01/H02 filters and Import/Auth DTOs change additively.
Acceptance covers21 support-domain integration cases plus2 additive migration cases
and1 scoped unsupported-constraint readiness case, across targeted runs. Fresh reads,
correction/NO_OP/retry, rollback/concurrency, current Staff domain/read-price rights,
Store isolation and cross-file master dependencies pass. Staff with legacy grants
can still analyze Sales; new history rights are never implicit. Selected A1/source/
Auth, recipe/supplier/opening/count/completeness and retained reads regressions pass.
Qwen projection is compact supported metadata (`sheet_profile/2`, mapping_prompt/3),
not complete FE descriptors; existing96KB input limit and advisory validation stay
unchanged, offline transport tests pass. No full-suite/whole-FE/real-data claim.
See [Import](IMPORT_MAPPING_API_CONTRACT_VI.md),
[inventory](features/IMPORT_SCHEMA_INVENTORY.md) and [workflow](runbooks/FULL_TEST_FLOW.md).

## HISTORICAL INFORMATION — Import126b0f2 A1 acceptance

Sales preview freezes one Product/day effect with stable source/report contributions,
stockout and full location/provenance lineage. Exact duplicates collapse; conflicts
block; independent aggregation requires explicit disjoint confirmation. Stockout is
connected to schema-2 baseline/trained demand inputs and readiness. Historical
schema-1 JSON/digest/replay remains unchanged; see [ADR-A1](adr/ADR-A1-observed-stockout-demand-policy.md).

Additive migration `0019_sales_stockout`, parent `0017_planning_exports`, is verified
on `shelfcash_import_test` as `shelfcash_import_tester`, with no Auth dependency.
Upgrade preserves existing quantities/unknown observations; downgrade blocks known
observations. Fresh-Session acceptance covers correction, independent contributions,
duplicate/no-op, three stockout states, explicit missing-observation policy, causal
baseline/trained capture/replay and immutable Planning evidence. Current rights,
Store isolation, atomic rollback and concurrent stale-preview rejection are verified.
Contribution revisions require correction rights/resolution even when canonical
quantity/stockout is unchanged. Baseline replay retains each warning once.
Relevant targeted regressions passed; this is not a fresh full-suite or whole-FE gate.
Real-data demand quality is NOT EVALUATED. No development/Auth/shared-test DB migration,
head merge, commit/push or live provider call. Auth/Import heads remain independent
until integration. See [test workflow](runbooks/FULL_TEST_FLOW.md) for DB ownership.

CURRENT FACT: isolated local Gmail smoke is SMTP-accepted (one non-token email to
the configured username); inbox arrival is confirmed by the user. No further
smoke email is authorized. Auth demo uses its own
DB/role `shelfcash_auth_demo` at5434 and HTTPS backend8102, with only email delivery
enabled. HTTPS health/CORS and graceful shutdown were exercised on the empty DB.
The Gmail demo is retained at its B2 schema; B3/B4 migrations are applied only to the
guarded Auth acceptance DB. A demo restart using current source requires a separately
authorized demo upgrade; this slice neither migrates nor resets that database.
Real credential-email/browser acceptance remains unverified: the inspected FE
lacks signup/verify/setup/forgot/reset pages/adapters and HTTPS setup. Scope is
BE only; the BE launcher neither configures nor starts FE. Account workflow email to
the configured test username is authorized. See
[Auth local demo instructions](features/AUTH_SESSION.md#local-gmail-smokedemo-profile).

## HISTORICAL INFORMATION — Auth0fbb979 B1–B4 acceptance, 13/10/2026

The source composes 58 core HTTP operations plus health (59 operations/55 paths).
At Auth0fbb979, Alembic had head `0023_auth_permissions_v3` and63 application
tables. This source inventory is not proof of the schema/data in a running DB.
CURRENT FACT B4: backend/fake-delivery acceptance is COMPLETE / VERIFIED on
shelfcash_auth_test/shelfcash_auth_tester. Linked HTTP flows cover verified and
not-yet-registered invitees, exact grants/live revocation, two-Store isolation,
decline/new identity and password-reset session revocation, with fresh-session reads.
Catalogue v3/43 descriptors exactly matches Import A2 and retains all37 v2
descriptors; existing Staff receives no automatic grants. Additive Auth0023 extends
only the grants CHECK, preserves pending/token/membership state, and refuses unsafe
downgrade. Pending invitation delivery also recovers in a fresh fake-delivery process.
Affected Auth/Staff/API/schema regressions passed. No new route: N19 const:true
corrects its schema while keeping strict consent. The Import0021 CHECK overlap is
an explicit central BE merge concern, not a head merge performed here. Browser and
real credential-email workflow acceptance remain pending; targeted results are not
a new full-suite pass. Coverage and commands belong to the existing runbook.
CURRENT FACT B3: backend/fake-delivery acceptance is COMPLETE on
shelfcash_auth_test/shelfcash_auth_tester. Fresh-session state proves decline gives
no membership/grants/access; targeted tests cover token/proof/authority/expiry/CAS,
Origin/CSRF, replay/key conflict, rollback/lost acknowledgment, accept/decline/revoke
races, terminal offer/filter/events and later new-invitation acceptance. Related
invitation/B1/B2/session and migration/schema regressions passed after fixture and
route-inventory fixes. This is targeted coverage, not a fresh full-suite pass.

| Area | Implemented source and relevant acceptance coverage |
| --- | --- |
| Auth/Store/Staff | B1 signup/verify/resend and B2 forgot/reset with no automatic membership, cookie sessions, current Store grants, assisted setup, invitations/consent/audit; auth/staff API and persistence tests |
| Catalog/Inventory | Menu, live recipes, inventory/lots/movements, receipt/opening/threshold and future recipe calendar; public-read/stock/schedule tests |
| Import | Upload quota/seal/ACK, parser, typed descriptors/manual mappings, Owner profile approval, preview/confirm_review, nine-schema atomic commit, completion/history; Import API/unit/persistence tests |
| Forecast/Planning | Baseline/trained serving, explicit versioned configuration, readiness, durable acceptance/capture/worker, BOM/FEFO/procurement/2/comparison/winner, retained reads; forecast/planning tests |
| Retained/PDF | Ingredient/detail/reasons, Run/Import history, durable private PDF publication/download with current rights and hash/size proof; inspection/history/export durability tests |

Composition: `app/main.py`; one backend process with independent default-OFF
Import, Planning, PDF and account-email delivery thread flags. B1 atomically stores
unverified account/token/encrypted intent, then dispatches outside transactions using
the invitation dispatch loop. Completion verifies email and sets holder password
without issuing a session. B2 reuses RESET credential tokens and N7; requests
preserve credentials/sessions, completion atomically changes the password and
revokes all account sessions. B3 adds holder decline through IN01 with atomic terminal/event/receipt and no
membership/grants/Store access; Store creation remains outside these slices. Backend B1/B2 acceptance is COMPLETE with fake delivery on the isolated
`shelfcash_auth_test` database using role `shelfcash_auth_tester`. Coverage includes
fresh-session state, delivery recovery in a new process, token lifecycle, retry,
concurrency and auth/session/invitation regressions. Real credential-email workflows and browser delivery
remain unverified; the separate Gmail non-token smoke is inbox-confirmed. Configuration/FE flow:
[Auth feature](features/AUTH_SESSION.md). No automatic migration/reset/seed, model
activation, paid provider, order placement or customer selection persistence.

## CURRENT FACT ? local workflow and acceptance limits

The supported S4.11 environment uses `shelfcash_integration_s411` on port5433,
owned private runtime and explicit per-Store BASELINE. Automated persistence tests
own explicitly allowlisted `shelfcash_test`, `shelfcash_import_test`, `shelfcash_auth_test`
or `shelfcash_integration_test`; neither target is the development database.
See [the runbook](runbooks/FULL_TEST_FLOW.md).

CURRENT FACT: người dùng đã thử FE thật thành công ít nhất tới mapping lần đầu.
Điều này chưa chứng minh toàn browser flow import/planning end-to-end thành công.
HISTORICAL INFORMATION: tag `v1.0` tại `cf6732e` giữ discovery lấy dòng đầu làm
header, đã push cùng nhánh `feat/from_forecast_to_decision_run`.
CURRENT FACT trên `feat/import_mapping_rules`: discovery nhận diện header trong
tám dòng đầu sau preamble đơn cột, giữ raw preamble/header và số dòng vật lý;
controlled aliases, indexed candidates/reasons, Owner full-spec group review,
approved-profile reuse và cảnh báo drift theo scope đã khai báo. Lần đầu vẫn cần
nguồn/định danh/conventions và xử lý mọi cột mơ hồ/ngoài phạm vi. Không auto-approval.
Adapter OpenRouter có bounded semantic candidates/reasons, safe diagnostics,
configurable sample/token/timeout/provider bounds và stale mapping publication fence.
Cần opt-in mặc định OFF và key. Live gateway probe trên POS demo qua Qwen3.5-9B /
DeepInfra đã trả proposal hợp lệ: SLX → sales.quantity, giữ hai target RULE, bốn
cột ngoài schema để null; không activate profile/commit. HTTP/DB lifecycle tests
vẫn dùng mock; một live probe không chứng minh whole browser flow hoặc reliability.
M04 EXCEL_SERIAL + workbook epoch cho Owner duyệt deterministic date-only normalization;
không tạo count/receipt timestamp. Header reorder/epoch change là profile drift;
profile XLSX cũ thiếu epoch cần review lại. Unknown/unsupported/README không tự IGNORE;
atomic commit và permissions giữ nguyên. Sáu workbook gốc không bị sửa; 21/72 cột
nghiệp vụ có target rules, 51 còn unresolved/ngoài workflow, 2 cột README chỉ ignore hints.
Chi tiết/giới hạn tại [Import feature](features/IMPORT_STAGING_PREVIEW.md).

CURRENT FACT: đối chiếu [legacy handoff](../IMPORT_SCHEMA_LEGACY_HANDOFF_VI.md) và
current source xác nhận cả chín import schemas có canonical writers; core gaps cần
tách source resolution, consumer và readiness khỏi registry/mapping coverage.
Recipe per-serving/batch đã có explicit quantity_basis column/shared resolution,
exact whole-yield normalization, source-value/line-basis provenance và old-profile
review guard. Existing writer/BOM/readiness dùng canonical values; không migration,
loss vẫn áp một lần ở BOM. Supplier price/MOQ có explicit source basis, denominator
quantity/unit, exact pack price và physical MOQ ceil; source/canonical DTO tách riêng,
preview/completion giữ semantics/raw/declaration/rule chains. Old profiles thiếu basis
cần review; fees thuộc preview read-set. Coverage tại term start không thay horizon
readiness. Excel opening_stock đã nối InventoryUseCases writer và receipt identity
của N6; inventory_count giữ target/delta trên existing lots. Whole-batch dependencies
gồm master rows/reservations, nested declaration bindings và current scoped completeness
nối operational/2 capture. Analyze không auto-bind từ signature; M04 source
declaration trước compatible reuse, unknown row identity không tự fork profile.
Recipe cùng Product/version qua nhiều sheets bị RECIPE_SOURCE_SCOPE_AMBIGUOUS;
split-part grain chưa hỗ trợ. Fresh Store public intake/custom Planning không seed
business entities; R01 vẫn unknown nếu default configuration chưa có. Explicit EMPTY
với retained zero lots dùng được ở operational/2; historical /1 giữ semantics cũ.
HISTORICAL INFORMATION: legacy stockout có consumer forecast thật theo source.
CURRENT FACT: A1 đã nối observed stockout và versioned demand consumer với acceptance
trên DB Import riêng; không mở A2. Sáu workbook là acceptance inputs, không schema authority.
Đối chiếu legacy là static source audit, không chạy legacy runtime. Recipe source
acceptance dùng synthetic public flow/guarded PostgreSQL test, fresh-session read,
dated BOM và recipe-dependency readiness; Supplier acceptance dùng fresh-session term
read, exact fixed-basket budget/MOQ oracle, public planning capture/retained Run và
fee readiness. Không real-provider/whole FE acceptance.
Danh mục và trace thuộc [Import schema inventory](features/IMPORT_SCHEMA_INVENTORY.md).

HISTORICAL INFORMATION: prior S4.11 verification recorded API/native-worker/fresh-
session/PDF/restart gates and twelve current-screen Edge gates. Those are previous
results, not a new run. Current FE has Import mapping/preview/confirm/commit and
planning C01-C05/C08 source. Whole mapping browser continuation remains NOT_RUN;
PDF and planning-history UI remain incomplete. S4.11 stays PARTIAL; API acceptance
cannot certify the whole UI. No FE repository changes are part of cleanup.

## TECHNICAL DEBT / known discrepancies

- Historical review TD-BE-001–013 (`008_TechDebt.md`, original reference not
  present in this repository): Store-wide mapping
  queue, supplier discovery, detailed preview projections, export discovery và
  Today facts chưa có public capability tương ứng. V01 canonical Ingredient paging,
  M02 auto filter/batch counters và C01 budget absence/create đã có source contract;
  không đồng nghĩa FE integration acceptance hoặc deployment đã xác minh.
- CURRENT FACT B4: N19 structural drift is corrected with const:true and strict
  validation; B3 implements decline separately through IN01. Historical review
  status outside this worktree does not override these source/test facts.
- Cold deep retained validation measured about13s for a synthetic50-Product Run;
  this is historical diagnostic evidence, not a capacity/SLA guarantee.
- Privileged SQL/tracked ORM can bypass some internal application guards. Public
  authorization does not retroactively turn trusted internal commands into public APIs.
- Real-data forecast accuracy and long-term retention/operational purge are not
  evaluated/approved. Model artifacts and operational private resources are preserved.

## CURRENT FACT - authorized contract/query-boundary repair, 2026-10-12

ADR-013 permits authorized self-approval and remains ACCEPTED, not superseded.
Current Owner-only reusable-profile approval/activation implements the detailed
product authority; Staff may propose, and batch confirmation/commit separately
recheck current rights. Original unimplemented ADR status is historical.

Import history, public Planning, Planning worker and PDF query access now lives
in concrete repositories using the caller Session. Application retains authority,
transactions, locks, idempotency and recovery orchestration. Recipe adapter fakes
explicitly filter assignment/Store/Product; Money tests distinguish new-input
bounds, numeric-equivalent NO_OP and exact retained evidence. Independent API
inventories include current inspection/export/history paths and GET methods.
Full-suite collection uses importlib and qualified shared-fixture imports to
retain both unit/integration PlanningRun modules with identical basenames.
Real Planning/PDF process test targets use a fixture-free helper module for
Windows spawn; service calls, DB guards and original waits remain unchanged.
No API, schema, permission, business calculation or worker policy changed.
Verification outcomes and limits are reported in the conversation.

## CURRENT FACT ? documentation/tooling ownership

Shared API conventions and Catalog/Inventory now belong to API_CONTRACT, with
three independent Authorization/Import/Planning contracts. Original10/10 OpenAPI
bytes, archive/entry provenance and pinned hashes survive as a fixture and the
compatibility changelog. Browser dependency manifests belong in scripts/browser.
Routine outputs use ignored runtime/verification; canonical source, fixtures and
business audit/provenance are kept. No cleanup changes to business APIs/algorithms/
schema are authorized. Exact current verification is reported in the conversation,
not accumulated here as a PASS log.

## HISTORICAL INFORMATION — cleanup verification, 2026-10-12

On isolated local shelfcash_test, the selected unit/API/public-planning/export
run returned 1039 passed, 15 failed, 2 skipped. This is not a full-suite pass.
Observed failures: application query boundary (1), obsolete recipe-repository
mocks missing assigned_only (11), fee precision expectation beyond current
input limit (1), outdated exhaustive OpenAPI inventories (2). Product source and
these tests were hash-identical to the pre-cleanup worktree; none was weakened.
This establishes unchanged related files, not reproduction of all 15 failures
immediately before cleanup or equivalence of the entire test environment.
Tooling tests pass (20). Real native HTTP import/commit/readiness/planning/retained
PDF, current-rights/replay/negative cases and same-cookie restart passed against
a separate test profile, with fresh-session persistence assertions. This evidence
does not establish whole FE UI acceptance or real forecast quality.
