# Schema v1 proposal

**PROPOSAL:** all business entities below are conceptual; no business tables exist
in the scaffold. Field names/types, constraints and indexes must be accepted for each
vertical slice before migrations/models are implemented. No hidden aggregate is implied.

**CURRENT FACT / ACCEPTED DECISION (ADR-003):** SQLite is the current Competition
database, with SQLAlchemy 2.x and synchronous Session. Reset between versions is
acceptable. Alembic makes schema state/evolution explicit; long-lived backwards-compatible
migration support is not a current requirement. The initial empty revision creates
only `alembic_version`. There is no DecisionRun ORM model yet.

## Common conventions — PROPOSAL

Each entity has a primary `id`. Store-owned records use `store_id` with enforced
foreign keys and application authorization. Cross-store relationships must be
rejected by the backend; composite keys/FKs may enforce them when appropriate.
Identifier encoding, timestamp storage and currency/quantity precision are unresolved.
Do not rely on SQLite floating point for exact financial truth: choose an explicit
money representation/rounding contract in the first affected slice.
Business-date boundaries use an explicitly agreed store timezone/cutoff policy.
Indexes below are candidates for real queries, not a command to create unused indexes.

| Entity | Purpose and key fields | Relationships | Important constraints / indexes | Current state or historical snapshot |
| --- | --- | --- | --- | --- |
| User | Human identity: id, login identifier, display name, authentication reference, active flag | Memberships connect users to stores | Unique normalized login identifier; no plaintext secrets; auth mechanism deferred | Current identity; historical decisions cannot rely on mutable display name for meaning |
| Store | Business scope: id, name, timezone, active flag | Parent of memberships and store-owned operational data | Required name/timezone; store isolation across relations | Current store settings, relevant values copied into decision history |
| StoreMembership | Access: id, user_id, store_id, role, delegated permissions, active flag | User ↔ Store | Unique (store_id, user_id); role restricted to OWNER/STAFF; explicit permission vocabulary; index user_id | Current authorization; audited actor context may be captured in runs |
| ImportJob | Trace ingestion: id, store_id, source reference/digest, status, mapping_profile_id, created_at, validation summary | Store; optional MappingProfile; provenance for imported rows | Store/date index; validated status transitions; immutable source reference; file/row errors separate from accepted data | Historical import execution/status record |
| MappingProfile | Approved store mapping: id, store_id, profile version, canonical schema version, file fingerprint, field mapping, approval actor/time, status | Store, approving User/Membership; ImportJobs | Unique (store_id, profile key, version); mapping targets restricted to canonical fields; approved versions immutable | Versioned approved mapping snapshot, with explicit current active selection |
| Product | Saleable item: id, store_id, code, name, active flag | Store; Recipes, SalesDaily, ForecastPrediction | Unique (store_id, code); store-scoped relations | Current catalog; relevant version/data preserved in history |
| Ingredient | Procurement/consumption item: id, store_id, code, name, base_unit, active flag | Store; RecipeLine, InventoryLot, SupplierTerm | Unique (store_id, code); valid unit; no implicit incompatible conversions | Current catalog; historical units/identities captured in runs |
| Recipe | Versioned expansion definition: id, store_id, product_id, version, effective_from, effective_to, yield quantity/unit | Product; RecipeLines | Unique (product_id, version); positive yield; effective range validation and unambiguous version selection | Versioned recipe snapshot; referenced versions cannot silently change |
| RecipeLine | Ingredient amount per recipe yield: id, recipe_id, ingredient_id, quantity, unit | Recipe → Ingredient in same store | Positive quantity; index recipe_id; conversion into ingredient base unit must be explicit; duplicate-line policy deferred | Belongs to immutable recipe version |
| Supplier | Supplier identity: id, store_id, code, name, active flag | Store; SupplierTerms | Unique (store_id, code); index store_id | Current supplier metadata; historical relevant terms captured separately |
| SupplierTerm | Ordering inputs: id, store_id, supplier_id, ingredient_id, unit price/currency, pack_size, MOQ, lead_time_days, valid_from/to, version | Supplier and Ingredient in same Store | pack_size > 0; MOQ ≥ 0; price ≥ 0; lead time ≥ 0; valid ranges; index supplier/ingredient/date; term version uniqueness | Versioned term; chosen values copied into DecisionRun |
| SalesDaily | Observed daily sales: id, store_id, product_id, business_date, quantity, import_job_id | Store, Product; optional ImportJob | Unique (store_id, product_id, business_date) for daily aggregate; index store/date; quantity validation and correction policy must be frozen | Historical observation, potentially corrected explicitly; run captures exact used data/version |
| InventoryLot | Stock by lot: id, store_id, ingredient_id, lot code, received/available date, expiry date, remaining quantity, unit, import_job_id | Ingredient, Store; optional ImportJob | Quantity ≥ 0; index store/ingredient/expiry; date consistency; same-store links; expired/future arrivals excluded from availability | Current lot balance; historical usable balances/availability copied into decisions |
| BusinessConstraint | Explicit planning settings: id, store_id, version, effective range, budget, planning horizon, target service level, allowed supplier references | Store; validated Supplier references if used | Typed important fields; budget ≥ 0, valid horizon/target/range; index store/effective date; backend validates unsupported constraints | Versioned settings with current selection; exact used values in run snapshot |
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

Freeze deletion/retention policy, unit/money representation, corrections, login handling,
delegated permission storage, forecast input artifact retention and exact package schema
in affected slices. Choose schema evolution for clarity and reproducibility, without
legacy compatibility scaffolding or an unrequested database engine.
