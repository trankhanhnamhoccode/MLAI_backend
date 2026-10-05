# Canonical daily sales persistence — S1.3

## Status and purpose

CURRENT FACT: SalesDaily persistence exists; no import, correction service, revenue/
promotion engine, forecast, API or repository. ADR-008 freezes correction policy.

## Invariants and tables

sales_daily reads/references Store/Product and stores one finite nonnegative quantity
in Product.selling_unit for (store_id,product_id,sales_date). Composite FK enforces
same-store Product. Unique canonical key excludes source/filename. No optional
business fields were added without a current use case. Storage rows are mutable;
business-day timezone conversion and correction audit are not implemented.

Future import: same identity/values UNCHANGED -> no write; changed 100 ->105 is
CHANGED -> explicit authorized domain correction, never sum 205. Duplicate DB inserts
are rejected; no generic upsert/replace-all behavior exists. Source trace must be
added at an authorized import boundary, not fabricated ImportJob fields now.

## Tests and fixtures

S1.3 targeted tests commit/close/reload quantity 10.125 on 2026-10-01, reject duplicate
changed row and independently confirm old value remains, reject negative/NaN and
missing/cross-store Product. Zero sales and same date in two valid store/product
contexts are allowed. A Product belongs to one Store, so the same product_id cannot
be borrowed by another Store. Tests own only shelfcash_test.

## Manual verification and DB inspection

Follow [S13_VERIFICATION](../runbooks/S13_VERIFICATION.md). Expected head
0005_data_semantics_correction; sales_daily empty after reset. Shared command executes:

```sql
SELECT store_id, product_id, sales_date, quantity FROM sales_daily
ORDER BY store_id, product_id, sales_date;
```

Expected no development rows after reset/tests; unique store/product/date, NUMERIC
quantity CHECK and composite FK exist. Targeted tests prove persisted fixture values
using new sessions. No upload/API path exists to manually demonstrate import.

## Failure/reset/limits and future API

Invalid/duplicate data fails PostgreSQL integrity checks; roll back and resolve
the domain conflict, not unconditional overwrite. reset_db reapplies head; seed
writes no rows. See DATABASE_RESET for guards. No correction/provenance engine,
full snapshot import or public sales API; future surface remains PROPOSAL.

ACCEPTED DECISION (ADR-010): sales date/product/quantity are REQUIRED. Missing
quantity is not zero; canonical promotion requires established facts. Future mapping
retains missing/ambiguous source values outside canonical sales; no import exists.
