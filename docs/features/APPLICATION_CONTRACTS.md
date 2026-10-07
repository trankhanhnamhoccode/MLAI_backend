# Application contracts and validated paths -- S1.6 / S1.7

## Purpose and boundaries -- ACCEPTED DECISION

S1.6 freezes an internal boundary callable from future HTTP, Import, CLI/tests or
internal workflows without simulating HTTP. API contract != Application contract.
API handles transport; typed application use cases validate/orchestrate/own writes;
repositories perform persistence on the supplied synchronous Session. Future engines
own deterministic domain computation. No business engine or public route is added.

```text
Future HTTP / Import / internal caller
  -> typed application input -> validation -> use case
  -> S1.5 repository -> SQLAlchemy / PostgreSQL -> typed by-value output
```

## Implemented contracts and methods -- CURRENT FACT

| Contract module | Use case methods | Input / output |
| --- | --- | --- |
| store | StoreUseCases.create / get | CreateStoreInput / GetStoreInput -> StoreResult |
| catalog | ProductUseCases.create / get; IngredientUseCases.create / get | Product and Ingredient typed create/scoped read -> by-value results |
| supplier | SupplierTermUseCases.create / get | CreateSupplierTermInput / GetSupplierTermInput -> SupplierTermResult |
| inventory | InventoryUseCases.receive / adjust / get / movements | ReceiveInventoryInput / AdjustInventoryInput / GetInventoryLotInput -> lot+movement / lot / tuple of movements |
| sales | SalesUseCases.record / history | RecordDailySalesInput / GetSalesHistoryInput -> SalesResult / tuple of SalesResult |
| forecast | ForecastUseCases.start / complete / fail / get | StartForecastRunInput / CompleteForecastRunInput / FailRunInput / RunReferenceInput -> ForecastRunResult including ordered predictions |
| decision | DecisionUseCases.start / complete / fail / get | StartDecisionRunInput / CompleteDecisionRunInput / FailRunInput / RunReferenceInput -> DecisionRunResult |
| recipe | RecipeUseCases.create_version / get_active | CreateRecipeVersionInput / GetActiveRecipeInput -> RecipeResult with typed lines; read returns None when no version is effective |

Locations: app/application/contracts, use_cases, errors.py; small preconditions in
_validation.py. Contracts use Pydantic v2, extra=forbid, frozen fields and input
revalidation on entry, including nested models. No request/header/status/route imports.
Inputs/outputs reuse fields when semantics agree; no mechanical DTO stack/framework.
Results contain UUID/date/aware datetime/Decimal and tuples, never ORM rows. JSON is
copied by value; nested JSON remains locally mutable but cannot change tracked or
committed persistence. Frozen Pydantic fields are not claimed as recursively immutable.

## Validation responsibilities -- ACCEPTED DECISION / CURRENT FACT

Pydantic checks required facts, type, length/nonblank, finite nonnegative Decimal,
ordered date ranges/quantiles, distinct prediction identities, timezone-aware instants,
positive integer package version and allowed recommendation. Decimal inputs accept
Decimal, decimal strings or integers; float/bool quantities/prices are rejected.
There is no implicit rounding/fixed scale/conversion. Case-sensitive SKUs and exact
unit labels are preserved, including surrounding spaces: no invented normalization.
Product active=true reuses the accepted catalog lifecycle metadata default. Optional
SKU/price stays None; required sales/date/quantity and run metadata have no invented
business fallback. ADR-010 completeness is respected; no generic warning engine.

Application checks current Store/Product/Ingredient/Supplier/lot/Forecast scope and
existence, exact ingredient units, tracked receipt expiry, nonnegative corrected
balance, RUNNING-only
terminal lifecycle, terminal time >= start, prediction membership in the inclusive
forecast horizon and completed same-store Forecast consumption by Decision. Decision
planning period is ordered; no speculative planning/horizon equality is imposed.
PostgreSQL FK/UNIQUE/CHECK/exclusions remain final safety nets. Pydantic contains no
forecast/BOM/FEFO/procurement/simulation/recommendation computation.

## Store context and errors -- ACCEPTED DECISION

Store creation establishes a new UUID; Store read requires that explicit UUID.
All Store-owned entity entry paths require explicit store_id and scoped repositories.
Missing and wrong-store entities both raise NOT_FOUND without cross-store probing.
Scope enforces data isolation; it does not prove an actor is authorized. These are
trusted internal entry points; membership/login/delegated permissions remain future
and must precede any real business exposure through a public transport.

| Error | Behavior |
| --- | --- |
| Pydantic ValidationError | Shape invalid before any repository call; native typed validation details remain available |
| ApplicationError / VALIDATION_ERROR | Valid shape violates current-state time/horizon, exact unit, required tracked expiry or nonnegative corrected balance rule |
| ApplicationError / NOT_FOUND | Missing Store or scoped entity; wrong-store references use the same convention |
| ApplicationError / CONFLICT | Known canonical SKU/Sales/prediction/version key or active period conflict; also a caller Session already owns a transaction |
| ApplicationError / INVALID_LIFECYCLE | Terminal Forecast/Decision write or Decision references a non-completed Forecast |

Known PostgreSQL conflicts map only exact SQLSTATE plus named constraint: 23505
for uq_products_store_sku, uq_ingredients_store_sku, uq_sales_daily_store_product_date,
uq_forecast_predictions_run_product_date, uq_recipes_product_version and
uq_supplier_terms_pair_version; 23P01 for ex_recipes_product_period and
ex_supplier_terms_pair_period. Duplicate/overlapping versions never edit old periods. No raw DB internals are required for those
known errors. Unknown IntegrityError/OperationalError/programming errors propagate
after rollback; broad catches perform rollback and re-raise, never invent a business
error. Application categories carry no HTTP status; future API mapping is separate.

## Transactions and historical lifecycle -- ACCEPTED DECISION / CURRENT FACT

Composition supplies one Session to participating repositories; caller closes it.
Use a dedicated fresh Session for each write. Write methods require an idle clean
Session, visibly begin, validate/load, stage, flush, map a result before commit, then
commit. Any failure in the owned transaction rolls back. An already-open transaction
is rejected before begin/rollback/commit, preserving unrelated caller work. Shape
validation occurs before starting the transaction. No hidden commit decorator,
UnitOfWork or generic service exists. Repository S1.5 ownership remains unchanged.

Read methods suppress autoflush and never commit/rollback or mutate rows. SQLAlchemy
read autobegin still occurs; caller must end it or use a new Session before a write.
Do not mix uncommitted ORM edits with application reads and expect committed-state
snapshots: Session identity-map semantics still apply to internal repository rows.

Forecast start stores explicit metadata only. Complete locks/refreshes the scoped
RUNNING row, checks each supplied Product/date, appends validated predictions, stages
COMPLETED and commits in the same transaction. Empty predictions are allowed by the
existing persistence contract; coverage/data-readiness requirements await S2.
Fail stores a supplied sanitized failure and terminal time. Retry always starts a
new UUID. Complete/fail never changes a terminal run. No input hasher/artifact/model
runner exists and fingerprints do not promise reproducibility or deduplicate runs.

Decision start requires a completed same-store Forecast and stores planning metadata.
Complete locks/refreshes RUNNING, checks the source Forecast again, persists copied
snapshot/package/fingerprint/version/recommendation and commits together. Fail stores
explicit sanitized failure without output. Start deliberately leaves snapshot/version
absent rather than manufacturing facts. Supplied snapshots/packages are fixture or
trusted internal input in S1.6; no engine creates them.

Two explicit repository extensions get_running_for_update expose existing scoped
RUNNING row locks for application validation; guard/lock lifetime remains S1.5. They
do not commit, close, compute or authorize. Direct ORM/SQL still bypasses policy.

## Known limitations -- CURRENT FACT / PROPOSAL

JsonObject is a finite object of recursively typed JsonValue, not dict[str, Any].
It deliberately validates only the envelope; full versioned Decision business schema,
all-candidate evaluation/recommendation consistency, captured-input provenance and
snapshot-before-computation await the engine slice. Positive supplied package versions
are retained; no automatic version is fabricated. Initial real engine format starts
at 1 under ADR-005/011. Monetary/quantity values in opaque fixtures use decimal strings;
JsonObject is not a second money contract. Failure strings must already be sanitized
by the trusted caller; no credential/stack-trace sanitization claim is made.

HISTORICAL INFORMATION: S1.6 covered representative paths only. S1.7 now adds the
remaining authorized operational boundaries below. Supplier identity creation stays
an explicit S1.5 repository prerequisite; SupplierTerm has its own application path.
There is no public business transport, actor authorization, import/readiness engine,
supplier selection, inventory set_on_hand, usage/waste/expiration writer or FEFO.
Direct privileged ORM/SQL can still bypass application history policy.

## Tests and manual verification -- CURRENT FACT

Follow [S16 verification](../runbooks/S16_VERIFICATION.md) and
[FULL_TEST_FLOW](../runbooks/FULL_TEST_FLOW.md). Unit contracts reject bad shape before
writes; integration uses actual isolated shelfcash_test, two Stores and fixed fixtures.
It verifies close/fresh-session persistence, typed copied outputs, scoped/temporal
reads, duplicates without overwrite, terminal guards, rollback after real SQL flush,
commit failure, unexpected DB propagation and preservation of caller-owned work.
Forecast/Decision fixture results prove persistence orchestration, not calculations.
API tests continue to verify only health/OpenAPI. No business e2e API tests are claimed.

Rollback reverts application/contracts/errors/tests/docs and two small lock lookups;
there is no schema/migration rollback. Head remains 0006_forecast_decision_persist.

## S1.7 operational contract -- ACCEPTED DECISION / CURRENT FACT

- Store create/read preserves name, explicit timezone/currency and active metadata.
  Defaults Asia/Ho_Chi_Minh and VND remain accepted scaffold defaults. Timezone is
  nonblank <=64 characters; currency is exactly three uppercase ASCII letters.
  Neither is claimed as validation against IANA/ISO catalogs. Names are nonunique.
- Ingredient create/read validates its Store; SKU is nullable and unique per Store.
  base_unit is an exact nonblank label, expiry_tracking=false and active=true reuse
  accepted metadata defaults. No canonical quantity or unit is inferred.
- SupplierTerm create/read requires scoped Supplier and Ingredient, exact unit,
  explicit version/effective_from/pack quantity/MOQ/per-pack cost/lead time. Only
  effective_to, shelf life and accepted active metadata may be omitted. Active
  periods are inclusive and cannot overlap; inactive overlaps remain allowed.
- Recipe create_version validates scoped Product, every scoped Ingredient/unit,
  unique ingredient lines, explicit positive yield and explicit loss in [0,1).
  Header and all lines are flushed and committed together. The required lines
  tuple may explicitly be empty under the existing persistence contract; this
  does not assert BOM readiness. get_active retains inclusive date selection.

### Money, units and time -- ACCEPTED DECISION

All canonical quantities/money use finite Decimal with no binary float, implicit
rounding or fixed scale. Product.price and InventoryLot.unit_cost are optional;
SupplierTerm.pack_cost is required cost of one whole pack in Store.currency, not
price per base unit. Thus known 15000 g at 28 VND/g is 420000 VND per pack; this
slice accepts the confirmed pack value and does not perform source conversion.
Inventory unit_cost is per Ingredient.base_unit. Currency is inherited from Store;
these writers accept no alternate currency field or conversion. Existing budget
unit=Store.currency policy is unchanged; no budget/constraint writer is introduced.
Budget validation at such a future boundary is not an unclosed S1.7 gate.

Ingredient.base_unit, RecipeLine.unit, SupplierTerm.unit and InventoryLot.unit must
match exactly. Product.selling_unit describes Recipe yield; ingredient line values
are quantities for that entire yield. No kg/g/L/ml conversion or normalization.
Business DATE facts (sales, effective periods, receipt/expiry, forecast/planning)
are distinct from event instants. Receipt received_date stays None when unknown;
no upload/snapshot/occurred_at/current date substitutes it. Both-known dates enforce
expiry>=received_date. Tracked ingredients require known expiry at receipt.
Inventory occurred_at must be aware and is normalized to UTC; Store.timezone is
business interpretation metadata, not a source of fabricated business dates.
Future forecast cutoff/expiry-day computation and currency rounding remain PROPOSAL.

### Correction and atomic inventory paths -- ACCEPTED DECISION / CURRENT FACT

Sales duplicate Store/Product/date remains CONFLICT: no sum, upsert, overwrite or
full correction workflow. Recipe/SupplierTerm corrections create an explicitly
numbered new version with supplied nonoverlapping periods. Existing rows are never
edited or auto-closed; an open previous period therefore blocks an overlapping new
version until a separately authorized correction workflow resolves it.

receive creates a new received lot with positive initial balance plus exactly one
positive RECEIPT movement in one application-owned transaction. Optional paired
source reference and note are retained. lot_code is nonunique and does not provide
idempotency; repeated receipts create new UUIDs, not silent deduplication/upsert.

adjust accepts a finite nonzero signed delta only for COUNT_CORRECTION or
MANUAL_ADJUSTMENT, requiring a nonblank note as reason and optionally paired source
reference. It loads the scoped lot using existing SELECT FOR UPDATE with
populate_existing, holding the lock through commit/rollback. Plain Python domain
arithmetic adds the delta exactly and rejects a negative result; application stages
the locked materialized balance and one correcting movement together. No history
edit/delete or absolute-balance setter exists. Actor metadata is absent from the
current schema; this trusted internal slice makes no actor/authentication claim.

All six new writers follow the S1.6 idle-Session/begin/flush/result/commit convention.
Any failure, including a downstream constraint or commit failure, rolls back the
entire owned transaction. Concurrent adjustments wait for the same lot lock and
refresh its committed balance before adding their delta. By-value results survive
Session close. Reads do not flush/commit caller work. No additional repository
extension, DB trigger, dependency, table or migration was needed in S1.7.

### S1.7 verification -- CURRENT FACT

See [S17_VERIFICATION](../runbooks/S17_VERIFICATION.md) and
[S17_TASK_NOTES](../runbooks/S17_TASK_NOTES.md). New unit/integration coverage includes
shape/precision/domain independence; scoped exact Decimal writes; atomic Recipe
header+lines; receipt and correction rollback after real flush; every new writer's
commit failure/caller transaction preservation; read no-autoflush/no-commit;
stale cached balance refresh; real two-session PostgreSQL lock contention with no
lost update; and the complete S1 operational chain followed by fresh-session reads.
Existing S1.6 lifecycle/terminal/horizon/error regressions are preserved unchanged.
Rollback adds only application/domain/tests/docs changes; schema head stays
0006_forecast_decision_persist. Runtime counts and final gate evidence are recorded
in CURRENT_STATE, not inferred from HTTP status or schema fixtures.
