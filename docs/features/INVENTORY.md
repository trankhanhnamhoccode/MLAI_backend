# Inventory lot state and movement history — S1.3

## Status and purpose

CURRENT FACT: InventoryLot/InventoryMovement schema exists; mutation service, FEFO,
expiry processing, inventory API and repositories do not. ADR-009 is ACCEPTED policy;
its application behavior is not implemented by merely storing these two tables.

## Invariants and persistence

inventory_lots = current lot state; on_hand_quantity is a finite nonnegative
materialized balance. Ingredient/unit and optional supplier must match the Store.
Only actually received stock belongs here; incoming stock != InventoryLot.
Optional expiry >=receipt date when both dates are known. Ingredient.expiry_tracking=true will require expiry
at a future receipt boundary; schema permits NULL and no cross-table trigger exists.
Optional unit_cost is nonnegative finite Store-currency cost per Ingredient.base_unit.
lot_code optional/nonunique, not an accepted universal import identity.

inventory_movements = change history. Composite FK matches lot/store/ingredient.
Allowed types RECEIPT, USAGE, WASTE, EXPIRED, COUNT_CORRECTION, MANUAL_ADJUSTMENT.
Finite nonzero delta; receipt positive, usage/waste/expired negative, count/manual
either sign. Required occurred_at TIMESTAMPTZ; optional paired opaque reference
type/ID and note. Lot deletion is restricted while movements reference it.

Expired lot = retained for audit but usable for future demand is zero by policy.
No expiry-day cutoff or usable-stock/FEFO computation is implemented.
Direct unexplained overwrite = not allowed application behavior. Future service
must create movement + update balance in one protected transaction. Schema has no
automatic balance trigger, sum invariant, mandatory receipt movement or append-only
SQL enforcement. Privileged direct writes remain possible; do not call them an
implemented audit-safe inventory workflow. Reason/actor/provenance validation awaits
the mutation/import slice. This is not Event Sourcing.

## Tests and deterministic fixtures

S1.3.1 / ADR-010: received_date may be unknown (NULL, no default), classified as
OPTIONAL_WARNING. Actually received current stock remains meaningful; future FEFO
readiness depends on expiry, while inventory-age analysis is unavailable. Snapshot
date != received date. Missing expiry remains unknown; automatic derivation requires
known receipt, known accepted shelf life and an explicit accepted domain rule and is
not implemented. Future warnings contain code/severity/field/entity/impact; no warning
API or readiness computation exists now. Canonical ID supplies lot identity even when
source lot_code is optional; future import identity resolution is not implemented.

test_data_semantics_correction.py persists unknown receipt through ORM NULL and raw
SQL omitted/NULL values, commits/closes/reloads in a fresh session, checking known
expiry and quantity remain exact. No snapshot date is silently stored. New 0005
preserves known receipt data on downgrade/re-upgrade and refuses downgrade with
unknown dates instead of backfilling fabricated facts. Resolve dates from confirmed
source evidence before downgrade, or explicitly reset development data; failed
transactional downgrade leaves head/schema/data unchanged.

S1.3 tests persist/read a Milk ml lot received 2026-10-01, expiry 2026-10-07, balance
50, unit cost 30; commit/close/new-session reload. Test negative/invalid dates/unit/
Store/supplier, unknown nullable metadata, zero balance/cost and same-day expiry.
RECEIPT +50, USAGE -20 and each allowed type/sign persist; invalid types/zero/NaN/
wrong signs or lot/ingredient/Store fail. New sessions confirm movement insertion
does not auto-update balance. Expired Jan 2026 lot remains stored. Parent base-unit
changes and deleting a referenced lot fail. All fixtures own shelfcash_test.

## Manual verification and DB inspection

Use [S13_VERIFICATION](../runbooks/S13_VERIFICATION.md), which executes:

```sql
SELECT id, store_id, ingredient_id, received_date, expiry_date,
       on_hand_quantity, unit FROM inventory_lots ORDER BY id;
SELECT lot_id, store_id, ingredient_id, movement_type, quantity_delta,
       occurred_at, reference_type, reference_id FROM inventory_movements
ORDER BY lot_id, occurred_at, id;
```

After reset both tables have zero rows; head 0005_data_semantics_correction. Tests
independently verify actual fixture records before their isolated cleanup. Schema
inspection shows numeric/date/type/sign CHECKs and exact-unit/lot composite FKs.
No GUI/host psql needed; no inventory HTTP operation exists.

## Failure/reset/retry and limitations

Invalid writes fail in PostgreSQL; roll back before retry. reset_db is guarded
destructive development reset; downgrade 0004 drops six new tables/history. No
automatic deletion of expired lots. No inbound/order, import, reconciliation,
actor security, locking/mutation service, FEFO or public API. Future surface PROPOSAL.
