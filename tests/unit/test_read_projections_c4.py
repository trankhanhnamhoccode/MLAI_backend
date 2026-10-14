"""Hand-calculated source/action counts, bounded cached cells and local days."""
from datetime import date, timedelta
from uuid import uuid4
import pytest
from app.application.planning_discovery import local_created_range,captured_budget
from app.application.import_read_projection import aggregate,source_effect_row,pinned_sources,planned_effect
from app.application.contracts import import_mapping as dto
from tests.unit.test_import_actual_receipts import rows,receipt


@pytest.mark.parametrize('day,hours',[(date(2026,3,8),23),(date(2026,11,1),25)])
def test_created_date_uses_local_midnights_across_dst(day,hours):
    lower,upper=local_created_range(day,day,'America/New_York')
    assert upper-lower==timedelta(hours=hours)


def test_captured_budget_missing_evidence_differs_from_known_zero():
    assert captured_budget({}).model_dump()==dict(availability='unavailable',limit=None,currency=None)
    assert captured_budget({'resolution':{'budget':{'amount':'0','currency':'VND'}}}).model_dump()==dict(availability='available',limit='0',currency='VND')


def test_aggregate_counts_distinct_actions_and_source_records_with_overlap():
    ingredient=uuid4();row=rows([receipt(ingredient)],ingredient)[0]
    a=row.source_location
    a3=a.model_copy(update={'row_number':3});b=a.model_copy(update={'file_id':uuid4(),'sheet_id':uuid4()})
    row=row.model_copy(update={'source_locations':(a,a3,b)})
    other=row.model_copy(update={'row_id':uuid4(),'source_locations':(),
        'source_location':a.model_copy(update={'row_number':4}),'classification':'CHANGED'})
    sources=[dict(file_id=str(a.file_id),sheet_id=str(a.sheet_id),rows=[{'row_number':i} for i in (2,3,4)]),
        dict(file_id=str(b.file_id),sheet_id=str(b.sheet_id),rows=[{'row_number':2}])]
    batch=aggregate([row,other],sources,dto.PreviewScope())
    left=aggregate([row,other],sources,dto.PreviewScope(file_id=a.file_id))
    right=aggregate([row,other],sources,dto.PreviewScope(file_id=b.file_id))
    assert batch.logical_action_count==2 and batch.raw_source_rows.count==4
    assert left.logical_action_count+right.logical_action_count==3
    selected=aggregate([row,other],sources,dto.PreviewScope(classification='NEW'))
    assert selected.logical_action_count==1 and selected.raw_source_rows.count==3
    assert aggregate([row],None,dto.PreviewScope()).raw_source_rows.count is None


def test_formula_cached_value_display_bound_and_old_preview_unavailable():
    ingredient=uuid4();row=rows([receipt(ingredient)],ingredient)[0];loc=row.source_location
    source=[dict(sheet_id=str(loc.sheet_id),rows=[dict(row_number=loc.row_number,cells=[
        dict(column_index=0,raw='5',kind='numeric',formula=True),
        dict(column_index=1,raw='x'*201,kind='text',formula=False)])])]
    payload=dict(reviewed_sheets=[dict(sheet_id=str(loc.sheet_id),headers=['Cached quantity','Long note'])],read_set_digest='frozen')
    projected=source_effect_row(row,payload,source)
    assert projected.source_cells[0].formula_present and projected.source_cells[0].raw_value=='5'
    assert projected.source_cells[1].raw_value is None and projected.source_evidence_availability=='partial'
    assert 'SOURCE_CELL_DISPLAY_UNAVAILABLE' in {n.code for n in projected.warnings}
    bounded=source_effect_row(row,payload,source,max_cells=1)
    assert bounded.source_cells_truncated and len(bounded.source_cells)==1
    assert pinned_sources(payload,{'sources':source}) is None
    assert source_effect_row(row,payload,None).source_evidence_availability=='unavailable'


def test_recipe_unreserved_identity_and_sales_merge_are_not_fabricated():
    from app.application.contracts.import_domains import RecipeValue,SalesSource
    ingredient=uuid4();row=rows([receipt(ingredient)],ingredient)[0]
    recipe=RecipeValue(product_id=uuid4(),version=1,effective_from=date(2026,10,10),effective_to=None,
        yield_quantity='1',yield_unit='cup',process_loss_rate='0',lines=())
    recipe_row=row.model_copy(update={'after':recipe,'receipt_effect':None,'target_reserved_or_existing_id':None})
    effect=planned_effect(recipe_row,'frozen')
    assert effect.recipe_id is None and effect.identity_availability=='not_reserved'
    sales=SalesSource(product_id=recipe.product_id,sales_date=date(2026,10,10),quantity='8',unit='cup',business_report_key='synthetic')
    merged=row.model_copy(update={'after':sales,'receipt_effect':None,'before':None,'proposed_action':'MERGE_DISJOINT_SALES'})
    assert planned_effect(merged,'frozen').action=='merge'


def test_preview_sensitive_permissions_remain_pinned_and_empty_file_is_known():
    from types import SimpleNamespace
    from app.application.use_cases.import_staging import ImportStaging
    from app.application.import_read_projection import mapping_selection
    from app.application.contracts.auth import AuthError
    preview=SimpleNamespace(content_json=dict(source_read_permissions=['procurement.cost.read'],
        read_set={'_captured_schemas':['inventory_receipts']},rows=[]))
    with pytest.raises(AuthError) as failure:
        ImportStaging._preview_read_authority(preview,('ingredient.read','inventory.read'))
    assert failure.value.code=='PERMISSION_DENIED'
    empty_file=uuid4()
    chosen,counters=mapping_selection([],[],dto.MappingCounterScope(file_id=empty_file),file_ids=[empty_file])
    assert not chosen and counters.filtered.total==0


def test_blocked_receipt_keeps_typed_blocked_effect_without_claiming_a_write():
    ingredient=uuid4();row=rows([receipt(ingredient)],ingredient)[0]
    row=row.model_copy(update={'blockers':(dto.Notice(code='RECEIPT_IDENTITY_CONFLICT',severity='ERROR',message='Explicit conflict'),),
        'receipt_effect':row.receipt_effect.model_copy(update={'action':'BLOCKED','conflict_code':'RECEIPT_IDENTITY_CONFLICT'})})
    effect=planned_effect(row,'frozen')
    assert effect.kind=='receipt' and effect.action=='BLOCKED' and effect.conflict_code=='RECEIPT_IDENTITY_CONFLICT'


def test_opening_replay_uses_retained_zero_planned_inventory_delta():
    from app.application.contracts.import_domains import OpeningValue
    ingredient=uuid4();row=rows([receipt(ingredient)],ingredient)[0]
    opening=OpeningValue(**receipt(ingredient,quantity='10'),lot_id=uuid4())
    current=dto.InventoryEffect(origin='OPENING_STOCK',lot_id=opening.lot_id,before_quantity='8',after_quantity='8',
        quantity_delta='0',movement_type=None,unit='l',observed_at=opening.observed_at)
    row=row.model_copy(update={'after':opening,'receipt_effect':None,'inventory_effect':current,'proposed_action':'NO_OP'})
    assert planned_effect(row,'frozen').quantity_delta=='0'
