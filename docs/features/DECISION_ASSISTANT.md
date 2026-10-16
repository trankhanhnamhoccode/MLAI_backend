# Decision Assistant evidence foundation

## CURRENT FACT - L5 backend integration scope

Local integration base8b09685 preserves forecast metadata2/schema3, offer admission
and reused quantity TypeAdapter. Assistant checkpoint1f9b5c5 preserves L4.1 history.
No Assistant business/presentation semantics change in L5: V6 default, candidate8
explicit trial only, independent summary/chat provider flags OFF. No operator-facing
version selector. Accepted ADR-001/004/007/011/020-022 intent remains unchanged.
The single additive merge revision l5_20261016_assistant_f4 joins the two applied
heads without rewriting either; old generations/receipts keep their pinned versions.

Combined-source PostgreSQL fake-provider acceptance covers durable summary/chat,
current authority, concurrency, lost ACK, actual child-process death/recovery,
terminal/stale writer fences, cold process reads and V6/7/8 replay. Engine-created
20g/35g, failed/partial and mixed-path Runs are retained through existing L4.1 tests.
New host acceptance runs real baseline Planning worker before cold summary/chat V6.
New compatibility fixture copies original synthetic F4 input/output/pin verbatim
with source SHA, validates schema3 and metadata2, executes host capture/Planning
against new explicit synthetic operations, then reads Assistant with forecast/native
search/network forbidden. It does not execute challenger inference or read artifacts.
Canonical ForecastRun input/metadata/predictions and Assistant rows survive merge
revision traversal; populated parent downgrades reject evidence loss. Fixtures are
technical correctness evidence, not new native runtime, real-data or accuracy proof.

Public OpenAPI adds only AS01/AS02/AS03,73->76 operations/66->69 paths; every old
operation and component schema compares equal to premerge main. C08/PDF remain
separate retained consumers; their ordinary cold semantic replay debt remains.
See [handoff](../handoff/010_BE_CAPABILITY_RESPONSE_VI.md) and [Planning18](../PROCUREMENT_API_CONTRACT_VI.md#decision-assistant)
for exact workflows/examples; [runbook](../runbooks/FULL_TEST_FLOW.md#assistant-l5)
owns setup/commands and verification results. Browser/deployment E2E and new live
acceptance of combined source remain PENDING. No provider call, default promotion,
what-if, ordering, model reviewer, Import/forecast activation or FE change in L5.

CURRENT FACT L2/L3: immutable `decision_evidence/1`, durable cold consistency reads,
typed deterministic summary, optional bounded model presentation and AS01/AS02
durable PostgreSQL lifecycle and AS03 optional conversational prose are implemented.
Focused offline/owned-DB verification and an explicitly authorized synthetic Gemini
summary smoke are separate evidence. No new grant or deployment.
The [Planning contract §18](../PROCUREMENT_API_CONTRACT_VI.md#decision-assistant)
owns current summary/chat requests/responses/errors/lifecycle. Existing C08 remains the
structured explanation in §15.3. ADR-001/004/011/020–022 govern retained authority.

## CURRENT FACT — S1 bounded plan narrative

S1 composition selected `summary_profile/2`; S2 selected `summary_profile/4`;
current S3 composition selects `/6` as described below. SUMMARY_LLM_ENABLED remains OFF.
AS01/AS02 reuse the existing durable lifecycle, current rights, exact retained
evidence and receipts. Profile/1 still reads and renders its original six-family
deterministic/presentation output. Profile/2 uses prompt `plan_summary_prompt/2`,
internal schema `summary_narrative/2`, renderer `plan_summary_renderer/2` and
validator `summary_narrative_guard/2`. These pins participate in generation identity;
an old key replays its old result even after settings change. No migration is needed.

BE `communication_plan` selects outcome/recommendation, viewed-option identity and
exact costs/budget, per-Product/path assessment counts, computed/excluded scope,
retained forecast horizon when present, search/proof and relevant limitations.
Failed retained winners remain diagnostic; no eligible candidate, blocked
computation and execution error have different messages. Incomplete/unproven
search is a separate proof statement, never an infeasibility conclusion. Empty
retained purchases mean no additional purchase, not no plan. Missing option costs
are unavailable, not zero. Unknown fee coverage differs from retained payable fees
whose delivery classification is unavailable. Nonterminating money displays as
an exact fraction; no quantity totals across units or invented daily demand.

Provider input is task/language/detail_level/instruction plus selected fact IDs,
families, issued evidence IDs and licensed complete clause surfaces. No raw
package, source text, captured entity names, question/history or operational data
outside these selected facts is sent. Output is `{schema_version,headline,summary,
key_points,warning_summary}`: each section has family and clauses containing
`{fact_id,text,evidence_ids}`. Headline maps to outcome, summary to cost, three
supporting points to requirements/coverage/proof, warning_summary to limitations.
The model returns the text and bindings. This is bounded narrative wording,
with licensed sentence variants and within-family composition, rather than the
old ordering/tone schema. It is deliberately **not unrestricted prose**: a correct
paraphrase outside this vocabulary falls back. It does not claim general entailment
or demonstrated Gemini language quality.

The summary-specific validator matches each entire clause to its selected semantic
fact, family and exact references, requires every material fact once, and rejects
extra/repeated/misplaced clauses. Matching numbers or existing evidence IDs alone
never suffices. Wrong winner/entity/currency/amount/units, polarity, scope, proof,
actual-versus-simulated meaning or unsupported causes cannot pass. No substring
repair, grammar inherited from chat, model reviewer, regeneration or business
recomputation is used. All new-mode failures render the complete deterministic
profile/2 plan; no long universal disclaimer is forced beyond the short simulation
boundary and applicable retained limitations.

Public SummaryAnswer keeps schema_version `plan_summary/1`, its existing fields
and six claims. Internal sections are flattened to those families; FE can display
`answer`, `claims[].text/evidence_ids`, `references`, existing source and diagnostics.
The historical wire value `model_presentation` also denotes accepted profile/2
narrative; distinguish it using renderer/prompt/validator versions. The only public
schema delta is additive enum values in those three existing version fields. No
new public DTO fields or endpoint. Older results keep their original version labels.
Fresh reads reconstruct clause bindings and reconcile the full retained answer
against its pinned plan; GET and replay never call a provider. Current authorization
is repeated immediately before provider dispatch, publication and delivery; provider
work holds no Session. Lost-ACK/fencing/process recovery retain the original policy.

HISTORICAL INFORMATION / reference only: the user supplied the newly placed
`backend/shelfcash_legacy_review.zip`, archive SHA256
`8c58050723d2b9dc7837859679ee9a65c758482a17e5475496bf33f9ad272a9a`.
Its WORKTREE_STATUS identifies clean main `cac7c5a6a46c5751063be6b27866e3672acd2e2a`,
collected 2026-10-07. Eight selected summary/communication/style/narrative/test/status
entries were verified against MANIFEST hashes. It arrived without the `(5)` suffix;
that filename alone is not an identity claim. Only communication priorities and
provenance distinctions informed S1; no adapter/registry/engine/guard pipeline was
ported. In particular, its no-recommendation → infeasible wording is not adopted.

S1 is offline/fake-provider evidence only. S2 model configuration and pending live
acceptance are in the [runbook](../runbooks/FULL_TEST_FLOW.md#summary-narrative-s1).

## CURRENT FACT — S2 Gemini acceptance and limits

S1 checkpoint `93d6ecb` is OFFLINE VERIFIED; its old generation formats remain
supported. HISTORICAL INFORMATION: S2 checkpoint `070a721` uses summary_profile/4, prompt
plan_summary_prompt/3, internal schema summary_narrative/3, unchanged renderer
plan_summary_renderer/2 and unchanged summary_narrative_guard/2. Profile/3 pins
reasoning disabled while preserving the old nested schema; profile/4 also uses
compact output. Original profiles/1 and /2 keep their prior transport and pins.

Google rejected the nested S1 provider schema with a too-many-states error.
The new wire grammar is one flat clauses array of `{fact_id,text}`; provider
schema omits nested length constraints. Local CompactNarrative still enforces
bounds, and BE binds each fact to its issued references before the same full
clause/family/coverage reconciliation. Unknown IDs, missing obligations, altered
amounts/entities/units/polarity or unlicensed assertions still fail. This reduces
provider grammar complexity and output tokens without accepting weaker claims.
The model sees selected fact IDs, families and licensed surfaces; references
remain backend-owned. Public fields are unchanged; prompt_version additionally
admits plan_summary_prompt/3. No endpoint, permission, migration or engine change.

CURRENT FACT: the six-case persisted synthetic A?F matrix was evaluated through
real AS01/auth/CSRF/application validation with Gemini 2.5 Flash via pinned Google,
no provider fallback, price ceiling and 1,200-token output cap. On the final source,
A/B/C/D/F were accepted. E omitted the required reference-only fact; the full
correct deterministic fallback was published. This is a model coverage failure,
not an observed false rejection. Two earlier HTTP400 attempts remain separately
recorded, with unknown costs still reserved; no retry on an unchanged error.
Raw/final/source/validation/cost evidence and the requested CASE_REVIEW.md are
under ignored runtime/s2-summary. No live result is relabelled as a later source.

Codex grading finds factual/status/proof boundaries supported on these fixtures;
naturalness/usefulness are limited by licensed sentences, technical proof wording,
slash-joined strategy aliases and counts that do not replace Product-level detail.
In blocked Runs, “phạm vi đã tính” describes retained computed input scope and can
be misread as successful completion; the outcome must remain visible alongside it.
The correct out-of-vocabulary cost paraphrase probe is rejected offline. The live
prompt asks for licensed clauses, so five accepted cases do not establish free
paraphrase acceptance. Grading is by Codex, not independent human review.

Recommendation: GO WITH LIMITS for a bounded S3 trial showing current status,
claims/references and fallback diagnostics; unrestricted prose, final owner-facing
UX acceptance and production readiness remain unverified. No S3 action or live
runtime activation follows automatically. Providers remain OFF by default; Chat,
Import and forecast configuration are unchanged. See the
[runbook](../runbooks/FULL_TEST_FLOW.md#summary-narrative-s1) for exact opt-in,
budget/target guards and reproducible offline/live checks.

<a id="current-fact--s21-owner-summary-selection"></a>
## CURRENT FACT — bounded owner summary

Application composition selects `summary_profile/6`, `owner_summary_selection/2`,
`plan_summary_prompt/5`, compact `summary_narrative/3`, renderer/4 and
`summary_owner_guard/4`. No env selector, worker, engine, migration, permission,
route or public field is added. Existing version enums are extended. Historical
profiles/1–5 keep original implementations, selected facts, text and exact replay.

BE selects required/optional/detail-only facts. Model input has only selected
required/optional examples and typed money slots, status/outcome/winner/viewed
context; references remain BE-owned. Full packages, notice messages, diagnostic
detail-only facts and current catalog lookups are excluded. Required omission or
unsupported sentence falls back; optional omission is valid. Finite complete
grammars retain exact money/currency/entity/unit/role; other sentence variants are
bounded. This does not implement general entailment, free prose or a model judge.

One option shared by multiple strategies is called the proposed option. The
viewed nonwinner qualifier remains required. Purchase summaries show at most three
safe captured-name lines in original order, never deduplicating equal quantity/
Ingredient/unit when suppliers/terms/dates differ or even when values coincide.
Each sentence retains original line ordinal and exact quantity/unit/arrival date.
Collection-level `/option/purchases` and captured-name references are the supported
evidence granularity; ordinal identifies the member, no new index-pointer contract.
A required qualifier says quantities are per line, not Ingredient totals. Missing/
unsafe labels or more than three lines require an abbreviated-list qualifier and
detail link instruction. No pack conversion, totals across units, order creation
or receipt is inferred. All canonical purchase details remain in retained C03/C05.

C08 collects retained capture problems, forecast/result warnings and BOM/option
engine warnings. Selection also inspects forecast and viewed-option notices.
Known BASELINE_FALLBACK, FORECAST_TRAINING_OVERLAP,
FORECAST_TRAINING_BOUNDS_UNKNOWN and OFFER_OMITTED get short verified qualifiers.
Matching codes are grouped as categories without asserting a shared root cause or
counting independent entities; references cover all retained occurrences. Unknown
codes get a neutral required notice to review details; original untrusted messages
are never echoed. Unknown assumptions similarly retain a neutral qualifier;
routine capture assumptions remain detail-only, while hypothetical-stock warning
stays required. Warnings do not become blockers or change eligibility. Full
warnings/issues remain available in C03/C05/C08 as applicable. Assumptions remain
in retained capture and operational_basis where projected; no new detail DTO is added.

Requirements refer only to evaluated Product/path scope. Missing-recipe grouping
requires exact Product/code/affected-date evidence. Scope never claims successful
computation. One plain search limitation preserves UNPROVEN; finite certification
does not imply global optimality. Zero purchase remains a valid plan, without an
invented stock-sufficiency cause. Failed diagnostic amounts remain detail-only;
blocked unknown fee is not zero. Deterministic fallback retains these obligations.

Configuration is startup Settings: SUMMARY_LLM_ENABLED=false, SUMMARY_MODEL unset,
SUMMARY_PROVIDERS=[] (explicit OpenRouter default routing, no fallback),
SUMMARY_MAX_TOKENS=3072, SUMMARY_INPUT_BYTES=16000, timeout20/deadline25 seconds.
An explicitly authorized operator can set model `google/gemini-2.5-flash`, providers
`["Google"]`, tokens1200, timeout30/deadline35, with existing private
OPENROUTER_API_KEY. Key presence alone enables nothing. Startup composition chooses
profile/6 for new generations, including model-OFF fallback; AS02 and old receipts
use retained pins without provider calls. Invalid/missing provider configuration
degrades to deterministic fallback. Settings changes require an authorized process
restart. Disable by SUMMARY_LLM_ENABLED=false and restart; retained rows need no
rollback/migration. Chat/Import/email flags remain independent. No restart occurs
as part of local source integration, no paid-call authorization is implied.

HISTORICAL INFORMATION: S2.1 six synthetic Gemini/Google cases were accepted only
on fingerprint05d778b47a229f70bd859dc8903e916cabaef0c52ac9ed9052d42a1fd7573110
(profile/5, selection/1, prompt/4, renderer/3, guard/3). Original artifacts/closed
ledgers remain unchanged. S3 source changes warnings/shortlist and is verified
offline/fake-provider only. Codex grading is not independent owner UX acceptance.
No browser/whole-FE, final-source live Gemini or production readiness claim.
Current [runbook](../runbooks/FULL_TEST_FLOW.md#summary-narrative-s1) owns verification
commands, owned targets and activation boundaries.

## Internal boundary

`PublicPlanning.assistant_evidence(token,run_id,option_id=None,ingredient_id=None)`
reuses `read_record`: resolve owning Store, current actor/session/Store membership
and all READ_PERMISSIONS **before** loading aggregate content. Whole denial applies
to missing budget/cost rights. Every call repeats authorization, including cache
hits; the caller cannot submit authoritative facts/winner/proof. No route/composition
change exposes raw evidence input. AS01/AS02 call this trusted boundary, never
accept client facts. Existing3MiB inspection bound still applies.

`project_evidence` consumes only a trusted already-verified record/C03 view pair.
It is not an untrusted JSON decoder or authenticity verifier. Frozen nested DTOs,
tuples and exact quantity/service DTOs preserve immutable values; canonical digest
references are provenance/debug identities, not signatures or permission tokens.
Do not call this projector with client-supplied records or use a DTO validation
success as evidence that a PlanningRun exists or belongs to an actor.

Overview carries retained request/effective configuration and budget, temporal
basis, computed/excluded Products and units, Ingredient identities/captured labels,
forecast provenance, strategies/search/proof, option identities/eligibility, C08
blockers/warnings and snapshot assumptions/source references. Excluded overrides
remain NOT_EVALUATED. Missing labels stay null/not_captured; no live-name fallback.
Option detail is explicit and preserves C03 exact costs, fee components, purchases,
per-Product/path service and assessments. Ingredient detail reuses C05 projection,
keeping captured stock separate from simulated daily balances/shortage/ending.
With no winner, an explicit reference option remains reference-only. Overview does
not embed option purchases/service tables or daily Ingredient details.
Summary explicitly requests a small pairwise projection from retained comparison
facts (cost and Product deltas, no Ingredient table); ordinary overview does not.
One relevant pair may be rendered with exact to-minus-from direction, not a global
ranking or causal claim. Comparison availability participates in scoped ref IDs.
Failed partial pipelines may retain a selector winner; evidence preserves that
diagnostic identity while recommendation_available stays false. This corrects
L1's over-strict rejection of that valid retained state, without changing engine
facts or permitting a winner on completed no-winner outcomes. Summary states the
failure explicitly and never promotes the diagnostic winner into a recommendation.

Evidence refs bind schema, Run/Store, aggregate/input/result/request identities,
versions and projection context. `resolve` accepts only issued IDs and resolves
their typed field pointer in that immutable bundle. Cross-Run/option/Ingredient
or changed-version refs are rejected. A field citation alone is not prose grounding.
Omissions explicitly exclude actual outcomes, probability/profit/causality and a
zero-purchase baseline from this projection; no extra business calculation exists.

## Durable cold verification and compatibility

HISTORICAL INFORMATION L1: cache-only reads returned EVIDENCE_NOT_VERIFIED after
restart/eviction. Existing default cold `decode_row` validates nested contracts
that call `expand_bom` and exact procurement `_evaluate`/serving and selector
reconciliation. It does not run native candidate search, but it does recompute
business checks. This remains explicit technical debt for existing C03/PDF callers;
their default validation and historical replay/digests are preserved.

CURRENT FACT L2 uses `VerifiedPlanningReads.read(evidence=True)` and an explicit
trusted Pydantic validation context for retained consistency. It verifies whole
JSON hash, storage/phase versions, column identities, canonical round-trip,
input/result digests, capture/configuration/provenance relationships and all typed
boundaries. It checks BOM equations, serving conservation/coverage/FEFO, candidate
packs/MOQ/budget/fees/arrivals/capacity/services, journal consistency/domain
coverage, comparison projections and selector key inequalities. No engine
entrypoint, solver, forecast, allocator, `_evaluate`, `expand_bom` or selector is
executed. Validation arithmetic checks retained facts; it does not generate new
business results. No `model_construct`, renamed fake verified object or persisted
verification receipt bypasses semantics. Ordinary write/re-execution validation
continues using its existing stronger replay checks.

Journal vectors without retained serving rows cannot be independently simulated
or re-ranked by this reader; their recorded classifications remain retained
execution evidence. Full finite journal coverage/consistency and published
candidate equations are checked, but this is not a new independent certificate
of every rejected vector or historical optimizer correctness. Summary never
upgrades retained proof/UNPROVEN/INCOMPLETE. Database hash is not source authenticity.

Fresh Session/process or cache miss succeeds on supported retained graphs without
warm-up. Unsupported version has distinct503 UNSUPPORTED_RESULT_VERSION; corruption
is503 RESULT_INTEGRITY_UNAVAILABLE; absent phase facts remain nullable availability;
technical DB/programming failures are not business fallback. Validation modes have
separate cache keys so a consistency read cannot weaken a default C03/PDF deep read.
Each hit still hashes raw JSON and binds identity/revision columns. Negative failures
are not cached. Cache4 entries/16MiB is only an optimization; oversized records use
the cold path. No latency/capacity SLA is inferred.

## Summary implementation

`plan_summary_rendering` owns facts, exact displays and six material claim families.
Provider returns only typed ordering/tone, not prose/assertions/entities/numbers.
Server-owned variants give bounded language choice and preserve the answer even on
schema rejection. This intentionally narrow L2 presentation cannot demonstrate
unrestricted model prose quality; numeric repair, sentence removal and NLP guards
remain unimplemented. Every claim ref resolves; final stored answer is compared
against renderer plus pinned evidence on reads. No raw workbook/source text/history
is sent. A captured Product name may appear inside a server-rendered pairwise
statement; it remains quoted data and cannot become provider instructions or
authoritative model assertions.

SummaryProfile is separate from Import config/flag; default OFF, explicit model
required for network use. Empty providers explicitly permits default OpenRouter
routing; explicit routes remain restricted. Key alone never enables it. Transport
reuses only mapping's NoRedirect behavior, with task-specific strict schema, input/
output byte caps, token cap, per-read timeout/cooperative deadline, one attempt and
no route/model substitution or ambiguous billable retry. Diagnostics retain safe
model/provider/prompt/validator/usage/failure information; no raw sensitive logs.

`PlanSummaries` owns synchronous acceptance/running claim, provider outside Session,
fresh authorized publication and retained read/replay. Concrete SummaryRepository
owns queries. Two purpose-specific tables and partial unique identity index prevent
concurrent duplicate running/completed generations; immutable key receipts and DB
terminal-transition triggers fence publication. Failed identities allow explicit
new-key retries, not automatic provider replay. OS-dead owner recovery occurs only
on explicit POST replay; GET never calls a provider, starts work or performs recovery.
Detailed statuses/idempotency/errors belong to the canonical contract, not this doc.

## Verification and remaining acceptance

CURRENT FACT live synthetic summary smoke: google/gemini-2.5-flash resolved Google;
2 single-attempt completions, each422 prompt/28 completion tokens,1.875s measured
transport latency; usage.cost total$0.0003932. First schema-valid raw response
fell back at the application explicit-provider guard; guard fixed with unit/DB
regressions, second response accepted. Raw ordering/tone becomes exact server-owned
claims; final refs/schema/GET/replay and offline timeout fallback checked through
AS01/AS02. Pricing/parameter metadata checked before each call; max_price0.3/2.5
USD per million and conservative text-token reservation$0.0203008/call,≤3 calls and
≤$0.10, no retry. Safe synthetic raw/final and write-ahead slots stay ignored under
runtime/assistant-test/live-smoke. Regular pytest skips live tests; explicit command
in runbook. No real Store facts or key/headers are retained. The check proves this
constrained presentation only, not arbitrary prose grounding or L4 evaluation.

## Scoped chat implementation

HISTORICAL INFORMATION original L3 acceptance: progressive synthetic smoke consumed
10 completion attempts, with0 original model-accepted finals. One transport has
unknown usage/cost, fully reserved; known replies resolved google/gemini-2.5-flash /
Google and returned schema-valid prose. False rejects on legitimate wording/ellipsis
were corrected through scoped regressions and offline AS03 replay. Original live
finals remain immutable fallback. No fresh paid call after the final fixes fits
the exhausted attempt cap; this is not conversational live acceptance or L4.

CURRENT FACT L3.1 live acceptance remains PENDING. The separate30-completion/
USD1.00 ledger consumed6 attempts:3 accepted development cost/proof/Ingredient
responses, one rejected tradeoff, its unknown timeout regeneration, then HTTP429
on the next frozen evaluation. No further paid calls/model/provider change. Known
cost USD0.0065817;2 unknown costs retain USD0.0281184 reservation. Final-source
context/pair and proof eligibility/requirements fixes pass offline AS03 fake-provider replay, not a fresh full live
subset. Every request/fact/prompt/schema/preflight/raw/final/version and replay
count stays ignored in runtime/assistant-test/conversational-l31-live. Source
fingerprints distinguish WIP iterations; current source is not historical source
for every attempt. The historical14-case Codex-authored wording probe reports0 false accepts
and1 legitimate unsupported paraphrase. This is a finite limitation, not a change
to the valid label or proof of general quality. L4 remains pending.

CURRENT FACT L3.2 checkpoint a29ae1f3db9d850d65dbb17a92d534f94cca235f, after L3.1 checkpoint44b451893e7cc4735b6d79d9410db1ba95e0dcac: AS03 keeps its route and authority/lifecycle.
`chat_context` resolves bounded structured context: Run/evidence version, viewed
option/pair, Ingredient/Product identity and pending original question/candidates.
Retained partial-name matches are candidates: "milk" can match two captured milk
labels, requiring structured clarification. A candidate selection resumes the
original question; explicit new entity/option replaces old context. Pronouns need
one antecedent; multiple or foreign-version context clarifies. IDs are revalidated
against this Run; no live catalogue, business facts or rights come from context.
Ingredient topic (purchase/purchase_rationale/captured stock/daily shortage/ending) can carry across
an explicit entity switch. Product labels/IDs also produce scoped candidates and can resume pending
questions or explicit service follow-ups. General semantic alias resolution
remains limited to captured names, not live catalogue synonyms.

`conversational_evidence` selects question-specific main obligations separately
from optional supporting facts. Cost need not repeat budget/fees unless asked;
Ingredient stock uses captured lot quantities, daily questions use retained date/
path balances, not recalculation. Proof includes retained viewed-option eligibility and per-Product/path requirement
assessments (target/status/shortfall with units), alongside selector/proof scope.
No-winner includes retained rejection reasons,
nonzero customer gaps and blockers, or explicit missing-detail facts. Pairwise
facts preserve exact to-minus-from direction and individual Product/path units.
No whole-package prompt or silently dropped main facts. More than16 main facts,
24 selected facts or the serialized input cap gives complete topic fallback.
Warnings are contextual: no blanket summary disclaimer or "0 warnings" footer.

Chat has independent CHAT_* flags/model/routes/bounds, default OFF. New work pins
prompt/5, chat_assertions/6, selection plan/6 and conversational_assertions/2.
`chat_prompting` composes common instructions, one of seven intent families,
resolved Run/option/Ingredient/Product context, evidence availability and detail,
two placeholder style examples with versioned IDs, and the assertion contract.
Examples carry no concrete quantities/names/fact IDs and are never citation sources.
The serialized request remains byte/token bounded; selected example IDs/versions
are retained in opt-in synthetic request artifacts. Production receipts pin prompt
version/hash rather than storing raw prompts. There is no model reviewer.
A clarified request sends its resolved original question while retaining the client
question separately as untrusted data. purchase_rationale preserves a why follow-up
across an explicit entity switch; broad budget questions do not inherit Ingredient.
Why answers distinguish quantity, a scoped retained simulation row when available,
and the missing exact causal/zero-purchase explanation. Simulation factors are not
proof of why a precise quantity is optimal. Missing rows remain missing.
The provider writes
real prose plus typed assertion proposals (fact/role/entity/path/value/unit/
polarity). Proposals are reconciled to sealed facts; citations/slots alone do not
validate prose. `chat_assertions` separately checks material predicates, exact
numeric/unit binding, polarity/scope/identity and residual unsupported words.
Non-authoritative connective phrasing can vary; the legacy grammar is retained
only for supported complex/proof subsets. This is bounded deterministic checking,
not general semantic entailment. Reviewer models are not used/enabled.

Each independent assertion is a repair/removal boundary. Exact numeric replacement
requires one unambiguous sealed fact with matching role/entity/path/unit and a
single amount, then full revalidation. No nearest-number or unit repair. Invalid
optional assertions or redundant assertions may be trimmed as whole units; missing
main obligations or unverified material main text require regeneration/fallback.
A maximum of2 completions (first plus one semantic regeneration) share a request
deadline and worst-case cost reservation. Feedback contains failure codes and only
original permitted facts/wording, never new authority from output. Unknown transport
outcomes, schema/refusal/provider failures are not automatically retried. Final
coverage and grounding are rechecked. Dispositions distinguish ACCEPTED, REPAIRED,
TRIMMED, REGENERATED and FALLBACK, with assertion positions/reasons/fact IDs in
safe public traces. Opt-in synthetic artifacts join these to captured rejected
clauses, selected facts and reconciliation results. Unknown usage remains null,
including a known first response followed by an uncertain second completion. Model OFF uses
the same scoped deterministic facts. Summary/import behavior remains independent.

Replay dispatches by pinned renderer/validator version: old /1-/2 receipts and
old generation plans use their pinned renderer/selector/grammar. New selection
plan/6 and deterministic renderer/7 own current context/obligations. Frozen
chat_context_v3/chat_assertions_v3 preserve plan/3 and validator/3 behavior, including
its documented false rejection; chat_assertions_v4/chat_assertions_v5 preserve their development receipts. Implicit plan/2 and renderer/3 retain earlier
obligations, including L3.1 development receipts. New context
and empty diagnostic fields are elided in old canonical shapes. No original
live finals are rewritten. No new migration/table/service/endpoint is required.

Legacy assistant_message/1 deterministic receipts remain immutable/readable.
Additive0030 chat_generations owns accepted/running/completed/failed claims, pinned
request/profile/evidence/selection/prompt/schema/validator/process and terminal
fences. A completed assistant_message/2 receipt and final generation commit atomically.
Scoped key advisory locks serialize old/new acceptance across config changes and
close before provider waits. Provider is outside Session/transaction; current
authority repeats after preflight immediately before completion and at publication,
delivery and replay. Revocation discards output. Same key/body never calls again;
different body409; new key is explicit new work, not exactly-once provider billing.
Running alive/unknown409; only explicit replay of an OS-proven dead claim records
PROCESS_INTERRUPTED without repeating an unknown completion. Same failed key stays
failed. Applied ACK loss reconciles exact durable records, not guessed success;
unapplied/technical failure never becomes business fallback. No worker/queue/
conversation platform or lazy GET generation. Migration refuses retained-row
downgrade and has only been applied on the owned assistant test DB.

CURRENT FACT: focused no-DB tests use hand-authored read contracts and interned static
synthetic pipeline fixtures from existing s363 review artifacts, not newly generated
PlanningRuns or customer evidence. Original file hashes are retained in fixtures;
test-only interned JSON removes repeated subgraphs, not facts. They exercise overview and
option/Ingredient projection, mixed units, exact fractions/display, cost components,
null/zero, exclusions/assumptions/warnings, no-winner/failed/partial/UNPROVEN,
foreign/dangling references, current-rights-before-materialization ordering and
revoked-session/grant denial on repeated application reads. Cache tests verify
misses avoid cold decoding and changed raw hashes cannot hit a verified entry.
No solver/provider network/SMTP or training is used. These unit boundary oracles
are separate from the real PostgreSQL/HTTP acceptance below.

Owned isolated container/database shelfcash_assistant_test at5436, limited tester
shelfcash_assistant_tester, guarded reset/migration and private runtime credentials.
Real auth/HTTP/fresh-session tests cover create/execute/read, same/new-key replay,
concurrency, failed retries, current grants/Store isolation, revocation during mock,
lost/unapplied ACKs, stale writer, immutable terminal records, schema round-trip/
parity and Run preservation after live budget/catalog changes. A fresh process
reads cold evidence and summary with engine entrypoints forbidden; a real child
crash demonstrates explicit replay without automatically repeating provider work.
No other DB/worktree/runtime was migrated. Commands and target ownership:
[runbook](../runbooks/FULL_TEST_FLOW.md#assistant-l2).

CURRENT FACT L3.2 verification: the fixed14-case developer/Codex corpus reports
0FA/0FR, not independent human grading or general entailment. V5 adds explicit
per-fact slots (including literal null and polarity) after development live showed
correct proof prose with wrong proposed slots. Strict slot checking remains; prose
is independently checked. Comparative cao hon/thap hon expressions bind to signed
deltas, Product/path and the retained positive cost role; no global ranking/cause.
When purchase evidence is unavailable, its missing-cause qualifier does not assert
that a proposed quantity exists. V3/V4 code remains pinned for old receipts.

HISTORICAL INFORMATION: evaluated V5 source0e3199d201853962b40222d3f11079309b8779286e36a8023b3978227eb3a8b5
is PARTIAL, not a full live PASS:11 completions produced7 ACCEPTED,1 REGENERATED,
1 FALLBACK and1 deterministic clarification. The final context turn switching to
condensed milk was not executed after the shared30-attempt cap was reached.
V4 development results remain separate. Final budget/quantity/why/missing/proof/
comparison and first3 context turns have actual saved live responses; no-winner
correctly falls back after a valid rejection paraphrase is rejected, then an
unknown fact ID appears during regeneration. Two valid V5 live paraphrases (why and
rejection, attempts22/27) were false rejects; no labels were changed to hide them.
V6 now accepts the exact scoped omission variant and an optional colon before the
exact option rejection reason, with whole-clause/slot/polarity checks retained.
24 unit tests and3 real AS03/owned-PG fake-provider replay tests pass, including
V5 pinned replay. Observed wording is rebound to fresh synthetic scoped refs;
original raw22/27 and V5 outcomes are unchanged. V6 live acceptance was PENDING
at checkpoint because the old shared attempts were exhausted.
Proof/comparison are correct but verbose for simple detail. No unsupported material
claim was observed in reviewed finals; this finite check is not general safety.

Shared ledger30/30: known USD0.0551248, two historical unknowns reserve0.0281184,
upper0.0832432; all full reservations0.421776. Monetary headroom does not authorize
another call. The11 evaluated V5 completions used27133 input/5354 output tokens and
USD0.0215249, resolved Gemini2.5Flash/Google; completion latency1811..6515ms.
All saved finals have fresh-session persistence comparison, identical replay with0
extra completions and GET405/no generation. Tests deliberately clean their owned
DB afterward; final test DB is head0030 with0 users/Runs/chat rows.
Linked SQL28 passed before V5; V5 focused12 pass/1 test-fixture expectation failure,
then affected V4-pinned replay1 passed. Unit/API34 pass; ordinary live8 skipped.
V4 live8 lifecycle cases passed; V5 live7 passed/1 partly executed context case
skipped at cap. Those pytest results are not model-quality grades. No full suite.

CURRENT FACT: separately authorized group `L32-V6-acceptance-1` evaluates the same
V6 fingerprint2e06f304211cbd999ce88625fcbfde01e2a57800bd785d3e9fe2d07cb8f5a3a7,
prompt5/validator6/selection6/renderer7/assertions2. Source, actual prompt/schema,
fixtures, harness and Codex-authored expected matrix were frozen before live.
Finite synthetic acceptance is PASS WITH LIMITS: seven standalone cases plus all
four context turns produced9 ACCEPTED/1 REGENERATED/1 clarification. The first
condensed-milk raw omitted required simulation requested/available/shortage prose
despite exact typed slots; rejection was correct. One bounded regeneration
restored complete evidence/proposal/causal-boundary prose. Saved-raw offline replay
reproduces reject/accept, with positive/omission/wrong-Ingredient regression; no
application source/fixture fix or further paid rerun was needed.

The four turns clarify ambiguous milk, resume the original purchase question for
fresh milk, retain its why topic, then switch to condensed milk's own fact IDs and
simulation. Both synthetic quantities are20 g, so identity/provenance rather than
numeric inequality establishes the switch. Every final checks each required right
revoked (replay/new key403), inactive/other Store membership404, fresh-session
persisted equality and same-key/body POST replay with0 additional completions.
GET405 is a negative method probe; AS03 has no message GET endpoint.

New ledger11/16 attempts, known USD0.0203539, unknown0, full reservations0.1546512
under USD0.30;5 slots remain unused after the matrix completed. Resolved model
google/gemini-2.5-flash/provider Google,26263 input/4990 output tokens; completion
latency2077..5858ms (median3733). No429/timeouts. Old ledger30/30 and its two
unknown reservations remain byte-identical. New offline13 pass/8 opt-in skips,
fake HTTP four-turn/authority harness2 pass, observed omission regression1 pass;
live8 lifecycle cases pass separately from manual Codex raw/prose quality review.
Initial harness expectation403 for inaccessible Store was corrected to contracted404;
failed and passing logs are preserved. No full suite or independent human/model judge.

Limits remain: verbose proof/comparison at simple detail, opaque option IDs in
no-winner wording, clarification kind with diagnostic disposition=FALLBACK, and
finite paraphrase support rather than general entailment. No historical response
was relabelled. New acceptance harness/tests/docs remain WIP; no L4/FE/deployment.
Review artifacts stay in ignored runtime/assistant-test/L32-V6-acceptance-1; the
scoped review ZIP can be removed without losing original source or evidence.

## L4 quality evaluation and explicit candidate presentation

CURRENT FACT after acceptance checkpoint464dec8dc5c04f2f773ce4cedcee26e342151f57:
V6 remains the default. `AssistantChat(..., presentation_version=7)` explicitly
selects candidate191b9bd60ce5256cf1fa4a50e9a159852effb6b1d1d98debe3e431fb3932cf77,
selection7/prompt6/validator7/renderer8/resolver5/assertions2. No private config,
public DTO/endpoint, permission or migration change. Default composition is unchanged.

`chat_readability` groups only exact members from verified retained projections.
Requirement groups need complete declared Product/path coverage, no exclusions,
matching target/unit, PASS and known zero shortfall; missing/exception rows stay
explicit. Equal Product/unit/delta across paths can group with every original path;
different values stay separate. Group models reject duplicates, mixed semantics
and altered reference unions. BE creates wording; model slots and complete prose
are checked independently. There is no fact-ID whitelist, arithmetic, averaging,
metric rewrite or removal of main obligations. Technical detail keeps individual
rows. Boundary grouping preserves evaluated-only, finite certificate and global
optimality limits. Named nonwinner remains a viewed option, not a recommendation.

Labels derive from captured identity/scope: unique bounded captured name, otherwise
local deterministic ordinal; option source strategies label deduplicated baskets.
Ordinal labels do not rank business quality. Product gaps carry Product identity
in addition to actual option ID; labels are generated per identity, avoiding ambiguous
string replacement for duplicate names. IDs remain in typed fields/references.
Instruction-like labels are treated as untrusted and use local labels; this finite
screen is not a general injection proof. No current catalogue names are read.
Renderer8 sets clarification disposition=CLARIFICATION (enum already existed).
Old renderer/validator/resolver versions remain pinned; frozen V6 and resolver4
copies preserve canonical replay. Resolver5 adds failed-run outcome wording while
still reporting retained status when the user incorrectly presumes a failure.

Evaluation corpus `tests/fixtures/assistant_l4/corpus.json` freezes36 scenarios,
original18 development/18 evaluation split, criteria and six live scenarios before
candidate runtime changes. Labels are Codex-authored, not independent human review.
Eight evaluation cases used during development/evaluator correction are explicitly
exposed in exposure.json; remaining10 are9 offline checks and1 real SQL authority
gate, not statistically independent unseen evidence. The hand-authored20/35g,
zero/unknown, negative/zero/mixed-path and missing/exception variants are projected
contract inputs with new synthetic identity/references, never forged retained SQL
runs, new engine outputs or real facts. Real HTTP live uses the existing consistent
retained20/20g fixture. No solver/forecast or zero-purchase scenario is run in chat.

Offline baseline34 pass/1 failed-run intent gap/1 separate SQL; candidate35 pass/1
SQL. Ten explicitly labelled assertion probes (1 valid/9 invalid, repair disabled)
show0FA/0FR for both; these counts are not36-scenario model accuracy. Initial two
null-pointer metric failures were evaluator bugs: a reference resolving to null is
valid unavailable evidence, not dangling. Logs/results are retained, labels unchanged.
Exposed E08 failed-run wording motivated versioned resolver5, with positive/negative
tests. Post-live fixture audit found reversed-pair context still pointed forward,
so the initial negative case exercised missing comparison. E06 is now exposed;
context and independent value/path oracles are corrected with4 passing regressions.
Audited offline results replace the earlier metric interpretation, not original
files; app191b9bd6 and all live traces remain unchanged. Scope/reference security is separately covered through actual HTTP/SQL,
fresh-session equality, current-right/Store denial and replay with0 new calls.

Paired six live scenarios/full four-turn chain: baseline9 completions,7 ACCEPTED,
1 REGENERATED and1 clarification; candidate8 completions,8 ACCEPTED/1 clarification.
All final material prose/coverage reviewed against sealed facts, not just slots or
pytest lifecycle. Baseline raw7 is a valid comma/colon mechanistic paraphrase falsely
rejected; saved-raw replay shows validator7 inherits this limitation. Candidate
canonical live wording success is not broader entailment improvement. No historical
response, label or old ledger is relabelled. No model reviewer is used.

Observed character counts proof522→408, comparison564→308, no-winner469→344;
quantity38→50 and why235→263 are not uniformly improved. Baseline input22209/
output4544, USD0.0180227; candidate20133/3159, USD0.0139374. Total reduction partly
reflects one fewer regeneration; average input per completion slightly increases.
Completion median2625ms baseline versus2834.5ms candidate, application-response
median5172ms versus3889ms; single samples and provider variability preclude a general
latency claim. L4 ledger17/24 calls, USD0.0319601 known, no unknown, reservations
USD0.2390064/0.50;7 slots unused. Old30/30 and11/16 groups, including5 unused slots
and historical unknown reservations, remain separate and unchanged.

Focused verification: initial19 unit/API, later40 focused unit/API and17 SQL; final
affected20 unit/API and3 SQL pass. Separate budget3 pass/live6 skip without opt-in.
Baseline live6 lifecycle cases pass79.98s; candidate6 pass68.40s. OpenAPI exact diff0,
76 operations/69 paths/head0030. No full suite. One old regression output writer
overwrote its historical pair artifact; new output was preserved separately and
original restored from a hash-verified review ZIP. Old callers now target L4;
all1939 prior artifact bytes verify unchanged after recovery.

DECISION FOR THIS EVALUATION: keep V6 default. Candidate passes finite technical
gates and improves three readability strata, but remaining evaluation cases do not
show a correctness advantage; inherited paraphrase rejection, offline-only20/35 and
small live sample limit replacement evidence. Candidate remains explicit WIP for
review, not disabled-provider naturalness evidence, production readiness or L5.

### L4.1 focused acceptance of the derived candidate

CURRENT FACT L4 checkpoint46d15459d40f006152f51a4101a9563cc96eb150 preserves
candidate7 and all historical evaluation. L4.1 source
2d7e2c938baea975c39175fe3b699cb062fddc4a2f99352b62ba776c54246a4f is derived
candidate8, not a new PASS label for old7. Versions selection8/prompt7/validator8/
renderer9/resolver5/assertions2; V6 default unchanged, explicit presentation8 only.
Frozen `chat_assertions_v7` and `chat_readability_v7` retain old generation7 plans,
obligations/rendering and paraphrase rejection. Version6 remains pinned too.

Saved L4 baseline raw7 contains all20/20/0g values, Sữa tươi, LOW/2026-10-08 and
simulated scope; its comma/"và" construction is semantically equivalent to the
canonical colon/semicolon construction. Validator8 derives exactly this complete
alternate grammar from each scoped card, with no wildcard, token removal or
fact-ID/slot bypass. Offline saved-raw replay rejects unchanged on6/7, accepts8.
Minimal pairs reject wrong requested/available/shortage quantities, unit/entity/
path/date, negation/polarity, omitted numbers, causal/optimality/actual additions.
The reusable sanitized fixture carries original validation input/provenance;
it is not a new provider response or independent human label.

Simple why no longer requires the first arbitrary LOW/day row. Quantity and the
explicit missing exact causal/zero-purchase evidence boundary remain mandatory;
retained daily factor remains available as support with resolvable references.
Technical detail and explicit path/date requests retain relevant required factors.
Live fresh-milk why voluntarily includes its factor; condensed-milk why safely
omits it. This is main/support separation, not fabricated cause, aggregate or
silent truncation. Missing evidence remains explicit. No new engine work in chat.

`tests/assistant_l41_cases.py` creates actual synthetic PlanningRuns through
accepted setup, capture, existing exact engine and accept/claim/retain/finalize,
then full validation/fresh read. The supplier inputs are10g and17.5g packs with
20g demand/BASE95: both need two packs, yielding20g fresh and35g condensed milk.
No output quantity JSON patch/model_construct bypass. Captured labels/forecast
metadata are explicit synthetic test inputs. Mixed comparison uses explicit
custom BASE40 (default remains approved BASE95), p25 half/p75 double and native
search to produce distinct baskets. The engine supplies to-minus-from lean minus
balanced/protected: cost−5VND; Product0 BASE/HIGH−5 and LOW0cup; Product1 BASE−2.5,
HIGH−17.5 and LOW0cup. Grouping joins only exact matching members. Failed fixture
injects a protected-search failure, retaining diagnostic incumbent/other exact
facts without promoting an actionable recommendation. Missing failed-detail
admission and exceptions/exclusions/duplicate labels have focused offline tests.

Focused live acceptance is PASS WITH LIMITS on frozen source2d7e2c93:5 model
ACCEPTED/1 deterministic CLARIFICATION,0 regeneration/repair/trim/fallback, no
provider failure. Full four turns clarify two milk candidates, resume fresh20g,
retain fresh why topic, switch to condensed35g with its own identity/fact/refs.
Failed response distinguishes execution error/diagnostic winner, retained protected
rejection/gaps9.5/19cup; mixed response preserves distinct−2.5/−17.5/0 values/path
and simulated scope. Codex reviewed raw/final/material facts/main coverage,
separate from3 lifecycle test cases passing125.27s; no independent human/model judge.
Every final checks fresh-session receipt equality, same-key/body replay0 calls,
each revoked right403 and inactive/other Store404. GET405 is only a negative method
probe, AS03 has no message GET endpoint. Offline real SQL also creates6/7 generations
on the same valid20/35 Run then replays byte-equivalent results with8 selected.

This slice used5 new calls18–22 in the SAME L4-quality-evaluation-1 group, cost
USD0.0099809, no unknown usage. Aggregate22/24, known USD0.0419410, full reservations
USD0.3093024/0.50;2 slots remain unused. No new budget, reset/refund or transfer from
the5 unused L3.2 acceptance slots. Prior L4 baseline/candidate17 calls and older
unknown reservations stay unchanged. Configured Gemini2.5Flash/Google/default
OpenRouter routing and preflight/byte/token/pricing caps unchanged; no429/timeouts.

Verification: final22 focused units pass9.95s; earlier affected37 unit/API pass/
3 opt-in skips38.24s. Milk HTTP/SQL1 pass42.27s and affected mixed/failed HTTP/SQL2
pass74.80s. An initial unit helper used resolver4 for8; corrected helper picks5.
Mixed fixture initially collapsed all baskets at BASE95, then a proposed default40
was correctly rejected by the policy guard. Explicit custom40 fixed fixture setup;
separate affected1 pass44.05s before HTTP assertions. Failed logs and prior outputs
remain, no contract weakened. OpenAPI exact diff0,76/69/head0030. No full suite.

DECISION FOR FOCUSED ACCEPTANCE: candidate8 is eligible for explicit controlled
trial within verified scope; V6 stays default. Finite paraphrase grammar, synthetic
evidence, generic quantity wording and sometimes technical/long mixed-path prose
remain limits. No general entailment, production readiness, real-customer result
or superiority claim. L4.1 changes stay WIP; no L5/FE/default/deployment action.
Review `runtime/assistant-test/l41/index.json` and the scoped ignored acceptance
ZIP; all historical evidence bytes remain unchanged and originals stay outside ZIP.

### Why-quantity evidence audit

CURRENT FACT `planning_inspection_projection.ingredient_detail` already exposes
proposed purchases, captured stock, daily balances and related Product fulfilled
contributions/recipe IDs/dates. Chat selects quantity and one matching daily row;
contributions are projected but not selected. They could contextualize simulation
consumption; they do not establish why an exact purchase was selected. Captured
BOM/recipe/source issues and strategy diagnostics/proof describe admission/search,
not a per-line causal or zero-purchase certificate. No such certificate was identified
in the inspected typed retained contracts. This is a scoped source/schema audit,
not exhaustive knowledge of all possible engine outputs. Missing exact rationale
remains explicit; chat does not run a new engine or invent counterfactual evidence.

## Legacy review and future slices

HISTORICAL INFORMATION: read-only reference audit at
`D:\hocc_bk\ai\proj\projectAttacker2026\attackerBE\docs\LLM_REGRESSION_REVIEW_VI.md`
(legacy HEAD cac7c5a6a46c5751063be6b27866e3672acd2e2a), plus
`Forecast_Engine_FandB/shelfcash_legacy_review.zip` under the project parent.
The ZIP's overall_summary, FE explanation contract, schemas and CHAT-7/8 audit
were inspected as source only. No legacy runtime/import dependency/schema port.
Read-only L3.2 inspection of decision_intelligence/style_examples.py and
ingredient_synthesis.py confirms intent/evidence-case/detail selection, non-authoritative
placeholders, positive/negative examples and selected-example diagnostics. Those
principles inform current composition; no legacy repairs/removals/runtime code is
ported or assumed active. Findings are offline regressions, not proof of comparative live wording quality.
Legacy recommendation_available/expected_fill_rate mismatches motivate typed
current C03 ProductService/service fields; no legacy aggregate fill field is made up.

TECHNICAL CHOICE: current OpenRouter mapping transport has no-redirect credentials,
deadline/timeout/response-byte/token/attempt bounds, strict JSON parsing and safe
typed diagnostics worth reusing in a future provider adapter. Its workbook payload,
mapping prompt/schema and mapping enable flag are task-specific. L1 does not extract
a generic gateway or alter mapping behavior. A future wording task must own its
profile, scoped allowlisted evidence and authorization before transport.

PROPOSAL next slices (separate authorization): L4 broader fixed-evidence live evaluation with explicit
cost/attempt caps and raw/final diagnostics; L5 HTTP/FE/security/restart integration.
Broader free-prose acceptance, Vietnamese/English paraphrase coverage and quality
remain L4 requirements. L3 tests exercise bounded paraphrases/negation/compound
clauses and conservative rejection; they do not prove general NLP correctness.
Historical profile/1 summary rejects all free provider assertions and only uses
presentation ordering/tone. New profile/2 bounded narrative is described above;
chat transport/prompt/validation do not control summary behavior.
Explanation of existing verified Runs needs no merge from data-readiness/challenger;
new data admission/forecast quality evidence remains separately scoped.

Shared integration files with readiness/challenger: Planning contract, CURRENT_STATE,
ROADMAP, app/main.py, app/config.py/.env.example, model registration, scripts/dev.py
guards and runbook. Assistant also touches retained Planning validators/reader,
planning_public and body limits. Reconcile these deliberately at integration;
no manual copy of readiness WIP or dependency on challenger promotion.
