"""Separate /2 owned PostgreSQL source; shared repositories, unchanged /1 source."""
from datetime import datetime
from typing import Callable

from pydantic import ValidationError
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.application.contracts.decision_capture import (
    OperationalDecisionInput, OperationalFacts, StoreFact, ForecastFact, ScopedPrediction, SourceTime, CaptureProblem,
)
from app.application.contracts.decision_capture_v2 import OperationalDecisionInputV2, OperationalFactsV2, MenuProduct, SupplierTermIdentity
from app.application.contracts.decision_execution import CapturedDecisionProduct, CapturedDecisionIngredient, CapturedRecipe, CapturedDecisionConstraint
from app.application.contracts.inventory import InventoryLotResult
from app.application.contracts.recipe import RecipeLineInput
from app.application.contracts.supplier import SupplierTermResult
from app.application.contracts.forecast_model import ExecutionDetails
from app.application.decision_snapshot_source import OperationalDataError
from app.application.forecast_serialization import restore_prepared, RetainedInputError
from app.application.offer_admission import missing_offer_fields
from app.domain.forecasting.validation import forecast_dates
from app.infrastructure.database.forecast_execution_session import _execution_session
from app.repositories.identity import StoreRepository
from app.repositories.catalog import CatalogRepository
from app.repositories.recipe import RecipeRepository
from app.repositories.inventory import InventoryRepository
from app.repositories.supplier import SupplierRepository
from app.repositories.constraints import ConstraintsRepository
from app.repositories.forecast import ForecastRepository
from app.repositories.forecast_input import ForecastInputRepository
from app.repositories.forecast_execution_metadata import ForecastExecutionMetadataRepository


class PostgresDecisionSnapshotSourceV2:
    """Never accepts a caller Session. All DTO construction occurs inside capture.

    All active menu captured; inactive catalog retained for override validation.
    No Ingredient/FEFO filtering; unknown/expired/future stock survives capture. Application validates readiness after resources close.
    """
    def __init__(self, engine: Engine):
        self.engine = engine

    def read(self, request: OperationalDecisionInputV2, clock: Callable[[], datetime]) -> OperationalFactsV2:
        request = OperationalDecisionInputV2.model_validate(request)
        days = forecast_dates(request.cutoff_date)
        # Apply before begin/first statement; READ COMMITTED is insufficient here.
        with self.engine.connect().execution_options(isolation_level='REPEATABLE READ', postgresql_readonly=True) as connection:
            with _execution_session(connection) as session:
                session.begin()
                return read_operational_facts_v2(session,request,clock)


def read_operational_facts_v2(session: Session,request: OperationalDecisionInputV2,clock: Callable[[],datetime]) -> OperationalFactsV2:
    """Reuse the exact /2 row projection inside S4.9's owned coherent snapshot.

    Caller must own a READ ONLY REPEATABLE READ transaction; this helper never
    commits/closes it. The existing public source still accepts only an Engine.
    """
    request=OperationalDecisionInputV2.model_validate(request)
    days=forecast_dates(request.cutoff_date)
    store = StoreRepository(session).get_store_by_id(request.store_id)
    captured_at = clock()  # First SELECT fixed MVCC snapshot; marker, not temporal inventory lookup.
    times = []
    problems = []
    menu = []
    ingredient_scope_ids = []
    term_scope = []

    def fail(code, entity, identifier, field, detail):
        raise OperationalDataError((CaptureProblem(code=code, kind='DATA_BLOCKER', entity=entity,
            entity_id=identifier, field=field, detail=detail),), captured_at)

    def scoped(row, entity):
        if row.store_id != request.store_id:
            fail('CROSS_STORE_SOURCE', entity, getattr(row, 'id', None), 'store_id', 'Repository row outside requested Store')
        return row

    def remember(row, entity, identifier=None):
        identifier = identifier or row.id
        for attr, kind in (('created_at','ROW_CREATED_AT'), ('updated_at','ROW_UPDATED_AT'), ('completed_at','RUN_COMPLETED_AT')):
            value = getattr(row, attr, None)
            if value is not None:
                times.append(SourceTime(entity=entity, entity_id=identifier, kind=kind, at=value))

    def value(cls, row, entity, **fields):
        try:
            return cls(**fields) if fields else cls.model_validate(row)
        except ValidationError as error:
            admission=request.procurement.offer_admission
            if entity=='supplier_term' and admission:
                omitted=next((o for o in admission.omissions if o.term_id==row.id and o.reason=='SUPPLIER_TERM_FACT_UNAVAILABLE'),None)
                values={field:getattr(row,field,None) for field in SupplierTermResult.model_fields}
                if omitted and missing_offer_fields(values,error)==omitted.missing_fields:
                    return None  # Original identity/version and missing fields remain in captured admission.
            if entity=='recipe_line':
                problems.append(CaptureProblem(code='INVALID_RECIPE_LINE',kind='DATA_BLOCKER',entity='product',entity_id=product_id,field='recipe_line',detail=str(error)))
                return None
            # Product/Ingredient attribution is retained even when a row is
            # malformed. Unknown attribution remains a whole-capture error.
            local_entity = 'product' if entity in {'product','recipe','recipe_line','forecast_prediction'} else 'ingredient' if entity in {'ingredient','inventory_lot','supplier_term'} else None
            identifier = (getattr(row, 'product_id', None) or (getattr(row, 'id', None) if entity=='product' else None)) if local_entity=='product' else (getattr(row,'ingredient_id',None) or (getattr(row,'id',None) if entity=='ingredient' else None))
            if local_entity is None or identifier is None:
                fail('INVALID_SOURCE_ROW', entity, getattr(row,'id',None), 'source_fields', str(error))
            problems.append(CaptureProblem(code='INVALID_SOURCE_ROW',kind='DATA_BLOCKER',entity=local_entity,entity_id=identifier,field=entity,detail=str(error)))
            return None

    products, ingredients, recipes, lots, terms, constraints = [], [], [], [], [], []
    store_value = None
    if store is not None:
        remember(store, 'store')
        store_value = value(StoreFact, store, 'store', id=store.id, timezone=store.timezone, currency=store.currency)
    catalog = CatalogRepository(session)
    recipe_repo = RecipeRepository(session)
    supplier_repo = SupplierRepository(session)
    # This first catalog read and every later query share the Store-read MVCC snapshot.
    for row in catalog.list_products(request.store_id):
        scoped(row, 'product')
        menu.append(MenuProduct(store_id=row.store_id,product_id=row.id,name=row.name,
            selling_unit=row.selling_unit,active=row.active))
        if not row.active:
            continue
        product_id = row.id
        if row is None:
            continue  # Explicit requested scope checked in application; never fabricate Product.
        scoped(row, 'product'); remember(row, 'product')
        products.append(value(CapturedDecisionProduct, row, 'product', store_id=row.store_id,
            product_id=row.id, selling_unit=row.selling_unit, sku=row.sku))
        for recipe in recipe_repo.list_recipe_versions(request.store_id, product_id, assigned_only=True):
            scoped(recipe, 'recipe')
            if recipe.effective_from > days[-1] or (recipe.effective_to is not None and recipe.effective_to < days[0]):
                continue
            remember(recipe, 'recipe')
            lines = []
            for line in recipe_repo.list_recipe_lines(request.store_id, recipe.id):
                scoped(line, 'recipe_line'); remember(line, 'recipe_line')
                if line.recipe_id != recipe.id:
                    fail('RECIPE_LINE_PARENT_MISMATCH', 'recipe', recipe.id, 'lines', 'Recipe line parent mismatch')
                line_value = value(RecipeLineInput, line, 'recipe_line')
                if line_value is not None:
                    lines.append(line_value)
                else:
                    problems.append(CaptureProblem(code='INVALID_RECIPE_LINE',kind='DATA_BLOCKER',entity='product',entity_id=product_id,field='recipe_line',detail='Invalid line in captured Product recipe'))
            recipes.append(value(CapturedRecipe, recipe, 'recipe', id=recipe.id, store_id=recipe.store_id,
                product_id=recipe.product_id, version=recipe.version, effective_from=recipe.effective_from,
                effective_to=recipe.effective_to, yield_quantity=recipe.yield_quantity,
                process_loss_rate=recipe.process_loss_rate, lines=tuple(lines)))
    for row in catalog.list_ingredients(request.store_id):
        scoped(row, 'ingredient'); remember(row, 'ingredient')
        ingredient_scope_ids.append(row.id)
        ingredients.append(value(CapturedDecisionIngredient, row, 'ingredient', store_id=row.store_id,
            ingredient_id=row.id, unit=row.base_unit, expiry_tracking=row.expiry_tracking))
        for lot in InventoryRepository(session).list_lots(request.store_id, row.id):
            scoped(lot, 'inventory_lot'); remember(lot, 'inventory_lot')
            if lot.supplier_id is not None and supplier_repo.get_supplier(request.store_id, lot.supplier_id) is None:
                fail('LOT_SUPPLIER_SCOPE_MISMATCH', 'inventory_lot', lot.id, 'supplier_id', 'Supplier unavailable in Store')
            lots.append(value(InventoryLotResult, lot, 'inventory_lot'))
        for term in supplier_repo.list_active_supplier_terms(request.store_id, row.id, days[0]):
            scoped(term, 'supplier_term'); remember(term, 'supplier_term')
            supplier = supplier_repo.get_supplier(request.store_id, term.supplier_id)
            if supplier is None:
                fail('TERM_SUPPLIER_SCOPE_MISMATCH', 'supplier_term', term.id, 'supplier_id', 'Supplier unavailable in Store')
            scoped(supplier, 'supplier'); remember(supplier, 'supplier')
            if request.procurement.offer_admission and not supplier.active:
                continue  # Same explicit active-supplier scope as declarations_for; /1 and legacy /2 stay unchanged.
            term_scope.append(SupplierTermIdentity(store_id=term.store_id,term_id=term.id,
                ingredient_id=term.ingredient_id,supplier_id=term.supplier_id,
                version=term.version if request.procurement.offer_admission else None))
            terms.append(value(SupplierTermResult, term, 'supplier_term'))
    for row in ConstraintsRepository(session).list_constraints(request.store_id):
        scoped(row, 'constraint')
        if not row.active:
            continue
        upper = days[0] if row.constraint_type == 'BUDGET_LIMIT' else days[-1]
        if row.effective_from > upper or (row.effective_to is not None and row.effective_to < days[0]):
            continue
        remember(row, 'constraint')
        constraints.append(value(CapturedDecisionConstraint, row, 'constraint', id=row.id, store_id=row.store_id,
            version=row.version, kind=row.constraint_type, ingredient_id=row.scope_id, value=row.numeric_value,
            unit=row.unit, effective_from=row.effective_from, effective_to=row.effective_to))
    forecast_value = None
    repo = ForecastRepository(session)
    run = repo.get_forecast_run(request.store_id, request.forecast_run_id) if request.forecast_run_id is not None else None
    if run is not None:
        scoped(run, 'forecast_run'); remember(run, 'forecast_run')
        predictions = []
        for row in repo.list_predictions(request.store_id, run.id):
            scoped(row, 'forecast_prediction')
            predictions.append(value(ScopedPrediction, row, 'forecast_prediction'))
        retained_row = ForecastInputRepository(session).get_input(request.store_id, run.id)
        retained = digest = None
        if retained_row is not None:
            scoped(retained_row, 'forecast_input'); remember(retained_row, 'forecast_input', run.id)
            try:
                retained = restore_prepared(retained_row.prepared_json, retained_row.serialization_version, retained_row.digest)
            except RetainedInputError as error:
                fail('FORECAST_RETAINED_INTEGRITY_INVALID', 'forecast_run', run.id, 'retained_input', str(error))
            digest = retained_row.digest
        metadata = ForecastExecutionMetadataRepository(session).get(request.store_id, run.id)
        execution = None
        if metadata is not None:
            scoped(metadata, 'forecast_metadata')
            execution = value(ExecutionDetails, metadata, 'forecast_metadata', **metadata.details_json)
        forecast_value = value(ForecastFact, run, 'forecast_run', id=run.id, store_id=run.store_id, status=run.status,
            training_start_date=run.training_start_date, training_end_date=run.training_end_date,
            forecast_start_date=run.forecast_start_date, forecast_end_date=run.forecast_end_date,
            input_fingerprint=run.input_fingerprint, model_type=run.model_type, model_version=run.model_version,
            artifact_key=run.artifact_key, completed_at=run.completed_at, predictions=tuple(p for p in predictions if p is not None),
            retained=retained, retained_digest=digest, execution=execution)
    # Deduplicate timestamps of a supplier reached through several terms.
    clean = lambda rows: tuple(r for r in rows if r is not None)
    return OperationalFactsV2(facts=OperationalFacts(captured_at=captured_at,
        store=store_value,forecast=forecast_value,products=clean(products),ingredients=clean(ingredients),
        recipes=clean(recipes),lots=clean(lots),supplier_terms=clean(terms),constraints=clean(constraints),
        source_times=tuple(sorted(set(times),key=lambda t:(t.entity,t.entity_id,t.kind)))),
        catalog=tuple(menu),ingredient_scope_ids=tuple(ingredient_scope_ids),supplier_term_scope=tuple(term_scope),problems=tuple(problems))
