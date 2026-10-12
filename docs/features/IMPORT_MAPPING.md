# Import / Mapping

CURRENT FACT: Import đã có parser/staging/Owner mapping approval/preview và atomic
canonical commit. Workflow/status/permissions do
[Import contract](../IMPORT_MAPPING_API_CONTRACT_VI.md) sở hữu; implementation và
giới hạn parser/rules/reuse ở [Import staging](IMPORT_STAGING_PREVIEW.md).

ACCEPTED DECISION: [ADR-008](../adr/ADR-008-import-idempotency-correction-policy.md)
governs content/business identity, classification, correction/provenance and
explicit modes. Inventory changes also follow ADR-009. ImportJob/profiles/hash/
parser/preview hiện đã có; không phải mọi correction/import mode đề xuất trong
ADR đều đã wired. Runtime facts cần đối chiếu contract/code/tests được dẫn ở trên.

## Data completeness — ACCEPTED DECISION, ADR-010

| Level | Accepted completeness policy |
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
analysis. Mapping retains raw values, ambiguity, unknowns, decisions, warnings
and conflicts; canonical storage is not a catch-all for unresolved raw data.
Illustrative warning below includes optional field/entity/impact; current Import
Notice requires code/severity/message and exposes optional source_location:

```json
{"code":"MISSING_RECEIVED_DATE","severity":"WARNING","message":"Inventory age analysis unavailable","field":"received_date","entity":"inventory_lot","impact":"Inventory age analysis unavailable"}
```

PROPOSAL / illustrative future preview, not an implemented API:
100 rows: 82 READY, 12 READY_WITH_WARNINGS, 4 INVALID, 2 AMBIGUOUS.
Mapping/readiness states are distinct from ADR-008's business-change classification
NEW/UNCHANGED/CHANGED/INVALID/CONFLICT. Ví dụ này không phải acceptance result;
runtime preview/mapping behavior thuộc các tài liệu canonical được dẫn ở đầu file.
