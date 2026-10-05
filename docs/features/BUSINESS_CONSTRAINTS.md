# Versioned business constraint persistence — S1.3

CURRENT FACT (S1.5): internal repository access is now implemented; see
[PERSISTENCE_ACCESS](PERSISTENCE_ACCESS.md). Statements below about repository
absence describe the HISTORICAL INFORMATION of this schema slice. Its direct
Session tests remain schema evidence; operational services/APIs/engines and
application lifecycle/audit enforcement remain unimplemented.

## Status and purpose

CURRENT FACT: controlled BusinessConstraint persistence exists, no constraint API,
repository or planning/simulation computation. Backend owns type vocabulary; LLM
cannot invent types. ADR-001/007 and DATABASE_SCHEMA govern this storage boundary.

## Registry, scope and version semantics

business_constraints references stores; INGREDIENT scopes also reference ingredients.
Only STORE/BUDGET_LIMIT and INGREDIENT/MIN_SAFETY_STOCK. STORE scope_id NULL;
INGREDIENT scope_id required, same Store and exact base_unit through composite FK.
numeric_value required finite >=0. Budget unit uppercase currency shape; matching
Store.currency is future application validation, not DB-enforced. No text/JSON value,
MAX_STORAGE, other scopes, store_settings budget or Budget aggregate exists.

Version positive integer, unique per store/scope/type including NULL STORE scope
via PostgreSQL NULLS NOT DISTINCT. Inclusive start/end, NULL end unbounded; end>=start.
GiST exclusion blocks overlapping active periods using a non-NULL scope expression.
Inactive drafts can overlap but activation cannot violate integrity. At D select
active AND start<=D AND (end IS NULL OR D<=end), returning zero/one per logical key.
Different Stores/Ingredients/types are independent. Stored versions remain editable;
future changes should create new versions and snapshots capture exact used values.

## Tests and required fixtures

S1.3 tests persist/reload STORE budget 7000000 VND, Milk safety 10000 ml, Jan 2026
period and adjacent Feb open end. Reject scope/id/type combinations, invalid number/
version/range/unit and cross-store/missing Ingredient; enforce unique version even
with NULL scope, overlap/shared boundary and inactive activation. Multiple logical
keys can share dates; zero value and single-day period are valid. Tests use only
shelfcash_test, committed writer closed before reads.

## Manual verification and DB inspection

Follow [S13_VERIFICATION](../runbooks/S13_VERIFICATION.md), which executes:

```sql
SELECT store_id, scope_type, scope_id, constraint_type, numeric_value, unit,
       version, effective_from, effective_to, active FROM business_constraints
ORDER BY store_id, scope_type, scope_id, constraint_type, version;
```

Expected after reset: zero rows, head 0006_forecast_decision_persist. Schema inspection
shows registry/scope/value/version/date CHECKs, NULLS NOT DISTINCT unique, partial
exclusion and ingredient/store/unit FK. Fixture values are verified through new
sessions by targeted tests; no manual development writes/API required.

## Failure/reset/limits and future API

Invalid registry/scope/value/reference/version/overlap fails in PostgreSQL; malformed
reversed ranges may fail during range construction. Roll back before retry. Guarded
reset_db reapplies head with no data, seed stays no-op. No spent/reserved/rollover,
authorization, currency conversion, solver or public API; future surface PROPOSAL.

ACCEPTED DECISION (ADR-010): missing numeric/effective-date business facts cannot
be replaced with zero or upload dates. Internal version is backend metadata, distinct
from an effective date. No import/readiness service or new constraint type is added.
