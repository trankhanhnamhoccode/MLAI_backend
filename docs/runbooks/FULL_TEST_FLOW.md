# Chạy và kiểm thử ShelfCash từ đầu đến cuối

<a id="assistant-l2"></a>
## Decision Assistant L2/L3 — isolated verification

CURRENT FACT source: AS01 explicit synchronous summary create/replay and AS02
retained read, AS03 optional conversational prose/clarification with topic fallback,
no what-if execution/worker/deployment. Source76 operations/69 paths;0030 adds
fenced provider generations after0029 immutable chat receipts;
contract/limits at [Planning §18](../PROCUREMENT_API_CONTRACT_VI.md#decision-assistant)
and [feature](../features/DECISION_ASSISTANT.md). C08 remains structured facts.

Worktree backend-decision-assistant / feat/decision-assistant. Use its dependencies
or the already installed sibling backend Python **without changing that checkout**.
Do not copy a serving .env. Provisioner owns only labeled container
shelfcash-assistant-test-postgres, volume shelfcash-assistant-test-pgdata,
127.0.0.1:5436, database shelfcash_assistant_test and limited
shelfcash_assistant_tester. No other instance is connected/migrated/reset.
Tester has schema creation/DML only on this disposable DB, not superuser/CREATEDB/
CREATEROLE/replication/BYPASSRLS. Private credentials/URL in ignored
runtime/assistant-test/private; never print/copy them to Git. If container/volume/
credentials disagree, reconcile ownership instead of deleting/resetting blindly.
Provisioning does not reset. Tests use the existing guarded reset and cleanup;
dedicated target/current_user checks run before migrations. No .env edits needed.

```powershell
Set-Location D:\hocc_bk\ai\proj\projectMLAI\backend-decision-assistant
$assistantPython = '..\backend\.venv\Scripts\python.exe'
& $assistantPython -B -m scripts.assistant_test_database
& $assistantPython -B -m scripts.assistant_tests tests/integration/test_assistant_summary.py tests/integration/test_assistant_chat.py -q -p no:cacheprovider
& $assistantPython -B -m scripts.assistant_tests tests/integration/test_conversational_chat.py -q -p no:cacheprovider
& $assistantPython -B -m pytest tests/unit/test_decision_evidence.py tests/unit/test_assistant_cold_reads.py tests/unit/test_plan_summary.py tests/unit/test_assistant_chat.py tests/unit/test_assistant_smoke_budget.py tests/api/test_plan_summary_openapi.py tests/live/test_assistant_smoke.py -q -p no:cacheprovider
git diff --check
```

Expected: historical synthetic graphs read on cold cache/fresh Session/process with
engine entrypoints forbidden; corrupt versions/hash/equations reject, no live facts
rewrite history. AS01 completes deterministic response with model OFF; GET/replay
returns retained result without provider. Mock generation calls outside transaction,
concurrent same identity once, current grant/Store denial, late writer denial,
transport-lost ACK reconciliation versus unapplied commit failure, explicit dead
process recovery without repeating provider. Additive migration round-trip/parity
and terminal immutability use this DB only. Fixture provenance and synthetic nature
are recorded in tests/fixtures/decision_assistant, not customer/unseen evidence.

The runner forces model/email/business worker flags OFF and removes provider key
for its child test process; provider-enabled cases inject fake clients. Unit transport
tests mock OpenRouter responses. No train, solver fixture generation, benchmark,
SMTP/live Qwen or browser/full-suite acceptance. Read/create summary for a historical
Run does not depend on readiness/challenger merge or model promotion. API manual flow
after a separately authorized deployment: C03→pin response_version→AS01 with UUID
key + Origin/CSRF→follow Location AS02; never auto-generate from a GET.

L2 has no automatic worker/retry. A running generation owned by alive/unknown process
stays409 on POST replay. Only OS-proven dead owner is failed on explicit replay;
GET remains read-only. Same key retains failure, explicit new key may retry. Keep
private test resources/evidence; do not purge runtime or delete the volume as cleanup.

AS03 manual flow after separately authorized deployment: C03 response_version,
POST `/api/v1/procurement-plans/{plan_id}/assistant/messages` with UUID key,
Origin/CSRF, SummaryRequest fields plus question, ingredient_id:null or retained
UUID, history:[] or bounded user/assistant messages. Clarification keeps original
question and asks for retained ID; explicit new request/key after selection.
Same key/body replays, changed question/history/context409. No GET message endpoint
or implicit computation; C05 links/details retain exact Ingredient scope. CHAT_* is
independent from SUMMARY_*/Import and default OFF; a key alone never enables it.
Model-enabled acceptance pins profile/evidence/selection/prompt/schema/validator,
calls preflight/provider outside DB, repeats authority immediately before completion,
then validates full assertions/coverage and publishes immutable final. Running409;
dead owner only fails on explicit replay, never automatically retries paid work.
Read source/disposition/reason: HTTP200 fallback is not accepted model wording.

### Explicit synthetic live smoke (separate authorization only)

Ordinary pytest skips `tests/live/test_assistant_smoke.py`; offline tests never
enable it. The standalone command below deliberately enables a paid test and
reads this worktree's private .env in memory. Never run against a real Store.
It uses synthetic static fixtures and only the guarded assistant test DB. Before
every completion it checks public endpoint metadata/support/pricing and sets
provider.max_price prompt0.3/completion2.5 USD per million, no fallback/model swap.
Text request≤16000 bytes/max_tokens≤256, conservative prompt bound65536 plus256
output reserves$0.0203008 per attempt;3 reservations≤$0.0609024, under$0.10.
No tools/search/modalities or per-request fees are allowed. Exclusive write-ahead
attempt slots under ignored runtime/assistant-test/live-smoke survive timeouts/
crashes and are never refunded. Do not delete/recycle slots or increase bounds.
Normal tests mock all of this metadata/transport. No key/header dump or real data.

```powershell
& $assistantPython -B -m scripts.assistant_live_smoke --allow-paid-synthetic-max-3-usd-0.10
```

CURRENT FACT: authorization for this smoke was used for2 attempts (first application
route guard fallback, then accepted after targeted fix), total usage.cost$0.0003932.
Do not rerun merely to consume the remaining slot. Safe synthetic raw/final artifacts
remain ignored. GET/replay made0 additional model calls; timeout fallback was offline.
This verifies model presentation routing/schema through AS01/AS02, not free prose,
model chat or a broader L4 evaluation. L3 chat always uses deterministic evidence.

### Conversational AS03 opt-in smoke and offline replay

Ordinary pytest skips all6 conversational live cases. The opt-in CLI alone enables
synthetic AS03 calls on the guarded assistant DB. It reads this worktree's private
.env key only in memory and uses its configured Gemini model; SUMMARY_MODEL is
permitted as test-only selection for this already approved model. Production chat
does not inherit summary model/config: explicit CHAT_LLM_ENABLED/CHAT_MODEL/
CHAT_PROVIDERS/CHAT_* bounds are required. Empty providers is explicit default
OpenRouter routing, no fallback/model substitution. No real Store data is approved.

Public endpoint support/price metadata is checked before each completion. Request
sets temperature0, strict JSON schema, reasoning disabled, require_parameters=true,
max_price prompt0.3/completion2.5 USD per million and per-request0; no tools/search/
attachments. Slots1..8:≤12000 serialized UTF-8 bytes, conservative prompt bound32768,
output768, reserve$0.0117504 each. Slots9..10 MUST use≤6144 bytes, prompt bound8192,
output128, reserve$0.0027776 each. Total worst-case$0.0995584≤$0.10 for10 attempts.
Byte caps include messages/schema and token bounds reserve additional framing.
Exclusive write-ahead slots survive uncertain calls and are never refunded, deleted
or recycled. The current ledger under runtime/assistant-test/conversational-live is
exhausted. Do not bypass it; another batch needs its own explicit authorization.

```powershell
# Paid command, separate explicit authorization only; current batch is exhausted.
& $assistantPython -B -m scripts.conversational_live_smoke --allow-paid-synthetic-max-10-usd-0.10 --case all
# Only when an authorized small slot remains:
& $assistantPython -B -m scripts.conversational_live_smoke --allow-paid-synthetic-max-10-usd-0.10 --case followup --small-output
# Offline: inspect a synthetic AS03 acceptance for the final ellipsis regression.
& $assistantPython -B -m scripts.assistant_tests tests/integration/test_conversational_chat.py::test_elliptical_purchase_form_is_accepted_offline_through_as03 -q -p no:cacheprovider
& $assistantPython -B -m pytest tests/unit/test_conversational_chat.py tests/unit/test_conversational_budget.py tests/live/test_conversational_smoke.py -q -p no:cacheprovider
```

Inspect every raw-N/final-N artifact and prompt/schema/evidence hashes, resolved
model/provider, usage/cost/latency/finish reason, source/disposition/reason and replay
completion count. All attempts stay, including rejected/fallback. The first transport
failure has no recovered raw usage: cost is unknown, not zero, and fully reserved.
This progressive10-attempt batch had0 original source=model finals. Legitimate
paraphrase false rejects were fixed with scoped controls/offline AS03 replay; they
are not relabeled as new live PASS. The fixture has one deduplicated option, so
trade-off smoke tests missing pair evidence, not known pairwise numeric quality.
Fresh final-version live acceptance/broad L4 evaluation remains pending. HTTP200/
pytest PASS alone is not a model quality result; evolving WIP versions are not an
accuracy benchmark. Independent summary live artifacts/results remain unchanged.

<a id="customer-self-service"></a>
### L3.1/L3.2 synthetic conversational verification (shared cap)

CURRENT FACT: original conversational-live remains immutable/exhausted. L3.1
conversational-l31-live and L3.2 conversational-l32-live share the same30-attempt/
USD1.00 cap. Both durable ledgers are read before every paid POST. Their artifacts retain freeze metadata,
full provider request/preflight/facts/prompt/schema, raw responses and AS03 request/
final/replay/failure traces. No session/Authorization headers are exported. Model
is configured Gemini2.5Flash, default OpenRouter routing without fallback; current
metadata support/prices are checked before every POST. Up to30 completions including
regeneration, aggregate USD1.00. Input<=24000 bytes, conservative36864 input tokens,
output<=1200 at capped USD0.3/2.5 per million reserves USD0.0140592/completion,
USD0.421776 for all30. Unknown costs keep their reservation. No ledger reset.

```powershell
# Offline and isolated assistant SQL only; no paid calls by ordinary pytest.
& $assistantPython -B -m pytest tests/unit/test_chat_l31.py tests/unit/test_chat_l31_corpus.py tests/unit/test_chat_l31_budget.py tests/live/test_chat_l31_live.py -q -p no:cacheprovider
& $assistantPython -B -m scripts.assistant_tests tests/integration/test_chat_l31.py tests/integration/test_conversational_chat.py tests/integration/test_assistant_summary.py -q -p no:cacheprovider
# L3.2 offline units and separately guarded assistant HTTP/PostgreSQL:
& $assistantPython -B -m pytest tests/unit/test_chat_l32.py tests/unit/test_chat_l32_lifecycle.py tests/unit/test_chat_l32_budget.py tests/api/test_plan_summary_openapi.py tests/live/test_chat_l32_live.py -q -p no:cacheprovider
& $assistantPython -B -m scripts.assistant_tests tests/integration/test_chat_l31.py tests/integration/test_conversational_chat.py -q -p no:cacheprovider
# Offline freeze after verification; stores source snapshot, never calls DB/model.
& $assistantPython -B -m scripts.conversational_l32_live --freeze-source
# Paid only under the explicit shared authorization; DB prerequisite must be ready.
& $assistantPython -B -m scripts.conversational_l32_live --allow-paid-shared-l31-l32-max-30-usd-1.00 --case all
```

Freeze app/fixture hash before evaluation. If source changes, previous calls become
development evidence and only a fresh fixed-version subset is acceptance; all
attempts/costs remain in the same batch. Stop on systemic failure, fix offline,
run affected tests before another paid call. Review facts, main-answer completeness
and naturalness separately; HTTP200/source=model are not a quality oracle.

CURRENT FACT L3.2: Docker/owned assistant PostgreSQL resumed. Linked HTTP/SQL28
passed. V5 focused12 pass and one newly added V4 replay expectation failure was
corrected, then affected1 pass; V5 unit/API34 pass. Current normal live8 cases skip
without opt-in. Commands/output stay in runtime/assistant-test/l32/index.json.

Paid L3.2 used24 completions:13 development V4 and11 final V5. Together with L3.1
this exhausts30/30. Known USD0.0551248 plus historical unknown reservation0.0281184
has upper0.0832432; full reservations0.421776. No further paid work is authorized
by unused dollars. Do not rerun the paid command or reset/delete/refund slots.
Evaluated V5 source0e3199d2 is PARTIAL:7 accepted/1 regenerated/1 fallback/1
clarification; the final condensed-milk context turn was unexecuted at cap.
V4 had proof/null/polarity slot failures and a comparative false reject. V5 sends
canonical per-fact slots and preserves nulls; sign/role-bound comparatives are
supported, with old V4 replay retained. Two other valid nonnumeric V5 paraphrases
were rejected (attempts22/27); regeneration27->28 also returns an unknown fact ID.
No-winner fallback is factually scoped, not accepted model wording. V6 fixes
those2 bounded variants offline:24 unit and3 actual AS03/PG fake-provider replay
tests pass, including immutable V5 replay. Source2e06f304 (prompt5/
validator6/plan6/renderer7) was live PENDING at checkpoint a29ae1f3; no further
call belongs to this exhausted group. Never relabel these old raw/final results.

Every saved final checks fresh-session persisted response, equal POST replay with0
additional completions and GET405/no generation. Owned test cleanup leaves head0030
and zero users/Runs/chat rows. No development DB, main/runtime8103/FE changes.
The shared runner fsyncs reservations before network, lowers a final request to
one completion when only one slot remains, and skips unexecuted turns at zero.
Timeout/unknown usage retains reservations;429 stops the batch without retry or
provider change. An abandoned lock is fail-closed. The old L3.1 caller is retired.
The isolated live fixture retains authorized Gemini/default OpenRouter routing;
production CHAT_* never inherits summary flags/model. No reviewer model is used.

HISTORICAL INFORMATION L3.1 batch outcome:6 completions; known cost USD0.0065817, unknown
attempts5/6 reserve USD0.0281184, known+unknown upper USD0.0347001 (all6 full
reservations USD0.0843552). Attempts1-5 are development:3 accepted cost/proof/
Ingredient, tradeoff wording false reject and timeout during semantic regeneration.
Freeze2 budget returned HTTP429, so final live acceptance is PENDING; no paid call
after429. Final identity-conflict/proof-assessment fixes are offline-only; new selection
plan/3 and renderer/4 preserve prior implicit plan/2 and renderer/3 obligations. Do not retry
an unknown completion or call this a complete7-case final-version live PASS.
Review runtime/assistant-test/conversational-l31-live/index.json and each attempt/
raw/final; offline-pair-replay.json in runtime/assistant-test/l31 explicitly uses
FAKE provider/new scoped IDs, not a rewritten live result.

Static realistic fixture has captured two milk labels, distinct5/10VND baskets,
50/100 percent Product service and exact per-Product/path deltas. It was authored
once with explicitly fixed baskets/exact serving, not search/solver/forecast;
read/replay tests never execute engines. Wording corpus expectations were authored by the Codex coding assistant, not an
independent human panel or model reviewer. Historical L3.1 has14 cases, zero false
accepts and one legitimate unsupported paraphrase. Current L3.2 finite offline
probe has0 false accepts/0 false rejects; this does not prove general NLP correctness. Context, repair,
regeneration and old pinned receipt compatibility have separate SQL tests. L2
summary remains ordering/tone presentation; no production reviewer is enabled.

### V6 acceptance — separate authorized group

CURRENT FACT `L32-V6-acceptance-1` is separate from the closed30-attempt ledger.
It permits16 completions including regeneration, USD0.30 total conservative
reservation, USD0.0140592 per call at unchanged24000-byte/36864-token conservative
input and1200 output bounds/pricing caps. A durable exclusive/fsynced reservation
precedes each completion. Unknowns retain full reservation, crash lock fails closed,
429 stops the entire group without retries/model/provider change. Old groups are
never reset, refunded or appended. Ordinary pytest skips all8 new live cases.

```powershell
# Offline tests and separately guarded owned-DB fake-provider harness:
& $assistantPython -B -m pytest tests/unit/test_chat_v6_acceptance_budget.py tests/unit/test_chat_l32_budget.py tests/unit/test_chat_l32_final_paraphrases.py tests/live/test_chat_v6_acceptance.py -q -p no:cacheprovider --tb=short
& $assistantPython -B -m scripts.assistant_tests tests/integration/test_chat_v6_acceptance_harness.py -q -p no:cacheprovider --tb=short
& $assistantPython -B -m pytest tests/unit/test_chat_v6_acceptance_findings.py -q -p no:cacheprovider --tb=short
# Executed acceptance commands below are historical, not a request to rerun:
& $assistantPython -B -m scripts.conversational_v6_acceptance --freeze-source
& $assistantPython -B -m scripts.conversational_v6_acceptance --allow-paid-l32-v6-acceptance-1-max-16-usd-0.30
```

Frozen source2e06f304 has finite synthetic live PASS WITH LIMITS:9 ACCEPTED,
1 REGENERATED,1 deterministic clarification; all4 conversation turns executed.
Raw10 omitted simulation numbers with correct slots, so the independent prose
check rejected it; raw11 restored complete scoped facts. No production source or
fixture change. Fresh-session equality, POST replay0 and rights/Store denials were
checked on all11 finals. No message GET exists;405 is a negative method check.
Live8 lifecycle cases pass109.45s; Codex-authored quality review is separate.
Offline13 passed/8 skipped, fake HTTP harness2 passed, observed omission test1 passed.
An initial harness403 expectation for inaccessible Store failed2 tests, corrected
to documented404 before live; logs remain, no authorization contract change.

New group used11/16 calls, cost USD0.0203539, no unknown usage; all reservations
USD0.1546512/0.30,5 slots unused.26263 input/4990 output tokens, resolved
Google/google/gemini-2.5-flash, completion latency2077..5858ms/median3733. No new429
or timeout. Stop after completed matrix rather than consume remaining slots.
Review `runtime/assistant-test/L32-V6-acceptance-1/index.json`, quality-review and
resource-ledger, with original requests/facts/prompt/schema/raw/finals/traces.
Old artifacts remain bytes-identical; missing original HTTP/header bytes are
explicit, never reconstructed. Verbose proof/comparison, opaque option labels,
clarification disposition mismatch and finite-language limits remain. No full
suite, real/unseen-data claim, L4, reviewer model, FE/runtime deployment.

### L4 paired quality evaluation — separate group

CURRENT FACT L3.2 acceptance checkpoint464dec8dc5c04f2f773ce4cedcee26e342151f57.
Default remains V6. Candidate is explicit application composition presentation7,
not a new client parameter/config flag. No endpoint/schema migration/API delta.
Corpus/split/criteria in tests/fixtures/assistant_l4; exposure.json marks eight
evaluation cases exposed to development. Read per-stratum results and raw prose,
not a single accuracy or pytest lifecycle score.20/35g inputs are offline projected
fixtures only; live uses consistent retained20/20g synthetic evidence.

```powershell
& $assistantPython -B -m pytest tests/unit/test_assistant_l4_budget.py tests/live/test_chat_l4_live.py -q -p no:cacheprovider --tb=short
& $assistantPython -B -m pytest tests/unit/test_assistant_l4_presentation.py tests/unit/test_chat_l32_final_paraphrases.py tests/api/test_plan_summary_openapi.py -q -p no:cacheprovider --tb=short
& $assistantPython -B -m scripts.assistant_tests tests/integration/test_assistant_l4.py -q -p no:cacheprovider --tb=short
# Use a NEW ignored output path; evaluator preserves prior results exclusively.
& $assistantPython -B -m scripts.assistant_l4_eval --version 7 --split all --output runtime/assistant-test/l4/reproduction-candidate.json
# Historical paid commands, not instructions to repeat a completed evaluation:
& $assistantPython -B -m scripts.conversational_l4_live --phase baseline --freeze-source
& $assistantPython -B -m scripts.conversational_l4_live --phase baseline --allow-paid-l4-max-24-usd-0.50
& $assistantPython -B -m scripts.conversational_l4_live --phase candidate --freeze-source
& $assistantPython -B -m scripts.conversational_l4_live --phase candidate --allow-paid-l4-max-24-usd-0.50
```

`L4-quality-evaluation-1` has its own write-ahead/fsynced exclusive ledger, cap24
completions including both phases/regeneration/retries, USD0.50 conservative total.
Unchanged byte/token/price bounds reserve USD0.0140592 each (24 reserve0.3374208).
Unknown cost retains reservation;429 stops the whole group, crash lock fails closed.
Private configured Gemini/OpenRouter routing unchanged, no fallback/model judge.
Normal pytest skips six live scenarios. Freeze copies full app/fixture/corpus and
selected harness sources per phase; a baseline freeze cannot be recreated from a
changed candidate worktree. Keep snapshots and use their original source for replay.

Executed baseline6 lifecycle tests passed,9 completions; candidate6 passed,8 calls.
Separate Codex review: baseline7 ACCEPTED/1 REGENERATED/1 clarification, candidate8
ACCEPTED/1 clarification; all4 turns complete, all finals fresh-persisted, same-key
replay0, current rights403/Store isolation404. No message GET exists. Total17/24,
known USD0.0319601, no unknown usage, reservations0.2390064/0.50,7 slots unused.
Old30/30 ledger and L3.2 group11/16 with5 unused slots are unchanged, not pooled.
Stop after completed subset. No call is needed to spend unused slots.

Offline baseline34 pass/1 coverage failure/1 SQL, candidate35 pass/1 SQL; original
metric-null failures remain historical and corrected separately. Authored assertion
probe FA/FR0/0 is separate from the baseline valid live paraphrase false rejection,
also rejected by candidate in offline replay. Proof/comparison/no-winner shorten;
quantity/why do not improve uniformly. Keep V6 default pending broader evidence.
Final affected20 unit/API/3 SQL tests pass, earlier focused40/17; no full suite.
Exact commands/results and phase source/version/usage/latency are under ignored
runtime/assistant-test/l4/index.json and L4-quality-evaluation-1. Review ZIP is scoped,
ignored and deletable without losing originals; no secrets, DB dumps or whole runtime.

### L4.1 focused acceptance — remaining L4 budget only

CURRENT FACT checkpoint L4 `46d15459d40f006152f51a4101a9563cc96eb150`;
derived candidate8 source2d7e2c938baea975c39175fe3b699cb062fddc4a2f99352b62ba776c54246a4f,
prompt7/validator8/selection8/renderer9/resolver5/assertions2. Default6 unchanged.
Explicit `AssistantChat(...,presentation_version=8)` supports controlled trial;
no public request/config field, migration/endpoint or OpenAPI delta.

```powershell
& $assistantPython -B -m pytest tests/unit/test_assistant_l41.py -q -p no:cacheprovider --tb=short
& $assistantPython -B -m scripts.assistant_tests tests/integration/test_assistant_l41.py -q -p no:cacheprovider --tb=short
# Historical executed paid acceptance, not an instruction to consume spare slots:
& $assistantPython -B -m scripts.conversational_l41_live --freeze-source
& $assistantPython -B -m scripts.conversational_l41_live --allow-paid-l41-remaining-l4-max-24-usd-0.50
```

The new opt-in uses ONLY existing L4-quality-evaluation-1 reservations/cap24/USD0.50.
Before this slice17 calls;5 new calls18–22 cost USD0.0099809, aggregate22/24 known
USD0.0419410/full reservations0.3093024, unknown0.2 slots unused. Old L3.2 group
11/16 and its5 unused slots are not consumed/transferred. Unknown reservation,
crash lock and429 whole-group stop remain unchanged. No new budget or blind retry.

Factories create actual validated retained20/35g, failed/partial and mixed-path
Runs through capture/exact pipeline/PlanningRun persistence in guarded assistant
DB only. Different pack inputs cause20/35; no output patch. Mixed uses explicit
custom BASE40, never altering default BASE95. Test engine execution authors Runs,
not chat/replay behavior. No production data/development DB/forecast training.
Protocol/expected oracles freeze in tests/fixtures/assistant_l41/protocol.json.

Final22 unit tests pass; earlier37 unit/API+3 live skips;20/35 four-turn HTTP/DB fake
wording1 pass with old6/7 generation replay, affected mixed/failed HTTP/SQL2 pass.
OpenAPI diff0. Live3 lifecycle scenarios pass125.27s,6 finals:5 ACCEPTED and1
CLARIFICATION, no regeneration/fallback. All four turns execute20→35 with different
scoped refs; every final verifies current rights/Store isolation, fresh response
equality and POST replay0 calls. No message GET resource;405 is a negative probe.
Quality review is Codex-authored against all raw/final prose/facts, not pytest or
independent human/model grading. Saved raw7 offline replay is explicit old6/7
reject/new8 accept; new minimal pairs retain material prose/slot protection.
Simple why factors are support unless explicit path/date or technical detail;
quantity/missing exact-rationale boundary always remain main obligations.

Retain failed helper/fixture logs: offline resolver mapping corrected to5; mixed
default40 was blocked correctly, then valid custom40 used. Evidence/old results
are never relabelled. Read `runtime/assistant-test/l41/index.json`, quality-review,
resource-ledger and new live phase `L4-quality-evaluation-1/l41-candidate8`.
Focused acceptance PASS WITH LIMITS allows explicit trial only. No full suite,
default selection, general entailment/production readiness, FE/deployment or L5.

## CURRENT FACT — setup khách hàng từ số0

Checkout chính: `D:\hocc_bk\ai\proj\projectMLAI\backend`, main, `.venv` riêng.
T03 `POST /api/v1/stores` tạo Store/Owner cho active verified credential-ready
account; source73 operations/66 paths, head0027/72 tables. Không seed account/Store
hoặc bắt khách dùng assisted provisioning/accounts.json.
**FE/browser self-service BLOCKED/PENDING:** source FE hiện chưa có signup,
EMAIL_VERIFY consumer/callback và create Store flow được xác nhận. Backend API/fake
delivery chạy được không chứng minh browser/email workflow thật đã chạy.

### A. Checkout sạch và setup lần đầu

Cần Git, Python3.11+, Docker Desktop Linux engine và PowerShell. `tzdata` được khai
báo để IANA timezone chạy trên Windows sạch. Chỉ clone nếu thư mục chưa tồn tại:

```powershell
Set-Location D:\hocc_bk\ai\proj\projectMLAI
git clone --branch main https://github.com/trankhanhnamhoccode/MLAI_backend.git backend
Set-Location .\backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[dev]'
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
.\.venv\Scripts\python.exe -m scripts.local_runtime secrets
notepad .env
```

Không clone/switch đè WIP. Trong lượt chuẩn hóa này, WIP9 gồm4 tracked và8 untracked
files đã giữ byte-for-byte trên nhánh cũ ở `backend-import-mapping-preserved`, có
verified backup ngoài Git; Import15/Auth0 giữ nguyên. Không merge tài liệu cũ đè main.
Legacy `.env` cũng được backup trước khi chuẩn bị profile mới; runtime/model artifacts
cũ không bị purge. `backend-main-integrated` giữ snapshot cũ để recovery, không dùng
venv/runtime/certificate của nó cho customer profile.

`secrets` chỉ thay placeholders DB/initial Docker password và tạo random32bytes
base64 encryption key trong ignored `.env`, không stdout. Idempotent, giữ password/key
thật đã có; trước thay file có backup ngoài Git. Không rotate key khi còn queued
intents. Không gửi `.env`, App Password, token hoặc cookie vào chat/Git/FE.

| Nhóm `.env` | Ý nghĩa / cách điền |
| --- | --- |
| DATABASE_URL | Limited `shelfcash_local_runtime` → `shelfcash_local`, loopback5433. Password tự nhập cần URL encoding; secrets tự sinh URL hợp lệ. |
| MIGRATION_DATABASE_URL | `shelfcash_local_migrator` → cùng DB; owner schema nhưng không superuser/CREATEDB/CREATEROLE. Chỉ migrate/upgrade CLI dùng. |
| TEST_DATABASE_URL | Dedicated `shelfcash_local_tester` → `shelfcash_local_test`; test/reset chỉ DB này, không customer/demo. |
| POSTGRES_USER/PASSWORD/PORT, LOCAL_POSTGRES_CONTAINER | Initial admin cho volume mới hoặc tên admin/container hiện hữu. Đổi initial password trong file không đổi role cũ. Máy này dùng container `shelfcash-integration-s411-postgres-1`, admin `shelfcash_integration`,5433; không Compose thứ hai tranh port. |
| RUNTIME/UPLOAD/MODEL_ARTIFACT_DIRECTORY | Dưới `runtime/local/app` trong checkout này, không trỏ worktree khác. Stop/upgrade giữ uploads/model artifacts. |
| AUTH_ALLOWED_ORIGINS/AUTH_DEV_COOKIE, LOCAL_PORT | Exact JSON `["https://localhost:5173"]`, false,8103. FE5173 khác BE8103, credentials include; không wildcard. |
| AUTH_SMTP_HOST/PORT/USERNAME/PASSWORD/DELIVERY_SENDER | Provider SMTP được phép; adapter dùng implicit TLS SMTP_SSL, thường465, không STARTTLS587. Sender phải được provider cho phép; username/App Password nhập local. |
| AUTH_DELIVERY_ENCRYPTION_KEY | Private random32bytes/base64 do secrets tạo; khác SMTP App Password, giữ trong suốt đời queued intents. |
| AUTH_FRONTEND_URL | SETUP operator giữ `/credentials/complete` ở HTTPS5173; khách không cần assisted SETUP. |
| AUTH_PASSWORD_RESET_FRONTEND_URL | `https://localhost:5173/credentials/complete`, route FE gọi N7, token trong fragment. |
| AUTH_INVITATION_FRONTEND_URL | `https://localhost:5173/invitations/{invitation_id}`. BE thay UUID vào path, token trong fragment; FE `/invitations/:invitationId` đã xác nhận từ source. Fixed landing formatter cũ vẫn giữ. |
| AUTH_VERIFICATION_FRONTEND_URL | **Chưa xác nhận route/consumer A05 phía FE, để trống.** Cần HTTPS page cùng Origin. Không trỏ EMAIL_VERIFY vào N7/SETUP page để báo email đã chạy. |
| AUTH_EMAIL_DELIVERY_ENABLED | Defaultfalse. Explicittrue sau khi SMTP/key/callback đúng; một email thread cho verification/reset/invitation. Status báo từng capability độc lập; enabled không chứng minh callback available. Không chạy thêm CLI dispatcher. |
| IMPORT/PLANNING/PDF_EXPORT/NOTIFICATION_WORKER_ENABLED | Template customer explicittrue, một process. Application defaults vẫn OFF. Chỉ mở phần cần; kiểm từng thread, không chạy worker trùng. |
| AUTH_OPERATOR_ID/KEY | Operator-only assisted paths, optional/để trống cho khách. Không dùng để tạo Store/invite khách hàng. |
| IMPORT_LLM_SUGGESTIONS_ENABLED, OPENROUTER_* | Defaultfalse/key trống. Adapter hiện hỗ trợ mapping model `qwen/qwen3.5-9b`; timeout30s/deadline60s/sample8/max tokens1800/provider allowlist JSON[]. Key không tự bật provider. OPENROUTER_MODEL tổng quát không chọn model Import, đã bỏ khỏi mẫu mới. Không live call trong setup/tests. |
| LOCAL_SMOKE_RECIPIENT | Optional test recipient user cấu hình rõ; chỉ explicit smtp-smoke gửi một mail, init/start/tests không gửi. |

Gmail là một lựa chọn, không hardcode provider: bật 2-Step Verification, tạo App
Password trong Google Account rồi nhập riêng AUTH_SMTP_PASSWORD; không dùng password
đăng nhập thường. Username/sender có thể cùng Gmail demo nếu được phép. Tài khoản tổ
chức/security policy có thể không cho App Password; xem [Google App Passwords](https://support.google.com/accounts/answer/185833).
Gmail SMTP: smtp.gmail.com/implicit SSL465. Không tắt certificate verification.
Lượt setup này không gửi mail. Khi user tự cấu hình recipient test, có thể explicit:

```powershell
# Optional, chỉ một mail tới LOCAL_SMOKE_RECIPIENT, không tạo account/token:
.\.venv\Scripts\python.exe -m scripts.local_runtime smtp-smoke
```

Sau khi `.env` đúng, từ `backend`:

```powershell
.\.venv\Scripts\python.exe -m scripts.local_runtime docker
.\.venv\Scripts\python.exe -m scripts.local_runtime init-db
.\.venv\Scripts\python.exe -m scripts.local_runtime migrate
.\.venv\Scripts\python.exe -m scripts.local_runtime tls
Import-Certificate -FilePath .\runtime\local\private\localhost.cer -CertStoreLocation Cert:\CurrentUser\Root
.\.venv\Scripts\python.exe -m scripts.local_runtime start
.\.venv\Scripts\python.exe -m scripts.local_runtime status
```

Docker reuse/start đúng configured container; port occupied/container khác thì từ
chối Compose mới. Máy mới dùng compose.local.yaml/named volume riêng. Init chỉ tạo
DB local/test với roles hạn chế, marker/HBA đúng DB; không đổi credentials DB cũ.
DB đã tồn tại thiếu marker bị từ chối. Migrate là first-time-only khi chưa có Alembic,
kiểm current_database/current_user và một head; không reset/stamp/seed. Test schema
do guarded fixture quản lý riêng. Expected DB mới: head0027,72 tables, users/stores0;
server running, bốn business threads true. Email/provider OFF tới explicit opt-in.

TLS/key mới thuộc checkout này; chỉ import public cert một lần trên máy browser.
Probe trust đúng PEM, không skip verification. Start đòi committed source sạch và
PID/birth/run_id đúng, không kill process lạ. Thay effective `.env` hoặc source cần
stop/start. Status báo source SHA/root/configuration_matches, worker observations và
email capabilities; health chỉ liveness. BE launcher không sửa/chạy/dừng FE.

### B. Chạy hằng ngày

```powershell
Set-Location D:\hocc_bk\ai\proj\projectMLAI\backend
.\.venv\Scripts\python.exe -m scripts.local_runtime start
.\.venv\Scripts\python.exe -m scripts.local_runtime status
# Khi không dùng:
.\.venv\Scripts\python.exe -m scripts.local_runtime stop
```

API base `https://localhost:8103`, Origin `https://localhost:5173`. Không init/migrate/
seed/reset mỗi ngày. DB demo cũ `shelfcash_integration_demo`/head0026 được giữ riêng,
không reset để giả “từ số0”; không chạy launcher cũ cùng8103.
Upgrade source có migration mới: chờ jobs queued/running hoàn tất, stop rồi backup:

```powershell
.\.venv\Scripts\python.exe -m scripts.local_runtime stop
.\.venv\Scripts\python.exe -m scripts.local_runtime backup
.\.venv\Scripts\python.exe -m scripts.local_runtime upgrade
.\.venv\Scripts\python.exe -m scripts.local_runtime start
```

Backup custom/full payload/SHA256, private config và counts nằm ngoài Git. Upgrade
đòi đúng marker/identity, process DEAD, không pending/running work, backup khớp state;
sau upgrade kiểm counts bảng cũ. Failure giữ archive/evidence, không automatic
downgrade/stamp/reset hoặc restore đè DB đang dùng.

### C.14 luồng khách hàng theo Nam/Nguyên

Persona tự chọn email thuộc quyền mình. JSON đầy đủ do [OpenAPI](../handoff/openapi.json)
và DTO sở hữu. Paths dưới đây đầy đủ; UUID/versions từ responses hiện hành. Browser
dùng credentials include; protected mutations có Origin, current X-CSRF-Token,
Idempotency-Key và If-Match nếu contract yêu cầu. Timeout giữ key/body; intent mới
dùng key mới. Không log/persist token/cookie/password trong console/localStorage.

| Bước / người / điều kiện | API theo thứ tự | Expected, negative và recovery |
| --- | --- | --- |
| 1 Nam mới; SMTP/key/verification callback available | POST `/api/v1/auth/register`; POST `/api/v1/auth/email-verifications/complete`; POST `/api/v1/auth/login`; GET `/api/v1/auth/me`; GET `/api/v1/stores` | Signup202 không session/Store/grants. EMAIL_VERIFY token + password hoàn tất A05, rồi login, stores[]. Expired: POST `/api/v1/auth/email-verifications/request`, mail mới; không N7.503 kiểm capability,429 chờ. **Signup/verify UI/callback FE còn thiếu.** |
| 2 Nam active/verified/credential-ready/login | POST `/api/v1/stores`; GET `/api/v1/stores/{store_id}`; POST `/api/v1/auth/logout`; login lại và GET `/api/v1/stores` |201 StoreSummary/Location, Owner còn sau login. Unverified không login/create, foreign UUID404; owner_user_id/role/grants422. Same key/body201 cùngID, khác body409, revoke chặn replay. Multi-Store explicit được phép. **FE cần màn hình/API T03.** |
| 3 Nguyên tự signup/verify như bước1; Nam Owner chọn grants | POST `/api/v1/stores/{store_id}/staff-invitations`; GET `/api/v1/stores/{store_id}/staff-invitations`; GET `/api/v1/staff-invitations/{invitation_id}` với X-Invitation-Token; POST `/api/v1/staff-invitations/{invitation_id}/accept`; GET Store context; GET `/api/v1/stores/{store_id}/memberships`; PUT `/api/v1/stores/{store_id}/memberships/{membership_id}/permissions` | Mail qua owned durable worker; signup không accept invitation. Accept201 exact offered grants, allow/403 denial, revoke hiệu lực ngay. Expired/revoked: Owner POST `/api/v1/stores/{store_id}/staff-invitations/{invitation_id}/actions` để reissue;409/412 refetch. Không SQL cấp quyền. |
| 4 Nguyên verified, invitation khác pending | GET `/api/v1/staff-invitations/{invitation_id}`; POST `/api/v1/staff-invitations/{invitation_id}/decline` | Terminal, không membership mới; accept:false không thay decline. Expired → Owner reissue/new identity. Giữ memberships Store khác; decline UI cần FE xác nhận. |
| 5 Nam/Nguyên verified, có sessions | POST `/api/v1/auth/password-reset/request`; POST `/api/v1/auth/credentials/complete`; POST `/api/v1/auth/login` | Request202 không logout; completion RESET thu hồi mọi session, giữ memberships/grants. Expired request token mới; không reset SQL/operator. Credentials page N7 đã có, forgot UI cần FE consumer. |
| 6 Nam Owner, Store trống; explicit files/import/domain rights | POST `/api/v1/stores/{store_id}/imports`; POST `/api/v1/imports/{import_id}/files`; POST `/api/v1/imports/{import_id}/analyze`; GET `/api/v1/jobs/{job_id}`; GET `/api/v1/imports/{import_id}/mapping-summary`; GET `/api/v1/imports/{import_id}/mappings`; PATCH `/api/v1/imports/{import_id}/mappings/{mapping_id}`; POST `/api/v1/stores/{store_id}/mapping-profiles/{profile_id}/decisions`; POST `/api/v1/imports/{import_id}/process`; GET `/api/v1/imports/{import_id}`; GET `/api/v1/imports/{import_id}/completion`; GET `/api/v1/stores/{store_id}/products` | Upload/analyze không canonical writes. Resolve source/bindings/create identities explicit, Owner approve exact spec; preview → confirm_review → commit theo DTO là các intent riêng. Fresh readback/I06, không chỉ202. Timeout poll/replay cùng key, stale409/412 refetch/preview mới. Browser continuation pending. |
| 7 Nam/Staff đủ import/mapping/domain grants; active approved profile | POST `/api/v1/stores/{store_id}/imports`; POST `/api/v1/imports/{import_id}/analyze`; GET `/api/v1/imports/{import_id}/mapping-summary`; GET `/api/v1/imports/{import_id}/mappings`; PATCH `/api/v1/imports/{import_id}/mappings/{mapping_id}`; POST `/api/v1/imports/{import_id}/process`; GET `/api/v1/imports/{import_id}/sheets/{sheet_id}/field-options` | Source/header/spec khớp reuse; entity mới explicit create/bind; drift/ambiguity cần review/Owner version mới. Retired không fresh reuse. Không suy source từ filename;409/412 reload pins. |
| 8 Người có sales.record/read và import grants; Product/day/report explicit | POST `/api/v1/stores/{store_id}/imports`; POST `/api/v1/imports/{import_id}/process`; GET `/api/v1/imports/{import_id}/completion`; GET `/api/v1/stores/{store_id}/readiness` | Replace/merge contributions theo declared scope; stockout true/false/unknown khác nhau. Absent row không delete, retry không cộng lại. Source/version đổi → new preview. Synthetic forecast correctness không là accuracy thật. |
| 9 Nam review recipe/supplier/opening/count có nguồn | POST `/api/v1/stores/{store_id}/imports`; POST `/api/v1/imports/{import_id}/process`; GET `/api/v1/stores/{store_id}/suppliers`; GET `/api/v1/stores/{store_id}/inventory`; GET `/api/v1/stores/{store_id}/inventory/{ingredient_id}`; PUT `/api/v1/stores/{store_id}/inventory/{ingredient_id}/threshold`; GET `/api/v1/stores/{store_id}/products/{product_id}/recipe-schedule` | Recipe basis/unit/yield/loss, pack/price/MOQ/lead/effective facts explicit. Opening khác count lot existing. Missing không0/default, upload date không received date. Conflict/stale refresh evidence; split-report deferred. |
| 10 Có inventory.receive/read và sensitive rights khi có cost/supplier | Excel inventory_receipts qua workflow bước6; POST `/api/v1/stores/{store_id}/inventory/receipts`; GET `/api/v1/stores/{store_id}/inventory/{ingredient_id}/movements` | Shared identity Excel↔N6 hai chiều, effects/atomic commit/fresh stock. Same identity/payload reuse, khác conflict; lost ACK cùng key. Purchase history/planned purchases không stock; không tự completeness. |
| 11 Nguyên active Staff; Nam Owner | POST/GET `/api/v1/stores/{store_id}/permission-requests`; GET `/api/v1/stores/{store_id}/permission-requests/{request_id}`; POST `/api/v1/stores/{store_id}/permission-requests/{request_id}/actions`; GET `/api/v1/notifications`; GET `/api/v1/notifications/unread-count`; PATCH `/api/v1/notifications/{notification_id}` | Approve subset union giữ unrelated grants; request không grant. Dispatcher → inbox/count/read; read không quyết định task. Revoke/mất membership chặn target, replay không regrant.409/412 refetch grants/catalogue. FE cần PR/inbox consumer. |
| 12 Nguyên có mapping.propose/batch reads; Nam Owner | POST `/api/v1/imports/{import_id}/mapping-submissions`; GET `/api/v1/stores/{store_id}/mapping-submissions`; GET `/api/v1/stores/{store_id}/mapping-submissions/{submission_id}`; POST `/api/v1/stores/{store_id}/mapping-profiles/{profile_id}/decisions`; notifications bước11 | Submit pins → request_changes/reject/approve → notification; profile approved chưa nhập data. Preview/confirm/commit riêng. Drift/retired/revoke chặn; stale explicit resubmit ID mới, không sửa pinned history. |
| 13 Nam/Staff đủ planning/result/finance; facts/completeness explicit | GET `/api/v1/stores/{store_id}/readiness`; GET `/api/v1/stores/{store_id}/planning-context`; POST `/api/v1/stores/{store_id}/planning-requirements`; PUT `/api/v1/stores/{store_id}/planning-budget`; POST `/api/v1/stores/{store_id}/procurement-plans`; GET `/api/v1/procurement-plans/{plan_id}`; GET `/api/v1/stores/{store_id}/procurement-plans` | Khách tự khai requirements/budget; blocked R01 giải thích missing, không seed.202 accepted, poll terminal; no winner khác failed. Creator/day theo Store, captured budget giữ nguyên. Timeout same key; intent mới Run/key mới, không sửa retained result. |
| 14 Có retained Run/result và export/finance rights | GET `/api/v1/procurement-plans/{plan_id}/ingredients`; GET `/api/v1/procurement-plans/{plan_id}/ingredients/{ingredient_id}`; GET `/api/v1/procurement-plans/{plan_id}/explanation`; POST/GET `/api/v1/procurement-plans/{plan_id}/exports`; GET `/api/v1/jobs/{job_id}`; GET `/api/v1/procurement-plans/{plan_id}/exports/{export_id}`; GET `/api/v1/stores/{store_id}/today`; GET `/api/v1/imports/{import_id}`; GET `/api/v1/imports/{import_id}/mapping-summary`; GET `/api/v1/imports/{import_id}/mappings` | PDF job → EX01/N11 current rights/hash; GET không render/jobs. Missing/corrupt explicit export mới nếu allowed. Today forbidden/unavailable khác0; counters/provenance cùngpins, không cộng overlap. Snapshot409 page1,403 grants, queued kiểm workers. Today FE hiện placeholder; browser pending. |

T03 body minh họa (metadata user chọn, không business defaults):

```json
{"name":"Quán test của Nam","timezone":"Asia/Ho_Chi_Minh","currency":"VND"}
```

Ví dụ HTTP PowerShell sau khi account đã verify và trust public cert, password không
để thành literal trong shell history; các bước khác dùng Postman/cookie jar tương tự:

```powershell
$api = 'https://localhost:8103'
$origin = 'https://localhost:5173'
$email = Read-Host 'Email account đã verify'
$privatePassword = Read-Host 'Password' -AsSecureString
$body = @{email=$email;password=[Net.NetworkCredential]::new('', $privatePassword).Password;remember_me=$false} | ConvertTo-Json
$login = Invoke-RestMethod -Method Post -Uri "$api/api/v1/auth/login" -Headers @{Origin=$origin} -ContentType application/json -Body $body -SessionVariable customer
$body = $null
$storeKey = [guid]::NewGuid().ToString()
$headers = @{Origin=$origin;'X-CSRF-Token'=$login.data.session.csrf_token;'Idempotency-Key'=$storeKey}
$storeBody = @{name='Quán test của Nam';timezone='Asia/Ho_Chi_Minh';currency='VND'} | ConvertTo-Json
$created = Invoke-RestMethod -Method Post -Uri "$api/api/v1/stores" -Headers $headers -WebSession $customer -ContentType application/json -Body $storeBody
Invoke-RestMethod -Uri "$api/api/v1/stores/$($created.data.store_id)" -WebSession $customer
```

T03 timeout: retry cùng storeKey/storeBody, không sinh quán thứ hai.
Workflow meaning và permissions: [Authorization](../AUTHORIZATION_CONTRACT_VI.md#self-service-stores),
[Import](../IMPORT_MAPPING_API_CONTRACT_VI.md), [Planning](../PROCUREMENT_API_CONTRACT_VI.md).
Inputs tối thiểu, chỉ import khi user chọn synthetic test:
[products.csv](../../tests/fixtures/local_self_service/products.csv),
[ingredients.csv](../../tests/fixtures/local_self_service/ingredients.csv).
Chỉ master metadata, chưa recipe/sales/stock/supplier/budget/completeness, không READY.
Owner review source keys rồi create/bind, không tự ghép UUID. Inputs richer/oracles
nằm trong tests/integration/test_import_actual_receipts.py, test_import_planning_a3.py,
test_import_recipe_basis.py và test_import_supplier_basis.py; không upload ngầm hoặc
coi synthetic là facts kinh doanh thật.

### D. Troubleshooting/recovery và tests

| Dấu hiệu | Recovery |
| --- | --- |
| Port5433 occupied | Chọn đúng existing container/admin; không Compose thứ hai, không đổi role/password cũ. |
| DB authentication failed | Kiểm runtime/migrator/test URLs khác initial Docker credentials qua editor local; không reset volume hoặc overwrite mật khẩu thật bằng secrets. |
| Init từ chối marker/role | Giữ evidence, kiểm ownership/partial setup; không đổi marker/stamp/credentials để vượt guard. |
| Source/config mismatch | Commit source hợp lệ; stop/start để nạp profile mới, không kill process lạ8103. |
| TLS error | Trust đúng cert riêng, kiểm SAN/expiry. Renew cần backup/stop/thay/trust có kiểm soát, không skip verify. |
| Register/resend/forgot503 | Kiểm flag và từng email_capabilities. Verification callback pending FE; SMTP smoke pass không thay consumer/callback. |
| Mail chưa nhận/token expired | Kiểm sender/App Password/private logs/spam; resend/reissue đúng workflow. Unknown invitation SMTP outcome không auto resend proof cũ; không hai dispatchers. |
|401/403/404 | Login/current CSRF/Origin, current membership/grants đúng Store. UUID không cấp quyền, không SQL tạo Owner/Staff. |
|409/412/428 | Refetch resource/version/catalogue và review lại;428 thêm preconditions. Lost ACK cùng key/body, không key mới để né conflict. |
| Queued/readiness blocked | Kiểm từng worker/DB dependency; poll job, nhập facts/config/completeness có nguồn, không seed/fakezero. |

Tests dùng dedicated TEST_DATABASE_URL; fixture chỉ reset/migrate shelfcash_local_test.
Không dùng DB local/demo/development để chạy reset. Chạy test/reset tuần tự, provider/
SMTP fake cho automated tests. Probe `python -m scripts.dev status --test-database`
không seed. API/fake-delivery acceptance khác browser/real email E2E; exact verification
commands/results được cập nhật trong phần hiện hành trước bàn giao.

#### Verification self-service trên máy này

Final focused83 passed/32.84s, gồm public signup/fake delivery/T03/current Owner,
multi-Store/isolation, rollback/concurrency/lost ACK/revoke, explicit CSV import,
Owner-created Store → self-registered Staff invitation/background delivery/accept,
body/header/Origin guards, local tooling và application query boundaries:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/integration/test_store_creation.py tests/api/test_store_creation_openapi.py tests/api/test_self_service_auth.py tests/unit/test_local_runtime.py tests/unit/test_invitation_email.py tests/unit/test_application_contracts.py -q --tb=short --show-capture=no
```

Schema/migration/tooling milestone210 passed/307.72s trước khi thêm boundary test
T03 cuối (đã pass trong focused83; chạy lại file selection hiện hành có thêm case).
Có migration/table mới và test
DB guard mới nên mở rộng các schema round-trip/metadata/head/caller checks; không
chạy full feature suite. Exact selection (PowerShell, từ backend):

```powershell
$schemaTests = Get-ChildItem tests/integration/test_*_schema.py -File | ForEach-Object { $_.FullName }
$boundaryTests = @(
 'tests/integration/test_database_bootstrap.py', 'tests/integration/test_integrated_migrations.py',
 'tests/integration/test_verification_commands.py', 'tests/integration/test_forecast_decision_persistence.py',
 'tests/integration/test_store_creation.py', 'tests/integration/test_notifications.py::test_additive_upgrade_metadata_and_retention_guard',
 'tests/api/test_auth_openapi.py', 'tests/api/test_store_creation_openapi.py', 'tests/api/test_discovery_openapi.py',
 'tests/api/test_collaboration_openapi.py', 'tests/api/test_notification_openapi.py', 'tests/api/test_import_openapi.py', 'tests/api/test_stock_writes_openapi.py',
 'tests/unit/test_sales_stockout_migration.py', 'tests/unit/test_integration_contract_snapshot.py',
 'tests/unit/test_integrated_demo.py', 'tests/unit/test_local_runtime.py'
)
& .\.venv\Scripts\python.exe -m pytest @schemaTests @boundaryTests -q --tb=short --show-capture=no
```

Auth/Invitation affected gate trước các linked/boundary cases cuối:149 passed/1 test failure,
336.91s. Same selector bên dưới hiện có thêm cases; không hứa count lịch sử khi
chạy source mới. Failure kỳ vọng RuntimeError nhưng PostgreSQL raise DBAPIError khi
retention chặn downgrade đúng; sửa exception assertion, không bỏ guard. Affected
retention/import cases2 pass/12.61s, sau đó đã có trong final focused/schema gates.

```powershell
.\.venv\Scripts\python.exe -m pytest tests/integration/test_store_creation.py tests/integration/test_email_verification.py tests/integration/test_password_reset.py tests/integration/test_staff_public.py tests/integration/test_invitation_decline.py tests/api/test_store_creation_openapi.py tests/unit/test_email_verification_transport.py tests/unit/test_invitation_email.py -q --tb=short --show-capture=no
```

Các gate overlap, không cộng thành unique/full-suite count. RED ban đầu T03 trả405
trước implementation. Tooling fixture ENVIRONMENT và stale Auth OpenAPI inventory
Today/Supplier được sửa; affected14 pass rồi final83/210 pass. Private config digest
không in ra status; sau display refinement, local tooling12 pass/0.76s.
Own venv dependency installation và pip check PASS. CLI secrets/init-db/migrate/tls,
custom backup/full payload/SHA256 và guarded no-op upgrade đã chạy trên DB local mới;
test status xác nhận limited tester/0027/72 tables/0 application rows sau cleanup.
Old demo quiescence/backup/stop đã kiểm riêng, không reset/migrate DB đó. No SMTP/model
call hoặc browser E2E trong các checks này; runtime source/SHA do status khi start báo.

Runtime customer VERIFIED trên committed source checkpoint
`86fcc6795957baea9b2d7f343a8079bed44c1559`: own backend/.venv, TLS verified bằng own
PEM, API73/66 khớp handoff artifact, exact Origin/CORS và unauthenticated T03 denial.
Direct SQL kiểm đúng local DB/runtime role, migrator owner, no super/CREATEDB/CREATEROLE/
role inheritance/schema CREATE;72 tables,0 application rows trước/sau HTTP probes,
không accounts/Stores seed. Bốn business threads true, email false, no hidden jobs/
intents; source/profile digest khớp, không traceback runtime. Own paths dưới checkout.
Demo cũ stopped; schema/counts mọi bảng khớp backup sau stop, giữ head0026 và dữ liệu.
Source SHA cuối của process do status báo sau khi đồng bộ commit docs; không hardcode
SHA commit chứa chính dòng tài liệu này. Chỉ backend/runtime VERIFIED; EMAIL_VERIFY
callback/consumer và Store-create UI phía FE còn thiếu, email thật/browser E2E PENDING.

<a id="linked-acceptance-c5"></a>
## HISTORICAL INFORMATION — C5 backend/runtime VERIFIED; browser PENDING

C4 checkpoint `eabab333ee8738a0fa758b91f95a106d662edac6`, gồm C1–C4 trên main
base6f80735. Fetch origin không có main delta/conflict; một head0026, source72/66.
C5 tổng thể chưa COMPLETE: browser E2E PENDING và cần đội FE/người dùng.
Không SMTP/OpenRouter, không recipe split-report/AI/what-if hoặc policy mới.
Runtime đã nâng cấp theo [luồng HTTPS8103](#integrated-demo-runtime); migration phải có
backup verified và source committed sạch. Không chạy trực tiếp worktree tests/WIP.

| Nhóm | Backend coverage và evidence kế thừa/bổ sung |
| --- | --- |
| A | PR subset union giữ menu.read; current grants, dispatcher → inbox/count/read, fresh receipts; replay sau revoke không regrant, inactive membership ẩn inbox/chặn target. |
| B | Staff submit/current-sensitive reads → Owner queue/detail/N5 → notification/read → review/preview/commit riêng. C2 drift/retirement/revoke/fault/dispatch cases giữ nguyên; không coi notification là task decision. |
| C | Excel/formN6 dedupe hai chiều, lost ACK, atomic writer, fresh stock/capture; bổ sung Today inventory/readiness giữ unknown và blocked actions khi thiếu facts. Purchase/planned history vẫn history-only, không stock. |
| D | C4 pinned counters/raw/effects/aggregates, multi-source overlap/AND scopes, revision/digest và stale cursor; không cộng file totals thành batch total. |
| E | Real Planning/PDF worker, retained evidence/labels và N9 local creator/date/captured budget → EX01 → N11 bytes/hash; live cap đổi không sửa history; revoke chặn discovery/download. GET không tạo job/render. |
| F | Today section current guards/partial unavailable/snapshot; no GET solver/canonical writes, no fake zero/KPI. |

### Commands và kết quả C5

Chạy từ `backend-notifications-foundation` với DB `shelfcash_notifications_test` /
`shelfcash_notifications_tester`, loopback5433. Không dùng profile demo cho pytest.
Tests/reset DB chạy tuần tự; synthetic fixtures và fake delivery. Interpreter dùng
venv hiện có, modules phải resolve theo worktree hiện hành (`python -m ...`).

```powershell
Set-Location D:\hocc_bk\ai\proj\projectMLAI\backend-notifications-foundation
$c5Python = '..\backend-integrate-import-auth\.venv\Scripts\python.exe'
& $c5Python -m pytest tests/integration/test_permission_requests.py::test_union_replay_after_revoke_and_atomic_notifications tests/integration/test_import_actual_receipts.py::test_excel_actual_receipt_shared_n6_identity_and_separate_commit tests/integration/test_planning_exports.py::test_real_pdf_winner_job_replay_download_and_font_proof -q --tb=short --show-capture=no
& $c5Python -m pytest tests/integration/test_mapping_submissions.py tests/integration/test_import_actual_receipts.py::test_form_then_excel_reuses_receipt_without_new_inventory tests/integration/test_import_actual_receipts.py::test_receipt_uncertain_commit_reconciles_shared_ledger_without_repeat tests/integration/test_import_actual_receipts.py::test_receipt_updates_fresh_capture_and_keeps_retained_planning_run tests/integration/test_import_projections_c4.py tests/integration/test_discovery_c4.py tests/integration/test_planning_export_durability.py::test_staff_current_read_export_replay_worker_and_download_rights -q --tb=short --show-capture=no
& $c5Python -m pytest tests/integration/test_integrated_migrations.py::test_demo_upgrade_0024_to_current_preserves_accounts_and_grants tests/integration/test_integrated_migrations.py::test_upgrade_from_each_branch_head_preserves_v3_grants_and_schema_parity tests/unit/test_integrated_demo.py tests/unit/test_integration_contract_snapshot.py tests/api/test_discovery_openapi.py -q --tb=short --show-capture=no
```

Kết quả lần lượt3 passed/28.82s,20 passed/105.49s,25 passed/9.30s;
48 cases trong ba selections không overlap. Unit tooling19 cũng chạy riêng trước
và sau refinement backup payload check (0.64s/0.73s); không cộng lại thành coverage mới.
Đây là gate tổng hợp có chọn lọc cho linked/infrastructure milestone, không full suite.
C4 focused24/affected191, C3/C2/C1 evidence phía dưới được tái dùng, không claim rerun.
Fresh owned test probe sau cleanup: role hạn chế, head0026,71 tables,0 application rows,
6 flags OFF. Không truy cập/reset các DB test nhánh khác.

Fail→fix setup: PostgreSQL container cũ đang stopped → start lại đúng container;
không đổi credentials/volume. Offline artifact helper lúc đầu resolve editable package
của worktree cũ → pin current source root trước imports; generation cuối block DB/socket,
validate DTO examples và đo đúng72/66. Staged secret scan ban đầu match callback URL
vì tên setting chứa PASSWORD_RESET → phân biệt public callback URL với private values;
không bỏ kiểm password/token/key thật. Không có behavioral test failure trong C5.


Runtime verification C5 trên DB demo thật: custom backup đã verify TOC/full payload/
SHA256 trước0024→0026; tất cả counts bảng cũ giữ nguyên,71 tables sau upgrade.
API probes pass TLS, OpenAPI72/66, exact Origin/CORS/cookie/CSRF/login/me/isolation,
Today/inbox và four worker observations; SQL probe kiểm từng queue/DB trực tiếp,
không dùng health để kết luận dependency ready. Source/root/SHA do status cung cấp.
Giữ3 holders/2 Stores/menu.read grant và2 terminal import jobs đã tồn tại;
products/ingredients/planning còn trống tại thời điểm probe, không seed completeness.
Lần verify đầu dừng vì guard cũ yêu cầu zero historical jobs; sửa CLI probe kiểm
queued/running và bảo toàn counts/current grants, verify thực tế sau sửa PASS.
Không xóa jobs, reset DB hoặc đổi policy để làm xanh. Credentials/cert bytes
copy sang main giữ nguyên; runtime private storage thuộc serving worktree bền vững.

Runtime commands đã thực hiện từ committed main:

```powershell
$demoPython = '..\backend-integrate-import-auth\.venv\Scripts\python.exe'
& $demoPython -m scripts.integrated_demo backup-upgrade
& $demoPython -m scripts.integrated_demo stop
& $demoPython -m scripts.integrated_demo migrate
& $demoPython -m scripts.integrated_demo start
& $demoPython -m scripts.integrated_demo_accounts verify
& $demoPython -m scripts.integrated_demo status
```

Profile transfer là thao tác một lần, không chạy init/provision lại. Chỉ source/root
đổi và notification flag opt-in; old DB credentials, TLS, callbacks giữ nguyên.
Backup/private accounts không thuộc artifacts FE/Git. Browser checklist vẫn PENDING;
real email workflow, model quality, production SLA và nonempty demo job execution
chưa được kiểm trong lượt này. Tests chạy real workers trên synthetic test DB là
backend evidence, không thay thế browser hoặc job receipts trên demo thật.

### Browser checklist — PENDING, không phải backend API acceptance

Dùng persona **Nam = Owner**, **Nguyên = Staff** tương ứng holders private; tên persona
không tự đổi stored identity hoặc tạo account mới. Không copy credentials vào docs/FE.

| Luồng browser cần FE/người dùng kiểm | Expected outcome / recovery |
| --- | --- |
| Login HTTPS, đổi Store, reload | Secure cookie/credentials include; Store khác404,401 login lại. Certificate phải trust; không tắt verification. |
| Nguyên xin quyền, Nam approve subset | Refresh T02, unrelated grants còn; inbox/count/read cập nhật sau dispatcher.409/412 refetch/review, không replay bằng key mới để né CAS. |
| Nguyên submit mapping, Nam request changes/approve | Mở current MQ03 từ notification; approval không báo import complete. Stale pins cần review/submit/preview mới, retired/revoked không tiếp tục bằng snapshot cũ. |
| Excel actual → preview/commit → Kho/Today | Kiểm số lượng và receipt identity explicit; lost ACK retry cùng key; history/planned purchases không stock. Store thiếu config vẫn cần setup, không seed để xanh. |
| Counters/raw cells/file-sheet filters | Dùng cùng revision/digest, hiểu unavailable/truncated và overlap; snapshot409 reload page1, không cộng totals giữa scope giao nhau. |
| Planning → History → export/discovery/download | Creator/day theo Store zone, captured budget giữ nguyên; EX01 không tạo job. Missing/corrupt bytes cần explicit export mới nếu allowed;403 kiểm current grants. |
| Today partial/blocked và logout | Forbidden/unavailable khác zero; không trigger solver từ GET; job queued kiểm worker status, không khởi động worker trùng. |

Browser vẫn PENDING; không dùng intercepted responses hoặc TestClient để gọi là browser pass.

<a id="read-discovery-c4"></a>
## HISTORICAL INFORMATION — C4 Today và read discovery checkpoint

C4 COMPLETE backend acceptance theo các nhóm A–F dưới đây; giữ source WIP để review.
C3 đã commit local `b1c906a0ea65a3b20a46d161166668d26701f0a9` với message
`feat(import): support Excel actual inventory receipts`; không rerun gate105 chỉ
để commit. C4 giữ WIP để review, không commit/push/merge hoặc nâng cấp demo8103.
Source đo được72 operations/66 paths, giữ69 C3 locators; thêm D01/SU01/EX01.
Extensions trên I04/M01/M02/N9; catalogue permissions-v3/43 và head0026/71 tables
không đổi, không migration C4. Browser E2E và live runtime C4 chưa chạy.

### Chạy checks trong worktree này

Setup DB/private config dùng [phần collaboration](#notifications-c1), không Compose
thứ hai. Chỉ notifications test DB/limited role trên5433, tests/reset tuần tự;
không trỏ sang demo, development hoặc DB test nhánh khác. Tests có fixtures explicit,
không seed Store/defaults để che readiness. Provider/email/background flags OFF;
workers trong tests chỉ chạy bounded run_one trên DB riêng, không gửi SMTP/model.

```powershell
Set-Location D:\hocc_bk\ai\proj\projectMLAI\backend-notifications-foundation
$collaborationPython = (Resolve-Path ..\backend-integrate-import-auth\.venv\Scripts\python.exe).Path
& $collaborationPython -m scripts.dev status --test-database

# C4 linked acceptance + current grants/C1–C3 integration boundaries:
& $collaborationPython -m pytest tests/integration/test_discovery_c4.py tests/integration/test_import_projections_c4.py tests/integration/test_planning_discovery_c4.py tests/integration/test_import_actual_receipts.py::test_receipt_mq_owner_approval_keeps_inventory_empty_until_commit tests/integration/test_permission_requests.py::test_union_replay_after_revoke_and_atomic_notifications tests/integration/test_planning_export_durability.py::test_staff_current_read_export_replay_worker_and_download_rights tests/unit/test_read_projections_c4.py tests/api/test_discovery_openapi.py -q --tb=short --show-capture=no --junitxml=runtime/notifications/c4-acceptance.xml -o junit_logging=system-out

# Final C4 gate sau fixture fixes và typed blocked/opening-effect refinements:24 passed.
& $collaborationPython -m pytest tests/integration/test_discovery_c4.py tests/integration/test_import_projections_c4.py tests/integration/test_planning_discovery_c4.py tests/unit/test_read_projections_c4.py tests/api/test_discovery_openapi.py -q --tb=short --show-capture=no --junitxml=runtime/notifications/c4-final-focused.xml -o junit_logging=system-out

# Affected old readers/writers/rights/DTOs; source C4 changes justify these regressions:
& $collaborationPython -m pytest tests/integration/test_notifications.py tests/integration/test_permission_requests.py tests/integration/test_mapping_submissions.py tests/integration/test_collaboration_boundaries.py tests/integration/test_import_actual_receipts.py tests/integration/test_import_setup_stock.py tests/integration/test_stock_writes.py tests/integration/test_retained_history.py tests/integration/test_planning_exports.py tests/integration/test_readiness_context.py tests/unit/test_application_contracts.py tests/unit/test_import_preview.py tests/unit/test_import_actual_receipts.py tests/unit/test_read_projections_c4.py tests/unit/test_integration_contract_snapshot.py tests/api/test_discovery_openapi.py tests/api/test_collaboration_openapi.py tests/api/test_notification_openapi.py tests/api/test_import_openapi.py tests/api/test_stock_writes_openapi.py -q --tb=short --show-capture=no --junitxml=runtime/notifications/c4-regressions.xml

& $collaborationPython -m scripts.integration_contract_snapshot
git diff --check
```

Expected database/current_user: shelfcash_notifications_test /
shelfcash_notifications_tester, at_head=true/0026,71 tables. Không status/reset
probe trong khi một pytest session đang chạy. Original32-operation baseline giữ
nguyên; reusable C3 locator fixture có provenance checkpoint b1c906a, không thay
historical OpenAPI/handoff artifacts bằng snapshot mới.

### Luồng đọc cho FE

- A — D01 `/api/v1/stores/{store}/today?section=inventory,imports,mapping,permissions,readiness,planning`.
  Omit section lấy cả sáu, limit1..20/default5 cho mỗi sample. Chỉ active membership
  để vào; từng section kiểm quyền. Forbidden không counts/names/versions/timing;
  technical failure là unavailable, không zero. Current readiness không đồng nghĩa
  import completed; latest Run có queued/running/completed/failed và outcome/error.
  Snapshot bind section selection/current rights/Store day; stale409 refetch.
- B — SU01 `/api/v1/stores/{store}/suppliers?q=...&active=true&limit=50`.
  supplier.read, canonical same-Store ID/name/active/opaque version, folded name
  sort/UUID tie-break; cursor/filter/snapshot bound. Không terms/cost/contact,
  không yêu cầu chọn supplier nếu N6 fact cho phép null; inactive policy N6 giữ nguyên.
- C — M01/M02 nhận file_id/sheet_id/review_only/status/origin AND filters. Origin
  là suggestion_origin. M02 snapshot_id nhận mapping_revision từ M01; next cursor
  giữ cùng filters/limit. New counters đếm issues, batch unfiltered/filtered rõ;
  legacy Progress không đổi nghĩa và page length không phải total.
  I04 `include_preview=true&preview_id={id}&projection=source_effect` đọc pinned
  source → typed canonical → effect, không parser/model/recanonicalization từ GET.
  Raw cached formula chỉ có value/kind/formula_present, không expression. Cell/header
  >200 chars trả null + display warning; caps200 cells/action,2000/page, explicit
  partial/unavailable/truncated. Old preview thiếu source pin trả unavailable,
  không đoán lại từ file. Current và pinned sensitive permissions chặn whole response.
- D — Cùng I04: preview.aggregates chứa batch/selected/files/sheets, raw source
  rows và logical actions riêng. Hai file chung receipt: raw2/logical1 ở batch,
  mỗi file raw1/logical1; child totals overlap. Master reservation là action riêng
  nhưng raw row không nhân đôi. Classification áp sau grouping, records góp matched
  actions chỉ đếm một lần trong selected scope. Filters chỉ đổi read view; confirm/
  atomic commit vẫn toàn batch. Totals không phụ thuộc rows_limit hoặc page đã tải.
- E — N9 thêm created_by_user_id/created_date_from/to (AND với status/forecast dates),
  dùng accepted_at theo local midnight Store, upper bound exclusive ngày kế tiếp,
  đúng DST. Unknown creator trả empty; Staff dùng A03/RunSummary, không cần N12.
  captured_budget available/limit/currency là effective limit tại acceptance,
  không current Store cap/spend/remaining; known0 khác unavailable/null. Giữ cả ba
  finance/result permissions và list snapshot. Aggregate không hợp lệ vẫn integrity
  error; absent-evidence fallback được kiểm ở projector, không backfill Run giả.
- F — EX01 `GET /api/v1/procurement-plans/{run}/exports?option_id=...&status=...`.
  Current export+result+finance rights; trả export/job locators và verified artifact
  evidence. Queued/running=pending, completed bytes có thể available/missing/
  unverifiable; execution status không bị sửa vì file mất. Hash/size/download URL
  chỉ khi verified. GET không render/regenerate/tạo job; N11 kiểm lại bytes/rights.

Recipe identity limit: existing preview chưa reserve recipe_id trước commit;
RecipeEffect có Product/version/date/dependencies và identity_availability=
not_reserved, recipe_id=null khi chưa pin ID. Không bịa UUID hoặc sửa writer để
trang trí GET. Opening/count/history có typed effects riêng; không đổi nghiệp vụ.
Canonical examples/DTO meaning thuộc [API](../API_CONTRACT.md#today-operations),
[Import §17](../IMPORT_MAPPING_API_CONTRACT_VI.md#mapping-projections) và
[Planning §17](../PROCUREMENT_API_CONTRACT_VI.md#planning-discovery).

### Verification và giới hạn

Gate wire/architecture ban đầu60 passed. Linked C4 gate trước sửa fixture cuối:
24 passed/2 failed; affected N12 fake-clock alignment + typed blocked receipt check
sau sửa3 passed. Final C4 focused gate **24 passed (63.94s)**; related C1–C3/readiness/
history/PDF/DTO/architecture regression **191 passed (614.68s)**. Không cộng các gate
overlap thành unique/full-suite count. Query evidence và current grants/fresh-session
reads nằm trong tests; generated results chỉ ở ignored runtime.

Fail→fix trong setup/checks: Today basis có UUID/timestamp cần serialize trước digest;
fixture giữ grants sorted, đúng nested membership DTO và cùng fake clock cho N6/N12;
date-boundary fixture không lùi trước thời điểm config được tạo; export assertion
theo IDs, không giả thứ tự hai rows cùng timestamp. Giữ assertions/guards nghiệp vụ.
Review còn bổ sung pinned preview read permissions và known empty file/intersection
để mapping change không hạ quyền preview cũ hoặc biến empty thành foreign scope.

Query evidence (constant giữa page sizes trong fixtures): Today imports15 tasks,
limit1/20:14 SQL statements; SU01 15 suppliers, limit1/100:8; N9 3 Runs,
limit1/100:10; EX01 2 exports, limit1/100:10. Counts gồm authorization và transaction
statements được engine hook quan sát; GET tests assert không INSERT/UPDATE/DELETE.
Đây là focused fixtures, không production SLA. Matching-scope snapshot/hash work và
PDF artifact verification vẫn tăng theo số records/bytes, dù không N+1 DB queries.
Không browser/live runtime C4, real SMTP/model hoặc production-scale benchmark claim.
Final `scripts.dev status --test-database` và owned read-only probe pass: đúng
DB/role notifications5433, at_head=true/head0026,71 tables,0 application rows sau
fixture cleanup; limited role và cả sáu flags vẫn OFF. OpenAPI giữ69 locators C3,
thêm đúng D01/SU01/EX01, definitions cũ đổi chỉ I04/M01/M02/N9; N6 DTOs,
ReceiptEffect/ProfileSpec C3 không đổi. Baseline32 không bị thay. Secrets/whitespace/
local links/JSON examples và outside-WIP fingerprints được kiểm; main6f80735 và
backend9/Import15/Auth0 WIP giữ nguyên, C4 index trống. Không commit C4 hoặc mở C5.

<a id="excel-actual-receipt-c3"></a>
## HISTORICAL INFORMATION — C3 Excel hàng thực nhận checkpoint

C2 đã commit local `b9fe048a6c64ffb79438068076ee3e9d99d75fda` sau C1 f85c7cdd.
C3 COMPLETE backend acceptance, commit local b1c906a; không push/merge. Checkpoint source head0026,69 operations/64 paths,
permissions-v3/43,70 application tables/71 tổng; không DDL/endpoint/grant mới.
Demo8103 vẫn snapshot tích hợp cũ head0024/59 operations; không restart/upgrade.
Browser E2E chưa chạy, Gmail smoke cũ không chứng minh workflow email E2E.

### Chuẩn bị và luồng kiểm tra

Dùng đúng worktree/interpreter dưới đây; setup DB/role/private config được giữ
ở [phần setup C1/C2](#notifications-c1). Chỉ `shelfcash_notifications_test` và
role hạn chế `shelfcash_notifications_tester` trên5433. Không dùng DB demo/test nhánh
khác và không chạy pytest/reset đồng thời. Không migrate/reset DB mỗi lần đọc.
Trên máy này Docker Desktop đã được mở, chỉ start container PostgreSQL hiện hữu;
không Compose thứ hai hoặc thay credentials/volume.

```powershell
Set-Location D:\hocc_bk\ai\proj\projectMLAI\backend-notifications-foundation
$collaborationPython = (Resolve-Path ..\backend-integrate-import-auth\.venv\Scripts\python.exe).Path
& $collaborationPython -m scripts.dev status --test-database
# Chạy tuần tự; fixture chỉ sở hữu/reset notifications test DB:
& $collaborationPython -m pytest tests/integration/test_import_actual_receipts.py tests/unit/test_import_actual_receipts.py tests/api/test_stock_writes_openapi.py -q --tb=short --show-capture=no
```

Expected DB/current_user đúng hai tên trên, head0026, at_head=true,71 tables.
Accounts/Store/Ingredient trong tests là fixtures explicit qua provisioning/
application boundaries; không public operator endpoint, bypass verification hoặc
default Staff grants. Password/token chỉ local private/fixture, không docs/commit.
Store chưa import/config có thể trống/UNKNOWN; không seed để che readiness.

Luồng qua public API đã kiểm bằng HTTP test client, worker thật và PostgreSQL:

1. Login đúng Store, I01 draft → I02 upload CSV/XLSX → I03 analyze; J01 poll.
   Chọn `inventory_receipts`, khai source namespace/report_type và
   inventory_semantics=actual_receipt; source_record_id ổn định từng receipt line.
2. M01–M04 review fields/identity/physical conversion có evidence. Facts/date/
   supplier/cost không lấy từ filename/upload/profile defaults. observed_at là
   timestamp ISO có timezone; date-only/Excel serial không đủ observation fact.
   Nullable supplier/cost/date phải explicit null; known cost0 được giữ nguyên.
   Field inventory tại [schema inventory](../features/IMPORT_SCHEMA_INVENTORY.md#inventory_receipts--hàng-thực-nhận-c3).
3. Nếu cần Owner duyệt, MQ01 submit → MQ02/MQ03 → N5 approve/request_changes.
   Approved profile reuse cần source proof và không gọi model. Activation chưa ghi kho;
   spec drift/retirement/current Staff rights vẫn kiểm lại.
4. I05 phase=preview → J01 → I04 include=preview,configurations. Kiểm canonical
   facts, warnings/blockers và typed receipt_effect: CREATE/REUSE/BLOCKED, stable
   receipt/lot/movement IDs, occurred_at/recorded_at. Preview không ghi kho.
5. I05 phase=confirm_review, rồi phase=commit với revision/digest/CAS/key hiện hành;
   J01 → I06. Receipt-only resolutions=[]; không gọi N6 HTTP từng dòng. Commit cần
   import.commit + inventory.receive; đọc/bind ingredient/inventory, nonnull supplier
   và cost dùng quyền hiện hành (cost là procurement.cost.read, kể cả giá0).
6. Completion.receipt_reference trong canonical_references giữ receipt/lot/movement,
   action CREATED/REUSED và audit_reference. Refresh V01/V02/inventory/readiness từ
   session mới. Receipt không tự khai complete; fresh capture thấy stock mới,
   retained PlanningRun cũ không đổi. PREVIEW_STALE cần preview/confirm lại, gồm
   inventory/read-set/declaration drift hoặc qua ngày Store mới.

Shared writer: N6 StockWrites.receive và Import actual/opening cùng
InventoryReceipts → InventoryUseCases.receive_in_transaction, cùng ledger
InventoryReceiptRecord, một transaction toàn batch. Same identity/normalized facts
replay, khác facts conflict; duplicate rows coalesce giữ mọi location và nested
per-source transformation evidence. REUSE_RECEIPT.quantity_delta là movement cũ,
không tăng stock lần nữa; new file không xóa receipts vắng mặt. Tên file/lot label
không chứng minh independent business identity. Opening/count/purchase history/
Planning purchases giữ nghiệp vụ riêng. [Contract §16](../IMPORT_MAPPING_API_CONTRACT_VI.md#excel-actual-receipt)
sở hữu semantics; không mở projection C4.

Provider/SMTP và tất cả background-worker flags mặc định OFF. Integration tests
explicit gọi bounded Import run_one trên own DB; không gửi email/model, không
bật process mới hoặc sửa runtime8103. Notification dispatcher opt-in ở phần C1/C2.

### Verification C3 trên máy này

Các commands đã chạy tuần tự với interpreter/worktree trên; targeted passing
không phải full-suite pass. Nhóm N6/opening/count/stock/readiness + C3 ban đầu:

```powershell
# 51 passed /2 failed trước sửa hai giả định trong test:
& $collaborationPython -m pytest tests/integration/test_stock_writes.py tests/integration/test_import_setup_stock.py tests/integration/test_import_inventory_supplier.py tests/integration/test_import_readiness_snapshot.py tests/integration/test_import_actual_receipts.py tests/api/test_stock_writes_openapi.py -q --tb=short --show-capture=no --junitxml=runtime/notifications/c3-inventory-regressions.xml

# 14 passed /1 failed; hai failure trên đã pass, còn day-rollover confirm fence:
& $collaborationPython -m pytest 'tests/integration/test_import_setup_stock.py::test_fresh_multifile_setup_readiness_custom_planning_and_retained_run[True]' tests/integration/test_import_actual_receipts.py::test_concurrent_receipt_jobs_share_identity_then_stale_batch_requires_refresh tests/integration/test_import_actual_receipts.py::test_receipt_foreign_identity_binding_is_scope_safe tests/integration/test_import_actual_receipts.py::test_new_receipt_file_does_not_delete_absent_receipt_or_reuse_lot_label tests/integration/test_import_actual_receipts.py::test_receipt_store_day_rollover_requires_new_preview tests/unit/test_import_actual_receipts.py -q --tb=short --show-capture=no --junitxml=runtime/notifications/c3-affected-fixes.xml

# Sau sửa fence + explicit timestamp validation:12 passed.
& $collaborationPython -m pytest tests/integration/test_import_actual_receipts.py::test_receipt_store_day_rollover_requires_new_preview tests/integration/test_import_actual_receipts.py::test_receipt_spec_change_uses_existing_queue_and_stale_decision_fence tests/unit/test_import_actual_receipts.py -q --tb=short --show-capture=no --junitxml=runtime/notifications/c3-receipt-final-fixes.xml
```

Fail→fix: A3 fixture chọn row theo domain sales thay vì vị trí đầu; concurrent
fixture chuẩn bị cả hai analyses trước queue commits, không giả worker sẽ claim
job vừa tạo. Fence day-rollover ban đầu chỉ ở commit; đã thêm tại confirm.
Các lỗi fixture ban đầu về provenance wire shape, sensitive I04 selector,
retired alias binding và capture import path đã sửa/rerun affected cases;
không bỏ assertion nghiệp vụ hoặc nới guards để pass.

OpenAPI giữ69/64; thêm ActualReceiptValue,ReceiptEffect,ReceiptCommitReference và
extensions typed rows/schema selectors, không đổi operation definitions hoặc N6
StockReceiptRequest/Result. Original baseline provenance giữ nguyên.
Regression C1/C2/field/history ban đầu196 passed/1 failed (417.89s): Sales test
assumed preview order. Đã đổi assertion sang exact Product→quantity mapping,
giữ kiểm cả hai records và known zero; case được rerun trong final targeted gate.

```powershell
& $collaborationPython -m pytest tests/integration/test_notifications.py tests/integration/test_permission_requests.py tests/integration/test_mapping_submissions.py tests/integration/test_collaboration_boundaries.py tests/integration/test_import_rule_review.py tests/integration/test_import_field_value_bindings.py tests/integration/test_import_history_a2.py tests/unit/test_notifications.py tests/unit/test_collaboration.py tests/unit/test_import_supplier_basis.py tests/unit/test_import_stockout.py tests/unit/test_import_recipe_basis.py tests/unit/test_import_opening_stock.py tests/unit/test_import_history_a2.py tests/unit/test_import_field_values.py tests/api/test_notification_openapi.py tests/api/test_collaboration_openapi.py tests/api/test_stock_writes_openapi.py -q --tb=short --show-capture=no --junitxml=runtime/notifications/c3-collaboration-regressions.xml

& $collaborationPython -m pytest tests/integration/test_import_field_value_bindings.py::test_first_sales_then_reuse_requires_new_import_report_key tests/integration/test_import_actual_receipts.py tests/unit/test_import_actual_receipts.py tests/unit/test_import_preview.py tests/unit/test_application_contracts.py tests/unit/test_integration_contract_snapshot.py tests/api/test_stock_writes_openapi.py -q --tb=short --show-capture=no --junitxml=runtime/notifications/c3-final-targeted.xml

& $collaborationPython -m scripts.integration_contract_snapshot
git diff --check
```

Không rerun full suite chỉ vì docs; kiểm architecture/query separation, original
OpenAPI baseline, current N6/C3 DTOs và related Import boundaries trong nhóm trên.
Final targeted gate: **105 passed** (200.87s), gồm toàn bộ20 C3 HTTP/PG cases,
14 C3 unit cases, case Sales vừa sửa và related preview/architecture/OpenAPI.
Final owned probe + `scripts.dev status --test-database`: reachable, đúng DB/role
riêng5433, at_head=true/head0026,71 tables; fixture cleanup để0 application rows.
Role vẫn không superuser/CREATEDB/CREATEROLE/replication/bypassrls; cả sáu worker/
email/model flags OFF. Audit file checks: original WIP backend9/Import15/Auth0 và
main6f80735 giữ nguyên, C3 index trống; secret/whitespace checks,197 local links và
35 JSON examples pass. Không claim full-suite hoặc browser/runtime8103 pass.

<a id="notifications-c1"></a>
## HISTORICAL INFORMATION — C1/C2 collaboration acceptance

Worktree `D:\hocc_bk\ai\proj\projectMLAI\backend-notifications-foundation`, branch
`feat/notifications-foundation`, base main6f80735; C1 commit local f85c7cdd,
C2 COMPLETE backend, commit local b9fe048, head0026/69 operations/64 paths. Commands này **không nâng cấp/bật
C1/C2 trên demo8103**. FE/browser E2E
chưa chạy; OpenRouter/SMTP và Import/Planning/PDF/email workers OFF trong profile C1/C2.

### Setup lần đầu

Phiên này đã provision `shelfcash_notifications_test`, role riêng
`shelfcash_notifications_tester` (không superuser/CREATEDB/CREATEROLE), trên instance
Docker PostgreSQL5433 hiện hữu. Role có HBA boundary chỉ đúng DB; DB marker xác nhận
owned test target. Không chạy thêm Compose. `.env` ignored của worktree đã đặt
DATABASE_URL và TEST_DATABASE_URL cùng target C1/C2; credentials giữ local private ở
`runtime/notifications/private/db.json`, không copy vào docs/Git/chat. Máy khác cần
provision riêng DB/role này và cấu hình private trước; không reuse demo credentials.
Không trỏ test/reset vào DB demo/development hoặc các DB test nhánh khác.

Commands thực tế trên máy này dùng interpreter integration đã cài dependencies,
nhưng import source/config theo working directory collaboration:

```powershell
Set-Location D:\hocc_bk\ai\proj\projectMLAI\backend-notifications-foundation
$collaborationPython = (Resolve-Path ..\backend-integrate-import-auth\.venv\Scripts\python.exe).Path
& $collaborationPython -m scripts.dev status --test-database --allow-unmigrated
# Chỉ tiếp tục khi database/current_user đúng owned collaboration DB, DATABASE_URL cũng đúng target đó:
& $collaborationPython -m alembic upgrade head
& $collaborationPython -m scripts.dev status --test-database
```

Expected current_database/current_user: shelfcash_notifications_test /
shelfcash_notifications_tester; head `["0026_collaboration_requests"]`,71 tables,
at_head=true. Upgrade additive, không seed. Alembic kiểm effective target/role;
không stamp/drop/reset để giải quyết mismatch. Tests dùng supported reset fixture
chỉ trên DB này, không chạy song song với test session khác.

### Dispatcher hằng ngày và ownership

```powershell
# Từ worktree collaboration, sau khi đã đặt $collaborationPython như trên:
& $collaborationPython -m scripts.dispatch_notifications --help
& $collaborationPython -m scripts.dispatch_notifications --limit 20
& $collaborationPython -m scripts.dev status --test-database
```

Command sở hữu một batch, tự kết thúc; không để lại process cần stop, không HTTP
poll delivery endpoint. Empty DB expected `Completed notifications: 0`; count0
không chứng minh không có pending/failed/not-due intent. Status đọc DB/head/table
counts, không dùng health để xác nhận dispatch ready. Operator xem intent status,
attempt/next_attempt_at/error_code qua local DB đã được authorize, không public API.
Sau sửa dispatcher cho failed payload, retry giữ nguyên identity:
`& $collaborationPython -m scripts.dispatch_notifications --retry-failed <intent-UUID> --limit 20`.
Không sửa payload/audit hoặc tạo event mới để bypass lỗi.

Long-running worker chỉ thuộc lifespan của ASGI process có explicit
`NOTIFICATION_WORKER_ENABLED=true`; tên thread shelfcash-notifications, bounded batch
20 mỗi1s, stop event + join khi process shutdown. Default false không connect DB từ
startup/health. Chỉ bật trong profile collaboration đã migrate, đúng DB/runtime directory;
không bật flag hoặc restart demo8103 trong lát này. Lifecycle opt-in/stop được test
bằng dispatcher double; DB dispatcher thật được kiểm qua batch/persistence tests.

### FE API delta và giới hạn

NF01 GET `/api/v1/notifications`: store_id/unread/limit/cursor, không body.
NF02 GET `/api/v1/notifications/unread-count`: store_id/snapshot_id; dùng snapshot
từ NF01 khi cần cùng observation. NF03 PATCH `/api/v1/notifications/{UUID}` với
`{read:true|false}`, exact Origin, X-CSRF-Token, quoted If-Match và canonical UUID
Idempotency-Key. Cookie requests luôn credentials include. PATCH trả ETag;
refetch badge/list, không count theo độ dài page.409 snapshot đổi thì refetch từ
đầu;412 đọc version mới/review trước key mới; retry timeout giữ key/body/CAS cũ.
Contract/typed DTO/error/security details do
[notification contract](../NOTIFICATION_API_CONTRACT_VI.md) và OpenAPI sở hữu.
Không thêm notification grants. PR/MQ locators reauthorize own/Owner và sensitive
source rights; thiếu quyền target thì link=null. N13/PR/MQ là producers thật,
không public send endpoint. Runtime8103 chưa có NF/PR/MQ routes; browser E2E pending.

<a id="collaboration-c2"></a>
### CURRENT FACT — C2 quyền và mapping queue

PR01 submit không grant; PR02 trả own Staff requests + catalogue43, Owner toàn Store;
PR03 đọc current grants/state/ETag; PR04 approve union subset, reject/cancel giữ grants.
Lấy expected_grants_version qua T02 membership.authorization_version hoặc
PR03.current_grants_version; If-Match PR04 dùng quoted request.version.
Retry uncertain ACK giữ key/body/CAS cũ; receipt sau revoke không regrant.
N13 vẫn replace và N14 audit có nullable permission_request_id/decision_id.

MQ01 submit/withdraw dùng quoted **import_revision** làm If-Match; response ETag là
batch revision, submission.version là CAS riêng. Không tăng batch/mapping revision
do submit. MQ02 Owner mặc định submitted eligible, Staff tất cả own; explicit state
đọc lịch sử. MQ03 trả pinned spec/source/evidence, evidence_limit1..100/default20
và evidence_cursor; current_profile/eligibility chỉ báo trạng thái hiện hành.
N5 dùng profile lifecycle ETag; queue caller gửi cả submission_id và
expected_submission_version. Direct N5 có live submission vẫn áp cùng pins.

Luồng kiểm tra qua public boundaries:
1. Dùng private account/provisioning và invitation acceptance được hỗ trợ để có
   active Owner/Staff; cấp explicit test grants, không public operator endpoint.
2. Staff PR01 → Owner PR03/PR04 approve subset → trên session Staff cũ refresh
   A03/T02; unrelated grants còn nguyên. Dispatcher batch → requester NF01.
3. Staff I01/I02/I03 và source declaration M04 → MQ01 submit full profile;
   Owner MQ02/MQ03 kiểm pinned source/spec → N5 approve/request_changes/reject.
4. Approval chỉ activate profile. Người nhập vẫn I05 preview → đọc I04 →
   confirm_review → explicit commit; kiểm fresh committed rows/I06 riêng.
5. M04/source/lifecycle drift làm task stale; sửa rồi explicit submit mới.
   NF03 read/unread không xóa queue hoặc quyết định thay PR04/N5.

HTTP test clients thực hiện đúng các routes/cookie/Origin/CSRF/CAS/receipt trên
PostgreSQL thật. Fixture reset **chỉ owned notifications test DB**, tuần tự;
không chạy khi có manual session cần giữ dữ liệu trên DB đó. Synthetic accounts,
source CSV và product fixture có nguồn explicit trong tests; không account/seed
demo mới hoặc credentials trong docs. `.env`/private db.json chỉ giữ credentials
DB; không dùng accounts của demo8103 để test C2.

```powershell
# Từ đúng worktree và interpreter đã khai báo ở trên:
& $collaborationPython -m pytest tests/integration/test_permission_requests.py tests/integration/test_mapping_submissions.py tests/integration/test_collaboration_boundaries.py tests/unit/test_collaboration.py tests/api/test_collaboration_openapi.py -q --tb=short --show-capture=no
& $collaborationPython -m scripts.integration_contract_snapshot
git diff --check
```

CURRENT FACT: C2 source +7 PR/MQ operations/+6 paths từ C1 →69/64; old route chỉ
N5 body extension, old DTO extensions chỉ Approve/Reject/DecisionResult/PermissionEvent.
Additive0026 giữ0025 facts; own DB/role guards như setup ở trên. Producers PR submit/
approve/reject và MQ submit/N5 outcomes atomic; no-op grant approval không thêm
PermissionEvent, PR approval không duplicate membership.grants_changed.
Verification trên máy này dùng cùng interpreter/working directory nêu trên,
SMTP/OpenRouter OFF và chỉ owned notifications test DB, tuần tự. Các lệnh đã chạy:

```powershell
# Full milestone gate, trước đợt sửa cuối:2308 passed /10 failed (4018.95s).
& $collaborationPython -m pytest -q --tb=short --show-capture=no --junitxml=runtime/notifications/c2-suite.xml

# Sau sửa query separation/inventories và C2 refinements:56 passed.
& $collaborationPython -m pytest tests/unit/test_application_contracts.py tests/unit/test_collaboration.py tests/unit/test_integration_contract_snapshot.py tests/unit/test_sales_stockout_migration.py tests/api/test_collaboration_openapi.py -q --tb=short --show-capture=no

# Linked HTTP/PG+C2 cases lúc này:21 passed (trước khi thêm hai retention cases cuối).
& $collaborationPython -m pytest tests/integration/test_collaboration_boundaries.py tests/integration/test_permission_requests.py tests/integration/test_mapping_submissions.py -q --tb=short --show-capture=no --junitxml=runtime/notifications/c2-targeted.xml

# Affected old failures + C1/N13/N5 regressions và strengthened OpenAPI:69 passed.
& $collaborationPython -m pytest tests/integration/test_data_semantics_correction.py::test_migration_downgrade_reupgrade_preserves_known_receipt tests/integration/test_data_semantics_correction.py::test_downgrade_refuses_unknown_receipt_without_fabrication tests/integration/test_forecast_decision_persistence.py::test_fresh_migration_exact_tables_and_downgrade tests/integration/test_supplier_operational_constraints.py::test_fresh_schema_and_downgrade_reupgrade tests/integration/test_verification_commands.py tests/integration/test_notifications.py tests/integration/test_staff_public.py tests/integration/test_import_rule_review.py tests/api/test_collaboration_openapi.py tests/api/test_notification_openapi.py tests/unit/test_notifications.py -q --tb=short --show-capture=no --junitxml=runtime/notifications/c2-regressions.xml

# Two final C2 facts/audit/pins/terminal/downgrade+GET cache/body guards:2 passed.
& $collaborationPython -m pytest tests/integration/test_collaboration_boundaries.py::test_permission_request_facts_audit_and_terminal_retention tests/integration/test_collaboration_boundaries.py::test_mapping_pin_terminal_and_migration_retention -q --tb=short --show-capture=no
```

Fail→fix:9 full-gate failures là stale head0024/table65/API59 expectations;
cập nhật exact inventory tới0026/71/69, giữ original API baseline và migration
parent tests. Failure còn lại là direct SQL trong application; chuyển query của
PR/MQ/inbox/dispatcher sang concrete repositories, giữ architecture guard và
caller-owned Session/fences. Refinements thêm current batch/profile revisions vào
queue/evidence snapshots, bounded source-page projection, ETag OpenAPI,
private,no-store và256-byte versions; absent N5 queue fields giữ original receipt
fingerprint. Các case bổ sung xác minh old Staff session/current grants, uncertain
ACK/races, terminal snapshots, source/pin/Store/revoke boundaries, rollback and
separate Staff preview/confirm/commit; không chỉ HTTP2xx.

Full gate chạy một lần vì schema/shared transaction milestone. Sau sửa chỉ rerun
affected coverage theo policy; **không có final full-suite PASS claim**. Các nhóm
trên có overlap, không cộng thành số unique acceptance cases. C2 COMPLETE backend
scope, đã được yêu cầu commit local; chưa merge/push. Browser E2E, demo8103 upgrade và real email/model
workflow chưa verified; C3 chưa bắt đầu.

### Verification foundation, provider OFF

```powershell
& $collaborationPython -m pytest tests/unit/test_notifications.py tests/integration/test_notifications.py tests/api/test_notification_openapi.py -q --tb=short --show-capture=no
& $collaborationPython -m scripts.integration_contract_snapshot
git diff --check
```

HISTORICAL INFORMATION: command pytest foundation trên pass25 cases tại C1. Schema/lifecycle changes có lý
do chạy regressions Auth/Staff, guarded tooling và affected migration roundtrips;
những nhóm liên quan đã pass, không gọi targeted pass là full regression.
`integration_contract_snapshot` so với original baseline32 operations; C1 delta
đã kiểm riêng với main6f80735: giữ nguyên59 operations/55 paths và DTO cũ, thêm3 NF
operations/paths. GET list/count, read/no-op/replay và
delivery được kiểm qua fresh sessions; không email/model/browser live call.

HISTORICAL INFORMATION trước C5: runtime8103 thuộc worktree tích hợp, giữ0024 và daily
commands cũ; không thay commands đó sang collaboration source để vượt migration guard.

<a id="integrated-demo-runtime"></a>
## HISTORICAL INFORMATION — runtime tích hợp trước customer self-service

Chạy từ `D:\hocc_bk\ai\proj\projectMLAI\backend-main-integrated`, branch
`main`, source committed gồm C1–C4 và C5 tooling. Status báo source_root/source_sha của process.
Đây là launcher **chỉ BE**; không dùng `scripts/local-integration.ps1` của demo S4.11
cho nhánh tích hợp. Launcher cũ dùng settings.json riêng và volume demo cũ, không .env
mới. DB cũ shelfcash_integration_s411/head0017 cùng hai Store được giữ nguyên.

### Chạy hằng ngày — môi trường này đã setup

Mở Docker Desktop, bảo đảm instance PostgreSQL hiện có đang chạy. Trong PowerShell:

```powershell
Set-Location D:\hocc_bk\ai\proj\projectMLAI\backend-main-integrated
$demoPython = '..\backend-integrate-import-auth\.venv\Scripts\python.exe'
& $demoPython -m scripts.integrated_demo status
& $demoPython -m scripts.integrated_demo start
# Khi cần dừng BE:
& $demoPython -m scripts.integrated_demo stop
```

Expected status: DB `shelfcash_integration_demo`, role runtime, revisions
`["0026_collaboration_requests"]`,71 bảng. Trước start có thể stopped; sau start là
running, import_alive/planning_alive/pdf_alive/notification_alive=true, email_enabled=false.
Start reuse đúng process do launcher sở hữu, không mở process trùng. Expected stop:
`Owned BE and lifespan workers stopped; DB/data preserved` hoặc already stopped.
Không reset/migrate/seed khi chạy hằng ngày. Launcher không khởi động/dừng FE.
FE đang lỗi khi người dùng test và tạm dừng xử lý; browser E2E pending.

### Profile, DB và cấu hình private

API base `https://localhost:8103` (không thêm `/api/v1`), exact allowed Origin
`https://localhost:5173`. Instance Docker hiện có: container
`shelfcash-integration-s411-postgres-1`, loopback5433; không Compose thứ hai.
DB riêng `shelfcash_integration_demo`, marker `ShelfCash integrated HTTPS demo v1`;
runtime `shelfcash_integration_demo_runtime`, migration `shelfcash_integration_demo_migrator`.
Cả hai NOSUPERUSER/NOCREATEDB/NOCREATEROLE/NOREPLICATION/NOBYPASSRLS, không membership
role khác. Migrator sở hữu schema; runtime chỉ CONNECT/USAGE/DML/sequence, không CREATE.
HBA rules dành riêng hai role đứng trước rules cũ, chỉ cho đúng DB với SCRAM và
từ chối DB khác. Rules/credentials cũ không đổi; backup config/HBA trước chỉnh nằm
ngoài repo tại sibling `.shelfcash-private-backups` (private, không đưa Git).

Ignored `.env` chọn DB demo và runtime storage riêng; TEST_DATABASE_URL vẫn chỉ
shelfcash_integration_test/shelfcash_integration_tester, không trỏ demo. Tests/reset
không được dùng demo; guard reset hiện hành từ chối tên này. Process environment
override .env nên launcher luôn kiểm effective target/security và connected identity.
Runtime private secrets/keys/accounts ở `runtime/integrated-demo/private`, không in
URL/password/token hoặc đưa vào report/FE/Git. HBA/DB provisioning cần container cũ
đang chạy; launcher không tự khởi động/dừng Docker, reset hoặc migrate khi start.

### Setup lần đầu — không chạy lại mỗi ngày

Cần Python3.11+, Docker Desktop Linux engine, instance hiện có ở trên và ignored
.env có TEST_DATABASE_URL đúng `shelfcash_integration_test`/
`shelfcash_integration_tester`. Guard này được kiểm trước mọi provisioning.
Clone/máy mới cần operator cấu hình instance và test credentials đúng trước init;
profile không tự tạo instance/test DB, không dùng runtime secrets của người khác.

```powershell
Set-Location D:\hocc_bk\ai\proj\projectMLAI\backend-main-integrated
$demoPython = '..\backend-integrate-import-auth\.venv\Scripts\python.exe'
# Chỉ máy mới chưa có venv/dependencies:
python -m venv .venv
$demoPython = '.\.venv\Scripts\python.exe'
& $demoPython -m pip install -e '.[dev]'
# Chỉ nếu chưa có .env; sửa TEST_DATABASE_URL qua editor local trước init:
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Template .env.example dùng shelfcash_test, cần đổi sang integration test DB/role
được cấp riêng; không in connection URL/password. Khi prerequisites đã đúng:

```powershell
& $demoPython -m scripts.integrated_demo init
& $demoPython -m scripts.integrated_demo backup-upgrade
& $demoPython -m scripts.integrated_demo migrate
& $demoPython -m scripts.integrated_demo start
& $demoPython -m scripts.integrated_demo_accounts provision
```

Init giữ credentials/cert/DB đã sở hữu, từ chối DB/role đã tồn tại không có private
ownership credentials. Migrate kiểm current_database/current_user/marker/owner/role
trước Alembic và chỉ upgrade tới single head của source graph (hiện0026); không drop/reset/seed. Sau migration,
runtime có71 bảng (70 application + Alembic). Migration credentials không dùng
cho process BE. Chạy init lại chỉ khôi phục profile demo, giữ TEST_DATABASE_URL;
không dùng để ghi đè tùy biến một môi trường khác.

Port8103 được kiểm trước start; không kill process khác hay đổi port ngầm. Metadata
PID/birth/run_id, worker observations và matched exit nằm private. Stop cooperative
qua Uvicorn/lifespan, join workers; không forced kill. UNKNOWN/reused PID bị từ chối.
DB/volume/audit/credentials giữ sau stop. Status kiểm DB identity/head/schema và
incarnation/worker observation mới; health chỉ là liveness.

### Upgrade demo hiện có — không reset

C5 chuyển source serving sang `backend-main-integrated` committed sạch. Private config,
accounts/cert và app storage được copy có chọn lọc từ worktree tích hợp; credentials,
Origin/callback và business facts giữ nguyên. Không chạy init/provision để đổi existing
accounts/grants. Không dùng `.env` tests của worktree notifications để phục vụ demo.
Launcher start từ chối source WIP hoặc reuse process đang chạy snapshot SHA khác.

Trước migrate: kiểm connected database/user/marker/limited role, pending/running jobs;
backup-upgrade dùng custom pg_dump, verify TOC/full payload/SHA-256 và lưu counts cùng
private config ngoài Git tại sibling `.shelfcash-private-backups`. Backup không ZIP.
Stop đúng owned process và kiểm không còn work; migrate từ chối live/UNKNOWN process,
backup thiếu/hỏng/row counts thay đổi, source SHA/root khác hoặc unknown migration.
Alembic dùng migrator riêng, sau upgrade kiểm head/schema và giữ counts các bảng cũ;
runtime tiếp tục limited role. Không stamp/downgrade tự động hoặc đụng DB khác.

```powershell
# Sau khi đã chọn worktree/interpreter như luồng hằng ngày:
& $demoPython -m scripts.integrated_demo backup-upgrade
& $demoPython -m scripts.integrated_demo stop
& $demoPython -m scripts.integrated_demo migrate
& $demoPython -m scripts.integrated_demo start
& $demoPython -m scripts.integrated_demo_accounts verify
```

Nếu work phát sinh sau backup hoặc backup source không khớp, dừng ở guard và tạo backup
mới sau quiescence; không bỏ guard. Khi upgrade fail, giữ archive/config/error evidence,
đối chiếu transactional schema trước controlled recovery; không restore đè DB đang dùng.
Daily start/status/stop không migrate hoặc tạo backup mới.

### Trust certificate một lần và yêu cầu FE

TLS cert self-signed localhost/127.0.0.1 SAN,30 ngày, sinh theo tooling Auth hiện có.
BE/probe giữ TLS verification, probe trust đúng `localhost.pem`, không verify=False.
Để browser tin certificate, người dùng cài public cert vào CurrentUser trust store:

```powershell
Import-Certificate -FilePath .\runtime\integrated-demo\private\localhost.cer -CertStoreLocation Cert:\CurrentUser\Root
```

Đây là thao tác trust trên máy người dùng, chưa được launcher thực hiện. Chỉ import
public certificate, không private key. Certificate hết hạn cần thay có kiểm soát;
init không tự overwrite key/cert.
FE sở hữu HTTPS/config/cert và lỗi browser hiện tại; launcher BE không làm phần FE.
HISTORICAL INFORMATION: private local helper từng kiểm page/config qua TLS mà
không sửa FE files; đó không phải browser E2E pass và không thuộc luồng chạy BE.
HTTP5173 bị từ chối đúng
allowlist. Requests dùng credentials include; cookie __Host Secure/HttpOnly/
SameSite=Lax/Path=/; CSRF token hiện hành bắt buộc cho protected mutations.

Callbacks, đối chiếu source FE đọc ngày14/10 (browser chưa verify):

| Purpose | FE route / trạng thái | API consumer |
| --- | --- | --- |
| SETUP/RESET | `https://localhost:5173/credentials/complete#token=<private>`; route có trong source, hai settings callback đã khớp | POST `/api/v1/auth/credentials/complete` |
| Invitation private delivery | `https://localhost:5173/invitations/{invitationId}#token=<private>`; route có trong source | GET offer với X-Invitation-Token, POST `/api/v1/staff-invitations/{id}/accept` |
| Invitation SMTP | Chưa configure: sender hiện hành dùng fixed page + fragment invitation_id/token, không tự thay path param. Cần chốt formatter/landing route với FE trước real delivery | N18/N19 như trên |
| EMAIL_VERIFY | Chưa có route FE được xác nhận; callback unset. FE cần nối trang verification, không đoán /verify-email | POST `/api/v1/auth/email-verifications/complete` |

### Tài khoản local, dữ liệu và workers

```powershell
notepad .\runtime\integrated-demo\private\accounts.json
```

Owner/Staff test đã có trong private `accounts.json`: Owner Store chính, Staff chỉ
`menu.read` qua public invitation/acceptance, Owner thứ hai ở Store riêng để kiểm
isolation. Provisioning dùng audited AssistedProvisioning với evidence **synthetic
holder theo yêu cầu người dùng**, không giả proof của người thật; SETUP qua private
capture rồi public N7. Private setup/invitation files giữ token/link cho recovery;
token đã dùng không dùng lại, login bằng credentials ở accounts.json. Mở file bằng
editor local riêng; không cat vào chat/log, không copy vào config FE/localStorage.
Provision không reset password hoặc khôi phục grants đã revoke cho account hoàn tất.
Store trống, cần import/configuration/completeness có nguồn; không tạo business facts,
default budget/readiness hay operational fixtures để làm xanh.

Import/Planning/PDF/notification bật trong một process BE; idle dependency calls kiểm đúng DB,
runtime writable và thread observation. Không chạy worker thứ hai trên DB này.
OpenRouter/Qwen OFF, không live model call. SMTP fields có thể được init tái sử dụng
từ ignored .env của backend-auth-self-service; Auth email delivery giữ OFF và không
SMTP connect/send trong setup này. Public register/resend/forgot trả503
EMAIL_DELIVERY_UNAVAILABLE đúng contract, không hứa check-email. Credential và
invitation test dùng private capture; invitation dispatch không chạy SMTP tự động.
Muốn bật real email cần xác nhận callback/FE và scope email riêng, không chỉ bật flag.
Gmail smoke lịch sử chỉ chứng minh một email smoke, khác signup/setup/reset/
invitation workflow E2E. Lượt hoàn thiện/merge không gửi email hoặc model thật.

### Kiểm chứng BE — không browser E2E/full acceptance

```powershell
& $demoPython -m scripts.integrated_demo_accounts verify
& $demoPython -m pytest tests/unit/test_integrated_demo.py tests/unit/test_database_config.py tests/api/test_auth_openapi.py tests/api/test_staff_openapi.py -q --tb=short --show-capture=no
```

Verify dùng certificate trust rõ ràng; kiểm HTTPS health/OpenAPI đo từ source, hiện72 operations/66
paths, exact CORS preflight và wrong Origin/HTTP5173 rejection, login/me/cookie/CSRF,
Owner/Staff isolation/read denial, fresh committed holders/current Staff grants và
preservation của business history hiện có. DB/queue probes là read-only và dùng live worker
observations; không gọi run_one/recover cạnh workers đang chạy. Cho phép terminal history, từ chối khi có queued/running jobs/runs/exports;
verify không consume việc thật và kiểm counts business tables giữ nguyên.
Stop/start đã exercised trong C5 cần kiểm theo đúng source commit đã bàn giao. Nonempty job execution, SMTP gửi thật,
browser FE flow và real-data quality chưa verified trên runtime này; acceptance
lịch sử trên DB test không thay thế chúng.

### Troubleshooting

| Dấu hiệu | Cách xử lý |
| --- | --- |
| Connection refused | Kiểm Docker instance hiện có/port5433; với8103 dùng BE status/start. Không mở Compose tranh port hoặc kill process khác. |
| DB authentication failed | Kiểm effective .env đúng DB/role và credentials private đúng instance. Không đổi role/password cũ, reset volume hoặc migrate để sửa auth. |
| Certificate error | Trust public localhost.cer trên máy browser; kiểm SAN/expiry. Không tắt TLS verification hoặc tự thay cert/key đang dùng. |
| Origin/CORS | Đúng HTTPS5173 và credentials include; FE5173 khác BE8103. Không wildcard hoặc thêm /api/v1 vào base URL. |
| 401 | Login lại bằng credentials private; session có thể expired/revoked. Kiểm cookie Secure/HTTPS và credentials include. |
| 403 | Kiểm Origin/CSRF rồi current Store permissions; Staff chỉ menu.read. Owner cấp quyền qua boundary được hỗ trợ, không SQL/bypass. |
| Job queued | Kiểm status worker observations/flags và private server.log. Không chạy thêm worker; email queued khi delivery OFF không tự gửi thật. |

## HISTORICAL INFORMATION — profiles và acceptance có scope riêng

Giữ các commands/evidence bên dưới theo đúng worktree/DB/profile được nêu;
không dùng chúng làm startup bản tích hợp hoặc kết luận browser E2E pass.

## A3 — backend Import → readiness → Planning acceptance

Run from `D:\hocc_bk\ai\proj\projectMLAI\backend-import-sales-stockout`, branch
`feat/import-sales-stockout`. Keep the A1/A2 WIP/setup. Use the existing interpreter;
provider OFF, sequential owned-DB tests, no server/browser or Auth worktree changes.
The main synthetic Store is created through assisted provisioning and all operational
facts enter through public Import/configuration boundaries; no business seed fills gaps.
Only the isolated unsupported-rule scope case uses the existing persisted-rule fixture.

Before pytest, validate configured target **and the connected database/role**, without
printing URLs/credentials. Do not use development, demo, Auth or shared test databases.

```powershell
Set-Location D:\hocc_bk\ai\proj\projectMLAI\backend-import-sales-stockout
$env:IMPORT_LLM_SUGGESTIONS_ENABLED='false'
@'
from app.config import Settings
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
s = Settings()
u = make_url(s.test_database_url)
assert u.database == 'shelfcash_import_test' and u.username == 'shelfcash_import_tester'
assert not s.import_llm_suggestions_enabled
engine = create_engine(s.test_database_url)
with engine.connect() as c:
    assert c.execute(text('SELECT current_database(), current_user')).one() == ('shelfcash_import_test', 'shelfcash_import_tester')
engine.dispose()
print('Owned Import DB/role and provider-OFF guards PASS')
'@ | & ..\backend\.venv\Scripts\python.exe -
```

A3 coverage selectors below reproduce the acceptance gaps and affected helper callers.
For continuation after a failure, run only the failed/affected selector; do not repeat
already passing A1/A2 groups or a broad suite without a new reason.

```powershell
$cases = @(
  'tests/integration/test_import_setup_stock.py::test_fresh_multifile_setup_readiness_custom_planning_and_retained_run',
  'tests/integration/test_import_planning_a3.py',
  'tests/integration/test_import_recipe_basis.py::test_two_recipe_reports_same_version_never_union_distinct_ingredients',
  'tests/integration/test_import_staging.py::test_multiple_approved_profiles_require_explicit_context_selection',
  'tests/integration/test_import_inventory_supplier.py::test_mixed_commit_lost_ack_is_reconciled_and_public_count_scope_invalidates_on_new_lot',
  'tests/integration/test_import_setup_stock.py::test_fresh_opening_public_commit_reimport_and_count',
  'tests/integration/test_import_history_a2.py::test_history_depends_on_reviewed_master_across_file_order'
)
& ..\backend\.venv\Scripts\python.exe -m pytest @cases -q --tb=short --show-capture=no
```

Expected main fixture: eight complementary files establish one Product/Ingredient/
Supplier, recipe1 litre/cup, observed uncensored sales2 cups, pack4 litres at10 VND,
opening12 litres and explicit fee NONE. Source/report, Store identities and units
are reviewed before Owner full-spec approval; preview/confirm/commit run real Import
workers and fresh Sessions. Explicit stock/sales/procurement coverage and BASELINE
serving declaration, Store cap100 and custom BASE95% are required. R01 may still report
DEFAULT_CONFIGURATION_UNAVAILABLE; successful custom Planning does not claim default
readiness. Completion readiness is execution capability, not forecast quality.

Seven-day BASE demand14 cups needs14 litres: winner purchases1 pack, total10, fees0,
fulfilled14/lost0/service100%, consumed14/expired0/ending2. After explicit count0 plus
CONFIRMED_EMPTY, winner buys4 packs for40 and ends2. Canonical stock stays unchanged
by Planning; three movements are opening+12/count-2/count-10, one opening receipt.
Budget100→80 and sales2→3 correction after retention leave both public Run responses
and the original complete retained aggregate unchanged. Both upload orders are covered.
Synthetic expected arithmetic/causal mechanics do not establish real forecast accuracy.

Staff case obtains exact grants through public invitation/acceptance, reuses the
approved declared source and commits without model calls. A new token stays unresolved;
adding an alias forks the spec, Staff approval fails and Owner approval is required.
Existing A1/A2 evidence owns stockout3-state/contributions/masked correction/current
rights/isolation/rollback, history correction/price protection/no implicit grants and
retained consumer coverage. A3 inherits that evidence instead of rerunning whole groups.
The scoped safety case distinguishes unrelated Ingredients/future dates from a current
computed dependency; unsupported value0 blocks Planning and does not block forecast.

Recovery: fixture tests own only the guarded Import DB and reset it before/after a
case using supported reset code. If connection/role/head guard fails, stop and correct
the dedicated setup; never fall back to another DB or kill unrelated sessions. If a
job fails, inspect J01/error and fresh state; obtain new preview/confirmation for stale
input, resolve source/identity or use a nonretired approved version. A lost ACK retries
the same key and reads the durable receipt; never blindly reapply stock. Preserve
source/audit/artifacts and WIP. Migration heads remain independent; no migration,
feature, FE change or provider call is needed for this acceptance slice.

## A2 — manual review và targeted checks trên DB Import riêng

CURRENT FACT: worktree `D:\hocc_bk\ai\proj\projectMLAI\backend-import-sales-stockout`,
branch feat/import-sales-stockout; interpreter có dependencies tại
`..\backend\.venv\Scripts\python.exe`. Settings TEST_DATABASE_URL phải trỏ
shelfcash_import_test/role shelfcash_import_tester trước bất kỳ pytest/reset nào.
Provider OFF; mỗi phiên chạy DB checks tuần tự, không dùng shelfcash_test/Auth/dev DB.
Import migration0021 parent0019; không merge Auth heads0018/0020. Không startup migrate.

```powershell
Set-Location D:\hocc_bk\ai\proj\projectMLAI\backend-import-sales-stockout
$env:IMPORT_LLM_SUGGESTIONS_ENABLED='false'
& ..\backend\.venv\Scripts\python.exe -c "from app.config import Settings; from sqlalchemy.engine import make_url; u=make_url(Settings().test_database_url); assert u.database=='shelfcash_import_test' and u.username=='shelfcash_import_tester'; print('Import DB guard OK')"
& ..\backend\.venv\Scripts\python.exe -m pytest tests/integration/test_import_history_a2.py tests/integration/test_import_history_migration_a2.py -q --tb=short --show-capture=no
```

Manual synthetic flow: upload rows with stable source_record_key/evidence; declare
source/report before reuse; review typed fields and approved entity/physical unit
bindings; Owner approves reusable profile. Staff must separately have new domain
read/write grants and import.commit; purchase requires procurement.cost.read. Preview
keeps RECORDED_HISTORY_ONLY and calendar's no-feature warning. Confirm review, then
commit; a correction additionally sends history_corrections row_id/expected_version/
reason plus commit reason. I06 exposes history_record/canonical_version/provenance;
H01/H02 category calendar/usage/purchase discovers uploads (promotion=sales). Reimport
same facts NO_OP, changed fact append revision; old completion stays unchanged.
Verify through fresh Session that history rows exist and no lot/movement/receipt/
SupplierTerm is generated. History presence does not make Planning inputs complete.
R01 rejects configured unsupported MIN_SAFETY_STOCK for computed scope. Six demo
workbooks do not supply business truth or replace synthetic boundary coverage.

Coverage and current task notes/results belong in the conversation; commands above
are repeatable verification instructions, not a claim of a full suite or FE pass.

<a id="integrated-acceptance"></a>
## Bản tích hợp Import/Auth — PostgreSQL riêng, không FE/SMTP/provider

CURRENT FACT: branch feat/integrate-import-auth, worktree backend-integrate-import-auth,
common base b1ede89, Import126b0f2 và Auth0fbb979. One head0024_integrate_import_auth,
64 application tables/65 with Alembic; original branch heads/receipts below are historical.
Một Docker PostgreSQL có sẵn tại127.0.0.1:5432. Integration owns ONLY
shelfcash_integration_test / shelfcash_integration_tester; no superuser/CREATEDB/
CREATEROLE/replication. pg_hba denies cross-DB; local ignored .env supplies both
DATABASE_URL/TEST_DATABASE_URL, ENVIRONMENT=test and runtime/integration paths.
LLM/Import/Planning/PDF/account-email worker flags are OFF by default.

Before writes, effective settings and connected current_database/current_user are
checked. Integration role is mandatory for this named DB. Alembic test migrations
also check identity. Never supply another tree's .env or use a second Compose on5432.
No development/Import/Auth/demo/shared-test DB reset/migration. One pytest process
at a time on this DB. Dedicated source roles/DBs and Gmail demo remain unchanged.

```powershell
Set-Location D:\hocc_bk\ai\proj\projectMLAI\backend-integrate-import-auth
.\.venv\Scripts\python.exe -m scripts.dev status --test-database
.\.venv\Scripts\python.exe -m alembic heads
# Explicit owned integration DB reset only when needed:
.\.venv\Scripts\python.exe -m scripts.dev reset --test-database
# New traversal/guard gap checks:
.\.venv\Scripts\python.exe -m pytest tests/integration/test_integrated_migrations.py tests/unit/test_database_config.py -q
# Linked business coverage inherited from the accepted branch commits:
.\.venv\Scripts\python.exe -m pytest tests/integration/test_auth_combined_acceptance.py tests/integration/test_import_planning_a3.py tests/integration/test_import_history_a2.py -q
# New linked Owner grants / Staff Import / live revoke coverage:
.\.venv\Scripts\python.exe -m pytest tests/integration/test_integrated_auth_import.py -q --tb=short --show-capture=no
# Full integration milestone gate (run once; failures rerun by affected selectors):
.\.venv\Scripts\python.exe -m pytest -q --tb=short --show-capture=no --junitxml=runtime/integration/full-suite.xml
```

Migration0024 merges0021/0023. Both original v3 upgrades are safe in either order.
Integration-only repairs of the two unreleased downgrades walk applied ancestry,
retain v3 while the companion needs it and guard the last removal against retained
six-key grants. A2 history retention remains independent. Historical v1.0 is untouched;
no stamp or deleting grants/data to force downgrade. Both branch-head upgrades and
partial/final rollback/ORM-default parity pass new6-case traversal coverage.
Schema/model tests retain exact inventory/constraint checks. Standalone branch
catalogue retention tests now explicitly apply that branch without companion v3;
integration tests separately prove the changed companion-preservation behavior.

Verification results: initial traversal/guard gate28 passed; schema/tooling gate
232 passed/4 failed (236 cases). Four stale head/inventory expectations were repaired;
5 affected checks passed, including fresh-process RESET delivery. These overlapping
runs are not added as a unique total. The first full milestone invocation was
interrupted after the last observed progress at70%, with failures but no terminal
summary/XML. It is NOT a completed full-suite result. This lost failure evidence
requires a replacement milestone gate; its ignored runner flushes each test outcome
and redacts database credentials so interruption cannot lose completed-case evidence.
The replacement wrapper then exposed a Windows-spawn harness bug: without its
__main__ guard the PDF child launched nested pytest. Only the698 reports before
that case are valid (690 passed/8 failed); later reports are invalid, preserved
outside Git, and do not count as backend failures or passes. Only this task's runner
process tree was stopped. The corrected guarded runner selects1584 remaining,
failed or affected cases and deselects679 already-passing cases; its selection is
in ignored runtime/integration/remaining-selection.json. Six newly collected cases
cover public Staff history grants and exact signed projection deltas. This is a
resumed/targeted gate, NOT a completed single-invocation full-suite pass. It completed
with1575 passed/9 failed, no skips (1584 selected; 1786.278 seconds). Failures exposed
stale source-proof/stockout/basis fixtures, the new fake-delivery callback assertion,
and a direct SQL query outside the repository boundary. The scoped max-version query
was moved into the existing ImportHistoryRepository, retaining the caller's Session
and transaction. Affected selectors plus the whole architecture/bounds/history modules
then yielded72 passed/3 failed (75 cases; 186.824 seconds). The last three failures
were the new linked flow's expectation after live write revocation: approved runtime
already rejects confirm_review with403 PERMISSION_DENIED. Corrected assertions passed
all3 cases (29.223 seconds), preserving checks for exact grants, fresh committed
history and accept replay never restoring revoked grants. Signed
quantity delta regression cases passed in the resumed gate. Overlapping counts are
never added; no completed single-invocation full-suite pass is claimed.

Final affected commands (sequential, same owned DB; no full gate repeat):

```powershell
.\.venv\Scripts\python.exe -m pytest tests/integration/test_import_recipe_basis.py::test_source_basis_reuse_reads_current_rows_and_unit_change_blocks tests/integration/test_import_staging.py::test_missing_zero_duplicates_and_future_rows_are_blockers tests/integration/test_integrated_auth_import.py tests/integration/test_recipe_schedule.py::test_import_recipe_and_editor_share_real_pg_fence_and_version_allocation tests/integration/test_s47_audit_remediation.py::test_sales_correction_http_requires_effective_action_reason_before_acceptance tests/unit/test_application_contracts.py tests/unit/test_s47_bounds_reason.py tests/integration/test_import_history_a2.py -q --tb=short --show-capture=no --junitxml=runtime/integration/final-targeted.xml
.\.venv\Scripts\python.exe -m pytest tests/integration/test_integrated_auth_import.py -q --tb=short --show-capture=no --junitxml=runtime/integration/auth-import-final.xml
```

Ignored XML/logs are development evidence, not application audit or portable handoff
artifacts. The three-case linked coverage spans calendar, usage and purchase history;
it complements the accepted Auth B4/Import A3 flows and does not replace browser E2E.
Final status confirms effective shelfcash_integration_test/shelfcash_integration_tester,
head0024,65 tables and zero application rows after fixture teardown; no additional
reset was needed. Role superuser/CREATEDB/CREATEROLE/replication flags are all false.
OpenAPI source-manifest parity, JSON references, handoff links/anchors, Python compile
and Git whitespace checks pass. The15 original Import WIP hashes remain unchanged
and the Auth source worktree remains clean.

Original15 Import WIP review (source WIP untouched):

| File | Integration disposition |
| --- | --- |
| scripts/probe_decision_test_database.py | Superseded: identical guarded-target adaptation already committed by Auth; receives expanded shared allowlist |
| scripts/verify_forecast_execution.py | Superseded: same Auth adaptation; tested process caller uses integration target |
| scripts/verify_forecast_trained.py | Superseded: same Auth adaptation, exact retained/artifact replay retained |
| scripts/verify_s362_acceptance.py | Superseded: same Auth adaptation; integration guard retained |
| tests/integration/test_catalog_recipe_schema.py | Receive effective-identity intent from Auth; adapt exact integrated table inventory/head |
| tests/integration/test_database_bootstrap.py | Same identity adaptation; preserve exact tables and check head0024 |
| tests/integration/test_forecast_decision_persistence.py | Same identity adaptation;65-table head inventory, later-table downgrade exclusions include both branches |
| tests/integration/test_identity_store_schema.py | Same identity adaptation; exact65-table inventory/head0024 |
| tests/integration/test_operational_import_schema.py | Same identity adaptation; include A2 history in later-table roundtrip scope |
| tests/integration/test_planning_configuration_schema.py | Same identity adaptation; include both branches in roundtrip exclusions/head0024 |
| tests/integration/test_planning_export_schema.py | Same identity adaptation; integrated schema/head0024 |
| tests/integration/test_public_reads.py | Superseded: identical guarded identity/lock-monitor adaptation already in Auth |
| tests/integration/test_recipe_schedule_schema.py | Same identity adaptation; preserve period/column constraints, integrated inventory/head0024 |
| tests/integration/test_supplier_operational_constraints.py | Same identity adaptation; exact inventory and exclusion constraints/head0024 |
| tests/integration/test_verification_commands.py | Same effective identity and process environment intent; exact65-table status/seed/no-row expectations/head0024 |

No WIP business implementation is imported. Old Import-only inventories/0017
expectations are superseded, not copied over Auth metadata. Other shared repairs:
API Import's54-op assertion recognizes the five accepted Auth operations; Auth/RESET
child recovery verifies the fixture's guarded identity instead of hardcoded Auth DB.
No test is deleted/skipped to obtain pass. Legacy reuse tests now declare this
upload's source/report before preview, preserve atomicity/stale-read/confirmation
assertions and test the provider boundary only after source proof. Sales tests use
explicit missing-stockout policy and A1 contribution-level raw zero/overlap semantics.
Integration repairs one projection regression: regrouping sales had discarded the
existing changes.quantity.delta. Exact Fraction arithmetic restores it, without
changing writer totals/replace/merge decisions; signed/high-precision checks cover it.

[FE010/artifacts](../handoff/010_BE_CAPABILITY_RESPONSE_VI.md) owns FE handoff. OpenAPI
is source-only, examples synthetic validated DTOs. Unified server not started; no
ready base URL, browser/real workflow-email E2E or deployment claim. Existing Gmail
smoke/inbox receipt is historical and does not cover credential workflow.

## Phạm vi và chuẩn bị

**CURRENT FACT:** một backend Python/FastAPI với các thread Import, Planning và
PDF bật độc lập. Worker là phần xử lý job nền; ba flags mặc định OFF, demo bật
chúng trong private settings. Không cần provider trả phí hoặc kích hoạt mô hình
đã huấn luyện. Startup không migrate/reset/seed/call provider.

Cài Python3.11+, Docker Desktop với Linux containers và Docker Compose. Để chạy
FE cần Node>=22.22 và repo `Shelfcash_FE_v2` nằm cạnh `backend`. Microsoft Edge
chỉ cần cho browser harness tự động. Mở Docker Desktop trước khi dùng DB.

Mọi lệnh dưới đây chạy trong PowerShell tại **backend**, trừ đoạn có Push-Location:

```powershell
Set-Location D:\hocc_bk\ai\proj\projectMLAI\backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[dev]'
```

Nếu `.venv` đã có thì dùng lại. Không cần activate; gọi thẳng python trong venv.

| Môi trường | DB | BE | FE | Dữ liệu |
| --- | --- | --- | --- | --- |
| Development | shelfcash,5432 | 8000 | tùy cấu hình | dữ liệu của developer, không reset/migrate trong test release |
| Automated tests | shelfcash_test, local | TestClient/process theo test | không cần FE | fixtures riêng, được tests reset có guard |
| Demo S4.11 | shelfcash_integration_s411,5433 | 18001 | 5173 | synthetic riêng, có marker sở hữu/Store allowlist |

Store là quán; Owner là chủ quán; Staff là nhân viên. Quyền product không bao gồm
quyền reset/seed/admin DB. Không dùng dữ liệu khách thật trong profile demo.


ACCEPTED DECISION (explicit user authorization): different owned test DBs may run
in parallel; this extends ADR-007's original sequential test workflow only across
isolated DBs. No change to persistence or transaction architecture.

CURRENT FACT: parallel Auth/Import worktrees use one existing local PostgreSQL
instance on 127.0.0.1:5432. Import owns `shelfcash_import_test` (role
`shelfcash_import_tester`); Auth owns `shelfcash_auth_test` (role
`shelfcash_auth_tester`). Each ignored `.env` supplies its TEST_DATABASE_URL;
process environment overrides `.env`, so verify the effective target before writes.
Dedicated roles have no superuser/CREATEDB/CREATEROLE rights and own only their DB.
Local pg_hba rules restrict these roles to their corresponding database.
Tests/reset are sequential within each DB; different owned DBs may run in parallel.
Legacy `shelfcash_test` remains supported. Stop both clients before setup changes;
do not start another Compose on port5432 or touch shared/development DBs.

Run from the intended worktree (no credentials in commands):
```powershell
.\.venv\Scripts\python.exe -m scripts.dev status --test-database
.\.venv\Scripts\python.exe -m scripts.dev reset --test-database
# PowerShell wrapper: .\scripts\reset_db.ps1 -TestDatabase
.\.venv\Scripts\python.exe -m pytest tests/unit/test_database_config.py
```
Status prints actual database/current_user and this tree's migration heads.
Reset explicitly selects effective TEST_DATABASE_URL, validates the allowlist,
checks connected identity, and migrates only that tree's head. Bare reset still
uses DATABASE_URL: use --test-database for worktree test setup. Never print URLs.
Historical isolated-source setup: Auth0023 descends from0022/0020/0018/0017;
Import0021 descends from0019/0017. Integration0024 explicitly joins these heads
only in the integration worktree. Source tree DBs retain their separate graphs.

### B4 Auth/Staff acceptance without FE or SMTP

Run in backend-auth-self-service. Confirm status reports only shelfcash_auth_test /
shelfcash_auth_tester before tests. These fixtures reset that guarded database;
run one pytest process at a time and leave Gmail demo/Import/development untouched.

```powershell
.\.venv\Scripts\python.exe -m scripts.dev status --test-database
.\.venv\Scripts\python.exe -m pytest tests/integration/test_auth_combined_acceptance.py tests/integration/test_auth_catalogue_v3_schema.py tests/unit/test_auth_catalogue_v3.py tests/api/test_staff_openapi.py -q
```

Combined HTTP cases capture fake verification/invitation/reset mail; provision
synthetic Owner Stores through AssistedProvisioning, not public signup. They verify
registered/unregistered invitees, exact grants, live changes on existing sessions,
two-Store isolation, decline/new invitation, receipt replay after grant revocation,
and reset/session revocation through fresh-session reads. The schema test checks
additive preservation, downgrade retention and pending delivery in a fresh process.
Public membership deactivation is not implemented; the test exercises the existing
persisted membership boundary and does not invent a new endpoint.

| Invariant / existing coverage to reuse | Responsible test module |
| --- | --- |
| Signup enumeration, expiry/reissue/single-use, rollback/lost acknowledgment, rates, service-wide unavailable, restart/bounded delivery | test_email_verification.py |
| RESET lifecycle/purpose/session revocation, rollback/lost acknowledgment, bounded claims and process restart | test_password_reset.py |
| Session/proof/current grants, assisted setup, cookie/Origin/CSRF and logout | test_auth_public.py; test_self_service_auth.py |
| Accept/reissue/revoke, no ghost access, pinned catalogue, grant CAS, replay, delivery uncertainty and locking | test_staff_public.py |
| Decline fences/replay, accept/decline/revoke races, rollback/lost acknowledgment, N16/N18 terminal reads | test_invitation_decline.py |

Select affected nodes when changing these boundaries; do not rerun every module
just to total cases. Existing evidence is reusable coverage, not a new full-suite
pass. Browser and real credential-email workflow acceptance remain pending; one
user-confirmed Gmail smoke inbox delivery proves only that smoke message.

## 1. Thiết lập demo mới — chỉ thực hiện một lần

Nếu đã có `runtime/s411/private/settings.json` và demo data thì sang mục2.
Init sinh cấu hình/bí mật riêng trong runtime bị Git ignore; không sửa root `.env`
để cấu hình launcher. Các lệnh này chỉ migrate DB demo có đúng guard, không DB
development. Không reset môi trường đang có dữ liệu để chạy lại.

```powershell
.\.venv\Scripts\python.exe -m scripts.integration init
docker compose --env-file runtime/s411/private/compose.env -f compose.integration.yaml up -d --wait
.\.venv\Scripts\python.exe -m scripts.integration migrate
.\.venv\Scripts\python.exe -m scripts.integration status
.\.venv\Scripts\python.exe -m scripts.integration start
.\.venv\Scripts\python.exe -m scripts.integration seed
```

Đúng target: role `shelfcash_integration`, host127.0.0.1:5433,
DB `shelfcash_integration_s411`, Compose project `shelfcash-integration-s411`,
named volume `integration-s411-data`. Guard chặn provider key/model live.

Seed demo là workflow riêng: application provisioning có audit → giao credential
qua kênh holder local → N7 hoàn tất mật khẩu; Owner mời Staff → Staff đăng nhập
và nhận lời. Không tự đăng ký Owner qua FE, không SQL cấp quyền/mật khẩu chung,
không SMTP thật. Demo có5 Products,1 Ingredient theo dõi hạn dùng,5 recipes,
70 sales có zero, supplier/term/NONE-fee evidence, completeness declarations,
hai opening lots gồm stock hết hạn. BASELINE/DEFAULT_BASE95 và budget1.000.000VND
là lựa chọn fixture, không mặc định nghiệp vụ. Staff ban đầu chỉ `menu.read`;
Owner/Store thứ hai kiểm chứng isolation. Seed không phải bước startup.

Cài dependencies FE nếu chưa có; đây là cài đặt local, không sửa source FE:

```powershell
Push-Location ..\Shelfcash_FE_v2
try { npm ci --no-audit --no-fund } finally { Pop-Location }
```

## 2. Khởi động/reuse để thao tác trên browser

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/local-integration.ps1 docker
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/local-integration.ps1 status
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/local-integration.ps1 start
```

Mở **http://localhost:5173/login**. BE health là
`http://localhost:18001/health`; schema là `/openapi.json` (`/docs` và `/redoc` tắt).
Health200 chỉ chứng minh process sống. Launcher kiểm DB head/sở hữu process và
port; reuse FE/BE thuộc launcher, không đổi port hoặc kill process khác.

Private config ở `runtime/s411/private/settings.json`; tài khoản ở `accounts.json`,
dataset/Store ở `dataset.json`. Mở bằng editor riêng, không cat credentials ra
log/chat, không đưa vào VITE/localStorage/Git. Config được load bằng
`Settings(_env_file=None)`, root `.env` không tác động launcher.

FE dùng `VITE_DATA_SOURCE=api`, `VITE_API_BASE_URL=http://localhost:18001`;
không thêm `/api/v1` vào base URL vì paths đã có. FE/BE cùng dùng localhost,
Origin đúng `http://localhost:5173`, requests có credentials include. Sau login
dùng CSRF hiện hành; mutation thêm key/CAS theo từng route. Cookie local
`shelfcash_dev_session` là HttpOnly/SameSite=lax, chỉ loopback; production giữ
Secure `__Host-shelfcash_session`.

**FE đang chạy thủ công:** kiểm trang login và Network trong browser; nếu API base
URL/mode/Origin đúng thì dùng lại. Không gọi launcher `start` cho FE không có
ownership metadata: nó sẽ từ chối port5173 đang bị process khác giữ. Chỉ bật BE:

```powershell
.\.venv\Scripts\python.exe -m scripts.integration status
# Chỉ khi BE18001 chưa chạy và không có ownership conflict:
.\.venv\Scripts\python.exe -m scripts.integration start
```

Nếu FE sai mode/base URL, dừng bằng Ctrl+C tại terminal đã chạy FE của bạn rồi
khởi động lại trong repo FE với hai VITE variables trên; không kill theo port.

Import/Planning/PDF workers đã chạy trong lifespan BE demo; không chạy thêm worker
trên cùng DB. Dispatcher lời mời không cần cho demo Owner hoặc local seed.
`scripts.dispatch_invitations` là tác vụ SMTP riêng, cần cấu hình delivery/HTTPS
và operator credential; không chạy để thử mapping hay gửi thư thật trong flow này.

## 3. Test như khách hàng trên browser

1. Login bằng Owner demo → chọn đúng Store. Nếu nhiều Store, FE phải cho chọn;
   Staff chỉ xem/thao tác theo grants hiện hành. Login200 không chứng minh có
   quyền import hoặc planning.
2. Vào Import, chọn business context date và files → upload → Analyze. Chờ job
   analysis xong; kiểm file đã nhận, file rejected và acknowledgment trước seal.
   Upload không ghi Menu/Sales/Kho.
3. Review từng sheet: loại dữ liệu, headers, field options, source context và
   identity. Unknown không tự IGNORE. Sheet không hỗ trợ phải được quyết định
   rõ với reason/ack; không map receipt thành kiểm kê lô. Lần đầu cần Owner duyệt
   toàn profile. Profile reuse vẫn không thay confirmation của batch.

   CURRENT FACT trên nhánh import sau tag v1.0: Owner đọc toàn spec và mappings,
   có thể duyệt nhóm RULE đủ điều kiện bằng N5 mà không xác nhận riêng từng cột.
   M01 `include_profile_details=true`, M02 `review_only=false` cho xem đầy đủ;
   candidates/reason/header_row/preamble_samples hỗ trợ review. Cột mơ hồ, ngoài
   schema và required facts thiếu vẫn phải xử lý trước. FE chưa được sửa/kiểm chứng
   cho cách duyệt nhóm này; nếu UI vẫn buộc từng cột, dùng workflow hiện hành hoặc
   các API trên theo [Import contract](../IMPORT_MAPPING_API_CONTRACT_VI.md).

   Số items review không phải số cột nghiệp vụ bắt buộc: còn classification,
   source context, identity và conversion issues. M03 mô tả requiredness theo
   từng schema; required-nullable vẫn cần giá trị/null rõ, không tự bỏ field.
   Chỉ IGNORE cột không dùng sau khi đọc ý nghĩa/evidence; business rule chưa hỗ
   trợ không trở thành optional chỉ vì không có target.
4. Preview → xem blockers/warnings/NEW/UNCHANGED/CHANGED/CONFLICT, giá trị trước/sau
   và các nhóm cần quyền ghi. Sửa mapping/context thì preview cũ mất hiệu lực.
   Thiếu fact thì bổ sung evidence đúng nghĩa, không nhập0/ngày upload để xanh.
5. Xác nhận review → Commit → chờ job terminal → đọc completion và refetch các
   màn hình liên quan. Preview/save/HTTP202 không chứng minh dữ liệu đã commit.
   Commit atomic: có blocker hoặc thiếu quyền một nhóm thì không ghi cả batch.
6. Readiness: xem từng thiếu sót; cấu hình requirements/budget theo phiên bản.
   Chọn Planning default/custom/saved → chạy → chờ đúng run_id hoàn tất. Không
   tự train, không stock depletion hay đặt hàng sau import/planning.
7. Xem phương án, winner, chi tiết nguyên liệu/lý do. Completed không có winner
   đủ điều kiện vẫn là kết quả hợp lệ; outcome/proof/search khác status. Lịch sử
   giữ input/result đã capture, thay stock/recipe hiện tại không sửa Run cũ.
8. Nếu UI có chức năng tương ứng, xem lịch sử và xuất PDF. API hỗ trợ N9/H01/H02,
   N10 yêu cầu PDF tiếng Việt, J01 polling, N11 tải riêng tư kiểm SHA/size/quyền
   hiện hành. PDF/lịch sử Planning UI còn thiếu; không coi API pass là UI pass.
   Export/view không lưu lựa chọn khách hàng và không tạo đơn mua.

**Giới hạn kiểm chứng:** người dùng đã thử FE thật tới mapping lần đầu; chưa có
bằng chứng toàn browser flow import → Planning thành công. S4.11 vẫn PARTIAL.
Rules v1.0 chỉ canonical keys/aliases hiện hành, chưa bao phủ headers demo. Adapter
OpenRouter tùy chọn đã có; manual/profile/rules hoạt động không cần provider.

Để kiểm API/native workers và committed state qua fresh SQLAlchemy Session trên
demo owned, các lệnh sau ghi thêm dữ liệu synthetic/output; chúng không phải
browser acceptance hoặc startup, không chạy trên developer/customer DB:

```powershell
.\.venv\Scripts\python.exe -m scripts.integration e2e
.\.venv\Scripts\python.exe -m scripts.integration cases
.\.venv\Scripts\python.exe -m scripts.integration restart-check
```

`e2e` kiểm import/readiness/planning/history/PDF, `cases` kiểm quota/ACK/CAS/seal/
profile/values/replay/current rights. `restart-check` so cookie/Run/PDF trước/sau
restart thuộc ownership. Upload bytes ở PostgreSQL import_blobs; PDF bytes riêng
tư ở app runtime còn được receipts/jobs tham chiếu, không purge như cache.

## 4. Dừng đúng process

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/local-integration.ps1 stop
# Khởi động lại process thuộc launcher nếu cần:
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/local-integration.ps1 restart
```

Stop chỉ dừng FE/BE có đúng incarnation/command metadata; Docker và volume còn.
FE thủ công dùng Ctrl+C tại terminal của bạn; BE khởi động riêng dùng
`python -m scripts.integration stop` với python trong venv. Không chạy launcher
stop khi5173 thuộc FE khác. Sau crash, `recover-stopped` yêu cầu process cũ được OS
xác nhận DEAD, port free và đúng DB/Store guards; ALIVE/UNKNOWN chặn, không sửa DB.

## 5. Automated tests — khác thao tác browser và seed

Chạy từ backend. `.env` có thể được tạo từ `.env.example` nếu chưa có; chỉ
cấu hình TEST_DATABASE_URL trỏ PostgreSQL local **shelfcash_test** cho profile cũ;
profile tích hợp dùng DB/role riêng ở mục integrated-acceptance. Không in URL có
password. Guard từ chối DB ngoài explicit allowlist. Tests chạy tuần tự, reset/migrate fixtures chỉ DB
test; không migrate/reset development. Docker development service chỉ cung cấp
PostgreSQL, không cần upgrade schema shelfcash để chạy tests:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker compose up -d --wait --wait-timeout 90 postgres
.\scripts\test.ps1 unit
.\scripts\test.ps1 api
.\scripts\test.ps1 integration
# Full suite tại mốc release/tích hợp lớn:
.\scripts\test.ps1 all
.\.venv\Scripts\python.exe -m scripts.integration_contract_snapshot
```

Chọn targeted tests cho slice nhỏ theo AGENTS; không cộng các lần chạy overlap
thành tổng test độc lập. Full suite cho release chứa thay đổi rộng schema/quyền/
transaction. Quan sát commands/results trong hội thoại, không dùng PASS lịch sử.
OpenAPI check giữ fixture original10/10 `tests/fixtures/openapi_20261010.json`,
pinned SHA/provenance ở compatibility changelog; output runtime/verification/openapi.
Baseline32 →54 operations (22 thêm,6 đổi I01-I05/M04, không bỏ) là inventory của
v1.0, không chứng minh toàn UI. DTO examples ở docs/features/examples là synthetic.

Browser harness tự động (không mocks/interception) cần demo owned đang chạy:

```powershell
npm ci --prefix scripts/browser --no-audit --no-fund
node --check scripts/integration_browser.mjs
node scripts/integration_browser.mjs
```

Manifest/lock ở scripts/browser; node_modules/reports/screenshots bị ignore.
Resume flags cần cùng dataset và prior report, không dùng sau reset.

## 6. Development mới, lỗi thường gặp và reset

Chỉ khi chủ động thiết lập DB development mới: cấu hình root `.env` theo
`.env.example`, chạy Docker như mục5, `scripts/db_status.ps1 -AllowUnmigrated`,
`alembic.exe upgrade head` trong venv, rồi `scripts/db_status.ps1`. BE chạy bằng
python venv `-m uvicorn app.main:app --host 127.0.0.1 --port 8000`. Worker flags
cần bật rõ nếu thực hiện jobs; `seed_demo` chỉ kiểm schema, không tạo dataset.
Schema Auth source head0023/63 bảng ứng dụng; health không xác nhận DB. Volume development
`shelfcash-postgres-data` giữ qua restart; đổi Compose password không đổi role
password trong volume đã init. POSIX wrappers tồn tại nhưng runtime chưa certified.

| Dấu hiệu | Xử lý |
| --- | --- |
| Docker API unavailable | Mở Docker Desktop, chờ engine Linux sẵn sàng, kiểm docker ps |
| DB không đúng head | Kiểm target/config trước; chỉ upgrade target đã chủ động chọn, không reset development |
| Port/PID ownership conflict | Dùng process hiện có nếu đúng config; không kill/đổi port tùy tiện |
| CORS/login không giữ cookie | localhost cả FE/BE, đúng Origin5173, credentials include, không thêm /api/v1 vào base URL |
| Staff403 | Refresh quyền, Owner cấp đúng grants; không bypass bằng key/membership giả |
| Signup/resend503 EMAIL_DELIVERY_UNAVAILABLE | Kiểm opt-in/TLS SMTP/key/HTTPS verification-page Origin theo [Auth feature](../features/AUTH_SESSION.md); không chờ email hoặc tạo Store từ response này |
| Job queued mãi | Kiểm worker flags/private log và native lifespan; không chạy worker thứ hai trên cùng DB |
| Mapping/preview bị stale | Refresh revision, review lại thay đổi, preview lại; không reuse confirmation cũ |
| Readiness bị chặn | Xem missing/unknown/ambiguous facts và evidence, không bịa unit/date/MOQ/fee |

Reset là hành động phá dữ liệu riêng, không thuộc startup/release. Local reset
wrappers chỉ cho development shelfcash hoặc các DB test trong explicit allowlist;
test mode từ chối shelfcash. Lượt tích hợp chỉ dùng shelfcash_integration_test với
role riêng đã guard, không dùng các targets còn lại dù tooling hỗ trợ. Dừng
clients, backup dữ liệu muốn giữ trước; không xóa volume/kill arbitrary sessions.
S4.11 reset-disposable cần đúng marker/Store allowlist/matched server exit/no
clients; không có Store-only reset. Giữ private artifact generations, audit,
provenance, models và retained PDF theo chính sách retention đã được duyệt.

## 7. Kiểm synthetic engine không cần DB/provider

Inputs/oracles nằm trong source/fixtures, outputs ở ignored runtime/verification.
Timing native không chứng minh chất lượng forecast hay exact infeasibility:

```powershell
.\.venv\Scripts\python.exe -B -m scripts.review_planning_verification
.\.venv\Scripts\python.exe -B -m scripts.benchmark_procurement_v2
.\.venv\Scripts\python.exe -B -m scripts.verify_procurement_v2_benchmark
.\.venv\Scripts\python.exe -B -m scripts.benchmark_decision_pipeline_v2
.\.venv\Scripts\python.exe -B -m scripts.benchmark_planning_setup
```

`review_planning_verification --benchmark-directory <directory>` kiểm thêm typed
results từ planning_setup mới chạy. Không ZIP/handoff bundlers. Semantics ở
[API](../API_CONTRACT.md), [Import](../IMPORT_MAPPING_API_CONTRACT_VI.md),
[Authorization](../AUTHORIZATION_CONTRACT_VI.md), [Planning](../PROCUREMENT_API_CONTRACT_VI.md);
[CURRENT_STATE](../CURRENT_STATE.md) tách runtime facts khỏi proposals.
