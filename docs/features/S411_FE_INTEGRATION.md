# S4.11 consumer workflow and acceptance checklist

Authority: the shared API and three specialist contracts + current DTO/OpenAPI. ZIP10/10 is historical
baseline; source DTOs/current OpenAPI carry current definitions.
Packaging PASS does not mean runtime/FE browser acceptance. Local profile/runbook
is [current runbook](../runbooks/FULL_TEST_FLOW.md); private values never enter handoff.

1. A01 receives session cookie/CSRF; use A03 and T01/T02 current authority/Store day.
   Browser credentials include; never store passwords/tokens in VITE/localStorage.
2. I01 creates only a draft. I02 sends files[]/client_file_ids[]; preserve original
   files/key/IDs on uncertain retry. HTTP200 may include rejected receipts. Read
   I04 for whole-batch quota/source-set/version; acknowledge every rejected ID at
   I03, exact accepted scope, file-set and If-Match. Seal prevents more uploads.
3. Poll real J01/I04, respect2000ms hints. M01/M02/M03 show actual classification,
   fields/options/source issues. M04 writes explicit manual review if provider is
   unavailable. Owner approves reusable profile only when required. Approved
   profile reuse is Store-scoped; IMPORT_VALUE must be supplied per batch.
4. I05 preview pins mapping/read-set. Wait for preview job, re-read I04; review
   before/after/errors. confirm_review pins digest/revision with explicit reason.
   Mapping/value/IGNORE edits invalidate both preview and confirmation. Commit
   needs exact retained pins; reason required only for actual correction/merge/
   count/amendment. Poll J01 then I06 retained completion; 2xx is not DB proof.
5. Read R01/C01 before planning; separate data validity, execution availability,
   missing/unknown and estimated exclusions. Save N1–N3 is independent of
   readiness; N4 cap requires correct create/replace conditional header.
6. C02 uses default/saved/custom and UUID key; queued202/Location/Retry-After.
   Poll C03 until terminal. No result yet is null; no eligible winner differs from
   proven infeasibility. BASELINE fixture quality is not trained quality/SLA.
7. C04/C05 separate captured physical stock from option-specific hypothetical
   daily demand/FEFO/arrivals. Conditional-null result_digest uses snapshot
   integrity, never fake digest/zero. C08 renders retained engine reasons.
8. N9 reopens the same Run UUID. H01/H02 use first-upload Store date, not data_date;
   signed cursor/snapshot errors require refresh, no mixed pages. Current granular
   rights can deny previously accessible history/result/download.
9. N10 explicitly includes option_id:null to select winner or real candidate ID;
   J01 PDF discriminated context/result includes private relative download URL,
   SHA/bytes. N11 fetches authenticated PDF binary, checks status/headers; never
   parse it as JSON or expose private filesystem path. GET does not render again.

Error handling:400 malformed headers/transport,401 unauthenticated,403 current
rights/CSRF/Origin,404 foreign/notfound,409 conflicting identity/stale evidence or
not-ready,412 CAS revision,413 admission bound,422 typed validation/reason/ACK,
428 missing conditional,503 integrity/artifact unavailable. Use actual code/body
for each operation; do not blindly replay mutations with new keys. Null/omitted/
zero remain distinct; unknown cost/date/completeness stays explicit.

Previous browser evidence is historical; fresh verification is reported in the conversation. Checklist still required for full browser
acceptance: UI login/reload/logout; authenticated upload/partial receipts/seal/
polling; manual mappings/profile/review/commit; missing/invalid/denial states;
planning and retained screens/history; private PDF download; current revocation;
restart sessions/artifacts; screenshots/accessibility and no mock fallback.
Current FE source has mapping/planning integration, but whole-chain browser continuation remains NOT_RUN; retained-history/PDF controls are incomplete.

HISTORICAL INFORMATION from prior Edge verification: nine existing-screen gates passed,
including normal Staff Menu grant/Inventory denial. Complete browser status stays
PARTIAL. H01/H02 emit explicit meta.warnings:Notice[]; nonterminal status is
in_progress and Notice.details is not mandatory. Do not hide malformed envelopes
with defaults. Current examples/s411 supersede old S410 traces for those shapes.
Concurrent history reads retry only40001 as a whole with current rights/snapshot,
five attempts/0.75s total backoff; other failures and exhaustion remain explicit.
