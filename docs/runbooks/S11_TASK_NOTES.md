# S1.1 Identity + Store schema cluster

HISTORICAL INFORMATION: observations and verification below describe S1.1 before
S1.2. The S1.1 contract remains accepted; current global head/state is in CURRENT_STATE.

Classification: ACCEPTED DECISION for the storage contract frozen in this authorized
slice; CURRENT FACT for pre-edit observations. No additional architecture ADR needed:
this slice implements ADR-002/007 persistence and future membership relationships.

- Observed state: clean working tree, S0 complete, no business models/tables; healthy
  local PostgreSQL. Existing `0001_scaffold` and scripts/tests must be preserved.
- Scope: three persistence models and migration `0002_identity_store` only. No
  domain services, repositories, public API, authentication or access enforcement.
- Public contract: health/routes/OpenAPI unchanged; snapshot taken before edits.
- Relevant authority: ADR-002 modular boundaries, ADR-007 PostgreSQL synchronous
  Session/psycopg/Alembic and isolated test DB; ADR-006 future authorization distinction.
- IDs: PostgreSQL UUID PKs with `gen_random_uuid()` server defaults; explicit IDs
  remain possible for deterministic tests. All required fields NOT NULL.
- User: email varchar(320), unique, nonempty, PostgreSQL-lowercase with no whitespace.
  Callers must supply canonical values; DB rejects noncanonical input, no automatic
  rewrite or full email/RFC/Unicode/authentication validation. password_hash opaque
  nonblank text, display_name nonblank varchar(200), active default true.
- Store: nonblank name varchar(200), not unique; nonblank timezone varchar(64),
  default Asia/Ho_Chi_Minh; currency varchar(3), uppercase three-letter shape,
  default VND. Defaults frozen here; IANA/ISO catalog validation and money rules deferred.
- Membership: UUID FKs to existing store/user, deletion RESTRICT; unique pair
  (store_id,user_id); role varchar(5), required OWNER or STAFF, no implicit role.
  delegated_permissions JSONB defaults [] and must equal []; vocabulary/authorization
  remain unaccepted, so nonempty permissions are rejected rather than invented.
- Common: active defaults true; created_at/updated_at TIMESTAMPTZ defaults now().
  Engine sessions use UTC. SQLAlchemy updates set updated_at=now(); raw SQL updates
  must explicitly maintain updated_at. No trigger framework or naive defaults.
- Indexes: unique email and membership pair already cover email/store lookup.
  Only extra index: membership user_id for reverse user-to-store membership lookup.
- Acceptance: fresh migrations/metadata match, fresh-session round trips, DB-level
  uniqueness/role/FK/default/timestamp/canonical email checks, delete restriction,
  exactly three business tables, existing regressions and manual inspection steps.
- Impact: BE persistence/tooling expectations only; FE and ML/Data none. Demo gains
  three empty tables, no seeded identities. Seed remains a schema-verifying no-op.
- Rollback: downgrade new revision to 0001_scaffold drops these three tables/data;
  guarded reset remains supported. Keep unrelated runtime/history untouched; no commit.
- Verification: targeted tests then full runner, healthy Compose, reset/current/status,
  seed, app import/OpenAPI/live health, pip check and scope/diff review. Test writes
  own only shelfcash_test. No next slice is authorized by completion.

## Acceptance verification — CURRENT FACT

Completed on 2026-10-05, Windows/Python 3.11.9:

- Targeted `python -m pytest tests/integration/test_identity_store_schema.py -q`:
  22 passed. Expected migration tables/metadata/PK/FK/index/unique/check/defaults
  agree, fresh-session User/Store/Membership persistence and UTC/update behavior pass.
- `./scripts/test.ps1 all`: 42 passed (14 unit, 26 integration, 2 API), one existing
  upstream warning. All destructive tests use shelfcash_test; no skipped integration.
- Compose up/ps: healthy PostgreSQL 17.11. Canonical reset/status/seed, Alembic
  upgrade/current pass: head 0002_identity_store, only three empty business tables
  and one revision row. Documented SQL inspection of columns/defaults/constraints
  succeeds, development counts remain empty after testing and live HTTP verification.
- App/model/domain import safety passes with DB connect forbidden; pre/post and
  live OpenAPI are exact matches. Live health HTTP 200 payload unchanged, server stopped.
- pip check and diff whitespace pass. API_CONTRACT/public API/domain/repos and
  dependency surface untouched; no S1.2 models/tables or seed fixtures, no commit.

S1.1 is complete, S1 remains in progress. Next proposed slice is S1.2 Catalog +
Recipe; no automatic authorization follows from this verification.
