"""IMP14 evaluation of detached facts. No forecast/solver/provider execution."""
from datetime import date,timedelta
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo
from pydantic import ValidationError
from app.application.contracts import readiness as dto
from app.application.contracts import import_domains as domains
from app.application.import_identity import content_digest
from app.application.operational_import_facts import declaration_dependency,current_fees,inventory_matches
from app.application.planning_fee_bindings import fee_bindings

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


def evaluate(facts,store,now,start,actions,permissions,*,model_issue=None,forecast_available=True,planning_available=False):
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
            for excluded in exclusions:
                warnings.extend(issue(code,'sales' if code=='PRODUCT_HISTORY_MISSING' else 'inventory' if code in ('INVENTORY_SCOPE_UNKNOWN','REQUIRED_EXPIRY_MISSING') else 'recipe',excluded.product_id,excluded.affected_dates) for code in excluded.reason_codes)
            if len(menu)>50:
                blockers.append(issue('RESOURCE_LIMIT_EXCEEDED','catalog'));data='invalid'
            if facts.serving is None:
                unknown.append(issue('MODEL_CONFIGURATION_UNKNOWN','configuration'))
            if model_issue:
                blockers.append(issue(model_issue,'forecast'));data='invalid'
            if current_ids and history_watermark is None:
                warnings.append(issue('HISTORY_NOT_AVAILABLE_THROUGH_CUTOFF','sales'))
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
                if facts.defaults is None:
                    unknown.append(issue('DEFAULT_CONFIGURATION_UNAVAILABLE','configuration'))
                elif (len(facts.defaults.requirements.paths)!=1 or facts.defaults.requirements.paths[0].path!='BASE' or
                    Decimal(facts.defaults.requirements.paths[0].min_fill_rate_percent)!=95 or facts.defaults.requirements.paths[0].product_overrides or facts.defaults.requirements.budget_limit is not None):
                    blockers.append(issue('REQUIREMENTS_INVALID','configuration'));data='invalid'
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
                active_suppliers={r['id'] for r in snapshot['suppliers'] if r['active']}
                terms=[r for r in snapshot['supplier_terms'] if r['ingredient_id'] in required and r['active'] and r['supplier_id'] in active_suppliers and contains(r,start)]
                if len(terms)>100:blockers.append(issue('RESOURCE_LIMIT_EXCEEDED','supplier'));data='invalid'
                for ingredient in sorted(required):
                    if not any(r['ingredient_id']==ingredient for r in terms):
                        warnings.append(issue('SUPPLIER_TERM_MISSING','supplier',ingredient,scope='INGREDIENT'))
                fee_rows=[r for r in current_fees(snapshot) if contains(r['payload'],start)]
                fee=None
                if len(fee_rows)==1:
                    try:fee=domains.FeeSource.model_validate(fee_rows[0]['payload'])
                    except ValidationError:blockers.append(issue('UNSUPPORTED_FEE_RULE','fees'));data='invalid'
                if fee is None or fee.coverage!='COMPLETE' or fee.currency!=snapshot['stores'][0]['currency'] or (fee.effective_to is not None and fee.effective_to<days[-1]):
                    blockers.append(issue('PAYABLE_FEE_COVERAGE_UNKNOWN','fees'));data='incomplete' if data=='valid' else data
                elif fee.mode!='NONE':
                    bindings=fee_bindings(snapshot['term_source_records'],snapshot['supplier_source_records'],fee_rows[0]['source_system_key'])
                    if not bindings.covers(fee,terms):
                        blockers.append(issue('PAYABLE_FEE_COVERAGE_UNKNOWN','fees'));data='incomplete'
                for term in terms:
                    if Decimal(term['pack_cost'])==0:
                        bounded=bool(contexts and any(str(l.ingredient_id)==term['ingredient_id'] and str(l.supplier_id)==term['supplier_id'] for l in contexts[0][1].supplier_limits))
                        source=next((r for r in snapshot['term_source_records'] if r['id']==term['id']),None)
                        bounded=bounded or bool(source and source['payload'].get('maximum_order_base_quantity') is not None)
                        if not bounded:blockers.append(issue('OFFER_BOUND_UNKNOWN','supplier'));data='incomplete'
                constraints=[r for r in snapshot['business_constraints'] if r['active'] and r['scope_type']=='STORE' and any(contains(r,day) for day in days)]
                if facts.cap and any(Decimal(r['numeric_value'])!=Decimal(facts.cap.amount) or r['unit']!=facts.cap.currency for r in constraints):
                    blockers.append(issue('BUDGET_CONFIGURATION_CONFLICT','constraints'));data='invalid'
        if unknown and data=='valid':data='unknown'
        availability='blocked' if blockers else 'unknown' if unknown else 'ready'
        results.append(dto.ActionReadiness(action=action,availability=availability,can_execute=availability=='ready',
            data_status=data,execution_status=execution,blockers=tuple({i.code:i for i in blockers+unknown}.values()),warnings=tuple(warnings)))
    source_versions=versions(facts)
    return dto.Readiness(store_id=store,as_of_date=today,evaluated_at=now,
        data_version=content_digest(dict(versions=source_versions.model_dump(mode='json'),start=str(start),actions=actions,
            permissions=sorted(permissions),runtime=[forecast_available,planning_available])),
        evaluated_forecast_start_date=start,cutoff_date=cutoff,actions=tuple(results),source_versions=source_versions,
        scope_estimate=scope,history_watermark=history_watermark)
