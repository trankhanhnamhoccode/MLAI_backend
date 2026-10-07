# Import / Mapping

Status: PROPOSED / NOT IMPLEMENTED.

ACCEPTED DECISION: [ADR-008](../adr/ADR-008-import-idempotency-correction-policy.md)
governs future content/business identity, classification, correction/provenance and
explicit modes. Inventory changes also follow ADR-009. These policies are not an
implemented parser/import/correction workflow. No ImportJob, MappingProfile, hash,
Excel parser, preview, import mode or public payload/endpoint contract exists.

## Data completeness — ACCEPTED DECISION, ADR-010

| Level | Future mapping behavior |
| --- | --- |
| REQUIRED | Missing sales date/product/quantity is INVALID, without guessed values. |
| CONDITIONAL_REQUIRED | Missing lead time blocks delivery feasibility; missing expiry blocks expiry-based computations where required. |
| OPTIONAL_WARNING | Unknown received_date permits current stock but warns that inventory-age analysis is unavailable. |
| OPTIONAL | Missing applicable optional metadata, e.g. movement note, produces no warning for the current use case. |

These levels apply to named use cases. Canonical SupplierTerm is deliberately strict:
effective_from and procurement inputs including lead time must be established before
promotion. Partial supplier identity can exist without a canonical term.

Missing != zero, false, upload date, snapshot date or arbitrary default. MISSING
means absent values; AMBIGUOUS means present values with unresolved meaning.

| Value origin | Meaning |
| --- | --- |
| SOURCE_EXPLICIT | Source states the fact directly. |
| DETERMINISTIC_DERIVED | Proven source/unit inputs yield explainable, testable deterministic results. |
| SYSTEM_ASSIGNED | Backend-owned metadata such as internal canonical version. |
| UNKNOWN | No established fact or certain derivation. |
| AMBIGUOUS | More than one plausible interpretation remains. |

Known 15 kg/pack and 28,000 VND/kg imply 420,000 VND/pack, not 28,000 per pack.
Unknown price units cannot be guessed. LLM suggestions are not canonical truth.
Unknown effective date cannot become upload date. Snapshot date is not receipt date.
Expiry derivation requires known receipt, known accepted shelf life and an explicit
accepted domain derivation rule; no such automatic derivation is implemented here.

## Readiness, warnings and canonical promotion

Valid data may be ready for display but not delivery feasibility or inventory-age
analysis. Future mapping retains raw values, ambiguity, unknowns, decisions, warnings
and conflicts; canonical storage is not a catch-all for unresolved raw data.
Future warning shape includes code, severity, field, entity and impact:

```json
{"code":"MISSING_RECEIVED_DATE","severity":"WARNING","field":"received_date","entity":"inventory_lot","impact":"Inventory age analysis unavailable"}
```

PROPOSAL / illustrative future preview, not an implemented API:
100 rows: 82 READY, 12 READY_WITH_WARNINGS, 4 INVALID, 2 AMBIGUOUS.
Mapping/readiness states are distinct from ADR-008's business-change classification
NEW/UNCHANGED/CHANGED/INVALID/CONFLICT. No preview, warning endpoint, readiness column,
staging, parser, mapping engine or import behavior is implemented.
