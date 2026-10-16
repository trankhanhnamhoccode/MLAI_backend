"""Reviewed cross-file full-name bindings, independent of catalog source codes/SKUs."""
from uuid import UUID
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.models import Product, SalesDaily
from app.models.import_staging import ImportProfileVersion
from tests.integration.test_auth_public import env
from tests.integration.test_import_setup_stock import fresh_store, review_batch, complete
from tests.integration.test_import_staging import csv_source
from tests.integration.test_import_commit import analyzed_files
from tests.integration.test_import_classification import listing
from tests.integration.test_import_rule_review import summary, declare_context
from tests.integration.test_import_field_value_bindings import activate


def test_full_names_preserve_size_temperature_and_reviewed_reuse_without_matching_codes(fresh_store):
    c=fresh_store
    names=('Sinh tố dâu size L lạnh','Sinh tố dâu size S lạnh','Sinh tố dâu size L nóng')
    records=[dict(source_business_key=f'CATALOG-ONLY-{n}',name=name,selling_unit='cup',
        sku=None,price='15000',active=True) for n,name in enumerate(names)]
    catalog=analyzed_files(c,[('catalog.csv',csv_source('products',records))])
    review_batch(c,catalog,creations={r['source_business_key']:('product',
        {k:v for k,v in r.items() if k!='source_business_key'}) for r in records},
        source_context=dict(source_system_key='CATALOG-NAMES',report_type='CATALOG'))
    complete(c,catalog)
    with Session(c[0][1]) as fresh:
        ids={p.name:p.id for p in fresh.scalars(select(Product))}
        assert set(ids)==set(names) and len(set(ids.values()))==3
        assert all(p.sku is None for p in fresh.scalars(select(Product)))
    # Public Store-scoped menu supplies the full display names for manual review;
    # this test does not pretend M02 already projects identity candidates.
    response=c[0][5].get(f'/api/v1/stores/{c[1].store_id}/products',params={'q':'Sinh tố dâu'})
    assert response.status_code==200,response.text
    assert {r['name'] for r in response.json()['data']['items']}==set(names)
    sales=[dict(product_id=name,sales_date='2026-10-09',quantity=str(n+2),unit='cup',
        business_report_key='FULL-NAMES-REPORT',is_stockout=False) for n,name in enumerate(names)]
    content=csv_source('sales',sales)
    assert b'CATALOG-ONLY' not in content and b'sku' not in content
    context=dict(source_system_key='SALES-NAMES-DIFFERENT-FILE',report_type='DAILY',sales_semantics='daily_total')
    ident=analyzed_files(c,[('sales-by-name.csv',content)])
    # Exact names still need explicit selection/approved profile, never auto-merge.
    declare_context(c,ident,context)
    assert {i['source_header'] for i in listing(c,ident) if i['issue_type']=='identity'}==set(names)
    assert not summary(c,ident)['can_preview']
    review_batch(c,ident,bindings=ids,source_context=context,approve_profiles=False)
    proposal,=summary(c,ident)['profile_proposals']
    assert {r['source_token']:r['canonical_id'] for r in proposal['spec']['identity_rules']}=={
        name:str(ident) for name,ident in ids.items()}
    assert not summary(c,ident)['can_preview']  # Resolved is not approved.
    activate(c,ident)
    complete(c,ident)
    with Session(c[0][1]) as fresh:
        assert {r.product_id:r.quantity for r in fresh.scalars(select(SalesDaily))}=={
            ids[name]:n+2 for n,name in enumerate(names)}
        versions=fresh.scalar(select(func.count()).select_from(ImportProfileVersion))
    second=analyzed_files(c,[('renamed-sales.csv',content)])
    declare_context(c,second,context)  # Select source/reuse before manual remapping.
    assert summary(c,second)['binding_refs'] and summary(c,second)['can_preview']
    assert not [i for i in listing(c,second) if i['issue_type']=='identity'
                and i['status'] not in ('resolved','auto_mapped')]
    _,done=complete(c,second)
    assert done['outcome']=='no_changes'
    for ambiguous in ('Sinh tố dâu','Sinh tố dâu size L','Sinh tố dâu size XL lạnh'):
        partial=analyzed_files(c,[('ambiguous.csv',csv_source('sales',[{**sales[0],'product_id':ambiguous}]))])
        declare_context(c,partial,context)
        assert any(i['source_header']==ambiguous and i['status']=='unmatched'
            for i in listing(c,partial) if i['issue_type']=='identity')
        assert not summary(c,partial)['can_preview']
    with Session(c[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(Product))==3
        assert fresh.scalar(select(func.count()).select_from(SalesDaily))==3
        assert fresh.scalar(select(func.count()).select_from(ImportProfileVersion))==versions
        assert all(p.sku is None for p in fresh.scalars(select(Product)))
