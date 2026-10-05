# Domain model

ACCEPTED DECISION: boundaries and business authority below describe future behavior,
not implemented services. Entity details are PROPOSAL under Schema v1. CURRENT FACT:
only empty domain packages exist; no computation, entities or aggregates exist in code.

## Boundaries and relationships

| Boundary | Entities / value concepts | Responsibility and dependencies |
| --- | --- | --- |
| Identity / Authorization | User, StoreMembership, OWNER, STAFF, delegated permissions | Authorize store-scoped reads, simulation and mutation separately; all other boundaries enforce permissions at application entry. |
| Import / Mapping | ImportJob, MappingProfile, canonical fields | Validate operational inputs; approved profiles and rules first; bounded LLM suggestion only for ambiguity; human approval where required. |
| Catalog / Recipe | Store, Product, Ingredient, Recipe, RecipeLine; units, recipe version | Define saleable products, ingredients and deterministic expansion inputs; no LLM facts. |
| Operational Data | SalesDaily; store business date, cutoff | Validated historical sales feed Forecasting; cutoff separates observed inputs from future demand. |
| Forecasting | ForecastRun, ForecastPrediction, P25/P50/P75 | Deterministic model/baseline outputs with input/model versions; consumes sales and product catalog. |
| Ingredient Demand | Ingredient quantity over time | Expands forecast using catalog/recipe versions; does not select procurement strategy. |
| Inventory / FEFO | InventoryLot; usable quantity, expiry, arrival | Supplies deterministic lot availability/allocation to simulator using demand and dates. |
| Procurement | Supplier, SupplierTerm, BusinessConstraint; packs, MOQ, lead time, candidate strategy | Generates exactly LEAN/BALANCED/PROTECTED candidates from demand, inventory and constraints. |
| Decision | DecisionRun, versioned package, simulation metrics, warnings, risks, recommendation, hypothetical comparison | Simulates each candidate, compares deterministically and preserves evidence; human owns final decision. |

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
