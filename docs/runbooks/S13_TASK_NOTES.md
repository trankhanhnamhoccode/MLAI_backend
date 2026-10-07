# HISTORICAL INFORMATION: S1.3 task baseline before S1.3.1

# S1.3 contract and work plan

Pre-edit CURRENT FACT: clean working tree, head 0003_catalog_recipe, seven business
tables, 93 passing tests recorded. Preserve S1.1/S1.2 models/migrations and API.
Authority: ADR-002/007 and newly authorized ADR-008/009; no provider/FE/ML behavior.
Freeze before implementation: exactly six new tables, no public endpoints, repository,
service, import, FEFO or S1.4. Tests use isolated shelfcash_test and fresh sessions.
Rollback scope: downgrade 0004 drops only six new tables/rows, retaining S1.1/S1.2.
Revision 0004_supplier_ops_constraints fits Alembic's 32-character version column.

ACCEPTED storage choices: UUID/defaults/UTC timestamp/Decimal conventions unchanged.
Supplier names nonunique; required nonblank names. SupplierTerm has positive integer
version, inclusive dates, optional unbounded end and active true. Pair/version unique
across all versions; overlap exclusion applies only to active rows. Pack quantity
finite >0, integer minimum packs >=1, finite cost >=0 in Store currency, integer lead
>=0 and optional shelf-life >=0. Retain required unit as base-unit FK witness to
prevent historical pack quantities being reinterpreted by later base-unit edits.

Sales has only required canonical store/product/date/finite quantity >=0 and timestamps;
no revenue/promotion without current use case. Source is not identity. No correction
flow. InventoryLot has optional supplier/lot_code/expiry/unit_cost, received date,
finite balance >=0, exact unit; unit_cost is store-currency cost per base unit.
No uniqueness invented for lot_code. No expiry_tracking trigger, automatic balance
updates or append-only SQL enforcement. Movement references are optional paired
opaque type/text ID (no ImportJob FK); note optional. Signs/types per ADR-009.

BusinessConstraint: only STORE/BUDGET_LIMIT and INGREDIENT/MIN_SAFETY_STOCK, required
finite numeric >=0, exact required unit, positive integer version, inclusive dates,
active true. No arbitrary text/JSON value. STORE scope_id NULL; INGREDIENT required
same-store/base-unit FK. Budget unit has uppercase currency shape; matching Store.currency
is a future application validation (no conditional FK/trigger framework). No MAX_STORAGE.
NULLS NOT DISTINCT version uniqueness handles STORE keys; GiST exclusion uses
coalesce(scope_id,store_id), scope_type and constraint_type, filtered to active rows.

Test first -> explicit typed models/migration -> targeted PostgreSQL constraints and
round trips -> preserve regression harness -> docs/manual verification -> full tests,
reset/migration/downgrade, Docker readiness, actual schema, import/OpenAPI/live health,
pip check, diff/status/whitespace. Update completion only after evidence passes.

## Verification — CURRENT FACT

Initial schema expectation failed at old 0003 before implementation. Final targeted:
80 passed; canonical PowerShell full runner: 173 passed, one existing upstream warning,
no skips. Fresh migrations, 0004->0003->head and prior scaffold/base downgrade/re-upgrade
pass on shelfcash_test. Metadata comparison passes, exclusion separately inspected
and exercised through SQL/activation tests. Development reset/upgrade/current/seed/status
and actual S13_VERIFICATION read-only inspection pass at new head with thirteen empty
business tables, one revision row. Compose config/up --wait/ps: PostgreSQL 17.11 healthy.
Import/model/domain with DB connection forbidden, exact generated/live OpenAPI baseline,
live health and pip check pass. Verification server stopped; no commit. Prior models/
migrations, API/domain/repository code and dependencies unchanged. Diff/status/whitespace
reviewed; no S1.4/import/order schema. POSIX wrappers unchanged, previous syntax checks
only; no runtime verification claimed. Policy/schema-only limits documented explicitly.
