# Auth/session, assisted setup and B1/B2 self-service

CURRENT FACT customer onboarding: signup/A05/password/login không tự tạo Store;
T03 POST /api/v1/stores tạo Store/Owner/audit/receipt atomic cho holder verified.
Không accounts.json hoặc assisted setup cho khách. Metadata explicit, no business
seed; replay/current authority/isolation theo [contract](../AUTHORIZATION_CONTRACT_VI.md#self-service-stores).
Local setup/SMTP/callback/status và14 flows ở [FULL_TEST_FLOW](../runbooks/FULL_TEST_FLOW.md#customer-self-service).
Single opt-in email thread handles verification/reset/invitation. Parameterized
invitation FE callback đã hỗ trợ; EMAIL_VERIFY page/consumer và Store-create UI
còn cần FE nối. Không browser/real email workflow claim từ fake-delivery tests.

CURRENT FACT C2: PR01–PR04 add own Staff requests/catalogue and Owner union subset
decisions through the existing grants boundary. N13 keeps replace semantics; N14
adds nullable request/decision references. Approval notifications are distinct from
direct grants changes; retained replay never restores revoked grants. Workflow/DTO
authority is [the permission request contract](../AUTHORIZATION_CONTRACT_VI.md#permission-requests),
operating/test commands are in [FULL_TEST_FLOW](../runbooks/FULL_TEST_FLOW.md#collaboration-c2).

CURRENT FACT B4: linked HTTP/PostgreSQL acceptance combines these auth flows with
Staff invitations, live permissions-v3 grants, two-Store isolation and decline.
Both pre-registered and subsequently verified invitees are exercised with fake
delivery and fresh-session reads. RESET requests/failures preserve sessions;
completion revokes all holder sessions while preserving Store memberships/grants.
Coverage ownership and runnable targeted commands are in
[the runbook](../runbooks/FULL_TEST_FLOW.md#b4-authstaff-acceptance-without-fe-or-smtp).
Browser and real workflow-email acceptance remain pending.

CURRENT FACT S4.4 prerequisite: T01 cursor signing now uses server-private process
material through shared CursorSigner, not client-held session token as key. Binding
session/account/list/permissions/limit and422 stale/invalid behavior unchanged.
Old cursors require refresh after process/key replacement. Verified negative HTTP/
PostgreSQL case and scope limits: [historical scope notes (retired)](../runbooks/FULL_TEST_FLOW.md).

CURRENT FACT S4.2 extension: N12–N19 and encrypted-intent dispatcher now reuse
these session/proof/current-grant boundaries. See [Staff workflow](STAFF_PERMISSIONS_INVITATIONS.md).
The exclusions below describe the historical S4.1 slice scope; planning/one-time
bypass remain absent. Existing session/credential workflows remain; B1 and N7
now share the accepted10-attempt completion limit documented below.

CURRENT FACT: ten routes under `/api/v1`: A01 POST `/auth/login`, A03 GET
`/auth/me`, A04 POST `/auth/logout`, N7 POST `/auth/credentials/complete`, T01 GET
`/stores`, T02 GET `/stores/{store_id}`, B1 A02 POST `/auth/register`, A05 POST
`/auth/email-verifications/complete`, A06 POST `/auth/email-verifications/request`,
B2 A07 POST `/auth/password-reset/request`.
Product authority: [Authorization](../AUTHORIZATION_CONTRACT_VI.md#auth-self-service).
Forgot/reset request, decline, Store creation and one-time bypass remain outside B1.

## B1 configuration and FE flow

CURRENT FACT: AUTH_EMAIL_DELIVERY_ENABLED defaults false. Enabling it starts one
bounded account-email thread in the backend process. Configure TLS SMTP using the
existing AUTH_SMTP_HOST/PORT, sender and optional username/password, plus
AUTH_VERIFICATION_FRONTEND_URL (HTTPS verification page whose exact Origin is in
AUTH_ALLOWED_ORIGINS). The page cannot contain query/fragment/userinfo. Keep
AUTH_DELIVERY_ENCRYPTION_KEY (private base64-encoded random32-byte key) stable while
queued intents exist; neither API payload nor requester cookie chooses the target
email or redirect. Missing/disabled configuration gives generic503
EMAIL_DELIVERY_UNAVAILABLE/Retry-After60 before account lookup. Enabling this flag
authorizes configured delivery in that environment; synthetic acceptance uses a
fake adapter and fake SMTP exclusively, never production SMTP.

FE sequence: A02 `{email,display_name}` → generic202/check_email → read email
fragment token into memory, clear it immediately and keep no-referrer → A05
`{token,password}` →200/next_action=login → A01 → A03/T01. New account has zero
Stores. A06 `{email}` resends after60 seconds; response always has
retry_after_seconds=60 and exposes no account/delivery ID. All three POSTs require
exact Origin, no session CSRF, and never issue/rotate a cookie. FE must implement
its verification page separately; this change does not edit FE source.

On completion timeout or generic400 EMAIL_VERIFICATION_TOKEN_INVALID, try login
with the just-entered password or request a fresh verification; do not claim the
previous completion succeeded. Pending deliveries recover after restart; claimed
uncertain attempts have60-second leases and at most3 sends of the same token.
Duplicate email is possible, without duplicate completion. A known send failure
is retained privately; public resend can issue a fresh token after cooldown/rate
window. Reissue invalidates older tokens atomically with new intent acceptance.
Successful/failed/expired/cancelled delivery removes its secret transport copy,
retaining digest/outcome/history. SMTP receipt does not verify the account.

CURRENT FACT: B1 backend acceptance is complete with fake delivery on
`shelfcash_auth_test` / `shelfcash_auth_tester`. Synthetic HTTP/PostgreSQL tests
assert fresh committed state, races, stale proof/credential bindings, expiry after
lock waits, bounded uncertain-delivery retries, lost commit acknowledgment/retry,
rollback and recovery in a new process. Related auth/session/invitation regressions
are covered. The SMTP message
formatter uses a fake TLS client. Real SMTP/browser delivery and timing equality
are not established; execution results are reported in the conversation.

## B2 configuration and FE flow

CURRENT FACT: B2 backend/fake-delivery acceptance is complete on the isolated
Auth DB. Tests cover session revocation, failure/uncertain commit retry, private
delivery recovery in a fresh process, concurrent completion/claims, no authority
changes, additive migration/metadata and related B1/auth/invitation regressions.

CURRENT FACT: A07 accepts the existing `{email}` DTO and returns the same generic
202 PublicEmailAcceptance as B1. Only active verified accounts receive a RESET
intent, including verified accounts whose credential is still unset. Unknown,
unverified and inactive accounts create no reset token/intent and return the same
acknowledgment. Service-wide unavailable503 occurs before account lookup.

Configure AUTH_PASSWORD_RESET_FRONTEND_URL as an HTTPS reset page with exact
allowlisted Origin; no query/fragment/userinfo. B2 shares AUTH_EMAIL_DELIVERY_ENABLED,
AES key, TLS SMTP settings and one local worker with B1; each workflow uses its
own configured page and capability. There is no fallback to the verification URL.
A07 accepts no redirect/role/Store fields and never resolves target from a cookie.

FE sequence: A07 `{email}` ?202/check_email ? email `#token=...` ? clear fragment,
keep token only in memory/no-referrer ? N7 `{token,password}` ?200/next_action=login
? A01. N7 remains the SETUP/RESET consumer, dispatched by stored token purpose;
EMAIL_VERIFY tokens belong only to A05. Request/reissue/pre-commit failure preserve password
and every current session. Success increments credential revision, consumes reset
tokens, cancels queued reset secrets, revokes all account sessions and records audit
in one transaction. It gives no session and changes no Store/membership/grants.

Reissue after60 seconds invalidates older RESET tokens only after new encrypted
intent acceptance; public email limits are shared with B1 (3/email,20/IP/15min).
N7/B1 completion share10/IP/15min. Lost commit acknowledgment may leave a durable
but unreturned acceptance/completion: retry request during cooldown does not create
another intent; consumed-token retry returns generic400, then try login with the
new password. Known delivery failure permits public reissue after cooldown;
uncertain claimed sends recover with60-second leases and at most3 attempts.
Expired/cancelled/settled secrets are scrubbed while provenance is retained.
Completion remains available when SMTP capability is disabled. Real SMTP/browser
and timing-equality certification remain outside fake-delivery acceptance.

## FE transport

### Local Gmail smoke/demo profile

CURRENT FACT: `scripts.auth_demo` prepares a separate Compose project
`shelfcash-auth-demo`, PostgreSQL17 on127.0.0.1:5434 and a named volume, with
database/role `shelfcash_auth_demo`. Only an empty DB can be claimed with its
ownership marker; initialization preserves existing demo data and migrates the
Auth head. There is no reset or business seed. Acceptance/Import/development DBs
are never targets. Private DB credentials, stable delivery encryption key and
local TLS key live under ignored `runtime/auth-demo/private`; SMTP settings remain
in the user's `.env`/environment. Do not print private files or run Compose config
to dump interpolated credentials. Production contracts/source are unchanged.

Run from the backend worktree in PowerShell:

```powershell
.venv\Scripts\python.exe -m scripts.auth_demo init
.venv\Scripts\python.exe -m scripts.auth_demo status
# Foreground HTTPS server and account-email dispatcher:
.venv\Scripts\python.exe -m scripts.auth_demo serve
# Another terminal, or Ctrl+C in the server terminal:
.venv\Scripts\python.exe -m scripts.auth_demo stop
# Wait for Application shutdown complete before stopping the demo DB:
.venv\Scripts\python.exe -m scripts.auth_demo db-stop
```

The server binds loopback8102 with HTTPS, access logging disabled, Secure/HttpOnly
session cookies and no Import/Planning/PDF/LLM workers. Both account-email
dispatchers enforce a demo-only recipient boundary: only AUTH_SMTP_USERNAME may
reach SMTP. Other deliveries fail privately without changing public responses.
An empty queue sends nothing; user browser actions enqueue further account email.

Gmail uses smtp.gmail.com:465, SMTP_SSL and ssl.create_default_context(), with
hostname/certificate verification. The `smoke` command reserves its attempt before
network access and sends one non-token message to AUTH_SMTP_USERNAME. It never
retries authentication failure or ambiguous delivery. Preserve smtp-smoke.json;
do not remove it to resend without new authorization. CURRENT FACT: the one
authorized smoke was SMTP-accepted and inbox arrival was subsequently confirmed
by the user. No further smoke email is authorized. Signup/verification/reset
workflow emails to the configured test username are authorized; no other recipient
is permitted in this demo. Inbox delivery does not itself verify an Auth account.
HTTPS health/CORS and clean shutdown were exercised against the
empty demo DB, not browser E2E or a real credential-email workflow.

The profile overrides configuration without editing `.env`:

| Purpose | FE HTTPS page | Consumer under `/api/v1` |
| --- | --- | --- |
| EMAIL_VERIFY | `https://localhost:5173/verify-email` | POST `/auth/email-verifications/complete` |
| SETUP | `https://localhost:5173/setup-password` | POST `/auth/credentials/complete` |
| RESET | `https://localhost:5173/reset-password` | POST `/auth/credentials/complete` |

BE handoff: API base https://localhost:8102, exact allowed Origin
https://localhost:5173. Keep both hosts localhost and use HTTPS with credentials
include. FE owns its source, HTTPS/API configuration, screens and adapters. The
BE launcher does not generate FE configuration or start FE. Earlier temporary
FE verification tooling is retired; retained ignored runtime inputs are not part
of the supported workflow.

The generated self-signed certificate has localhost and
127.0.0.1 SANs and30-day validity. Trust it locally or accept the local browser
certificate warning on both origins before API requests; never disable Gmail
TLS verification. The launcher does not install OS trust or silently replace an
expired certificate/key. Its init preserves existing configuration and data.

CURRENT FACT: the inspected sibling Shelfcash_FE_v2 has login/session screens,
but no signup/verification/setup/forgot/reset routes or adapters. Base Vite HTTPS
is absent and remains an FE-owned prerequisite.
Unknown routes redirect to login. FE needs public `/signup`, `/verify-email`,
`/setup-password`, `/forgot-password`, `/reset-password`, outside AuthGuard and
StoreGate. This backend task does not edit FE source.

The current auth.data.ts adapter implements only login/readSession/logout.
FE handoff: extend the FE boundary with register(A02), verification request(A06), verification
complete(A05), reset request(A07) and credential completion(N7), using existing
requestJson with method POST and auth public; its default protected mode otherwise
requires a session CSRF token. Preserve credentials include/no-store. Validate
the data/meta/error envelope and workflow DTOs; acceptance is
{next_action:check_email,delivery:{status:accepted},retry_after_seconds:60},
completion is {next_action:login,completed_at}. Signup accepts email/display_name
only; email requests accept email only; completion accepts token/password only.
Password is12..128 characters and at most1024 UTF-8 bytes; token at most512 UTF-8
bytes. Do not log inputs or store token/password in localStorage/sessionStorage.
Public pages must read and clear the fragment before any fallback redirect,
analytics or unrelated fetch. A consumed/stale token is not a success indication;
on an uncertain completion try login with the chosen password before reissue.

Browser checklist after those prerequisites are implemented:

1. Signup only with AUTH_SMTP_USERNAME: A02 `{email,display_name}` gives202.
   Open the email, read fragment token into memory, immediately clear it with
   history replacement/no-referrer; A05 `{token,password}` gives200/login action.
   A01 login and A03 me succeed; T01 lists zero Stores. Do not create Store/grants.
2. A06 `{email}` resends after60 seconds. Generic202 is acknowledgment, not inbox
   evidence. Keep token/password out of console, logs, screenshots and reports.
3. Keep authenticated browser A and a separate profile B. A07 `{email}` requests
   reset; A's A03 still returns200. Open reset link in B, clear fragment and call
   N7 `{token,password}`. After200, A's A03 returns401; old-password login fails,
   new-password login succeeds. N7 itself issues no session. Reusing the token
   fails; expired/invalid completion preserves A's session.
4. All fetches use credentials include, with browser-supplied exact Origin.
   Logout sends X-CSRF-Token from login/me. Handle unavailable/cooldown errors
   generically and retain canonical password validation. Manual inbox/browser
   evidence remains separate from backend fake-delivery acceptance.

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

## CURRENT FACT — integrated BE runtime

The integrated worktree has a separate BE-only HTTPS8103 demo on
`shelfcash_integration_demo`, migration0024, limited runtime/migration roles,
exact Origin `https://localhost:5173` and Secure __Host cookies. It preserves the
older S4.11/Gmail demo databases. Commands, certificate trust, private synthetic
holder credentials and current callback ownership are in
[FULL_TEST_FLOW](../runbooks/FULL_TEST_FLOW.md#integrated-demo-runtime).
Current sibling FE source implements `/credentials/complete` and
`/invitations/:invitationId`; this supersedes the historical missing-setup screen
observation above for this runtime. FE HTTPS/verification remains pending.
Integrated SETUP/RESET callbacks use `/credentials/complete`; EMAIL_VERIFY and SMTP
invitation callbacks remain unset pending FE/formatter alignment. SMTP settings
are reused privately where present, but delivery stays OFF: no real email in setup.
Private assisted delivery and public credential/invitation completion provision
synthetic holders; Staff has only explicitly offered `menu.read`. Browser E2E and
real email remain unverified; runtime TLS/session/Store isolation probes pass.

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
Canonical permissions-v3 is immutable plain Python; Staff grants independent, Owner
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
peerIP/15min; B1 verify and N7 share10 attempts/peerIP/15min. Public email requests
use20/IP and3/canonical-email/15min, with60-second issuance cooldown. Email-key
exhaustion remains generic202; IP exhaustion gives429 Retry-After;
no permanent account lock. Old limiter rows/history are not auto-purged in this
slice; retention/maintenance and production capacity testing remain technical debt.
Password hashing runs synchronously in the request worker; no security/latency SLA.

Commit/cleanup errors never become successful HTTP results. Auth does not reconcile
uncertain commits to success: a lost acknowledgment can leave a durable but unreturned
session/receipt/completion. Credential retry may find consumed token; user then
tries login as specified. Session never leaves server unless confirmed commit
returned. Provision reference supports retry; issue cannot recover secret material.
No modification to S2/S3 uncertain-commit semantics.
