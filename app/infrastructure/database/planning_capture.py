"""S4.9 coherent owned RR snapshot: source pins, declarations and /2 facts."""
from dataclasses import dataclass
from decimal import Decimal,localcontext
from fractions import Fraction
from uuid import UUID,uuid5
from pydantic import ValidationError
from app.application.contracts.offer_admission import OfferAdmission
from app.application.offer_admission import term_from_snapshot,missing_offer_fields,omission
from app.application.planning_source_proof import source_confirmation
from app.application.contracts import import_domains as domains
from app.application.contracts.decision_capture import InventoryScopeDeclaration,CaptureProblem
from app.application.contracts.decision_capture_v2 import DecisionCaptureOutcomeV2
from app.application.contracts.decision_execution import DecisionPolicy
from app.application.contracts.planning_public_evidence import PublicPlanningCapture,IngredientLabel
from app.application.contracts.planning_source_evidence import (PlanningSourceEvidence,TermEvidence,SupplierEvidence,FeeEvidence,DeclarationEvidence,BoundEvidence)
from app.application.contracts.planning_public import ForecastView
from app.application.planning_public_projection import notice,forecast_window_warnings
from app.application.use_cases.planning_pipeline import PlanningPipelineDeclarations,prepare_planning_pipeline
from app.application.contracts.procurement import ProcurementOffer,OfferBound,SupplierFee,IngredientCapacity,SupplierLimit
from app.application.forecast_preparation import prepare_observations
from app.application.forecast_serialization import serialize_prepared
from app.application.use_cases.forecast_serving import source_digest
from app.application.readiness_evaluation import latest_declarations,contains,versions
from app.application.operational_import_facts import declaration_dependency,current_fees,inventory_matches
from app.application.planning_fee_bindings import fee_bindings
from app.application.decision_capture_v2_validation import project_capture_v2
from app.application.contracts.auth import AuthError
from app.infrastructure.database.auth_session import auth_session
from app.infrastructure.database.decision_capture_v2 import read_operational_facts_v2
from app.repositories.readiness import load_readiness


@dataclass(frozen=True)
class PlanningCaptured:
    declarations: PlanningPipelineDeclarations
    capture: DecisionCaptureOutcomeV2
    evidence: PublicPlanningCapture
    source_matches: bool


def problem(code,store,field):
    return CaptureProblem(code=code,kind='DATA_BLOCKER',entity='store',entity_id=store,field=field,detail=code.replace('_',' '))


def fee_total(components):
    values=tuple(Decimal(c.amount) for c in components)
    # Money inputs have<=18 fractional/18 integer digits. Choose enough exact
    # coefficient precision for the entire sum, independent of ambient context.
    with localcontext() as context:
        context.prec=40+len(str(max(1,len(values))))
        return sum(values,Decimal(0))


def declarations_for(record,facts,forecast_id,now):
    snap=facts.snapshot;store=record.store_id;start=record.request.forecast_start_date
    end=record.resolution.forecast_end_date;problems=[]
    admission_policy=record.public_acceptance.offer_eligibility_policy if record.public_acceptance else None
    omissions=[]
    active={r['id'] for r in snap['products'] if r['active']}
    recipes={r['id'] for r in snap['recipes'] if r['assigned'] and r['product_id'] in active and r['effective_from']<=str(end) and (r['effective_to'] is None or r['effective_to']>=str(start))}
    required={r['ingredient_id'] for r in snap['recipe_lines'] if r['recipe_id'] in recipes}
    rows=latest_declarations(snap)
    valid=[(r,d) for r,d in rows if r['dependency_digest']==declaration_dependency(snap,d)]
    inventory=[]
    for ingredient in snap['ingredients']:
        ident=UUID(ingredient['id'])
        matches=inventory_matches(snap,rows,ident,now)
        inventory.append(InventoryScopeDeclaration(ingredient_id=ident,state=matches[0].state if len(matches)==1 else 'UNKNOWN',
            provenance=matches[0].evidence_reference if len(matches)==1 else 'No unique current complete inventory evidence'))
    contexts=[d for r,d in valid if isinstance(d,domains.ProcurementDeclaration) and d.effective_from<=start and (d.effective_to is None or d.effective_to>=end)]
    context=contexts[0] if len(contexts)==1 else None
    capacities=tuple(IngredientCapacity(store_id=store,provenance=context.evidence_reference,**c.model_dump()) for c in context.capacities) if context else ()
    limits=tuple(SupplierLimit(store_id=store,provenance=context.evidence_reference,**c.model_dump()) for c in context.supplier_limits) if context else ()
    if context and context.no_additional_orders_state!='CONFIRMED_NONE':problems.append(problem('LIMIT_CONFIGURATION_UNKNOWN',store,'no_additional_orders'))
    supplier_ids={r['id'] for r in snap['suppliers'] if r['active']}
    terms=[r for r in snap['supplier_terms'] if r['ingredient_id'] in required and r['active'] and r['supplier_id'] in supplier_ids and contains(r,start)]
    fees=[r for r in current_fees(snap) if contains(r['payload'],start)]
    fee=domains.FeeSource.model_validate(fees[0]['payload']) if len(fees)==1 else None
    coverage='COMPLETE' if fee and fee.coverage=='COMPLETE' and (fee.effective_to is None or fee.effective_to>=end) and fee.currency==record.resolution.budget.currency else 'UNKNOWN'
    if fee and fee.mode!=record.resolution.configuration.policy.fee_mode:
        coverage='UNKNOWN';problems.append(problem('PAYABLE_FEE_DECLARATION_CONFLICT',store,'fees'))
    fee_system=fees[0]['source_system_key'] if len(fees)==1 else None
    bindings=fee_bindings(snap['term_source_records'],snap['supplier_source_records'],fee_system)
    offers=[];bound_evidence=[]
    for term in terms:
        if admission_policy:
            try:term_from_snapshot(term)
            except ValidationError as error:
                missing=missing_offer_fields(term,error)
                if missing:
                    omissions.append(omission(term,'SUPPLIER_TERM_FACT_UNAVAILABLE',missing))
                else:
                    problems.append(CaptureProblem(code='INVALID_SOURCE_ROW',kind='DATA_BLOCKER',entity='ingredient',
                        entity_id=term['ingredient_id'],field='supplier_term',detail='Invalid/conflicting offer fact; not eligible for omission'))
                continue
            ingredient=next((i for i in snap['ingredients'] if i['id']==term['ingredient_id']),None)
            if ingredient and ingredient['expiry_tracking'] and term['shelf_life_days'] is None:
                omissions.append(omission(term,'SUPPLIER_TERM_FACT_UNAVAILABLE',('shelf_life_days',)))
                continue
        bounds=[];supplier_bounds=[]
        cost=Fraction(Decimal(term['pack_cost']));pack=Fraction(Decimal(term['pack_size_base_quantity']))
        if cost:bounds.append(int(Fraction(record.resolution.budget.amount)//cost))
        source=next((r for r in snap['term_source_records'] if r['id']==term['id']),None)
        if source and source['payload']['maximum_order_base_quantity'] is not None:
            supplier_bounds.append(int(Fraction(Decimal(source['payload']['maximum_order_base_quantity']))//pack))
        declared_bounds=[int(Fraction(l.maximum_quantity)//pack) for l in limits if str(l.supplier_id)==term['supplier_id'] and str(l.ingredient_id)==term['ingredient_id']]
        supplier_bounds.extend(declared_bounds)
        if supplier_bounds:bounds.extend(supplier_bounds)
        if not bounds:
            if admission_policy:omissions.append(omission(term,'OFFER_BOUND_UNKNOWN'))
            else:problems.append(problem('OFFER_BOUND_UNKNOWN',store,'offers'))
            continue
        payable=None
        if fee and fee.mode=='NONE':payable=Decimal(0)
        elif fee and fee.mode=='PER_OFFER':
            key=bindings.term_keys.get(term['id'])
            if key not in fee.covered_source_term_keys:coverage='UNKNOWN'
            else:payable=fee_total(c for c in fee.components if c.source_term_key==key)
        bound_evidence.append(BoundEvidence(term_id=term['id'],effective_budget=record.resolution.budget.amount,budget_version=record.resolution.budget_version,
            pack_cost=Decimal(term['pack_cost']),pack_size=Decimal(term['pack_size_base_quantity']),
            source_maximum_quantity=Decimal(source['payload']['maximum_order_base_quantity']) if source and source['payload']['maximum_order_base_quantity'] is not None else None,
            declared_limit_quantity=next((l.maximum_quantity for l in limits if str(l.supplier_id)==term['supplier_id'] and str(l.ingredient_id)==term['ingredient_id']),None),maximum_packs=min(bounds)))
        offers.append(ProcurementOffer(term_id=term['id'],arrival_lot_id=uuid5(record.run_id,term['id']),
            bound=OfferBound(maximum_packs=min(bounds),source='CAPTURED_SUPPLIER_LIMIT' if declared_bounds else 'TECHNICAL_SEARCH_LIMIT',
                derivation=f'S49-bound/1: floor(accepted effective budget / positive pack cost), intersect captured source maximum and declared supplier limits; budget version {record.resolution.budget_version}',
                proof_scope='CAPTURED_FINITE_DOMAIN_ONLY'),payable_fee=payable,
            provenance='Captured effective Store supplier term; hypothetical one-order arrival identity'))
    eligible_ids={str(o.term_id) for o in offers}
    fee_terms=[t for t in terms if t['id'] in eligible_ids] if admission_policy else terms
    if fee and not bindings.covers(fee,fee_terms):coverage='UNKNOWN'
    supplier_fees=[]
    if fee and fee.mode=='PER_SUPPLIER_ORDER':
        for supplier in sorted({t['supplier_id'] for t in fee_terms}):
            aliases=bindings.supplier_keys.get(supplier,frozenset())
            supplier_fees.append(SupplierFee(supplier_id=supplier,amount=fee_total(c for c in fee.components if c.source_supplier_key in aliases)
                if aliases & set(fee.covered_source_supplier_keys) else None,provenance=fee.evidence_reference))
    if len(active)>50 or len(required)>100 or len(terms)>100 or len([r for r in snap['inventory_lots'] if r['ingredient_id'] in required])>1000:
        problems.append(problem('RESOURCE_LIMIT_EXCEEDED',store,'scope'))
    # The DTO bound is not a truncation. Excess offers cannot enter computation;
    # preserve their canonical source rows and the whole-Run resource blocker.
    if len(offers)>100:offers=[];bound_evidence=[]
    return PlanningPipelineDeclarations(forecast_run_id=forecast_id,inventory_scope=tuple(inventory),
        committed_inbound_state=context.committed_inbound_state if context else 'UNKNOWN',
        committed_inbound_provenance=context.evidence_reference if context else 'No unique current procurement context evidence',
        no_additional_orders_provenance=context.evidence_reference if context and context.no_additional_orders_state=='CONFIRMED_NONE' else 'No additional-order confirmation unavailable; capture blocked',
        snapshot_policy=DecisionPolicy(),offers=tuple(offers),supplier_fees=tuple(supplier_fees),capacities=capacities,supplier_limits=limits,
        capacity_state=context.capacity_state if context else 'UNKNOWN',supplier_limit_state=context.supplier_limit_state if context else 'UNKNOWN',
        provenance='S49 coherent RR operational source and explicit declarations',payable_fee_coverage=coverage,
        payable_fee_coverage_provenance=fee.evidence_reference if fee else 'No unique complete payable fee evidence',
        offer_admission=OfferAdmission(omissions=tuple(omissions)) if admission_policy else None),tuple(problems),tuple(bound_evidence)


class PostgresPlanningCapture:
    def __init__(self,engine,clock):self.engine,self.clock=engine,clock

    def read(self,record,served,preparation,elapsed):
        with self.engine.connect().execution_options(isolation_level='REPEATABLE READ',postgresql_readonly=True) as connection:
            with auth_session(connection) as s:
                facts=load_readiness(s,record.store_id)
                now=self.clock()
                matched=True
                try:current=prepare_observations(facts,record.store_id,record.request.forecast_start_date)
                except AuthError as error:
                    if error.code!='NO_COMPUTABLE_PRODUCTS':raise
                    matched=served is None
                else:
                    matched=served is not None and serialize_prepared(current).digest==served.identity.prepared_digest and source_digest(facts,current)==served.identity.source_digest
                declarations,extra,bounds=declarations_for(record,facts,served.run.id if served else None,now)
                request=prepare_planning_pipeline(record.resolution,declarations)
                source=read_operational_facts_v2(s,request,self.clock)
                if extra:source=source.model_copy(update={'problems':(*source.problems,*extra)})
                snap=facts.snapshot
                term_ids={str(t.term_id) for t in source.supplier_term_scope}
                term_versions={r['id']:r['version'] for r in snap['supplier_terms']}
                source_evidence=PlanningSourceEvidence(
                    terms=tuple(TermEvidence(term_id=r['id'],version=term_versions[r['id']],source_system_key=r['source_system_key'],
                        source_record_key=r['source_record_key'],payload=r['payload']) for r in snap['term_source_records'] if r['id'] in term_ids),
                    suppliers=tuple(SupplierEvidence(supplier_id=r['supplier_id'],source_system_key=r['source_system_key'],source_record_key=r['source_record_key']) for r in snap['supplier_source_records']),
                    fees=tuple(FeeEvidence(id=r['id'],version=r['version'],source_system_key=r['source_system_key'],source_record_key=r['source_record_key'],payload=r['payload']) for r in current_fees(snap) if contains(r['payload'],record.request.forecast_start_date)),
                    declarations=tuple(DeclarationEvidence(id=r['id'],version=r['version'],source_system_key=r['source_system_key'],source_record_key=r['source_record_key'],
                        dependency_digest=r['dependency_digest'],payload=r['payload']) for r,d in latest_declarations(snap)),bounds=bounds,
                    observed_history_product_ids=tuple(sorted({UUID(r['product_id']) for r in snap['sales_daily'] if r['sales_date']<=str(record.resolution.cutoff_date)
                        and any(p['id']==r['product_id'] and p['active'] for p in snap['products'])})),
                    confirmations=tuple(source_confirmation(entity,identifier,r,snap['import_audit'])
                        for entity,rows in (
                            ('supplier_term',[(r['id'],r) for r in snap['term_source_records'] if r['id'] in term_ids]),
                            ('supplier',[(r['supplier_id'],r) for r in snap['supplier_source_records']]),
                            ('fee',[(r['id'],r) for r in current_fees(snap) if contains(r['payload'],record.request.forecast_start_date)]),
                            ('declaration',[(r['id'],r) for r,d in latest_declarations(snap)]))
                        for identifier,r in rows) if declarations.offer_admission else None)
        capture=DecisionCaptureOutcomeV2(semantics_version='operational_capture/2',request=request,captured_at=source.facts.captured_at,
            source=source,**project_capture_v2(request,source))
        identity=served.identity if served else None
        forecast=ForecastView(forecast_run_id=served.run.id,input_digest=identity.prepared_digest,model_type=identity.model_type,
            model_version=identity.model_version,artifact_identity=identity.artifact_identity,start_date=served.run.forecast_start_date,
            end_date=served.run.forecast_end_date,history_start_date=preparation.prepared.request.history_start_date,
            history_end_date=preparation.prepared.request.cutoff_date,training_start_date=identity.training_start_date,
            training_end_date=identity.training_end_date,reused=served.reused,quality_status='not_evaluated',
            warnings=(tuple(notice(w.code,entity='product' if w.product_id else 'forecast',entity_id=w.product_id) for w in source.facts.forecast.execution.warnings)
                if source.facts.forecast and source.facts.forecast.execution else ())+
                forecast_window_warnings(identity.training_start_date,identity.training_end_date,served.run.forecast_start_date,served.run.forecast_end_date)) if served else None
        return PlanningCaptured(declarations,capture,PublicPlanningCapture(forecast=forecast,identity=identity,source_versions=versions(facts),
            preparation_seconds=elapsed,operational_evidence=source_evidence,
            ingredient_labels=tuple(IngredientLabel(ingredient_id=r['id'],name=r['name'],sku=r['sku']) for r in snap['ingredients']
                if capture.prepared and any(str(i.ingredient_id)==r['id'] for i in capture.prepared.ingredients))),matched)
