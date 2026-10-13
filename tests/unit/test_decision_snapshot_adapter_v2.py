"""Repository mapping tests only; not PostgreSQL acceptance."""
from types import SimpleNamespace
import pytest
from tests.unit.test_decision_snapshot_adapter import repositories
from app.infrastructure.database import decision_capture as old
from app.infrastructure.database import decision_capture_v2 as adapter
from app.application.use_cases.decision_capture_v2 import capture_decision_v2
from scripts.decision_capture_v2_demo_cases import synthetic_case_v2


def wire(repositories,monkeypatch):
    request,facts,source,state,values,lot,line=repositories
    monkeypatch.setattr(adapter,'_execution_session',old._execution_session)
    product=values[(old.CatalogRepository,'get_product')]
    product.name='SYNTHETIC';product.active=True
    def menu(repo,store):
        assert state['session'] and state['connection'] and state['begun']
        return [product]
    monkeypatch.setattr(adapter.CatalogRepository,'list_products',menu)
    return synthetic_case_v2()[0],facts,adapter.PostgresDecisionSnapshotSourceV2(source.engine),state,values,lot,line


def test_v2_owned_mapping_and_detached_facts(repositories,monkeypatch):
    r,f,source,state,values,lot,line=wire(repositories,monkeypatch)
    c=capture_decision_v2(r,source,lambda:f.captured_at)
    assert c.status=='CAPTURED' and c.prepared.capture_version==2
    assert not state['connection'] and not state['session']
    lot.on_hand_quantity=99;line.quantity=888
    assert c.source.facts.lots[0].on_hand_quantity==1
    assert c.prepared.recipes[0].lines[0].quantity==1
    assert [recipe.id for recipe in c.prepared.recipes]==[f.recipes[0].id]
    assert ('list_recipe_versions',(f.products[0].product_id,True)) in state['calls']


def test_v2_malformed_recipe_line_is_product_exclusion(repositories,monkeypatch):
    r,f,source,state,values,lot,line=wire(repositories,monkeypatch);line.quantity=-1
    c=capture_decision_v2(r,source,lambda:f.captured_at)
    assert c.status=='NO_COMPUTABLE_PRODUCTS'
    assert c.exclusions[0].product_id==f.products[0].product_id
    assert 'INVALID_RECIPE_LINE' in {p.code for p in c.problems}
    assert not state['connection'] and not state['session']


def test_v2_malformed_lot_maps_shared_ingredient_not_transport_error(repositories,monkeypatch):
    r,f,source,state,values,lot,line=wire(repositories,monkeypatch);lot.on_hand_quantity=None
    c=capture_decision_v2(r,source,lambda:f.captured_at)
    assert c.status=='NO_COMPUTABLE_PRODUCTS'
    assert any(p.entity=='ingredient' and p.code=='INVALID_SOURCE_ROW' for p in c.exclusions[0].reasons)
    assert not state['connection'] and not state['session']


def test_v2_transport_programming_error_propagates_after_cleanup(repositories,monkeypatch):
    r,f,source,state,values,lot,line=wire(repositories,monkeypatch)
    class Broken:
        @property
        def store_id(self):raise ValueError('Injected repository programming error')
    values[(old.InventoryRepository,'list_lots')]=[Broken()]
    with pytest.raises(ValueError,match='repository programming'):
        capture_decision_v2(r,source,lambda:f.captured_at)
    assert not state['connection'] and not state['session']


def test_v2_invalid_ingredient_scope_identity_preserves_known_dependencies(repositories,monkeypatch):
    r,f,source,state,values,lot,line=wire(repositories,monkeypatch)
    values[(old.CatalogRepository,'list_ingredients')][0].base_unit=''
    c=capture_decision_v2(r,source,lambda:f.captured_at)
    assert c.status=='NO_COMPUTABLE_PRODUCTS'
    assert c.source.ingredient_scope_ids==(f.ingredients[0].ingredient_id,)
    assert c.source.facts.ingredients==()
    assert c.exclusions[0].product_id==f.products[0].product_id
    assert 'INGREDIENT_FACT_UNAVAILABLE' in {p.code for p in c.problems}


def test_v2_invalid_term_keeps_reference_for_known_exclusion(repositories,monkeypatch):
    r,f,source,state,values,lot,line=wire(repositories,monkeypatch)
    values[(old.SupplierRepository,'list_active_supplier_terms')][0].pack_cost=-1
    c=capture_decision_v2(r,source,lambda:f.captured_at)
    assert c.status=='NO_COMPUTABLE_PRODUCTS'
    assert c.source.supplier_term_scope[0].term_id==r.procurement.offers[0].term_id
    assert 'OFFER_SCOPE_INVALID' not in {p.code for p in c.problems}
    assert 'SUPPLIER_TERM_FACT_UNAVAILABLE' in {p.code for p in c.problems}
