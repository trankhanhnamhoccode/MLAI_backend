# ADR-010 — Data Completeness and Missing Business Facts Policy

Status: ACCEPTED

Classification: ACCEPTED DECISION. S1.3.1, 2026-10-05.
Related: ADR-001, ADR-007, ADR-008, ADR-009. Their accepted decisions remain intact.

## Context

Source examples can contain known current lot quantity/expiry without receipt date,
or a supplier price per kg without an effective date. Canonical facts must preserve
their real meaning rather than make incomplete inputs appear computation-ready.

## Field completeness

| Level | Missing-field behavior |
| --- | --- |
| REQUIRED | INVALID; no fabricated value. Sales date/product/quantity are examples. |
| CONDITIONAL_REQUIRED | Required by a specified condition/use case; missing inputs block that computation, e.g. lead time for delivery feasibility. |
| OPTIONAL_WARNING | Record can remain valid; issue a structured warning describing lost capability, e.g. unknown lot receipt date. |
| OPTIONAL | Absence has no impact on the current use case and generates no warning. |

Each future mapping field must declare a level for its applicable use case.
Missing is never zero, false, upload date, snapshot date or an arbitrary business
default. Explicit accepted defaults/rules must be distinguishable from source facts.

## Source fact classification

| Origin | Meaning |
| --- | --- |
| SOURCE_EXPLICIT | Source directly states the fact. |
| DETERMINISTIC_DERIVED | Proven source/unit inputs support deterministic, explainable, testable derivation. |
| SYSTEM_ASSIGNED | Backend-owned metadata, such as internal canonical version 1. |
| UNKNOWN | Source supplies no fact and no certain derivation exists. |
| AMBIGUOUS | Data exists but multiple plausible meanings remain unresolved. |

MISSING means absent data; AMBIGUOUS means present data with unclear meaning.
They remain separate. LLM suggestions cannot become canonical business truth.

## Canonical promotion and computations

A canonical record may be valid yet not ready for every computation. Unknown lead
time blocks delivery feasibility; it must never become zero. Readiness is evaluated
per use case, without fake fallback values. No readiness column is required now.

SupplierTerm remains strict canonical procurement input: effective_from, pack cost,
pack quantity, minimum packs and lead time must be known before promotion. Supplier
identity can exist independently. Missing effective_from stays unresolved in future
mapping; upload date is not an effective date. Internal version is SYSTEM_ASSIGNED.
Canonical pack_cost means cost of one complete pack in Store.currency. Proven
15 kg/pack and 28,000 VND/kg yield 420,000 VND/pack; 28,000 is not pack_cost.
Keep this representation; future normalization requires established unit semantics.

InventoryLot represents actually received stock, even if its receipt date is unknown.
received_date is OPTIONAL_WARNING, nullable, without a default. Required lot identity
(canonical ID), Store, Ingredient, quantity and matching base unit still apply.
Current stock can be used; future FEFO readiness depends on known expiry; inventory
age analysis is unavailable without receipt date. Snapshot date is not receipt date.
Expiry order is checked when both receipt and expiry are known. Missing tracked expiry
remains unknown. Derivation would require known receipt, accepted shelf-life fact and
an explicit accepted domain derivation rule; this ADR does not enable automatic expiry
derivation. Incoming stock remains outside InventoryLot under ADR-009.

Canonical tables hold sufficiently established entity facts. Future import/mapping
retains raw values, unknown/ambiguous states, mapping decisions, warnings and conflicts.
Canonical nullable warning fields do not imply storing every raw ambiguity there.

## Structured warnings and implementation boundary

Future warnings contain at least code, severity, field, entity and impact. Example:

```json
{"code":"MISSING_RECEIVED_DATE","severity":"WARNING","field":"received_date","entity":"inventory_lot","impact":"Inventory age analysis unavailable"}
```

These are accepted future boundary semantics, not an implemented warning API, import
engine or readiness service. S1.3.1 changes only receipt-date nullability/date-check
clarity through 0005. Downgrade restores NOT NULL and refuses unresolved NULL rows;
it must not backfill invented dates. Development reset remains an explicit alternative.
