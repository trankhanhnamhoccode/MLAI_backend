"""Historical /2 graphs are checked without executing engine entrypoints."""
import copy
import pytest
from tests.assistant_cases import retained_record, row_for
from app.application.planning_retained_reads import VerifiedPlanningReads
from app.application.contracts.planning_run import PlanningPersistenceError
from app.application.planning_serialization import digest


@pytest.fixture(autouse=True)
def no_engine(monkeypatch):
    import importlib
    def forbidden(*a,**k): raise AssertionError('No engine re-execution on retained read')
    for module,names in (
        ('app.application.use_cases.procurement',('_evaluate','evaluate_procurement_basket','execute_procurement')),
        ('app.application.procurement_v2_validation',('_evaluate',)),
        ('app.application.use_cases.bom',('expand_bom',)),
        ('app.application.use_cases.serving',('simulate_serving',)),
        ('app.domain.decision.serving',('simulate',)),
        ('app.application.use_cases.procurement_selection',('select_winner','selection_facts','compare_procurement_v2')),
    ):
        for name in names: monkeypatch.setattr(importlib.import_module(module),name,forbidden)


@pytest.mark.parametrize('kind',['stock','purchase','infeasible','failed-partial'])
def test_fresh_reader_cold_and_warm_old_graphs(kind):
    row = row_for(retained_record(kind))
    record,view = VerifiedPlanningReads().read(row,evidence=True)
    assert record.result_digest == row.record_json['result_digest']
    assert (view.result.winner_option_id is None) == (kind=='infeasible')
    again,_ = VerifiedPlanningReads().read(row,evidence=True)
    assert again == record


@pytest.mark.parametrize('change',['hash','version','cost','winner','service','bom','journal','proof','identity'])
def test_retained_corruption_even_with_rehashed_envelope(change):
    row = row_for(retained_record('stock'))
    raw = copy.deepcopy(row.record_json)
    if change=='hash': row.record_digest = '0'*64
    elif change=='version': raw['storage_version']='planning_storage/99'
    elif change=='identity': row.store_id = row.actor_id
    else:
        pipeline=raw['result']
        if change=='cost': pipeline['procurement']['strategies'][0]['candidate']['outlay']['numerator']='99'
        if change=='winner': pipeline['selection']['winner_token']=None
        if change=='service': pipeline['comparison']['options'][0]['products'][0]['unit']='foreign-unit'
        if change=='bom': pipeline['bom']['contributions'][0]['quantity']='999e0'
        if change=='journal': pipeline['procurement']['strategies'][0]['journal'][0]['customer_pass']=False
        if change=='proof': pipeline['procurement']['strategies'][0]['search_complete']=False
    row.record_json=raw
    if change!='hash':row.record_digest=digest('aggregate',raw)
    with pytest.raises(PlanningPersistenceError) as error: VerifiedPlanningReads().read(row,evidence=True)
    assert error.value.code == ('UNSUPPORTED_RESULT_VERSION' if change=='version' else 'RESULT_INTEGRITY_UNAVAILABLE')
