# ADR-008 — Import Idempotency and Correction Policy

## Status

ACCEPTED — authorized by S1.3 on 2026-10-05.

## Context

Different filenames may contain the same business facts; the same filename may
contain different content. Repeated imports must not duplicate canonical state or
silently replace a store's history. Sales corrections and inventory mutations need
different authority and audit rules.

## Decision

- Filename is display/source metadata, never data identity. Future import must
  detect exact duplicate content by store + content hash and, by default, avoid
  writing the same business data a second time. Hashing/import records are not
  implemented in S1.3.
- Classify each record: NEW (identity absent), UNCHANGED (same identity and values),
  CHANGED (same identity, different business values), INVALID (validation fails),
  CONFLICT (insufficient backend authority to choose a merge/correction).
- UNCHANGED performs no business write. NEW may insert after validation. CHANGED
  follows explicit domain-specific correction policy; never generic UPSERT EVERYTHING.
- A new upload is not replace-all. Rows absent from a file are not deleted unless
  a future explicit full-snapshot replacement contract authorizes that behavior.
- Sales identity is Store + Product + sales_date, never source/file. A repeated
  quantity 100 is UNCHANGED; a replacement value 105 is CHANGED, never an addition
  producing 205. Correction approval/write/audit implementation remains a later slice.
- Inventory changes must follow ADR-009: confirmed received lot state plus justified
  movement and balance update in one application transaction. An imported stock count
  does not authorize unexplained balance overwrite. Ambiguous lot identity is CONFLICT;
  nullable/nonunique lot_code alone is not an accepted universal import identity.
- Preserve enough provenance to trace accepted business records to source/import
  when needed. This does not require import_id on every S1.3 table. Inventory movement
  reference fields are reserved trace hooks; no ImportJob FK/type is fabricated.
- Import mode must be explicit: preview_only writes no business data; atomic can
  roll back the entire import on a critical failure; partial_success can persist valid
  rows and report rejected rows. Exact critical-error/approval contracts are future work.

## Consequences and boundaries

Canonical database uniqueness provides a backstop, not an import engine. There is
no parser, hash, classification code, correction workflow, mode implementation,
ImportJob/MappingProfile table or import API in S1.3. Preserve source trace and
domain authority when those features are authorized. LLM cannot determine new
business identities, invent fields or choose corrections.

## Rejected/deferred alternatives

REJECTED: filename identity, additive re-import of canonical sales, generic upsert,
default replace-all, silent deletion and unexplained stock overwrite.
DEFERRED: source identity/key mapping, provenance schema, correction permissions,
hash execution and import transaction/report contracts.

## Revisit conditions and affected areas

A future import slice must explicitly define each domain's identities/corrections,
mode and audit acceptance tests under this policy. Affects persistence, import/data,
authorization, future FE preview/report flows, demo reproducibility and tests.
