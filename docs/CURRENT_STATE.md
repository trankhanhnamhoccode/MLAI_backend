# Current state

## CURRENT FACT — A3 backend acceptance complete, 2026-10-13

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

## CURRENT FACT — A2 backend acceptance complete in the Import worktree

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

## CURRENT FACT — A1 acceptance complete in the import worktree

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

## HISTORICAL INFORMATION — mốc phát hành v1.0, 12/10/2026

The source composes 53 core HTTP operations plus health (54 operations/50 paths).
Alembic has one head `0017_planning_exports`; registered metadata has 60 application
tables. This source inventory is not proof of the schema/data in a running DB.

| Area | Implemented source and relevant acceptance coverage |
| --- | --- |
| Auth/Store/Staff | Cookie sessions, current Store grants, assisted setup, invitations/consent/audit; auth/staff API and persistence tests |
| Catalog/Inventory | Menu, live recipes, inventory/lots/movements, receipt/opening/threshold and future recipe calendar; public-read/stock/schedule tests |
| Import | Upload quota/seal/ACK, parser, typed descriptors/manual mappings, Owner profile approval, preview/confirm_review, nine-schema atomic commit, completion/history; Import API/unit/persistence tests |
| Forecast/Planning | Baseline/trained serving, explicit versioned configuration, readiness, durable acceptance/capture/worker, BOM/FEFO/procurement/2/comparison/winner, retained reads; forecast/planning tests |
| Retained/PDF | Ingredient/detail/reasons, Run/Import history, durable private PDF publication/download with current rights and hash/size proof; inspection/history/export durability tests |

Composition: `app/main.py`; one backend process with independent default-OFF
Import, Planning and PDF thread flags. No automatic migration/reset/seed, model
activation, paid provider, order placement or customer selection persistence.

## CURRENT FACT ? local workflow and acceptance limits

The supported S4.11 environment uses `shelfcash_integration_s411` on port5433,
owned private runtime and explicit per-Store BASELINE. Automated persistence tests
own explicitly allowlisted `shelfcash_test`, `shelfcash_import_test` or `shelfcash_auth_test`; neither target is the development database.
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

- [Review TD-BE-001–013](../008_TechDebt.md) giữ tất cả OPEN: Store-wide mapping
  queue, supplier discovery, detailed preview projections, export discovery và
  Today facts chưa có public capability tương ứng. V01 canonical Ingredient paging,
  M02 auto filter/batch counters và C01 budget absence/create đã có source contract;
  không đồng nghĩa FE integration acceptance hoặc deployment đã xác minh.
- N19 OpenAPI accept:boolean rộng hơn validator true-only; false trả422, không
  persisted decline. Authorization contract ghi drift; chưa sửa business lifecycle.
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
