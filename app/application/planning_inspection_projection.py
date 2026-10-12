"""Read-only projection from fully verified retained records, never live facts."""
from datetime import timedelta
from fractions import Fraction
from app.application.contracts import planning_inspection as dto
from app.application.contracts.planning_configuration import ConfigurationError
from app.application.planning_public_projection import quantity,fraction,notice,plain,PUBLIC_CODES
from app.application.contracts.planning_public import PlanningNotification,PlanningNotificationDetails


def terminal(record):
    if record.status in ('queued','running'):raise ConfigurationError('RESULT_NOT_READY',409)


def computed(record):
    terminal(record)
    if record.capture is None or record.capture.prepared is None:
        raise ConfigurationError('COMPUTED_SCOPE_NOT_AVAILABLE',409)
    return record.capture.prepared


def select(view,option_id):
    options=view.result.options if view.result else ()
    if option_id is not None:
        option=next((o for o in options if o.option_id==option_id),None)
        if option is None:raise ConfigurationError('OPTION_NOT_FOUND',404)
        return option,'explicit'
    winner=view.result.winner_option_id if view.result else None
    return (next((o for o in options if o.option_id==winner),None),'winner') if winner else (None,'not_selected')


def label(record,ingredient_id):
    labels=record.public_capture.ingredient_labels if record.public_capture else None
    found=next((i for i in labels or () if i.ingredient_id==ingredient_id),None)
    return (found.name,'captured') if found else (None,'not_captured')


def related(prepared,ingredient_id):
    days=tuple(prepared.request.cutoff_date+timedelta(days=i) for i in range(1,8))
    result=[]
    for product in prepared.products:
        recipes=[r for r in prepared.recipes if r.product_id==product.product_id and any(l.ingredient_id==ingredient_id for l in r.lines)]
        dates=tuple(d for d in days if any(r.effective_from<=d and (r.effective_to is None or d<=r.effective_to) for r in recipes))
        if dates:result.append((product,recipes,dates))
    return result


def engine_notices(issue):
    return tuple(PlanningNotification(code=PUBLIC_CODES.get(issue.code,issue.code),message=issue.impact,
        details=PlanningNotificationDetails(field=issue.field,entity=a.entity,entity_id=a.entity_id,
            affected_dates=(issue.day,) if issue.day else None,suggested_action=issue.suggested_action,classification=issue.kind))
        for a in issue.affected)


def distinct(notifications):
    found={}
    for notification in notifications:found.setdefault(notification.model_dump_json(),notification)
    return tuple(found.values())


def scoped_issues(record,ingredient_id,option=None):
    prepared=record.capture.prepared
    products={p.product_id for p,_,_ in related(prepared,ingredient_id)}
    lots={l.id for l in prepared.lots if l.ingredient_id==ingredient_id}
    terms={t.id for t in prepared.supplier_terms if t.ingredient_id==ingredient_id}
    allowed={'ingredient':{ingredient_id},'product':products,'inventory_lot':lots,'supplier_term':terms}
    problems=record.result.problems if record.result else record.capture.problems
    output=[notice(p.code,p.field,p.entity,p.entity_id,(p.day,) if p.day else None) for p in problems if p.entity_id in allowed.get(p.entity,set())]
    retained=next((o for o in record.result.comparison.options if option and o.token==option.option_id),None) if record.result and record.result.comparison else None
    for issue in retained.issues if retained else ():
        output.extend(n for n in engine_notices(issue) if n.details.entity_id in allowed.get(n.details.entity,set()))
    if label(record,ingredient_id)[0] is None:output.append(notice('LABEL_NOT_CAPTURED',entity='ingredient',entity_id=ingredient_id))
    return distinct(output)


def ingredient_row(record,view,ingredient,option,status):
    name,availability=label(record,ingredient.ingredient_id)
    purchases=tuple(p for p in option.purchases if p.ingredient_id==ingredient.ingredient_id) if option else None
    return dto.IngredientResultRow(ingredient_id=ingredient.ingredient_id,unit=ingredient.unit,
        display_name=name,name_availability=availability,
        purchase_quantity=quantity(sum((fraction(p.quantity) for p in purchases),Fraction())) if purchases is not None else None,
        purchase_line_count=len(purchases) if purchases is not None else None,
        path_balances=tuple(b for b in option.ingredient_balances if b.ingredient_id==ingredient.ingredient_id) if option else None,
        issues=scoped_issues(record,ingredient.ingredient_id,option),detail_available=True)


def evaluation(record,option):
    if option is None or record.result is None or record.result.procurement is None:return None
    for strategy in record.result.procurement.strategies:
        if strategy.strategy.lower() in option.source_strategies and strategy.candidate is not None:
            return strategy.candidate.evaluation
    return None


def ingredient_detail(record,view,ingredient_id,option_id):
    prepared=computed(record)
    ingredient=next((i for i in prepared.ingredients if i.ingredient_id==ingredient_id),None)
    if ingredient is None:raise ConfigurationError('INGREDIENT_NOT_IN_RUN',404)
    option,status=select(view,option_id)
    name,availability=label(record,ingredient_id)
    declaration=next((d for d in record.capture.request.inventory_scope if d.ingredient_id==ingredient_id),None)
    # The source capture includes expired physical lots excluded by simulation.
    lots=record.capture.source.facts.lots if record.capture.source else prepared.lots
    captured=dto.CapturedStock(captured_at=record.capture.captured_at,
        lots=tuple(dto.CapturedLot(lot_id=l.id,quantity=quantity(Fraction(l.on_hand_quantity)),unit=l.unit,
            received_date=l.received_date,expiry_date=l.expiry_date,supplier_id=l.supplier_id,
            unit_cost=plain(l.unit_cost) if l.unit_cost is not None else None,
            cost_availability='known' if l.unit_cost is not None else 'unknown') for l in lots if l.ingredient_id==ingredient_id),
        scope_declaration=declaration.state if declaration else 'UNKNOWN',provenance=declaration.provenance if declaration else None)
    evaluated=evaluation(record,option)
    known=evaluated is not None and evaluated.status=='COMPLETE'
    daily=tuple(dto.IngredientDay(path=d.path_id,day=d.day,unit=d.unit,
        **{f:quantity(getattr(d,f)) for f in ('requested','available','shortage','consumed','expired','other_waste','ending')},
        incoming_quantity=quantity(sum((fraction(l.arrivals) for l in evaluated.lots if l.ingredient_id==ingredient_id and l.path_id==d.path_id and l.day==d.day),Fraction())))
        for d in evaluated.ingredients if d.ingredient_id==ingredient_id) if known else None
    dependencies=tuple(dto.ProductDependency(product_id=p.product_id,selling_unit=p.selling_unit,ingredient_unit=ingredient.unit,
        recipe_ids=tuple(sorted(r.id for r in recipes)),affected_dates=dates,
        fulfilled_contributions=tuple(dto.FulfilledContribution(path=c.path_id,day=c.day,quantity=quantity(c.quantity))
            for c in evaluated.contributions if c.ingredient_id==ingredient_id and c.product_id==p.product_id) if known else None)
        for p,recipes,dates in related(prepared,ingredient_id))
    return dto.IngredientDetail(run_id=record.run_id,result_digest=record.result_digest,ingredient_id=ingredient_id,unit=ingredient.unit,
        selected_option_id=option.option_id if option else None,selection_status=status,display_name=name,name_availability=availability,
        captured_stock=captured,purchases=tuple(p for p in option.purchases if p.ingredient_id==ingredient_id) if option else None,
        daily_balances=daily,related_products=dependencies,issues=scoped_issues(record,ingredient_id,option),
        evidence_availability='known' if known else 'partial' if record.result else 'not_evaluated')


def explanation(record,view,option_id):
    terminal(record)
    if option_id is not None:select(view,option_id)
    result=view.result
    problems=record.result.problems if record.result else record.capture.problems if record.capture else ()
    blockers=list(notice(p.code,p.field,p.entity,p.entity_id,(p.day,) if p.day else None) for p in problems if p.kind=='DATA_BLOCKER')
    warnings=list(notice(p.code,p.field,p.entity,p.entity_id,(p.day,) if p.day else None) for p in problems if p.kind=='WARNING')
    if view.forecast:warnings.extend(view.forecast.warnings)
    if result:warnings.extend(result.warnings)
    engine_issues=tuple(record.result.bom.issues) if record.result and record.result.bom else ()
    if record.result and record.result.comparison:engine_issues+=tuple(i for o in record.result.comparison.options for i in o.issues)
    for issue in engine_issues:
        if issue.kind in ('DATA_BLOCKER','HARD_VIOLATION'):blockers.extend(engine_notices(issue))
        elif issue.kind=='WARNING':warnings.extend(engine_notices(issue))
    options=tuple(dto.OptionReason(option_id=o.option_id,eligible=o.eligible,rejection_reasons=o.rejection_reasons,
        not_selected_reason=o.not_selected_reason,source_strategies=o.source_strategies,
        evidence=tuple(s for s in result.strategies if s.strategy in o.source_strategies))
        for o in result.options if option_id is None or o.option_id==option_id) if result else ()
    return dto.Explanation(run_id=record.run_id,result_schema_version=record.result.semantics_version if record.result else None,
        result_digest=record.result_digest,availability='available' if result and result.completeness=='full' else 'partial' if result else 'unavailable',
        outcome=record.outcome,winner=dto.ExplanationWinner(option_id=result.winner_option_id if result else None,reason_code=result.winner_reason if result else 'NOT_EVALUATED'),
        exclusions=tuple(dto.ExcludedProduct(product_id=e.product_id,reason_codes=tuple(dict.fromkeys(PUBLIC_CODES.get(p.code,p.code) for p in e.reasons)),
            affected_dates=e.affected_dates) for e in record.capture.exclusions) if record.capture else (),
        blockers=distinct((*blockers,*((notice(record.error_code),) if record.error_code else ()))),warnings=distinct(warnings),options=options,
        evidence_availability='known' if result and result.strategies else 'unknown' if result else 'not_evaluated')
