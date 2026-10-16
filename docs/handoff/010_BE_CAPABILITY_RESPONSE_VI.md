# START_HERE ? handoff FE th?ng nh?t

## Source v? ?i?m b?t ??u

CURRENT FACT S1 isolated WIP: the source OpenAPI now admits summary `/2` renderer,
prompt and validator values in three existing fields; paths/DTO fields remain
unchanged. The added `summary_narrative_fake_provider` example is labelled offline
projection; older examples keep their original pins. See the
[canonical summary contract](../PROCUREMENT_API_CONTRACT_VI.md#185-as01as02--current-fact-summary-contract)
and [feature limits](../features/DECISION_ASSISTANT.md#current-fact--s1-bounded-plan-narrative).
This WIP does not update a published ZIP, FE or runtime8103.

CURRENT FACT: combined backend c? **76 operations / 69 paths**, migration head
`l5_20261016_assistant_f4` (merge0030 v? f4_20261016_metadata_v2). Recovery checkpoint
`2e4a048` ???c merge gi? l?ch s? v?i Assistant main `e499112` t?i `e48c74a`.
Git commit ch?a t?i li?u/artifacts n?y s? h?u source provenance; kh?ng ghi SHA t?
tham chi?u. ZIP cu?i xu?t t? final main sau push: **PROVENANCE.json trong g?i** ghi
exact source SHA, remote main SHA v? tr?ng th?i ?? ??i chi?u. ??i chi?u manifest
tr??c khi d?ng; working-tree artifact kh?ng t? l? release/deployment.

FE pin c? `869eaec914aa6905d6b935889afebe7d973004ae`, OpenAPI SHA256
`790443d80350cc597c7c06179309e43303ba558de34017ea1dd4113de71fc1ee`.
[Diff machine-readable](openapi_diff_fe73.json) d?ng ??ng baseline hash: ch? th?m
AS01/AS02/AS03, kh?ng ??i/x?a73 operations ho?c schemas c?. Historical handoff ZIP
v? original baseline ???c gi?; kh?ng gh?p artifacts t? c?c nh?nh WIP.

??c theo th? t?:

1. [OpenAPI source](openapi.json) ? c?u tr?c request/response/headers/errors.
2. [API chung](../API_CONTRACT.md), [Authorization](../AUTHORIZATION_CONTRACT_VI.md),
   [Import](../IMPORT_MAPPING_API_CONTRACT_VI.md), [Planning/Assistant](../PROCUREMENT_API_CONTRACT_VI.md),
   [Notifications](../NOTIFICATION_API_CONTRACT_VI.md) ? workflow, meaning, quy?n.
3. [Recovery matrix v? journal allowlist](recovery_journal.json) ? method/path,
   phase, key/CAS/body, readers, exclusions v? journal field rules.
4. [V? d? ?? validate](examples.json) ? actual synthetic HTTP tr?n combined source,
   provider OFF; summary/chat/context/clarification, Store v? Import recovery.
5. [Current state](../CURRENT_STATE.md), [runbook](../runbooks/FULL_TEST_FLOW.md),
   [Assistant limits](../features/DECISION_ASSISTANT.md),
   [audit recovery](../reports/FE_019_BACKEND_RECOVERY_AUDIT.md).

## ?? c? trong source v? gi?i h?n availability

Hai BE bugs ?? s?a: delayed same-key confirm_review tr? matching durable receipt
tr??c completion/CAS guard trong continuation, sau current authority; canonical
Import worker ch? reconcile recognized uncertain COMMIT v?i durable proof. Programming
error sau commit v?n n?i l?n; completed state kh?ng th?nh failed/kh?ng write l?i.
Architecture repair chuy?n effective DB/limited-role query sang infrastructure,
kh?ng n?i guard/test. Receipt retention test d?ng migration graph hi?n t?i v? gi?
Store/Owner/audit/receipt sau failed destructive downgrade.

CURRENT FACT: T03 Store/Owner atomic; N13 grants audited replay; PR/MQ/N5/M04 workflow;
I01?I06 upload/analyze/preview/review/commit/completion; N6 receipt; planning config,
recipe schedule, C02/C03/N9; PDF N10/J01/N11/EX01; NF inbox/read. Permissions-v3/43,
Store isolation, exact arithmetic/CAS/idempotency/worker fencing kh?ng ??i.
TypeAdapter optimization gi? nguy?n. Forecast C ch? test-only/OFF, kh?ng promote.

Source availability kh?c deployed availability: task n?y **kh?ng restart8103,
kh?ng migrate demo/development, ??i .env/flags ho?c g?i SMTP/OpenRouter**. Kh?ng ??a
m?t base URL nh? ?? verified ph?c v? source m?i. Operator c?n ??i chi?u process/source
manifest v? DB head, review backup/quiescence/schema upgrade/flags r?i th?c hi?n qua
supported runbook trong nhi?m v? deployment ri?ng. FE integration ph?i ki?m tra
??ng serving artifact; health200 ch? liveness, kh?ng x?c nh?n schema/features.

## Assistant delta

| ID | Exact method/path | Ti?p t?c/recovery |
| --- | --- | --- |
| AS01 | POST `/api/v1/procurement-plans/{plan_id}/assistant/summary` | Explicit synchronous create/replay; UUID key, original body/evidence version. Location ??n AS02. |
| AS02 | GET `/api/v1/procurement-plans/{plan_id}/assistant/summary/{generation_id}` | Retained read; kh?ng implicit generate/recover/provider. |
| AS03 | POST `/api/v1/procurement-plans/{plan_id}/assistant/messages` | Same key/body POST replay. **Kh?ng GET message endpoint**; kh?ng gi? J01 polling. |

Current planning.result.read + budget.read + procurement.cost.read tr?n ??ng Store
cho c? ba; mutation th?m current session/Origin/CSRF/key. expected_evidence_version
l?y t? retained C03 response_version; mismatch409. Same key/different body409;
running/live ho?c unknown generation claim409. AS02 c? th? tr? retained running/failed;
GET kh?ng recover. Explicit operation-specific replay ch? recover proven-dead claim,
kh?ng l?p uncertain provider call; xem contract ?? ph?n bi?t terminal failure.

V6 m?c ??nh; candidate8 ch? explicit `AssistantChat(...,presentation_version=8)`
composition trial, ch?a c? operator selector hay FE field ch?n version. SUMMARY_LLM_ENABLED
v? CHAT_LLM_ENABLED ??c l?p, default OFF; IMPORT_LLM_SUGGESTIONS_ENABLED ri?ng.
Model OFF c? deterministic fallback/clarification; HTTP200 kh?ng ch?ng minh model
?? ch?y. Return structured context/pending clarification cho follow-up; history
kh?ng l? business evidence. Gi? unknown/missing name, version, references/diagnostics;
kh?ng suy t?n t? ID ho?c fabricate friendly labels. Summary/chat kh?ng thay solver,
kh?ng t? approve purchasing, t?o order/stock receipt ho?c ch?n l?i winner.

## Recovery ?? duy?t: FE persistent journal + BE hi?n c?

ACCEPTED DECISION: FE tri?n khai journal (khuy?n ngh? IndexedDB), persist **tr??c**
dispatch. Scope actor/Store/operation/resource; original key/body/CAS/timestamp theo
allowlist, pending/unknown/confirmed ho?c rejection c? semantics r?. Restore sau F5
ki?m current session/actor/Store, r?i explicit readback/exact replay. Fresh cookie/
CSRF l?y t? Auth hi?n t?i, kh?ng persist. Kh?ng t? t?o key m?i ?? gi?i quy?t unknown.
FE journal ch?a ???c implement/verify browser trong task BE n?y.

[recovery_journal.json](recovery_journal.json) l? field allowlist **default DENY**;
kh?ng serialize to?n request theo OpenAPI. full_body ch? cho T03(name/timezone/currency),
I01(data_date), I03(file-set/accepted/rejected IDs), I05 preview(phase/mapping_revision),
N4(amount), N21 commit(change/digest/confirm/warning IDs), N10(format/option/locale),
NF03(read) v? AS01(evidence/option/locale/detail). I05 commit ch? pure insert/NO_OP
v?i reason absent/null v? c?c correction arrays empty/absent ??ng JSON rules;
C02 ch? default/saved v?i requirements absent/null. Original field presence/array
order v?n gi?; ngo?i conditions th? full-body journal replay disabled.

C?c body ch?a review (grants/decision reason, mapping/source resolution, stock facts,
custom requirements, AS03 question/history/pending original question) ch? metadata
ho?c excluded theo JSON; **kh?ng b? field r?i replay body thi?u**. Handoff field
review ch? cho ordinary non-secret business metadata; kh?ng cho nh?p credentials
v?o c?c field ??. Password/token/session/CSRF/cookie, email/invitation proof, secret
keys, raw uploaded cells/file bytes lu?n excluded. Secret-bearing auth flows kh?ng
thu?c generic replay/journal. AS03 exact POST replay c? ? BE nh?ng kh?ng t? cho ph?p
persist to?n c?u h?i/l?ch s? h?i tho?i trong generic journal.

Actor isolation kh?ng thay XSS protection/shared-device policy. PROPOSAL FE: explicit
logout/retention UX, kh?ng silently expire unresolved intents; confirmed records ch?
x?a theo FE policy ???c review. Logout/clear journal **kh?ng cancel/rollback** write.
Kh?ng c? retention policy m?i ph?a BE, generic status/negative proof API ho?c
cross-device receipt discovery. Definitive abandon/fencing l? backlog ri?ng.

Empty list/absent receipt/403/404/timeout kh?ng definitive no-effect. Readback c?
th? m?i h?n receipt; replay denial gi? nguy?n original uncertainty. Payload hash
kh?ng t?i d?ng ???c body ?? m?t. Key m?i kh?ng x?c nh?n stock/Store m?i.

## Checklist FE ti?p theo

- Regenerate typed services t?76/69 v? ??c diff; ki?m serving source/schema ri?ng.
- Implement allowlisted durable pre-dispatch journal v? restore pending/unknown
  sau m?t response/F5; kh?ng automatic replay/new-key mutation.
- Store/actor switch c? l?p intent; logout/relogin d?ng fresh CSRF v? original scope;
  session h?t kh?ng ch?ng minh accepted worker rollback.
- Test stale CAS, revoked rights, concurrent acceptance/replay, same key/different
  body; retained receipt kh?ng reapply grants ho?c canonical data b? ??i sau ??.
- Test lookup empty tr??c request ??n tr?; kh?ng unlock competing creation/write
  t? empty/404/403 ho?c timeout. Test journal write failure tr??c dispatch.
- Upload: I02 c? BE exact multipart replay theo key + ordered client IDs/name/bytes
  hash, nh?ng FE helper018 ch?a h? tr?; kh?ng g?i ??y l? thi?u BE API. Kh?ng journal
  raw files/cells. Gi? accepted-file identities v? I04 quota/source-set authoritative.
- Preview review ?? persist trong I04; domain decisions ch?a submit kh?c persisted
  confirm_review/accepted commit resolutions. Kh?ng h?a m?i resolver choice ?? saved.
- Email/invitation proof, signup/password/reset flows d?ng operation-specific UX;
  verification kh?ng session/Store, invalid consumed token kh?ng ch?ng minh no-effect.
- Verify AS01/AS02/AS03 evidence version, unknown names/context/pending clarification,
  same-key replay v? current revocation; kh?ng invent GET messages.
- Browser/F5/full Owner/Staff E2E, XSS/shared-device acceptance v?n NOT_RUN ? BE task.

BACKLOG: accepted-file delete/replace/unseal; Today outlook/arrival/pending customer
decision; immediate canonical create+bind (staged proposals ?? c?); standalone saved
Preview domain decisions; richer token/session continuation; cross-device discovery/
negative fencing. Latest Run kh?ng l? pending purchasing approval; recommendation
kh?ng t?o order/receipt. Import curated templates/I1/I2 semantic WIP ch?a t?ch h?p,
kh?ng m? t? l? runtime ?? c?.

Verification m?i v? actual invocations/limits: runbook recovery integration v? g?i
verification. Kh?ng claim full-suite, browser, F5 E2E, deployment ho?c paid-model PASS.
