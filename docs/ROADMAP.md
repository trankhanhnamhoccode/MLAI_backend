# Remaining work and acceptance gates

## CURRENT FACT / limits — bounded owner summary integration

S3 local integration completes important-warning and distinct-purchase-line acceptance with
offline/fake-provider tests. Profile/6 preserves historical profile/5 and earlier
replay. Final-source live Gemini, independent owner UX, browser/FE integration and
production acceptance remain unverified. Historical S2.1 live evidence is pinned
to its original fingerprint; closed ledgers are not reopened. Local integration
does not push remote, deploy/restart runtime8103 or enable providers. Operator
activation is a separate authorized step, using the
[feature](features/DECISION_ASSISTANT.md#current-fact--bounded-owner-summary) and
[runbook](runbooks/FULL_TEST_FLOW.md#summary-narrative-s1). No new engine work follows.

TECHNICAL DEBT: broad regression still has historical pre-Assistant schema/head
assertions and feature-specific DB/runtime fixture prerequisites. These existing
main-base failures are separate from passing affected summary verification; no
test or applied migration is weakened to hide them.

## CURRENT FACT — P1/P1.1 owner-friendly PDF

Backend presentation /3 from approved9a80f970 is integrated locally with history;
P1/P1.1 owner review approved, deployment/browser acceptance remains separate. N10/N11/EX01 and retained /1,/2
compatibility remain. No FE/engine/capture/provider/migration work, remote push,
deployment or next slice. Existing Summary stays independent; no Summary insertion into PDF. Store/Supplier name capture and global unit display
aliases remain separate gaps. Primary comparison uses the same P1 synthetic oracle;
not the original169-page Run or real business/whole-FE acceptance.
[Policy](PROCUREMENT_API_CONTRACT_VI.md#154-pdf--n10n11-thêm-không-thay-planning-state),
[manual verification](runbooks/FULL_TEST_FLOW.md#owner-pdf-p1).

## CURRENT FACT - L5 backend source integration

Decision Assistant L4.1 checkpoint1f9b5c5 is integrated with main base8b09685 in an
isolated worktree. Backend integration VERIFIED by required focused combined-source gates. V6 default,
candidate8 explicit controlled trial only; summary/chat flags independently OFF,
forecast challenger test-only/OFF and Import Qwen separate. Local integration is
not deployment or browser/live E2E acceptance; these remain PENDING. No next slice
or activation follows automatically. Current feature/runbook own scope and limits;
older isolated L4/L5-pending accounts below are historical checkpoints.

## CURRENT FACT — Decision Assistant L3 / remaining L4–L5

L1 and L2/deterministic foundation checkpoints are local; foundation implements cold durable consistency evidence reads,
typed summary renderer/fallback, constrained model presentation and AS01/AS02
durable receipt/claim/publication lifecycle. Focused unit/API and owned PostgreSQL
tests exercise fresh-process/revocation/concurrency/ACK/restart behavior with no
engine/provider network. Cold misses no longer require cached verification. See
[implementation/limits](features/DECISION_ASSISTANT.md) and
[summary / conversational chat contract](PROCUREMENT_API_CONTRACT_VI.md#decision-assistant).

- L3.1 checkpoint44b45189 (after local L3 checkpoint f9dba875): structured context/pending
  clarification, question obligations, typed assertions/prose checks and bounded
  repair/one regeneration. Existing L3 implemented: AS03 optional conversational prose, sealed scoped facts,
  bounded user-history context, clarification, independently configured provider,
  deterministic assertion grammar/coverage checks and durable provider lifecycle.
  No what-if/ordering/config/inventory writes. Finite resolution and conservative
  grammar may reject legitimate paraphrases; general language entailment/quality
  remains unverified. Summary presentation and import behavior remain separate.
  Live acceptance remains NOT PASSED:10 progressive attempts retained original
  fallback finals; final wording fixes have offline AS03 acceptance only. The separately authorized L3.1 synthetic batch uses a new ledger;
  final-source live acceptance remains PENDING after6 calls (3 development
  accepted; tradeoff false reject/unknown timeout then freeze2 HTTP429). No paid
  retry/model change. Final context/pair fixes are offline-only; current limits
  and cost are in the feature/runbook, separate from original NOT_PASSED.
- L3.2 checkpoint a29ae1f3: dynamic intent/evidence/detail prompts, two placeholder examples,
  resumed why/context and explicit slots/null/polarity, comparative sign/cost-role
  checks and V3/V4/V5 pinned replay. Current prompt5/validator6/plan6, renderer7.
  Evaluated V5 live PARTIAL:11 completions,7 accepted/1 regenerated/1 fallback/
  1 clarification; last context entity switch unexecuted at shared cap30/30.
  Fixed14-case Codex-labelled offline corpus0FA/0FR;2 additional valid live
  paraphrases rejected in V5, fixed offline in V6 with24 unit/3 real AS03-PG
  fake replay tests. V6 was PENDING at that checkpoint; prior results stay historical.
  Separate L32-V6-acceptance-1 now passes the frozen V6 synthetic matrix with limits:
  11/16 completions,9 accepted/1 regenerated/1 clarification, all4 conversation turns.
  Correct slots with omitted simulation prose were rejected then regenerated;
  no application source change. All11 finals checked current rights/Store isolation,
  fresh persistence and replay0. Known USD0.0203539, reservations0.1546512/0.30,
  no unknown usage,5 unused slots. Quality review is Codex-authored, not human-panel
  evaluation. Proof/comparison remain verbose, opaque option IDs and clarification
  disposition mismatch remain. New acceptance harness/tests/docs are WIP. Linked SQL28 pass;
  V5 focused12 pass plus affected V4 replay1 pass after test expectation fix;
  unit/API34 pass. All saved finals fresh-persisted/replay0/GET405. Budget is
  exhausted by attempts, not dollars: known0.0551248 plus unknown reserve0.0281184.
  No real/unseen evidence, reviewer model, new route/migration or whole-chat PASS.
- L4 finite evaluation complete with limits, implementation WIP: V6 default retained;
  explicit candidate7 adds typed grouping, local labels, consistent clarification
  diagnostics and resolver5 failed-run intent.36 frozen scenarios originally18/18;
  eight evaluation cases exposed to development, remaining9 offline/1 SQL pass
  both versions. Candidate35 pass/1 separate security gate; baseline34 pass/1 intent
  coverage gap/1 security gate. Six paired synthetic live scenarios and full4-turn
  chain: baseline9 calls versus candidate8;17/24 total, USD0.0319601 known,
  reservations0.2390064/0.50. Candidate improves proof/comparison/no-winner prose,
  not uniformly quantity/why. Inherited valid-paraphrase false rejection remains;
  no independent human/unseen/general grounding claim or automatic default switch.
 20/35g detection is offline projection-only; live retains the existing20/20g Run.
  Broader quality/real-data evidence and review precede any default/integration choice.
- L5 pending: FE/browser/runtime integration and broader operational acceptance.
  L4.1 focused acceptance is PASS WITH LIMITS after L4 checkpoint46d15459;
  derived candidate8 (prompt7/validator8/selection8/renderer9/resolver5) qualifies
  for explicit controlled trial in the verified scope, with V6 still default.
  Capture/engine/persistence factory proves20g/35g across all4 real HTTP/DB/live
  turns; actual failed/partial and mixed-path comparison preserve scope.5 accepted/
  1 clarification,5 calls, USD0.0099809; shared L4 now22/24, known0.0419410,
  reservations0.3093024/0.50.2 unused, no new group or older-slot transfer.
  Full-clause paraphrase fix and optional simple why factors keep old6/7 replay.
  Finite quality review and focused security/persistence checks do not authorize L5.
  Summary HTTP/owned-DB revocation/fresh retained reads/restart are L2 acceptance,
  not a claim that chat/whole FE or production deployment is verified.

No readiness/challenger merge is required to explain existing verified Runs;
data admission and model quality do not become proven by wording/projection tests.
No automatic next slice follows L2; runtime8103/main/FE/other WIP remain outside it.

CURRENT FACT: the FE019 recovery repair preserves current authorization and public
contracts while correcting delayed Import review replay and canonical-commit
exception reconciliation. Existing reads/replay cover retained positive outcomes;
recovery after losing key/body is operation-specific and has no negative proof.
ACCEPTED DECISION: FE persistent pre-dispatch intent journal under the explicit
handoff field allowlist; FE implementation/F5/browser acceptance remains pending.
Cross-device committed discovery or an explicitly fenced terminal protocol is
separate BACKLOG, not an endpoint authorized here. File delete/unseal,
immediate canonical resolver writes, standalone Preview choices, pending procurement
decisions and richer public token/session continuation remain unimplemented feature
scope. See [FE019 audit](reports/FE_019_BACKEND_RECOVERY_AUDIT.md) for precise existing
capabilities, dependencies and decisions; no new endpoint/business policy is approved.

CURRENT FACT: local launcher shutdown watcher tolerates Windows observation-file
replacement failure; targeted lifecycle tooling regressions cover bounded retry,
persistent denial and run-scoped stop after write failure. Native restart/browser
acceptance after this repair remains separate; clean-source start guard retained.

CURRENT FACT: optional user-requested synthetic local Owner/Store CLI is available
as `python -m scripts.seed_local_owner`; repeatable login-ready fixture without
business seed or customer onboarding changes. See [local setup/recovery](runbooks/FULL_TEST_FLOW.md#customer-self-service).
`python -m scripts.seed_local_staff` adds one synthetic Staff through invitation
consent to that Store, initial `menu.read`; current grants remain Owner-managed.
Browser FE and business-feature acceptance remain separate gates.

CURRENT FACT F4: source is integrated into main local; isolated C0 test opt-in reaches the real ForecastRun/Planning worker
and retained public reads; production/default serving remains host, C1 exploratory.
F3 checkpoint `5a8e0a8` is PARTIAL19/24 synthetic, not production/real-impact acceptance.
F4 local checkpoint is `8f4d908`; technical test-only acceptance VERIFIED, product
activation NOT IMPLEMENTED, production promotion LOCKED. F4.1 profiling COMPLETE
for its frozen offline subset (one attempt21.5297089s, one Planning/one inference,
zero native solves). A remains INCOMPLETE/no winner, so exact output equivalence
and native solver latency are unverified. Schema/conversion and semantic revalidation
costs are measured; optimization, representative C latency and general F3 timeout
attribution require separate work. Old/new claims stay consumed; no retry or business
optimization in F4.1. F4.1 checkpoint is `b9ec978`. F4.2 checkpoint `8537e12` reuses the static
quantity adapter with differential/fixed-output checks; six uninstrumented Planning
runs show lower median18.8043 to 10.6877s on one fixture, unchanged selected facts but
changed deadline coverage/proof. No broader validator refactor or production claim;
representative quality/latency/activation gates remain. See [F4.2](features/FORECAST_ENGINE_INTEGRATION.md#forecast-f4-2);
Local main integration is verified; no next slice, promotion, deployment or demo
restart/migration is authorized. See the
[canonical F4 boundary/gates](features/FORECAST_ENGINE_INTEGRATION.md#forecast-f4)
and [F4 verification](runbooks/FULL_TEST_FLOW.md#forecast-f4). The single metadata2
migration head follows0027; future integration of Assistant/import migrations still
requires graph review. Preserve historical replay source/artifacts; representative
latency/real-data eligibility, browser/recovery/rollback and explicit demo activation
authorization remain. No FE delta is required for this unchanged public API.

## ACCEPTED DECISION / CURRENT FACT — forecast engine challenger

Phạm vi E1 được người dùng duyệt: giữ BE host và toàn bộ Planning business authority;
forecast engine mới qua adapter riêng, không LLM/OpenRouter trong E1–E5. E1 COMPLETE
compatibility/protocol; E2 COMPLETE internal typed opt-in adapter với pinned installed
forecast-only source/dependencies, native fixed inference và private retained replay.
Tiny synthetic correctness VERIFIED; không production integration/accuracy/promotion.
Main/demo/customer DB và serving artifacts giữ nguyên; E1–E4/admission checkpoint local
`eaf40b9`, merge main readiness tại `1c48162`; thay đổi tiếp theo giữ WIP để review.

[FORECAST_ENGINE_INTEGRATION](features/FORECAST_ENGINE_INTEGRATION.md) là canonical
owner của matrix, data/artifact inventory, replay/availability/reconstruction/CQR
boundaries, benchmark/promotion và các gates E1–E5. E2 native correctness VERIFIED;
E3 PARTIAL: causal training/scoring harness và A/B/C native synthetic replay VERIFIED;
real accuracy REAL_BENCHMARK_BLOCKED, promotion INSUFFICIENT_EVIDENCE.
E4 PARTIAL: counterfactual shared-facts host Planning + fixed-basket realized harness;
bounded execution INCOMPLETE khi chạm wall budget, checkpoints giữ nguyên, không
thay fixtures/search resources để tìm kết quả đẹp. Real impact REAL_IMPACT_BLOCKED.
E5 production activation/promotion NOT_STARTED; isolated technical integration is
covered separately by the explicit F4 scope above. Thiếu authorized unseen demand/
vintages/calendar và historical operational snapshots chặn real quality/impact claims.
Không mở production serving. CURRENT FACT: A/B demo hồi cứu manifest/2
đã chạy và replay8 checkpoints VERIFIED trên baseline đến08/07, với declarations
được duyệt theo dataset hash. Đây là EXPLORATORY A/B, không phải bằng chứng C.
C tại /2 vẫn BLOCKED (calendar vintages/native train minimum). CURRENT FACT /3:
user-authorized calendar assumption và point window20 ngày đủ native support84+,
giữ calibration28 và strict holdout quarantine. A/B/C đã chạy mới cùng scope/masks,
420 forecasts và exact replay12 checkpoints VERIFIED, exploratory only; không chọn
winner từ aggregate khi Product/horizon regressions còn hiện diện. /2 và E3/E4 cũ
nguyên bytes. E4 bộ mới vẫn BLOCKED và không chạy; không có POS09–15/07 để score.
Exact selection/metrics tại [canonical integration](features/FORECAST_ENGINE_INTEGRATION.md#demo-baseline-ab).
Current /3 support/results/limits tại [demo A/B/C](features/FORECAST_ENGINE_INTEGRATION.md#demo-abc-v3);
checkpoint A/B/admission `c4ff88a`, exploratory /3 checkpoint `a863fb5`.
CURRENT FACT F1: generic read-only historical replay verified12 checkpoints/4 artifacts,
typed budget representation fixed without changing original identities; independent
1176-group metric audit agrees. H6 advantage is closure-concentrated (106.484% of net
B−C benefit); quantile undercoverage precedes point/sorting. No model improvement
or general superiority proven. F1 checkpoint `6a50d815ba983f511a92388b2ade18d6fd6b4b93`;
E5/promotion NOT_STARTED. CURRENT FACT F2: authorized shared closure comparison and
one endpoint residual-quantile variant completed in one3.844s batch,0 boosters/
point/CQR fits,4 endpoint artifacts on exact retained /3 origins. No anchor/feature
search or fresh data found/assumed; all evaluation remains exposed development.
C1 improves aggregate endpoints/coverage while preserving P50/CQR but fails frozen
validation subgroup guard; retain C0 endpoints. Common-policy B has lower exposed
evaluation point error; no serving winner is selected. No-fit replay, independent
1540-group score audit and original-file preservation verified. F2 checkpoint is
`fcb33abb9c2316d41d564d5653233f6dc4e80a5e`.
Details and limits: [canonical F2](features/FORECAST_ENGINE_INTEGRATION.md#forecast-f2).
CURRENT FACT F3: authorized counterfactual host Planning on retained F2 B/C0/C1,
two chronological origins/four explicit synthetic fixtures/three arms; main
comparison B_COMMON vs C0_COMMON, C1 not selected. Source-faithful real impact is
still BLOCKED. Single300s hard-capped batch PARTIAL with19/24 retained cases,
5 missing, no resumed batch.50 native solve attempts recorded, no forecast fits.
Both finite-oracle cases pass without upgrading native proof. Common baskets on
24/06 yield identical fixed-basket observed service; on01/07 scarce_purchase B
buys3 packs/63 VND vs C0/C1 4 packs/83 VND, but censored truth blocks realized
evaluation. No empirical production winner, savings or inventory-impact claim.
F3 is checkpointed at `5a8e0a8`; [canonical F3](features/FORECAST_ENGINE_INTEGRATION.md#forecast-f3)
owns assumptions, resources, proof/partial results and replay limits.
HISTORICAL INFORMATION: F3 checkpoint described F4 as NOT_STARTED/unauthorized;
that status is superseded by the isolated test-only F4 acceptance above. Product
activation/promotion still requires reviewed forecast choice, provenance/availability,
operational completeness and the remaining runtime/browser/rollback gates.
No main/FE integration or automatic deployment is authorized.

## CURRENT FACT / PROPOSAL — data readiness D1–D5

ACCEPTED DECISION: readiness theo facts/semantics của action/scope, không yêu cầu
đủ sáu files. [Canonical policy](features/DATA_READINESS_POLICY.md) sở hữu source
matrix, current gaps, issue/assumption proposal, API impact và acceptance cases.

| Slice | Status và gate |
| --- | --- |
| D1 audit/policy | COMPLETE, local checkpoint c930dfe66cfda5de5896164e16fcf8f4c7acaefe từ main052cddee; documentation-only, không runtime/API delta; đã tích hợp main local cùng D2–D5, chưa push/deploy. |
| D2 forecast eligibility/fallback | COMPLETE, local checkpoint9f720caf01fdf0a8f586c049660a2fcc9447ade3. Shared choice + typed internal assessment, scoped all-censored R01/C01/Today fix, dependency/runtime-vs-integrity; focused forecast/HTTP/PG/replay gates, OpenAPI giữ nguyên. Không full-suite/accuracy claim. |
| D3 confirmed facts/partial scope | COMPLETE, local checkpoint d0f3716c261f6634d5fcd5ae886c00cf3014276c: accepted offer_eligibility/1, scoped local omission/source proof, remaining eligible domain/zero purchase; shared unknown/invalid/safety vẫn block; old-policy queued/retained payloads giữ semantics/digests. |
| D4 public readiness/warnings | COMPLETE, local checkpoint72415332e2a5224ab9909d54606d7e7e374bdd18: contextual R01/C01 query + scope/version/forecast metadata, shared resolver/admission và warnings; Today default consistent, retained C03/C08 source references. I06 retained schema unchanged. |
| D5 backend linked acceptance | VERIFIED, committed11ef320a5873fc4dc314fdad63878db5f8a8b38c và tích hợp main local giữ ancestry: public setup/custom/omission/zero purchase/shared fee/retention, independent small oracle và final D2–D5 focused unit/API/PG gate. Không production source/contract delta. Không yêu cầu FE/workbook đủ facts; timing root cause còn mở; không E3/E4/training/accuracy benchmark. |

Main đã có baseline và recognized fallback; không mở lại từ đầu hoặc dùng research
calendar gate chặn product baseline. E3 real accuracy blocked/E4 synthetic incomplete
thuộc challenger branch/WIP, không tích hợp hoặc đổi kết quả trong D1. Main local
runtime/config/DB/artifacts và mọi challenger WIP được bảo toàn.

CURRENT FACT — source integration giữ73 operations/66 paths/head0027; final focused
gate chạy riêng PostgreSQL5437 (limited integration role), không đổi demo8103.

CURRENT FACT — checkpoint E4/admission và merge main readiness vào challenger đã
hoàn tất trong nhiệm vụ riêng; manifest/2 A/B và kết quả được mô tả tại canonical
integration phía trên. Không sửa frozen E3/E4 hoặc gộp các protocol. C/E4 trên bộ
mới vẫn BLOCKED; E5/promotion và Decision Assistant không thuộc execution này.

D5 không bao gồm FE/browser E2E hoặc real accuracy/savings. Các hạng mục đó chưa
nghiệm thu, không là blocker cho backend-only acceptance. D3 deadline instability
chưa có root cause; bounded diagnostics không đóng issue bằng một lượt pass.

## CURRENT FACT

Self-service Store/customer local IMPLEMENTED: T03 additive,73/66/head0027/72 tables;
verified holder tạo Store/Owner atomic, no seed/provisioning requirement. Canonical
backend own venv/runtime/TLS, guarded local/test DBs; historical source WIP retained.
Email/worker setup and14 flows in [runbook](runbooks/FULL_TEST_FLOW.md#customer-self-service).
FE signup/EMAIL_VERIFY callback/create Store/browser acceptance remains BLOCKED/PENDING;
không mở subscription/OAuth/transfer/delete hoặc deferred recipe/AI/what-if.
Backend focused83/schema210 và owned HTTPS runtime/limited DB/4 business workers đã
VERIFIED, no business seed. Email/model OFF, old demo/data/WIP preserved; các gate
overlap, không full-suite hoặc real email/browser acceptance claim.

### HISTORICAL INFORMATION — C5 checkpoint

C5 backend linked acceptance VERIFIED (3+20 cases, migration/tooling gate25);
C4 checkpoint eabab333. Runtime HTTPS8103/head0026 VERIFIED, browser E2E PENDING, nên C5 tổng thể
chưa COMPLETE. Source72/66/head0026; R05/R09 implemented, R10 deferred.
Xem [canonical C5 matrix/commands](runbooks/FULL_TEST_FLOW.md#linked-acceptance-c5).

### HISTORICAL INFORMATION — acceptance trước C5

C1 notification foundation committed locally at f85c7cdd on `feat/notifications-foundation`;
C2 COMPLETE backend acceptance committed locally at b9fe048a6c64ffb79438068076ee3e9d99d75fda.
C3 COMPLETE backend acceptance, local commit b1c906a0ea65a3b20a46d161166668d26701f0a9; final targeted105 passed,
affected regressions/fail→fix and limits in runbook; no full-suite/browser claim.
NF01–NF03 + PR01–PR04/MQ01–MQ03, source69 operations/64 paths, additive0026, own guarded
notifications test DB. Inbox/read/current-authority and durable local delivery
acceptance covered; existing N13 grants producer is connected atomically.
PR union decisions and MQ pinned queue/N5 extensions connect atomic producers and
current target authorization. Profile approval leaves preview/confirm/commit explicit.
Notification worker default OFF; retained demo8103 remains0024/OpenAPI59.
Browser/live email/provider remain unverified; C2 local checkpoint, no merge/push.
See [contract status](NOTIFICATION_API_CONTRACT_VI.md) and
[verification/run commands](runbooks/FULL_TEST_FLOW.md#notifications-c1).

Local unified source: Import126b0f2 + Auth0fbb979 on feat/integrate-import-auth;
integration verification uses its dedicated DB/head0024. A separate integrated
BE demo is prepared at HTTPS8103 on shelfcash_integration_demo/head0024, with
limited runtime/migration roles, explicit synthetic accounts and three workers.
Runtime TLS/Auth/isolation/idle dependencies and graceful lifecycle are verified;
browser E2E, actual nonempty jobs on this demo and real credential-email workflow
remain unverified. FE work is paused following errors in user testing.
FE HTTPS/API configuration and verification/invitation delivery
callback alignment remain FE integration prerequisites; email/provider stay OFF.
Commands and private credential/trust instructions belong to
[FULL_TEST_FLOW](runbooks/FULL_TEST_FLOW.md#integrated-demo-runtime).
Branch milestones below remain their historical acceptance evidence.
FE artifacts: [response010](handoff/010_BE_CAPABILITY_RESPONSE_VI.md).

Local Gmail preparation: one SMTP smoke message accepted, inbox user-confirmed;
isolated Auth demo DB and HTTPS8102 lifecycle checked. BE-only scope: FE HTTPS/API configuration,
self-service pages/adapters and real workflow-email/browser acceptance remain
open with the FE team. No further smoke email; account workflow email to the configured
test username is authorized. Operational steps belong
to [Auth feature](features/AUTH_SESSION.md#local-gmail-smokedemo-profile).

| Scope | State | Boundary |
| --- | --- | --- |
| S0/S1 | Implemented | PostgreSQL/local tooling, operational models/repositories and typed internal application paths |
| S2 | Implemented mechanics | Baseline/trained quantiles, retained inputs/evaluation/artifacts/replay; real-data quality NOT EVALUATED |
| S3.1-S3.6.4 | Implemented internal paths | Validated decision/BOM/serving/FEFO, procurement/1 and /2, comparison/selector, operational capture/setup and durable PlanningRun |
| S4.1-S4.10 | Implemented backend scope | Auth/Staff, public Menu/Inventory, Import/commit, calendar/config/readiness, public Planning, retained history/PDF |
| S4.11 | PARTIAL | Local integration/API coverage exists; whole mapping browser continuation NOT_RUN; PDF/planning-history UI incomplete |
| A1 Sales/reimport + stockout | COMPLETE | Migration0019 and targeted PostgreSQL acceptance on owned shelfcash_import_test; fresh-session sales/stockout, causal capture/trained/replay, retained Planning, rights/isolation/rollback/concurrency; real-data quality not evaluated |
| A2 support history + constraints | COMPLETE backend scope | Four history-only schemas, append revisions/current domain grants and retained reads; 24 targeted DB acceptance cases plus affected regressions; R01 scoped unsupported safety-stock blocker; no full-suite/whole-FE or forecast-feature claim |
| A3 Import → readiness → Planning | COMPLETE backend acceptance | Fresh provisioned Store/public imports and config/real workers/fresh reads; both upload orders and exact purchase/service/stock oracle; Staff invitation/source reuse/Owner spec change, conflict/ambiguity, scoped unsupported safety and lost ACK/retry; 11 unique targeted DB cases plus inherited A1/A2 evidence; no browser/full-suite/real-accuracy claim |
| B1 | COMPLETE backend/fake-delivery acceptance | A02/A05/A06 signup/email verify/resend; isolated Auth DB, fresh-session persistence, token/retry/concurrency/transport coverage and auth/session/invitation regressions; no Store/grants/session from signup or verify; real workflow email/browser unverified |
| B2 | COMPLETE backend/fake-delivery acceptance | A07 public RESET request via encrypted durable intent, existing N7 completion/session revocation; token/retry/concurrency/recovery/transport and schema coverage, B1/auth/session/invitation regressions; no Store/grants changes; isolated Auth DB; real workflow email/browser unverified |
| B3 | COMPLETE backend/fake-delivery acceptance | IN01 explicit holder decline; terminal fields/capabilities/events/filter, immutable receipt/current-authority replay; fences/rollback/uncertain commit/races/new-identity acceptance and related auth/schema regressions; no membership/grants/access/email; Auth-only test DB; browser UI unverified |
| B4 | COMPLETE backend/fake-delivery VERIFIED | Linked HTTP/PostgreSQL signup/invitation/grants/multi-Store/decline/reset flows and fresh reads; Product-approved v3/43 catalogue sync, additive Auth0023 CHECK and restart recovery; affected auth/Staff/API/schema regressions; no full-suite claim; browser/real workflow email pending; CHECK overlap reconciled in integration-only0021/0023 plus merge0024 |
| C1 | COMPLETE backend foundation, local commit f85c7cdd | NF01–NF03; durable intent/dispatcher/read receipt, N13 atomic producer, historical DB0025 and25 C1 cases plus affected regressions; no push/merge |
| C2 | COMPLETE backend acceptance, local commit b9fe048 | PR01–PR04 union/grants/audit/receipt; MQ01–MQ03 full-spec pins, N5 queue decisions, current target rights and atomic producers; own DB0026; verification/limits in FULL_TEST_FLOW; no browser/runtime8103 upgrade |
| C3 | COMPLETE backend acceptance, local commit b1c906a | Fifteenth schema inventory_receipts; shared N6 writer/identity, typed effects/completion and current guards; no new route/grant/migration, retained head0026; targeted HTTP/PG verification in [runbook](runbooks/FULL_TEST_FLOW.md#excel-actual-receipt-c3); browser/demo8103 pending |
| C4 | COMPLETE backend acceptance A–F, checkpoint eabab333 | D01/SU01/EX01; I04/M01/M02/N9 extensions; source72/66, no catalogue/migration change; final focused24/related191 passed, commands/limits in FULL_TEST_FLOW; no full-suite/live runtime/browser claim |

These are functional checkpoints, not a claim each is a Git commit or every route
passed a fresh full suite. Current runtime/debt is in [CURRENT_STATE](CURRENT_STATE.md).
Acceptance uses [FULL_TEST_FLOW](runbooks/FULL_TEST_FLOW.md) and relevant tests.

## CURRENT FACT - authorized repair scope

The ADR-013 authority clarification, recipe adapter test doubles, Money boundary
expectations, current API inventories and four application query boundaries have
been repaired without changing product/API behavior. Related tests remain active,
including both capture versions. Verification results are reported in the
conversation; S4.11 UI acceptance and remaining product proposals are unchanged.

## ACCEPTED DECISION — phạm vi tiếp theo được người dùng duyệt

Chốt/push v1.0 trước rồi tách nhánh import: audit sáu workbook chỉ đọc, cải tiến
deterministic mapping proposals và approved Store/source/report/version profile
reuse, phát hiện drift, giữ Owner approval và atomic commit. Provider thật cần
duyệt model/dữ liệu/giới hạn calls/chi phí riêng trước khi gửi dữ liệu. Không sửa
FE, triển khai ngoài import hoặc deploy trong phạm vi này.

CURRENT FACT: v1.0 đã push; nhánh import riêng đã có header/preamble discovery,
controlled aliases/candidates/reasons, full-spec Owner review và scoped drift notice.
Reuse không học từ proposal chưa duyệt. Slice analyze → rules/LLM proposal → Owner
review → reuse đã có bounded candidates/reasons/diagnostics, late-result revision
fence và offline HTTP/DB acceptance. Numeric Excel dates hỗ trợ explicit
EXCEL_SERIAL + workbook epoch + Owner review; không tự chọn date semantics.
Live gateway probe POS demo đã nhận proposal hợp lệ cho SLX và giữ unsupported
columns null; không mở rộng workbook khác hay activate/commit. Whole browser flow
và broader model quality chưa kiểm chứng; live calls theo approved scope. Version
`v1.2` chưa release; Supplier source price/MOQ basis đã có explicit quantity/unit
declarations và exact normalization; recipe source basis đã có explicit
PER_SERVING/WHOLE_BATCH và Owner-reviewed scalar resolution → exact normalization
→ preview/atomic commit → fresh recipe/BOM/recipe readiness. Không defaults/loss kép,
old profiles thiếu basis cần review; output conversion chưa hỗ trợ. FE chưa có
acceptance cho selector/provenance mới;
CURRENT FACT A2: usage/purchase history, declared calendar và observed promotion có
record-only import writer/readback. Calendar/weather forecast features, waste/BOM
reconciliation và arbitrary tabular rules chưa hỗ trợ, không suy từ history presence.

ACCEPTED DECISION: ưu tiên nghiệp vụ cốt lõi theo chuỗi schema → mapping/resolution
→ validation → persistence → consumer → readiness, không theo số cột của sáu workbook.
Giữ Owner approval/profile reuse/exact semantics; không port defaults, permissive
conversions hoặc constraints chỉ lưu nhưng chưa enforce. Chín writer schemas hiện có
được dùng làm nền; thiếu một alias không được xem là thiếu cả persistence/consumer.
CURRENT FACT: Recipe serving/batch và SupplierTerm price/MOQ units đã implement
trong các slices được người dùng duyệt. Supplier source/canonical contracts tách
riêng; whole-pack price/MOQ normalization, Owner/profile review, preview/atomic
commit và immutable evidence nối writer/capture/procurement/readiness hiện có.
Acceptance gồm fresh-session persistence, exact MOQ/budget oracle và retained Run;
không đồng nghĩa toàn browser flow hoặc full regression. Các nghiệp vụ ngoài phạm
vi vẫn cần authorization riêng. Xem
[field inventory/gaps](features/IMPORT_SCHEMA_INVENTORY.md).

CURRENT FACT: lát setup identity/opening/count/completeness đã nối public intake
đến custom Planning trên Store mới không seed business facts. Source opening_stock
dùng writer/receipt identity N6, whole-batch dependencies và typed declaration
bindings; count/stock CAS, quyền và atomic rollback giữ nguyên. R01/capture operational/2
cùng kiểm một current completeness scope, nhận explicit zero trên retained lots.
Source declaration M04 đi trước compatible reuse; signature không chứng minh nguồn.
Recipe cross-sheet cùng version bị RECIPE_SOURCE_SCOPE_AMBIGUOUS; split-part grain
chưa supported. Retirement giữ chặn cả fresh reuse và pending commit.
Default configuration absence vẫn UNKNOWN; whole browser acceptance chưa chạy.
Excel actual receipts vẫn ngoài phạm vi lát setup identity.

ACCEPTED DECISION: người dùng đã mở A1 sales/reimport và stockout riêng;
[ADR-A1](adr/ADR-A1-observed-stockout-demand-policy.md) sở hữu capture/consumer policy.
A2 được duyệt riêng: recorded calendar/promotion/usage/purchase và constraints đã
contract/enforce; không Excel actual receipts, Auth workflow hoặc queue/notification.

HISTORICAL INFORMATION Import126b0f2 A3: backend acceptance of the implemented chain is complete on the owned
Import DB, provider OFF. Coverage extends existing tests only at the missing oracle,
retained correction/count/config, Staff public-grants/reuse and scope/retry boundaries.
No runtime/schema/API/permission change or migration was needed. A1/A2 targeted
evidence is reused explicitly rather than repeating broad groups. See current
[workflow/expected outcomes/recovery](runbooks/FULL_TEST_FLOW.md). No next feature
slice, FE work, commit/push/merge/deploy or ZIP was authorized by that A3 milestone.
The separate integration task authorizes only its local branch merge/commit; no push,
main merge, deployment or next product feature follows it.

## CURRENT FACT C4 — read projections đã triển khai trong local source

- [R05 file/sheet preview aggregates](IMPORT_MAPPING_API_CONTRACT_VI.md#preview-aggregates): retained raw rows and distinct logical actions, overlap semantics and same pinned digest; implemented I04 extension; demo8103 not upgraded.
- [R09 captured effective RunSummary budget](PROCUREMENT_API_CONTRACT_VI.md#history-captured-budget): acceptance limit/currency/availability, financial rights and list snapshot/pagination; implemented local source C4, demo8103 not upgraded.
- R10 recipe split-report identity/completeness and cross-file/sheet assembly are DEFERRED. Source-before-reuse/scope ambiguity guards and valid single-sheet assembly remain implemented; no Product question blocks handoff.

## PROPOSAL / ngoài phạm vi đã duyệt

- TD-BE review (`008_TechDebt.md`, original reference not present in this repo)
  là review/acceptance dependency, không ủy quyền
  implement/deploy endpoint PROPOSED. Ưu tiên Product freeze queue semantics TD004
  trước Staff→Owner→Staff; kế tiếp supplier/location TD007 và settings TD010,
  preview/PDF discovery/Today TD006/008/009. Budget absence/create hiện có C01/N4,
  Ingredient discovery có V01; FE cần current environment/rights/persistence evidence.
  Product chốt assisted/public provisioning và decline TD001/002; AI/What-if/PO
  TD011–013 phải chốt scope/design trước API. Owner cá nhân và ngày môi trường mới
  chưa được xác nhận; không mục nào đủ điều kiện đề nghị đóng từ review tài liệu.

- Dashboard D01/prototype screens and draft PO remain proposals unless separately
  approved; the retired v0 prototype contract is not implementation authority.

- Finish whole-chain browser acceptance against real BE: mapping/Owner approval,
  preview/confirm/commit, readiness, Planning and retained/history/PDF UI; distinguish
  unsupported UI from API defects and assert fresh-session persistence.
- Assess forecast quality using suitable observed sales/correction provenance;
  do not activate trained artifacts merely because training code exists.
- Owner lifecycle/reactivation, one-time approval allowlist/TTL and sensitive audit
  retention need separate reviewed scope. Stored membership alone is not authority.
- Notification C1 is now separately authorized/implemented as described above;
  permission requests, mapping producers and public Store onboarding remain
  separate future slices. B4 alone did not authorize them. Email delivery is
  opt-in and requires the configured HTTPS verification page and private encryption
  key; [Auth feature](features/AUTH_SESSION.md) owns configuration and FE flow.
- AI wording/copilot, deterministic hypothetical what-if, customer selection and
  draft/actual purchase orders are not silently enabled by current Planning/PDF.
- Stock/correction/purchase history extensions, unsupported supplier conditions,
  safety-stock semantics and latency improvements require explicit slices.

CURRENT FACT: isolated worktree test DB setup is supported; effective target, dedicated
roles and reset commands are documented in [FULL_TEST_FLOW](runbooks/FULL_TEST_FLOW.md).
Parallel tests require different owned DBs; each DB remains sequential.

## Acceptance policy ? ACCEPTED DECISION

Select tests for changed behavior and affected callers. Full pytest is for important
integration milestones or broad shared-contract/schema/transaction/infrastructure
changes when targeted coverage is insufficient; state why it is needed. Pure doc
changes use link/content checks, not full pytest. Never treat historical PASS logs
or HTTP2xx as fresh regression/persistence proof. A fresh Session must verify commits.
Public API changes require explicit contract approval and OpenAPI diff.

Update this document when scope/status changes; keep execution logs in the
conversation. No automatic next product slice follows cleanup.
