"""Validate detached operational facts; never read live data during computation."""
from datetime import datetime, timezone
from typing import Callable
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from app.application.contracts.decision_capture import (
    OperationalDecisionInput, OperationalFacts, DecisionCaptureOutcome, CaptureProblem, CapturedForecastProvenance,
)
from app.application.contracts.decision_execution import (
    DecisionExecutionInput, PreparedDecisionInput, CapturedDecisionForecast,
    DecisionForecastPoint, DecisionIssue, AffectedEntity, SourceReference,
)
from app.application.decision_snapshot_source import DecisionSnapshotSource, OperationalDataError
from app.application.forecast_serialization import serialize_prepared
from app.application.use_cases.bom import _canonical_snapshot
from app.domain.forecasting.validation import forecast_dates, validate_output_coverage


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def capture_decision(request: OperationalDecisionInput, source: DecisionSnapshotSource,
                     clock: Callable[[], datetime] = utc_now) -> DecisionCaptureOutcome:
    request = OperationalDecisionInput.model_validate(request)
    problems: list[CaptureProblem] = []
    times = ()
    prepared = None
    provenance = None

    def problem(code, entity, identifier, field, detail, kind='DATA_BLOCKER', day=None):
        problems.append(CaptureProblem(code=code, entity=entity, entity_id=identifier,
            field=field, detail=detail, kind=kind, day=day))

    def result():
        return DecisionCaptureOutcome(status='DATA_BLOCKED' if any(p.kind == 'DATA_BLOCKER' for p in problems)
            else 'CAPTURED', request=request, captured_at=captured_at, prepared=prepared,
            problems=tuple(sorted(problems, key=lambda p: (p.code, p.entity, str(p.entity_id), p.day or request.cutoff_date))),
            source_times=tuple(sorted(times, key=lambda t: (t.entity, t.entity_id, t.kind))),
            forecast_provenance=provenance,
            inventory_time_semantics='CURRENT_BALANCES_OBSERVED_NOT_HISTORICAL_AS_OF', decision_readiness='NOT_ASSESSED')

    try:
        facts = source.read(request, clock)
    except OperationalDataError as error:
        captured_at = error.captured_at
        problems.extend(error.problems)
        return result()
    # Do not catch source transport/programming exceptions as business infeasibility.
    captured_at = facts.captured_at
    try:
        facts = OperationalFacts.model_validate(facts.model_dump())
    except ValidationError as error:
        problem('INVALID_OPERATIONAL_FACT', 'store', request.store_id, 'facts', str(error))
        return result()
    times = facts.source_times
    store, forecast = facts.store, facts.forecast
    if forecast is not None:
        provenance = CapturedForecastProvenance(run_id=forecast.id, status=forecast.status,
            training_start_date=forecast.training_start_date, training_end_date=forecast.training_end_date,
            forecast_start_date=forecast.forecast_start_date, forecast_end_date=forecast.forecast_end_date,
            completed_at=forecast.completed_at, retained_input_digest=forecast.retained_digest,
            prediction_units_source='RETAINED_FORECAST_INPUT_REQUIRED', execution=forecast.execution)
    if store is None or store.id != request.store_id:
        problem('STORE_NOT_FOUND_IN_SCOPE', 'store', request.store_id, 'store_id', 'Requested Store unavailable')
        return result()
    days = forecast_dates(request.cutoff_date)
    try:
        capture_day = captured_at.astimezone(ZoneInfo(store.timezone)).date()
    except (ValueError, OverflowError, KeyError) as error:
        problem('INVALID_STORE_TIMEZONE', 'store', store.id, 'timezone', str(error))
        return result()
    if capture_day != days[0]:
        problem('CURRENT_CAPTURE_DATE_MISMATCH', 'store', store.id, 'captured_at',
                'Current balances cannot be relabelled as historical day-start inventory; capture must be on local D+1')
    for rows, key in ((facts.products, 'product_id'), (facts.ingredients, 'ingredient_id'),
                      (facts.recipes, 'id'), (facts.lots, 'id'), (facts.supplier_terms, 'id'), (facts.constraints, 'id')):
        if len({getattr(r, key) for r in rows}) != len(rows):
            problem('DUPLICATE_SOURCE_IDENTITY', 'store', store.id, key, 'Duplicate source row identity')
        if any(r.store_id != store.id for r in rows):
            problem('CROSS_STORE_SOURCE', 'store', store.id, 'store_id', 'Source row is outside requested Store')
    if {p.product_id for p in facts.products} != set(request.product_ids):
        problem('PRODUCT_SCOPE_MISSING', 'store', store.id, 'product_ids', 'Requested Product scope unavailable in Store')
    if forecast is None or (forecast.store_id, forecast.id) != (store.id, request.forecast_run_id):
        problem('FORECAST_NOT_FOUND_IN_SCOPE', 'store', store.id, 'forecast_run_id', 'ForecastRun unavailable in requested Store')
    elif forecast.status != 'COMPLETED':
        problem('FORECAST_NOT_COMPLETED', 'store', store.id, 'forecast_run_id', 'Explicit forecast must be COMPLETED')
    else:
        if (forecast.training_end_date, forecast.forecast_start_date, forecast.forecast_end_date) != (request.cutoff_date, days[0], days[-1]):
            problem('FORECAST_WINDOW_MISMATCH', 'store', store.id, 'forecast_run_id', 'Forecast origin/horizon differs from request')
        if any((p.store_id, p.forecast_run_id) != (store.id, forecast.id) for p in forecast.predictions):
            problem('CROSS_STORE_PREDICTION', 'store', store.id, 'predictions', 'Prediction Store/run identity mismatch')
        try:
            validate_output_coverage(request.product_ids, request.cutoff_date,
                tuple((p.product_id, p.forecast_date) for p in forecast.predictions))
        except ValueError as error:
            problem('FORECAST_COVERAGE_INVALID', 'store', store.id, 'predictions', str(error))
        retained = forecast.retained
        if retained is None or forecast.retained_digest is None:
            problem('FORECAST_UNIT_PROVENANCE_UNAVAILABLE', 'store', store.id, 'retained_input',
                    'Predictions do not persist units; integrity-verified retained input required, including legacy runs')
        else:
            if (serialize_prepared(retained).digest != forecast.retained_digest or
                    forecast.input_fingerprint != forecast.retained_digest):
                problem('FORECAST_INPUT_INTEGRITY_MISMATCH', 'store', store.id, 'retained_input', 'Retained input digest differs from completed forecast')
            if (retained.request.store_id, retained.request.product_ids, retained.request.cutoff_date,
                    retained.request.history_start_date) != (store.id, request.product_ids, request.cutoff_date, forecast.training_start_date):
                problem('FORECAST_RETAINED_SCOPE_MISMATCH', 'store', store.id, 'retained_input', 'Retained origin/history/Product scope differs')
            units = {p.product_id: p.selling_unit for p in retained.products}
            if any(units.get(p.product_id) != p.selling_unit for p in facts.products):
                problem('FORECAST_PRODUCT_UNIT_DRIFT', 'store', store.id, 'selling_unit', 'Current Product unit differs from retained forecast unit; no conversion inferred')
        if forecast.completed_at is None or not forecast.input_fingerprint:
            problem('FORECAST_PROVENANCE_MISSING', 'store', store.id, 'forecast_run_id', 'Completed forecast lacks required provenance')
        elif forecast.completed_at > captured_at:
            problem('FORECAST_COMPLETION_AFTER_CAPTURE', 'store', store.id, 'completed_at', 'Forecast completion cannot be after the capture observation marker')
        if retained is not None and retained.timezone != store.timezone:
            problem('FORECAST_TIMEZONE_DRIFT', 'store', store.id, 'timezone', 'Current timezone differs from the retained forecast local-date context')
        if forecast.model_type != 'historical_quantile_baseline' and forecast.execution is None:
            problem('FORECAST_METADATA_MISSING', 'store', store.id, 'execution', 'Non-baseline run requires captured execution metadata/warnings')
        if forecast.execution and any(w.severity == 'ERROR' for w in forecast.execution.warnings):
            problem('FORECAST_ERROR_WARNING', 'store', store.id, 'warnings', 'Forecast source includes ERROR warnings; decision capture blocked')
    ingredient_ids = {i.ingredient_id for i in facts.ingredients}
    declarations = {d.ingredient_id: d for d in request.inventory_scope}
    if set(declarations) != ingredient_ids:
        problem('INVENTORY_SCOPE_UNCONFIRMED', 'store', store.id, 'inventory_scope', 'Declare inventory completeness for exactly all captured Store Ingredients')
    for ingredient in sorted(ingredient_ids & set(declarations)):
        declaration = declarations[ingredient]
        lots = [l for l in facts.lots if l.ingredient_id == ingredient]
        if declaration.state == 'UNKNOWN' or (not lots and declaration.state != 'CONFIRMED_EMPTY'):
            problem('INVENTORY_BALANCE_MISSING', 'ingredient', ingredient, 'on_hand_quantity', 'Missing lot rows are not zero; confirmed-empty declaration required')
        if lots and declaration.state == 'CONFIRMED_EMPTY':
            problem('INVENTORY_DECLARATION_CONFLICT', 'ingredient', ingredient, 'inventory_scope', 'Confirmed-empty declaration conflicts with existing lot rows, including explicit zero')
    if request.committed_inbound_state != 'CONFIRMED_NONE':
        problem('COMMITTED_INBOUND_UNSUPPORTED', 'store', store.id, 'committed_inbound', 'No canonical committed-inbound source or supported engine semantics; never reinterpret as stock/arrival')
    config = request.procurement
    if config.capacity_state == 'UNKNOWN' or config.supplier_limit_state == 'UNKNOWN':
        problem('LIMIT_CONFIGURATION_UNKNOWN', 'store', store.id, 'procurement', 'Unknown constraints cannot become unconfigured/unconstrained')
    budgets = [c for c in facts.constraints if c.kind == 'BUDGET_LIMIT']
    if not budgets and config.budget is None:
        problem('BUDGET_SOURCE_MISSING', 'store', store.id, 'budget', 'No effective DB budget and no explicit budget declaration')
    if len(budgets) > 1:
        problem('BUDGET_OVERLAP', 'store', store.id, 'constraints', 'Multiple effective budget rows')
    elif budgets and config.budget and (config.budget.state != 'KNOWN' or config.budget.amount != budgets[0].value or config.budget.currency != store.currency):
        problem('BUDGET_SOURCE_CONFLICT', 'store', store.id, 'budget', 'Explicit budget cannot override captured DB budget')
    for product in request.product_ids:
        for day in days:
            recipes = [r for r in facts.recipes if r.product_id == product and r.effective_from <= day and (r.effective_to is None or day <= r.effective_to)]
            if len(recipes) > 1:
                problem('RECIPE_OVERLAP', 'product', product, 'recipe', 'Overlapping effective recipes', day=day)
            elif not recipes or not recipes[0].lines:
                problem('MISSING_RECIPE', 'product', product, 'recipe', 'Missing or empty recipe; zero demand does not bypass recipe policy', day=day)
    term_keys = [(t.supplier_id, t.ingredient_id) for t in facts.supplier_terms]
    if len(set(term_keys)) != len(term_keys):
        problem('SUPPLIER_TERM_OVERLAP', 'store', store.id, 'supplier_terms',
                'Multiple effective terms for one Supplier/Ingredient pair; no implicit offer-version selection')
    for lot in facts.lots:
        ingredient = next((i for i in facts.ingredients if i.ingredient_id == lot.ingredient_id), None)
        if lot.received_date is not None and lot.received_date > capture_day:
            problem('FUTURE_RECEIPT_NOT_INBOUND', 'inventory_lot', lot.id, 'received_date', 'Future operational lot excluded by serving; not committed inbound', kind='WARNING')
        elif lot.on_hand_quantity > 0:
            if ingredient and ingredient.expiry_tracking and lot.expiry_date is None:
                problem('MISSING_EXPIRY', 'inventory_lot', lot.id, 'expiry_date', 'Positive tracked stock requires expiry')
            if lot.received_date is None:
                problem('MISSING_RECEIVED_DATE', 'inventory_lot', lot.id, 'received_date', 'Inventory age unknown; date not backfilled', kind='WARNING')
            if lot.unit_cost is None:
                problem('MISSING_COST', 'inventory_lot', lot.id, 'unit_cost', 'Inventory value unknown', kind='WARNING')
        if lot.expiry_date is not None and lot.expiry_date < capture_day:
            problem('EXPIRED_OPERATIONAL_LOT', 'inventory_lot', lot.id, 'expiry_date', 'Captured expired stock remains in audit; serving excludes it', kind='WARNING')
    if any(p.kind == 'DATA_BLOCKER' for p in problems):
        return result()
    references = [SourceReference(entity='store', entity_id=store.id, origin='SOURCE_EXPLICIT'),
                  SourceReference(entity='forecast_run', entity_id=forecast.id, origin='SOURCE_EXPLICIT')]
    for rows, entity, key in ((facts.products, 'product', 'product_id'), (facts.ingredients, 'ingredient', 'ingredient_id'),
                              (facts.recipes, 'recipe', 'id'), (facts.lots, 'inventory_lot', 'id'),
                              (facts.supplier_terms, 'supplier_term', 'id'), (facts.constraints, 'constraint', 'id')):
        references.extend(SourceReference(entity=entity, entity_id=getattr(r, key), version=getattr(r, 'version', None), origin='SOURCE_EXPLICIT') for r in rows)
    try:
        prepared = _canonical_snapshot(PreparedDecisionInput(request=DecisionExecutionInput(
            store_id=store.id, forecast_run_id=forecast.id, product_ids=request.product_ids,
            cutoff_date=request.cutoff_date, order_at=captured_at), timezone=store.timezone,
            currency=store.currency, inventory_as_of=captured_at,
            forecast=CapturedDecisionForecast(store_id=store.id, run_id=forecast.id, cutoff_date=request.cutoff_date,
                input_fingerprint=forecast.input_fingerprint, model_type=forecast.model_type, model_version=forecast.model_version,
                artifact_identity=forecast.artifact_key, predictions=tuple(DecisionForecastPoint(
                    **p.model_dump(exclude={'id','store_id','forecast_run_id'}), unit=units[p.product_id]) for p in forecast.predictions),
                warnings=forecast.execution.warnings if forecast.execution else ()),
            products=facts.products, ingredients=facts.ingredients, recipes=facts.recipes, lots=facts.lots,
            supplier_terms=facts.supplier_terms, constraints=facts.constraints, policy=request.snapshot_policy,
            issues=tuple(DecisionIssue(code=p.code, kind=p.kind, field=p.field,
                affected=(AffectedEntity(entity=p.entity, entity_id=p.entity_id),), impact=p.detail,
                suggested_action='Review captured source/declaration; do not fabricate missing facts') for p in problems),
            assumptions=('DAY_START_CAPTURE','COMPLETE_INVENTORY_SCOPE','NO_ADDITIONAL_ORDERS',
                'CURRENT_BALANCES_NOT_HISTORICAL_AS_OF', 'DAY_START_ATTESTATION:' + request.day_start_provenance,
                'NO_ADDITIONAL_ORDERS_ATTESTATION:' + request.no_additional_orders_provenance),
            source_references=tuple(references)))
    except ValidationError as error:
        problem('SNAPSHOT_SEMANTICS_INVALID', 'store', store.id, 'prepared', str(error))
    return result()
