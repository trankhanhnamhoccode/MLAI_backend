"""IMP14 evaluation of detached facts. No forecast/solver/provider execution."""
from datetime import date,timedelta
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo
from app.application.contracts import readiness as dto
from app.application.contracts import import_domains as domains
from app.application.contracts.forecast_eligibility import ForecastEligibility
from app.application.import_identity import content_digest
from app.application.operational_import_facts import declaration_dependency,inventory_matches
from app.domain.forecasting.stockout import Observation, reconstruct

ACTION_READS={
    'import':('import.read',),'menu':('menu.read',),'inventory':('inventory.read','ingredient.read'),
    'forecast':('planning.context.read','sales.read'),
    'planning':('planning.context.read','budget.read','procurement.cost.read'),
}


def issue(code,source,ident=None,dates=(),scope=None):
    return dto.Issue(code=code,source=source,scope=scope or ('PRODUCT' if ident else 'STORE'),
        entity_id=UUID(str(ident)) if ident else None,affected_dates=tuple(dates),details=dto.IssueDetails())


def versions(facts):
    snapshot=facts.snapshot
    groups={'catalog':('products','ingredients','stores'),'recipes':('recipes','recipe_lines'),
        'inventory':('inventory_lots','inventory_movements'),'sales':('sales_daily',),
        'suppliers':('suppliers','supplier_terms','supplier_source_records','term_source_records'),
        'fees':('payable_fee_records',),'declarations':('scope_declaration_records','business_constraints')}
    values={key:content_digest({t:snapshot[t] for t in tables}) for key,tables in groups.items()}
    values['planning_config']=content_digest(dict(default=facts.defaults.model_dump(mode='json') if facts.defaults else None,
        cap=facts.cap.model_dump(mode='json') if facts.cap else None,saved=[r.model_dump(mode='json') for r in facts.saved]))
    values['model_config']=facts.serving.version if facts.serving else None
    return dto.SourceVersions(**values)


def latest_declarations(snapshot):
    current={}
    for row in snapshot['scope_declaration_records']:
        key=row['source_system_key'],row['source_record_key']
        if key not in current or row['version']>current[key]['version']:
            current[key]=row
    return tuple((row,domains.DeclarationSource.model_validate(row['payload']).declaration) for row in current.values())


def contains(row,day):
    return row['effective_from']<=str(day) and (row['effective_to'] is None or row['effective_to']>=str(day))


def recipe_dependencies(snapshot,product,days):
    ids={r['id']:r for r in snapshot['ingredients']}
    problems=[];dependencies=set()
    for day in days:
        recipes=[r for r in snapshot['recipes'] if r['product_id']==product['id'] and r['assigned'] and contains(r,day)]
        code=None
        if len(recipes)!=1:
            code='RECIPE_PERIOD_GAP' if not recipes else 'RECIPE_OVERLAP'
        else:
            recipe=recipes[0]
            lines=[r for r in snapshot['recipe_lines'] if r['recipe_id']==recipe['id']]
            if not lines:
                code='RECIPE_EMPTY'
            elif not Decimal(recipe['yield_quantity']).is_finite() or Decimal(recipe['yield_quantity'])<=0 or not Decimal(recipe['process_loss_rate']).is_finite() or not 0<=Decimal(recipe['process_loss_rate'])<1:
                code='INVALID_RECIPE_CONTENT'
            for line in lines:
                ingredient=ids.get(line['ingredient_id'])
                if ingredient is None:
                    # Cannot establish graph authority to exclude other dependents.
                    return (),('SOURCE_FAILURE_SCOPE_UNKNOWN',),()
                dependencies.add(ingredient['id'])
                if line['unit']!=ingredient['base_unit']:
                    code='UNIT_MISMATCH'
                elif not Decimal(line['quantity']).is_finite() or Decimal(line['quantity'])<=0:
                    code='INVALID_RECIPE_CONTENT'
        if code:
            problems.append((code,day))
    return tuple(sorted(dependencies)),tuple(dict.fromkeys(c for c,_ in problems)),tuple(sorted({d for _,d in problems}))


def watermark(snapshot,declarations,ids,cutoff):
    result=[]
    for row,d in declarations:
        if not isinstance(d,domains.SalesDeclaration) or d.state!='COMPLETE' or set(map(str,d.product_ids))!=set(ids):
            continue
        if row['dependency_digest']!=declaration_dependency(snapshot,d):
            continue
        observations={(r['product_id'],r['sales_date']) for r in snapshot['sales_daily'] if r['product_id'] in ids and str(d.from_date)<=r['sales_date']<=str(d.to_date)}
        if len(observations)!=len(ids)*((d.to_date-d.from_date).days+1):
            continue
        if d.from_date<=cutoff<=d.to_date:
            result.append(min(d.to_date,cutoff))
    return max(result,default=None)


def evaluate(facts,store,now,start,actions,permissions,*,forecast_assessment: ForecastEligibility | None=None,forecast_available=True,planning_available=False,planning_request=None):
    snapshot=facts.snapshot
    today=now.astimezone(ZoneInfo(snapshot['stores'][0]['timezone'])).date()
    cutoff=start-timedelta(days=1)
    days=tuple(start+timedelta(days=i) for i in range(7))
    menu=[p for p in snapshot['products'] if p['active']]
    declarations=latest_declarations(snapshot) if {'forecast','planning','inventory'}&set(actions) else ()
    base_scope=[];planning_scope=[];forecast_exclusions=[];planning_exclusions=[];graph_unknown=False
    dependencies={}
    for p in (menu if {'forecast','planning'}&set(actions) else ()):
        history=[r for r in snapshot['sales_daily'] if r['product_id']==p['id'] and r['sales_date']<=str(cutoff)]
        codes=[];affected=()
        if not history:
            codes.append('PRODUCT_HISTORY_MISSING')
        elif not any(r.usable for r in reconstruct(tuple(Observation(date.fromisoformat(r['sales_date']),
                Decimal(r['quantity']), r.get('is_stockout')) for r in history), cutoff)):
            codes.append('CENSORED_HISTORY_NOT_USABLE')
        else:
            base_scope.append(p['id'])
        if codes:
            forecast_exclusions.append(dto.Exclusion(product_id=p['id'],reason_codes=tuple(codes),affected_dates=()))
        deps,recipe_codes,affected=recipe_dependencies(snapshot,p,days)
        if 'SOURCE_FAILURE_SCOPE_UNKNOWN' in recipe_codes:
            graph_unknown=True
        codes.extend(recipe_codes)
        if not recipe_codes:
            for ident in deps:
                matching=inventory_matches(snapshot,declarations,ident,now)
                lots=[r for r in snapshot['inventory_lots'] if r['ingredient_id']==ident]
                if len(matching)!=1:
                    codes.append('INVENTORY_SCOPE_UNKNOWN')
                ingredient=next(r for r in snapshot['ingredients'] if r['id']==ident)
                if ingredient['expiry_tracking'] and any(r['expiry_date'] is None and Decimal(r['on_hand_quantity'])>0 for r in lots):
                    codes.append('REQUIRED_EXPIRY_MISSING')
        if codes:
            planning_exclusions.append(dto.Exclusion(product_id=p['id'],reason_codes=tuple(dict.fromkeys(codes)),affected_dates=affected))
        else:
            planning_scope.append(p['id']);dependencies[p['id']]=deps
    ids=planning_scope if 'planning' in actions else base_scope
    scope=dto.ScopeEstimate(menu_product_count=len(menu),estimated_computable_product_count=len(ids),
        excluded_products=tuple(planning_exclusions if 'planning' in actions else forecast_exclusions)) if {'forecast','planning'}&set(actions) else None
    history_watermark=watermark(snapshot,declarations,ids,cutoff) if ids and scope else None
    resolution=None;configuration_issues=();configuration_status='UNKNOWN'
    if 'planning' in actions:
        from app.application.contracts.planning_setup import PlanningRequest
        from app.application.contextual_planning import resolve_context
        request=planning_request or PlanningRequest(requirements_mode='default',forecast_start_date=start,
            default_requirements_version=facts.defaults.version if facts.defaults else 'unconfigured')
        resolution,configuration_issues=resolve_context(facts,store,now,request)
        configuration_status='RESOLVED' if resolution else 'INVALID'
    results=[]
    for action in actions:
        blockers=[];warnings=[];unknown=[];data='valid';execution='available'
        if action=='import':
            if not {'import.create','import.upload'}<=set(permissions):
                blockers.append(issue('ACTION_NOT_GRANTED','authorization'))
        elif action=='menu':
            if not menu:warnings.append(issue('MENU_EMPTY','catalog'))
        elif action=='inventory':
            for ingredient in snapshot['ingredients']:
                if len(inventory_matches(snapshot,declarations,ingredient['id'],now))!=1:
                    warnings.append(issue('STOCK_COMPLETENESS_UNKNOWN','inventory',ingredient['id'],scope='INGREDIENT'))
        else:
            current_ids=planning_scope if action=='planning' else base_scope
            exclusions=planning_exclusions if action=='planning' else forecast_exclusions
            if not menu:
                blockers.append(issue('NO_ACTIVE_PRODUCTS','catalog'));data='incomplete'
            if not current_ids:
                blockers.append(issue('NO_COMPUTABLE_PRODUCTS','catalog'));data='incomplete'
                if any('CENSORED_HISTORY_NOT_USABLE' in e.reason_codes for e in exclusions):
                    blockers.append(issue('CENSORED_HISTORY_NOT_USABLE', 'sales'))
            for excluded in exclusions:
                warnings.extend(issue(code,'sales' if code in ('PRODUCT_HISTORY_MISSING', 'CENSORED_HISTORY_NOT_USABLE') else 'inventory' if code in ('INVENTORY_SCOPE_UNKNOWN','REQUIRED_EXPIRY_MISSING') else 'recipe',excluded.product_id,excluded.affected_dates) for code in excluded.reason_codes)
            if len(menu)>50:
                blockers.append(issue('RESOURCE_LIMIT_EXCEEDED','catalog'));data='invalid'
            if facts.serving is None:
                unknown.append(issue('MODEL_CONFIGURATION_UNKNOWN','configuration'))
            if forecast_assessment and forecast_assessment.blockers:
                blockers.extend(forecast_assessment.blockers)
                if forecast_assessment.failure_kind in ('DEPENDENCY_UNAVAILABLE','RUNTIME_UNAVAILABLE'):
                    execution='unavailable'
                else:
                    data='incomplete' if forecast_assessment.failure_kind=='HISTORY_UNUSABLE' else 'invalid'
            if current_ids and history_watermark is None:
                warnings.append(issue('HISTORY_NOT_AVAILABLE_THROUGH_CUTOFF','sales'))
            for pid in current_ids:
                demand = reconstruct(tuple(Observation(date.fromisoformat(r['sales_date']), Decimal(r['quantity']),
                    r.get('is_stockout')) for r in snapshot['sales_daily']
                    if r['product_id'] == pid and r['sales_date'] <= str(cutoff)), cutoff)
                for method, code in (('UNKNOWN_OBSERVED_COMPATIBILITY','STOCKOUT_UNKNOWN'),
                        ('CENSORED_UNSUPPORTED','CENSORED_HISTORY_EXCLUDED'), ('PAST_MEDIAN','DEMAND_RECONSTRUCTED')):
                    dates = tuple(r.day for r in demand if r.method == method)
                    if dates:
                        warnings.append(issue(code, 'sales', pid, dates))
            if forecast_assessment:
                for warning in forecast_assessment.warnings:
                    details=dto.IssueDetails(field=warning.field,impact=warning.impact)
                    matching=[i for i in warnings if (i.code,i.entity_id)==(warning.code,warning.product_id)]
                    if matching:
                        warnings=[i.model_copy(update={'details':details}) if i in matching else i for i in warnings]
                    else:
                        warnings.append(dto.Issue(code=warning.code,source='forecast',scope='PRODUCT' if warning.product_id else 'STORE',
                            entity_id=warning.product_id,affected_dates=(),details=details))
            if not forecast_available:
                execution='unavailable';blockers.append(issue('EXECUTION_UNAVAILABLE','runtime'))
            if action=='planning':
                if 'planning.run' not in permissions:
                    blockers.append(issue('ACTION_NOT_GRANTED','authorization'))
                if not planning_available:
                    execution='unavailable';blockers.append(issue('EXECUTION_UNAVAILABLE','runtime'))
                    blockers.append(issue('PLANNING_WORKFLOW_UNAVAILABLE','runtime'))
                if facts.cap is None:
                    blockers.append(issue('BUDGET_CEILING_UNKNOWN','configuration'));data='incomplete'
                if configuration_issues:
                    blockers.extend(configuration_issues);data='incomplete'
                if resolution:
                    warnings.extend(issue(w.code,'configuration') for w in resolution.warnings)
                if start!=today:
                    warnings.append(issue('NONCURRENT_PLANNING_CURRENT_FACTS','inventory'))
                if graph_unknown:
                    blockers.append(issue('SOURCE_FAILURE_SCOPE_UNKNOWN','recipe'));data='invalid'
                required={i for p in planning_scope for i in dependencies[p]}
                if len(required)>100 or len([r for r in snapshot['inventory_lots'] if r['ingredient_id'] in required])>1000:
                    blockers.append(issue('RESOURCE_LIMIT_EXCEEDED','inventory'));data='invalid'
                contexts=[(r,d) for r,d in declarations if isinstance(d,domains.ProcurementDeclaration) and
                    d.effective_from<=start and (d.effective_to is None or d.effective_to>=days[-1]) and
                    r['dependency_digest']==declaration_dependency(snapshot,d)]
                if len(contexts)!=1:
                    blockers.extend((issue('LIMIT_CONFIGURATION_UNKNOWN','constraints'),issue('COMMITTED_INBOUND_UNKNOWN','constraints')));data='incomplete'
                else:
                    d=contexts[0][1]
                    for condition,code in ((d.committed_inbound_state=='UNKNOWN','COMMITTED_INBOUND_UNKNOWN'),
                        (d.committed_inbound_state=='PRESENT_UNSUPPORTED','COMMITTED_INBOUND_UNSUPPORTED'),
                        (d.no_additional_orders_state!='CONFIRMED_NONE','LIMIT_CONFIGURATION_UNKNOWN'),
                        (d.capacity_state=='UNKNOWN' or d.supplier_limit_state=='UNKNOWN','LIMIT_CONFIGURATION_UNKNOWN')):
                        if condition:blockers.append(issue(code,'constraints'));data='incomplete'
                    if any(c.unit!=next((r['base_unit'] for r in snapshot['ingredients'] if r['id']==str(c.ingredient_id)),None) for c in (*d.capacities,*d.supplier_limits)):
                        blockers.append(issue('UNIT_MISMATCH','constraints'));data='invalid'
                    if len({c.ingredient_id for c in d.capacities})!=len(d.capacities) or len({(c.supplier_id,c.ingredient_id) for c in d.supplier_limits})!=len(d.supplier_limits):
                        blockers.append(issue('DUPLICATE_CONFIGURATION_IDENTITY','constraints'));data='invalid'
                    scoped_terms=[r for r in snapshot['supplier_terms'] if r['active'] and contains(r,start)
                        and any(s['id']==r['supplier_id'] and s['active'] for s in snapshot['suppliers'])]
                    if any(not any((r['supplier_id'],r['ingredient_id'])==(str(c.supplier_id),str(c.ingredient_id)) for r in scoped_terms) for c in d.supplier_limits):
                        blockers.append(issue('DECLARED_CONSTRAINT_SCOPE_INVALID','constraints'));data='invalid'
                if resolution:
                    from app.application.planning_admission import planning_declarations
                    from uuid import uuid5,NAMESPACE_URL
                    admission,extra,_=planning_declarations(resolution,facts,None,now,
                        run_id=uuid5(NAMESPACE_URL,str(store)),offer_policy='offer_eligibility/1')
                    blockers.extend(issue(p.code,'supplier' if p.field in ('offers','supplier_term') else 'constraints',
                        p.entity_id if p.entity=='ingredient' else None,scope='INGREDIENT' if p.entity=='ingredient' else 'STORE') for p in extra)
                    if extra:data='invalid'
                    if admission.payable_fee_coverage!='COMPLETE':
                        blockers.append(issue('PAYABLE_FEE_COVERAGE_UNKNOWN','fees'));data='incomplete' if data=='valid' else data
                    offered={str(o.term_id) for o in admission.offers}
                    terms=[r for r in snapshot['supplier_terms'] if r['id'] in offered]
                    for ingredient in sorted(required):
                        if not any(r['ingredient_id']==ingredient for r in terms):
                            warnings.append(issue('SUPPLIER_TERM_MISSING','supplier',ingredient,scope='INGREDIENT'))
                    for omitted in admission.offer_admission.omissions:
                        warnings.append(dto.Issue(code='OFFER_OMITTED',source='supplier',scope='INGREDIENT',
                            entity_id=omitted.ingredient_id,affected_dates=(),details=dto.IssueDetails(
                                field='supplier_term',entity_id=omitted.term_id,reference=omitted.source_reference,
                                version=omitted.version,classification=omitted.reason,proof_scope=admission.offer_admission.proof_scope,
                                suggested_action='Provide missing offer facts or a finite bound through the reviewed source workflow.')))
                constraints=[r for r in snapshot['business_constraints'] if r['active'] and r['scope_type']=='STORE' and any(contains(r,day) for day in days)]
                if len([r for r in constraints if r['constraint_type']=='BUDGET_LIMIT'])>1:
                    blockers.append(issue('BUDGET_OVERLAP','constraints'));data='invalid'
                if any(r['active'] and r['constraint_type']=='MIN_SAFETY_STOCK'
                    and r['scope_id'] in required and any(contains(r,day) for day in days)
                    for r in snapshot['business_constraints']):
                    blockers.append(issue('MIN_SAFETY_STOCK_UNSUPPORTED','constraints'));data='invalid'
                if facts.cap and any(Decimal(r['numeric_value'])!=Decimal(facts.cap.amount) or r['unit']!=facts.cap.currency for r in constraints):
                    blockers.append(issue('BUDGET_CONFIGURATION_CONFLICT','constraints'));data='invalid'
        if unknown and data=='valid':data='unknown'
        availability='blocked' if blockers else 'unknown' if unknown else 'ready'
        results.append(dto.ActionReadiness(action=action,availability=availability,can_execute=availability=='ready',
            data_status=data,execution_status=execution,blockers=tuple({(i.code,i.source,i.scope,i.entity_id,i.affected_dates):i for i in blockers+unknown}.values()),warnings=ordered_issues(warnings),result_assessment='NOT_ASSESSED'))
    source_versions=versions(facts)
    planning_action=next((a for a in results if a.action=='planning'),None)
    planning_assessment=dto.PlanningAssessment(input_scope='SUPPLIED_REQUEST' if planning_request else 'DEFAULT_CONFIGURATION',
        requirements_mode=request.requirements_mode,configuration_status=configuration_status,
        blockers=planning_action.blockers,warnings=planning_action.warnings) if planning_action else None
    forecast_view=dto.ForecastAssessment(requested_mode=forecast_assessment.requested_mode,
        actual_model_type=forecast_assessment.actual_model_type,actual_model_version=forecast_assessment.actual_model_version,
        selection_reason=forecast_assessment.execution.selection_reason if forecast_assessment.execution else None) if forecast_assessment else None
    return dto.Readiness(store_id=store,as_of_date=today,evaluated_at=now,
        data_version=content_digest(dict(versions=source_versions.model_dump(mode='json'),start=str(start),actions=actions,
            permissions=sorted(permissions),runtime=[forecast_available,planning_available],
            request=planning_request.model_dump(mode="json") if planning_request else None,
            assessed_actions=[a.model_dump(mode='json') for a in results],
            forecast=forecast_view.model_dump(mode='json') if forecast_view else None)),
        evaluated_forecast_start_date=start,cutoff_date=cutoff,actions=tuple(results),source_versions=source_versions,
        scope_estimate=scope,history_watermark=history_watermark,
        planning_assessment=planning_assessment,forecast_assessment=forecast_view)


def ordered_issues(issues):
    """Stable public identity, including exact references; never collapse Product scopes."""
    return tuple({i.model_dump_json():i for i in sorted(issues,key=lambda i:i.model_dump_json())}.values())
