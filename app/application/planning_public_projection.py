"""Condensed PLAN9 presentation of verified retained facts; no live queries."""
from fractions import Fraction
from datetime import date,timedelta
from math import ceil
from app.application.contracts import planning_public as dto
from app.application.contracts.planning_setup import StoredRequirements,StoredPath,ProductOverride
from app.application.planning_serialization import digest
from app.domain.decision.quantities import display
from app.domain.decision.procurement_policy import service_summary

PUBLIC_CODES={'MISSING_RECIPE':'RECIPE_MISSING','RECIPE_INGREDIENT_UNIT_INVALID':'RECIPE_UNIT_MISMATCH',
    'PIPELINE_EXECUTION_ERROR':'EXECUTION_ERROR',
    'FORECAST_UNAVAILABLE':'PRODUCT_HISTORY_MISSING','FORECAST_COVERAGE_INVALID':'FORECAST_PRODUCT_INVALID',
    'FORECAST_PRODUCT_UNIT_DRIFT':'FORECAST_PRODUCT_INVALID','INVENTORY_BALANCE_MISSING':'INVENTORY_UNKNOWN',
    'MISSING_EXPIRY':'REQUIRED_EXPIRY_MISSING','MISSING_RECEIVED_DATE':'RECEIPT_DATE_UNKNOWN','MISSING_COST':'INVENTORY_COST_UNKNOWN',
    'PAYABLE_FEE_COVERAGE_UNKNOWN':'PAYABLE_FEE_UNKNOWN','LIMIT_CONFIGURATION_UNKNOWN':'CONSTRAINT_CONFIGURATION_UNKNOWN'}


def plain(value):
    text=format(value,'f')
    return text.rstrip('0').rstrip('.') if '.' in text else text


def fraction(value):
    if isinstance(value,Fraction):return value
    return Fraction(int(value.numerator),int(value.denominator))


def quantity(value):
    f=fraction(value)
    return dto.ExactQuantity(numerator=str(f.numerator),denominator=str(f.denominator),decimal_view=plain(display(f)))


def percent(value):return plain(display(Fraction(value)*100))


def notice(code,field=None,entity=None,entity_id=None,dates=None):
    code=PUBLIC_CODES.get(code,code)
    return dto.PlanningNotification(code=code,message=code.replace('_',' ').capitalize()+'.',
        details=dto.PlanningNotificationDetails(field=field,entity=entity,entity_id=entity_id,affected_dates=dates))


def capture_warning(record,problem):
    admission=record.declarations.offer_admission if record.declarations else None
    omitted=next((o for o in admission.omissions if o.term_id==problem.entity_id),None) if admission else None
    if problem.code!='OFFER_OMITTED' or omitted is None:
        return notice(problem.code,problem.field,problem.entity,problem.entity_id,(problem.day,) if problem.day else None)
    return dto.PlanningNotification(code='OFFER_OMITTED',
        message='Offer excluded from this Run; results and proofs cover only captured eligible offers.',
        details=dto.PlanningNotificationDetails(field='supplier_term',entity='supplier_term',entity_id=omitted.term_id,
            ingredient_ids=(omitted.ingredient_id,),classification=omitted.reason,proof_scope=admission.proof_scope,
            source_reference=omitted.source_reference,source_version=omitted.version,
            suggested_action='Provide the missing offer facts or finite bound through the existing reviewed source workflow, then create a new Run.'))


def forecast_window_warnings(training_start: date | None,training_end: date | None,
                             forecast_start: date,forecast_end: date) -> tuple[dto.PlanningNotification,...]:
    """PLAN7 provenance only: never reject overlap or substitute another model."""
    if training_start is None or training_end is None:
        return (notice('FORECAST_TRAINING_BOUNDS_UNKNOWN',entity='forecast'),)
    start=max(training_start,forecast_start);end=min(training_end,forecast_end)
    if start>end:return ()
    dates=tuple(start+timedelta(days=offset) for offset in range((end-start).days+1))
    return (notice('FORECAST_TRAINING_OVERLAP',entity='forecast',dates=dates),)


def configuration(record):
    r=record.resolution
    # Restore the customer's source budget null, while the separate accepted
    # effective budget remains exact and immutable.
    requested_budget=(r.configuration.defaults.requirements.budget_limit if record.request.requirements_mode=='default'
        else r.configuration.saved.requirements.budget_limit if record.request.requirements_mode=='saved'
        else record.request.requirements.budget_limit)
    return dto.RunConfiguration(requirements_mode=record.request.requirements_mode,
        effective_requirements=StoredRequirements(budget_limit=requested_budget,paths=tuple(StoredPath(
            path=p.path,min_fill_rate_percent=percent(p.minimum),product_overrides=tuple(ProductOverride(product_id=o.product_id,
                min_fill_rate_percent=percent(o.target)) for o in p.overrides)) for p in r.requirements.paths)),
        budget=dto.BudgetAtAcceptance(limit=plain(r.budget.amount),currency=r.budget.currency,
            ceiling_at_acceptance=plain(r.budget_ceiling.amount),ceiling_version=r.budget_version),
        default_version=r.default_reference.version if r.default_reference else None,
        saved_reference=dto.PlanningSavedReference(id=r.saved_reference.saved_requirement_id,version=r.saved_reference.version,
            updated_at=r.saved_reference.updated_at) if r.saved_reference else None)


def scope(record):
    c=record.capture
    if c is None:return None
    requirements=record.resolution.requirements
    return dto.RunScope(menu_products=tuple(dto.PlanningProductBrief(product_id=p.product_id,name=p.name,selling_unit=p.selling_unit) for p in c.menu),
        computed_product_ids=c.computed_product_ids,menu_count=len(c.menu),computed_count=len(c.computed_product_ids),
        coverage_status='none' if not c.computed_product_ids else 'full' if len(c.computed_product_ids)==len(c.menu) else 'partial',
        excluded_products=tuple(dto.Exclusion(product_id=e.product_id,code=PUBLIC_CODES.get(e.reasons[0].code,e.reasons[0].code),field=e.reasons[0].field,
            affected_dates=e.affected_dates,ingredient_ids=tuple(sorted({p.entity_id for p in e.reasons if p.entity=='ingredient' and p.entity_id})),
            message='; '.join(sorted({p.code for p in e.reasons})),suggested_action='Correct the retained exclusion causes and submit a new Run.',
            requirement_overrides=tuple(dto.ExcludedOverride(path=p.path,target_percent=percent(o.target)) for p in requirements.paths
                for o in p.overrides if o.product_id==e.product_id)) for e in c.exclusions))


def gap(g,units):
    return dto.Gap(product_id=g.product_id,path=g.path,target_percent=percent(g.target),shortfall=quantity(g.shortfall_quantity),unit=units[g.product_id])


def results(record):
    r=record.result
    if r is None:return None
    units={p.product_id:p.selling_unit for p in r.capture.menu}
    bindings={b.strategy:b.option_token for b in r.comparison.bindings} if r.comparison else {}
    strategies=tuple(dto.StrategyResult(strategy=s.strategy.lower(),construction_path=s.construction_path,option_id=bindings.get(s.strategy),
        execution=s.execution,termination=s.termination,customer_pass=s.customer_pass,construction_pass=s.construction_pass,
        selection_kind=s.selection_kind,customer_feasibility=s.customer_feasibility,construction_feasibility=s.construction_feasibility,
        proof=s.proof,proof_scope=s.proof_scope,domain_size=str(s.domain_size),search_complete=s.search_complete,
        customer_gaps=tuple(gap(g,units) for g in s.customer_gaps),construction_gaps=tuple(gap(g,units) for g in s.construction_gaps),
        diagnostic=notice(s.termination) if s.diagnostic else None) for s in r.procurement.strategies) if r.procurement else ()
    options=[]
    eligible=set(r.selection.eligible_tokens) if r.selection else set()
    rejected={x.option_token:x.reasons for x in r.selection.rejected} if r.selection else {}
    winner=r.selection.winner_token if r.selection else None
    for o in r.comparison.options if r.comparison else ():
        fees=tuple(dto.PlanningFeeComponent(basis=f.basis,entity_id=f.entity_id,amount=quantity(f.amount)) for f in o.outlay.components)
        terms={t.id:t for t in r.capture.source.facts.supplier_terms}
        purchases=[]
        for b in o.basket:
            term=terms[b.term_id]
            # These dates and costs are retained engine input/output, not live.
            arrival=next(a for a in o.arrivals if a.lot_id==next(x.arrival_lot_id for x in r.procurement.input.offers if x.term_id==b.term_id))
            purchases.append(dto.Purchase(supplier_term_id=b.term_id,supplier_id=b.supplier_id,ingredient_id=b.ingredient_id,unit=b.unit,packs=b.packs,
                quantity=quantity(b.quantity),arrival_date=arrival.arrival_day,expiry_date=arrival.expiry_date,
                purchase_outlay=quantity(Fraction(term.pack_cost)*b.packs),
                payable_fee_components=tuple(f for f in fees if f.basis=='OFFER' and f.entity_id==b.term_id)))
        assessments=[]
        for p in record.resolution.requirements.paths:
            for product in o.products:
                if product.path!=p.path:continue
                override=next((x for x in p.overrides if x.product_id==product.product_id),None)
                target=override.target if override else p.minimum
                shortfall=max(Fraction(0),fraction(product.requested)*Fraction(target)-fraction(product.fulfilled))
                assessments.append(dto.Assessment(product_id=product.product_id,path=p.path,target_percent=percent(target),
                    applied_source='product_override' if override else 'common',status='FAIL' if shortfall else 'PASS',shortfall=quantity(shortfall)))
        for e in r.capture.exclusions:
            for p in record.resolution.requirements.paths:
                override=next((x for x in p.overrides if x.product_id==e.product_id),None)
                assessments.append(dto.Assessment(product_id=e.product_id,path=p.path,target_percent=percent(override.target if override else p.minimum),
                    applied_source='product_override' if override else 'common',status='NOT_EVALUATED',shortfall=None))
        not_selected=None
        if o.token!=winner:
            if o.token not in eligible:
                not_selected='RELATED_BLOCKER' if 'RELATED_BLOCKER' in rejected.get(o.token,()) else 'CUSTOMER_REQUIREMENTS_NOT_MET'
            else:
                chosen=next(x for x in r.comparison.options if x.token==winner)
                def minima(option):
                    return tuple(service_summary((fraction(p.requested),fraction(p.fulfilled)) for p in option.products if p.path==path)[0] for path in ('HIGH','BASE','LOW'))
                not_selected='HIGHER_COST' if fraction(o.outlay.total)>fraction(chosen.outlay.total) else 'LOWER_SERVICE_TIE' if minima(o)!=minima(chosen) else 'STABLE_ORDER_TIE'
        options.append(dto.Option(option_id=o.token,source_strategies=tuple(s.lower() for s in o.source_strategies),eligible=o.token in eligible,
            rejection_reasons=rejected.get(o.token,()),not_selected_reason=not_selected,
            costs=dto.Costs(currency=o.outlay.currency,purchase=quantity(o.outlay.purchase),payable_fees=quantity(o.outlay.payable_fees),
                delivery_fees=quantity(o.outlay.delivery_fees) if o.outlay.delivery_fees is not None else None,
                fee_classification='NONE' if o.outlay.fee_classification=='NO_PAYABLE_FEES' else 'PAYABLE_FEE_TYPE_NOT_CAPTURED',total=quantity(o.outlay.total),fee_components=fees),
            purchases=tuple(purchases),product_services=tuple(dto.ProductService(product_id=p.product_id,unit=p.unit,path=p.path,
                requested=quantity(p.requested),fulfilled=quantity(p.fulfilled),lost_sales=quantity(p.lost),
                service=dto.Service(numerator=p.service.numerator,denominator=p.service.denominator,percent_view=percent(fraction(p.service))) if p.service else None) for p in o.products),
            ingredient_balances=tuple(dto.IngredientBalance(ingredient_id=i.ingredient_id,unit=i.unit,path=i.path,
                consumed=quantity(sum((fraction(d.consumed) for d in o.daily_ingredients if d.ingredient_id==i.ingredient_id and d.path_id==i.path),Fraction())),
                expired=quantity(i.expired),ending_usable=quantity(i.horizon_ending)) for i in o.ingredients),
            requirements_assessment=tuple(assessments),issues=(*tuple(notice(i.code) for i in o.issues),
                *((notice('DELIVERY_FEE_TAXONOMY_UNAVAILABLE'),) if o.outlay.fee_classification=='PAYABLE_FEE_TYPE_NOT_CAPTURED' else ()))))
    return dto.PlanningResult(completeness='full' if not r.capture.exclusions and r.comparison is not None and r.outcome not in ('EXECUTION_ERROR','COMPUTATION_BLOCKED','NUMERIC_UNSUPPORTED') else 'partial',
        strategies=strategies,options=tuple(options),winner_option_id=winner,winner_reason=r.selection.reason if r.selection else 'NOT_EVALUATED',
        warnings=tuple(capture_warning(record,p) for p in r.problems if p.kind=='WARNING'))


def project_run(record, *, response_version=None):
    r=record.result
    timing=r.timing if r else None
    return dto.RunView(run_id=record.run_id,store_id=record.store_id,status=record.status,outcome=record.outcome,
        accepted_at=record.accepted_at,started_at=record.started_at,finished_at=record.finished_at,response_version=response_version or digest('aggregate',record),
        request=record.request,configuration=configuration(record),operational_basis=record.capture.operational_basis if record.capture else None,
        forecast=record.public_capture.forecast if record.public_capture else None,scope=scope(record),
        execution=dto.ExecutionView(engine_semantics_version='procurement/2',comparison_version='procurement_comparison/2',selector_version='procurement_selector/1',
            elapsed_ms=ceil((record.public_execution.elapsed_seconds if record.public_execution else timing.total_seconds)*1000),engine_elapsed_ms=ceil(timing.engine_seconds*1000),engine_deadline_ms=30000,
            engine_overrun_ms=ceil(timing.engine_overrun_seconds*1000),comparison_selector_elapsed_ms=ceil((timing.comparison_seconds+timing.selector_seconds)*1000),
            search_complete=all(s.search_complete for s in r.procurement.strategies) if r.procurement else False) if timing and r.procurement else None,
        result=results(record),errors=(notice(record.error_code),) if record.error_code else
            tuple(notice(p.code,p.field,p.entity,p.entity_id) for p in record.capture.problems if p.kind=='DATA_BLOCKER' and p.entity!='product') if record.capture else ())
