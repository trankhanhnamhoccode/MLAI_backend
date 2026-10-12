from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal, localcontext
from uuid import uuid4
import json
import pytest
from pydantic import ValidationError
from app.application.planning_serialization import canonical_bytes, exact_json, request_digest, decimal_text, digest
from app.application.contracts.planning_setup import PlanningRequest
from app.application.contracts.planning_run import PlanningRunRecord, PlanningClaim, outcome_mapping
from app.infrastructure.planning_process import current_process, liveness
from tests.planning_persistence_cases import case, computation


def custom():
    return dict(requirements_mode='custom',forecast_start_date='2026-10-08',
        requirements=dict(paths=[dict(path='BASE',min_fill_rate_percent='95',product_overrides=[])]))


def test_request_identity_object_order_numeric_equivalence_and_array_order():
    a=custom();b=deepcopy(a)
    b['requirements']['paths'][0]['min_fill_rate_percent']='95.0'
    assert request_digest(a)==request_digest(dict(reversed(list(b.items()))))
    a['requirements']['paths'].append(dict(path='HIGH',min_fill_rate_percent='90'))
    b=deepcopy(a);b['requirements']['paths'].reverse()
    assert request_digest(a)!=request_digest(b)


def test_omitted_null_zero_and_empty_preserved_after_json_roundtrip():
    identities=[]
    for budget in ('omitted',None,'0'):
        r=custom()
        if budget!='omitted':r['requirements']['budget_limit']=budget
        typed=PlanningRequest.model_validate(r)
        roundtrip=PlanningRequest.model_validate(json.loads(canonical_bytes(typed)))
        assert typed.model_fields_set==roundtrip.model_fields_set
        assert typed.requirements.model_fields_set==roundtrip.requirements.model_fields_set
        identities.append(request_digest(typed))
    assert len(set(identities))==3
    a=custom();b=deepcopy(a);del b['requirements']['paths'][0]['product_overrides']
    assert request_digest(a)!=request_digest(b)


@pytest.mark.parametrize('value',[95.0,True,'NaN','Infinity','1e2',None])
def test_invalid_request_numeric_never_canonicalized(value):
    r=custom();r['requirements']['paths'][0]['min_fill_rate_percent']=value
    with pytest.raises(ValidationError):request_digest(r)


def test_exact_decimal_identity_independent_of_context_and_extreme_exponents():
    with localcontext() as c:
        c.prec=2
        assert decimal_text(Decimal('95.000'))=='95e0'
        assert decimal_text(Decimal('-0.000'))=='0'
        values=[Decimal('12345678901234567890.000000000123'),Decimal('1e-1000000'),Decimal('1e1000000')]
        for value in values:assert Decimal(exact_json(value))==value
    with pytest.raises(ValueError):decimal_text(Decimal('NaN'))


@pytest.mark.parametrize('kind,expected',[
    ('stock',('completed','recommendation_available')),('purchase',('completed','recommendation_available')),
    ('infeasible',('completed','no_eligible_candidate')),('blocked',('completed','computation_blocked')),
    ('empty',('completed','no_computable_products')),('numeric',('completed','computation_blocked')),
    ('partial',('failed','execution_error'))])
def test_actual_pipeline_mapping_and_exact_roundtrip(kind,expected):
    request,resolution,declarations,capture,result=computation(kind)
    assert outcome_mapping(result)==expected
    now=datetime.now(timezone.utc)
    record=PlanningRunRecord(run_id=uuid4(),actor_id=uuid4(),store_id=resolution.configuration.store_id,
        key_digest='0'*64,request_digest=request_digest(request),request=request,resolution=resolution,
        accepted_at=now,status=expected[0],started_at=now,finished_at=now,
        claim=PlanningClaim(token=uuid4(),generation=1,process=current_process()),
        declarations=declarations,capture=capture,input_digest=digest('capture',capture),
        result=result,result_digest=digest('result',result),outcome=expected[1],
        error_code='PIPELINE_EXECUTION_ERROR' if expected[0]=='failed' else None,
        error_summary='Internal failure' if expected[0]=='failed' else None)
    restored=PlanningRunRecord.model_validate(json.loads(canonical_bytes(record)))
    assert canonical_bytes(restored)==canonical_bytes(record)
    if kind=='partial':assert restored.result.selection.winner_token
    if kind=='stock':
        assert restored.result.comparison.options[0].outlay.total.numerator=='0'
        with pytest.raises(ValidationError):
            PlanningRunRecord.model_validate(record.model_copy(update={'input_digest':'f'*64}))
        with pytest.raises(ValidationError):
            PlanningRunRecord.model_validate(record.model_copy(update={'result_digest':'f'*64}))
    bad=record.model_copy(update={'outcome':'no_computable_products'})
    if kind!='empty':
        with pytest.raises(ValidationError):PlanningRunRecord.model_validate(bad)


@pytest.mark.parametrize('field,value',[('storage_version','planning_storage/2'),('package_schema_version',2),
    ('package_schema_version',True),
    ('store_id',uuid4()),('request_digest','f'*64),('status','completed')])
def test_constructed_aggregate_cannot_bypass_revalidation(field,value):
    request,resolution,_,_,_=case()
    record=PlanningRunRecord(run_id=uuid4(),actor_id=uuid4(),store_id=resolution.configuration.store_id,
        key_digest='0'*64,request_digest=request_digest(request),request=request,resolution=resolution,
        accepted_at=datetime.now(timezone.utc),status='queued')
    with pytest.raises(ValidationError):PlanningRunRecord.model_validate(record.model_copy(update={field:value}))


def test_real_local_process_identity_not_a_timeout_and_foreign_host_unknown():
    current=current_process();assert liveness(current)=='ALIVE'
    assert liveness(current.model_copy(update={'birth':current.birth+'different'}))=='DEAD'
    assert liveness(current.model_copy(update={'host':'not-this-machine'}))=='UNKNOWN'


def test_exact_fraction_roundtrip_never_uses_decimal_display_as_identity():
    from app.application.contracts.serving import Quantity as ExactQuantity
    from fractions import Fraction
    from app.domain.decision.quantities import display
    quantity=ExactQuantity(numerator='1',denominator='3',decimal_view=display(Fraction(1,3)))
    restored=ExactQuantity.model_validate(json.loads(canonical_bytes(quantity)))
    assert (restored.numerator,restored.denominator)==('1','3')
    assert restored.decimal_view==quantity.decimal_view


def test_large_internal_counter_is_exact_integer_not_binary_float_or_wire_string():
    count=2**100+1
    retained=json.loads(canonical_bytes({'domain_size':count}))
    assert type(retained['domain_size']) is int and retained['domain_size']==count


def test_pure_captured_boundary_rejects_invalid_copied_capture_before_solver():
    from app.application.use_cases.planning_pipeline import prepare_planning_pipeline
    from app.application.use_cases.decision_capture_v2 import capture_decision_v2
    from app.application.use_cases.decision_pipeline_v2 import execute_captured_pipeline_v2
    request,resolution,decl,source,_=case()
    capture=capture_decision_v2(prepare_planning_pipeline(resolution,decl),source,lambda:source.facts.facts.captured_at)
    invalid=capture.model_copy(update={'status':'DATA_BLOCKED'})
    with pytest.raises(ValidationError):
        execute_captured_pipeline_v2(invalid,lambda *a:pytest.fail('invalid capture must not solve'))
