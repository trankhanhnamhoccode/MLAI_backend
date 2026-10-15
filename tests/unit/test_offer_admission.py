"""Version/proof safety for missing offer-local facts, never corrupt/shared inputs."""
from uuid import UUID
import pytest
from pydantic import ValidationError

from app.application.contracts.decision_capture_v2 import OperationalDecisionInputV2,OperationalFactsV2
from app.application.contracts.offer_admission import OfferAdmission
from app.application.contracts.decision_capture import CaptureProblem
from app.application.offer_admission import omission,missing_offer_fields,term_from_snapshot
from app.application.use_cases.decision_capture_v2 import capture_decision_v2
from app.application.planning_serialization import digest,canonical_bytes
from scripts.decision_capture_v2_demo_cases import synthetic_case_v2,SyntheticSnapshotSourceV2
from tests.unit.test_decision_snapshot_adapter_v2 import repositories,wire


def captured(request,facts):
    return capture_decision_v2(request,SyntheticSnapshotSourceV2(facts),lambda:facts.facts.captured_at)


def missing_term():
    request,facts=synthetic_case_v2()
    raw=facts.facts.supplier_terms[0].model_dump()
    omitted=omission(raw,'SUPPLIER_TERM_FACT_UNAVAILABLE',('pack_cost',))
    r=request.model_dump();r['procurement']['offer_admission']=OfferAdmission(omissions=(omitted,)).model_dump()
    r['procurement']['offers']=()
    f=facts.model_dump();f['facts']['supplier_terms']=()
    f['supplier_term_scope'][0]['version']=raw['version']
    return OperationalDecisionInputV2.model_validate(r),OperationalFactsV2.model_validate(f),raw


def test_d2_legacy_serialization_and_projection_remain_byte_identical():
    r,f=synthetic_case_v2();c=captured(r,f)
    assert digest('request',r)=='07dbfa9b2b107db96539c5186a1a619631bfd08f32497a2095e4e2f74ba20fd8'
    assert digest('source',f)=='e74c368cba80ca67e6b98682fc546f9b8da88eeaf9d414a4844547c9d34dc810'
    assert digest('capture',c)=='7e94f7521ff65f1d3e6f6d5a02888b49a1a3fda9a6640cf0aaf924d622bdfb10'
    assert b'offer_admission' not in canonical_bytes(c)
    assert captured(OperationalDecisionInputV2.model_validate_json(r.model_dump_json()),
                    OperationalFactsV2.model_validate_json(f.model_dump_json()))==c


def test_missing_numeric_fact_is_offer_local_not_product_exclusion():
    r,f,_=missing_term();c=captured(r,f)
    assert c.status=='CAPTURED' and not c.exclusions
    assert c.prepared.supplier_terms==() and c.procurement_input.offers==()
    assert {p.code for p in c.problems}=={'OFFER_OMITTED'}
    assert c.request.procurement.offer_admission.omissions[0].version==1


@pytest.mark.parametrize('field,value', [('term_id',UUID(int=888)),('supplier_id',UUID(int=888)),
    ('ingredient_id',UUID(int=888)),('store_id',UUID(int=888)),('version',2)])
def test_conflicting_omission_identity_or_version_blocks_whole_capture(field,value):
    r,f,_=missing_term();data=r.model_dump()
    data['procurement']['offer_admission']['omissions'][0][field]=value
    c=captured(OperationalDecisionInputV2.model_validate(data),f)
    assert c.status=='DATA_BLOCKED' and c.prepared is None
    assert 'OFFER_OMISSION_INVALID' in {p.code for p in c.problems}


def test_missing_term_without_policy_retains_legacy_product_exclusion():
    r,f,_=missing_term();data=r.model_dump();data['procurement'].pop('offer_admission')
    c=captured(OperationalDecisionInputV2.model_validate(data),f)
    assert c.status=='NO_COMPUTABLE_PRODUCTS'
    assert 'SUPPLIER_TERM_FACT_UNAVAILABLE' in {p.code for p in c.exclusions[0].reasons}


@pytest.mark.parametrize('kind',['invalid','unknown'])
def test_omission_never_suppresses_corrupt_fact_or_unknown_attribution(kind):
    r,f,raw=missing_term();data=f.model_dump()
    data['problems']=(CaptureProblem(code='INVALID_SOURCE_ROW',kind='DATA_BLOCKER',
        entity='ingredient' if kind=='invalid' else 'opaque',entity_id=raw['ingredient_id'] if kind=='invalid' else None,
        field='supplier_term',detail='Invalid negative or unknown scope is not absence').model_dump(),)
    c=captured(r,OperationalFactsV2.model_validate(data))
    assert c.status==('NO_COMPUTABLE_PRODUCTS' if kind=='invalid' else 'DATA_BLOCKED')
    assert c.prepared is None


def test_known_recipe_exclusion_keeps_menu_override_while_unknown_graph_blocks():
    from tests.unit.test_decision_pipeline_v2 import pair
    r,f=pair();data=r.model_dump();data['procurement']['offer_admission']=dict(omissions=())
    second=f.catalog[1].product_id
    data['requirements']['paths'][0]['overrides']=[dict(product_id=second,target='1')]
    r=OperationalDecisionInputV2.model_validate(data)
    data=f.model_dump()
    for identity,term in zip(data['supplier_term_scope'],data['facts']['supplier_terms']):identity['version']=term['version']
    data['facts']['recipes']=[x for x in data['facts']['recipes'] if x['product_id']!=second]
    c=captured(r,OperationalFactsV2.model_validate(data))
    assert len(c.menu)==2 and len(c.computed_product_ids)==1
    assert c.exclusions[0].product_id==second and len(c.exclusions[0].affected_dates)==7
    assert c.override_assessments[0].status=='NOT_EVALUATED'
    assert c.request.requirements.paths[0].overrides[0].product_id==second
    data=f.model_dump()
    for identity,term in zip(data['supplier_term_scope'],data['facts']['supplier_terms']):identity['version']=term['version']
    data['facts']['recipes'][0]['lines'][0]['ingredient_id']=UUID(int=5555)
    c=captured(r,OperationalFactsV2.model_validate(data))
    assert c.status=='DATA_BLOCKED' and c.prepared is None
    assert 'SOURCE_FAILURE_SCOPE_UNKNOWN' in {p.code for p in c.problems}


@pytest.mark.parametrize('missing,invalid', [('pack_cost',False),('lead_time_days',False),('pack_cost',True)])
def test_missing_scalar_recognition_does_not_cover_invalid_remaining_fields(missing,invalid):
    _,f=synthetic_case_v2();data=f.facts.supplier_terms[0].model_dump();data[missing]=None
    if invalid:data['pack_size_base_quantity']='-1'
    with pytest.raises(ValidationError) as error:term_from_snapshot(data)
    assert missing_offer_fields(data,error.value)==(() if invalid else (missing,))


def test_duplicate_omission_is_conflict_not_deduplicated():
    r,_,_=missing_term();o=r.procurement.offer_admission.omissions[0]
    with pytest.raises(ValidationError):OfferAdmission(omissions=(o,o))


@pytest.mark.parametrize('value,expected',[(None,'CAPTURED'),(-1,'NO_COMPUTABLE_PRODUCTS')])
def test_repository_missing_scalar_is_distinct_from_invalid_value(repositories,monkeypatch,value,expected):
    from app.infrastructure.database import decision_capture as adapter
    request,facts,source,_,rows,_,_=wire(repositories,monkeypatch)
    term=rows[(adapter.SupplierRepository,'list_active_supplier_terms')][0]
    rows[(adapter.SupplierRepository,'get_supplier')].active=True
    raw=vars(term).copy()
    data=request.model_dump()
    data['procurement']['offer_admission']=OfferAdmission(omissions=(
        omission(raw,'SUPPLIER_TERM_FACT_UNAVAILABLE',('pack_cost',)),)).model_dump()
    data['procurement']['offers']=()
    term.pack_cost=value
    result=capture_decision_v2(OperationalDecisionInputV2.model_validate(data),source,lambda:facts.captured_at)
    assert result.status==expected
    assert result.source.supplier_term_scope[0].version==raw['version']
    if value is None:
        assert result.source.facts.supplier_terms==() and result.exclusions==()
    else:
        assert 'INVALID_SOURCE_ROW' in {p.code for p in result.exclusions[0].reasons}


def test_known_inactive_supplier_scope_matches_public_capture(repositories,monkeypatch):
    from app.infrastructure.database import decision_capture as adapter
    request,facts,source,_,rows,_,_=wire(repositories,monkeypatch)
    rows[(adapter.SupplierRepository,'get_supplier')].active=False
    data=request.model_dump();data['procurement']['offer_admission']=dict(omissions=())
    data['procurement']['offers']=()
    result=capture_decision_v2(OperationalDecisionInputV2.model_validate(data),source,lambda:facts.captured_at)
    assert result.status=='CAPTURED' and result.source.supplier_term_scope==()


def test_shared_unknown_and_safety_constraint_survive_local_omission():
    r,f,raw=missing_term()
    data=r.model_dump();data['procurement']['capacity_state']='UNKNOWN'
    c=captured(OperationalDecisionInputV2.model_validate(data),f)
    assert c.status=='DATA_BLOCKED' and 'LIMIT_CONFIGURATION_UNKNOWN' in {p.code for p in c.problems}
    from app.application.use_cases.decision_pipeline_v2 import execute_captured_pipeline_v2
    from tests.unit.test_procurement_v2 import NoCandidate
    data=f.model_dump();data['facts']['constraints']=[dict(id=UUID(int=333),store_id=r.store_id,version=1,
        kind='MIN_SAFETY_STOCK',ingredient_id=raw['ingredient_id'],value='0',unit=raw['unit'],
        effective_from=raw['effective_from'],effective_to=None)]
    c=captured(r,OperationalFactsV2.model_validate(data))
    result=execute_captured_pipeline_v2(c,NoCandidate)
    assert result.outcome=='COMPUTATION_BLOCKED'
    assert any(x.kind=='MIN_SAFETY_STOCK' for x in result.capture.prepared.constraints)
    assert result.procurement is None  # Existing decision preflight blocks before solver.


@pytest.mark.parametrize('kind',['exact','absent','foreign','multiple'])
def test_existing_source_confirmation_pins_actor_only_from_unique_exact_audit(kind):
    from app.application.planning_source_proof import source_confirmation
    from datetime import datetime,timezone
    identifier=str(UUID(int=21));row_id=str(UUID(int=22));store=str(UUID(int=23));actor=UUID(int=24)
    row=dict(store_id=store,source_system_key='source',source_record_key='record',
        provenance=dict(row=dict(row_id=row_id),spec=dict(version='immutable-v1')))
    audit=dict(id=str(UUID(int=25)),store_id=store,actor_id=str(actor),occurred_at=datetime(2026,10,10,tzinfo=timezone.utc),
        record_json=dict(completion=dict(canonical_references=[dict(canonical_id=identifier,row_id=row_id)])))
    audits=[] if kind=='absent' else [dict(audit,store_id=str(UUID(int=30)))] if kind=='foreign' else [audit,audit] if kind=='multiple' else [audit]
    proof=source_confirmation('supplier_term',identifier,row,audits)
    assert proof.provenance_digest and proof.source_record_key=='record'
    assert proof.actor_id==(actor if kind=='exact' else None)
    assert (proof.audit_id is not None)==(kind=='exact')
