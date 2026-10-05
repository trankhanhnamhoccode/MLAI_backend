# Database schema — implemented cluster and Schema v1 proposals

**CURRENT FACT:** S1.1 implements `users`, `stores`, `store_memberships`; S1.2 adds
`products`, `ingredients`, `recipes`, `recipe_lines`. S1.3 adds `suppliers`,
`supplier_terms`, `sales_daily`, `inventory_lots`, `inventory_movements`,
`business_constraints` — thirteen business tables total.
**ACCEPTED DECISION:** the storage semantics below are frozen for these authorized
clusters. ADR-008/009 freeze import correction/inventory audit policy, not runtime
import/mutation services. All other Schema v1 entities remain PROPOSAL; each requires its own accepted
slice before models/migrations are implemented. No hidden aggregate is implied.

**ACCEPTED DECISION (ADR-007):** PostgreSQL is the Competition database, with
SQLAlchemy 2.x, psycopg and synchronous Session. Local infrastructure is Docker
Compose PostgreSQL with a named volume. Reset between versions is
acceptable. Alembic makes schema state/evolution explicit; long-lived backwards-compatible
migration support is not a current requirement. The initial empty revision creates
only `public.alembic_version`; the next migration `0002_identity_store` creates the
three identity/store tables. `0003_catalog_recipe` adds four catalog/recipe tables;
`0004_supplier_ops_constraints` adds six S1.3 tables; current head
`0005_data_semantics_correction` makes received_date nullable and clarifies its date check. No other business
model is implemented. This shorter revision fits Alembic's 32-character version field.
Tests own separate `shelfcash_test`; development
uses `shelfcash`. Reset recreates only the guarded target's `public` schema.

## IMPLEMENTED — S1.1 storage contract

Models: `app/models/user.py`, `store.py`, `store_membership.py`. Migration:
`alembic/versions/0002_identity_store.py`, parent `0001_scaffold`. All columns below
are NOT NULL. Tables represent mutable current state, not audit snapshots. No
repository, authentication/authorization enforcement or business API exists yet.

### Shared columns

| Column | PostgreSQL type | Default / semantics |
| --- | --- | --- |
| id | UUID PK | `gen_random_uuid()` database-generated v4; explicit UUID allowed |
| active | BOOLEAN | `true`; stored lifecycle flag, no access enforcement |
| created_at | TIMESTAMPTZ | `now()` at insertion; no automatic later change |
| updated_at | TIMESTAMPTZ | `now()` on insert; SQLAlchemy UPDATE uses `now()` |

Database engine sessions use UTC; outputs are aware instants. PostgreSQL TIMESTAMPTZ
stores an instant rather than a store-local naive datetime. Raw SQL updates must
explicitly set `updated_at`; no timestamp trigger is installed. `now()` is the
transaction timestamp. No timestamp/user-lifecycle service is implemented.

### users

Purpose: stored human identity only. Password processing/login semantics deferred.

| Column | Type | Storage rule |
| --- | --- | --- |
| email | VARCHAR(320) | Unique canonical email; nonempty, `email = lower(email)`, no POSIX whitespace |
| password_hash | TEXT | Opaque nonblank hash value; algorithm/verification not implemented |
| display_name | VARCHAR(200) | Must contain a non-whitespace character |

Constraints: PK `id`; `uq_users_email`; `ck_users_email_canonical`,
`ck_users_password_hash_nonblank`, `ck_users_display_name_nonblank`.
No FKs. The unique email constraint supplies its lookup index; no redundant email
index is added. Canonicalization is a storage requirement: callers supply lowercase
values without whitespace. PostgreSQL rejects uppercase/whitespace input, never
silently rewrites it. Its `lower()`/POSIX whitespace definitions govern this check;
RFC validation, Unicode case-folding, mailbox-provider equivalence, verification
and a normalization/login application workflow are NOT IMPLEMENTED.

### stores

Purpose: mutable F&B store/business context and future tenancy boundary.

| Column | Type | Storage rule / default |
| --- | --- | --- |
| name | VARCHAR(200) | Nonblank, explicitly NOT unique |
| timezone | VARCHAR(64) | Nonblank; default `Asia/Ho_Chi_Minh` frozen in S1.1 |
| currency | VARCHAR(3) | Uppercase three-letter shape; default `VND` frozen in S1.1 |

Constraints: PK `id`; `ck_stores_name_nonblank`, `ck_stores_timezone_nonblank`,
`ck_stores_currency_shape`. No FKs, unique name rule or additional indexes.
Timezone/currency defaults were previously unresolved and are accepted only for
this storage cluster. IANA timezone/ISO currency catalog validation, financial
precision/conversion and business-date cutoff remain future contracts.

### store_memberships

Purpose: persisted User ↔ Store relationship, not permission enforcement.

| Column | Type | Storage rule |
| --- | --- | --- |
| store_id | UUID FK → stores.id | Existing store; `ON DELETE RESTRICT` |
| user_id | UUID FK → users.id | Existing user; `ON DELETE RESTRICT` |
| role | VARCHAR(5) | Required `OWNER` or `STAFF`; no default |
| delegated_permissions | JSONB | Default `[]`; must equal `[]` in S1.1 |

Constraints: PK `id`; FKs `fk_store_memberships_store` and
`fk_store_memberships_user`; `uq_store_memberships_store_user` on (store_id,user_id);
`ck_store_memberships_role` and `ck_store_memberships_permissions_reserved`.
Constrained string avoids a separate enum lifecycle while preserving role integrity.
The unique pair's index covers store-to-member lookup, so no redundant store_id index
is added. Explicit `ix_store_memberships_user_id` supports reverse user-to-store
membership lookup. Parent deletion is rejected while memberships exist; no implicit
cascade or real-state deletion workflow. A user can belong to several stores and a
store can have several users, with at most one row per pair. No sole-owner/minimum-owner
or active-parent rule is invented.

`delegated_permissions` is an empty reserved list. Nonempty lists, objects and JSON
null are rejected; no arbitrary permission vocabulary is accepted. Opening that
vocabulary needs a later explicit contract/migration. Membership presence/role/active
does NOT grant runtime authorization in S1.1.

Verification: [STORE_IDENTITY](features/STORE_IDENTITY.md), targeted real PostgreSQL
tests `tests/integration/test_identity_store_schema.py`, and
[FULL_TEST_FLOW](runbooks/FULL_TEST_FLOW.md). Reset leaves these three tables empty
and the S1.2/S1.3 tables empty, with one `alembic_version` row `0005_data_semantics_correction`;
seed writes no entities.

Implementation references: [PostgreSQL date/time types](https://www.postgresql.org/docs/17/datatype-datetime.html)
and [SQLAlchemy defaults/onupdate](https://docs.sqlalchemy.org/en/20/core/defaults.html).

## IMPLEMENTED — S1.2 Catalog + Recipe storage contract

Models: `app/models/product.py`, `ingredient.py`, `recipe.py`, `recipe_line.py`.
Migration `0003_catalog_recipe`, parent `0002_identity_store`. All columns NOT NULL
except `products.sku`, `products.price`, `ingredients.sku`, `recipes.effective_to`.
All four have UUID PK `id` default `gen_random_uuid()` and `created_at TIMESTAMPTZ`
default `now()`. Products/ingredients/recipes also have `updated_at TIMESTAMPTZ`
with the same insert/ORM-update semantics as S1.1. Raw SQL updates set it explicitly.
These are editable versioned definitions/current catalog, not immutable execution
snapshots. No historical snapshot immutability trigger or computation is implemented.

### products

| Column | Type | Rule/default |
| --- | --- | --- |
| store_id | UUID | FK stores.id, RESTRICT deletion |
| sku | VARCHAR(64), nullable | Case-sensitive, nonblank if present; unique within store |
| name | VARCHAR(200) | Nonblank; not unique |
| selling_unit | VARCHAR(32) | Nonblank exact unit label |
| price | NUMERIC, nullable | Finite >= 0; store currency; NULL means unspecified |
| active | BOOLEAN | Default true; stored flag only |

PK id; `fk_products_store`; `uq_products_store_sku` (store_id,sku).
PostgreSQL NULL-distinct uniqueness permits multiple missing SKUs in one store.
No SKU normalization or global uniqueness. `uq_products_id_store` (id,store_id)
is the required target for recipe's same-store FK. Checks:
`ck_products_name_nonblank`, `ck_products_sku_nonblank`,
`ck_products_selling_unit_nonblank`, `ck_products_price` (rejects NaN/infinities).
The store/SKU index covers store catalog lookup; no redundant store_id index.

### ingredients

| Column | Type | Rule/default |
| --- | --- | --- |
| store_id | UUID | FK stores.id, RESTRICT deletion |
| sku | VARCHAR(64), nullable | Same case-sensitive store-scoped/null rules as Product |
| name | VARCHAR(200) | Nonblank, not unique; canonical stored label |
| base_unit | VARCHAR(32) | Nonblank, exact case-sensitive unit, no conversion |
| expiry_tracking | BOOLEAN | Default false; flag only, no inventory behavior |
| active | BOOLEAN | Default true |

PK id; `fk_ingredients_store`; `uq_ingredients_store_sku` (store_id,sku).
`uq_ingredients_id_store_unit` (id,store_id,base_unit) supports the line integrity FK.
Checks `ck_ingredients_name_nonblank`, `ck_ingredients_sku_nonblank`,
`ck_ingredients_base_unit_nonblank`. Store/SKU uniqueness covers store lookup.
Unit vocabulary is not a conversion/validation catalog (e.g. ml and L differ).

### recipes

| Column | Type | Rule/default |
| --- | --- | --- |
| store_id | UUID | FK stores.id and same-store product FK |
| product_id | UUID | Composite FK (product_id,store_id) -> products(id,store_id) |
| version | INTEGER | Required > 0, unique per product |
| effective_from | DATE | Required inclusive start |
| effective_to | DATE, nullable | Inclusive end >= start; NULL means unbounded future |
| yield_quantity | NUMERIC | Finite > 0; total product output in Product.selling_unit |
| process_loss_rate | NUMERIC | Default 0; 0 <= rate < 1, recipe-level loss |

PK id; FKs `fk_recipes_store`, `fk_recipes_product_store`, both ON DELETE RESTRICT.
Unique `uq_recipes_product_version` (product_id,version), `uq_recipes_id_store`
(id,store_id) supports lines. Checks `ck_recipes_version`, `ck_recipes_period`,
`ck_recipes_yield`, `ck_recipes_loss`.

`ex_recipes_product_period` uses GiST exclusion:
`product_id WITH =, daterange(effective_from,effective_to,'[]') WITH &&`.
Migration enables standard PostgreSQL `btree_gist` for UUID equality. The database
rejects overlapping inserts/updates, including concurrent transactions. Shared end/start
day overlaps; the next version can begin the following day. Same-day recipes are valid.
An unbounded version blocks all later overlapping versions. Different products can
share periods. At day D resolve using `effective_from <= D AND (effective_to IS NULL
OR D <= effective_to)` to obtain 0/1 row. Product.active does not bypass exclusion.
No resolver repository is implemented. Unique product/version supports product queries;
exclusion supplies its GiST index; no speculative date-only index.

NUMERIC maps to Decimal, with no fixed scale or implicit business rounding; price,
yield and line quantity reject NaN/infinities. PostgreSQL NUMERIC implementation limits
still apply. Loss is at Recipe level, not per Ingredient. Future BOM formula is
`actual_requirement = theoretical_requirement / (1 - process_loss_rate)`;
800 ml over yield 10 cups means theoretical 80 ml/cup. With loss 0.05 this becomes
80/0.95 (~84.21 ml). **BOM computation is NOT IMPLEMENTED.**

### recipe_lines

| Column | Type | Rule |
| --- | --- | --- |
| store_id | UUID | Required integrity witness shared by both composite FKs |
| recipe_id | UUID | FK (recipe_id,store_id) -> recipes(id,store_id) |
| ingredient_id | UUID | FK (ingredient_id,store_id,unit) -> ingredients(id,store_id,base_unit) |
| quantity | NUMERIC | Finite > 0 for the entire recipe yield |
| unit | VARCHAR(32) | Must exactly equal Ingredient.base_unit |

PK id; `uq_recipe_lines_recipe_ingredient` (recipe_id,ingredient_id),
`ck_recipe_lines_quantity`. FKs `fk_recipe_lines_recipe_store` and
`fk_recipe_lines_ingredient_store_unit`, ON DELETE RESTRICT / default NO ACTION
on update. store_id is intentional redundant integrity data; unit is retained as
requested. Both enable declarative database checks without services or triggers.
Ingredient base-unit changes and parent-store changes cannot invalidate referenced
lines/recipes. Parent deletion is blocked while referenced. No implicit cascading
business deletion. Recipe/ingredient duplicates must be combined by a future caller.
Unique recipe/ingredient covers recipe lookup. Explicit `ix_recipe_lines_ingredient_id`
supports reverse ingredient usage and referential checks; no redundant recipe_id index.

Verification: [CATALOG_RECIPE](features/CATALOG_RECIPE.md), actual PostgreSQL tests
`tests/integration/test_catalog_recipe_schema.py`. Downgrade to 0002 drops only
these four tables/rows; btree_gist is retained because it may be shared/preexisting.
Normal reset recreates public (including its extension objects), then upgrades head.
The Compose role can install the extension. No new public API or repository exists.
References: [PostgreSQL btree_gist](https://www.postgresql.org/docs/17/btree-gist.html),
[range exclusion](https://www.postgresql.org/docs/17/rangetypes.html).

## IMPLEMENTED — S1.3 Supplier / Operational / Constraints storage contract

Migration `alembic/versions/0004_supplier_operational_constraints.py`, revision
`0004_supplier_ops_constraints`, parent `0003_catalog_recipe`. Typed models are
`app/models/supplier.py`, `supplier_term.py`, `sales_daily.py`, `inventory_lot.py`,
`inventory_movement.py`, `business_constraint.py`. No repository/service/API exists.
Every table has UUID PK `id`, database `gen_random_uuid()` default, and `created_at
TIMESTAMPTZ DEFAULT now()`. All except movements have `updated_at TIMESTAMPTZ` with
the S1.1 insert/ORM-update convention; raw SQL updates must set it explicitly.
All columns required unless marked nullable. NUMERIC maps to Decimal, without fixed
scale/business rounding; NaN/infinities are rejected. Store currency governs costs;
currency conversion/change and money rounding remain future application contracts.
All FKs below use ON DELETE RESTRICT, default NO ACTION on updates. No cascade,
timestamp, inventory-balance, expiry or ledger immutability trigger is introduced.

### suppliers

Purpose: store-owned supplier identity, not global supplier directory.

| Column | Type | Rule/default |
| --- | --- | --- |
| store_id | UUID | FK stores.id |
| name | VARCHAR(200) | Nonblank; NOT unique within/across stores |
| active | BOOLEAN | true |

PK id; `fk_suppliers_store`; `uq_suppliers_id_store` (id,store_id) is the required
composite FK target. `ck_suppliers_name_nonblank`; explicit `ix_suppliers_store_id`
supports listing suppliers in a store (the id-leading unique index cannot do that).
Current mutable identity state; no source codes, contacts or supplier CRUD invented.

### supplier_terms

Purpose: versioned pack purchasing inputs for Supplier ↔ Ingredient (many-to-many).
Changes should create a new version, adjusting periods explicitly; SQL rows remain
editable and no historical immutability service is implemented. Snapshot consumers
must preserve used values under ADR-005 when implemented.

| Column | Type | Rule/default |
| --- | --- | --- |
| store_id | UUID | Same-store integrity witness for supplier/ingredient |
| supplier_id | UUID | FK (supplier_id,store_id) -> suppliers(id,store_id) |
| ingredient_id | UUID | FK (ingredient_id,store_id,unit) -> ingredients(id,store_id,base_unit) |
| unit | VARCHAR(32) | Exact base-unit witness, prevents reinterpretation after unit edits |
| version | INTEGER | >0, required |
| effective_from | DATE | Inclusive start |
| effective_to | DATE nullable | Inclusive end >= start, NULL unbounded |
| pack_size_base_quantity | NUMERIC | Finite >0, Ingredient.base_unit per pack |
| minimum_order_packs | INTEGER | >=1, minimum whole packs when an order is placed |
| pack_cost | NUMERIC | Finite >=0, Store currency per pack |
| lead_time_days | INTEGER | >=0 |
| shelf_life_days | INTEGER nullable | >=0 when provided; unspecified when NULL |
| active | BOOLEAN | true; only active rows participate in overlap exclusion |

PK id; `fk_supplier_terms_supplier_store`, `fk_supplier_terms_ingredient_store_unit`.
`uq_supplier_terms_pair_version` (supplier_id,ingredient_id,version) across active
and inactive rows. Checks `ck_supplier_terms_version`, `ck_supplier_terms_period`,
`ck_supplier_terms_pack_size`, `ck_supplier_terms_minimum_packs`,
`ck_supplier_terms_pack_cost`, `ck_supplier_terms_lead_time`, `ck_supplier_terms_shelf_life`.
`ex_supplier_terms_pair_period`: GiST supplier_id =, ingredient_id =,
daterange(from,to,'[]') && WHERE active, reusing parent btree_gist. Concurrent SQL
inserts/updates/activation cannot produce two active terms for the pair on one day.
Inactive overlapping drafts are allowed; duplicate version is still rejected.
At D select active AND from<=D AND (to IS NULL OR D<=to); zero/one result.
Shared boundary day overlaps; next-day adjacency and single-day periods are valid.
Unique pair/version covers supplier-term lookup; explicit
`ix_supplier_terms_ingredient_id` supports finding suppliers for an ingredient.
No redundant effective-date or supplier index.

Example: Milk base_unit ml; 12 x 1L pack is normalized externally to 12000 ml,
minimum packs 2, pack_cost 360000 VND. Two packs cost 720000 VND. This specifies
inputs only, not an implemented procurement/unit-conversion calculation.

### sales_daily

Purpose: one canonical daily sales total, not additive source observations.

| Column | Type | Rule |
| --- | --- | --- |
| store_id | UUID | Same-store product witness |
| product_id | UUID | FK (product_id,store_id) -> products(id,store_id) |
| sales_date | DATE | Canonical business sales day; timezone cutoff conversion not implemented |
| quantity | NUMERIC | Finite >=0 in Product.selling_unit |

PK id; `fk_sales_daily_product_store`, `uq_sales_daily_store_product_date`
(store_id,product_id,sales_date), `ck_sales_daily_quantity`. Unique index supports
store/product/day lookup; no source/import/filename in identity. No unnecessary
revenue/promotion fields. A source quantity 100 changed to 105 is CHANGED under
ADR-008, not a second row or total 205. Correction workflow/audit remains future;
direct persisted state is mutable, not a Sales correction implementation.

### inventory_lots

Purpose: current balance for actually received lots (ADR-009), not inbound orders.

| Column | Type | Rule |
| --- | --- | --- |
| store_id | UUID | Same-store ingredient/supplier witness |
| ingredient_id | UUID | FK (ingredient_id,store_id,unit) -> ingredients(id,store_id,base_unit) |
| supplier_id | UUID nullable | FK (supplier_id,store_id) -> suppliers(id,store_id); unknown allowed |
| lot_code | VARCHAR(128) nullable | Nonblank when present; no invented uniqueness/import identity |
| received_date | DATE nullable, no default | Known actual receipt day, or NULL (OPTIONAL_WARNING); never snapshot/upload date |
| expiry_date | DATE nullable | >= received_date when both dates are known |
| on_hand_quantity | NUMERIC | Current materialized finite balance >=0 |
| unit | VARCHAR(32) | Exactly Ingredient.base_unit |
| unit_cost | NUMERIC nullable | Finite >=0 in store currency per one Ingredient.base_unit; unknown allowed |

PK id; `fk_inventory_lots_ingredient_store_unit`, `fk_inventory_lots_supplier_store`.
Default MATCH SIMPLE skips optional supplier FK when supplier_id is NULL; required
ingredient/store/unit FK still protects the store. `uq_inventory_lots_id_store_ingredient`
(id,store_id,ingredient_id) supports movements. Checks `ck_inventory_lots_on_hand`,
`ck_inventory_lots_expiry`, `ck_inventory_lots_unit_cost`, `ck_inventory_lots_code_nonblank`.
`ix_inventory_lots_store_ingredient_expiry` supports store/ingredient lot inspection
ordered by expiry; no FEFO algorithm is claimed. Ingredient.expiry_tracking=true
will require expiry_date at future receipt/application boundaries; this conditional
cross-table rule is NOT DB-enforced in S1.3. Tracked lots with NULL expiry can be
inserted directly; tests/documentation expose that limit. Expired lots are retained,
but future usable quantity is zero. Expiry-day cutoff/FEFO is not implemented.

### inventory_movements

Purpose: quantity change history explaining lot balance, not Event Sourcing.

| Column | Type | Rule |
| --- | --- | --- |
| store_id | UUID | Must match referenced lot |
| lot_id | UUID | Composite FK (lot_id,store_id,ingredient_id) -> inventory_lots(id,store_id,ingredient_id) |
| ingredient_id | UUID | Must equal lot ingredient; quantity uses its base unit |
| movement_type | VARCHAR(24) | RECEIPT, USAGE, WASTE, EXPIRED, COUNT_CORRECTION, MANUAL_ADJUSTMENT |
| quantity_delta | NUMERIC | Finite, nonzero; positive increase/negative decrease |
| occurred_at | TIMESTAMPTZ | Required aware event instant; distinct from created_at |
| reference_type | VARCHAR(64) nullable | Opaque nonblank trace hook, paired with reference_id |
| reference_id | TEXT nullable | Opaque nonblank source/reference identifier, not ImportJob FK |
| note | TEXT nullable | Optional explanation; future correction boundary validates required reasons |

PK id; `fk_inventory_movements_lot_store_ingredient` blocks cross-store/ingredient
movement and deleting referenced lots. Checks `ck_inventory_movements_type`,
`ck_inventory_movements_delta`, `ck_inventory_movements_sign`,
`ck_inventory_movements_reference_pair` (both NULL or both nonblank).
RECEIPT positive; USAGE/WASTE/EXPIRED negative; count/manual corrections either sign.
`ix_inventory_movements_lot_occurred` supports per-lot chronological audit inspection.
No balance-trigger or ledger-sum constraint: inserting movement does not update lot.
Future service must create movement + change balance atomically with concurrency
protection. Unexplained overwrite is forbidden application policy, but direct SQL
can still edit balances/movements. Mandatory initial receipt, append-only history,
actor/provenance enforcement and reconciliation are NOT IMPLEMENTED.

### business_constraints

Purpose: controlled, versioned numeric planning inputs. Budget belongs here, not
Store settings or a separate aggregate. No arbitrary JSON/text values or LLM types.

| Column | Type | Rule/default |
| --- | --- | --- |
| store_id | UUID | FK stores.id |
| scope_type | VARCHAR(10) | STORE or INGREDIENT only |
| scope_id | UUID nullable | STORE: NULL; INGREDIENT: required same-store Ingredient |
| constraint_type | VARCHAR(24) | STORE/BUDGET_LIMIT or INGREDIENT/MIN_SAFETY_STOCK only |
| numeric_value | NUMERIC | Finite >=0 |
| unit | VARCHAR(32) | Budget: uppercase currency shape; safety: exact Ingredient.base_unit |
| version | INTEGER | >0 |
| effective_from | DATE | Inclusive start |
| effective_to | DATE nullable | Inclusive end >=start, NULL unbounded |
| active | BOOLEAN | true |

PK id; `fk_business_constraints_store`; `fk_business_constraints_ingredient_scope_unit`
(scope_id,store_id,unit) -> ingredients(id,store_id,base_unit). For STORE NULL scope_id
skips this FK; required scope/type CHECK ensures this is intentional.
`uq_business_constraints_scope_version` on (store_id,scope_type,scope_id,constraint_type,
version), PostgreSQL NULLS NOT DISTINCT: even NULL STORE identities cannot duplicate
versions. Checks `ck_business_constraints_registry_scope`,
`ck_business_constraints_numeric_value`, `ck_business_constraints_version`,
`ck_business_constraints_period`. `ex_business_constraints_scope_period` uses GiST
store_id =, scope_type =, coalesce(scope_id,store_id) =, constraint_type =,
daterange(from,to,'[]') && WHERE active. No NULL hole for STORE overlap; scope_type
separates STORE from INGREDIENT even if UUIDs happen to coincide. Unique/GiST indexes
cover store/logical-scope/version/period lookup; no speculative extra index.
Inactive overlap allowed, activation validated; active resolution follows the same
inclusive predicate as SupplierTerm. Budget value is in unit currency; matching
Store.currency is a future application validation, NOT conditional DB enforcement.
No multi-currency computation, spent/reserved/rollover, MAX_STORAGE or other scopes.

Verification: [SUPPLIER](features/SUPPLIER.md), [OPERATIONAL_DATA](features/OPERATIONAL_DATA.md),
[INVENTORY](features/INVENTORY.md), [BUSINESS_CONSTRAINTS](features/BUSINESS_CONSTRAINTS.md),
`tests/integration/test_supplier_operational_constraints.py` and FULL_TEST_FLOW.
Normal reset leaves thirteen empty business tables plus one current revision row;
seed writes no rows. Downgrade 0004->0003 drops only six new tables/rows, keeping
all S1.1/S1.2 schema and btree_gist. No Import/Forecast/Decision/Order tables exist.
Reference: [PostgreSQL NULLS NOT DISTINCT and exclusion](https://www.postgresql.org/docs/17/ddl-constraints.html).

## Remaining Schema v1 — PROPOSAL / FUTURE

### Common conventions — PROPOSAL

Each entity has a primary `id`. Store-owned records use `store_id` with enforced
foreign keys and application authorization. Cross-store relationships must be
rejected by the backend; composite keys/FKs may enforce them when appropriate.
S1.1 UUID/timestamp/store defaults above are accepted for that cluster only;
remaining identifiers and currency/quantity precision are unresolved.
Do not rely on floating point for exact financial truth: choose an explicit
money representation/rounding contract in the first affected slice.
Business-date boundaries use an explicitly agreed store timezone/cutoff policy.
Indexes below are candidates for real queries, not a command to create unused indexes.

| Entity | Purpose and key fields | Relationships | Important constraints / indexes | Current state or historical snapshot |
| --- | --- | --- | --- | --- |
| ImportJob | Trace ingestion: id, store_id, source reference/digest, status, mapping_profile_id, created_at, validation summary | Store; optional MappingProfile; provenance for imported rows | Store/date index; validated status transitions; immutable source reference; file/row errors separate from accepted data | Historical import execution/status record |
| MappingProfile | Approved store mapping: id, store_id, profile version, canonical schema version, file fingerprint, field mapping, approval actor/time, status | Store, approving User/Membership; ImportJobs | Unique (store_id, profile key, version); mapping targets restricted to canonical fields; approved versions immutable | Versioned approved mapping snapshot, with explicit current active selection |
| ForecastRun | Forecast provenance: id, store_id, cutoff date/time, horizon, input snapshot/digest, model/baseline identifier and version, parameters, status, created_at | Store; ForecastPredictions; DecisionRuns consume this run | Cutoff/horizon contract; store/cutoff index; completed outputs immutable; input references/digest alone insufficient if source mutates—retain used input content/artifact | Historical execution/input/model snapshot |
| ForecastPrediction | Explicit demand quantiles: id, forecast_run_id, product_id, business_date, p25, p50, p75 | ForecastRun and same-store Product | Unique (forecast_run_id, product_id, business_date); 0 ≤ p25 ≤ p50 ≤ p75; future date strictly after cutoff; index run/date | Historical forecast output, explicit modeled quantile columns, never arbitrary JSON |
| DecisionRun | Main auditable decision aggregate: id, store_id, forecast_run_id, cutoff/horizon, created_at, actor reference, package_schema_version, decision_package JSON | Store; ForecastRun; other provenance by copied facts/versioned references in package | package_schema_version ≥ 1, initially 1; backend validates versioned Pydantic package; index store/created_at; completed decisions immutable; recommendation must match evaluated candidates | Self-contained historical snapshot; no reinterpretation using current state |

## DecisionRun package — ACCEPTED DECISION, structure remains PROPOSAL

`package_schema_version` exists from version 1. The package must retain inputs and
versions, ingredient demand, all three candidates, simulator metrics, deterministic
selected recommendation, warnings, risks and business evidence. Include exact inventory,
supplier terms and constraint values used, recipe/model versions, cutoff/horizon and
simulation/comparison algorithm versions needed to understand the result later.
Mutable source references alone do not satisfy this requirement. A stored snapshot
need not promise future software can replay every old algorithm, but its historical
meaning must remain understandable and stable.

A schema-versioned validated JSON snapshot is appropriate for complex nested output
in the MVP. Do not normalize every candidate, risk or evidence object into its own
table without a documented query/integrity requirement. Important forecast P25/P50/P75
values remain explicit columns in ForecastPrediction. No extra aggregate is proposed.

Hypothetical what-if results are non-persistent as real business state by default.
Any later history of simulations must be explicitly distinguished from real decisions
and separately authorized; this proposal does not introduce a WhatIf aggregate/table.

## Deferred choices — PROPOSAL

Freeze remaining deletion/retention workflows, unit/money conversion/rounding,
domain correction implementation under ADR-008/009, login handling,
delegated permission storage, forecast input artifact retention and exact package schema
in affected slices. Choose schema evolution for clarity and reproducibility, without
legacy compatibility scaffolding or an unrequested database engine.

## IMPLEMENTED -- S1.3.1 source-semantics correction

ADR-010 is ACCEPTED. Migration 0005 changes only inventory_lots.received_date
nullability and ck_inventory_lots_expiry to `received_date IS NULL OR expiry_date
IS NULL OR expiry_date >= received_date`. No date default or new table is added.
Unknown receipt remains NULL; stock is meaningful, expiry-based FEFO readiness
depends on known expiry, and inventory age cannot be computed. Downgrade refuses
NULL receipt rows rather than inventing dates; confirmed source resolution or explicit
development reset is needed. All remaining constraints/indexes are unchanged.

SupplierTerm price is UNCHANGED: pack_cost is Store-currency cost per complete pack,
not cost per base unit. Known 15 kg and 28,000 VND/kg normalize to 420,000 VND/pack
(15,000 g when Ingredient.base_unit is g). Future normalization must prove units.
SupplierTerm effective_from is UNCHANGED, NOT NULL with no default, as are strict
canonical procurement inputs including lead_time_days. Unknown source effective date
cannot be promoted into an active canonical term; upload date is not evidence.
Internal version may be system-assigned; business facts must be established.
No import/staging/readiness column or computation exists.
