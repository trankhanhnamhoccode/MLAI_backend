from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.application.contracts.decision_capture import OperationalFacts, OperationalDecisionInput
from app.application.use_cases.decision_capture import capture_decision
from app.application.use_cases.decision_pipeline import execute_operational_pipeline
from app.application.procurement_solver import SolverProposal
from app.application.contracts.procurement import SolverEvidence
from app.infrastructure.procurement_milp import NativeSearch
from scripts.decision_capture_demo_cases import synthetic_case, SyntheticSnapshotSource


def capture(request, facts):
    return capture_decision(request, SyntheticSnapshotSource(facts), lambda: facts.captured_at)


def forbidden(*args):
    pytest.fail('Blocked capture reached solver')


def pipeline(request, facts, factory=forbidden):
    return execute_operational_pipeline(request, SyntheticSnapshotSource(facts), factory, lambda: facts.captured_at)


def codes(result):
    return {p.code for p in result.problems}


def test_happy_native_repository_port_to_comparison():
    request, facts = synthetic_case()
    result = pipeline(request, facts, NativeSearch)
    assert result.status == 'COMPUTED'
    assert result.capture.status == 'CAPTURED'
    assert result.bom.totals[0].quantity == 2
    assert result.serving.products[0].fulfilled.decimal_view == 1
    assert result.procurement.strategies[0].best_target_met.counts == (1,)
    assert result.comparison.options[0].outlay.total.decimal_view == Decimal('.1')
    assert result.decision_readiness == 'NOT_ASSESSED'
    assert result.capture.request.procurement.provenance.startswith('SYNTHETIC')
    assert result.procurement.input.budget.provenance == request.procurement.budget.provenance


@pytest.mark.parametrize('group', ['products','ingredients','recipes','lots','supplier_terms','constraints','forecast','predictions'])
def test_cross_store_values_block(group):
    request, facts = synthetic_case()
    data = facts.model_dump()
    if group == 'constraints':
        data[group] = [dict(id=UUID(int=6000), store_id=UUID(int=9999), version=1, kind='BUDGET_LIMIT',
            ingredient_id=None, value='5', unit='VND', effective_from=request.cutoff_date)]
    elif group == 'forecast':
        data[group]['store_id'] = UUID(int=9999)
    elif group == 'predictions':
        data['forecast']['predictions'][0]['store_id'] = UUID(int=9999)
    else:
        data[group][0]['store_id'] = UUID(int=9999)
    result = pipeline(request, OperationalFacts.model_validate(data))
    assert result.status == 'DATA_BLOCKED' and result.procurement is None
    assert any('STORE' in p.code or 'SCOPE' in p.code for p in result.capture.problems)


@pytest.mark.parametrize('mutation,code', [
    ('running','FORECAST_NOT_COMPLETED'), ('missing','FORECAST_COVERAGE_INVALID'),
    ('duplicate','FORECAST_COVERAGE_INVALID'), ('extra','FORECAST_COVERAGE_INVALID'),
    ('legacy','FORECAST_UNIT_PROVENANCE_UNAVAILABLE'), ('hash','FORECAST_INPUT_INTEGRITY_MISMATCH'),
    ('unit_drift','FORECAST_PRODUCT_UNIT_DRIFT'), ('window','FORECAST_WINDOW_MISMATCH'),
])
def test_forecast_invalid(mutation, code):
    request, facts = synthetic_case()
    data = facts.model_dump(); f = data['forecast']; points = list(f['predictions'])
    if mutation == 'running': f['status'] = 'RUNNING'
    elif mutation == 'missing': f['predictions'] = points[:-1]
    elif mutation == 'duplicate': f['predictions'] = points + [points[0]]
    elif mutation == 'extra': f['predictions'] = points + [points[0] | {'forecast_date':request.cutoff_date}]
    elif mutation == 'legacy': f['retained'] = None
    elif mutation == 'hash': f['retained_digest'] = 'wrong'
    elif mutation == 'unit_drift': data['products'][0]['selling_unit'] = 'piece'
    else: f['forecast_end_date'] = request.cutoff_date
    result = pipeline(request, OperationalFacts.model_validate(data))
    assert result.status == 'DATA_BLOCKED' and code in codes(result.capture)


def test_dated_recipe_capture_units_order_and_detachment():
    request, facts = synthetic_case()
    data = facts.model_dump(); recipe = data['recipes'][0]
    switch = request.cutoff_date + timedelta(days=4)
    recipe['effective_to'] = switch - timedelta(days=1)
    later = deepcopy(recipe); later.update(id=UUID(int=888),version=2,effective_from=switch,effective_to=None)
    later['lines'][0]['quantity'] = '2'
    data['recipes'] = (later, recipe)
    source = SyntheticSnapshotSource(OperationalFacts.model_validate(data))
    result = capture_decision(request, source, lambda: facts.captured_at)
    assert result.status == 'CAPTURED'
    from app.application.use_cases.bom import expand_bom
    bom = expand_bom(result.prepared)
    assert [r.quantity for r in bom.contributions[:7]] == [2,0,0,0,0,0,0]
    assert bom.contributions[3].recipe_id == UUID(int=888)
    saved = result.model_dump()
    data['recipes'][0]['lines'][0]['quantity'] = '999'
    source.facts = facts
    assert result.model_dump() == saved
    assert all(r.unit == 'g' for r in result.prepared.recipes[1].lines)


@pytest.mark.parametrize('mode', ['gap','empty','overlap','wrong_unit'])
def test_recipe_errors_stop_solver(mode):
    request, facts = synthetic_case(); data = facts.model_dump()
    recipe = data['recipes'][0]
    if mode == 'gap': data['recipes'] = ()
    elif mode == 'empty': recipe['lines'] = ()
    elif mode == 'overlap': data['recipes'] = (recipe, recipe | {'id':UUID(int=888),'version':2})
    else: recipe['lines'][0]['unit'] = 'kg'
    result = pipeline(request, OperationalFacts.model_validate(data))
    assert result.status == 'DATA_BLOCKED'
    assert ('MISSING_RECIPE' if mode in ('gap','empty') else 'RECIPE_OVERLAP' if mode == 'overlap' else 'SNAPSHOT_SEMANTICS_INVALID') in codes(result.capture)


def test_missing_lot_balance_distinct_from_zero_and_confirmed_empty():
    request, facts = synthetic_case()
    no_lots = facts.model_copy(update={'lots':()})
    assert 'INVENTORY_BALANCE_MISSING' in codes(capture(request, no_lots))
    zero = facts.model_dump(); zero['lots'][0]['on_hand_quantity'] = '0'
    assert capture(request, OperationalFacts.model_validate(zero)).status == 'CAPTURED'
    r = request.model_dump(); r['inventory_scope'][0]['state'] = 'CONFIRMED_EMPTY'
    empty_request = OperationalDecisionInput.model_validate(r)
    assert capture(empty_request, no_lots).status == 'CAPTURED'
    assert 'INVENTORY_DECLARATION_CONFLICT' in codes(capture(empty_request, facts))


@pytest.mark.parametrize('value', [None,'-1','NaN','Infinity',True,0.5])
def test_invalid_copied_balance_revalidated(value):
    request, facts = synthetic_case()
    lot = facts.lots[0].model_copy(update={'on_hand_quantity':value})
    invalid = facts.model_copy(update={'lots':(lot,)})
    assert 'INVALID_OPERATIONAL_FACT' in codes(pipeline(request, invalid).capture)


def test_future_and_expired_lots_preserved_but_not_consumed():
    request, facts = synthetic_case(); data = facts.model_dump()
    day = facts.captured_at.date(); lot = data['lots'][0]
    lot.update(received_date=day+timedelta(days=1), expiry_date=day+timedelta(days=3), on_hand_quantity='100')
    expired = lot | {'id':UUID(int=4444),'received_date':day-timedelta(days=3),'expiry_date':day-timedelta(days=1)}
    data['lots'] = (lot,expired)
    result = pipeline(request, OperationalFacts.model_validate(data), NativeSearch)
    assert {'FUTURE_RECEIPT_NOT_INBOUND','EXPIRED_OPERATIONAL_LOT'} <= codes(result.capture)
    assert len(result.capture.prepared.lots) == 2
    assert all(r.fulfilled.decimal_view == 0 for r in result.serving.products)
    assert result.procurement.strategies[0].best_target_met.counts == (2,)


@pytest.mark.parametrize('field,state', [('committed_inbound_state','PRESENT_UNSUPPORTED'),('committed_inbound_state','UNKNOWN')])
def test_committed_inbound_is_not_hypothetical_stock(field,state):
    request, facts = synthetic_case()
    request = OperationalDecisionInput.model_validate(request.model_dump() | {field:state})
    assert 'COMMITTED_INBOUND_UNSUPPORTED' in codes(pipeline(request,facts).capture)


def test_past_origin_is_not_historical_inventory_capture():
    request, facts = synthetic_case()
    facts = facts.model_copy(update={'captured_at':facts.captured_at+timedelta(days=1)})
    assert 'CURRENT_CAPTURE_DATE_MISMATCH' in codes(pipeline(request,facts).capture)


@pytest.mark.parametrize('problem', ['unknown_budget','missing_fee','missing_offer','unknown_capacity','safety'])
def test_procurement_preflight_blocks_before_solver(problem):
    request, facts = synthetic_case(); r=request.model_dump(); data=facts.model_dump()
    config=r['procurement']
    if problem == 'unknown_budget': config['budget'].update(state='UNKNOWN',amount=None)
    elif problem == 'missing_fee': config['policy']['fee_mode']='PER_OFFER'
    elif problem == 'missing_offer': config['offers'][0]['term_id']=UUID(int=999)
    elif problem == 'unknown_capacity': config['capacity_state']='UNKNOWN'
    else: data['constraints']=(dict(id=UUID(int=8888),store_id=request.store_id,version=1,kind='MIN_SAFETY_STOCK',
        ingredient_id=facts.ingredients[0].ingredient_id,value='1',unit='g',effective_from=request.cutoff_date),)
    result=pipeline(OperationalDecisionInput.model_validate(r),OperationalFacts.model_validate(data))
    assert result.status in ('DATA_BLOCKED','COMPUTATION_BLOCKED') and result.procurement is None


class LimitSearch:
    """Fault injection tests propagation only; no native timeout claim."""
    def __init__(self, counts): self.counts=counts
    def solve(self,rule,phase,deadline):
        return SolverProposal(SolverEvidence(phase=phase,status=1,message='FAULT LIMIT',incumbent=self.counts is not None,
            objective=None,bound=None,gap=None,nodes=None,seconds=0,variables=1,constraints=1,
            solver_version='FAULT',time_limit=1),self.counts)
    def exclude(self,*args,**kwargs): pass


@pytest.mark.parametrize('counts', [(1,),None])
def test_incomplete_and_unknown_propagate_without_fake_plan(counts):
    request,facts=synthetic_case()
    result=pipeline(request,facts,lambda *args:LimitSearch(counts))
    assert result.procurement.execution=='INCOMPLETE'
    for outcome in result.comparison.outcomes:
        assert outcome.execution=='INCOMPLETE' and outcome.proof=='UNPROVEN'
        assert outcome.target_feasibility==('PASS_EXISTS' if counts else 'UNKNOWN')
    assert result.decision_readiness=='NOT_ASSESSED'


def test_capture_transport_and_programming_errors_remain_exceptions():
    request,facts=synthetic_case()
    class BrokenSource:
        def read(self,*args): raise ValueError('programming failure')
    with pytest.raises(ValueError, match='programming failure'):
        execute_operational_pipeline(request,BrokenSource(),forbidden)


def test_no_valid_candidate_stays_absent_not_fake_zero_purchase():
    request,facts=synthetic_case();r=request.model_dump()
    r['procurement']['capacity_state']='DECLARED'
    r['procurement']['capacities']=(dict(store_id=request.store_id,ingredient_id=facts.ingredients[0].ingredient_id,
        unit='g',maximum_quantity='0',checkpoint='POST_RECEIPT_PRE_EXPIRY_PRE_CONSUMPTION',
        provenance='SYNTHETIC zero capacity conflicts with positive operational stock'),)
    result=pipeline(OperationalDecisionInput.model_validate(r),facts,lambda *args:LimitSearch(None))
    assert result.comparison.options==()
    assert all(row.best_available is None and row.best_target_met is None for row in result.procurement.strategies)
    assert all(row.target_feasibility=='UNKNOWN' for row in result.comparison.outcomes)


def test_solver_programming_error_remains_execution_error_with_evidence():
    request,facts=synthetic_case()
    def broken(*args): raise ValueError('FAULT programming bug')
    result=pipeline(request,facts,broken)
    assert result.status=='EXECUTION_ERROR' and result.procurement.execution=='ERROR'
    assert all(row.target_feasibility=='UNKNOWN' for row in result.comparison.outcomes)
    assert result.comparison.options  # Exact-valid baseline preserved, never success/infeasible.


def test_invalid_constructed_request_revalidated_before_source():
    request,facts=synthetic_case(); source=SyntheticSnapshotSource(facts)
    with pytest.raises(ValidationError):
        capture_decision(request.model_copy(update={'product_ids':()}),source)
    assert source.reads==0


def test_forecast_warning_and_execution_provenance_retained():
    request,facts=synthetic_case();data=facts.model_dump()
    data['forecast']['execution']=dict(selection_reason='BASELINE_SELECTED',warnings=(dict(code='BASELINE_FALLBACK',
        severity='WARNING',field='model_type',entity='forecast_run',impact='SYNTHETIC model not superior'),))
    result=capture(request,OperationalFacts.model_validate(data))
    assert result.status=='CAPTURED'
    assert result.forecast_provenance.execution.selection_reason=='BASELINE_SELECTED'
    assert result.prepared.forecast.warnings[0].code=='BASELINE_FALLBACK'
    assert result.forecast_provenance.training_end_date==request.cutoff_date


def test_overlapping_supplier_terms_rejected():
    request,facts=synthetic_case();data=facts.model_dump()
    data['supplier_terms']=data['supplier_terms']+(data['supplier_terms'][0]|{'id':UUID(int=3333),'version':2},)
    result=pipeline(request,OperationalFacts.model_validate(data))
    assert 'SUPPLIER_TERM_OVERLAP' in codes(result.capture)


def test_future_forecast_completion_and_timezone_drift_block():
    request,facts=synthetic_case();data=facts.model_dump()
    data['forecast']['completed_at']=facts.captured_at+timedelta(seconds=1)
    assert 'FORECAST_COMPLETION_AFTER_CAPTURE' in codes(capture(request,OperationalFacts.model_validate(data)))
    data=facts.model_dump();data['store']['timezone']='Asia/Ho_Chi_Minh'
    assert 'FORECAST_TIMEZONE_DRIFT' in codes(capture(request,OperationalFacts.model_validate(data)))
