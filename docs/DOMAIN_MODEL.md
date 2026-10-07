# Domain model

ACCEPTED DECISION: boundaries and business authority below describe future behavior,
not implemented engines. CURRENT FACT: plain Python domain implements exact
nonnegative inventory balance arithmetic (S1.7) and forecast semantic validation
(S2.1), plus baseline-specific readiness and historical quantile computation (S2.2).
S2.4–S2.7 add causal domain features/metrics and trained Forecast models in infrastructure,
with application evaluation/retained artifact replay; other domain engines remain absent.
S1.1 User/Store/StoreMembership and S1.2 Product/Ingredient/Recipe/RecipeLine
persistence models exist. S1.3 adds Supplier, SupplierTerm, SalesDaily, InventoryLot,
InventoryMovement and BusinessConstraint. Their storage contracts are accepted in DATABASE_SCHEMA;
S1.4 adds ForecastRun/ForecastPrediction/DecisionRun persistence only;
S2.3 adds internal retained baseline execution/replay; Decision Engine remains absent.
All other entity details remain PROPOSAL.

## IMPLEMENTED — Identity / Authorization + Store persistence subset

User stores UUID identity, canonical unique email, opaque password_hash, display name,
active flag and aware timestamps. Store stores UUID business context, nonunique name,
timezone/currency (defaults Asia/Ho_Chi_Minh / VND), active flag and aware timestamps.
StoreMembership links existing User and Store UUIDs, uniquely per pair, with constrained
OWNER/STAFF role and reserved empty delegated_permissions JSONB. Parent deletion is
restricted while referenced. These are mutable persistence rows, not domain services.

Relationship: User → many StoreMembership rows ← Store; a user may belong to multiple
stores and a store may have multiple users. Membership persistence exists.
Authorization enforcement, login/password verification, permissions,
application services and public User/Store/Membership APIs are NOT IMPLEMENTED.
No role, membership or active flag currently authorizes an application operation.
See [DATABASE_SCHEMA](DATABASE_SCHEMA.md) for exact accepted storage invariants and
[STORE_IDENTITY](features/STORE_IDENTITY.md) for persistence/manual verification.

## IMPLEMENTED — Catalog + Recipe persistence subset

Store owns Products and canonical Ingredients. Product owns dated Recipe versions;
Recipe owns RecipeLines pointing to Ingredients in the same Store. Store-scoped,
case-sensitive nullable SKUs are unique when present; names are not unique.
Product price is optional, nonnegative finite Decimal in store currency.

Recipe version is a positive integer unique per Product. Period boundaries are
inclusive DATEs; NULL effective_to means unbounded future. At D, active means
effective_from <= D and (effective_to IS NULL or D <= effective_to). PostgreSQL
exclusion guarantees at most one matching version, even for direct/concurrent SQL.
It can yield no recipe. Same-day periods are valid; shared boundary days overlap.

yield_quantity is finite >0 and represents total output in Product.selling_unit.
Each line quantity is finite >0 for that whole yield. process_loss_rate is recipe-level,
defaults zero and is in [0,1). Future BOM uses theoretical/(1-loss); computation is
NOT IMPLEMENTED. Units are nonblank exact labels with no conversion engine.
One Ingredient appears at most once per Recipe, and line.unit equals base_unit.
Composite FKs, including RecipeLine.store_id as an integrity witness, enforce
same-store graphs and exact units on inserts/updates. These are persistence
relationships, not application authorization. Definitions are mutable; no historical
snapshot immutability is claimed. See [CATALOG_RECIPE](features/CATALOG_RECIPE.md).

## IMPLEMENTED — Supplier / Operational / Constraints persistence

Supplier belongs to Store; names are not unique. SupplierTerm links Supplier and
Ingredient in the same Store, many-to-many. Pack size in Ingredient.base_unit,
minimum whole packs, pack cost in Store currency, lead/shelf-life days and positive
version are explicit. Retained unit is a DB integrity witness, not conversion logic.
Terms/constraints have inclusive DATE bounds, NULL open end and active flags;
partial GiST exclusion gives at most one active version per logical key at a day.
Inactive overlaps are allowed but activation is checked. Changes should preserve
history with new versions; SQL immutability is not enforced by these models.

SalesDaily is one finite nonnegative quantity per Store/Product/sales_date.
Source is not identity. ADR-008 freezes future NEW/UNCHANGED/CHANGED/INVALID/CONFLICT
classification, no additive duplicates, default replace-all or generic upsert,
domain-specific corrections, provenance and explicit modes. Import/correction
implementation remains absent. Changed total 100->105 never implies 205.

InventoryLot stores current actually received lot balance, not incoming stock.
Ingredient/optional supplier/store/unit must agree; balance finite >=0, optional
expiry >=receipt when both dates are known. InventoryMovement links the exact lot/store/ingredient, constrained
reason/type and signed nonzero finite delta, occurred time and optional source hooks.
ADR-009: current balance + movement history, not Event Sourcing. Expired lots retained
but unusable for future demand. Future application must atomically create movement
and update balance; unexplained overwrite is forbidden policy. No balance trigger,
FEFO, expiry computation, immutable SQL ledger or mutation workflow exists. Tracked
ingredients' mandatory expiry remains future application validation.

BusinessConstraint registry is only STORE/BUDGET_LIMIT (NULL scope_id) and
INGREDIENT/MIN_SAFETY_STOCK (required same-store Ingredient and exact base unit).
Value finite >=0; version unique even for NULL STORE scope. No arbitrary text/JSON,
other scopes/types or Budget aggregate. Budget currency shape is DB checked; exact
Store.currency matching is future application validation. Planning computation is
absent. See SUPPLIER, OPERATIONAL_DATA, INVENTORY and BUSINESS_CONSTRAINTS feature
docs for actual persistence tests and manual inspection.

## Boundaries and relationships

| Boundary | Entities / value concepts | Responsibility and dependencies |
| --- | --- | --- |
| Identity / Authorization | User, StoreMembership, OWNER, STAFF, delegated permissions | CURRENT FACT: User/membership persistence exists; permissions reserved empty. FUTURE: authorize store-scoped reads/simulation/mutation separately at application entry. |
| Import / Mapping | ImportJob, MappingProfile, canonical fields | ACCEPTED: ADR-008 policy. CURRENT FACT: no import implementation. FUTURE: validated idempotent domain corrections, profiles/rules and bounded ambiguity suggestions. |
| Catalog / Recipe | Store, Product, Ingredient, Recipe, RecipeLine; units, recipe version | CURRENT FACT: S1.2 persistence and DB integrity exist. FUTURE: APIs/resolution/BOM computation; no LLM facts. |
| Operational Data | SalesDaily; store business date, cutoff | CURRENT FACT: canonical daily persistence. FUTURE: import/correction and sales feed to Forecasting. |
| Forecasting | ForecastRun, ForecastPrediction, P25/P50/P75 | CURRENT FACT: persistence, S2.1 contracts and S2.2 pure historical baseline exist. S2.3 adds retained baseline persistence/replay. FUTURE: trained model and evaluation. |
| Ingredient Demand | Ingredient quantity over time | Expands forecast using catalog/recipe versions; does not select procurement strategy. |
| Inventory / FEFO | InventoryLot, InventoryMovement; usable quantity, expiry, arrival | CURRENT FACT: lot/movement schema; ADR-009 policy. FUTURE: atomic audited mutations and FEFO/availability/allocation. |
| Procurement | Supplier, SupplierTerm, BusinessConstraint; packs, MOQ, lead time, candidate strategy | CURRENT FACT: versioned input persistence. FUTURE: exactly LEAN/BALANCED/PROTECTED candidates; no procurement computation yet. |
| Decision | DecisionRun, versioned package, simulation metrics, warnings, risks, recommendation, hypothetical comparison | CURRENT FACT: historical persistence exists. FUTURE: simulates each candidate, compares deterministically and preserves evidence; human owns final decision. |

Dependencies follow the business pipeline: operational truth/catalog → forecast →
ingredient demand → inventory/supplier constraints → candidates → exact simulation
→ comparison/recommendation → DecisionRun → explanation/what-if. No circular imports,
ORM dependencies or transport concerns belong in domain code. Application orchestrates
cross-domain work; shared facts use explicit values/contracts when a slice needs them.

## Core invariants — ACCEPTED DECISION for later implementation

- Expired lots cannot satisfy future demand and contribute zero usable quantity.
- FEFO prefers the earliest usable expiry; unusable/not-yet-arrived lots are excluded.
- Procurement quantity obeys pack size; MOQ is respected when an order is placed.
  Zero orders need not satisfy MOQ. Exact rounding/unit conversion rules need a slice contract.
- Future demand starts strictly after the cutoff boundary; timezone/business-date
  and expiry boundary details must be frozen before implementation.
- Supplier lead time prevents using incoming inventory before arrival.
- Quantiles represent uncertainty, with P25 ≤ P50 ≤ P75; they are never three plans.
- Strategies are exactly LEAN, BALANCED and PROTECTED, with the objectives in ARCHITECTURE.
- Every candidate is evaluated by deterministic exact simulation. Recommendation
  and selected strategy come from backend comparison; infeasibility is reported,
  never hidden or repaired by invented LLM facts.
- LLM cannot create business facts, canonical fields, constraints or authorization.
- Store-scoped access is enforced by backend, including authorized facts sent to LLM.
- DecisionRun includes `package_schema_version` from version 1 and preserves historical
  inputs/versions, demand, candidates, metrics, selected recommendation, risks,
  warnings and evidence without reinterpretation through mutable current state.
- What-if recomputes from baseline plus explicit mutation. Its output is hypothetical;
  simulation permission is distinct from permission to mutate real business state.

## Value concepts — PROPOSAL requiring contract decisions

Use explicit quantities/units, monetary amounts, dates, cutoff, recipe/model versions,
strategy identifiers and evidence references as needed. Precision, pack conversions,
tie breaking and scenario selection are unresolved. No additional aggregates,
generic services or speculative inheritance are authorized by this document.

## Data completeness -- ACCEPTED DECISION (ADR-010)

REQUIRED missing facts invalidate a record. CONDITIONAL_REQUIRED inputs block only
their specified use case when unknown. OPTIONAL_WARNING permits a meaningful record
with an explicit lost-capability warning; OPTIONAL absence has no current-use-case
impact or warning. Strict canonical SupplierTerm still requires effective date and
procurement inputs; incomplete source data stays unresolved outside canonical terms.

### Source fact classification

SOURCE_EXPLICIT is stated evidence; DETERMINISTIC_DERIVED requires proven inputs
and units plus explainable/testable arithmetic; SYSTEM_ASSIGNED is backend metadata;
UNKNOWN lacks established facts; AMBIGUOUS has multiple plausible meanings. MISSING
is absence, distinct from AMBIGUOUS. Missing never becomes zero, false, upload date,
snapshot date or a fabricated business default. Suggestions cannot establish facts.

### Computation readiness

Valid canonical data is not necessarily ready for every computation. Unknown receipt
date permits stock representation, but blocks inventory-age analysis; future FEFO
depends on expiry evidence. Unknown lead time blocks delivery feasibility. No fake
fallbacks, readiness service or persisted readiness status exists in this slice.

### Canonical vs import boundary

Canonical holds sufficiently established entity facts, with allowed optional NULLs.
Future mapping retains raw/unknown/ambiguous values, decisions, warnings and conflicts.
Future warnings require code, severity, field, entity and impact. No warning API,
parser or staging tables exist. See ADR-010 and IMPORT_MAPPING for accepted policy.

## IMPLEMENTED -- S1.4 run persistence

Store owns ForecastRuns; runs own explicit Product/date predictions in the same
Store. Required training/horizon DATE windows are ordered; status is RUNNING,
COMPLETED or FAILED. Finite Decimal quantities satisfy 0 <= P25 <= P50 <= P75
in Product.selling_unit. These uncertainty quantiles are not mapped to
LEAN/BALANCED/PROTECTED strategies. Metadata records the actual model/version;
optional artifact key refers to filesystem binaries, metrics assess forecast quality.

DecisionRun requires same-store ForecastRun and ordered planning period. Completed
rows require positive package version (initially 1), fingerprint, object input/output
JSON, constrained recommended strategy and terminal time; failed/partial rows have no
fake completed output. Snapshots preserve used values plus identities/versions.
ADR-011 freezes snapshot-before-computation, historical self-containment, completed
immutability and new-run reruns. DB enforces local state/shape/FKs; service-level
immutability, horizon membership, forecast readiness and full package validation are
NOT IMPLEMENTED. No engine/hasher/snapshot builder or public API exists.
S1.5 concrete repositories provide scoped persistence access; see PERSISTENCE_ACCESS.
CURRENT FACT: Forecast/Decision repository writers guard RUNNING-only terminal
transitions and Forecast prediction append. Full application immutability/horizon/
package validation remains future; tracked ORM rows and privileged SQL can bypass
repository policy. No domain computation or business semantics changed in S1.5.
Returned ORM rows are internal persistence objects, never domain computation inputs.
What-if stays non-persistent by default; LLM cannot select recommendation or facts.
See FORECAST, DECISION_RUN and DATABASE_SCHEMA for actual contracts/limitations.

## S1.6 internal application boundary -- CURRENT FACT

The preceding schema-slice descriptions of future application invariants are
historical where superseded by [APPLICATION_CONTRACTS](features/APPLICATION_CONTRACTS.md).
Product creation/scoped read, canonical Sales insertion/history and dated Recipe
selection now have typed validated paths. Forecast completion validates same-store
Products, inclusive horizon and RUNNING lifecycle; Decision requires a completed
same-store Forecast and stores supplied metadata/snapshot/package atomically.
Outputs are by-value contracts rather than tracked ORM. Full engine/package business
validation, audited inventory mutations, correction workflows and authorization
remain future in that S1.6 slice. HISTORICAL INFORMATION: S1.6 added no domain
computation; S1.7/S2 later add inventory arithmetic, forecast baseline/features/metrics.

## S1.7 operational boundary -- CURRENT FACT

S1.7 supersedes earlier empty-domain and absent inventory/Ingredient/Recipe writer
claims for its authorized paths. Store/Ingredient and SupplierTerm create/read,
atomic Recipe version+lines, receipt lot+RECEIPT and locked movement-backed
corrections now use typed internal application contracts. The plain Python balance
function adds exact Decimal deltas and rejects negative results. S2 later adds
forecast baseline/features/metrics and the infrastructure trained model. Ingredient units match exactly and money inherits
Store.currency without conversion/rounding. Business DATE facts stay explicit;
aware inventory event timestamps are UTC. Unknown receipt stays NULL; tracked
Ingredients require expiry. New version/movement corrections leave accepted history
untouched. Full Sales correction, importing, auth and Decision computation remain
future work. Forecast's S2 extension is documented separately. See APPLICATION_CONTRACTS and S17_VERIFICATION for precise boundaries.
