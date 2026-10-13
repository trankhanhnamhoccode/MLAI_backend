# ADR-013 — Future Store mapping and approval direction

## Status

ACCEPTED — future product direction explicitly authorized in the S2.1 task,
2026-10-07. Classification: ACCEPTED DECISION for future behavior, not runtime fact.
Related ADR-004/008/010; no replacement or retroactive edit.

## Context / decision

Future import is Store-scoped with OWNER/STAFF and delegated actions. An authorized
mapper may approve a mapping they created. Profiles are separate by source/report
type; reviewed mapping versions are immutable. Approved mapping runs deterministically.
Mapping approval is distinct from import confirmation. Import audit retains the
exact mapping version used. LLM suggestions cannot create canonical facts or bypass
authorization; unknown semantics stay unresolved until approved rules establish them.

## Boundaries / consequences

HISTORICAL INFORMATION (S2.1 issuance): none of these mapping/import/permission
workflows was implemented. Mapping remained S5; authorization hardening remained S6.
Minimum access enforcement
must be present whenever an earlier public operation needs it; S6 is no deferral
permission. Roadmap ordering is unchanged, no import code/schema/API is authorized.

HISTORICAL INFORMATION (S2.1 deferred details): atomic versus partial import
contract and detailed permission matrix;
no confidence threshold, critical-error vocabulary or extra approval policy is accepted.
Freeze those contracts/tests in their authorized slices. Affects future BE/FE,
ML/Data import trace and demo approvals; S2.1 forecast validation is independent.

CURRENT FACT (2026-10-12): mapping/import/authorization workflows are now implemented;
see [CURRENT_STATE](../CURRENT_STATE.md). The current user-approved
[Import](../IMPORT_MAPPING_API_CONTRACT_VI.md) and
[Authorization](../AUTHORIZATION_CONTRACT_VI.md) contracts specify the previously
deferred permission matrix: Owner approves/activates reusable profiles, Staff may
propose under grants. An Owner may approve a profile they created. This applies
the accepted self-approval decision, does not require two separate people, and
does not supersede this ADR. Batch confirmation and commit require current rights.
