# Decision Assistant evidence foundation

CURRENT FACT L1: immutable internal `decision_evidence/1` and pure projections
exist; no HTTP summary/chat route, model call, generation, persistence or new grant.
The [Planning contract §18](../PROCUREMENT_API_CONTRACT_VI.md#decision-assistant)
owns the proposed FE requests/responses/errors/lifecycle. Existing C08 remains the
structured explanation in §15.3. ADR-001/004/011/020–022 govern retained authority.

## Internal boundary

`PublicPlanning.assistant_evidence(token,run_id,option_id=None,ingredient_id=None)`
reuses `read_record`: resolve owning Store, current actor/session/Store membership
and all READ_PERMISSIONS **before** loading aggregate content. Whole denial applies
to missing budget/cost rights. Every call repeats authorization, including cache
hits; the caller cannot submit authoritative facts/winner/proof. No route/composition
change exposes this internal method. Existing3MiB inspection bound still applies.

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

Evidence refs bind schema, Run/Store, aggregate/input/result/request identities,
versions and projection context. `resolve` accepts only issued IDs and resolves
their typed field pointer in that immutable bundle. Cross-Run/option/Ingredient
or changed-version refs are rejected. A field citation alone is not prose grounding.
Omissions explicitly exclude actual outcomes, probability/profit/causality and a
zero-purchase baseline from this projection; no extra business calculation exists.

## Cold verification limit and drift

CURRENT FACT / TECHNICAL DEBT: architecture prose describes retained reads as not
calling the engine. Existing cold `decode_row` actually validates nested contracts
that call `expand_bom` and exact procurement `_evaluate`/serving and selector
reconciliation. It does not run native candidate search, but it does recompute
business checks. L1 preserves those existing callers and does not hide the drift
by weakening historical validation or changing ADRs.

Assistant L1 uses `VerifiedPlanningReads.read(require_cached=True)`: hash the entire
stored JSON and bind all identity/revision columns, then accept only a previously
verified terminal entry in the **same** reader cache. Cold/mutated/evicted entry
fails closed with503 EVIDENCE_NOT_VERIFIED (integrity mismatch has its own503).
No cold decoder, BOM, forecast, serving, procurement or selector is invoked on
this L1 path. Restart/entry eviction therefore removes evidence availability until
existing authorized retained reading independently verifies the aggregate. L1
does not trigger that reading as a hidden warm-up. Default cache has4 entries/16MiB;
oversized records are never cached. Evidence delivery remains bounded, not a latency
or capacity guarantee. L2 must explicitly resolve this availability limit before
promising general generation across arbitrary retained runs/restarts.

## Verification and remaining acceptance

CURRENT FACT: focused no-DB tests use hand-authored retained-read contract fixtures,
not generated PlanningRuns or real customer evidence. They exercise overview and
option/Ingredient projection, mixed units, exact fractions/display, cost components,
null/zero, exclusions/assumptions/warnings, no-winner/failed/partial/UNPROVEN,
foreign/dangling references, current-rights-before-materialization ordering and
revoked-session/grant denial on repeated application reads. Cache tests verify
misses avoid cold decoding and changed raw hashes cannot hit a verified entry.
No solver/provider/socket/SMTP/DB setup or training is required. These are unit
boundary oracles; mocked repository/auth collaborators are not PostgreSQL acceptance.

No dedicated Decision Assistant DB is configured/allowlisted in current guarded
tooling. L1 does not borrow/reset another worktree's DB or bypass those guards.
Real session/Store/grant concurrency, PostgreSQL fresh reads after live config or
catalog changes, and process/restart integration remain unverified. Existing C03
security tests are historical coverage, not a new acceptance run here. Runtime
OpenAPI comparison and related C03/C08 schema tests cover unchanged HTTP surfaces.

## Legacy review and future slices

HISTORICAL INFORMATION: read-only reference audit at
`D:\hocc_bk\ai\proj\projectAttacker2026\attackerBE\docs\LLM_REGRESSION_REVIEW_VI.md`
(legacy HEAD cac7c5a6a46c5751063be6b27866e3672acd2e2a), plus
`Forecast_Engine_FandB/shelfcash_legacy_review.zip` under the project parent.
The ZIP's overall_summary, FE explanation contract, schemas and CHAT-7/8 audit
were inspected as source only. No legacy runtime/import dependency/schema port.
Findings are offline regressions, not proof of comparative live wording quality.
Legacy recommendation_available/expected_fill_rate mismatches motivate typed
current C03 ProductService/service fields; no legacy aggregate fill field is made up.

TECHNICAL CHOICE: current OpenRouter mapping transport has no-redirect credentials,
deadline/timeout/response-byte/token/attempt bounds, strict JSON parsing and safe
typed diagnostics worth reusing in a future provider adapter. Its workbook payload,
mapping prompt/schema and mapping enable flag are task-specific. L1 does not extract
a generic gateway or alter mapping behavior. A future wording task must own its
profile, scoped allowlisted evidence and authorization before transport.

PROPOSAL next slices (separate authorization): L2 deterministic summary/fallback,
generation validation, idempotency/cache and bounded optional provider; L3 on-demand
chat/clarification/history; L4 approved fixed-evidence live evaluation with explicit
cost/attempt caps and raw/final diagnostics; L5 HTTP/FE/security/restart integration.
Prose coverage, unit repair, Vietnamese/English negation/paraphrase and no-winner
guards are acceptance requirements in the canonical contract, not implemented here.
Explanation of existing verified Runs needs no merge from data-readiness/challenger;
new data admission/forecast quality evidence remains separately scoped.
