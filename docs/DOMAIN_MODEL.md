# Domain model and business meaning

## ACCEPTED DECISION / CURRENT FACT — A2 recorded support history

CalendarEvent is a Store-scoped declared inclusive event, distinct from observed
Product/day promotion. UsageHistory records actual Ingredient consumption; it is
not theoretical BOM, waste/loss or a stock transaction. PurchaseHistory records
historical quantity/price basis with separate order, receipt and report dates; it
is not received stock, committed inbound or current supplier terms. Exact reviewed
physical conversion applies to quantity and price denominator without rounding.
Stable source/report/record identity has immutable domain grain and append-only
confirmed correction revisions; absent records remain. History-only readers are
retained Import preview/completion and H01/H02 discovery, not forecast features.
See [Import](IMPORT_MAPPING_API_CONTRACT_VI.md) and
[Authorization](AUTHORIZATION_CONTRACT_VI.md) for accepted workflow/current rights.

## ACCEPTED DECISION ? identity, units and time

A User may belong to several Stores; Owner/Staff authority is scoped to current
active membership and granular grants. Operator support is an audited identity,
not another Store role. Stored membership alone never authorizes data exposure.
[Authorization](AUTHORIZATION_CONTRACT_VI.md) owns permissions/consent/approval.

Products/Ingredients/Suppliers belong to a Store. Names are not unique; nullable
SKUs are case-sensitive Store-scoped keys. Product.selling_unit is the sales/
forecast/recipe output unit; Ingredient.base_unit must match RecipeLine,
InventoryLot and SupplierTerm units exactly. There is no canonical unit conversion
engine. Import can apply explicitly declared Owner-reviewed conversion rules with
provenance; it cannot reinterpret existing canonical facts.

Business DATEs use Store timezone; event instants are aware UTC. Unknown received
or observed dates stay unknown, not upload date. Money inherits Store.currency;
no currency conversion or implicit rounding. Unknown, zero, empty and forbidden
are different states (ADR-010). Exact public decimal/rational types are defined
by [API](API_CONTRACT.md) and source DTOs.

## CURRENT FACT ? operational truth

Recipes have whole-yield quantities, process loss, dated lines and inclusive
nonoverlapping assigned applicability. BOM uses theoretical ingredient demand /
(1-loss); missing/empty recipes block or exclude according to captured scope.
Future-only recipe calendar changes have explicit preview/CAS/commit/audit, never
implicit period closure/reopening or historical content editing.

SalesDaily stores canonical Store/Product/day totals. Import source-contribution
revisions distinguish duplicate, replacement and confirmed independent-source
merge; changing file hash is not permission to add quantities. Approved mapping
is distinct from preview/commit confirmation. Canonical commit is atomic for all
requested groups; missing rights/blockers never silently drop rows.

CURRENT FACT A1 adds nullable observed product stockout, separately from inventory or
projected shortage. Contribution revisions retain observation evidence; quantity-only
preserves the contribution observation. Captured derived demand never overwrites
SalesDaily.quantity. [ADR-A1](adr/ADR-A1-observed-stockout-demand-policy.md) owns
schema-2 mechanics and legacy replay. Migration and targeted persistence/consumer
acceptance are verified on the owned Import test DB; real-data quality is not evaluated.

InventoryLot holds current physical balance; InventoryMovement holds justified
history. Receipt/count correction update movement+balance atomically under locks;
negative balance rejects. OPENING_STOCK observation is not an incoming purchase.
Count affects identified lots, not unexplained absolute overwrites or invented
receipts. Expired/unknown-date lots remain physical facts; eligibility is separate.
Inventory completeness requires explicit coverage/dependency evidence, not one receipt.

Supplier terms retain dated versions, exact pack size/unit/cost, whole-pack MOQ,
lead/shelf-life and scoped identity. Payable fees/capacity/supplier limits and
budget need explicit captured evidence; unknown is not zero/unlimited/unconfigured.

## CURRENT FACT / ACCEPTED DECISION ? forecast and decisions

Forecast captures explicit Products and sparse observed sales using Store-local D
and D+1..D+7 (ADR-012/014/015). Missing observations are not zero. P25/P50/P75 are
finite ordered nonnegative demand quantiles in each Product selling unit. Baseline
and trained LightGBM mechanics/evaluation/artifact replay exist; real-data quality
is NOT EVALUATED. Actual selected model and fallback reason remain retained.

LEAN/BALANCED/PROTECTED construct LOW/BASE/HIGH demand paths, not quantile aliases
or stochastic scenarios. Plain exact progressive serving/FEFO respects recipe/
expiry/arrival dates and shared physical stock. Native MILP generates candidate
pack baskets; exact domain simulation/validation owns hard validity.

Procurement/2 constructs100% per Product and applies explicit effective customer
requirements. Within customer-valid domain, construction pass minimizes purchase
plus declared fees; fallback uses minimum then mean Product service, outlay and
canonical ties. Mixed selling units are never summed as a service objective.
Winner requires exact validity, no related blocker and customer pass; no eligible
candidate gives null. Search incomplete/unproven, technical failure and exact
infeasibility proof are distinct (ADR-019/020). No universal BASE95 engine default.

Planning configuration/default/saved/budget/serving versions are frozen at acceptance;
operational values are captured before compute. PlanningRun is separate from the
original S1 DecisionRun schema. Retained result uses captured context, not current
stock/recipe/prices. Reads/export of an option do not persist customer selection.
Required nullable result_digest applies only to terminal captured scope without a
retained result; engine fields remain unavailable/null, not zero.

## ACCEPTED DECISION ? retention and limits

Completed Runs/snapshots/packages retain actual values and versions; rerun creates
new identity. Fingerprints are nonunique diagnostics, not deduplication/security.
Package version starts1. Model binaries/text are immutable local artifacts; metadata
is in PostgreSQL. Operational audit, source provenance, Runs/PDF and models are not
disposable development evidence (ADR-005/008/009/011/015/022).

What-if remains hypothetical/nonpersistent by default. No automatic purchasing,
customer selected-option write, one-time approval or AI business decision is enabled.
DB local constraints and application invariants have different coverage; privileged
SQL and tracked ORM can bypass some guards. Historical /1 remains readable and is
not reinterpreted as procurement/2. See [schema](DATABASE_SCHEMA.md),
[Planning](PROCUREMENT_API_CONTRACT_VI.md), [Import](IMPORT_MAPPING_API_CONTRACT_VI.md)
and [accepted ADR index](DECISIONS.md).
