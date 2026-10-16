# FE 018/019 — backend mutation recovery audit

16/10/2026. Scope: BE only; CURRENT FACT means source trace or the explicitly named
fresh verification below, not deployed/FE acceptance. New contracts below are
PROPOSAL, not approval to implement. Canonical workflow owners remain
[Authorization](../AUTHORIZATION_CONTRACT_VI.md),
[Import](../IMPORT_MAPPING_API_CONTRACT_VI.md),
[Planning](../PROCUREMENT_API_CONTRACT_VI.md),
[Inventory/recipe](../API_CONTRACT.md), and
[Notifications](../NOTIFICATION_API_CONTRACT_VI.md).

## Source, runtime and evidence

- Source baseline: local main/HEAD `8b0968562438a1558fb189e0ab18bfabbe0cd5a9`.
  Work is uncommitted on `feat/mutation-recovery-fixes` in the main checkout.
  Existing untracked 018/019 reports and `dts/` are preserved. No sibling worktree
  integration, fetch/pull/push, commit, restart or demo migration.
- FE pins `869eaec914aa6905d6b935889afebe7d973004ae` and OpenAPI SHA256
  `790443d80350cc597c7c06179309e43303ba558de34017ea1dd4113de71fc1ee`.
  Generated baseline OpenAPI equals the preserved handoff structurally: 73
  operations/66 paths. Different source SHA does not establish API mismatch.
- Local `runtime/local/private/server.json` records source `b0db90c...`; worker
  observation belongs to that recorded run. These files do not prove present
  liveness, current deployed OpenAPI or database schema. No live business calls
  or demo changes were made to resolve that uncertainty.
- 018 and 019 were read. Linked `FE_ask/019_Freeze_Integration_Gaps.md`,
  `FOUND_MISSING_UI.md`, coverage/verification inventories and the described reload
  image are not supplied in this checkout/request attachment. Their detailed UI
  findings and screenshots remain unverified; the explicit 018/019 findings below
  are independently auditable. Assistant/curated-template WIP stays excluded.
- Verification owns a new Compose project/volume `shelfcash-fe019-recovery`,
  PostgreSQL17 at `127.0.0.1:5440`, allowlisted `shelfcash_local_test`, role
  `shelfcash_local_tester` without superuser/CREATEDB/CREATEROLE/BYPASSRLS.
  URL/role/target are checked before connecting; `scripts.dev.validate_reset_target`
  and supported fixture reset/migration apply. No allowlist bypass. Providers and
  all background worker flags are OFF; explicit test worker calls/fake delivery only.
  Other test/development/demo databases are untouched. Private setup is excluded
  from the review ZIP.

## Findings

| Finding | Classification and evidence | Outcome |
| --- | --- | --- |
| Delayed same-key review confirmation races with canonical completion | Reproduced BE bug: `ImportStaging.confirm_review` rechecks completion before its second receipt lookup, after releasing the first transaction for read-set capture. Regression first returned 409 `IMPORT_STATE_CONFLICT` despite a committed matching receipt. | Move only the completion guard after receipt replay; current authorization, preview integrity and required write checks still precede replay. One review audit/receipt and canonical row, exact retained result/ETag. |
| Worker post-commit exception handling | Reproduced BE bug: `ImportStaging.run_one` swallowed a synthetic `RuntimeError` after real canonical commit (`DID NOT RAISE RuntimeError`); Import §10 requires programming errors to remain errors. | Only recognized SQLAlchemy/psycopg uncertain errors raised by the canonical COMMIT can reconcile through fresh retained completion/job proof. Reuses the existing `_is_uncertain_commit` classifier; no new retry framework. Completed state stays completed; error surfaces to worker logging. |
| Fingerprint presence wording | Contract/source discrepancy: Import §10 describes presence-sensitive body digest; `ImportStaging` validates then uses `model_dump`, which fills optional defaults. Actual DTO + `_request` comparison shows omitted Commit.reason and explicit null have the same fingerprint. | Preserve exact wire replay in FE. No fingerprint migration/compatibility change made. Clarify which optional defaults must be distinguished before changing persisted receipt semantics. Evidence is serializer-level, not another PostgreSQL mutation test. |
| Reload loses original intent | Missing public discovery capability for logical intent, not proof of rollback. 018/019 explicitly retain only in-memory intent. All receipt keys are digests; tracing IDs are not lookup keys. | Use operation readers where identities survive. Do not invent key/body or clear uncertainty after denied replay. No generic status endpoint added. |
| Accepted-file delete/replace/unseal | Unsupported new lifecycle. `ImportStaging.upload/analyze`, immutable blobs/files, sealed analysis and Import §9.1a intentionally preserve accepted bytes. | Existing alternative: explicitly create another draft/upload; it does not cancel an uncertain old mutation. Delete/unseal would need invalidation/quota/provenance/concurrency policy. |
| Resolver immediate create+bind | Partly available, partly new capability. `ImportStaging.resolve`, `new_entity_proposal` and Import §6.1 retain Product/Ingredient proposals/reserved IDs for atomic canonical commit. | FE can use descriptor-supported staged creation/binding now. Immediate independent canonical create/bind before batch commit is not the same contract and is unsupported. No generic CRUD added. |
| Separately saved Preview decisions | Separate review confirmation exists (`I05 confirm_review`, retained in I04); domain correction resolutions are frozen in accepted commit input and completion audit. Standalone editable decision persistence is unsupported. | FE can resume persisted review; do not imply every unsubmitted domain choice is saved. A separate save lifecycle needs pins/invalidation and current-rights decisions. |
| Today outlook/pending decision | `TodayReads.read` / D01 already exposes authorized operational sections and latest Run; C03 retains an accepted Run's forecast/result. No pending procurement decision/arrival/AI model exists. | Synchronize supported D01/retained Run semantics. Live outlook, arrivals and customer decision state are new features; do not rename latest Run as pending decision. |
| Email-token distinctions/authenticated continuation | Approved current behavior: `EmailVerification.complete` collapses invalid/expired/consumed proof to `EMAIL_VERIFICATION_TOKEN_INVALID`; N7 similarly uses `CREDENTIAL_TOKEN_INVALID`. A05/N7 create no session. | Explicit A01 then A03/T01 is supported. Rich public token-state discovery or automatic session continuation is a new security/product contract, not a reproduced bug. |
| FE synchronization/design | 019 says PR01/PR04 and IN01 action UX remain service-only; EX01, D01, MQ and staged entity proposals already exist. | UI availability is independent of BE capability and deployment. No FE source was inspected/changed; implementation claims here are attributed to supplied reports. |

## Recovery matrix — CURRENT FACT source trace

All paths below include `/api/v1`. **K** = original key/body/CAS retained by client;
**L** = key/body lost. Readers report present or retained state, not a negative
certificate. Unless explicitly noted, receipt storage has no TTL/expiry field and
no automatic purge path; that is current implementation, not a future retention SLA.
Synchronous mutations have no public pending receipt: uncommitted/in-flight requests
are not publicly distinguishable from absent/rolled-back/not-yet-arrived requests.
Current User/session/Store/membership/rights precede replay; later denial never
proves the previous intent had no effect. Reads can show newer state than a receipt.

| Operation; exact method/path | Key scope and fingerprint | Atomic storage / concurrent and replay behavior | Authoritative recovery with K / with L; authorization limits |
| --- | --- | --- | --- |
| T03 `POST /stores` | Required visible ASCII1..128; account actor + key digest; canonical validated name/timezone/currency JSON, no CAS. | `store_creation_receipts` + Store/OWNER + `auth_audit` in one transaction; User fence serializes same key. Replay201 original Store; different body409 `IDEMPOTENCY_CONFLICT`. Immutable receipt/no TTL. | K: exact POST, including after new login. L: T01 `GET /stores` then T02 `GET /stores/{store_id}` locates currently accessible Stores, not the originating intent. Current Owner required on replay; foreign actor key is a different namespace, not discovery. Missing/inaccessible Store404 is not no-effect. `StoreCreation.create`, `StoreCreationRepository.receipt/create`. |
| N13 `PUT /stores/{store_id}/memberships/{membership_id}/permissions` | Required nonblank key≤128 UTF-8 bytes; actor+Store+exact target route; body + normalized If-Match membership version. | `staff_request_receipts` + grants/revision + `permission_events` + notification intent atomic. Store/member fences; replay200 retained before checking stale CAS, never reapplies grants. No-op also receipts. | K: original PUT. L: N12 `GET /stores/{store_id}/memberships`, N14 `GET /stores/{store_id}/permission-events`; current grants/audit do not uniquely recover caller key. Owner-only; inactive target409, revoked Owner/foreign Store denied. `StaffUseCases.replace/_request/_old/_save`, `change_grants`. |
| N15 `POST /stores/{store_id}/staff-invitations`; N17 `POST /stores/{store_id}/staff-invitations/{invitation_id}/actions` | Same Staff key family; actor+Store+route; actions include action name in receipt namespace; body + If-Match for N17. Token stored hashed; email intent encrypted. | `staff_request_receipts` + invitation/event/delivery intent atomic; Store fence serializes; replay returns original receipt, does not resend/reissue/revoke again. Offer expires after7 days; delivery expiry follows offer, receipt has no TTL. | K: exact original mutation, current Owner. L: N16 `GET /stores/{store_id}/staff-invitations` (invitations/events filters), original ID if retained. Current state/delivery may differ from receipt. `StaffUseCases.create/action/_owner_rate`; throttle429 is not old-intent no-effect proof. |
| N19 `POST /staff-invitations/{invitation_id}/accept`; IN01 `POST /staff-invitations/{invitation_id}/decline` | Staff key family; actor+invitation route+Store; proof token hashed in fingerprint + body + original normalized If-Match. | `staff_request_receipts` + terminal/event atomic; accept also exact membership/grants. Sorted recipient/issuer User, Store and invitation locks serialize accept/decline/revoke. Accept first201/replay200; decline200; no grants reapplied. | K: same proof/body/key/CAS; current holder/session/email proof/Store. Accept replay requires active accepted membership; decline replay checks current issuer authority/catalogue. L: N18 `GET /staff-invitations/{invitation_id}` additionally requires `X-Invitation-Token`; without proof, N16 only available to Owner, T01/T02 only shows resulting accessible membership, not holder terminal proof. Expired/revoked410 and proof404 do not certify old outcome. `StaffUseCases._recipient/accept/decline/offer`. |
| PR01 `POST /stores/{store_id}/permission-requests`; PR04 `POST /stores/{store_id}/permission-requests/{request_id}/actions` | Required UUID key; Staff receipt actor+Store+route; submit body includes expected grants/catalogue; action digest body + supplied If-Match, checked normalized version. | `staff_request_receipts`, `permission_requests`/audit and notification intent; approval union/grants event same transaction. Store/member fences; replay retained result before stale CAS, no repeated union. One pending request/member. No TTL. | K: exact POST. L: PR02 `GET /stores/{store_id}/permission-requests`, PR03 `GET /stores/{store_id}/permission-requests/{request_id}`; Staff sees own, Owner Store scope. Approve/reject Owner; cancel requester; inactive target blocks even replay. Satisfied/invalid reconciliation may persist lifecycle audit before409, so blanket “4xx means no writes” is false. `PermissionRequests.submit/action/_receipt/reconcile_member`. |
| MQ01 `POST /imports/{import_id}/mapping-submissions` (submit/withdraw) | Required UUID + import If-Match; actor+Store+import route. Body includes profile/proposal/mapping/lifecycle/active pins or submission version; digest includes supplied match. | `import_receipts` + `mapping_submissions` + import audit/notification intent atomic. Store/batch fences and one submitted/profile; replay original submission before stale batch CAS. No TTL. | K: exact POST. L: MQ02 `GET /stores/{store_id}/mapping-submissions` filters/paging, MQ03 `GET /stores/{store_id}/mapping-submissions/{submission_id}` evidence; I04/M01/M02 current context. Staff own batch/submission, Owner Store scope, current pinned domain reads/propose rights. `MappingSubmissions.mutate/authority/drift`. |
| N5 `POST /stores/{store_id}/mapping-profiles/{profile_id}/decisions` | Required UUID + lifecycle If-Match; actor+Store+profile route; body includes action/proposal/active/submission pins. Absent optional C2 pins excluded to preserve older digest. | `import_receipts` + version/activation/rejection/lifecycle + audit + queue decision/notification atomic. Store/batch/profile fences; retained replay before CAS. Owner self-proposal approval allowed. | K: exact POST. L: M01 `GET /imports/{import_id}/mapping-summary`, M02 `GET /imports/{import_id}/mappings`, MQ02/MQ03 when submitted. Activation is not canonical import commit. Owner-only including replay. `ImportStaging.decision`, `MappingSubmissions.decision_target/finish_decision`. |
| M04 `PATCH /imports/{import_id}/mappings/{mapping_id}` | Required UUID + mapping If-Match; actor+Store+import+mapping route; typed resolution body + normalized match. | `import_receipts` + batch issues/proposal/binding/revisions/audit atomic; batch fence; same receipt before stale CAS, no repeat creation proposal. Preview/confirmation invalidation retained in batch. | K: exact PATCH. L: I04 and M01/M02 plus M03 `GET /imports/{import_id}/sheets/{sheet_id}/field-options`; current issue/reservation state may have advanced. Current mapping.propose + relevant source reads; own-batch sheet ignore fence preserved. `ImportStaging.resolve/_resolve_shared/_select_sheet`. |
| I03 `POST /imports/{import_id}/analyze` | Required UUID + import If-Match; actor+Store+import/analyze route; file_set_version, exact accepted IDs/rejected ACK set and original CAS. | `import_receipts` + seal/analysis identity + queued `import_jobs`/audit atomic. Batch fence; replay same acceptance even when job completed/failed. No receipt TTL. | K: exact POST; L with import ID: I04 `GET /imports/{import_id}` exposes lifecycle/active job; J01 `GET /jobs/{job_id}` if ID known; H01/H02 discover visible imports if import ID also lost. Worker current original session/rights; dead-process recovery marks failed without automatic recompute. `ImportStaging.analyze/_accept/run_one/recover/read/job`. |
| I05 `POST /imports/{import_id}/process`, phase=preview | UUID + import If-Match; phase-specific `import_receipts` namespace; body mapping_revision + normalized CAS. | Acceptance receipt/job/batch atomic; worker separately retains `import_previews`, batch reference and terminal job. queued/running/completed/failed; replay returns original queued acceptance, not latest preview. | K: exact POST then job/readback. L: I04 include_preview with explicit preview pin for rows, J01 when ID known; historical H01/H02 for batch discovery. Current import.preview and source read fences; failed job is not proof about another delayed intent. `ImportStaging.preview/_run_one/read`. |
| I05 same path, phase=confirm_review | UUID + import If-Match; phase namespace; preview ID/digest, mapping revision, confirm/reason + CAS. | `import_receipts` + retained confirmation, batch revision/audit atomic. Two-transaction source capture with current-rights recheck; fixed delayed same-key replay precedes completion/CAS guard. No pending receipt/TTL. | K: exact POST original pins; L: I04 retained confirmation if authorized. A new key after completion still conflicts. Replay current import.commit + required actions and source reads. `ImportStaging.confirm_review`. |
| I05 same path, phase=commit | UUID + import If-Match; phase namespace; preview/digest/confirm/reason/domain resolutions + original CAS; effective plan digest includes retained confirmation. | Acceptance receipt/job/commit_id/batch atomic; canonical effect + completion/job/audit later atomic in worker, under canonical table and authority fences. Replay202 original acceptance; not evidence canonical commit finished. | K: exact POST, then J01/I06 `GET /imports/{import_id}/completion`; L: known batch I04/I06, or paged H01 `GET /stores/{store_id}/imports/calendar`, H02 `GET /stores/{store_id}/imports`. Completion missing409 is not terminal negative. Current full write set on acceptance/replay and read/write set at worker; retained read requires current domain rights. `ImportStaging.commit/_commit_preview/_execute_commit/completion`. |
| N6 `POST /stores/{store_id}/inventory/receipts`; Excel inventory_receipts through I05 commit | UUID; N6 actor+Store+N6; normalized body (includes expected_inventory_version); additionally Store+source_system_key+source_record_id business identity, normalized facts digest excludes transport CAS. Import uses its phase key/preview pins. | `stock_request_receipts` + `inventory_receipt_records` + lot/movement/audit atomic; Import includes same writer in batch transaction. Source same facts replay even new key; different facts409 `RECEIPT_IDENTITY_CONFLICT`. Store/canonical table fences. | K: same N6 or original Import commit; L: V01/V02/V03/V04 inventory/movements, I06 for imported receipt. No public source-identity receipt finder; lot_code/name not unique. Current receive/read/ingredient rights; nonnull cost requires cost.read, retained projection masks cost after revocation. No re-receipt with invented source key. `StockWrites.receive/_run`, `InventoryReceipts.replay/create`. |
| N1 `POST /stores/{store_id}/planning-requirements`; N3 `PUT /stores/{store_id}/planning-requirements/{saved_requirement_id}`; N4 `PUT /stores/{store_id}/planning-budget` | UUID; actor+Store+create/update target or budget; presence-sensitive body + supplied match/none. N1 no CAS; N3 quoted version; N4 exactly one If-None-Match:* create or If-Match update. | `planning_configuration_receipts` + current saved/budget + revision/event atomic; Store fence; replay retained detail and original201/200 before stale CAS, no repeated update. No TTL. | K: exact write. L: C01 `GET /stores/{store_id}/planning-context` saved/budget context, N2 `GET /stores/{store_id}/planning-requirements/{saved_requirement_id}` detail. Current requirements/budget read+write; Staff manage own saved only. Later config is not original receipt. `PlanningConfigurationWrites.write/_replay/_authorize`. |
| N21 `POST /stores/{store_id}/products/{product_id}/recipe-schedule/changes`, preview/commit phases | UUID + quoted schedule If-Match; actor+Store+Product+phase; normalized body+version; commit includes change_id/preview_digest/warning ACKs. | `recipe_schedule_request_receipts`, preview/change row; commit recipe assignments/new content + retained receipt/audit same transaction; calendar fences. Same receipt before stale/date checks. No TTL. | K: original phase request; L with change_id: N22 `GET /stores/{store_id}/products/{product_id}/recipe-schedule/changes/{change_id}`; without ID N20 timeline only current calendar, no change discovery collection. Current menu/recipe read/manage plus create_version when new content. `RecipeSchedule.change/_commit/read_change`. |
| C02 `POST /stores/{store_id}/procurement-plans` | UUID; actor+Store+C02+key digest; presence-sensitive original request with exact numeric canonical digest; no client CAS header, explicit config versions in request. | `planning_runs` typed aggregate contains original/resolved request and receipt atomically; unique scoped key/ON CONFLICT plus authority fences; queued/running/completed/failed. Replay original acceptance before new config resolution. Indefinite retention ADR-022. | K: exact POST then C03 `GET /procurement-plans/{plan_id}`. L: paged N9 `GET /stores/{store_id}/procurement-plans`, creator/date/retained budget filters; match candidates, not name/date proof of original intent. Current RUN_PERMISSIONS, retained result/cost rights; worker original session rights; proven-dead owner recovery fails without recompute. `PublicPlanning.accept/read`, `PlanningRunUseCases.accept/_write`. |
| N10 `POST /procurement-plans/{plan_id}/exports` | UUID; actor+Store+Run+key digest; Run ID + typed export body (option/format). | `planning_exports` acceptance aggregate/receipt/job_id atomic, private artifact publication later; unique key/Store fence; queued/running/completed/failed. Replay original acceptance before renderer check; no retention TTL. | K: original POST then J01 and N11 `GET /procurement-plans/{plan_id}/exports/{export_id}`; L with Run ID: EX01 `GET /procurement-plans/{plan_id}/exports` with status/option/paging. Current export/result/budget/cost rights at acceptance/replay/worker/download; verify bytes/hash, no arbitrary URL. `PlanningExports.accept/_reconcile/job/download`, `PlanningExports.discovery`. |
| NF03 `PATCH /notifications/{notification_id}` | UUID; actor+notification+key digest; read boolean + exact quoted If-Match. | `notification_read_receipts` + own notification read_at/revision atomic; User/notification fences; no-op retained too. Replay returns original read state even if later toggled; no business decision. No TTL, immutable receipts. | K: same PATCH; L: paged NF01 `GET /notifications`, NF02 count/snapshot; inspect own notification current read state, not historical key. Current own recipient and Store access; object link separately reauthorized. `Notifications.read/_scope`, `NotificationRepository.own_notification/read_receipt`. |

## Failure and absence semantics

CURRENT FACT: request_id is transport tracing, Idempotency-Key identifies a scoped
logical intent, resource/job/commit IDs identify durable objects; none substitutes
for another. A server ID lost with the only response does not solve discovery.

An authentic validation/CAS/permission error may establish that **this invocation**
did not apply its business effect at that fence. It does not establish no earlier
same-key commit, no concurrent/late request, or no ancillary rate/audit/session
write. Examples: replay403/404 after revoke, consumed proof400, current CAS412,
receipt-conflict409, completion-missing409 and empty lists are not negative outcome
proof. Network/5xx/timeout remain unknown. No generic pending/failed/absent receipt
API, cancellation/fencing terminal, receipt-expiry response or key tombstone exists.
Absent receipt and “not yet dispatched” cannot be distinguished externally.

T03 late-arrival regression deliberately observes empty T01 and absent receipt,
then allows the old intent to create/commit. This is evidence against negative
inference, not an implementation of negative certification. Retained successful
receipts survive current state changes; N13 replay must never restore later removed
grants. Import queued acceptance, canonical completion and process-interrupted
failure are separate outcomes.

Public auth is separate: A02/A06/A07 generic202 intentionally hides account/email
existence and means durable accepted delivery workflow, not mailbox delivery.
`EMAIL_DELIVERY_UNAVAILABLE`503 is the documented service-wide preacceptance failure
for those operations; it says nothing about an earlier different attempt. A05/N7
one-use proof may have committed before response loss; invalid replay does not undo
verification/password. Explicit login with holder-chosen credentials is available;
no public recovery returns account existence, passwords, tokens, encrypted intent
plaintext or secret-bearing request bodies. A01/A04 session transitions use their
own rules, not generic business mutation replay. Invitation proof is never journaled
through the proposals below.

## Verification and limits

Selected coverage: fresh PostgreSQL Store/Owner/receipt, grants/event and Import
canonical state; lost ACK injection, exact replay/conflict/concurrency, revoked
authority and foreign resources; Import process death and competing workers;
affected public OpenAPI. No full suite or deployed/whole-FE/browser acceptance claim.
DB fixture resets only the dedicated test database between tests.

Commands run from backend with `.venv/Scripts/python.exe -B`. Temporary ignored
`runtime/fe019/run.py` reads the private URL without printing it, validates the
exact dedicated target/limited role, disables providers/workers, then invokes the
listed command. It is included sanitized in the review package for reproducibility;
credentials are not. Final supported command
`.venv/Scripts/python.exe -B runtime/fe019/run.py -m scripts.dev status --test-database`
passes: dedicated limited role, current head `f4_20261016_metadata_v2`, empty business
tables after fixture cleanup. Final `git diff --check` passes. OpenAPI structural
comparison before/after/FE pin passes with zero delta (73/66); canonical JSON SHA256
is `7a6d13ca1e7bafdee247504e9a0fa131c28c9796a0436691dfa309a847fbd366` for both
before/after. Markdown relative links in this report and57 exact route references
were checked against source/OpenAPI (the explicitly proposed route is excluded).

Executed commands (prefix for each: `.venv/Scripts/python.exe -B runtime/fe019/run.py -m pytest`;
every run also uses `-q --tb=short --show-capture=no` and
`--junitxml=runtime/fe019/<receipt>.xml`). Runs overlap; counts are not additive
independent acceptance totals.

| Receipt | Exact targets/additional options | Result |
| --- | --- | --- |
| review-before | `tests/integration/test_import_commit.py::test_concurrent_review_replay_after_canonical_commit_keeps_receipt` (before parametrization/fix) | 1 failed, expected200/actual409; real durable confirmation and canonical completion. |
| review-after | Same target after guard-order fix, before parametrization | 1 passed. |
| focused | `tests/integration/test_import_commit.py tests/integration/test_store_creation.py tests/integration/test_staff_public.py::test_grants_http_cas_replace_empty_noop_retry_current_authority tests/integration/test_staff_public.py::test_grants_lost_ack_replay_preserves_later_change_and_current_authority tests/integration/test_collaboration_boundaries.py::test_queue_concurrent_decisions_lost_ack_and_submission_cas tests/integration/test_collaboration_boundaries.py::test_current_staff_session_and_catalogue_fences tests/api/test_store_creation_openapi.py tests/api/test_import_openapi.py tests/api/test_staff_openapi.py -k 'not receipt_retention_schema_parity'` | 41 passed, 1 deselected, 224.09s; before worker exception fix. |
| worker-before | `tests/integration/test_import_commit.py::test_programming_error_after_durable_commit_is_not_reconciled_as_success` | 1 failed: programming error swallowed; fresh DB commit executed. |
| worker-after | `tests/integration/test_import_commit.py::test_programming_error_after_durable_commit_is_not_reconciled_as_success tests/integration/test_import_commit.py::test_uncertain_commit_after_durable_write_reconciles_without_repeat tests/integration/test_import_commit.py::test_lost_commit_acceptance_ack_reload_readback_and_exact_replay tests/integration/test_import_inventory_supplier.py::test_mixed_commit_lost_ack_is_reconciled_and_public_count_scope_invalidates_on_new_lot tests/integration/test_import_staging.py::test_completed_job_programming_error_is_not_success_or_failed tests/integration/test_import_staging.py::test_uncertain_acceptance_is_error_then_retry_reads_durable_receipt` | 6 passed, 73.32s. |
| security | `tests/integration/test_import_commit.py::test_concurrent_review_replay_after_canonical_commit_keeps_receipt tests/integration/test_import_classification.py::test_confirmation_stale_wrong_digest_and_current_revoke tests/integration/test_import_classification.py::test_confirmation_concurrent_receipt_and_new_preview_requires_review_again tests/integration/test_import_classification.py::test_staff_confirmation_checks_current_write_scope_and_retry_without_owner_approval tests/integration/test_import_classification.py::test_review_persistence_failure_rolls_back_confirmation_and_audit tests/integration/test_staff_public.py::test_owner_only_cross_store_filters_and_headers tests/integration/test_permission_requests.py::test_concurrent_winner_lost_ack_replay_and_membership_revoke tests/integration/test_mapping_submissions.py::test_withdraw_and_retirement_history tests/integration/test_notifications.py::test_visibility_account_store_switch_foreign_revoke_replay_and_suppression tests/unit/test_application_contracts.py::test_application_has_no_http_or_direct_queries tests/api/test_health.py::test_only_intended_routes_exist` | 10 passed, 2 failed, 57.82s: new revoke-test missing import (corrected below), unchanged baseline architecture debt (not corrected here). |
| affected-final | `tests/integration/test_import_commit.py::test_concurrent_review_replay_after_canonical_commit_keeps_receipt tests/unit/test_forecast_commit_errors.py tests/api/test_import_openapi.py` | 21 passed, 12.96s; both delayed review variants (normal/revoked), existing supported-stack classifier and OpenAPI. |
| process-final | `tests/integration/test_import_commit.py::test_actual_process_death_after_claim_requires_explicit_retry_not_double_write tests/integration/test_import_commit.py::test_two_actual_workers_claim_only_one_commit` | 2 passed, 13.43s after final source fix. |

Two preexisting lost-ACK injections used RuntimeError as a transport failure. They
now inject SQLAlchemy OperationalError wrapping psycopg OperationalError with
connection_invalidated=True, preserving their full canonical/audit/receipt assertions.
The separate programming-failure regression proves the runtime change; this is
not weakening data assertions or changing production fixtures to conceal a defect.

TECHNICAL DEBT: the architecture guard fails on committed
`planning_challenger.py` direct Session queries at146/148. Both that file and the
guard test equal HEAD after Git line-ending normalization; applying the same AST
guard to committed source reproduces146/148. Source/test were not changed here.
This is unrelated existing main debt, not a passing gate or an exemption added by
this task. `runtime/fe019/baseline-drift.json` retains sanitized comparison evidence.

Known test drift (deselected, not executed): `test_receipt_retention_schema_parity_and_no_destructive_downgrade`
hard-codes0027 as current head although main already has
`f4_20261016_metadata_v2`. Its downgrade crosses the F4 constraint and then hits the
retained Store guard; this task does not rewrite historical migration intent or
claim that stale head assertion passed. No migration/schema source change here.

Fault injection after real Session.commit and fresh Session assertions prove durable
rows; recreating ImportStaging proves no in-memory service dependence. Neither is
an actual backend process restart. The separately named preexisting Import
process-death test launches a child, verifies exit86 and retained running claim,
then explicit recovery/retry. T03/N13 native process crash acceptance is not run.
Receipt TTL expiry cannot be tested as a product state because no TTL exists.

I01/I02 are additional existing recovery capabilities: `POST /stores/{store_id}/imports`
requires UUID key, actor+Store+create-draft namespace, typed data_date body;
`POST /imports/{import_id}/files` requires UUID key, actor+Store+batch/files namespace,
ordered client IDs + filename + actual byte length/SHA256 fingerprint. `import_receipts`
is atomic with draft or upload metadata/blob/quota/audit. Exact upload replay is
checked before seal, while changed client identity/content conflicts. I04 metadata
and paged H02 are readers if client IDs/batch identity survive. Current create/upload
rights precede replay; no public raw-file/key finder or cancellation is implied.
018's generic mutation helper excludes I02 replay; that FE helper limitation does
not remove BE's existing multipart replay contract. Raw files are not proposed
for intent-journal storage. Source: `ImportStaging.create/upload/_request/_old`.

Public/token route audit (no business receipt-discovery API):

| Exact method/path | Atomic state, retention and recovery boundary |
| --- | --- |
| `POST /api/v1/auth/register`, `POST /api/v1/auth/email-verifications/request` | No Idempotency-Key; normalized email/rate guard, account/EMAIL_VERIFY digest+encrypted delivery intent/audit atomic. Proof30min, resend60s; no receipt TTL/public account discovery. Generic202, current provider-wide unavailable503; no session/Store. Same body can represent resend, not exact mutation replay. `EmailVerification.request`. |
| `POST /api/v1/auth/password-reset/request` | No key; account-scoped RESET digest/revision/encrypted delivery intent/audit atomic; proof30min/resend60s. Generic202, no password/session change until N7. `PasswordReset.request`. |
| `POST /api/v1/auth/email-verifications/complete`, `POST /api/v1/auth/credentials/complete` | No key; one-use proof/password body; User/account/proof fences, consume+credential transition/audit atomic; N7 revokes sessions. No retained secret-bearing request or replay result. Expired/consumed/mismatched proof shares invalid code; recover by explicit holder login or authorized new proof workflow, never infer no-effect from invalid retry. `EmailVerification.complete`, `AuthUseCases.complete`. |
| `POST /api/v1/auth/login`, `POST /api/v1/auth/logout` | No key; login credential verification+new session/audit, cookie may be lost with response; GET A03 can observe only the presented cookie. Session idle30min/absolute8h, remember7d/30d; logout revoke and cookie clear, repeated logout204 under Origin rules. No account/session enumeration or generic replay. `AuthUseCases.login/logout/_resolve`. |

## What FE can use now; proposals requiring decisions

CURRENT FACT: exact original key/body/CAS replay after current authorization;
operation readers in the matrix; I04 persisted review, I06 completion, PR/MQ queues,
N9 history and EX01 export discovery. Always page fully with current snapshots;
refresh current state separately from retained success. Do not retry with new keys
to resolve unknown outcomes. New session may permit replay with preserved intent;
accepted workers still have their own original-session authorization boundary.

| PROPOSAL (not implemented) | Concrete minimal contract, scope and retention | Absence/late-request/duplicate limits; decision needed |
| --- | --- | --- |
| FE pre-dispatch intent journal | Actor/Store/operation/resource, original key/CAS, payload fingerprint, timestamp; persist before dispatch and block unresolved competing writes after reload. Exclude passwords/email/invitation proof/tokens/raw uploaded cells. Exact replay only if an explicitly approved per-operation safe original body also survives; a hash cannot reconstruct it. Retain unresolved entries until positive reconciliation or explicit reviewed handling; current auth always required. No BE API delta. | Protects same intent only if journal write completed first; no negative certificate and no remote cancellation. Decide allowed body fields/storage/logout/shared-device retention with FE; BE does not implement FE here. |
| T03-specific committed creation discovery | Proposed `GET /api/v1/store-creations?limit&cursor`; authenticated verified holder only; return own retained `{creation_reference,store_id,created_at}` only while current Owner of active Store. No raw key/body/email and no foreign-actor lookup. Existing receipt lifetime, no invented TTL; scope-bound pagination and no forbidden counts. Existing T01 may already suffice for product needs. | Positive committed evidence only. Empty page/inaccessible receipt remains unknown; no pending record and no guarantee which lost intent a candidate belonged to. Decide whether additional creation reference/history is useful beyond T01; no endpoint added. |
| Scoped status with definitive negative outcome, only if required | Requires a separately approved preaccepted operation-specific intent identity, immutable payload digest, same current actor/Store authority, durable state machine and server-side terminal tombstone. Execute and abandon must lock/fence the same identity atomically; late dispatch must reject an abandoned identity. No generic auth/token/request-body recovery. Tombstones must be retained indefinitely unless an approved nonreusable-key expiry protocol proves late requests cannot execute. | A GET absence alone never fences. Terminal negative requires an atomic state-changing fence, duplicate protection and business-specific worker races/rights/retention tests. Decide need for explicit abandon/expiry and UX; materially new policy, not a bug fix or generic manager to implement now. |

Other feature dependencies: file removal needs provenance/quota/seal invalidation;
immediate resolver canonical writes need create authority and rollback identity;
saved domain decisions need read-set pins/invalidation; Today pending decisions need
an approved decision aggregate; richer public token states/session continuation need
anti-enumeration, holder proof and session-switch policy. None is authorized here.
The missing FE linked files are needed only to refine their concrete UI scenarios,
not to decide the proven recovery fixes.

Review delivery: ignored `runtime/shelfcash_FE019_recovery_review.zip` contains only
the changed source/tests/canonical docs, this report, sanitized verification receipts,
OpenAPI equality/delta evidence, guarded disposable setup/runner and SHA256 manifest.
Original files/private runtime are retained; no credentials/cookies/DB dump/raw private
data. ZIP CRC, per-entry hashes and exclusion/secret scans must pass before delivery.
No commit/merge/push/deploy/FE edit/SMTP/OpenRouter call is part of this work.
