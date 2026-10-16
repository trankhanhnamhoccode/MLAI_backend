"""Natural owner workbooks -> public Import -> native BASELINE Planning; no seed facts."""
import json
from pathlib import Path
from datetime import date,datetime
from decimal import Decimal
from uuid import UUID,uuid4
import pytest
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from app.models import Product,Ingredient,Supplier,Recipe,RecipeLine,SalesDaily,InventoryLot,InventoryMovement,SupplierTerm
from app.models.import_history import ImportHistoryRecord
from tests.integration.test_auth_public import env
from tests.integration.test_synthetic_cafe_pipeline import cafe
from tests.integration import test_synthetic_cafe_pipeline as oracle
from tests.integration.test_import_staging import post
from tests.integration.test_import_classification import mapping
from tests.integration.test_import_rule_review import summary
from tests.integration.test_import_setup_stock import complete
from tests.integration.import_i5_evidence import save,i5_trace

ROOT=Path(__file__).parents[1]/'fixtures/synthetic_cafe_human_v1'
MANIFEST=json.loads((ROOT/'manifest.json').read_text(encoding='utf-8'))


def items(c,ident):
    result=[];cursor=None
    while True:
        params={'review_only':'false','limit':100}
        if cursor:params['cursor']=cursor
        response=c[0][5].get('/api/v1/imports/'+ident+'/mappings',params=params)
        assert response.status_code==200,response.text
        wire=response.json();result+=wire['data']['items'];cursor=wire['meta']['pagination']['next_cursor']
        if not cursor:return result


def upload_many(c,files,*,renamed=False):
    ident=post(c,'/stores/'+str(c[1].store_id)+'/imports',{'data_date':str(oracle.CUTOFF)}).json()['data']['import_id']
    response=c[0][5].post('/api/v1/imports/'+ident+'/files',headers={**c[3],'Idempotency-Key':str(uuid4())},
        files=[('files[]',(('ban_xuat_lai_'+f) if renamed else f,(ROOT/f).read_bytes(),'application/octet-stream')) for f in files],
        data={'client_file_ids[]':[str(uuid4()) for _ in files]})
    assert response.status_code==200,response.text
    data=response.json()['data'];file_ids={r['file_id']:f for r,f in zip(data['items'],files,strict=True)}
    response=post(c,'/imports/'+ident+'/analyze',dict(file_set_version=data['file_set_version'],accepted_file_ids=list(file_ids),acknowledged_rejected_client_file_ids=[]),match=data['import_revision'])
    assert response.status_code==202,response.text
    assert c[2].run_one()==UUID(response.json()['data']['job_id'])
    specs={}
    for sheet in summary(c,ident)['sheets']:
        filename=file_ids[sheet['file_id']]
        spec=next(s for s in MANIFEST['files'][filename]['sheets'] if filename.endswith('.csv') or s['sheet']==sheet['name'])
        specs[sheet['sheet_id']]={**spec,'filename':filename}
    columns=[i for i in items(c,ident) if i['issue_type']=='column']
    counts=dict(columns=len(columns),suggested=sum(bool(i['target_field']) for i in columns),
        candidates=sum(not i['target_field'] and bool(i['candidate_targets']) for i in columns),
        unresolved=sum(not i['target_field'] and not i['candidate_targets'] for i in columns))
    return ident,specs,counts


def review(c,ident,specs,creations=None,bindings=None,*,ignore_purchase=False,require_reuse=False):
    creations=dict(creations or {});bindings=bindings or {};actions=[];attempted=set()
    if ignore_purchase:
        for i in items(c,ident):
            spec=specs[i['sheet_id']]
            if spec['filename']=='03_lich_su.xlsx' and spec['schema']=='purchase_history' and i['issue_type']=='classification':
                response=mapping(c,ident,i,{'resolution':dict(kind='sheet_type',sheet_type=None,ignored=True,acknowledgment=True,reason='Ca đủ tồn dùng lịch sử mua riêng trong05; giữ raw03, không nhập hai lần')})
                assert response.status_code==200,response.text
    for _ in range(500):
        pending=[i for i in items(c,ident) if i['status'] not in ('resolved','auto_mapped') and not i['ignored']]
        # Only the build_spec allowlist can be reviewed as a group by Owner.
        pending=[i for i in pending if not (i['issue_type']=='column' and i['suggestion_origin']=='RULE' and i['target_field'] and i['candidate_targets']==[i['target_field']] and
            (i['suggestion_reason'] in ('EXACT_CANONICAL_HEADER','CONTROLLED_HEADER_ALIAS') or 'DATE_CONVENTION_REVIEW' in (i['suggestion_reason'] or '')))]
        if not pending:break
        i=min(pending,key=lambda x:{'source_context':0,'classification':1,'column':2,'identity':3}.get(x['issue_type'],4))
        assert i['mapping_id'] not in attempted,i
        attempted.add(i['mapping_id']);spec=specs[i['sheet_id']];kind=i['issue_type']
        if kind=='source_context':
            resolution=dict(kind='source_context',source_system_key=MANIFEST['source_system_key'],report_type=MANIFEST['report_type'],date_format='EXCEL_SERIAL' if spec['filename'].endswith('.xlsx') else 'ISO',sales_semantics='daily_total',evidence_reference='Explicit fictional Cafe V1; manifest oracle mapping and cutoff')
            body={'resolution':resolution}
        elif kind=='classification':
            body={'resolution':dict(kind='sheet_type',sheet_type=spec['schema'],reason='Owner selects explicit supported workflow; manifest is review aid, not source inference')}
        elif kind=='column':
            index=i['source_location']['source_column_index'];target=spec['schema']+'.'+spec['columns'][index]['field']
            body={'target_field':target}
        elif kind=='identity':
            token=i['source_header']
            if token in creations:
                entity,metadata=creations.pop(token)
                resolution=dict(kind='new_entity_proposal',entity=entity,source_business_key=token,metadata=metadata,evidence_reference='Fictional source metadata, exact full name; never source code to SKU')
            else:
                reserved={e['source_business_key']:e['reserved_canonical_id'] for p in summary(c,ident)['profile_proposals'] for e in (p.get('spec') or {}).get('entity_proposals',())}
                assert token in bindings or token in reserved,(token,i)
                resolution=dict(kind='identity_binding',canonical_id=str(bindings.get(token) or reserved[token]))
            body={'resolution':resolution}
        else:raise AssertionError(i)
        response=mapping(c,ident,i,body);assert response.status_code==200,response.text
        actions.append(dict(issue_type=kind,sheet=spec['sheet'],body=body))
    else:raise AssertionError('Manual completion did not converge')
    current=summary(c,ident)
    if require_reuse:
        assert all(s['classification_origin']=='REUSED' for s in current['sheets'] if not s['ignored']),current
        assert not current['profile_proposals'],current
    for p in current['profile_proposals']:
        assert not p['missing_fields'],p
        response=post(c,f"/stores/{c[1].store_id}/mapping-profiles/{p['profile_id']}/decisions",dict(decision='approve_activate',proposal_revision=p['proposal_revision'],expected_active_version=p['active_version'],reason='Owner reviews full natural-header spec, exact identities and fictional source evidence'),match=p['lifecycle_revision'])
        assert response.status_code==200,response.text
        actions.append(dict(issue_type='profile_approval',profile_id=p['profile_id']))
    return actions


def fresh_compare(c,source):
    with Session(c[0][1]) as s:
        products={r.name:r for r in s.scalars(select(Product))};ingredients={r.name:r for r in s.scalars(select(Ingredient))};suppliers={r.name:r for r in s.scalars(select(Supplier))};lots={r.lot_code:r for r in s.scalars(select(InventoryLot))}
        for schema,records in [('products',products),('ingredients',ingredients),('suppliers',suppliers)]:
            assert set(records)=={r['name'] for r in source[schema]}
            for truth in source[schema]:
                for field,value in truth.items():
                    if not field.startswith('source_'):assert getattr(records[truth['name']],field)==value
        sales={(r.product_id,str(r.sales_date)):(r.quantity,r.is_stockout) for r in s.scalars(select(SalesDaily))}
        assert sales=={(products[r['product_id']].id,r['sales_date']):(Decimal(r['quantity']),r['is_stockout']) for r in source['sales']}
        recipes=list(s.scalars(select(Recipe)));lines=list(s.scalars(select(RecipeLine)))
        assert len(recipes)==4 and len(lines)==16
        for truth in source['recipes']:
            recipe=next(r for r in recipes if r.product_id==products[truth['product_id']].id)
            for field in ('version','yield_quantity','process_loss_rate'):assert getattr(recipe,field)==truth[field]
            assert str(recipe.effective_from)==truth['effective_from'] and recipe.effective_to is None
            line=next(r for r in lines if r.recipe_id==recipe.id and r.ingredient_id==ingredients[truth['ingredient_id']].id)
            assert line.quantity==truth['quantity'] and line.unit==truth['unit']
        assert len(lots)==len(source['opening_stock'])
        for truth in source['opening_stock']:
            lot=lots[truth['lot_code']]
            assert lot.on_hand_quantity==truth['quantity'] and lot.unit_cost==truth['unit_cost']
            assert lot.ingredient_id==ingredients[truth['ingredient_id']].id and lot.supplier_id==suppliers[truth['supplier_id']].id
            assert str(lot.received_date)==truth['received_date'] and (str(lot.expiry_date) if lot.expiry_date else None)==truth['expiry_date']
        terms=list(s.scalars(select(SupplierTerm)));assert len(terms)==5
        for truth in source['supplier_terms']:
            term=next(t for t in terms if t.ingredient_id==ingredients[truth['ingredient_id']].id)
            for field in ('unit','pack_size_base_quantity','pack_cost','lead_time_days','shelf_life_days','active'):assert getattr(term,field)==truth[field]
            assert term.minimum_order_packs==truth['minimum_order_quantity']
        names={str(r.id):r.name for r in list(products.values())+list(ingredients.values())+list(suppliers.values())}
        for domain in ('usage_history','purchase_history'):
            history=list(s.scalars(select(ImportHistoryRecord).where(ImportHistoryRecord.domain==domain)))
            assert len(history)==len(source[domain]) and all(r.version==1 for r in history)
            for record in history:
                truth=next(r for r in source[domain] if r['source_record_key']==record.source_record_key)
                for field,value in truth.items():
                    actual=record.payload[field]
                    if field.endswith('_id') and actual is not None:actual=names[actual]
                    if field.endswith('_at') and value is not None:assert datetime.fromisoformat(actual.replace('Z','+00:00'))==datetime.fromisoformat(value)
                    elif isinstance(value,(int,float)):assert Decimal(str(actual))==Decimal(str(value))
                    else:assert actual==value,(domain,field,actual,value)
        counts={model.__name__:s.scalar(select(func.count()).select_from(model)) for model in (Product,Ingredient,Supplier,Recipe,RecipeLine,SalesDaily,InventoryLot,InventoryMovement,ImportHistoryRecord)}
        return {k:r.id for k,r in products.items()},{k:r.id for k,r in ingredients.items()},{k:r.id for k,r in lots.items()},names,counts


def import_human(c,case):
    config=oracle.DATA['manifest']['scenarios'][case];source=oracle.DATA['workbooks'][config['file']]
    files=['01_danh_muc.xlsx','02_ban_hang.xlsx','03_lich_su.xlsx','05_ca_du_ton.xlsx' if case=='sufficient' else '04_ton_kho.xlsx','08_khai_bao_phi.csv']
    ident,specs,counts=upload_many(c,files)
    creations={}
    for schema,entity,key in [('products','product','source_business_key'),('ingredients','ingredient','source_business_key'),('suppliers','supplier','source_supplier_key')]:
        for r in source[schema]:
            metadata={k:v for k,v in r.items() if k!=key}
            if entity=='product':metadata['price']=str(metadata['price'])
            creations[r['name']]=(entity,metadata)
    actions=review(c,ident,specs,creations,ignore_purchase=case=='sufficient')
    with Session(c[0][1]) as s:
        assert all(s.scalar(select(func.count()).select_from(m))==0 for m in (Product,Ingredient,Supplier,Recipe,SalesDaily,InventoryLot))
    _,done=complete(c,ident);assert done['outcome']=='committed'
    products,ingredients,lots,names,before=fresh_compare(c,source)
    bindings={name:UUID(ident) for ident,name in names.items()}|lots
    scope='10_pham_vi_du_ton.csv' if case=='sufficient' else '09_pham_vi_ca_chinh.csv'
    sid,ss,scounts=upload_many(c,[scope]);actions+=review(c,sid,ss,bindings=bindings);complete(c,sid)
    # Same Store/source, changed transport filename, no canonical addition and no N5.
    replay,rules,replay_counts=upload_many(c,files,renamed=True)
    reused=review(c,replay,rules,bindings=bindings,ignore_purchase=case=='sufficient',require_reuse=True)
    _,again=complete(c,replay);assert again['outcome']=='no_changes'
    assert fresh_compare(c,source)[-1]==before
    save('human-import-'+case,dict(case=case,files=files,declarations=[scope],column_counts_first_analysis=counts,scope_column_counts=scounts,manual_actions=actions,reexport_actions=reused,reexport_column_counts=replay_counts,fresh_counts=before,reexport_outcome=again['outcome'],real_provider_calls=0,bootstrap='Auth/Store only via supported harness; no business seed',hashes=json.loads((ROOT/'hashes.json').read_text(encoding='utf-8'))))
    return config,products,ingredients,lots,ident


@pytest.mark.parametrize('case',['main','sufficient','insufficient_budget'])
def test_human_workbooks_real_import_reexport_and_planning(cafe,case,monkeypatch,i5_trace):
    monkeypatch.setattr(oracle,'import_scenario',import_human)
    def retain(name,data):
        if case=='main':
            result=data['pipeline']['result'];winner=next(o for o in result['options'] if o['option_id']==result['winner_option_id'])
            assert oracle.exact(winner['costs']['total'])==3620000
        save('human-'+name,data)
    monkeypatch.setattr(oracle,'save',retain)
    oracle.verify_pipeline(cafe,case,monkeypatch,i5_trace,train_candidate=False)
