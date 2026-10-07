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

CURRENT FACT: none of these mapping/import/permission workflows is implemented.
Mapping remains S5; authorization hardening remains S6. Minimum access enforcement
must be present whenever an earlier public operation needs it; S6 is no deferral
permission. Roadmap ordering is unchanged, no import code/schema/API is authorized.

DEFERRED: atomic versus partial import contract and detailed permission matrix;
no confidence threshold, critical-error vocabulary or extra approval policy is accepted.
Freeze those contracts/tests in their authorized slices. Affects future BE/FE,
ML/Data import trace and demo approvals; S2.1 forecast validation is independent.
