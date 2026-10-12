# S4.1 — public auth/session and assisted setup

CURRENT FACT S4.4 prerequisite: T01 cursor signing now uses server-private process
material through shared CursorSigner, not client-held session token as key. Binding
session/account/list/permissions/limit and422 stale/invalid behavior unchanged.
Old cursors require refresh after process/key replacement. Verified negative HTTP/
PostgreSQL case and scope limits: [historical scope notes (retired)](../runbooks/FULL_TEST_FLOW.md).

CURRENT FACT S4.2 extension: N12–N19 and encrypted-intent dispatcher now reuse
these session/proof/current-grant boundaries. See [Staff workflow](STAFF_PERMISSIONS_INVITATIONS.md).
The exclusions below describe the historical S4.1 slice scope; planning/one-time
bypass remain absent. No S4.1 session/credential product behavior changed.

CURRENT FACT: six routes under `/api/v1`: A01 POST `/auth/login`, A03 GET
`/auth/me`, A04 POST `/auth/logout`, N7 POST `/auth/credentials/complete`, T01 GET
`/stores`, T02 GET `/stores/{store_id}`. Implementation scope is S4.1 only; actual
verification and limits are in [historical scope notes (retired)](../runbooks/FULL_TEST_FLOW.md).
Product authority: AUTHORIZATION_CONTRACT_VI current v1. No self-registration,
invitation/grant editor, planning API, one-time bypass or automatic next slice.

## FE transport

Use HTTPS and `credentials: include`. Mutations require exact allowlisted Origin;
logout with a valid session also requires X-CSRF-Token from A01/A03. Login and N7
need Origin, not an existing CSRF token. Cookie is opaque random256-bit,
`__Host-shelfcash_session; Secure; HttpOnly; SameSite=Lax; Path=/`, no Domain.
Ordinary session idle30 minutes/absolute8 hours; remembered idle7 days/absolute30
days and Max-Age30 days. Only successful authenticated requests extend idle.
Login revokes a presented old session and rotates session/CSRF. Logout204 has no
body; expired/absent session still204 after Origin check. Any401 clears cookie.
Auth/private reads have no-store and Referrer-Policy:no-referrer.

JSON is data/meta/error; required nulls are preserved, UTC times use Z. Unknown
fields422. Login failures have the same INVALID_CREDENTIALS shape for absent,
inactive, wrong password or unusable credential. Errors never echo request inputs.
No Store login200/count0/defaultnull; exactly one accessible Store gives default;
multiple give null. Selection remains local per FE tab. Store context has no money.
T01 signed cursor binds session/account/current list+permissions/limit, sorted
name/UUID; changed list invalidates cursor with422 INVALID_CURSOR. No cached grant
snapshot authorizes a later request.

## Configuration and assisted manual flow

Set AUTH_ALLOWED_ORIGINS as JSON exact origins, e.g. `["https://fe.example.test"]`.
Default empty list denies browser mutations. Production never uses insecure
cookies. Explicit AUTH_DEV_COOKIE=true is permitted only development/test and
backend requests on loopback; it uses separate `shelfcash_dev_session`, never
weakens production __Host cookie. Do not use external HTTP origins or proxy headers
to disable security. Proxy/client-IP trust is deployment configuration: runtime
uses ASGI peer IP, not client-provided X-Forwarded-For.

Configure AUTH_OPERATOR_ID and secret AUTH_OPERATOR_KEY through deployment secret
configuration. Operator is a support audit identity, not a Store role. Verify the
account holder and requested Store ownership outside the app; record non-secret
case/evidence references. Commands require a hidden operator credential prompt:

```powershell
.venv/Scripts/python.exe -m scripts.provision_auth provision-store --command-file verified-owner.json
.venv/Scripts/python.exe -m scripts.provision_auth provision-account --command-file verified-account.json
.venv/Scripts/python.exe -m scripts.provision_auth issue-credential --command-file verified-credential-request.json
```

First two commands contain request_reference, evidence_reference, email,
display_name, optional existing_user_id. Store command also store_name, timezone,
currency. Existing email alone never binds ownership or resets password: operator
must supply the independently verified user UUID. Account-only creates no membership.
Provision writes User/unusable credential state, optional Store/OWNER membership
and audit atomically. Same reference/content/operator replays receipt; different
content409. No automatic backfill or role conversion.

Credential request contains user_id, purpose SETUP/RESET, verified_email and the
two references. SETUP only for unusable credential; RESET only for usable one.
Configure AUTH_SMTP_HOST/PORT (TLS465), optional username/password,
AUTH_DELIVERY_SENDER and HTTPS AUTH_FRONTEND_URL pointing to credential completion
screen. Real SMTP adapter sends only to verified holder email. Link token is in
fragment; FE consumes in memory and clears fragment before N7. CLI prints only
IDs/delivery status, never token/password/provider exception.

Issuance stores only SHA256 digest, user/credential revision and30-minute expiry.
New issuance invalidates prior tokens. No raw-token recovery or automatic retry;
use a new request reference after uncertain delivery. SMTP is outside DB atomicity:
duplicate/uncertain mail is possible, SMTP acceptance is not proof of receipt or
ownership. Delivery failure invalidates token and writes failure audit; if recording
fails the command errors, never falsely reports delivered. Actual external delivery
is an environment prerequisite, not claimed verified by synthetic tests.

N7 hashes untrimmed password with Argon2id (64MiB,t3,p4), consumes token, increments
credential revision, revokes sessions and records audit in one transaction. Only
one concurrent completion succeeds; retries get400 CREDENTIAL_TOKEN_INVALID.
Reset issuance itself keeps existing sessions; completion revokes them. User
deactivation has an additive PostgreSQL trigger revoking auth sessions atomically,
so later reactivation cannot resurrect them. This does not alter run state.

## Persistence, boundaries and limits

Migration0010 adds auth_accounts/auth_sessions/credential_tokens/membership_grants/
auth_audit/auth_rate_limits; existing S1 permissions=[] constraint remains. Verified
evidence reference/time is operator attestation, not automatic identity verification.
Sessions store token digest and bound CSRF token; CSRF alone cannot authenticate.
Audit contains references, IDs, digest/time, never passwords or raw tokens.
No update/delete audit endpoint. Privileged SQL remains outside application controls.
Additive StoreMembership.authorization_revision starts at1 without role/grant
backfill. PostgreSQL triggers advance it on active/role changes and each actual
grant-row change; no-op updates preserve it. Versions include this revision, so
grant removal/regrant or active off/on cannot revive an old authorization version.
This is a minimal CAS seam for S4.2, not its editor/audit workflow. Membership/list
reads lock authority rows for consistent current summaries, never during computation.
Canonical permissions-v2 is immutable plain Python; Staff grants independent, Owner
effective catalogue only in active owned Store. Unknown stored keys fail closed.

AuthUseCases owns fresh short sessions. `authorize_in_session` derives actor from
token, locks User→session→Store→membership and checks current grants; future mutation
writers must lock those same authority rows before commit. It never commits for
caller. `authorize_resource` adds a server-side `(resource_id, store_id)` predicate;
trusted application composition supplies the model, browser never supplies a role.
Accessible Store with missing action403; inaccessible/cross-Store resource404.
No one-time approval allowed in error details. S1 internal writers remain trusted
internal entrypoints, not automatically protected HTTP routes.

Persistent fixed-window limits: login5 failures/account+peerIP/15min;100 attempts/
peerIP/15min; credential20 attempts/peerIP/15min. These two unspecified IP ceilings
are delegated technical safety limits, not business requirements.429 Retry-After;
no permanent account lock. Old limiter rows/history are not auto-purged in this
slice; retention/maintenance and production capacity testing remain technical debt.
Password hashing runs synchronously in the request worker; no security/latency SLA.

Commit/cleanup errors never become successful HTTP results. Auth does not reconcile
uncertain commits to success: a lost acknowledgment can leave a durable but unreturned
session/receipt/completion. Credential retry may find consumed token; user then
tries login as specified. Session never leaves server unless confirmed commit
returned. Provision reference supports retry; issue cannot recover secret material.
No modification to S2/S3 uncertain-commit semantics.
