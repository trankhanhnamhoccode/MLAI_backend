"""Shared detached D3 admission for execution and contextual preflight; no I/O."""
from decimal import Decimal,localcontext
from fractions import Fraction
from uuid import UUID,uuid5
from datetime import datetime
from typing import Literal,TYPE_CHECKING
from pydantic import ValidationError
from app.application.contracts.offer_admission import OfferAdmission
from app.application.offer_admission import term_from_snapshot,missing_offer_fields,omission
from app.application.contracts import import_domains as domains
from app.application.contracts.decision_capture import InventoryScopeDeclaration,CaptureProblem
from app.application.contracts.decision_execution import DecisionPolicy
from app.application.contracts.planning_source_evidence import BoundEvidence
from app.application.use_cases.planning_pipeline import PlanningPipelineDeclarations
from app.application.contracts.procurement import ProcurementOffer,OfferBound,SupplierFee,IngredientCapacity,SupplierLimit
from app.application.operational_import_facts import declaration_dependency,current_fees,inventory_matches
from app.application.planning_fee_bindings import fee_bindings
from app.application.contracts.planning_setup import ResolvedPlanningSetup

if TYPE_CHECKING:
    from app.repositories.readiness import ReadinessFacts


def problem(code,store,field):
    return CaptureProblem(code=code,kind='DATA_BLOCKER',entity='store',entity_id=store,field=field,detail=code.replace('_',' '))


def fee_total(components):
    values=tuple(Decimal(c.amount) for c in components)
    # Money inputs have<=18 fractional/18 integer digits. Choose enough exact
    # coefficient precision for the entire sum, independent of ambient context.
    with localcontext() as context:
        context.prec=40+len(str(max(1,len(values))))
        return sum(values,Decimal(0))


def planning_declarations(resolution: ResolvedPlanningSetup,facts: 'ReadinessFacts',forecast_id: UUID | None,
                          now: datetime,*,run_id: UUID,offer_policy: Literal['offer_eligibility/1'] | None
                          ) -> tuple[PlanningPipelineDeclarations,tuple[CaptureProblem,...],tuple[BoundEvidence,...]]:
    from app.application.readiness_evaluation import latest_declarations,contains
    snap=facts.snapshot;store=resolution.configuration.store_id;start=resolution.request.forecast_start_date
    end=resolution.forecast_end_date;problems=[]
    admission_policy=offer_policy
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
    coverage='COMPLETE' if fee and fee.coverage=='COMPLETE' and (fee.effective_to is None or fee.effective_to>=end) and fee.currency==resolution.budget.currency else 'UNKNOWN'
    if fee and fee.mode!=resolution.configuration.policy.fee_mode:
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
        if cost:bounds.append(int(Fraction(resolution.budget.amount)//cost))
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
        bound_evidence.append(BoundEvidence(term_id=term['id'],effective_budget=resolution.budget.amount,budget_version=resolution.budget_version,
            pack_cost=Decimal(term['pack_cost']),pack_size=Decimal(term['pack_size_base_quantity']),
            source_maximum_quantity=Decimal(source['payload']['maximum_order_base_quantity']) if source and source['payload']['maximum_order_base_quantity'] is not None else None,
            declared_limit_quantity=next((l.maximum_quantity for l in limits if str(l.supplier_id)==term['supplier_id'] and str(l.ingredient_id)==term['ingredient_id']),None),maximum_packs=min(bounds)))
        offers.append(ProcurementOffer(term_id=term['id'],arrival_lot_id=uuid5(run_id,term['id']),
            bound=OfferBound(maximum_packs=min(bounds),source='CAPTURED_SUPPLIER_LIMIT' if declared_bounds else 'TECHNICAL_SEARCH_LIMIT',
                derivation=f'S49-bound/1: floor(accepted effective budget / positive pack cost), intersect captured source maximum and declared supplier limits; budget version {resolution.budget_version}',
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
