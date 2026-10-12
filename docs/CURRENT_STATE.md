# Current state

## CURRENT FACT — mốc phát hành v1.0, 12/10/2026

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
own `shelfcash_test`; neither target is the development database.
See [the runbook](runbooks/FULL_TEST_FLOW.md).

CURRENT FACT: người dùng đã thử FE thật thành công ít nhất tới mapping lần đầu.
Điều này chưa chứng minh toàn browser flow import/planning end-to-end thành công.
v1.0 có rules canonical keys/aliases, approved-profile reuse và adapter OpenRouter
tùy chọn, không provider call lúc startup. Discovery hiện lấy dòng đầu làm header;
workbook có title/ghi chú trước headers chưa được xử lý đúng. Mapping/identity/
context lần đầu còn thủ công; task release không gọi LLM thật. Cải tiến import
được tách sau tag v1.0, không lẫn vào source của mốc này.

HISTORICAL INFORMATION: prior S4.11 verification recorded API/native-worker/fresh-
session/PDF/restart gates and twelve current-screen Edge gates. Those are previous
results, not a new run. Current FE has Import mapping/preview/confirm/commit and
planning C01-C05/C08 source. Whole mapping browser continuation remains NOT_RUN;
PDF and planning-history UI remain incomplete. S4.11 stays PARTIAL; API acceptance
cannot certify the whole UI. No FE repository changes are part of cleanup.

## TECHNICAL DEBT / known discrepancies

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
