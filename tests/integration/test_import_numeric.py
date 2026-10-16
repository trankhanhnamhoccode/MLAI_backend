"""Independent numeric format lifecycle, using public master import prerequisites."""
from decimal import Decimal
from datetime import date
from uuid import UUID, uuid4
from xml.sax.saxutils import escape

import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models import Product, Ingredient, Recipe, RecipeLine
from tests.integration.test_auth_public import env
from tests.integration.test_import_setup_stock import fresh_store, review_batch, complete
from tests.integration.test_import_staging import csv_source, post, previewed
from tests.integration.test_import_commit import analyzed_files, commit, finished
from tests.integration.test_import_rule_review import summary, declare_context
from tests.integration.test_import_field_value_bindings import activate
from tests.integration.test_import_classification import mapping, listing, confirm
from tests.unit.test_import_parser import workbook
from app.domain.demand.bom import DemandPoint, DatedRecipe, RecipeLine as BOMLine, expand_dated_bom


CONTEXT=dict(source_system_key='INDEPENDENT-NUMERIC', report_type='RECIPES',sales_semantics=None)


def catalog(c):
    p=dict(name='Independent cold size L',selling_unit='cup',price='100',active=True)
    i=dict(name='Independent liquid',base_unit='ml',active=True,expiry_tracking=False)
    ident=analyzed_files(c,[('product.csv',csv_source('products',[dict(source_business_key='FULL-NAME',**p)])),
        ('ingredient.csv',csv_source('ingredients',[dict(source_business_key='LIQUID',**i)]))])
    review_batch(c,ident,creations={'FULL-NAME':('product',p),'LIQUID':('ingredient',i)})
    complete(c,ident)
    with Session(c[0][1]) as fresh:
        product=fresh.scalar(select(Product));ingredient=fresh.scalar(select(Ingredient))
        assert product.sku is None and ingredient.sku is None
        return dict(product_id=str(product.id),ingredient_id=str(ingredient.id),quantity_basis='PER_SERVING',
            quantity='2.5000000000000001E-2',unit='ml',yield_quantity='10',yield_unit='cup',
            process_loss_rate='0.2',version=1,effective_from='2026-01-01',effective_to=None)


def source(record, *, cell_kind='numeric', formula=False):
    fields=list(record)
    header='<row r="1">'+''.join(f'<c r="{chr(65+n)}1" t="inlineStr"><is><t>recipes.{key}</t></is></c>' for n,key in enumerate(fields))+'</row>'
    body=[]
    for n,(key,value) in enumerate(record.items()):
        address=chr(65+n)+'2'
        raw=escape(str(value)) if value is not None else ''
        if key=='quantity' and cell_kind=='numeric':
            body.append(f'<c r="{address}">'+('<f>1+1</f>' if formula else '')+f'<v>{raw}</v></c>')
        else:
            body.append(f'<c r="{address}" t="inlineStr"><is><t>{raw}</t></is></c>')
    return workbook(header+'<row r="2">'+''.join(body)+'</row>')


def test_numeric_rule_owner_commit_exact_loss_bom_replay_and_stale_change(fresh_store):
    c=fresh_store;record=catalog(c)
    # Existing canonical lexical input works before opting into the new rule.
    record['quantity']='0.125'
    ident=analyzed_files(c,[('independent.xlsx',source(record))])
    review_batch(c,ident,source_context=CONTEXT)
    old=previewed(c,ident);confirmed=confirm(c,ident,old)
    assert confirmed.status_code==200
    context={**CONTEXT,'recipe_quantity_format':'OOXML_FINITE_DECIMAL'}
    declare_context(c,ident,context)
    state=summary(c,ident)
    assert not state['can_preview'] and not state['binding_refs']
    assert state['profile_proposals'][0]['spec']['normalizations'][0]['kind']=='numeric_format'
    assert commit(c,ident,old,confirmed.json()['data']['import_revision']).status_code==412
    activate(c,ident)
    # A separate export contains a new exact quantity; current source is re-read.
    record['quantity']='2.5000000000000001E-2'
    second=analyzed_files(c,[('independent-new.xlsx',source(record))])
    declare_context(c,second,context)
    assert summary(c,second)['can_preview']
    read=previewed(c,second)
    row,=read['preview']['rows'];assert not row['blockers']
    assert row['after']['lines'][0]['quantity']=='0.25000000000000001'
    assert row['after']['process_loss_rate']=='0.2' and not row['warnings']
    assert row['line_provenance'][0]['provenance']['quantity']['source_value']==record['quantity']
    confirm_response=confirm(c,second,read);assert confirm_response.status_code==200
    with Session(c[0][1]) as fresh:assert fresh.scalar(select(func.count()).select_from(Recipe))==0
    key=str(uuid4());revision=confirm_response.json()['data']['import_revision']
    accepted=commit(c,second,read,revision,key=key);finished(c,second,accepted)
    assert commit(c,second,read,revision,key=key).json()['data']==accepted.json()['data']
    with Session(c[0][1]) as fresh:
        r=fresh.scalar(select(Recipe));line=fresh.scalar(select(RecipeLine))
        assert line.quantity==Decimal('0.25000000000000001') and r.process_loss_rate==Decimal('0.2')
        saved=DatedRecipe(r.id,r.product_id,r.effective_from,r.effective_to,r.yield_quantity,r.process_loss_rate,
            (BOMLine(line.ingredient_id,line.unit,line.quantity),))
    bom=expand_dated_bom((DemandPoint('BASE',UUID(record['product_id']),date(2026,7,8),Decimal(40)),),(saved,))
    assert not bom.gaps and bom.totals[0].quantity==Decimal('1.25000000000000005')


@pytest.mark.parametrize('raw,extra,code',[
    ('1e-2',dict(cell_kind='text'),'OOXML_NUMERIC_SOURCE_REQUIRED'),
    ('1e-2',dict(formula=True),'OOXML_NUMERIC_SOURCE_REQUIRED'),
    ('0',{},'INVALID_SOURCE_VALUE'),('-1e-2',{},'INVALID_OOXML_NUMERIC_QUANTITY'),
    ('1e999999',{},'OOXML_NUMERIC_RESOURCE_LIMIT'),
])
def test_numeric_bad_sources_never_commit(fresh_store,raw,extra,code):
    c=fresh_store;record=catalog(c);record['quantity']=raw
    ident=analyzed_files(c,[('different.xlsx',source(record,**extra))])
    review_batch(c,ident,source_context={**CONTEXT,'recipe_quantity_format':'OOXML_FINITE_DECIMAL'})
    read=previewed(c,ident)
    assert code in {b['code'] for row in read['preview']['rows'] for b in row['blockers']}
    assert confirm(c,ident,read).status_code==409
    with Session(c[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(Recipe))==0


def test_numeric_rule_cannot_be_enabled_for_csv(fresh_store):
    c=fresh_store;record=catalog(c)
    ident=analyzed_files(c,[('not-xlsx.csv',csv_source('recipes',[record]))])
    issue=next(i for i in listing(c,ident) if i['issue_type']=='source_context')
    result=mapping(c,ident,issue,{'resolution':dict(kind='source_context',**CONTEXT,
        recipe_quantity_format='OOXML_FINITE_DECIMAL',evidence_reference='Must reject CSV scope')})
    assert result.status_code==409 and result.json()['error']['code']=='OOXML_RECIPE_QUANTITY_SCOPE_REQUIRED'
