"""Fake repositories verify adapter mapping/lifecycle; not PostgreSQL evidence."""
from contextlib import contextmanager
from types import SimpleNamespace
import json
from uuid import uuid4
from datetime import timedelta

import pytest

from app.infrastructure.database import decision_capture as adapter
from app.application.use_cases.decision_capture import capture_decision
from app.application.use_cases.decision_pipeline import execute_operational_pipeline
from app.application.forecast_serialization import serialize_prepared
from app.application.decision_snapshot_source import OperationalDataError
from app.infrastructure.procurement_milp import NativeSearch
from scripts.decision_capture_demo_cases import synthetic_case


@pytest.fixture
def repositories(monkeypatch):
    request,facts=synthetic_case();state={'connection':False,'session':False,'begun':False,'options':None,'calls':[]}

    class Connection:
        def __enter__(self): state['connection']=True;return self
        def __exit__(self,*args): state['connection']=False
        def execution_options(self,**options):
            assert not state['begun']
            state['options']=options
            return self
    class Engine:
        def connect(self): return Connection()
    class Session:
        def begin(self):
            assert state['options']==dict(isolation_level='REPEATABLE READ',postgresql_readonly=True)
            state['begun']=True
    @contextmanager
    def owned_session(connection):
        assert state['connection'];state['session']=True
        try: yield Session()
        finally: state['session']=False;state['begun']=False
    monkeypatch.setattr(adapter,'_execution_session',owned_session)

    def row(data): return SimpleNamespace(**data,created_at=facts.captured_at,updated_at=facts.captured_at)
    product=row(dict(id=facts.products[0].product_id,store_id=request.store_id,sku='P0',selling_unit='cup'))
    ingredient=row(dict(id=facts.ingredients[0].ingredient_id,store_id=request.store_id,base_unit='g',expiry_tracking=False))
    recipe=row(facts.recipes[0].model_dump(exclude={'lines'}))
    recipe.assigned=True
    withdrawn=SimpleNamespace(**{**vars(recipe),'id':uuid4(),'assigned':False})
    outside_horizon=SimpleNamespace(**{**vars(recipe),'id':uuid4(),
        'effective_from':facts.forecast.forecast_end_date+timedelta(days=30),'effective_to':None})
    other_store=SimpleNamespace(**{**vars(recipe),'id':uuid4(),'store_id':uuid4()})
    other_product=SimpleNamespace(**{**vars(recipe),'id':uuid4(),'product_id':uuid4()})
    line=row(dict(id=recipe.id,store_id=request.store_id,recipe_id=recipe.id,**facts.recipes[0].lines[0].model_dump()))
    lot=row(facts.lots[0].model_dump());term=row(facts.supplier_terms[0].model_dump())
    supplier=row(dict(id=term.supplier_id,store_id=request.store_id))
    store=row(dict(id=request.store_id,timezone='UTC',currency='VND'))
    forecast=row(facts.forecast.model_dump(exclude={'predictions','retained','retained_digest','execution'}))
    encoded=serialize_prepared(facts.forecast.retained)
    retained=row(dict(id=forecast.id,store_id=request.store_id,prepared_json=json.loads(encoded.canonical_json),
        serialization_version=encoded.serialization_version,digest=encoded.digest))
    values={
        (adapter.StoreRepository,'get_store_by_id'):store,
        (adapter.CatalogRepository,'get_product'):product,
        (adapter.CatalogRepository,'list_ingredients'):[ingredient],
        (adapter.RecipeRepository,'list_recipe_versions'):[recipe,withdrawn,outside_horizon,other_store,other_product],
        (adapter.RecipeRepository,'list_recipe_lines'):[line],
        (adapter.InventoryRepository,'list_lots'):[lot],
        (adapter.SupplierRepository,'list_active_supplier_terms'):[term],
        (adapter.SupplierRepository,'get_supplier'):supplier,
        (adapter.ConstraintsRepository,'list_constraints'):[],
        (adapter.ForecastRepository,'get_forecast_run'):forecast,
        (adapter.ForecastRepository,'list_predictions'):[row(p.model_dump()) for p in facts.forecast.predictions],
        (adapter.ForecastInputRepository,'get_input'):retained,
        (adapter.ForecastExecutionMetadataRepository,'get'):None,
    }
    for cls,method in values:
        if (cls,method)==(adapter.RecipeRepository,'list_recipe_versions'):
            continue
        def read(self,store_id,*args,_key=(cls,method)):
            assert state['begun'] and state['session'] and state['connection']
            assert store_id==request.store_id
            state['calls'].append((_key[1],args))
            return values[_key]
        monkeypatch.setattr(cls,method,read)
    def recipe_versions(self,store_id,product_id,*,assigned_only=False):
        assert state['begun'] and state['session'] and state['connection']
        state['calls'].append(('list_recipe_versions',(product_id,assigned_only)))
        return [r for r in values[(adapter.RecipeRepository,'list_recipe_versions')]
                if r.store_id==store_id and r.product_id==product_id
                and (not assigned_only or r.assigned)]
    monkeypatch.setattr(adapter.RecipeRepository,'list_recipe_versions',recipe_versions)
    return request,facts,adapter.PostgresDecisionSnapshotSource(Engine()),state,values,lot,line


def test_scoped_repository_mapping_detached_before_computation(repositories):
    request,facts,source,state,values,lot,line=repositories
    captured=capture_decision(request,source,lambda:facts.captured_at)
    assert captured.status=='CAPTURED'
    assert not state['session'] and not state['connection']
    assert captured.prepared.lots[0].on_hand_quantity==1
    lot.on_hand_quantity=99;line.quantity=999
    assert captured.prepared.lots[0].on_hand_quantity==1
    assert captured.prepared.recipes[0].lines[0].quantity==1
    assert [r.id for r in captured.prepared.recipes]==[facts.recipes[0].id]
    assert ('list_recipe_versions',(facts.products[0].product_id,True)) in state['calls']
    assert any(call[0]=='list_active_supplier_terms' and call[1][-1]==facts.captured_at.date() for call in state['calls'])


def test_pipeline_solver_sees_adapter_resources_closed(repositories):
    request,facts,source,state,*_=repositories
    def factory(*args):
        assert not state['session'] and not state['connection']
        return NativeSearch(*args)
    result=execute_operational_pipeline(request,source,factory,lambda:facts.captured_at)
    assert result.status=='COMPUTED'


@pytest.mark.parametrize('quantity',[None,-1])
def test_bad_balance_row_is_data_error_and_resources_close(repositories,quantity):
    request,facts,source,state,values,lot,line=repositories
    lot.on_hand_quantity=quantity
    captured=capture_decision(request,source,lambda:facts.captured_at)
    assert captured.status=='DATA_BLOCKED'
    assert captured.problems[0].code=='INVALID_SOURCE_ROW'
    assert captured.problems[0].entity_id==lot.id
    assert not state['session'] and not state['connection']


def test_recipe_fake_filters_scope_and_assignment_with_false_default(repositories):
    request,facts,source,state,values,*_=repositories
    state.update(begun=True,session=True,connection=True)
    try:
        repo=adapter.RecipeRepository(SimpleNamespace())
        rows=values[(adapter.RecipeRepository,'list_recipe_versions')]
        assert repo.list_recipe_versions(request.store_id,facts.products[0].product_id)==rows[:3]
        assert repo.list_recipe_versions(request.store_id,facts.products[0].product_id,assigned_only=True)==[rows[0],rows[2]]
        assert repo.list_recipe_versions(uuid4(),facts.products[0].product_id)==[]
        assert repo.list_recipe_versions(request.store_id,uuid4())==[]
    finally:
        state.update(begun=False,session=False,connection=False)


def test_technical_repository_error_propagates_with_closed_resources(repositories):
    request,facts,source,state,values,lot,line=repositories
    class Broken:
        @property
        def store_id(self): raise RuntimeError('FAULT repository bug')
    values[(adapter.InventoryRepository,'list_lots')]=[Broken()]
    with pytest.raises(RuntimeError,match='repository bug'):
        capture_decision(request,source,lambda:facts.captured_at)
    assert not state['session'] and not state['connection']
