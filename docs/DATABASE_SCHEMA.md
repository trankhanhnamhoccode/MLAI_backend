# Database schema — implemented cluster and Schema v1 proposals

## CURRENT FACT - L5 combined migration graph

Single source head `l5_20261016_assistant_f4` has parents0030_conversational_chat
and f4_20261016_metadata_v2; both descend from0027_self_service_stores. The merge
revision has no DDL, renumbering or reparenting. Four Assistant tables and metadata2
constraint from their original migrations coexist:75 application tables/76 with
Alembic. Base.metadata and schema comparison match. Old isolated counts/heads below
are historical component facts, not the combined current head. No demo migration.
Empty roundtrip/from-each-parent upgrades and retained metadata2/Assistant guard
rehearsals run only on owned disposable L5 PostgreSQL5441. Downgrade parent guards
refuse evidence loss; do not downgrade a populated customer/development DB.

## CURRENT FACT — isolated assistant L2 schema

CURRENT FACT L4.1 adds only internal retained version8 (selection8/prompt7/
validator8/resolver5, renderer9 for new deterministic receipts). Version7 and6
remain pinned with absent optional fields elided as before. Actual test factory
uses PlanningRunUseCases.accept/claim/retain/finalize with captured input/exact
pipeline and fresh read;20/35 outputs are computed, not JSON quantity patches.
No column, migration, trigger, endpoint, retained-row rewrite or default6 change.

CURRENT FACT L4 candidate keeps head0030 and all columns/triggers. Explicit
presentation7 generations pin selection7/prompt6/validator7/resolver5 and renderer8.
Internal grouped cards carry typed original members, exact semantic values and
reference union; optional presentation/group/product_id fields elide when absent,
preserving old canonical plan JSON. New model-OFF renderer8 receipts and model-ON
generation7 read through their retained versions, independent of current selection.
V6 remains default; no rewrite/backfill, new endpoint or migration.

CURRENT FACT L3.2 keeps head0030 and the existing tables/triggers. New JSON
generation records pin prompt/5, chat_assertions/6 and assertions/2, structured
request context, per-request completion/cost limits and final safe failure traces.
New JSON selection_version pins plan/6; absent means legacy plan/2 and is elided
on canonical serialization. Existing L3.1 proof receipts do not acquire new
eligibility obligations during replay. No migration is needed for this JSON field.
Plan/4-/5-/6 pin the resolved question; absent is elided for old hashes.
Old records use their pinned selector/renderer/grammar on read; serializers elide
new absent fields to preserve original canonical hashes. No data rewrite/backfill.

L3 conversational head0030_conversational_chat depends only on0029. All sibling
revision directories were inspected before choosing the unused revision; no head
merge or applied-migration edits. Additive chat_generations brings this worktree
to76 tables including Alembic. UUID PK, actor/Store/Run RESTRICT FKs, unique scoped
key digest, request/record SHA-256, status/created_at and typed chat_generation/1
JSONB pin request/profile/evidence/selection/prompt/schema/validator/process/claim.
Running→terminal alone can change status/time/output/result/error; triggers reject
all terminal UPDATE/DELETE and downgrade refuses retained rows. A completed final
assistant_message/2 receipt and terminal generation commit atomically; /1 receipts
are preserved, not rewritten. Short advisory key lock serializes legacy receipt
versus new provider acceptance across configuration changes, never across network.
Same key/body replays; different body409. Alive/unknown running claim409; OS-proven
dead claim is failed only on explicit replay and never reissues an unknown paid call.
Failed keys remain failed; explicit new key is deliberate new work. Recognized
applied lost ACKs reconcile exact retained claims/finals in fresh Sessions; unapplied
or unknown DB/programming failures do not fabricate success. Only assistant test DB
is migrated, with no business/PlanningRun mutation or other-worktree DB access.

L3 additive head0029_assistant_messages (parent0028) adds assistant_messages,
bringing this worktree to75 tables with Alembic. All sibling revision directories
were checked; no0029 collision observed at creation. Composite PK actor/Store/Run/
key digest owns AS03 idempotency. RESTRICT FKs, normalized request digest and typed
assistant_message/1 JSONB request/response plus record SHA-256; no provider secret.
All UPDATE/DELETE rejected by trigger; downgrade refuses retained rows. Replay
checks current rights, exact request, raw hash and current pinned deterministic
renderer/evidence before delivery. No conversation graph, job or mutable lifecycle:
deterministic result and receipt commit atomically. Lost ACK returns503; explicit
same-key retry safely reads or recreates one receipt. Only owned assistant test DB
is migrated; no other worktree/runtime DB is touched.

`0028_assistant_summaries` depends only on0027_self_service_stores. All registered
worktree migration directories were inspected before choosing the unused revision;
no other head/dependency is merged or edited. Additive2 tables,74 including Alembic;
only the owned assistant test DB is migrated, not main/demo/readiness/challenger.

plan_summary_generations retains id, actor/Store/PlanningRun RESTRICT FKs,
identity/record SHA-256, status, created_at and typed canonical summary_generation/1
JSONB containing pinned request/profile/evidence digest/process/claim and result.
Partial unique(actor,Store,Run,identity_digest) applies to running/completed rows;
explicit new-key retry after failure can create a new generation. Receipts retain
actor/Store/Run/key digest PK, request digest and generation FK. They do not store
raw keys, credentials or mutate PlanningRun/operational rows.

DB triggers refuse receipt updates/deletes and all terminal generation updates/
deletes; running→terminal retains acceptance/claim identity and permits only
status/finished_at/result/error changes. Application additionally verifies exact
hash/canonical/column identity, renderer facts/refs and current rights. Downgrade
refuses retained generation rows; no purge/backfill or migration of another DB.
Lifecycle semantics belong to [Planning §18](PROCUREMENT_API_CONTRACT_VI.md#decision-assistant).

HISTORICAL INFORMATION before L5: main source head `f4_20261016_metadata_v2`
follows0027 and only permits execution metadata schema2 alongside1 in the existing
`forecast_execution_metadata` check constraint. No table/column/backfill or existing
payload change. Downgrade refuses retained schema2 rows; an empty dedicated F4 test
DB can roundtrip to0027. Integration verified fresh upgrade, empty roundtrip and
retained metadata2 downgrade rejection on a new isolated PostgreSQL17 project/volume
on loopback5438. Development/demo/Assistant/import/old challenger DBs were not
migrated or reset. Source head integration does not apply migrations to runtime.
[Forecast integration](features/FORECAST_ENGINE_INTEGRATION.md#forecast-f4) owns
the private test-only payload semantics; public schema/permissions stay unchanged.

CURRENT FACT self-service: head0027_self_service_stores,71 application tables/72 tổng.
Additive store_creation_receipts: composite PK(actor_id,key_digest), request_digest,
Store RESTRICT FK/unique, immutable typed result JSONB và created_at. T03 Store,
OWNER membership, AuthAudit STORE_CREATED và receipt cùng transaction. UPDATE/DELETE
trigger giữ receipt; downgrade từ chối retained rows. Không backfill/seed hoặc sửa
old Store facts. Local customer DB mới riêng; demo0026 được giữ, không reset/migrate.

CURRENT FACT C4: không migration/table/column mới, head0026/71 tables giữ nguyên.
New immutable ImportPreview JSON pin source_evidence_digest/source_read_permissions;
rows/canonical/read-set semantics giữ nguyên. History budget đọc retained acceptance;
PDF discovery đọc retained exports và existing private bytes. Không backfill facts
hoặc migrate/reset demo/development/DB test nhánh khác.

CURRENT FACT C3: không DDL/migration mới; single head0026 và70 application
tables/71 tổng giữ nguyên. Excel actual và form N6 dùng chung
inventory_receipt_records (Store/source namespace/record unique), inventory_lots,
inventory_movements và inventory_audit. Planned/committed receipt projection nằm
trong immutable Import preview/completion JSON hiện có, cùng transaction batch.
Không migrate/reset demo8103 hoặc DB khác.

## HISTORICAL INFORMATION — C2 schema head0026

`0026_collaboration_requests` nối additive sau0025, thêm permission_requests,
permission_request_audit và mapping_submissions:70 application tables/71 tổng.
Partial UNIQUE giới hạn một pending Store/member và một submitted/profile.
Mapping evidence giữ source digest/header/row offsets, tham chiếu captured sources
và original bytes đã bất biến; MQ03 chỉ dựng bounded page, không copy mọi raw cells.
Facts/spec/evidence/created identity bất biến; terminal records không reopen,
audit không sửa/xóa; downgrade từ chối retained rows. Reconciliation/decision đổi
state/version cùng transaction caller; không sửa migration lịch sử hoặc DB demo.
Grants vẫn membership_grants; PermissionEvent JSON có nullable request/decision
IDs và source PERMISSION_REQUEST_APPROVAL, không thêm permission catalogue.

### HISTORICAL INFORMATION — C1 checkpoint0025

C1 source head `0025_notifications_foundation` adds `notification_intents`,
`notifications` and `notification_read_receipts` to0024:67 application tables,
68 including Alembic. Intent identity unique(event_id,recipient_user_id,event_type),
projection unique intent_id; read receipt unique(actor_id,notification_id,key_digest).
FKs RESTRICT preserve provenance; nullable Store supports account scope. Payload
version1, delivery status/attempt and positive read revision CHECKs. DB triggers
retain immutable event/content/receipt facts; read_at changes advance revision,
no-op retains it. Downgrade refuses any retained C1 rows, no auto purge/backfill.
Only own `shelfcash_notifications_test` was migrated/reset during C1; demo8103
remains0024/65 tables. [Contract](NOTIFICATION_API_CONTRACT_VI.md) owns workflow.

## HISTORICAL INFORMATION — integrated head0024 base

One head `0024_integrate_import_auth`, parents0021_import_support_history and
0023_auth_permissions_v3, branching from0017 via Import0019 and Auth0018/0020/0022.
Metadata registers64 application tables,65 including Alembic. Auth account/token/
invitation models and Import history/stockout models are composed together.

Both0021/0023 upgrades replace ck_membership_grants_catalogue with the identical
43-key v3 CHECK and retain grants. Integration-only downgrade repairs walk applied
heads and ancestry: if the companion v3 revision remains, keep v3 and its grants.
The last v3 revision refuses downgrade with any six-key grant retained; otherwise
restores v2. Import history retention independently blocks0021 downgrade. No stamp,
backfill, grant deletion or historical v1.0 revision rewrite. A merge alone cannot
fix intermediate traversal, hence only the two unreleased branch revisions receive
this repair, only in integration; source trees stay intact.

Verified0017→either head→both→0024, both orders, metadata/default parity and partial/
final downgrade on the integration DB. [Traversal tests](../tests/integration/test_integrated_migrations.py)
assert retained grants unchanged and v2 rejects new keys after an evidence-free rollback.
Branch inventories below are historical; Gmail demo/Import/Auth/development/shared
DBs are not migrated. Commands and gate results: [runbook](runbooks/FULL_TEST_FLOW.md).

## HISTORICAL INFORMATION — Import126b0f2 migration0021

`0021_import_support_history`, parent `0019_sales_stockout`, creates one
purpose-specific append-only `import_history_records` table for four typed domains.
UUID id, Store RESTRICT FK, domain/source_system_key/report_type/source_record_key,
SHA-256 key hash, positive version, typed payload/provenance JSONB and explicit
recorded_at are required. Unique Store/domain/source/report/hash/version prevents
duplicate revision; JSON object/domain checks and immutable UPDATE/DELETE trigger
protect retained evidence. Application pins the full unhashed key, verifies Store
entity/unit/date/basis identity and uses existing table/read-set fences atomically.
No balance, movement, receipt, inbound or SupplierTerm writes originate here.

The migration expands membership_grants catalogue CHECK to 43 permissions-v3 keys;
it inserts no grants or business rows. Downgrade refuses retained history or newly
granted permission evidence. Current Import metadata has61 application tables (62 with Alembic).

HISTORICAL INFORMATION at Import126b0f2: both heads independently replaced the
same CHECK and restored v2 on downgrade. That overlap was open at the source
snapshot; the integration-only repairs and verified traversal are described above.
Original acceptance used shelfcash_import_test/shelfcash_import_tester, not Auth,
development or shared DBs.

## HISTORICAL INFORMATION — Auth0fbb979 B2/B3/B4 schema

Auth source head `0023_auth_permissions_v3` has parent `0022_invitation_decline`,
then `0020_password_reset_delivery` (parent0018); Import owns0019/0021 separately.
No historical revisions are edited or heads merged. Metadata has63 application
tables,64 with Alembic; this inventory does not mean the Gmail demo was migrated.

B2 adds password_reset_deliveries: encrypted durable transport per canonical
RESET credential token, email/proof binding, claim/lease/attempts/expiry/outcome.
It reuses credential_tokens and stores no plaintext token. N7 atomically changes
the credential and revokes sessions. Downgrade refuses RESET delivery evidence.

B3 adds nullable staff_invitations.declined_at and extends the status CHECK with
declined. Existing tokens/versions/grants and the pending-only unique index stay
intact. Terminal state consumes mutation capability while retaining digest proof
for holder offer reads/replay. Transition, DECLINED event and existing idempotency
receipt commit atomically, with no membership/grants write or new table.
Downgrade refuses retained declined state/event/receipt evidence.

B4 extends only ck_membership_grants_catalogue to the43 approved v3 keys.
No grants, memberships, invitation versions or token bindings are backfilled.
Downgrade to0022 refuses retained grants using the six new keys. Import0021 also
extends this same CHECK alongside its history tables: central BE integration must
reconcile the overlapping catalogue constraint and migration graph explicitly;
this Auth worktree does not merge heads or import those domain tables.

## HISTORICAL INFORMATION — B1 migration0018 inventory

`0018_email_verification` has parent `0017_planning_exports`, coordinated for the
Auth worktree. Two account-scoped tables: email_verification_tokens (digest-only
EMAIL_VERIFY purpose, email/proof/credential binding, expiry/consumption) and
email_verification_deliveries (one encrypted transport intent/token, claim/lease,
attempts/outcome/safe error code). No invitation/Store/membership/grants backfill.
AuthAccount proof fields may be NULL together for an unverified credential-unset
account; a CHECK enforces that state. Existing verified proofs stay unchanged;
proof_revision defaults to1 and application proof writers advance it. Current
metadata has62 application tables,63 with Alembic; one head0018. Synthetic tests
compare ORM/Alembic metadata and fresh committed state. Development DB is untouched.
Downgrade refuses retained verification tokens/delivery or unverified accounts;
operational evidence is not disposable test output. Configuration/flow belongs to
[Auth feature](features/AUTH_SESSION.md), product policy to [Authorization](AUTHORIZATION_CONTRACT_VI.md#auth-self-service).

## HISTORICAL INFORMATION — S4.10 migration0017

One additive purpose-specific planning_exports aggregate: export/job/Run/Store/
actor UUID identity, canonical accepted request/original receipt, key/request
digests, revision, lifecycle/claim/attempt, retained artifact SHA/size proof.
Actor/Store/Run/key uniqueness serializes replay; queue/history indexes support
bounded scans and existing Run history. ImportJob retains its mandatory Import
identity. No broker/generic-job table or business backfill. Head0017_planning_exports,
61 tables including Alembic. Empty down/up preserves populated older Run JSON;
any retained export intent prevents downgrade. ORM/Alembic metadata diff is empty.
Schema and affected persistence evidence: [current verification runbook](runbooks/FULL_TEST_FLOW.md).

## HISTORICAL INFORMATION — S4.8 migration0016

Eight additive tables: planning_defaults, planning_budgets, saved_requirements,
planning_configuration_events, planning_configuration_revisions,
planning_configuration_receipts, model_serving_configurations,
forecast_serving_identities. Store foreign keys restrict deletion; serving
identities use a composite ForecastRun/Store FK. Saved original creator and
creation time are immutable. Revision/audit/receipt/serving-identity triggers
reject UPDATE/DELETE. Historical values are retained in fixed typed JSON shapes.
Operator events have no fabricated customer actor. Config mutations serialize
through Store locking; saved active Product references use a Product write fence.
No backfill; downgrade refuses any configuration or retained evidence. Head0016,
60 tables including Alembic, verified by clean roundtrip and full ORM metadata
comparison on exact local shelfcash_test. See S48 notes and feature walkthrough.


## CURRENT FACT — S4.6 operational evidence, migration0014

Eight additive tables: supplier_source_records, term_source_records,
payable_fee_records, scope_declaration_records, inventory_receipt_records,
inventory_thresholds, stock_request_receipts, inventory_audit.
Typed Import models validate payloads before transaction-owned writers; JSONB holds
fixed discriminated fee/declaration/source shapes and provenance, not arbitrary
canonical extension dictionaries. Source record SHA-256 keys keep Unicode identities
within PostgreSQL index limits; raw identity is preserved/compared, no name dedup.
SupplierTerm/InventoryMovement gain id+Store unique keys for composite scoped evidence
FKs. Seven evidence tables reject UPDATE/DELETE; threshold is audited mutable CAS.
Fee period closing appends evidence revision, term closing only sets reviewed end;
no price rewrite/backfill/implicit readiness facts. Inventory dependency binds approved
scope to exact unchanged lots; N6 creates genuine lot+movement+actor/source identity.
S4.5 sources remain in immutable Import canonical audit; no rewrite/migration of
historical receipts. S4.8 consumes declarations later; no readiness evaluator here.
[Feature](features/IMPORT_INVENTORY_SUPPLIER.md), [evidence](runbooks/FULL_TEST_FLOW.md).


## S4.4 — CURRENT FACT / additive staging only

Migration0013_import_staging adds import_batches/import_blobs/import_files/
import_profiles/import_profile_versions/import_source_contexts/import_jobs/
import_previews/import_receipts/import_audit (41 non-Alembic tables total).
Store-scoped immutable bounded bytea blobs; receipt/audit/evidence/sealed-source
guards; proposals/current job metadata revisioned mutable. No backfill/canonical
writes. Test-only downgrade0012→upgradehead preserves canonical rows; development
DB untouched. See [Import staging](features/IMPORT_STAGING_PREVIEW.md); prior table counts below
are historical slice-time inventory. No canonical fee/completeness storage yet.
## S4.3 ? CURRENT FACT / additive optimistic read metadata

Migration0012_public_read_revisions adds public_read_revisions: Store PK/FK
(CASCADE metadata cleanup), three BIGINT revision counters, default1. Total31
non-Alembic tables plus Alembic. Existing Stores initialized with metadata only,
not business completeness/cost/threshold/ownership data. AFTER source row triggers
on Stores/Products/Ingredients/Recipes/RecipeLines/Lots/Movements advance relevant
counters atomically; INSERT/DELETE/ABA detected, rollback does not invalidate.
No business writes on public GET. REPEATABLE READ READ ONLY projections and signed
keysets implement optimistic snapshots; no transaction retained across requests.
See PUBLIC_MENU_INVENTORY_READS and historical scope notes (retired). Downgrade removes only this
metadata/function/triggers, tested only on shelfcash_test; development DB untouched.

## S4.2 — CURRENT FACT / additive Staff workflow storage

Migration0011_staff_invitations adds staff_invitations (Store/email/issuer/offer,
token digest/revision/expiry/state), permission_events, invitation_events,
staff_request_receipts (actor/Store/operation/key/body-CAS digest) and encrypted
invitation_delivery_intents (attempt/claim/expiry/ciphertext/outcome). Total30
business tables plus Alembic. History/receipt tables reject UPDATE/DELETE through
append-only triggers; invitation mutation is via fenced use cases. One pending
invitation per Store/email partial unique index. No ownership/grants backfill;
existing S4.1 revision and S1/S2/S3 schema/lifecycle unchanged. Application accept
atomically writes exact grants + membership + transition + audits + receipt.
See STAFF_PERMISSIONS_INVITATIONS and historical scope notes (retired) for retention/delivery limits.

## S4.1 — CURRENT FACT / additive authentication storage

Migration0010_auth_sessions adds six tables: auth_accounts (verified operator
attestation and usable-credential/revision state), auth_sessions (digest-only
session identity/CSRF/idle/absolute/revocation), credential_tokens (digest/purpose/
revision/expiry/consumption), membership_grants (per-membership canonical action
keys), auth_audit (non-secret support/credential/session references) and
auth_rate_limits (hashed fixed-window keys). Total25 business tables plus Alembic.
No ownership/grants backfill; S1 reserved delegated_permissions=[] remains enforced.
StoreMembership gains authorization_revision with server default1; membership
active/role and grant-row changes advance it through PostgreSQL triggers, preventing
ABA versions. Existing identity/Store access and create contracts retain defaults.
An AFTER User.active deactivation trigger revokes only new auth_sessions, atomically;
no run mutation or business computation trigger. Downgrade drops new auth tables
and trigger only, destroys their history; development DB untouched in this task.
S4.2 invitation/grant mutation/audit projections not exposed. Earlier sections
describe their original slice-time semantics; current auth is documented in
[AUTH_SESSION](features/AUTH_SESSION.md), evidence in historical scope notes (retired).

## S3.6.4 — CURRENT FACT / additive planning storage

Migration `0009_planning_runs` adds only `planning_runs`: UUID id (the single public
run_id), Store/User RESTRICT FKs, C02 operation, actor+Store+operation+key-digest
unique constraint, request/record SHA-256, status, accepted_at, revision and object
JSONB record. Typed planning_storage/1/package1 holds original request/resolution/
receipt plus optional claim/capture/result/errors/times. Separate capture/result
digests are verified with the full aggregate. No S1 table, state/check or package
version is changed; historical DecisionRun still requires a winner on completion.
There are nineteen business tables at this head (twenty including Alembic).
No auth/membership enforcement, immutability trigger or expiry/delete writer.
Direct privileged SQL can bypass application guards. No development migration.
Downgrade drops only this new planning history; no backfill/destructive upgrade.
[ADR-022](adr/ADR-022-internal-durable-planning.md) and
[feature](features/PLANNING_RUN.md) describe lifecycle/read verification and limits.
The absence/head/table-count statements below describe their original slice states.

CURRENT FACT (S3.3): no table/migration change. ADR-017 accepts future completed
evaluation without winner; schema/lifecycle evolution is deferred, not implemented.
S1 COMPLETED winner requirement remains enforced.

CURRENT FACT (S3.1): no table/migration change. New opt-in typed decision shapes
exist in application/contracts/decision_execution.py and decision_package.py; S1 DecisionRun opaque JSON
writers retain their existing storage contract. Typed-package persistence wiring,
input hashing/retention/replay and engine-level validation are not implemented.
See DECISION_DESIGN and ADR-016; existing PostgreSQL head remains 0008.

**CURRENT FACT:** S1.1 implements `users`, `stores`, `store_memberships`; S1.2 adds
`products`, `ingredients`, `recipes`, `recipe_lines`. S1.3 adds `suppliers`,
`supplier_terms`, `sales_daily`, `inventory_lots`, `inventory_movements`,
`business_constraints`; S1.4 adds `forecast_runs`, `forecast_predictions`,
`decision_runs`; S2.3 adds `forecast_run_inputs`; S2.7 adds
`forecast_execution_metadata` -- eighteen business tables total.
**ACCEPTED DECISION:** the storage semantics below are frozen for these authorized
clusters. ADR-008/009 freeze import correction/inventory audit policy, not runtime
import/mutation services. All other Schema v1 entities remain PROPOSAL; each requires its own accepted
slice before models/migrations are implemented. No hidden aggregate is implied.

**ACCEPTED DECISION (ADR-007):** PostgreSQL is the Competition database, with
SQLAlchemy 2.x, psycopg and synchronous Session. Local infrastructure is Docker
Compose PostgreSQL with a named volume. Reset between versions is
acceptable. Alembic makes schema state/evolution explicit; long-lived backwards-compatible
migration support is not a current requirement. The initial empty revision creates
only `public.alembic_version`; the next migration `0002_identity_store` creates the
three identity/store tables. `0003_catalog_recipe` adds four catalog/recipe tables;
`0004_supplier_ops_constraints` adds six S1.3 tables;
`0005_data_semantics_correction` makes received_date nullable and clarifies its date check.
Revision `0006_forecast_decision_persist` adds the three run tables;
`0007_forecast_input_retention` adds retained forecast inputs; current head
`0008_forecast_execution_meta` adds purpose-specific execution metadata. This shorter revision fits Alembic's 32-character version field.
Tests own separate `shelfcash_test`; development
uses `shelfcash`. Reset recreates only the guarded target's `public` schema.

## IMPLEMENTED — S1.1 storage contract

Models: `app/models/user.py`, `store.py`, `store_membership.py`. Migration:
`alembic/versions/0002_identity_store.py`, parent `0001_scaffold`. All columns below
are NOT NULL. Tables represent mutable current state, not audit snapshots. No
authentication/authorization enforcement or business API exists yet. S1.5 repository
access is documented separately in features/PERSISTENCE_ACCESS.md.

### Shared columns

| Column | PostgreSQL type | Default / semantics |
| --- | --- | --- |
| id | UUID PK | `gen_random_uuid()` database-generated v4; explicit UUID allowed |
| active | BOOLEAN | `true`; stored lifecycle flag, no access enforcement |
| created_at | TIMESTAMPTZ | `now()` at insertion; no automatic later change |
| updated_at | TIMESTAMPTZ | `now()` on insert; SQLAlchemy UPDATE uses `now()` |

Database engine sessions use UTC; outputs are aware instants. PostgreSQL TIMESTAMPTZ
stores an instant rather than a store-local naive datetime. Raw SQL updates must
explicitly set `updated_at`; no timestamp trigger is installed. `now()` is the
transaction timestamp. No timestamp/user-lifecycle service is implemented.

### users

Purpose: stored human identity only. Password processing/login semantics deferred.

| Column | Type | Storage rule |
| --- | --- | --- |
| email | VARCHAR(320) | Unique canonical email; nonempty, `email = lower(email)`, no POSIX whitespace |
| password_hash | TEXT | Opaque nonblank hash value; algorithm/verification not implemented |
| display_name | VARCHAR(200) | Must contain a non-whitespace character |

Constraints: PK `id`; `uq_users_email`; `ck_users_email_canonical`,
`ck_users_password_hash_nonblank`, `ck_users_display_name_nonblank`.
No FKs. The unique email constraint supplies its lookup index; no redundant email
index is added. Canonicalization is a storage requirement: callers supply lowercase
values without whitespace. PostgreSQL rejects uppercase/whitespace input, never
silently rewrites it. Its `lower()`/POSIX whitespace definitions govern this check;
RFC validation, Unicode case-folding, mailbox-provider equivalence, verification
and a normalization/login application workflow are NOT IMPLEMENTED.

### stores

Purpose: mutable F&B store/business context and future tenancy boundary.

| Column | Type | Storage rule / default |
| --- | --- | --- |
| name | VARCHAR(200) | Nonblank, explicitly NOT unique |
| timezone | VARCHAR(64) | Nonblank; default `Asia/Ho_Chi_Minh` frozen in S1.1 |
| currency | VARCHAR(3) | Uppercase three-letter shape; default `VND` frozen in S1.1 |

Constraints: PK `id`; `ck_stores_name_nonblank`, `ck_stores_timezone_nonblank`,
`ck_stores_currency_shape`. No FKs, unique name rule or additional indexes.
Timezone/currency defaults were previously unresolved and are accepted only for
this storage cluster. IANA timezone/ISO currency catalog validation, financial
precision/conversion and business-date cutoff remain future contracts.

### store_memberships

Purpose: persisted User ↔ Store relationship, not permission enforcement.

| Column | Type | Storage rule |
| --- | --- | --- |
| store_id | UUID FK → stores.id | Existing store; `ON DELETE RESTRICT` |
| user_id | UUID FK → users.id | Existing user; `ON DELETE RESTRICT` |
| role | VARCHAR(5) | Required `OWNER` or `STAFF`; no default |
| delegated_permissions | JSONB | Default `[]`; must equal `[]` in S1.1 |

Constraints: PK `id`; FKs `fk_store_memberships_store` and
`fk_store_memberships_user`; `uq_store_memberships_store_user` on (store_id,user_id);
`ck_store_memberships_role` and `ck_store_memberships_permissions_reserved`.
Constrained string avoids a separate enum lifecycle while preserving role integrity.
The unique pair's index covers store-to-member lookup, so no redundant store_id index
is added. Explicit `ix_store_memberships_user_id` supports reverse user-to-store
membership lookup. Parent deletion is rejected while memberships exist; no implicit
cascade or real-state deletion workflow. A user can belong to several stores and a
store can have several users, with at most one row per pair. No sole-owner/minimum-owner
or active-parent rule is invented.

`delegated_permissions` is an empty reserved list. Nonempty lists, objects and JSON
null are rejected; no arbitrary permission vocabulary is accepted. Opening that
vocabulary needs a later explicit contract/migration. Membership presence/role/active
does NOT grant runtime authorization in S1.1.

Verification: [STORE_IDENTITY](features/STORE_IDENTITY.md), targeted real PostgreSQL
tests `tests/integration/test_identity_store_schema.py`, and
[FULL_TEST_FLOW](runbooks/FULL_TEST_FLOW.md). Reset leaves these three tables empty
and the S1.2/S1.3 tables empty, with one `alembic_version` row `0006_forecast_decision_persist`;
seed writes no entities.

Implementation references: [PostgreSQL date/time types](https://www.postgresql.org/docs/17/datatype-datetime.html)
and [SQLAlchemy defaults/onupdate](https://docs.sqlalchemy.org/en/20/core/defaults.html).

## IMPLEMENTED — S1.2 Catalog + Recipe storage contract

Models: `app/models/product.py`, `ingredient.py`, `recipe.py`, `recipe_line.py`.
Migration `0003_catalog_recipe`, parent `0002_identity_store`. All columns NOT NULL
except `products.sku`, `products.price`, `ingredients.sku`, `recipes.effective_to`.
All four have UUID PK `id` default `gen_random_uuid()` and `created_at TIMESTAMPTZ`
default `now()`. Products/ingredients/recipes also have `updated_at TIMESTAMPTZ`
with the same insert/ORM-update semantics as S1.1. Raw SQL updates set it explicitly.
These are editable versioned definitions/current catalog, not immutable execution
snapshots. No historical snapshot immutability trigger exists. Forecast computation
and captured/artifact provenance are application/infrastructure behavior under S2,
not computation in these catalog ORM models.

### products

| Column | Type | Rule/default |
| --- | --- | --- |
| store_id | UUID | FK stores.id, RESTRICT deletion |
| sku | VARCHAR(64), nullable | Case-sensitive, nonblank if present; unique within store |
| name | VARCHAR(200) | Nonblank; not unique |
| selling_unit | VARCHAR(32) | Nonblank exact unit label |
| price | NUMERIC, nullable | Finite >= 0; store currency; NULL means unspecified |
| active | BOOLEAN | Default true; stored flag only |

PK id; `fk_products_store`; `uq_products_store_sku` (store_id,sku).
PostgreSQL NULL-distinct uniqueness permits multiple missing SKUs in one store.
No SKU normalization or global uniqueness. `uq_products_id_store` (id,store_id)
is the required target for recipe's same-store FK. Checks:
`ck_products_name_nonblank`, `ck_products_sku_nonblank`,
`ck_products_selling_unit_nonblank`, `ck_products_price` (rejects NaN/infinities).
The store/SKU index covers store catalog lookup; no redundant store_id index.

### ingredients

| Column | Type | Rule/default |
| --- | --- | --- |
| store_id | UUID | FK stores.id, RESTRICT deletion |
| sku | VARCHAR(64), nullable | Same case-sensitive store-scoped/null rules as Product |
| name | VARCHAR(200) | Nonblank, not unique; canonical stored label |
| base_unit | VARCHAR(32) | Nonblank, exact case-sensitive unit, no conversion |
| expiry_tracking | BOOLEAN | Default false; flag only, no inventory behavior |
| active | BOOLEAN | Default true |

PK id; `fk_ingredients_store`; `uq_ingredients_store_sku` (store_id,sku).
`uq_ingredients_id_store_unit` (id,store_id,base_unit) supports the line integrity FK.
Checks `ck_ingredients_name_nonblank`, `ck_ingredients_sku_nonblank`,
`ck_ingredients_base_unit_nonblank`. Store/SKU uniqueness covers store lookup.
Unit vocabulary is not a conversion/validation catalog (e.g. ml and L differ).

### recipes

| Column | Type | Rule/default |
| --- | --- | --- |
| store_id | UUID | FK stores.id and same-store product FK |
| product_id | UUID | Composite FK (product_id,store_id) -> products(id,store_id) |
| version | INTEGER | Required > 0, unique per product |
| effective_from | DATE | Required inclusive start |
| effective_to | DATE, nullable | Inclusive end >= start; NULL means unbounded future |
| yield_quantity | NUMERIC | Finite > 0; total product output in Product.selling_unit |
| process_loss_rate | NUMERIC | Default 0; 0 <= rate < 1, recipe-level loss |

PK id; FKs `fk_recipes_store`, `fk_recipes_product_store`, both ON DELETE RESTRICT.
Unique `uq_recipes_product_version` (product_id,version), `uq_recipes_id_store`
(id,store_id) supports lines. Checks `ck_recipes_version`, `ck_recipes_period`,
`ck_recipes_yield`, `ck_recipes_loss`.

`ex_recipes_product_period` uses GiST exclusion:
`product_id WITH =, daterange(effective_from,effective_to,'[]') WITH &&`.
Migration enables standard PostgreSQL `btree_gist` for UUID equality. The database
rejects overlapping inserts/updates, including concurrent transactions. Shared end/start
day overlaps; the next version can begin the following day. Same-day recipes are valid.
An unbounded version blocks all later overlapping versions. Different products can
share periods. At day D resolve using `effective_from <= D AND (effective_to IS NULL
OR D <= effective_to)` to obtain 0/1 row. Product.active does not bypass exclusion.
S1.5 RecipeRepository implements the accepted inclusive date lookup, without BOM. Unique product/version supports product queries;
exclusion supplies its GiST index; no speculative date-only index.

NUMERIC maps to Decimal, with no fixed scale or implicit business rounding; price,
yield and line quantity reject NaN/infinities. PostgreSQL NUMERIC implementation limits
still apply. Loss is at Recipe level, not per Ingredient. Future BOM formula is
`actual_requirement = theoretical_requirement / (1 - process_loss_rate)`;
800 ml over yield 10 cups means theoretical 80 ml/cup. With loss 0.05 this becomes
80/0.95 (~84.21 ml). **BOM computation is NOT IMPLEMENTED.**

### recipe_lines

| Column | Type | Rule |
| --- | --- | --- |
| store_id | UUID | Required integrity witness shared by both composite FKs |
| recipe_id | UUID | FK (recipe_id,store_id) -> recipes(id,store_id) |
| ingredient_id | UUID | FK (ingredient_id,store_id,unit) -> ingredients(id,store_id,base_unit) |
| quantity | NUMERIC | Finite > 0 for the entire recipe yield |
| unit | VARCHAR(32) | Must exactly equal Ingredient.base_unit |

PK id; `uq_recipe_lines_recipe_ingredient` (recipe_id,ingredient_id),
`ck_recipe_lines_quantity`. FKs `fk_recipe_lines_recipe_store` and
`fk_recipe_lines_ingredient_store_unit`, ON DELETE RESTRICT / default NO ACTION
on update. store_id is intentional redundant integrity data; unit is retained as
requested. Both enable declarative database checks without services or triggers.
Ingredient base-unit changes and parent-store changes cannot invalidate referenced
lines/recipes. Parent deletion is blocked while referenced. No implicit cascading
business deletion. Recipe/ingredient duplicates must be combined by a future caller.
Unique recipe/ingredient covers recipe lookup. Explicit `ix_recipe_lines_ingredient_id`
supports reverse ingredient usage and referential checks; no redundant recipe_id index.

Verification: [CATALOG_RECIPE](features/CATALOG_RECIPE.md), actual PostgreSQL tests
`tests/integration/test_catalog_recipe_schema.py`. Downgrade to 0002 drops only
these four tables/rows; btree_gist is retained because it may be shared/preexisting.
Normal reset recreates public (including its extension objects), then upgrades head.
The Compose role can install the extension. No new public API exists; S1.5 adds internal repository access without schema change.
References: [PostgreSQL btree_gist](https://www.postgresql.org/docs/17/btree-gist.html),
[range exclusion](https://www.postgresql.org/docs/17/rangetypes.html).

## IMPLEMENTED — S1.3 Supplier / Operational / Constraints storage contract

Migration `alembic/versions/0004_supplier_operational_constraints.py`, revision
`0004_supplier_ops_constraints`, parent `0003_catalog_recipe`. Typed models are
`app/models/supplier.py`, `supplier_term.py`, `sales_daily.py`, `inventory_lot.py`,
`inventory_movement.py`, `business_constraint.py`. S1.5 repositories exist; no operational service/API exists.
Every table has UUID PK `id`, database `gen_random_uuid()` default, and `created_at
TIMESTAMPTZ DEFAULT now()`. All except movements have `updated_at TIMESTAMPTZ` with
the S1.1 insert/ORM-update convention; raw SQL updates must set it explicitly.
All columns required unless marked nullable. NUMERIC maps to Decimal, without fixed
scale/business rounding; NaN/infinities are rejected. Store currency governs costs;
currency conversion/change and money rounding remain future application contracts.
All FKs below use ON DELETE RESTRICT, default NO ACTION on updates. No cascade,
timestamp, inventory-balance, expiry or ledger immutability trigger is introduced.

### suppliers

Purpose: store-owned supplier identity, not global supplier directory.

| Column | Type | Rule/default |
| --- | --- | --- |
| store_id | UUID | FK stores.id |
| name | VARCHAR(200) | Nonblank; NOT unique within/across stores |
| active | BOOLEAN | true |

PK id; `fk_suppliers_store`; `uq_suppliers_id_store` (id,store_id) is the required
composite FK target. `ck_suppliers_name_nonblank`; explicit `ix_suppliers_store_id`
supports listing suppliers in a store (the id-leading unique index cannot do that).
Current mutable identity state; no source codes, contacts or supplier CRUD invented.

### supplier_terms

Purpose: versioned pack purchasing inputs for Supplier ↔ Ingredient (many-to-many).
Changes should create a new version, adjusting periods explicitly; SQL rows remain
editable and no historical immutability service is implemented. Snapshot consumers
must preserve used values under ADR-005 when implemented.

| Column | Type | Rule/default |
| --- | --- | --- |
| store_id | UUID | Same-store integrity witness for supplier/ingredient |
| supplier_id | UUID | FK (supplier_id,store_id) -> suppliers(id,store_id) |
| ingredient_id | UUID | FK (ingredient_id,store_id,unit) -> ingredients(id,store_id,base_unit) |
| unit | VARCHAR(32) | Exact base-unit witness, prevents reinterpretation after unit edits |
| version | INTEGER | >0, required |
| effective_from | DATE | Inclusive start |
| effective_to | DATE nullable | Inclusive end >= start, NULL unbounded |
| pack_size_base_quantity | NUMERIC | Finite >0, Ingredient.base_unit per pack |
| minimum_order_packs | INTEGER | >=1, minimum whole packs when an order is placed |
| pack_cost | NUMERIC | Finite >=0, Store currency per pack |
| lead_time_days | INTEGER | >=0 |
| shelf_life_days | INTEGER nullable | >=0 when provided; unspecified when NULL |
| active | BOOLEAN | true; only active rows participate in overlap exclusion |

PK id; `fk_supplier_terms_supplier_store`, `fk_supplier_terms_ingredient_store_unit`.
`uq_supplier_terms_pair_version` (supplier_id,ingredient_id,version) across active
and inactive rows. Checks `ck_supplier_terms_version`, `ck_supplier_terms_period`,
`ck_supplier_terms_pack_size`, `ck_supplier_terms_minimum_packs`,
`ck_supplier_terms_pack_cost`, `ck_supplier_terms_lead_time`, `ck_supplier_terms_shelf_life`.
`ex_supplier_terms_pair_period`: GiST supplier_id =, ingredient_id =,
daterange(from,to,'[]') && WHERE active, reusing parent btree_gist. Concurrent SQL
inserts/updates/activation cannot produce two active terms for the pair on one day.
Inactive overlapping drafts are allowed; duplicate version is still rejected.
At D select active AND from<=D AND (to IS NULL OR D<=to); zero/one result.
Shared boundary day overlaps; next-day adjacency and single-day periods are valid.
Unique pair/version covers supplier-term lookup; explicit
`ix_supplier_terms_ingredient_id` supports finding suppliers for an ingredient.
No redundant effective-date or supplier index.

Example: Milk base_unit ml; 12 x 1L pack is normalized externally to 12000 ml,
minimum packs 2, pack_cost 360000 VND. Two packs cost 720000 VND. This specifies
inputs only, not an implemented procurement/unit-conversion calculation.

### sales_daily

CURRENT FACT A1 (verified on owned `shelfcash_import_test`): additive nullable
BOOLEAN `is_stockout`, no default/backfill. True is observed product stockout,
false known uncensored, null unknown. Quantity remains observed sales; immutable
Import audit retains contribution revisions/evidence and canonical before/after.
Forecast JSON captures derived demand separately. Migration `0019_sales_stockout`
has parent `0017_planning_exports`, no Auth dependency. Upgrade only adds the column;
downgrade refuses any non-null observation, including false. Upgrade and retention
guard are verified using fresh Sessions; no development or Auth DB migration here.

Purpose: one canonical daily sales total, not additive source observations.

| Column | Type | Rule |
| --- | --- | --- |
| store_id | UUID | Same-store product witness |
| product_id | UUID | FK (product_id,store_id) -> products(id,store_id) |
| sales_date | DATE | Canonical business sales day; timezone cutoff conversion not implemented |
| quantity | NUMERIC | Finite >=0 in Product.selling_unit |
| is_stockout | BOOLEAN nullable | Observed stockout true / known uncensored false / unknown null; no default/backfill |

PK id; `fk_sales_daily_product_store`, `uq_sales_daily_store_product_date`
(store_id,product_id,sales_date), `ck_sales_daily_quantity`. Unique index supports
store/product/day lookup; no source/import/filename in identity. No unnecessary
revenue/promotion fields. A source quantity 100 changed to 105 is CHANGED under
ADR-008, not a second row or total 205. Import correction/confirmed independent
contribution workflow retains immutable source revisions and canonical before/after
in Import audit. The materialized daily row remains mutable; it is not event sourcing.

### inventory_lots

Purpose: current balance for actually received lots (ADR-009), not inbound orders.

| Column | Type | Rule |
| --- | --- | --- |
| store_id | UUID | Same-store ingredient/supplier witness |
| ingredient_id | UUID | FK (ingredient_id,store_id,unit) -> ingredients(id,store_id,base_unit) |
| supplier_id | UUID nullable | FK (supplier_id,store_id) -> suppliers(id,store_id); unknown allowed |
| lot_code | VARCHAR(128) nullable | Nonblank when present; no invented uniqueness/import identity |
| received_date | DATE nullable, no default | Known actual receipt day, or NULL (OPTIONAL_WARNING); never snapshot/upload date |
| expiry_date | DATE nullable | >= received_date when both dates are known |
| on_hand_quantity | NUMERIC | Current materialized finite balance >=0 |
| unit | VARCHAR(32) | Exactly Ingredient.base_unit |
| unit_cost | NUMERIC nullable | Finite >=0 in store currency per one Ingredient.base_unit; unknown allowed |

PK id; `fk_inventory_lots_ingredient_store_unit`, `fk_inventory_lots_supplier_store`.
Default MATCH SIMPLE skips optional supplier FK when supplier_id is NULL; required
ingredient/store/unit FK still protects the store. `uq_inventory_lots_id_store_ingredient`
(id,store_id,ingredient_id) supports movements. Checks `ck_inventory_lots_on_hand`,
`ck_inventory_lots_expiry`, `ck_inventory_lots_unit_cost`, `ck_inventory_lots_code_nonblank`.
`ix_inventory_lots_store_ingredient_expiry` supports store/ingredient lot inspection
ordered by expiry; no FEFO algorithm is claimed. Ingredient.expiry_tracking=true
will require expiry_date at future receipt/application boundaries; this conditional
cross-table rule is NOT DB-enforced in S1.3. Tracked lots with NULL expiry can be
inserted directly; tests/documentation expose that limit. Expired lots are retained,
but future usable quantity is zero. Expiry-day cutoff/FEFO is not implemented.

### inventory_movements

Purpose: quantity change history explaining lot balance, not Event Sourcing.

| Column | Type | Rule |
| --- | --- | --- |
| store_id | UUID | Must match referenced lot |
| lot_id | UUID | Composite FK (lot_id,store_id,ingredient_id) -> inventory_lots(id,store_id,ingredient_id) |
| ingredient_id | UUID | Must equal lot ingredient; quantity uses its base unit |
| movement_type | VARCHAR(24) | RECEIPT, USAGE, WASTE, EXPIRED, COUNT_CORRECTION, MANUAL_ADJUSTMENT |
| quantity_delta | NUMERIC | Finite, nonzero; positive increase/negative decrease |
| occurred_at | TIMESTAMPTZ | Required aware event instant; distinct from created_at |
| reference_type | VARCHAR(64) nullable | Opaque nonblank trace hook, paired with reference_id |
| reference_id | TEXT nullable | Opaque nonblank source/reference identifier, not ImportJob FK |
| note | TEXT nullable | Optional explanation; future correction boundary validates required reasons |

PK id; `fk_inventory_movements_lot_store_ingredient` blocks cross-store/ingredient
movement and deleting referenced lots. Checks `ck_inventory_movements_type`,
`ck_inventory_movements_delta`, `ck_inventory_movements_sign`,
`ck_inventory_movements_reference_pair` (both NULL or both nonblank).
RECEIPT positive; USAGE/WASTE/EXPIRED negative; count/manual corrections either sign.
`ix_inventory_movements_lot_occurred` supports per-lot chronological audit inspection.
No balance-trigger or ledger-sum constraint: inserting movement does not update lot.
Future service must create movement + change balance atomically with concurrency
protection. Unexplained overwrite is forbidden application policy, but direct SQL
can still edit balances/movements. Mandatory initial receipt, append-only history,
actor/provenance enforcement and reconciliation are NOT IMPLEMENTED.

### business_constraints

Purpose: controlled, versioned numeric planning inputs. Budget belongs here, not
Store settings or a separate aggregate. No arbitrary JSON/text values or LLM types.

| Column | Type | Rule/default |
| --- | --- | --- |
| store_id | UUID | FK stores.id |
| scope_type | VARCHAR(10) | STORE or INGREDIENT only |
| scope_id | UUID nullable | STORE: NULL; INGREDIENT: required same-store Ingredient |
| constraint_type | VARCHAR(24) | STORE/BUDGET_LIMIT or INGREDIENT/MIN_SAFETY_STOCK only |
| numeric_value | NUMERIC | Finite >=0 |
| unit | VARCHAR(32) | Budget: uppercase currency shape; safety: exact Ingredient.base_unit |
| version | INTEGER | >0 |
| effective_from | DATE | Inclusive start |
| effective_to | DATE nullable | Inclusive end >=start, NULL unbounded |
| active | BOOLEAN | true |

PK id; `fk_business_constraints_store`; `fk_business_constraints_ingredient_scope_unit`
(scope_id,store_id,unit) -> ingredients(id,store_id,base_unit). For STORE NULL scope_id
skips this FK; required scope/type CHECK ensures this is intentional.
`uq_business_constraints_scope_version` on (store_id,scope_type,scope_id,constraint_type,
version), PostgreSQL NULLS NOT DISTINCT: even NULL STORE identities cannot duplicate
versions. Checks `ck_business_constraints_registry_scope`,
`ck_business_constraints_numeric_value`, `ck_business_constraints_version`,
`ck_business_constraints_period`. `ex_business_constraints_scope_period` uses GiST
store_id =, scope_type =, coalesce(scope_id,store_id) =, constraint_type =,
daterange(from,to,'[]') && WHERE active. No NULL hole for STORE overlap; scope_type
separates STORE from INGREDIENT even if UUIDs happen to coincide. Unique/GiST indexes
cover store/logical-scope/version/period lookup; no speculative extra index.
Inactive overlap allowed, activation validated; active resolution follows the same
inclusive predicate as SupplierTerm. Budget value is in unit currency; matching
Store.currency is a future application validation, NOT conditional DB enforcement.
No multi-currency computation, spent/reserved/rollover, MAX_STORAGE or other scopes.

Verification: [SUPPLIER](features/SUPPLIER.md), [OPERATIONAL_DATA](features/OPERATIONAL_DATA.md),
[INVENTORY](features/INVENTORY.md), [BUSINESS_CONSTRAINTS](features/BUSINESS_CONSTRAINTS.md),
`tests/integration/test_supplier_operational_constraints.py` and FULL_TEST_FLOW.
Normal reset at current head leaves eighteen empty business tables plus one current revision row;
seed writes no rows. Downgrade 0004->0003 drops only six new tables/rows, keeping
all S1.1/S1.2 schema and btree_gist. S1.4 run tables are documented below; no Import/Order/What-if tables exist.
Reference: [PostgreSQL NULLS NOT DISTINCT and exclusion](https://www.postgresql.org/docs/17/ddl-constraints.html).

## Remaining Schema v1 — PROPOSAL / FUTURE

Only ImportJob/MappingProfile remain proposed in the table below. ForecastRun,
ForecastPrediction and DecisionRun are implemented under the S1.4 contract later
in this document; earlier speculative cutoff/actor/parameter columns were not frozen
and are not silently claimed as implemented.

### Common conventions — PROPOSAL

Each entity has a primary `id`. Store-owned records use `store_id` with enforced
foreign keys and application authorization. Cross-store relationships must be
rejected by the backend; composite keys/FKs may enforce them when appropriate.
S1.1 UUID/timestamp/store defaults above are accepted for that cluster only;
remaining identifiers and currency/quantity precision are unresolved.
Do not rely on floating point for exact financial truth: choose an explicit
money representation/rounding contract in the first affected slice.
Business-date boundaries use an explicitly agreed store timezone/cutoff policy.
Indexes below are candidates for real queries, not a command to create unused indexes.

| Entity | Purpose and key fields | Relationships | Important constraints / indexes | Current state or historical snapshot |
| --- | --- | --- | --- | --- |
| ImportJob | Trace ingestion: id, store_id, source reference/digest, status, mapping_profile_id, created_at, validation summary | Store; optional MappingProfile; provenance for imported rows | Store/date index; validated status transitions; immutable source reference; file/row errors separate from accepted data | Historical import execution/status record |
| MappingProfile | Approved store mapping: id, store_id, profile version, canonical schema version, file fingerprint, field mapping, approval actor/time, status | Store, approving User/Membership; ImportJobs | Unique (store_id, profile key, version); mapping targets restricted to canonical fields; approved versions immutable | Versioned approved mapping snapshot, with explicit current active selection |

## DecisionRun package — ACCEPTED DECISION, structure remains PROPOSAL

`package_schema_version` exists from version 1. The package must retain inputs and
versions, ingredient demand, all three candidates, simulator metrics, deterministic
selected recommendation, warnings, risks and business evidence. Include exact inventory,
supplier terms and constraint values used, recipe/model versions, cutoff/horizon and
simulation/comparison algorithm versions needed to understand the result later.
Mutable source references alone do not satisfy this requirement. A stored snapshot
need not promise future software can replay every old algorithm, but its historical
meaning must remain understandable and stable.

A schema-versioned validated JSON snapshot is appropriate for complex nested output
in the MVP. Do not normalize every candidate, risk or evidence object into its own
table without a documented query/integrity requirement. Important forecast P25/P50/P75
values remain explicit columns in ForecastPrediction. No extra aggregate is proposed.

Hypothetical what-if results are non-persistent as real business state by default.
Any later history of simulations must be explicitly distinguished from real decisions
and separately authorized; this proposal does not introduce a WhatIf aggregate/table.

## Deferred choices — PROPOSAL

Freeze remaining deletion/retention workflows, unit/money conversion/rounding,
domain correction implementation under ADR-008/009, login handling,
delegated permission storage, forecast input artifact retention and exact package schema
in affected slices. Choose schema evolution for clarity and reproducibility, without
legacy compatibility scaffolding or an unrequested database engine.

## IMPLEMENTED -- S1.3.1 source-semantics correction

ADR-010 is ACCEPTED. Migration 0005 changes only inventory_lots.received_date
nullability and ck_inventory_lots_expiry to `received_date IS NULL OR expiry_date
IS NULL OR expiry_date >= received_date`. No date default or new table is added.
Unknown receipt remains NULL; stock is meaningful, expiry-based FEFO readiness
depends on known expiry, and inventory age cannot be computed. Downgrade refuses
NULL receipt rows rather than inventing dates; confirmed source resolution or explicit
development reset is needed. All remaining constraints/indexes are unchanged.

SupplierTerm price is UNCHANGED: pack_cost is Store-currency cost per complete pack,
not cost per base unit. Known 15 kg and 28,000 VND/kg normalize to 420,000 VND/pack
(15,000 g when Ingredient.base_unit is g). Future normalization must prove units.
SupplierTerm effective_from is UNCHANGED, NOT NULL with no default, as are strict
canonical procurement inputs including lead_time_days. Unknown source effective date
cannot be promoted into an active canonical term; upload date is not evidence.
Internal version may be system-assigned; business facts must be established.
No import/staging/readiness column or procurement computation was added in S1.3.1.
Forecast-specific readiness/computation now exists separately under S2.

## IMPLEMENTED — S1.4 Forecast + Decision persistence

Migration `alembic/versions/0006_forecast_decision_persistence.py`, revision
`0006_forecast_decision_persist`, parent `0005_data_semantics_correction`. This
30-character revision fits Alembic's version column. Only three tables are added,
bringing the business total to sixteen. ADR-011 is ACCEPTED; previous tables unchanged.

All id columns: UUID PK with gen_random_uuid(). All created_at columns: TIMESTAMPTZ
NOT NULL server now(). Run updated_at: TIMESTAMPTZ NOT NULL server now(), ORM update
now(); raw SQL callers maintain timestamps. Engine sessions use UTC. started_at is
explicit/required, no date/time fallback. Columns below NOT NULL unless nullable.
No computed engine output is generated by these models.

### forecast_runs

| Column | PostgreSQL type | Meaning |
| --- | --- | --- |
| id | UUID | Execution identity |
| store_id | UUID | FK stores.id, RESTRICT |
| status | VARCHAR(16) | RUNNING / COMPLETED / FAILED, explicit, no default |
| training_start_date, training_end_date | DATE | Inclusive ordered training period |
| forecast_start_date, forecast_end_date | DATE | Inclusive ordered forecast horizon |
| model_type, model_version | VARCHAR(128) | Nonblank actual model identity/version |
| artifact_key | TEXT nullable | Nonblank logical filesystem key, never binary model |
| metrics_json | JSONB nullable | Object evaluating forecast/model, not strategy scores |
| input_fingerprint | VARCHAR(128) nullable | Nonblank canonical-input digest; required when completed |
| started_at | TIMESTAMPTZ | Explicit run start |
| completed_at | TIMESTAMPTZ nullable | Terminal completion/failure time, >= start |
| error_code | VARCHAR(64) nullable | Nonblank sanitized failure classification |
| error_summary | TEXT nullable | Nonblank sanitized failure summary, no secret/stack dump |
| created_at, updated_at | TIMESTAMPTZ | Metadata timestamps |

PK id. `uq_forecast_runs_id_store(id,store_id)` provides composite FK target.
`fk_forecast_runs_store` restricts orphan/cross-store parent state. CHECKs:
`ck_forecast_runs_status`, `training_window`, `horizon`, `model_metadata`,
`artifact_key`, `fingerprint`, `metrics_object`, `timestamps`, `state`,
`error_nonblank` (each uses ck_forecast_runs_ prefix).
RUNNING: no completed_at/errors. COMPLETED: completed_at/fingerprint required, errors
absent. FAILED: completed_at and error code/summary required. Required windows/model
metadata exist even in RUNNING/FAILED; no adjacent-window rule. Metrics/artifact optional.
`ix_forecast_runs_store_created(store_id,created_at)` supports store run history;
no unique fingerprint. Input fingerprint alone does not preserve training content;
input/artifact retention remains a Forecast Engine requirement.

### forecast_predictions

| Column | PostgreSQL type | Meaning |
| --- | --- | --- |
| id | UUID | Prediction identity |
| forecast_run_id | UUID | Existing ForecastRun |
| store_id | UUID | Same-store integrity witness |
| product_id | UUID | Existing same-store Product |
| forecast_date | DATE | Predicted business date |
| p25, p50, p75 | NUMERIC | Exact finite nonnegative ordered quantities in Product.selling_unit |
| created_at | TIMESTAMPTZ | Metadata timestamp |

PK id. `uq_forecast_predictions_run_product_date(forecast_run_id,product_id,forecast_date)`
defines canonical prediction key. RESTRICT composite FKs `fk_forecast_predictions_run_store`
(forecast_run_id,store_id)->forecast_runs(id,store_id) and
`fk_forecast_predictions_product_store` (product_id,store_id)->products(id,store_id).
`ck_forecast_predictions_quantiles`: 0 <= p25 <= p50 <= p75, all finite (NaN/infinities
rejected). Unique index covers per-product run reads; explicit
`ix_forecast_predictions_run_date(run,date)` supports whole-run dated horizon reads;
`ix_forecast_predictions_product(product_id)` supports Product provenance/referenced
parent checks. Quantiles express uncertainty; never LEAN=P25/BALANCED=P50/PROTECTED=P75.
Prediction-date membership in the parent horizon is a future application invariant,
not a DB CHECK/trigger; S1.4 does not implement a resolver/writer enforcing it.

### decision_runs

| Column | PostgreSQL type | Meaning |
| --- | --- | --- |
| id | UUID | Decision execution identity |
| store_id | UUID | Same-store integrity witness |
| status | VARCHAR(16) | RUNNING / COMPLETED / FAILED, explicit |
| forecast_run_id | UUID | Required same-store ForecastRun |
| planning_start_date, planning_end_date | DATE | Inclusive ordered planning period |
| package_schema_version | INTEGER nullable | Positive when supplied/package exists; completed requires it; initial format 1 |
| input_fingerprint | VARCHAR(128) nullable | Nonblank nonunique input digest, completed requires it |
| input_snapshot_json | JSONB nullable | Object of actual input values/identities/versions |
| decision_package_json | JSONB nullable | Versioned object output package, completed only |
| recommended_strategy | VARCHAR(16) nullable | LEAN / BALANCED / PROTECTED, completed only |
| started_at | TIMESTAMPTZ | Explicit start |
| completed_at | TIMESTAMPTZ nullable | Terminal completion/failure time, >= start |
| error_code | VARCHAR(64) nullable | Nonblank sanitized failure classification |
| error_summary | TEXT nullable | Nonblank sanitized summary |
| created_at, updated_at | TIMESTAMPTZ | Metadata timestamps |

PK id. RESTRICT `fk_decision_runs_forecast_store`:
(forecast_run_id,store_id)->forecast_runs(id,store_id), transitively an existing Store.
CHECKs with ck_decision_runs_ prefix: status, planning_window, package_version,
package_version_required, fingerprint, snapshot_object, package_object, strategy,
timestamps, state, error_nonblank. COMPLETED requires version/fingerprint/snapshot/
package/strategy/terminal time, errors absent. RUNNING requires no terminal time/errors/
output package/recommendation. FAILED requires terminal time/errors, no package/
recommendation. Partial states may retain captured snapshot/fingerprint/version or
SQL NULL. JSONB uses none_as_null: SQL NULL is absent; JSON null/arrays/scalars fail
object checks. No positive-version default fabricates a completed package.
`ix_decision_runs_store_created(store_id,created_at)` supports history;
`ix_decision_runs_forecast(forecast_run_id)` supports forecast provenance/dependent reads.
Fingerprints are not unique: same-input reruns create new records.

### Historical/application boundary

Completed runs/predictions are historical immutable policy; no UPDATE/DELETE trigger
exists. CURRENT FACT (S1.5): repository lifecycle writers permit only RUNNING terminal
transitions and prediction append; direct ORM/SQL changes bypass these guards.
Future services enforce full application immutability, completed
forecast consumption, horizon membership, full versioned JSON validation, algorithm
provenance, all candidate evaluations, recommendation consistency, sanitization and
authorization. Snapshot holds values, not only live FK references. Build snapshot
BEFORE computation and compute from it; never re-query changed inputs afterward.
Future package includes actual evaluated LEAN/BALANCED/PROTECTED candidates; LLM
cannot select recommendation or supply business facts. Package schema version starts
at 1; needed engine/model version metadata belongs in the future versioned package,
not an invented framework/column now. Hashing/input retention is not implemented.
What-if remains non-persistent by default; no extra tables/services/APIs are added.
Full shapes remain future application contracts; DB only checks minimal presence/object
shape. Downgrade 0006->0005 drops exactly these three tables/history. Tests and manual
inspection are in FORECAST, DECISION_RUN and [FULL_TEST_FLOW](runbooks/FULL_TEST_FLOW.md).

CURRENT FACT (S1.6): schema is unchanged. Application paths now enforce prediction
horizon/Product membership, completed same-store forecast consumption, terminal
time/lifecycle and atomic supplied completion; see APPLICATION_CONTRACTS. Earlier
references to future horizon/readiness enforcement above describe the schema's limits,
not missing checks in those implemented application paths. Direct SQL still bypasses
them; full business package/provenance validation remains future.

## IMPLEMENTED ? S2.3 retained forecast input

ACCEPTED DECISION: ADR-014. Table forecast_run_inputs has forecast_run_id UUID PK,
store_id UUID required; same-Store composite FK to forecast_runs(id,store_id), RESTRICT.
prepared_json JSONB required/object CHECK; serialization_version INTEGER >0; digest
VARCHAR(64) lowercase hexadecimal SHA-256 shape CHECK; created_at TIMESTAMPTZ now().
One record/run, digest nonunique, no update/delete repository, no triggers or binary
artifacts. Positive future versions may store, but current loader accepts only v1.
Old S1 runs need no row. Execution start writes run/input in one transaction. Digests
are validated against versioned canonical prepared values, not JSONB rendered text.
Downgrade 0007 removes inputs only and destroys replay history; export/backup first.
Development may remain at 0006 until explicitly migrated; test verification owns only
shelfcash_test. No automatic startup migration or development reset is performed.


## IMPLEMENTED ? S2.7 purpose-specific execution metadata (ADR-015)

`forecast_execution_metadata`: PK forecast_run_id; store_id required, composite
same-Store ForecastRun FK ON DELETE RESTRICT; details_json JSONB object with required
numeric schema_version=1. Application validates typed selection_reason, candidate
artifact identity, postprocessing_version, raw crossing/negative counts and structured
warnings. Run/input/initial details start atomically; completion-only guarded update
commits with predictions/status. No terminal update/delete repository, no immutability
trigger. S1 and S2.3 runs need no row. Model binary/text stays local; run.artifact_key
is actual immutable model identity, metrics_json is not warning/provenance storage.
Downgrade 0008 drops this table only, losing warning/selection audit; export first.
Development DB is not automatically migrated. Tests own only shelfcash_test.


## CURRENT FACT — S4.7 / migration0015

`recipes.assigned` boolean NOT NULL DEFAULT true giữ header/content/dates của
recipe đã withdraw làm evidence; chỉ assigned rows thuộc inclusive exclusion và
operational dated capture. Không nullable hóa ngày đầu vào domain, không xóa
version/lines. `recipe_schedule_changes` giữ proposal/preview và completion/audit;
`recipe_schedule_request_receipts` giữ replay evidence theo phase/actor/Store/Product.
DB guards chặn sửa retained proposal, completed receipt/audit và request receipt.
Downgrade0015 từ chối nếu tồn tại evidence hoặc unassigned content; clean roundtrip
được kiểm trên shelfcash_test, không migrate development DB. Exact ORM/schema,
manual flow và verification ở [current verification runbook](runbooks/FULL_TEST_FLOW.md).
