"""Original July inventory: inspect physical observations without inventing receipts."""
import hashlib
import json
from pathlib import Path
from uuid import UUID

from sqlalchemy import func,select
from sqlalchemy.orm import Session

from app.models import Ingredient,InventoryLot,InventoryMovement
from app.models.operational_import import InventoryReceiptRecord,SupplierSourceRecord,TermSourceRecord
from app.models.import_history import ImportHistoryRecord
from app.models.import_staging import ImportBatch
from tests.integration.test_auth_public import env
from tests.integration.test_import_setup_stock import fresh_store,complete
from tests.integration.test_import_original_recipes import prepare_original_recipes
from tests.integration.test_import_i51_pos_declared import upload_declared_pos
from tests.integration.test_import_classification import listing,mapping
from tests.integration.test_import_field_value_bindings import activate
from tests.integration.test_import_rule_review import summary,declare_context
from tests.integration.test_import_staging import post
from tests.integration.import_i5_evidence import CASES,SOURCE_DIRECTORY,cells_by_sheet,save,i5_trace


def catalog_prerequisites(c,monkeypatch):
    """Current same-Store IDs from real approved Menu/recipe API flows, never SQL seed."""
    c,ident,_,_,_,_,sheet,_,_=prepare_original_recipes(c,monkeypatch)
    declarations=json.loads((Path(__file__).parents[1]/'fixtures/import_recipe_declarations.json').read_text(encoding='utf-8'))
    from tests.integration.test_import_original_recipes import original_recipe
    _,case,sheets=original_recipe();cells=sheets[case['sheets'][0]]
    units={cells[f'B{n}']:cells[f'D{n}'] for n in range(4,23)}
    for item in listing(c,ident):
        if item['sheet_id']==sheet['sheet_id'] and item['issue_type']=='identity' and item['source_location']['source_column_index']==1:
            name=item['source_header']
            response=mapping(c,ident,item,{'resolution':dict(kind='new_entity_proposal',entity='ingredient',source_business_key=name,
                metadata=dict(name=name,base_unit=units[name],**declarations['ingredients_by_full_name'][name]),
                evidence_reference=declarations['evidence'])})
            assert response.status_code==200,response.text
    declare_context(c,ident,dict(source_system_key=declarations['source_system_key'],report_type=declarations['report_type'],
        sales_semantics=None,date_format='EXCEL_SERIAL',recipe_quantity_format='OOXML_FINITE_DECIMAL',
        evidence_reference='Same approved synthetic July08 recipe source; current original cells and explicit metadata'))
    activate(c,ident);complete(c,ident)
    with Session(c[0][1]) as fresh:
        ingredients=fresh.scalars(select(Ingredient).where(Ingredient.store_id==c[1].store_id)).all()
        assert len(ingredients)==10 and len({i.name for i in ingredients})==10
        return {i.name:str(i.id) for i in ingredients}


def original_inventory():
    case=CASES[2];path=SOURCE_DIRECTORY/case['file']
    assert path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest()==case['sha256']
    return path,case,cells_by_sheet(path)


def inspect_inventory(c,path,case,schema,ingredients):
    ident=upload_declared_pos(c,path)
    state=summary(c,ident)
    stock=next(s for s in state['sheets'] if s['name']==case['sheets'][0])
    for sheet in state['sheets']:
        item=next(i for i in listing(c,ident) if i['sheet_id']==sheet['sheet_id'] and i['issue_type']=='classification')
        if sheet['sheet_id']==stock['sheet_id']:
            resolution=dict(kind='sheet_type',sheet_type=schema,reason='Explicit inspection of original stock snapshot; no receipt inference')
        else:
            resolution=dict(kind='sheet_type',sheet_type=None,ignored=True,acknowledgment=True,
                reason='Inventory-only scope; purchase history and vendor terms remain separate raw evidence')
        response=mapping(c,ident,item,{'resolution':resolution});assert response.status_code==200,response.text
    def own(kind):return [i for i in listing(c,ident) if i['sheet_id']==stock['sheet_id'] and i['issue_type']==kind]
    response=mapping(c,ident,own('source_context')[0],{'resolution':dict(kind='source_context',
        source_system_key='USER_SYNTHETIC_STOCK_INSPECTION',report_type='JULY_BASELINE_'+schema.upper(),
        inventory_semantics='lot_stock_count' if schema=='inventory_count' else None,
        date_format='EXCEL_SERIAL',evidence_reference='Inspection proposal only: source is user-created July08 snapshot; no approval of missing time/baseline facts')})
    assert response.status_code==200,response.text
    fields={1:schema+'.ingredient_id',2:schema+('.on_hand' if schema=='inventory_count' else '.quantity'),
        3:schema+'.unit',5:schema+('.lot_id' if schema=='inventory_count' else '.lot_code')}
    if schema=='opening_stock':fields[4]=schema+'.expiry_date'
    for column in range(7):
        item=next(i for i in own('column') if i['source_location']['source_column_index']==column)
        body={'target_field':fields[column]} if column in fields else {'resolution':dict(kind='ignored_optional_field',
            evidence_reference='Raw date-only observation / HSD / location retained; not a fabricated timestamp, count mutation or canonical location')}
        response=mapping(c,ident,item,body);assert response.status_code==200,response.text
    for item in own('identity'):
        if item['source_location']['source_column_index']==1:
            name=item['source_header'];assert name in ingredients
            response=mapping(c,ident,item,{'resolution':dict(kind='identity_binding',canonical_id=ingredients[name])})
            assert response.status_code==200,response.text
    return ident,stock


def test_original_inventory_distinguishes_unknown_lot_count_and_incomplete_opening(fresh_store,monkeypatch,i5_trace):
    c=fresh_store;ingredients=catalog_prerequisites(c,monkeypatch)
    path,case,sheets=original_inventory()
    count_id,count_sheet=inspect_inventory(c,path,case,'inventory_count',ingredients)
    count=summary(c,count_id);proposal,=count['profile_proposals']
    assert not count['can_preview']
    assert {'inventory_count.observed_at','inventory_count.reason'}<=set(proposal['missing_fields'])
    lots=[i for i in listing(c,count_id) if i['sheet_id']==count_sheet['sheet_id'] and i['issue_type']=='identity'
        and i['source_location']['source_column_index']==5]
    assert len(lots)==11 and all(i['status'] not in {'resolved','auto_mapped'} for i in lots)

    ident,sheet=inspect_inventory(c,path,case,'opening_stock',ingredients)
    opening=summary(c,ident);proposal,=opening['profile_proposals']
    assert 'opening_stock.source_record_id' in proposal['missing_fields'] and not opening['can_preview']
    context=next(i for i in listing(c,ident) if i['sheet_id']==sheet['sheet_id'] and i['issue_type']=='source_context')
    unsupported=mapping(c,ident,context,{'resolution':dict(kind='shared_value',scope='IMPORT_VALUE',
        target_field='opening_stock.source_record_id',value='NOT_A_REAL_KEY',evidence_reference='Negative scope probe; must not mutate')})
    assert unsupported.status_code==422 and summary(c,ident)['mapping_revision']==opening['mapping_revision']
    column=next(i for i in listing(c,ident) if i['sheet_id']==sheet['sheet_id'] and i['issue_type']=='column'
        and i['source_location']['source_column_index']==5)
    assert mapping(c,ident,column,{'target_field':'opening_stock.source_record_id'}).status_code==200
    switched=summary(c,ident)['profile_proposals'][0]['missing_fields']
    assert 'opening_stock.lot_code' in switched and 'opening_stock.source_record_id' not in switched
    assert mapping(c,ident,column,{'target_field':'opening_stock.lot_code'}).status_code==200
    state=summary(c,ident);read=c[0][5].get('/api/v1/imports/'+ident).json()['data']
    rejected=post(c,'/imports/'+ident+'/process',dict(phase='preview',mapping_revision=state['mapping_revision']),match=read['import_revision'])
    assert rejected.status_code==409 and rejected.json()['error']['code']=='OWNER_MAPPING_APPROVAL_REQUIRED'
    with Session(c[0][1]) as fresh:
        for model in (InventoryLot,InventoryMovement,InventoryReceiptRecord,ImportHistoryRecord,SupplierSourceRecord,TermSourceRecord):
            assert fresh.scalar(select(func.count()).select_from(model))==0
        batch=fresh.get(ImportBatch,UUID(ident))
        raw=next(s for s in batch.analysis_json['sources'] if s['sheet_id']==sheet['sheet_id'])
        assert len(raw['rows'])==11
        source=sheets[case['sheets'][0]]
        for row in raw['rows']:
            assert {cell['column_index']:cell['raw'] for cell in row['cells']}=={
                i:source.get(f'{letter}{row["row_number"]}') for i,letter in enumerate('ABCDEFG')}
    save('original-inventory-inspection',dict(outcome='BLOCKED_TIME_SEMANTICS_AND_ROW_KEY_REPRESENTATION',
        original_sha256=case['sha256'],ingredient_ids=ingredients,count_missing=count['profile_proposals'][0]['missing_fields'],
        opening_missing=state['profile_proposals'][0]['missing_fields'],single_column_switch_missing=switched,
        raw_stock_rows=11,raw_sheet_names=list(sheets),canonical_lots=0,canonical_movements=0,
        limits='No stock N5/confirmation/commit; date-only is not timestamp; count cannot create missing lots; purchase/vendor out of scope'))
    assert hashlib.sha256(path.read_bytes()).hexdigest()==case['sha256']
