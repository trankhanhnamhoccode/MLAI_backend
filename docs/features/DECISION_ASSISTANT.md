# Decision Assistant evidence foundation

CURRENT FACT L2/L3: immutable `decision_evidence/1`, durable cold consistency reads,
typed deterministic summary, optional bounded model presentation and AS01/AS02
durable PostgreSQL lifecycle and AS03 optional conversational prose are implemented.
Focused offline/owned-DB verification and an explicitly authorized synthetic Gemini
summary smoke are separate evidence. No new grant or deployment.
The [Planning contract §18](../PROCUREMENT_API_CONTRACT_VI.md#decision-assistant)
owns current summary/chat requests/responses/errors/lifecycle. Existing C08 remains the
structured explanation in §15.3. ADR-001/004/011/020–022 govern retained authority.

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

CURRENT FACT L3.2 WIP, after L3.1 checkpoint44b451893e7cc4735b6d79d9410db1ba95e0dcac: AS03 keeps its route and authority/lifecycle.
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

Most recently evaluated V5 source0e3199d201853962b40222d3f11079309b8779286e36a8023b3978227eb3a8b5
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
original raw22/27 and V5 outcomes are unchanged. Current source2e06f304 live
acceptance is PENDING because shared attempts are exhausted; no V6 paid call.
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
L2 summary still rejects all free provider assertions by schema and only uses
presentation ordering/tone. Chat transport/prompt/validation do not change it.
Explanation of existing verified Runs needs no merge from data-readiness/challenger;
new data admission/forecast quality evidence remains separately scoped.

Shared integration files with readiness/challenger: Planning contract, CURRENT_STATE,
ROADMAP, app/main.py, app/config.py/.env.example, model registration, scripts/dev.py
guards and runbook. Assistant also touches retained Planning validators/reader,
planning_public and body limits. Reconcile these deliberately at integration;
no manual copy of readiness WIP or dependency on challenger promotion.
