"""M2 public Product-ID declarations, reserved scope, Owner review and exact reuse."""
from uuid import UUID, uuid4
import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.models import Product
from app.models.import_staging import ImportBatch, ImportProfileVersion
from tests.integration.test_auth_public import env
from tests.integration.test_import_setup_stock import fresh_store,review_batch,complete
from tests.integration.test_import_staging import csv_source,previewed,post
from tests.integration.test_import_commit import analyzed_files
from tests.integration.test_import_commit import commit
from tests.integration.test_staff_public import staff_env
from tests.integration.test_import_classification import mapping,listing,confirm
from tests.integration.test_import_rule_review import summary,declare_context
from tests.integration.test_import_field_value_bindings import activate
from tests.integration.import_i5_evidence import i5_trace,save

SOURCE=dict(source_system_key='M2-SYNTHETIC',report_type='CATALOG')
RECORDS=[dict(source_business_key='CAT-L',name='Synthetic size L cold',selling_unit='cup',price='20000',active='Source label'),
         dict(source_business_key='CAT-S',name='Synthetic size S hot',selling_unit='cup',price='10000',active='Source label')]
METADATA={r['source_business_key']:{**{k:v for k,v in r.items() if k!='source_business_key'},
    'sku':'SYN-L' if n==0 else None,'active':n==0} for n,r in enumerate(RECORDS)}


def prepared(c):
    ident=analyzed_files(c,[('m2.csv',csv_source('products',RECORDS))])
    review_batch(c,ident,creations={key:('product',value) for key,value in METADATA.items()},
        source_context=SOURCE,approve_profiles=False)
    scope,=summary(c,ident)['product_value_scopes']
    assert not scope['unresolved_tokens'] and len(scope['products'])==2
    assert all(p['reference_state']=='reserved' for p in scope['products'])
    return ident,{p['source_token']:p['product_id'] for p in scope['products']}


def values(c,ident,target,entries,**extra):
    return mapping(c,ident,listing(c,ident)[0],{'resolution':dict(kind='product_values',
        target_field='products.'+target,values=entries,evidence_reference='Explicit synthetic per-Product facts',**extra)})


def payload(ids,target):
    return [dict(product_id=ident,value=METADATA[token][target]) for token,ident in ids.items()]


def test_reserved_mixed_product_values_commit_redeclare_reexport(fresh_store,i5_trace):
    c=fresh_store;ident,ids=prepared(c)
    assert values(c,ident,'sku',payload(ids,'sku')).status_code==200
    conflict=values(c,ident,'active',payload(ids,'active'))
    assert conflict.status_code==409 and conflict.json()['error']['code']=='FIELD_SOURCE_CONFLICT'
    response=values(c,ident,'active',payload(ids,'active'),replace_source_column_index=4,acknowledgment=True)
    assert response.status_code==200 and response.json()['data']['approval_required'],response.text
    proposal,=summary(c,ident)['profile_proposals']
    assert not proposal['missing_fields']
    assert all(r['version']=='product_field_value/1' and 'values' not in r for r in proposal['spec']['shared_field_bindings'])
    assert not summary(c,ident)['can_preview']
    activate(c,ident)
    read=previewed(c,ident)
    assert not read['preview']['summary']['blockers'],read
    confirmed=confirm(c,ident,read)
    assert confirmed.status_code==200,confirmed.text
    update=values(c,ident,'active',payload(ids,'active'))
    assert update.status_code==200 and not update.json()['data']['approval_required'],update.text
    assert commit(c,ident,read,confirmed.json()['data']['import_revision']).status_code==412
    with Session(c[0][1]) as fresh:assert fresh.scalar(select(func.count()).select_from(Product))==0
    read,done=complete(c,ident)
    with Session(c[0][1]) as fresh:
        for token,ident_value in ids.items():
            product=fresh.get(Product,UUID(ident_value)); expected=METADATA[token]
            assert product.store_id==c[1].store_id and product.name==expected['name']
            assert product.sku==expected['sku'] and product.active is expected['active']
        completion=fresh.get(ImportBatch,UUID(ident)).analysis_json['completion']
        assert {r['canonical_id'] for r in completion['canonical_references']}==set(ids.values())
        assert all(r['provenance']['sku']['value_source']=='IMPORT_VALUE'
            and r['provenance']['active']['declaration_id'] for r in completion['canonical_references'])
    second=analyzed_files(c,[('renamed-m2.csv',csv_source('products',RECORDS))])
    declare_context(c,second,SOURCE)
    m=summary(c,second)
    assert m['binding_refs'] and not m['can_preview'] and not m['sheets'][0]['import_values']
    assert {d['target_field'] for d in m['completion_guidance']['declarations']}=={'products.sku','products.active'}
    assert values(c,second,'sku',payload(ids,'sku')).status_code==200
    changed=values(c,second,'active',payload(ids,'active'))
    assert changed.status_code==200 and not changed.json()['data']['approval_required']
    _,again=complete(c,second)
    assert again['outcome']=='no_changes'
    with Session(c[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(Product))==2
        assert fresh.scalar(select(func.count()).select_from(ImportProfileVersion))==1
    save('m2-synthetic',dict(first=done,reexport=again,ids=ids))
    # Same approved rule cannot erase known SKU or change existing metadata.
    third=analyzed_files(c,[('changed-values.csv',csv_source('products',RECORDS))])
    declare_context(c,third,SOURCE)
    altered=payload(ids,'sku'); altered[0]['value']=None
    assert values(c,third,'sku',altered).status_code==200
    assert values(c,third,'active',payload(ids,'active')).status_code==200
    conflicted=previewed(c,third)
    assert not conflicted['preview']['summary']['can_commit']
    assert any(b['code']=='ENTITY_METADATA_CONFLICT' for r in conflicted['preview']['rows'] for b in r['blockers'])
    with Session(c[0][1]) as fresh:
        assert fresh.get(Product,UUID(ids['CAT-L'])).sku=='SYN-L'
        assert fresh.scalar(select(func.count()).select_from(Product))==2


@pytest.mark.parametrize('kind,code',[('missing','PRODUCT_VALUES_MISSING'),('extra','PRODUCT_VALUES_OUT_OF_SCOPE'),
    ('duplicate','PRODUCT_VALUES_DUPLICATE_ID'),('conflicting','PRODUCT_VALUES_CONFLICT')])
def test_product_value_ids_must_cover_current_reserved_scope(fresh_store,kind,code):
    c=fresh_store;ident,ids=prepared(c)
    entries=payload(ids,'active')
    if kind=='missing':entries=entries[:1]
    if kind=='extra':entries.append(dict(product_id=str(uuid4()),value=False))
    if kind in ('duplicate','conflicting'):entries.append({**entries[0],'value':entries[0]['value'] if kind=='duplicate' else not entries[0]['value']})
    response=values(c,ident,'active',entries,replace_source_column_index=4,acknowledgment=True)
    assert response.status_code==409 and response.json()['error']['code']==code,response.text
    with Session(c[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(Product))==0
        batch=fresh.get(ImportBatch,UUID(ident))
        assert not batch.analysis_json['sheets'][0]['import_values']


def test_unresolved_and_foreign_store_product_ids_are_rejected(fresh_store):
    from tests.integration.test_auth_public import provision
    c=fresh_store
    unresolved=analyzed_files(c,[('unresolved.csv',csv_source('products',RECORDS))])
    declare_context(c,unresolved,SOURCE)
    response=values(c,unresolved,'sku',[dict(product_id=str(uuid4()),value=None)])
    assert response.status_code==409 and response.json()['error']['code']=='PRODUCT_IDENTITY_UNRESOLVED',response.text
    other=provision(c[0],existing=c[1].user_id)
    foreign=(c[0],other,c[2],c[3],None)
    facts=dict(name='Foreign Product',selling_unit='cup',sku=None,price='1000',active=False)
    ident=analyzed_files(foreign,[('foreign.csv',csv_source('products',[dict(source_business_key='FOREIGN',**facts)]))])
    review_batch(foreign,ident,creations={'FOREIGN':('product',facts)},source_context=SOURCE)
    complete(foreign,ident)
    with Session(c[0][1]) as fresh:
        foreign_id=fresh.scalar(select(Product.id).where(Product.store_id==other.store_id))
    ident,ids=prepared(c)
    entries=payload(ids,'sku');entries[0]['product_id']=str(foreign_id)
    response=values(c,ident,'sku',entries)
    assert response.status_code==409 and response.json()['error']['code']=='PRODUCT_VALUES_OUT_OF_SCOPE',response.text
    with Session(c[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(Product).where(Product.store_id==c[1].store_id))==0


def test_product_values_staff_cas_revoke_and_no_approval_bypass(staff_env):
    from tests.integration.test_staff_public import create,accept_http,target_session,owner_session
    from tests.integration.test_auth_public import ORIGIN
    from app.application.use_cases.import_staging import ImportStaging
    from app.application.contracts.staff import GrantsRequest
    ctx=staff_env
    grants=tuple(sorted(('import.create','import.upload','import.read','import.analyze','mapping.read','mapping.propose','menu.read')))
    invitation,raw=create(ctx,grants=grants)
    assert accept_http(ctx,invitation,raw).status_code==201
    _,csrf=target_session(ctx)
    service=ImportStaging(ctx[0][2],ctx[0][0]);ctx[0][5].app.state.import_staging=service
    c=(ctx[0],ctx[2],service,{'Origin':ORIGIN,'X-CSRF-Token':csrf},None)
    ident,ids=prepared(c)
    item=listing(c,ident)[0];revision=summary(c,ident)['mapping_revision']
    path='/api/v1/imports/'+ident+'/mappings/'+item['mapping_id']
    body={'resolution':dict(kind='product_values',target_field='products.sku',values=payload(ids,'sku'),evidence_reference='Staff scoped explicit facts')}
    headers={**c[3],'If-Match':'"'+revision+'"','Idempotency-Key':str(uuid4())}
    response=ctx[0][5].patch(path,json=body,headers=headers)
    assert response.status_code==200 and response.json()['data']['approval_required'],response.text
    assert ctx[0][5].patch(path,json=body,headers=headers).json()['data']==response.json()['data']
    assert ctx[0][5].patch(path,json=body,headers={**headers,'Idempotency-Key':str(uuid4())}).status_code==412
    proposal,=summary(c,ident)['profile_proposals']
    denied=post(c,f'/stores/{c[1].store_id}/mapping-profiles/{proposal["profile_id"]}/decisions',
        dict(decision='approve_activate',proposal_revision=proposal['proposal_revision'],expected_active_version=None,reason='Staff cannot approve'),
        match=proposal['lifecycle_revision'])
    assert denied.status_code==403
    owner_session(ctx)
    member=ctx[1].memberships(ctx[4],ctx[2].store_id)[0].items[0]
    ctx[1].replace(ctx[4],ctx[2].store_id,member.membership_id,
        GrantsRequest(grants=tuple(g for g in grants if g!='mapping.propose'),reason='Revoke M2 proposal permission'),
        str(uuid4()),member.version,ctx[5]['X-CSRF-Token'],'m2-revoke')
    target_session(ctx)
    assert ctx[0][5].patch(path,json=body,headers=headers).status_code==403
    with Session(ctx[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(Product))==0
