"""Deterministic /2 preparation and reconciliation from retained detached facts."""
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo
from pydantic import ValidationError
from app.application.contracts.decision_capture import CaptureProblem, CapturedForecastProvenance
from app.application.contracts.decision_execution import (
    PreparedDecisionInput, DecisionExecutionInput, CapturedDecisionForecast,
    DecisionForecastPoint, DecisionIssue, AffectedEntity, SourceReference,
)
from app.application.contracts.decision_temporal import OperationalBasis
from app.application.contracts.decision_capture_v2 import ProductExclusion, OverrideAssessment
from app.application.contracts.procurement_v2 import ProcurementInputV2, EffectiveRequirements, PathRequirement
from app.application.forecast_serialization import serialize_prepared
from app.application.use_cases.bom import _canonical_snapshot
from app.domain.forecasting.validation import forecast_dates, validate_output_coverage


def project_capture_v2(request, wrapped):
    """Returns value-only derived fields. Never reads sources/DB or calls engines."""
    facts=wrapped.facts; store=facts.store; forecast=facts.forecast
    days=forecast_dates(request.cutoff_date)
    problems=list(wrapped.problems); global_problems=[]; local={}
    menu=tuple(sorted((p for p in wrapped.catalog if p.active),key=lambda p:p.product_id))
    menu_ids={p.product_id for p in menu}
    products={p.product_id:p for p in facts.products}; ingredients={i.ingredient_id:i for i in facts.ingredients}
    scoped_ingredients=set(wrapped.ingredient_scope_ids)
    term_scope={t.term_id:t for t in wrapped.supplier_term_scope}
    admission=request.procurement.offer_admission
    omitted={o.term_id:o for o in admission.omissions} if admission else {}

    def problem(code,entity,identifier,field,detail,day=None,kind='DATA_BLOCKER'):
        p=CaptureProblem(code=code,kind=kind,entity=entity,entity_id=identifier,field=field,detail=detail,day=day)
        problems.append(p)
        return p
    def block(code,detail):
        global_problems.append(problem(code,'store',request.store_id,'capture',detail))
    def exclude(product,p):
        local.setdefault(product,[]).append(p)
    def product_problem(product,code,detail,day=None):
        exclude(product,problem(code,'product',product,'product',detail,day))

    if store is None or store.id!=request.store_id:
        block('STORE_NOT_FOUND_IN_SCOPE','Store unavailable')
    for rows,key in ((wrapped.catalog,'product_id'),(facts.products,'product_id'),(facts.ingredients,'ingredient_id'),
                     (facts.recipes,'id'),(facts.lots,'id'),(facts.supplier_terms,'id'),(facts.constraints,'id')):
        if len({getattr(r,key) for r in rows})!=len(rows):block('DUPLICATE_SOURCE_IDENTITY','Duplicate source identity')
        if any(r.store_id!=request.store_id for r in rows):block('CROSS_STORE_SOURCE','Captured row outside Store')
    if not set(products)<=menu_ids:block('PRODUCT_SCOPE_UNKNOWN','Product facts outside active captured menu')
    if len(scoped_ingredients)!=len(wrapped.ingredient_scope_ids) or not set(ingredients)<=scoped_ingredients:
        block('INGREDIENT_SCOPE_UNKNOWN','Ingredient scope identities invalid')
    if len(term_scope)!=len(wrapped.supplier_term_scope) or any(t.store_id!=request.store_id or t.ingredient_id not in scoped_ingredients for t in term_scope.values()):
        block('TERM_SCOPE_UNKNOWN','Supplier term identity scope invalid')
    for term in facts.supplier_terms:
        identity=term_scope.get(term.id)
        if identity is None or (identity.store_id,identity.ingredient_id,identity.supplier_id)!=(term.store_id,term.ingredient_id,term.supplier_id):
            block('TERM_SCOPE_UNKNOWN','Supplier term DTO/identity disagree')
        elif admission and identity.version!=term.version:
            block('TERM_SCOPE_UNKNOWN','Supplier term version differs from captured identity')
    typed_terms={t.id:t for t in facts.supplier_terms}
    for identifier,o in omitted.items():
        identity=term_scope.get(identifier);term=typed_terms.get(identifier)
        if (identity is None or o.store_id!=request.store_id or identity.version!=o.version
                or (o.supplier_id,o.ingredient_id)!=(identity.supplier_id,identity.ingredient_id)
                or not o.effective_from<=days[0] or (o.effective_to is not None and days[0]>o.effective_to)
                or any(x.term_id==identifier for x in request.procurement.offers)):
            block('OFFER_OMISSION_INVALID','Omission identity/version/effectivity conflicts with captured source or eligible offers')
        elif o.reason=='OFFER_BOUND_UNKNOWN' and (term is None or term.pack_cost!=0
                or (term.version,term.effective_from,term.effective_to)!=(o.version,o.effective_from,o.effective_to)
                or any((l.supplier_id,l.ingredient_id)==(o.supplier_id,o.ingredient_id) for l in request.procurement.supplier_limits)):
            block('OFFER_OMISSION_INVALID','Omitted unbounded offer has known finite facts or mismatched term')
        elif o.reason=='SUPPLIER_TERM_FACT_UNAVAILABLE' and term is not None and not (
                o.missing_fields==('shelf_life_days',) and term.shelf_life_days is None
                and ingredients.get(o.ingredient_id) and ingredients[o.ingredient_id].expiry_tracking
                and (term.version,term.effective_from,term.effective_to)==(o.version,o.effective_from,o.effective_to)):
            block('OFFER_OMISSION_INVALID','Missing-fact omission contradicts captured typed term or consumer')
        else:
            problem('OFFER_OMITTED','supplier_term',identifier,'supplier_term',
                f'{o.reason}; {o.source_reference}; eligible-domain proof only, not market infeasibility',kind='WARNING')
    for identifier in set(term_scope)-{t.id for t in facts.supplier_terms}:
        if identifier not in omitted:
            problem('SUPPLIER_TERM_FACT_UNAVAILABLE','ingredient',term_scope[identifier].ingredient_id,'supplier_term','Scoped term identity exists but its numeric fact is unavailable')
    for identifier in scoped_ingredients-set(ingredients):
        problem('INGREDIENT_FACT_UNAVAILABLE','ingredient',identifier,'ingredient','Scoped Ingredient identity exists but its typed fact is unavailable')
    if any(o.product_id not in menu_ids for p in request.requirements.paths for o in p.overrides):
        raise ValueError('Unknown/cross-Store/inactive customer override; invalid input, not exclusion')
    basis=None; provenance=None
    if store:
        try:
            zone=ZoneInfo(store.timezone);local_day=facts.captured_at.astimezone(zone).date()
            hypothetical=local_day!=days[0]
            assumptions=('CURRENT_BALANCES_NOT_HISTORICAL_AS_OF','NO_INTERVENING_STOCK_EVOLUTION',
                         'ORIGINAL_RECEIPT_EXPIRY_DATES','NO_ADDITIONAL_ORDERS')
            basis=OperationalBasis(version='operational_basis/1',kind='HYPOTHETICAL_CURRENT_CAPTURE' if hypothetical else 'CURRENT_CAPTURE',
                captured_at=facts.captured_at,timezone=store.timezone,local_capture_date=local_day,
                planning_start_date=days[0],assumptions=assumptions)
            if hypothetical:
                problem('NONCURRENT_PLANNING_CURRENT_FACTS','store',store.id,'planning_start_date',
                    'Current captured balances/prices/dated recipes are hypothetical; not historical inventory or a forecast of intervening stock',kind='WARNING')
        except (ValueError,KeyError,OverflowError) as error:
            block('INVALID_STORE_TIMEZONE',str(error))
    if forecast:
        provenance=CapturedForecastProvenance(run_id=forecast.id,status=forecast.status,
            training_start_date=forecast.training_start_date,training_end_date=forecast.training_end_date,
            forecast_start_date=forecast.forecast_start_date,forecast_end_date=forecast.forecast_end_date,
            completed_at=forecast.completed_at,retained_input_digest=forecast.retained_digest,
            prediction_units_source='RETAINED_FORECAST_INPUT_REQUIRED',execution=forecast.execution)
    if request.forecast_run_id is None:
        if forecast is not None: block('FORECAST_IDENTITY_CONFLICT','No-forecast capture contains a forecast')
        for p in menu:
            product_problem(p.product_id,'PRODUCT_HISTORY_MISSING','No observed history through cutoff; no forecast fabricated')
    elif forecast is None or (forecast.store_id,forecast.id)!=(request.store_id,request.forecast_run_id):
        block('FORECAST_NOT_FOUND_IN_SCOPE','Referenced forecast unavailable in Store')
    elif forecast.status!='COMPLETED':
        block('FORECAST_NOT_COMPLETED','Referenced forecast is not COMPLETED')
    else:
        if (forecast.training_end_date,forecast.forecast_start_date,forecast.forecast_end_date)!=(request.cutoff_date,days[0],days[-1]):
            block('FORECAST_WINDOW_MISMATCH','Forecast cutoff/window differs')
        if forecast.completed_at is None or forecast.completed_at>facts.captured_at:
            block('FORECAST_PROVENANCE_MISSING','Missing completion marker or completion after capture')
        retained=forecast.retained
        if retained is None or forecast.retained_digest is None:
            block('FORECAST_UNIT_PROVENANCE_UNAVAILABLE','Integrity-verified retained input required')
        else:
            if serialize_prepared(retained).digest!=forecast.retained_digest or forecast.input_fingerprint!=forecast.retained_digest:
                block('FORECAST_INPUT_INTEGRITY_MISMATCH','Retained digest/run fingerprint differs')
            if (retained.request.store_id,retained.request.cutoff_date,retained.request.history_start_date)!=(request.store_id,request.cutoff_date,forecast.training_start_date):
                block('FORECAST_RETAINED_SCOPE_MISMATCH','Retained Store/origin/history differs')
            if store and retained.timezone!=store.timezone:block('FORECAST_TIMEZONE_DRIFT','Retained timezone differs')
            units={p.product_id:p.selling_unit for p in retained.products}
            for p in menu:
                points=[r for r in forecast.predictions if r.product_id==p.product_id]
                if p.product_id not in units:
                    product_problem(p.product_id,'FORECAST_UNAVAILABLE','No captured forecast for active Product')
                else:
                    try:validate_output_coverage((p.product_id,),request.cutoff_date,tuple((r.product_id,r.forecast_date) for r in points))
                    except ValueError as error:product_problem(p.product_id,'FORECAST_COVERAGE_INVALID',str(error))
                    if units[p.product_id]!=p.selling_unit:
                        product_problem(p.product_id,'FORECAST_PRODUCT_UNIT_DRIFT','Captured selling unit differs from forecast')
            if any((p.store_id,p.forecast_run_id)!=(request.store_id,forecast.id) or p.product_id not in units for p in forecast.predictions):
                block('CROSS_STORE_PREDICTION','Prediction outside referenced forecast/retained Product scope')
        if forecast.model_type!='historical_quantile_baseline' and forecast.execution is None:
            block('FORECAST_METADATA_MISSING','Non-baseline metadata unavailable')
        if forecast.execution:
            for w in forecast.execution.warnings:
                if w.severity=='ERROR':
                    if w.product_id in menu_ids:product_problem(w.product_id,'FORECAST_ERROR_WARNING',w.impact)
                    else:block('FORECAST_ERROR_WARNING',w.impact)

    dependencies={p:set() for p in menu_ids}
    for p in menu:
        if p.product_id not in products:product_problem(p.product_id,'PRODUCT_FACT_UNAVAILABLE','Active Product fact unavailable')
        elif products[p.product_id].selling_unit!=p.selling_unit:
            product_problem(p.product_id,'PRODUCT_UNIT_DRIFT','Menu and Product selling unit disagree')
        for day in days:
            matches=[r for r in facts.recipes if r.product_id==p.product_id and r.effective_from<=day and (r.effective_to is None or day<=r.effective_to)]
            if len(matches)!=1 or not matches[0].lines:
                product_problem(p.product_id,'RECIPE_OVERLAP' if len(matches)>1 else 'MISSING_RECIPE','Need exactly one nonempty effective recipe',day)
            for r in matches:
                for line in r.lines:
                    if admission and line.ingredient_id not in scoped_ingredients:
                        block('SOURCE_FAILURE_SCOPE_UNKNOWN','Recipe references Ingredient outside captured identity scope')
                    dependencies[p.product_id].add(line.ingredient_id)
                    i=ingredients.get(line.ingredient_id)
                    if i is None or i.unit!=line.unit:
                        product_problem(p.product_id,'RECIPE_INGREDIENT_UNIT_INVALID','Recipe Ingredient reference/unit invalid',day)
    if any(r.product_id not in menu_ids for r in facts.recipes):block('RECIPE_SCOPE_UNKNOWN','Recipe outside captured active menu')
    if admission:
        relevant=set().union(*dependencies.values()) if dependencies else set()
        offered={o.term_id for o in request.procurement.offers}
        if any(t.ingredient_id in relevant and t.id not in offered and t.id not in omitted for t in facts.supplier_terms):
            block('OFFER_ADMISSION_INCOMPLETE','Scoped valid offer omitted without versioned admission evidence')
    declarations={d.ingredient_id:d for d in request.inventory_scope}
    for identifier in ingredients:
        d=declarations.get(identifier);lots=[l for l in facts.lots if l.ingredient_id==identifier]
        if d is None or d.state=='UNKNOWN' or (not lots and d.state!='CONFIRMED_EMPTY'):
            problem('INVENTORY_BALANCE_MISSING','ingredient',identifier,'inventory_scope','Inventory missing is not zero; completeness required')
        elif any(l.on_hand_quantity > 0 for l in lots) and d.state=='CONFIRMED_EMPTY':
            problem('INVENTORY_DECLARATION_CONFLICT','ingredient',identifier,'inventory_scope','Confirmed-empty conflicts with positive captured stock')
    if not set(declarations)<=scoped_ingredients:block('INVENTORY_DECLARATION_SCOPE_INVALID','Declaration outside Store Ingredient scope')
    for rows,entity in ((facts.lots,'inventory_lot'),(facts.supplier_terms,'supplier_term')):
        for row in rows:
            i=ingredients.get(row.ingredient_id)
            if i is None:
                if row.ingredient_id not in scoped_ingredients:block('INGREDIENT_SCOPE_UNKNOWN','Operational row references unknown Ingredient')
            elif row.unit!=i.unit:problem('INGREDIENT_UNIT_MISMATCH','ingredient',i.ingredient_id,'unit',entity+' unit differs')
    if basis:
        for lot in facts.lots:
            i=ingredients.get(lot.ingredient_id)
            if lot.received_date is not None and lot.received_date>basis.local_capture_date:
                problem('FUTURE_RECEIPT_NOT_INBOUND','inventory_lot',lot.id,'received_date','Future operational lot excluded; not an inbound declaration',kind='WARNING')
            elif lot.on_hand_quantity>0:
                if i and i.expiry_tracking and lot.expiry_date is None:
                    problem('MISSING_EXPIRY','ingredient',lot.ingredient_id,'expiry_date','Positive tracked stock requires expiry')
                for attr,code in (('received_date','MISSING_RECEIVED_DATE'),('unit_cost','MISSING_COST')):
                    if getattr(lot,attr) is None:problem(code,'inventory_lot',lot.id,attr,'Captured fact unknown; not invented',kind='WARNING')
    term_keys=[(t.supplier_id,t.ingredient_id) for t in facts.supplier_terms]
    if len(set(term_keys))!=len(term_keys):block('SUPPLIER_TERM_OVERLAP','Ambiguous effective supplier terms')
    config=request.procurement
    for rows,key in ((config.offers,lambda o:o.term_id),(config.supplier_fees,lambda f:f.supplier_id),
                     (config.capacities,lambda c:c.ingredient_id),(config.supplier_limits,lambda c:(c.supplier_id,c.ingredient_id))):
        if len({key(r) for r in rows})!=len(rows):block('DUPLICATE_CONFIGURATION_IDENTITY','Duplicate caller declaration; do not filter duplicates away')
    # Validate original declarations before projecting excluded dependencies.
    # Otherwise filtering could silently discard a foreign/stale caller input.
    term_ids=set(term_scope)
    suppliers={t.supplier_id for t in term_scope.values()}
    if config.policy.fee_mode=='NONE' and (any(o.payable_fee not in (None,0) for o in config.offers) or any(f.amount not in (None,0) for f in config.supplier_fees)):
        block('PAYABLE_FEE_DECLARATION_CONFLICT','NONE fee mode contradicts positive declared fees')
    if any(o.term_id not in term_ids for o in config.offers):
        block('OFFER_SCOPE_INVALID','Offer is not a captured effective Store supplier term')
    if any(f.supplier_id not in suppliers for f in config.supplier_fees):
        block('SUPPLIER_FEE_SCOPE_INVALID','Fee supplier is outside captured terms')
    for c in (*config.capacities,*config.supplier_limits):
        if c.store_id!=request.store_id or c.ingredient_id not in scoped_ingredients or (c.ingredient_id in ingredients and c.unit!=ingredients[c.ingredient_id].unit):
            block('DECLARED_CONSTRAINT_SCOPE_INVALID','Declared constraint Store/Ingredient/unit invalid')
        elif hasattr(c,'supplier_id') and not any(t.supplier_id==c.supplier_id and t.ingredient_id==c.ingredient_id for t in term_scope.values()):
            block('DECLARED_CONSTRAINT_SCOPE_INVALID','Supplier limit pair unavailable')
    if request.committed_inbound_state!='CONFIRMED_NONE':block('COMMITTED_INBOUND_UNSUPPORTED','Unknown/present committed inbound cannot be ignored')
    if config.budget.state!='KNOWN' or config.budget_ceiling.state!='KNOWN':
        block('BUDGET_CEILING_UNKNOWN','Explicit known effective budget and ceiling required')
    elif config.budget.amount>config.budget_ceiling.amount:
        block('BUDGET_LIMIT_EXCEEDS_CEILING','Effective budget exceeds explicit frozen Store ceiling')
    if store and (config.budget.currency!=store.currency or config.budget_ceiling.currency!=store.currency):
        block('BUDGET_CURRENCY_CONFLICT','Explicit budget/ceiling currency differs from Store')
    if config.payable_fee_coverage!='COMPLETE':block('PAYABLE_FEE_COVERAGE_UNKNOWN','Full payable fee coverage declaration required')
    if config.capacity_state=='UNKNOWN' or config.supplier_limit_state=='UNKNOWN':block('LIMIT_CONFIGURATION_UNKNOWN','Unknown is not unconfigured')
    budgets=[c for c in facts.constraints if c.kind=='BUDGET_LIMIT']
    if len(budgets)>1:block('BUDGET_OVERLAP','Multiple operational budgets')
    if budgets and (config.budget_ceiling.amount!=budgets[0].value or config.budget_ceiling.currency!=budgets[0].unit):
        block('BUDGET_SOURCE_CONFLICT','Explicit frozen ceiling conflicts with operational constraint; no clamp/change')

    # Dependency classification is conservative: unknown object attribution blocks
    # the whole capture. Known Ingredient issues affect every dependent Product.
    for p in tuple(problems):
        if p.kind!='DATA_BLOCKER' or p in global_problems:continue
        if p.entity=='product' and p.entity_id in menu_ids:exclude(p.entity_id,p)
        elif p.entity=='ingredient' and p.entity_id in scoped_ingredients:
            for product,ids in dependencies.items():
                if p.entity_id in ids:exclude(product,p)
        else:
            if p not in global_problems:global_problems.append(p)
    excluded=tuple(ProductExclusion(product_id=p,reasons=tuple(sorted(set(rs),key=lambda r:(r.code,r.day or days[0],r.field,r.detail))),
        affected_dates=tuple(sorted({r.day for r in rs if r.day is not None}))) for p,rs in sorted(local.items()))
    computed=tuple(sorted(menu_ids-set(local)))
    prepared=envelope=None
    if not global_problems and computed and basis:
        needed=set().union(*(dependencies[p] for p in computed))
        kept_ingredients=tuple(i for i in facts.ingredients if i.ingredient_id in needed)
        kept_lots=tuple(l for l in facts.lots if l.ingredient_id in needed)
        eligible_ids={o.term_id for o in config.offers}
        kept_terms=tuple(t for t in facts.supplier_terms if t.ingredient_id in needed
            and (admission is None or (t.id in eligible_ids and t.id not in omitted)))
        kept_recipes=tuple(r for r in facts.recipes if r.product_id in computed)
        kept_constraints=tuple(c for c in facts.constraints if c.ingredient_id is None or c.ingredient_id in needed)
        ids={'store':{request.store_id},'product':set(computed),'ingredient':needed,
             'inventory_lot':{r.id for r in kept_lots},'supplier_term':{r.id for r in kept_terms},'constraint':{r.id for r in kept_constraints}}
        references=[SourceReference(entity='store',entity_id=request.store_id,origin='SOURCE_EXPLICIT'),SourceReference(entity='forecast_run',entity_id=forecast.id,origin='SOURCE_EXPLICIT')]
        for rows,entity,key in ((tuple(products[p] for p in computed),'product','product_id'),(kept_ingredients,'ingredient','ingredient_id'),(kept_recipes,'recipe','id'),(kept_lots,'inventory_lot','id'),(kept_terms,'supplier_term','id'),(kept_constraints,'constraint','id')):
            references.extend(SourceReference(entity=entity,entity_id=getattr(r,key),version=getattr(r,'version',None),origin='SOURCE_EXPLICIT') for r in rows)
        issues=tuple(DecisionIssue(code=p.code,kind=p.kind,field=p.field,affected=(AffectedEntity(entity=p.entity,entity_id=p.entity_id),),impact=p.detail,suggested_action='Review captured facts; no invented facts') for p in problems if p.kind=='WARNING' and p.entity in ids and p.entity_id in ids[p.entity])
        order_at=(facts.captured_at if basis.kind=='CURRENT_CAPTURE' else datetime.combine(days[0],time.min,tzinfo=ZoneInfo(store.timezone)).astimezone(timezone.utc))
        assumptions=tuple(dict.fromkeys((*basis.assumptions,'COMPLETE_INVENTORY_SCOPE','NO_ADDITIONAL_ORDERS_ATTESTATION:'+request.no_additional_orders_provenance)))
        try:
            prepared=_canonical_snapshot(PreparedDecisionInput(capture_version=2,operational_basis=basis,request=DecisionExecutionInput(store_id=store.id,forecast_run_id=forecast.id,product_ids=computed,cutoff_date=request.cutoff_date,order_at=order_at),timezone=store.timezone,currency=store.currency,inventory_as_of=facts.captured_at,
                forecast=CapturedDecisionForecast(store_id=store.id,run_id=forecast.id,cutoff_date=request.cutoff_date,input_fingerprint=forecast.input_fingerprint,model_type=forecast.model_type,model_version=forecast.model_version,artifact_identity=forecast.artifact_key,predictions=tuple(DecisionForecastPoint(**p.model_dump(exclude={'id','store_id','forecast_run_id'}),unit=products[p.product_id].selling_unit) for p in forecast.predictions if p.product_id in computed),warnings=forecast.execution.warnings if forecast.execution else ()),products=tuple(products[p] for p in computed),ingredients=kept_ingredients,recipes=kept_recipes,lots=kept_lots,supplier_terms=kept_terms,constraints=kept_constraints,policy=request.snapshot_policy,issues=issues,assumptions=assumptions,source_references=tuple(references)))
            requirements=EffectiveRequirements(paths=tuple(PathRequirement(path=p.path,minimum=p.minimum,overrides=tuple(o for o in p.overrides if o.product_id in computed)) for p in request.requirements.paths),provenance=request.requirements.provenance)
            offers=tuple(o for o in config.offers if o.term_id in {t.id for t in kept_terms})
            # Reject foreign/stale declarations, including ones unrelated to the
            # projected scope. Dropping only locally excluded dependencies is explicit.
            envelope=ProcurementInputV2(prepared=prepared,policy=config.policy,requirements=requirements,offers=offers,budget=config.budget,supplier_fees=tuple(f for f in config.supplier_fees if f.supplier_id in {t.supplier_id for t in kept_terms if t.id in {o.term_id for o in offers}}),capacities=tuple(c for c in config.capacities if c.ingredient_id in needed),supplier_limits=tuple(c for c in config.supplier_limits if c.ingredient_id in needed and (admission is None or any((t.supplier_id,t.ingredient_id)==(c.supplier_id,c.ingredient_id) for t in kept_terms))),arrivals=(),unsupported_configured_constraints=(),source_references=tuple(r for r in prepared.source_references if r.entity!='recipe'))
        except ValidationError as error:
            block('SNAPSHOT_CONFIGURATION_INVALID',str(error));prepared=envelope=None
    status='DATA_BLOCKED' if global_problems else ('CAPTURED' if computed else 'NO_COMPUTABLE_PRODUCTS')
    return dict(operational_basis=basis,menu=menu,computed_product_ids=computed,exclusions=excluded,
        override_assessments=tuple(OverrideAssessment(product_id=o.product_id,path=p.path,status='COMPUTED_SCOPE' if o.product_id in computed else 'NOT_EVALUATED') for p in request.requirements.paths for o in p.overrides),prepared=prepared,procurement_input=envelope,problems=tuple(sorted(set(problems),key=lambda p:(p.code,p.entity,str(p.entity_id),p.day or days[0],p.field,p.detail))),forecast_provenance=provenance,status=status)


def validate_capture_v2(result):
    if result.source is None:
        if (result.status!='DATA_BLOCKED' or result.prepared is not None or result.procurement_input is not None
                or not any(p.kind=='DATA_BLOCKER' for p in result.problems) or result.menu or result.computed_product_ids
                or result.exclusions or result.override_assessments or result.operational_basis is not None
                or result.forecast_provenance is not None):
            raise ValueError('Failed source cannot produce captured computation')
        return
    if result.captured_at!=result.source.facts.captured_at:
        raise ValueError('Capture observation instant changed')
    expected=project_capture_v2(result.request,result.source)
    if any(getattr(result,k)!=v for k,v in expected.items()):
        raise ValueError('Capture /2 projection, exclusions, provenance or prepared values changed')
