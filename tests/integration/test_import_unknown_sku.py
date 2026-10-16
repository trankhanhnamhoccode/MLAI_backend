"""Batch-scoped explicit unknown SKU through current public review/commit guards."""
from uuid import UUID, uuid4
import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.models import Product
from app.models.import_staging import ImportBatch, ImportProfileVersion
from tests.integration.test_auth_public import env, ORIGIN
from tests.integration.test_staff_public import staff_env
from tests.integration.test_import_setup_stock import fresh_store, review_batch, complete
from tests.integration.test_import_staging import csv_source, post, previewed
from tests.integration.test_import_commit import analyzed_files, commit, finished
from tests.integration.test_import_classification import listing, confirm
from tests.integration.test_import_field_value_bindings import shared, activate, summary
from tests.integration.import_i5_evidence import i5_trace, save

SOURCE = dict(source_system_key='SYNTHETIC_UNKNOWN_SKU',report_type='PRODUCT_CATALOG')
RECORDS = [dict(source_business_key='P-A',name='Synthetic A',selling_unit='cup',price='11000',active=True),
           dict(source_business_key='P-B',name='Synthetic B',selling_unit='box',price='22000',active=False)]


def prepared(context, filename='catalog.csv'):
    ident=analyzed_files(context,[(filename,csv_source('products',RECORDS))])
    review_batch(context,ident,source_context=SOURCE,approve_profiles=False,
        creations={r['source_business_key']:('product',dict(sku=None,
            **{k:v for k,v in r.items() if k != 'source_business_key'})) for r in RECORDS})
    return ident


def test_explicit_unknown_sku_owner_commit_replay_and_each_import_requires_declaration(fresh_store,i5_trace):
    c=fresh_store
    ident=prepared(c)
    proposal,=summary(c,ident)['profile_proposals']
    assert not proposal['missing_fields'] and proposal['spec'] is not None
    with Session(c[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(Product)) == 0
    response=shared(c,ident,'products.sku',None)
    assert response.status_code == 200 and response.json()['data']['approval_required'],response.text
    assert not summary(c,ident)['can_preview']
    decision=activate(c,ident)
    read=previewed(c,ident)
    assert all(r['after']['sku'] is None for r in read['preview']['rows'])
    assert all(r['provenance']['sku']['value_source']=='IMPORT_VALUE'
        and r['provenance']['sku']['declaration_id'] for r in read['preview']['rows'])
    first_confirmation=confirm(c,ident,read)
    assert first_confirmation.status_code == 200,first_confirmation.text
    # Even a replacement declaration of null has its own evidence/revision and
    # invalidates the previous confirmation, without reactivating the same rule.
    changed=shared(c,ident,'products.sku',None)
    assert changed.status_code == 200 and not changed.json()['data']['approval_required'],changed.text
    stale_commit=commit(c,ident,read,first_confirmation.json()['data']['import_revision'])
    assert stale_commit.status_code == 412,stale_commit.text
    with Session(c[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(Product)) == 0
    read=previewed(c,ident)
    confirmed=confirm(c,ident,read)
    assert confirmed.status_code == 200,confirmed.text
    key=str(uuid4())
    accepted=commit(c,ident,read,confirmed.json()['data']['import_revision'],key=key)
    done=finished(c,ident,accepted)
    replay=commit(c,ident,read,confirmed.json()['data']['import_revision'],key=key)
    assert replay.status_code == 202 and replay.json()['data']==accepted.json()['data']
    assert c[2].run_one() is None
    with Session(c[0][1]) as fresh:
        products={p.name:p for p in fresh.scalars(select(Product))}
        assert set(products)=={r['name'] for r in RECORDS}
        ids={p.name:str(p.id) for p in products.values()}
        for r in RECORDS:
            p=products[r['name']]
            assert p.store_id==c[1].store_id and p.sku is None and p.active is r['active']
            assert p.price==int(r['price']) and p.selling_unit==r['selling_unit']
        v=fresh.get(ImportProfileVersion,(UUID(decision['profile_id']),decision['approved_version']))
        assert v.spec_json['shared_field_bindings']==[
            dict(version='field_value/1',scope='IMPORT_VALUE',target_field='products.sku')]
        completion=fresh.get(ImportBatch,UUID(ident)).analysis_json['completion']
        assert {r['canonical_id'] for r in completion['canonical_references']}==set(ids.values())
        assert all(r['provenance']['sku']['source_value'] is None
            and r['provenance']['sku']['value_source']=='IMPORT_VALUE' for r in completion['canonical_references'])
    # Renaming/re-exporting never carries the old batch's declaration forward.
    second=analyzed_files(c,[('renamed.csv',csv_source('products',RECORDS))])
    review_batch(c,second,source_context=SOURCE,approve_profiles=False)
    m=summary(c,second)
    assert m['binding_refs'] and not m['can_preview'] and not m['sheets'][0]['import_values']
    assert any(b['code']=='MISSING_IMPORT_VALUE' for b in m['blockers'])
    response=shared(c,second,'products.sku',None)
    assert response.status_code==200 and not response.json()['data']['approval_required']
    read2,done2=complete(c,second)
    assert done2['outcome']=='no_changes'
    with Session(c[0][1]) as fresh:
        assert {p.name:str(p.id) for p in fresh.scalars(select(Product))}==ids
        assert fresh.scalar(select(func.count()).select_from(ImportProfileVersion))==1
        assert all(p.sku is None for p in fresh.scalars(select(Product)))
    save('m1-unknown-sku',dict(outcome='SYNTHETIC_SCOPE_EXPLICIT_NULL_COMMITTED_NOT_ORIGINAL_MENU',
        first=done,renamed_reexport=done2,canonical_ids=ids))


def test_unknown_sku_cannot_clear_existing_known_sku(fresh_store):
    c=fresh_store
    metadata=dict(name='Synthetic known SKU',selling_unit='cup',sku='KEEP-ME',price='15000',active=False)
    records=[dict(source_business_key='KNOWN',**metadata)]
    first=analyzed_files(c,[('known.csv',csv_source('products',records))])
    review_batch(c,first,creations={'KNOWN':('product',metadata)},source_context=SOURCE)
    complete(c,first)
    with Session(c[0][1]) as fresh:
        product=fresh.scalar(select(Product)); pid=product.id
    content=csv_source('products',[{k:v for k,v in records[0].items() if k!='sku'}])
    second=analyzed_files(c,[('unknown.csv',content)])
    review_batch(c,second,bindings={'KNOWN':pid},source_context=SOURCE,approve_profiles=False)
    assert shared(c,second,'products.sku',None).status_code==200
    activate(c,second)
    read=previewed(c,second)
    assert not read['preview']['summary']['can_commit']
    assert any(b['code']=='ENTITY_METADATA_CONFLICT' for r in read['preview']['rows'] for b in r['blockers'])
    with Session(c[0][1]) as fresh:
        product=fresh.get(Product,pid)
        assert product.sku=='KEEP-ME' and product.active is False
        assert fresh.scalar(select(func.count()).select_from(Product))==1
        assert not fresh.get(ImportBatch,UUID(second)).analysis_json.get('completion')


def test_unknown_sku_current_staff_grants_cas_and_replay_reauthorization(staff_env):
    from tests.integration.test_staff_public import create,accept_http,target_session,owner_session
    from app.application.use_cases.import_staging import ImportStaging
    from app.application.contracts.staff import GrantsRequest
    ctx=staff_env
    grants=tuple(sorted(('import.create','import.upload','import.read','import.analyze','mapping.read','mapping.propose','menu.read')))
    invitation,raw=create(ctx,grants=grants)
    assert accept_http(ctx,invitation,raw).status_code==201
    _,csrf=target_session(ctx)
    service=ImportStaging(ctx[0][2],ctx[0][0])
    ctx[0][5].app.state.import_staging=service
    c=(ctx[0],ctx[2],service,{'Origin':ORIGIN,'X-CSRF-Token':csrf},None)
    ident=prepared(c)
    revision=summary(c,ident)['mapping_revision']
    item=listing(c,ident)[0]
    path='/api/v1/imports/'+ident+'/mappings/'+item['mapping_id']
    body={'resolution':dict(kind='shared_value',target_field='products.sku',scope='IMPORT_VALUE',value=None,
        evidence_reference='Staff explicitly declares unknown SKU for both synthetic records')}
    headers={**c[3],'If-Match':'"'+revision+'"','Idempotency-Key':str(uuid4())}
    response=ctx[0][5].patch(path,json=body,headers=headers)
    assert response.status_code==200 and response.json()['data']['approval_required'],response.text
    assert ctx[0][5].patch(path,json=body,headers=headers).json()['data']==response.json()['data']
    stale=ctx[0][5].patch(path,json=body,headers={**headers,'Idempotency-Key':str(uuid4())})
    assert stale.status_code==412,stale.text
    proposal,=summary(c,ident)['profile_proposals']
    denied=post(c,f'/stores/{ctx[2].store_id}/mapping-profiles/{proposal["profile_id"]}/decisions',
        dict(decision='approve_activate',proposal_revision=proposal['proposal_revision'],
             expected_active_version=None,reason='Staff must not approve'),match=proposal['lifecycle_revision'])
    assert denied.status_code==403,denied.text
    owner_session(ctx)
    member=ctx[1].memberships(ctx[4],ctx[2].store_id)[0].items[0]
    ctx[1].replace(ctx[4],ctx[2].store_id,member.membership_id,
        GrantsRequest(grants=tuple(g for g in grants if g!='mapping.propose'),reason='Revoke proposal permission'),
        str(uuid4()),member.version,ctx[5]['X-CSRF-Token'],'sku-revoke')
    target_session(ctx)
    denied=ctx[0][5].patch(path,json=body,headers=headers)
    assert denied.status_code==403,denied.text
    with Session(ctx[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(Product))==0
        values=fresh.get(ImportBatch,UUID(ident)).analysis_json['sheets'][0]['import_values']
        assert len(values)==1 and values[0]['value'] is None
