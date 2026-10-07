# ADR-009 — Inventory Mutation and Audit Policy

## Status

ACCEPTED — authorized by S1.3 on 2026-10-05.

## Context

Expiry-aware planning requires separate received lots. A single ingredient total
cannot support FEFO or explain changes to balances. Current state must be fast to
inspect while retaining the reason for quantity changes.

## Decision

- Inventory is lot-level. InventoryLot represents stock actually received, with
  ingredient/base unit, received date, optional expiry/source and current balance.
  Incoming/unreceived stock is not InventoryLot; inbound/order persistence is future work.
- inventory_lots.on_hand_quantity is the current materialized, nonnegative lot
  balance. inventory_movements is the history explaining quantity changes.
  This is current state + audit history, not Event Sourcing or a generic event framework.
- Every application quantity change, including initial receipt, requires a reason
  and movement. Direct unexplained overwrite is not normal application behavior.
  Future application service must insert the movement and update balance in the
  same transaction, protecting against concurrent/lost updates and negative balance.
- Allowed movement types: RECEIPT, USAGE, WASTE, EXPIRED, COUNT_CORRECTION,
  MANUAL_ADJUSTMENT. Delta is finite and nonzero: RECEIPT positive; USAGE/WASTE/EXPIRED
  negative; COUNT_CORRECTION/MANUAL_ADJUSTMENT signed either way with an explicit reason.
  Unit is the lot's Ingredient.base_unit. Future writes preserve actor/source/reason
  trace and append correcting movements rather than editing/deleting accepted history.
- Expired lots are retained for audit, but usable quantity for future demand is zero.
  Expiration/FEFO computation, including expiry-day business cutoff, is not implemented
  by this schema. No scheduled expiration or automatic write-down is introduced.
- Ingredient.expiry_tracking indicates a future receipt validation requirement:
  tracked ingredients must have expiry_date. S1.3 stores/checks dates but does not
  enforce this cross-table conditional rule via triggers. Future receipt/import
  boundaries must validate it before accepting lots.

## Consequences and current enforcement

S1.3 enforces FK store/lot/ingredient/unit integrity, allowed movement types, signs,
finite values, nonnegative balance and expiry >= received date. It does not enforce
balance = sum(movements), mandatory receipt movement, append-only SQL access or
movement/balance atomic application behavior. No mutation service, trigger, repository
or API exists. Direct privileged SQL can bypass application audit policy; schema
tests/fixtures must not be presented as a production stock-mutation workflow.

## Rejected/deferred alternatives

REJECTED: ingredient-total-only stock, normal unexplained balance overwrite,
deleting expired lots, treating unreceived orders as on-hand stock, Event Sourcing.
DEFERRED: transaction/locking service, actor/provenance enforcement, correction
permissions, ledger immutability enforcement and inbound/order design.

## Revisit conditions and affected areas

Future receipt/use/correction features must implement and test atomic audited
mutations. Any change to these semantics requires explicit architectural review.
Affects Inventory, import/correction, future FEFO/procurement, audit, tests/demo and
authorization; no new runtime workflow is authorized by this ADR.
